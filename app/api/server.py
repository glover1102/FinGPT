import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, time as dt_time, timezone
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.api.heatmap_universe import (
    HEATMAP_UNIVERSE_VERSION,
    US_EQUITY_HEATMAP_UNIVERSE,
)
from app.api.openbb_agent import router as openbb_agent_router
from core.schemas.request import (
    COMPARE_MAX_CONCURRENCY,
    COMPARE_MAX_TICKERS,
    DEFAULT_COLLECTION_SOURCES,
    DISABLED_COLLECTION_SOURCES,
    KNOWN_COLLECTION_SOURCES,
    PRIMARY_COLLECTION_SOURCES,
    AnalysisRequest,
    CompareRequest,
    UniversalRequest,
)
from core.config.settings import load_settings
from core.schemas.response import AnalysisResponse, CompareResponse, ExecutionMeta
from core.schemas.portfolio import PortfolioRiskRequest, PortfolioRiskResponse
from core.schemas.topic import TopicResponse
from core.utils.asset_classifier import classify
from core.utils.logger import get_logger
from core.preflight import run_preflight
from core.utils.eval_dashboard import load_eval_dashboard
from core.utils.qdrant_admin import get_collection_info, purge_points
from pipelines.collect.cache import get_cache as get_collection_cache
from pipelines.collect.google_news_rss import collect_news_from_google_rss
from pipelines.backtest.engine import BacktestConfig, run_backtest, run_momentum_ranking_backtest, run_multi_asset_backtest
from pipelines.data_mart.storage.repository import data_health as data_mart_health, get_prices as data_mart_get_prices
from pipelines.output.exporters import response_to_csv, response_to_jsonl
from pipelines.orchestration.dispatch import dispatch_async
from pipelines.orchestration.research_pipeline import run_pipeline_async
from pipelines.analyze.portfolio_quant import analyze_portfolio_risk
from pipelines.portfolio.optimizer import optimize_portfolio
from pipelines.output.run_history import (
    get_run as history_get_run,
    list_runs as history_list_runs,
    ticker_summary as history_ticker_summary,
)
from pipelines.watchlist import store as watchlist_store
from pipelines.watchlist.scheduler import get_scheduler as get_watchlist_scheduler

# Preflight exercises real network dependencies (Qdrant, Ollama, FMP, SEC, YF).
# We cache the most recent report for a short TTL so the UI status badge can
# poll aggressively without thrashing external services.
_PREFLIGHT_CACHE_TTL_SEC = 15
_preflight_cache: dict[str, Any] = {"ts": 0.0, "report": None}
_preflight_lock = asyncio.Lock()
_DASHBOARD_EQUITY_HEATMAP_CACHE_TTL_SEC = 60
_dashboard_equity_heatmap_cache: dict[str, Any] = {"ts": 0.0, "payload": None}

logger = get_logger("api.server")
_settings = load_settings()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "app" / "web"
OUTPUTS_DIR = PROJECT_ROOT / "data" / "outputs"

SUPPORTED_INFERENCE_ROUTES = (
    "qwen",
    "mistral",
    "ollama",
    "primary",
    "fingpt",
    "llama-2",
    "gemma",
    "gemma-experimental",
)

_NON_COMPANY_DIRECT_ASSET_CLASSES = {"bond_etf", "commodity_etf", "forex", "futures", "crypto"}


class BacktestRunRequest(BaseModel):
    ticker: str | None = Field(default=None)
    tickers: list[str] = Field(default_factory=list)
    strategy: str = Field(default="buy_and_hold")
    lookback_days: int = Field(default=252, ge=2, le=5000)
    start_date: str | None = Field(default=None)
    end_date: str | None = Field(default=None)
    short_window: int = Field(default=20, ge=1, le=252)
    long_window: int = Field(default=50, ge=2, le=756)
    top_n: int = Field(default=1, ge=1, le=50)
    rebalance_every: int = Field(default=21, ge=1, le=252)
    transaction_cost_bps: float = Field(default=5.0, ge=0, le=1000)
    slippage_bps: float = Field(default=2.0, ge=0, le=1000)
    initial_capital: float = Field(default=1.0, gt=0)
    price_rows: list[dict[str, Any]] | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def _clean_ticker(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip().upper()
        return cleaned or None

    @field_validator("tickers", mode="before")
    @classmethod
    def _clean_tickers(cls, value: Any) -> list[str]:
        return _clean_ticker_list(value)

    @field_validator("strategy", mode="before")
    @classmethod
    def _clean_strategy(cls, value: Any) -> str:
        return str(value or "buy_and_hold").strip().lower()

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _clean_date(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None


class PortfolioOptimizeRequest(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    method: str = Field(default="equal_weight")
    lookback_days: int = Field(default=252, ge=2, le=5000)
    start_date: str | None = Field(default=None)
    end_date: str | None = Field(default=None)
    max_weight: float = Field(default=1.0, gt=0, le=1.0)
    returns_by_asset: dict[str, list[float]] | None = None

    @field_validator("tickers", mode="before")
    @classmethod
    def _clean_tickers(cls, value: Any) -> list[str]:
        return _clean_ticker_list(value)

    @field_validator("method", mode="before")
    @classmethod
    def _clean_method(cls, value: Any) -> str:
        return str(value or "equal_weight").strip().lower()

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _clean_date(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None


def _clean_ticker_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.replace(",", " ").split()
    else:
        raw = list(value)
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        ticker = str(item or "").strip().upper()
        if ticker and ticker not in seen:
            out.append(ticker)
            seen.add(ticker)
    return out

_EQUITY_HEATMAP_UNIVERSE = US_EQUITY_HEATMAP_UNIVERSE
_EQUITY_HEATMAP_BATCH_SIZE = 60


def _validation_422(message: str, code: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, "message": message})


def _validate_question_present(question: str | None) -> None:
    if not str(question or "").strip():
        raise _validation_422("질문을 입력해야 합니다.", "question_required")


def _validate_direct_ticker_request(request: AnalysisRequest) -> None:
    _validate_question_present(request.question)
    if not request.ticker:
        raise _validation_422(
            "단일 종목 분석 endpoint는 ticker가 필요합니다. ticker 없이 일반 질의를 하려면 /api/v1/research/universal 을 사용하세요.",
            "ticker_required_for_single_ticker_endpoint",
        )


def _validate_universal_request(request: UniversalRequest) -> None:
    _validate_question_present(request.question)
    if request.mode_hint == "ticker" and not request.ticker:
        raise _validation_422(
            "종목 분석 모드에서는 ticker 입력이 필요합니다. ticker 없이 일반 질의를 하려면 mode_hint=auto 또는 topic을 사용하세요.",
            "ticker_required_for_ticker_mode",
        )


def _direct_non_company_response(request: AnalysisRequest) -> AnalysisResponse | None:
    if not request.ticker:
        return None
    profile = classify(request.ticker)
    if profile.asset_class not in _NON_COMPANY_DIRECT_ASSET_CLASSES:
        return None
    return AnalysisResponse(
        ticker=profile.ticker,
        question=request.question,
        status="failed",
        error_metadata=(
            f"{profile.ticker}는 {profile.asset_class} 유형이라 단일 종목 endpoint가 아니라 "
            "/api/v1/research/universal topic 경로로 분석해야 합니다."
        ),
        summary="요청한 ticker는 개별 기업 종목이 아니므로 topic/universal 분석 경로가 필요합니다.",
        sentiment="Neutral",
        confidence=0.0,
        conclusion="UI에서는 자동/주제 모드로 실행하면 거시·시장구조 playbook으로 처리됩니다.",
        execution_meta=ExecutionMeta(
            extras={
                "route_hint": "use_universal_topic",
                "asset_class": profile.asset_class,
                "direct_endpoint_guard": True,
            }
        ),
    )

async def _start_watchlist_scheduler() -> None:
    """Spin up the in-process watchlist scheduler once the event loop is ready."""
    try:
        await get_watchlist_scheduler().start()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to start watchlist scheduler: {exc}")


async def _stop_watchlist_scheduler() -> None:
    try:
        await get_watchlist_scheduler().stop()
    except Exception:  # noqa: BLE001
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _start_watchlist_scheduler()
    try:
        yield
    finally:
        await _stop_watchlist_scheduler()


app = FastAPI(
    title="FinGPT Local Research Assistant",
    description="Local, privacy-preserving financial research API + Web UI.",
    version="1.1.0",
    lifespan=lifespan,
)

_raw_origins = (_settings.web_cors_origins or "").strip()
_cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
if bool(getattr(_settings, "openbb_agent_enabled", False)):
    for origin in str(getattr(_settings, "openbb_agent_allow_origins", "") or "").split(","):
        origin = origin.strip()
        if origin and origin not in _cors_origins:
            _cors_origins.append(origin)
_allow_any = _cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=None if not _allow_any else ".*",
    allow_credentials=not _allow_any,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(openbb_agent_router)


@app.post("/api/v1/research", response_model=AnalysisResponse)
async def analyze_research_legacy(request: AnalysisRequest):
    return await analyze_research(request)


@app.post("/api/v1/research/analyze", response_model=AnalysisResponse)
async def analyze_research(request: AnalysisRequest):
    logger.info(f"Received API request for ticker: {request.ticker}")
    _validate_direct_ticker_request(request)
    guarded = _direct_non_company_response(request)
    if guarded is not None:
        return guarded
    try:
        response = await run_pipeline_async(request)
        if response.status == "failed":
            logger.error(f"Request finalized with failed state: {response.error_metadata}")
        return response
    except Exception as e:
        logger.error(f"Unhandled exception during async API execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/research/universal")
async def universal_research(request: UniversalRequest) -> Dict[str, Any]:
    logger.info("[UNIVERSAL] Received request ticker=%s mode_hint=%s", request.ticker, request.mode_hint)
    _validate_universal_request(request)
    try:
        result = await dispatch_async(request)
        payload = result.model_dump(mode="json")
        if isinstance(result, TopicResponse):
            payload["mode"] = result.mode
        elif isinstance(result, CompareResponse):
            payload["mode"] = "multi_ticker"
        else:
            payload["mode"] = "single_ticker"
        return payload
    except Exception as e:
        logger.error(f"Unhandled exception during universal API execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/research/compare", response_model=CompareResponse)
async def compare_research(request: CompareRequest) -> CompareResponse:
    """Run the same question across N tickers and return a consolidated bundle.

    Individual ticker failures are surfaced as ``status='failed'`` entries rather
    than aborting the whole batch, so the comparison view always has something
    to render. A semaphore caps parallelism to protect local Ollama/FMP.
    """
    started = time.time()
    # Dedupe while preserving input order so the UI can render columns
    # deterministically even when the user pastes repeats.
    seen: set[str] = set()
    tickers: list[str] = []
    for raw in request.tickers:
        t = (raw or "").strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        tickers.append(t)
    if len(tickers) < 2:
        raise HTTPException(status_code=400, detail="At least 2 distinct tickers are required.")
    if len(tickers) > COMPARE_MAX_TICKERS:
        raise HTTPException(status_code=400, detail=f"Up to {COMPARE_MAX_TICKERS} tickers per compare request.")

    concurrency = max(1, min(request.concurrency, COMPARE_MAX_CONCURRENCY, len(tickers)))
    settings = load_settings()
    model_name = str(request.model or settings.primary_model or "").lower()
    is_local_ollama = "localhost" in settings.ollama_base_url or "127.0.0.1" in settings.ollama_base_url
    if is_local_ollama and any(marker in model_name for marker in ("qwen", "mistral", "fingpt")):
        # Local Ollama 7B-class models are not reliable under concurrent JSON
        # generation. Keep compare deterministic by serializing LLM-heavy runs.
        concurrency = 1
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(ticker: str) -> tuple[str, AnalysisResponse]:
        async with semaphore:
            try:
                sub_request = AnalysisRequest(
                    ticker=ticker,
                    question=request.question,
                    sources=list(request.sources),
                    lookback_days=request.lookback_days,
                    top_k=request.top_k,
                    model=request.model,
                )
                resp = await run_pipeline_async(sub_request)
                return ticker, resp
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[COMPARE] {ticker} failed: {exc}")
                return ticker, AnalysisResponse(
                    ticker=ticker,
                    question=request.question,
                    status="failed",
                    error_metadata=str(exc),
                    summary=f"{ticker} 실행 실패: {exc}",
                    sentiment="Neutral",
                    conclusion="비교 분석 중 파이프라인 예외가 발생했습니다.",
                )

    pairs = await asyncio.gather(*(run_one(t) for t in tickers))
    results = {t: r for t, r in pairs}
    return CompareResponse(
        question=request.question,
        tickers=tickers,
        results=results,
        elapsed_s=round(time.time() - started, 2),
        concurrency=concurrency,
    )


@app.post("/api/v1/research/portfolio/risk", response_model=PortfolioRiskResponse)
async def portfolio_risk(request: PortfolioRiskRequest) -> PortfolioRiskResponse:
    """Deterministic portfolio concentration, factor exposure, and stress analysis."""

    return await asyncio.to_thread(analyze_portfolio_risk, request)


@app.get("/api/v1/data/health")
async def data_health() -> Dict[str, Any]:
    """Structured data mart health, update history, provider status, and quality checks."""

    payload = await asyncio.to_thread(data_mart_health)
    provider_rows = payload.get("recent_provider_status") or []
    quality_rows = payload.get("recent_quality_checks") or []
    failed = [row for row in provider_rows if str(row.get("status") or "").lower() in {"failed", "error"}]
    stale = [row for row in quality_rows if str(row.get("status") or "").lower() in {"warn", "fail"}]
    payload["summary"] = {
        "provider_rows": len(provider_rows),
        "failed_provider_rows": len(failed),
        "quality_rows": len(quality_rows),
        "stale_or_failed_quality_rows": len(stale),
        "decision_status": "failed" if failed else ("partial" if stale else "ok"),
    }
    return payload


@app.get("/api/v1/data/prices/{ticker}")
async def data_prices(ticker: str, limit: int = 252) -> Dict[str, Any]:
    """Return normalized daily prices from the structured data mart."""

    clean_ticker = str(ticker or "").strip().upper()
    if not clean_ticker:
        raise HTTPException(status_code=422, detail="ticker is required")
    limit = max(1, min(int(limit or 252), 5000))
    rows = await asyncio.to_thread(data_mart_get_prices, clean_ticker, limit=limit)
    latest = rows[-1] if rows else None
    return {
        "status": "ok" if rows else "empty",
        "ticker": clean_ticker,
        "count": len(rows),
        "latest": latest,
        "items": rows,
    }


@app.post("/api/v1/backtest/run")
async def backtest_run(request: BacktestRunRequest) -> Dict[str, Any]:
    """Run a deterministic backtest against data-mart prices or explicit request rows."""

    rows = list(request.price_rows or [])
    data_status = "request_rows" if rows else "data_mart"
    if not rows:
        tickers = request.tickers or ([request.ticker] if request.ticker else [])
        if not tickers:
            raise HTTPException(status_code=422, detail="ticker, tickers, or price_rows is required")
        rows_by_asset: dict[str, list[dict[str, Any]]] = {}
        missing: list[str] = []
        for ticker in tickers:
            asset_rows = await asyncio.to_thread(data_mart_get_prices, ticker, limit=request.lookback_days)
            asset_rows = _filter_price_rows(asset_rows, start_date=request.start_date, end_date=request.end_date)
            rows_by_asset[ticker] = asset_rows
            if len(asset_rows) < 2:
                missing.append(ticker)
        config = BacktestConfig(
            strategy=request.strategy,
            short_window=request.short_window,
            long_window=request.long_window,
            transaction_cost_bps=request.transaction_cost_bps,
            slippage_bps=request.slippage_bps,
            initial_capital=request.initial_capital,
        )
        try:
            if request.strategy == "momentum_ranking" and len(tickers) > 1:
                result = await asyncio.to_thread(
                    run_momentum_ranking_backtest,
                    rows_by_asset,
                    lookback=request.short_window,
                    top_n=min(request.top_n, len(tickers)),
                    rebalance_every=request.rebalance_every,
                    config=config,
                )
                result["asset_results"] = {}
            else:
                asset_results = {
                    ticker: await asyncio.to_thread(run_backtest, asset_rows, config)
                    for ticker, asset_rows in rows_by_asset.items()
                }
                if len(asset_results) == 1:
                    result = next(iter(asset_results.values()))
                else:
                    result = await asyncio.to_thread(run_multi_asset_backtest, rows_by_asset, config)
                    result["summary_policy"] = "reported metrics come from one aligned multi-asset portfolio equity curve"
                result["asset_results"] = asset_results
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        result["ticker"] = request.ticker or (tickers[0] if len(tickers) == 1 else None)
        result["tickers"] = tickers
        result["missing_assets"] = missing
        result["price_counts"] = {ticker: len(asset_rows) for ticker, asset_rows in rows_by_asset.items()}
        result["data_status"] = "partial" if missing else data_status
        result["requested_range"] = {"start": request.start_date, "end": request.end_date, "lookback_days": request.lookback_days}
        return result
    config = BacktestConfig(
        strategy=request.strategy,
        short_window=request.short_window,
        long_window=request.long_window,
        transaction_cost_bps=request.transaction_cost_bps,
        slippage_bps=request.slippage_bps,
        initial_capital=request.initial_capital,
    )
    try:
        result = await asyncio.to_thread(run_backtest, rows, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["ticker"] = request.ticker
    result["tickers"] = request.tickers or ([request.ticker] if request.ticker else [])
    result["price_count"] = len(rows)
    result["data_status"] = data_status if rows else "empty"
    result["requested_range"] = {"start": request.start_date, "end": request.end_date, "lookback_days": request.lookback_days}
    return result


@app.post("/api/v1/portfolio/optimize")
async def portfolio_optimize(request: PortfolioOptimizeRequest) -> Dict[str, Any]:
    """Optimize portfolio weights from supplied returns or data-mart daily prices."""

    returns_by_asset = dict(request.returns_by_asset or {})
    missing: list[str] = []
    if not returns_by_asset:
        if not request.tickers:
            raise HTTPException(status_code=422, detail="tickers or returns_by_asset is required")
        for ticker in request.tickers:
            rows = await asyncio.to_thread(data_mart_get_prices, ticker, limit=request.lookback_days)
            rows = _filter_price_rows(rows, start_date=request.start_date, end_date=request.end_date)
            returns = _returns_from_price_rows(rows)
            if returns:
                returns_by_asset[ticker] = returns
            else:
                missing.append(ticker)
    try:
        result = await asyncio.to_thread(
            optimize_portfolio,
            returns_by_asset,
            method=request.method,
            max_weight=request.max_weight,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["missing_assets"] = missing
    result["data_status"] = "request_returns" if request.returns_by_asset else ("partial" if missing else "data_mart")
    result["tickers"] = request.tickers
    result["date_range"] = {"start": request.start_date, "end": request.end_date, "lookback_days": request.lookback_days}
    result["return_counts"] = {ticker: len(returns) for ticker, returns in returns_by_asset.items()}
    return result


def _filter_price_rows(
    rows: list[dict[str, Any]],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    if not start_date and not end_date:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        date = str(row.get("date") or "")
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        out.append(row)
    return out


def _returns_from_price_rows(rows: list[dict[str, Any]]) -> list[float]:
    returns: list[float] = []
    prices: list[float] = []
    for row in sorted(rows, key=lambda item: str(item.get("date") or "")):
        value = row.get("adjusted_close")
        if value is None:
            value = row.get("close")
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price > 0:
            prices.append(price)
    for idx in range(1, len(prices)):
        returns.append(prices[idx] / prices[idx - 1] - 1.0)
    return returns


def _sse_pack(event: str, data: Any) -> bytes:
    """Format a Server-Sent Events frame. Data is JSON-encoded for structured events."""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


async def _stream_with_runner(http_request: Request, runner):
    import queue as _threadqueue

    q: _threadqueue.Queue = _threadqueue.Queue(maxsize=512)
    _SENTINEL = object()

    def sink(event: dict[str, Any]) -> None:
        try:
            q.put_nowait(event)
        except _threadqueue.Full:
            pass

    async def run_and_enqueue():
        try:
            response = await runner(sink)
            payload = response.model_dump(mode="json")
            if isinstance(response, TopicResponse):
                payload["mode"] = response.mode
            elif isinstance(response, CompareResponse):
                payload["mode"] = "multi_ticker"
            else:
                payload["mode"] = "single_ticker"
            q.put_nowait({"event": "result", "payload": payload})
        except Exception as exc:
            logger.error(f"[SSE] pipeline failed: {exc}")
            q.put_nowait({"event": "pipeline_failed", "reason": str(exc)})
        finally:
            q.put_nowait(_SENTINEL)

    async def event_generator():
        task = asyncio.create_task(run_and_enqueue())
        try:
            yield _sse_pack("stream_open", {"ts": time.time()})
            request_stage_started = time.time()
            yield _sse_pack("stage_started", {"stage": "request"})
            yield _sse_pack(
                "stage_completed",
                {"stage": "request", "duration_s": round(time.time() - request_stage_started, 3)},
            )

            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 15.0)
                except _threadqueue.Empty:
                    if await http_request.is_disconnected():
                        break
                    yield b": heartbeat\n\n"
                    continue

                if item is _SENTINEL:
                    break

                event_name = item.get("event", "message")
                yield _sse_pack(event_name, item.get("payload", item))

                if await http_request.is_disconnected():
                    break
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/v1/research/stream")
async def research_stream(request: AnalysisRequest, http_request: Request):
    """Run the full research pipeline and stream stage progress via SSE.

    Clients receive granular events (`stage_started`, `stage_completed`,
    `pipeline_completed`, `pipeline_failed`) so the UI can show real progress
    rather than a simulated timeline. The final `result` event carries the
    complete ``AnalysisResponse`` payload identical to the ``/analyze`` endpoint.
    """
    logger.info(f"[SSE] Stream request for ticker: {request.ticker}")
    _validate_direct_ticker_request(request)
    guarded = _direct_non_company_response(request)
    if guarded is not None:
        async def immediate(_sink):
            return guarded

        return await _stream_with_runner(http_request, immediate)
    return await _stream_with_runner(
        http_request,
        lambda sink: run_pipeline_async(request, event_sink=sink),
    )


@app.post("/api/v1/research/universal/stream")
async def universal_research_stream(request: UniversalRequest, http_request: Request):
    logger.info("[UNIVERSAL_SSE] Received request ticker=%s mode_hint=%s", request.ticker, request.mode_hint)
    _validate_universal_request(request)
    return await _stream_with_runner(
        http_request,
        lambda sink: dispatch_async(request, event_sink=sink),
    )


# Clean UTF-8 overrides for validation helpers. They intentionally live after
# route definitions because FastAPI resolves these globals when requests run.
def _validate_question_present(question: str | None) -> None:
    if not str(question or "").strip():
        raise _validation_422("질문을 입력해야 합니다.", "question_required")


def _validate_direct_ticker_request(request: AnalysisRequest) -> None:
    _validate_question_present(request.question)
    if not request.ticker:
        raise _validation_422(
            "단일 종목 endpoint는 ticker가 필요합니다. ticker 없는 일반 질의는 /api/v1/research/universal/stream을 사용하세요.",
            "ticker_required_for_single_ticker_endpoint",
        )


def _validate_universal_request(request: UniversalRequest) -> None:
    _validate_question_present(request.question)
    if request.mode_hint == "ticker" and not request.ticker:
        raise _validation_422(
            "종목 모드에서는 ticker가 필요합니다. ticker 없이 질문하려면 자동 또는 주제 모드를 사용하세요.",
            "ticker_required_for_ticker_mode",
        )


def _direct_non_company_response(request: AnalysisRequest) -> AnalysisResponse | None:
    if not request.ticker:
        return None
    profile = classify(request.ticker)
    if profile.asset_class not in _NON_COMPANY_DIRECT_ASSET_CLASSES:
        return None
    return AnalysisResponse(
        ticker=profile.ticker,
        question=request.question,
        status="failed",
        error_metadata=(
            f"{profile.ticker}는 {profile.asset_class} 유형입니다. 단일 기업 endpoint가 아니라 "
            "/api/v1/research/universal/stream topic 경로로 분석해야 합니다."
        ),
        summary="요청한 ticker는 개별 기업 종목이 아니므로 topic/universal 분석 경로가 필요합니다.",
        sentiment="Neutral",
        confidence=0.0,
        conclusion="UI에서 자동 또는 주제 모드로 실행하면 거시·시장구조 playbook으로 처리합니다.",
        execution_meta=ExecutionMeta(
            extras={
                "route_hint": "use_universal_topic",
                "asset_class": profile.asset_class,
                "direct_endpoint_guard": True,
                "error_type": "validation_error",
            }
        ),
    )


def _ui_model_options() -> list[dict[str, Any]]:
    options = [
        {
            "id": "qwen",
            "label": f"{getattr(_settings, 'primary_model', 'qwen2.5:7b')} (Ollama · 기본)",
            "role": "primary",
            "enabled": True,
        }
    ]
    if bool(getattr(_settings, "enable_experimental_fallback", False)):
        options.append(
            {
                "id": "gemma-experimental",
                "label": f"{getattr(_settings, 'experimental_fallback_model', 'gemma4:e4b')} (fallback)",
                "role": "fallback",
                "enabled": True,
            }
        )
    return options


def _ui_presets() -> list[dict[str, str]]:
    return [
        {"id": "risk", "label": "단기 리스크", "question": "현재 드러나는 주요 단기 리스크와 시장이 과소평가하는 하방 시나리오는 무엇인가요?"},
        {"id": "catalyst", "label": "성장 촉매", "question": "향후 6~12개월 동안 가격을 움직일 핵심 상승 촉매와 검증 지표는 무엇인가요?"},
        {"id": "thesis", "label": "12개월 투자 가설", "question": "최신 공개 정보와 정량 지표를 기준으로 12개월 투자 가설을 정리해주세요."},
        {"id": "earnings", "label": "실적 신호", "question": "최근 실적과 가이던스에서 확인되는 매출, 마진, 비용 구조의 핵심 신호를 요약해주세요."},
        {"id": "competitive", "label": "경쟁 구도", "question": "경쟁 구도가 어떻게 변하고 있고, 가격 결정력과 시장점유율에는 어떤 영향을 주나요?"},
    ]


@app.get("/api/v1/config")
async def get_config() -> Dict[str, Any]:
    """Expose pipeline knobs so the UI stays in sync with the backend contract."""
    return {
        "models": _ui_model_options(),
        "default_model": "qwen",
        "output_language": getattr(_settings, "output_language", "ko"),
        "risk_engine": getattr(_settings, "risk_engine", "heuristic"),
        "sources": {
            "known": list(KNOWN_COLLECTION_SOURCES),
            "default": list(DEFAULT_COLLECTION_SOURCES),
            "primary": list(PRIMARY_COLLECTION_SOURCES),
            "disabled": list(DISABLED_COLLECTION_SOURCES),
        },
        "limits": {
            "lookback_days": {"min": 1, "max": 365, "default": 60},
            "top_k": {"min": 1, "max": 20, "default": 10},
            "compare": {
                "max_tickers": COMPARE_MAX_TICKERS,
                "max_concurrency": COMPARE_MAX_CONCURRENCY,
                "default_concurrency": 2,
            },
        },
        "topic_mode_enabled": bool(getattr(_settings, "topic_mode_enabled", True)),
        "presets": _ui_presets(),
        "dashboard": {
            "news_endpoint": "/api/v1/dashboard/news",
            "tradingview_enabled": True,
        },
    }


@app.get("/api/v1/dashboard/news")
async def dashboard_news(limit: int = 20) -> Dict[str, Any]:
    """News cards for the UI home dashboard.

    The dashboard is a front-page decision surface, so it should favor broad,
    reputable market coverage over issuer marketing pages or thin ETF blogs.
    Google News RSS remains the key-less transport, but selection is ranked by
    source quality, recency, and issue coverage.
    """
    watchlist: list[dict[str, Any]] = [
        {
            "symbol": "MARKET",
            "query": '("Wall Street" OR "S&P 500" OR "stock market") (Reuters OR CNBC OR Bloomberg OR "Wall Street Journal" OR "Financial Times")',
            "category": "equity_index",
            "lookback": 7,
        },
        {"symbol": "SPY", "query": None, "category": "equity_index", "lookback": 7},
        {"symbol": "QQQ", "query": None, "category": "equity_index", "lookback": 7},
        {
            "symbol": "MACRO",
            "query": '("Federal Reserve" OR inflation OR CPI OR "Treasury yields" OR "rate cuts") (Reuters OR CNBC OR Bloomberg OR "New York Times" OR "Financial Times")',
            "category": "macro_policy",
            "lookback": 10,
        },
        {
            "symbol": "RATES",
            "query": 'site:cnbc.com "Treasury yields" when:10d',
            "category": "rates_credit",
            "lookback": 10,
        },
        {
            "symbol": "BOND_MARKET",
            "query": 'site:bloomberg.com ("Treasury yields" OR "Bond Traders" OR "bond market") when:10d',
            "category": "rates_credit",
            "lookback": 10,
        },
        {"symbol": "TLT", "query": '"Treasury yields" OR "long bond ETF" OR TLT', "category": "rates_credit", "lookback": 10},
        {
            "symbol": "CREDIT",
            "query": 'site:bloomberg.com ("credit markets" OR "credit spreads" OR "high yield bonds") when:14d',
            "category": "rates_credit",
            "lookback": 14,
        },
        {
            "symbol": "CREDIT_REUTERS",
            "query": 'site:reuters.com ("credit spreads" OR "corporate debt" OR "high yield bonds") when:14d',
            "category": "rates_credit",
            "lookback": 14,
        },
        {"symbol": "HYG", "query": '"credit spreads" OR "high yield bonds" OR HYG', "category": "rates_credit", "lookback": 14},
        {
            "symbol": "AI_SEMIS",
            "query": '("AI chips" OR semiconductors OR Nvidia OR "AI capex") (Reuters OR CNBC OR Bloomberg OR "Financial Times")',
            "category": "ai_semis",
            "lookback": 10,
        },
        {
            "symbol": "EARNINGS",
            "query": '("earnings season" OR "earnings outlook" OR margins OR guidance) (Reuters OR CNBC OR Bloomberg OR "Wall Street Journal")',
            "category": "earnings",
            "lookback": 10,
        },
        {"symbol": "GLD", "query": '"gold price" OR "gold futures" OR "real yields gold" OR GLD', "category": "commodity", "lookback": 14},
        {"symbol": "OIL", "query": '"oil prices" OR "crude oil" OR OPEC OR "energy market"', "category": "commodity", "lookback": 14},
        {"symbol": "BTC-USD", "query": '"Bitcoin price" OR "Bitcoin ETF" OR cryptocurrency OR "crypto market"', "category": "crypto", "lookback": 14},
    ]
    max_items = max(6, min(int(limit or 20), 30))

    major_sources = (
        "reuters",
        "bloomberg",
        "cnbc",
        "wall street journal",
        "wsj",
        "financial times",
        "new york times",
        "nytimes",
        "associated press",
        "ap news",
        "barron's",
        "barrons",
    )
    market_sources = (
        "marketwatch",
        "yahoo finance",
        "axios",
        "fortune",
        "the economist",
        "seeking alpha",
    )
    low_priority_sources = (
        "invesco",
        "etf database",
        "tipranks",
        "motley fool",
        "moomoo",
        "minichart",
        "investing.com",
    )
    topic_keywords = {
        "equity_index": ("stock", "s&p", "nasdaq", "wall street", "equity", "market"),
        "macro_policy": ("inflation", "fed", "federal reserve", "consumer", "sentiment", "jobs", "cpi", "rates", "gdp"),
        "rates_credit": ("treasury", "yield", "bond", "credit", "spread", "debt", "fed", "rate", "default", "loan"),
        "ai_semis": ("ai", "chip", "semiconductor", "nvidia", "intel", "huawei", "capex"),
        "earnings": ("earnings", "profit", "margin", "guidance", "revenue", "quarter"),
        "commodity": ("oil", "crude", "gold", "opec", "commodity", "energy"),
        "crypto": ("bitcoin", "crypto", "cryptocurrency", "etf", "ethereum", "wallet"),
    }

    def _published_ts(value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def _repair_feed_text(value: Any) -> str:
        text = str(value or "")
        if not text or not any(marker in text for marker in ("â", "Ã", "Â")):
            return text
        try:
            repaired = text.encode("latin1").decode("utf-8")
            return repaired if repaired else text
        except Exception:
            return text

    def _source_score(item: dict[str, Any]) -> int:
        haystack = " ".join([
            str(item.get("source") or ""),
            str(item.get("title") or ""),
            str(item.get("url") or ""),
        ]).lower()
        if any(token in haystack for token in major_sources):
            return 0
        if any(token in haystack for token in market_sources):
            return 1
        if any(token in haystack for token in low_priority_sources):
            return 3
        return 2

    def _topic_score(entry: dict[str, Any], item: dict[str, Any]) -> int:
        category = str(entry.get("category") or "market")
        title = str(item.get("title") or "").lower()
        keywords = topic_keywords.get(category, ())
        return 0 if any(keyword in title for keyword in keywords) else 1

    def collect_one(entry: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            _, docs = collect_news_from_google_rss(
                str(entry["symbol"]),
                int(entry.get("lookback") or 10),
                limit=8,
                query_override=entry.get("query"),
                strict_purity=entry.get("query") is None,
            )
            return docs
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DASHBOARD_NEWS] %s failed: %s", entry.get("symbol"), exc)
            return []

    groups = await asyncio.gather(*(asyncio.to_thread(collect_one, entry) for entry in watchlist))
    seen: set[str] = set()

    def make_item(entry: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any] | None:
        symbol = str(entry["symbol"])
        title = _repair_feed_text(doc.get("title")).strip()
        url = str(doc.get("url") or "").strip()
        key = url or title.lower()
        if not title or key in seen:
            return None
        seen.add(key)
        published_at = doc.get("published_at") or doc.get("date") or ""
        item = {
            "symbol": symbol,
            "title": title,
            "source": _repair_feed_text(doc.get("source") or "Google News"),
            "url": url,
            "category": entry.get("category") or "market",
            "published_at": published_at,
            "collected_at": doc.get("collected_at") or datetime.now(timezone.utc).isoformat(),
            "summary": _repair_feed_text(doc.get("text") or doc.get("chunk") or ""),
        }
        item["source_tier"] = _source_score(item)
        item["topic_tier"] = _topic_score(entry, item)
        item["sort_ts"] = _published_ts(str(published_at))
        return item

    candidates_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for entry, docs in zip(watchlist, groups):
        symbol = str(entry["symbol"])
        candidates_by_symbol[symbol] = []
        for doc in docs:
            item = make_item(entry, doc)
            if item:
                candidates_by_symbol[symbol].append(item)
        candidates_by_symbol[symbol].sort(
            key=lambda row: (
                int(row.get("source_tier", 2)),
                int(row.get("topic_tier", 1)),
                -float(row.get("sort_ts", 0.0)),
            )
        )

    items: list[dict[str, Any]] = []
    used_categories: set[str] = set()
    for entry in watchlist:
        symbol = str(entry["symbol"])
        category = str(entry.get("category") or "market")
        if category in used_categories:
            continue
        if candidates_by_symbol.get(symbol):
            items.append(candidates_by_symbol[symbol][0])
            used_categories.add(category)
            if len(items) >= max_items:
                break
    if len(items) < max_items:
        category_counts: dict[str, int] = {}
        for item in items:
            category = str(item.get("category") or "market")
            category_counts[category] = category_counts.get(category, 0) + 1
        category_cap = 4
        leftovers = [item for rows in candidates_by_symbol.values() for item in rows if item not in items]
        leftovers.sort(
            key=lambda row: (
                int(row.get("source_tier", 2)),
                int(row.get("topic_tier", 1)),
                -float(row.get("sort_ts", 0.0)),
            )
        )
        deferred: list[dict[str, Any]] = []
        for item in leftovers:
            if len(items) >= max_items:
                break
            category = str(item.get("category") or "market")
            if category_counts.get(category, 0) >= category_cap:
                deferred.append(item)
                continue
            items.append(item)
            category_counts[category] = category_counts.get(category, 0) + 1
        if len(items) < max_items:
            items.extend(deferred[: max_items - len(items)])

    for item in items:
        item.pop("sort_ts", None)
        item.pop("topic_tier", None)

    return {
        "items": items[:max_items],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "google_news_rss",
        "selection_policy": "major_source_priority_issue_coverage",
    }


@app.get("/api/v1/dashboard/market")
async def dashboard_market() -> Dict[str, Any]:
    """Local market snapshot for the UI dashboard.

    The dashboard must not present previous-close data as live during the US
    cash session. We therefore try 5-minute yfinance bars first, mark stale
    prior-close data as non-decision-usable, and only use daily history as a
    clearly labelled fallback.
    """
    symbols = [
        {"symbol": "SPY", "label": "S&P 500", "asset_class": "equity_index"},
        {"symbol": "QQQ", "label": "Nasdaq 100", "asset_class": "equity_index"},
        {"symbol": "TLT", "label": "Long Treasury", "asset_class": "rates_bonds"},
        {"symbol": "HYG", "label": "High Yield Credit", "asset_class": "credit"},
        {"symbol": "LQD", "label": "IG Credit", "asset_class": "credit"},
        {"symbol": "GLD", "label": "Gold", "asset_class": "commodity"},
        {"symbol": "BTC-USD", "label": "Bitcoin", "asset_class": "crypto"},
        {"symbol": "DX-Y.NYB", "label": "DXY", "asset_class": "fx"},
        {"symbol": "^TNX", "label": "US 10Y Yield", "asset_class": "rates"},
    ]

    def pct_change(close_values: Any, periods: int) -> float | None:
        try:
            if len(close_values) <= periods:
                return None
            current = float(close_values.iloc[-1])
            previous = float(close_values.iloc[-1 - periods])
            if previous == 0:
                return None
            return round((current / previous - 1.0) * 100.0, 2)
        except Exception:
            return None

    def _as_iso(value: Any) -> str:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _close_series(frame: Any) -> Any:
        if frame is None or frame.empty or "Close" not in frame:
            raise RuntimeError("no close data")
        close = frame["Close"].dropna()
        if close.empty:
            raise RuntimeError("empty close series")
        return close

    def collect_one(item: dict[str, str]) -> dict[str, Any]:
        intraday_error = ""
        try:
            import yfinance as yf

            ticker = yf.Ticker(item["symbol"])
            intraday = ticker.history(period="5d", interval="5m", auto_adjust=False, prepost=False)
            close = _close_series(intraday)
            daily_last = close.groupby(close.index.date).last().dropna()
            if len(daily_last) < 2:
                raise RuntimeError("not enough intraday days for 1d return")
            last_idx = close.index[-1]
            as_of = _as_iso(last_idx)
            freshness = _us_market_freshness(as_of)
            usable = _dashboard_freshness_is_decision_usable(freshness.get("freshness_status"))
            daily_history = ticker.history(period="6mo", interval="1d", auto_adjust=False)
            daily_close = _close_series(daily_history)
            return {
                **item,
                "price": round(float(close.iloc[-1]), 4),
                "as_of": as_of,
                "source": "yfinance_intraday_5m",
                "status": "ok" if usable else "stale",
                "is_decision_usable": usable,
                "freshness_status": freshness.get("freshness_status", "unknown"),
                "age_minutes": freshness.get("age_minutes"),
                "market_clock": freshness.get("market_clock"),
                "returns": {
                    "1d": round((float(daily_last.iloc[-1]) / float(daily_last.iloc[-2]) - 1.0) * 100.0, 2),
                    "5d": pct_change(daily_close, 5),
                    "1m": pct_change(daily_close, 21),
                    "3m": pct_change(daily_close, 63),
                },
            }
        except Exception as exc:  # noqa: BLE001
            intraday_error = str(exc)
            try:
                import yfinance as yf

                history = yf.Ticker(item["symbol"]).history(period="6mo", interval="1d", auto_adjust=False)
                close = _close_series(history)
                last_idx = close.index[-1]
                as_of = last_idx.date().isoformat() if hasattr(last_idx, "date") else str(last_idx)
                freshness = _us_market_freshness(as_of)
                usable = _dashboard_freshness_is_decision_usable(freshness.get("freshness_status"))
                return {
                    **item,
                    "price": round(float(close.iloc[-1]), 4),
                    "as_of": as_of,
                    "source": "yfinance_daily_fallback",
                    "status": "ok" if usable else "stale",
                    "is_decision_usable": usable,
                    "freshness_status": freshness.get("freshness_status", "unknown"),
                    "age_minutes": freshness.get("age_minutes"),
                    "market_clock": freshness.get("market_clock"),
                    "intraday_error": intraday_error,
                    "returns": {
                        "1d": pct_change(close, 1),
                        "5d": pct_change(close, 5),
                        "1m": pct_change(close, 21),
                        "3m": pct_change(close, 63),
                    },
                }
            except Exception as fallback_exc:  # noqa: BLE001
                logger.warning("[DASHBOARD_MARKET] %s failed: %s", item["symbol"], fallback_exc)
            return {
                **item,
                "price": None,
                "as_of": "",
                "source": "yfinance",
                "status": "unavailable",
                "is_decision_usable": False,
                "freshness_status": "unknown",
                "age_minutes": None,
                "error": str(fallback_exc),
                "intraday_error": intraday_error,
                "returns": {"1d": None, "5d": None, "1m": None, "3m": None},
            }

    items = await asyncio.gather(*(asyncio.to_thread(collect_one, item) for item in symbols))
    ok_count = sum(1 for item in items if item.get("status") == "ok")
    decision_usable_count = sum(1 for item in items if item.get("is_decision_usable"))
    freshness_counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("freshness_status") or "unknown")
        freshness_counts[key] = freshness_counts.get(key, 0) + 1
    return {
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "yfinance",
        "ok_count": ok_count,
        "decision_usable_count": decision_usable_count,
        "freshness_counts": freshness_counts,
        "freshness_policy": "US market hours require fresh or delayed intraday data; stale prior-close data is labelled and excluded from decision-usable counts.",
        "warning": "" if decision_usable_count else "No fresh or delayed intraday market snapshot could be loaded from yfinance.",
    }


def _previous_business_day(value: Any) -> Any:
    day = value
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _expected_latest_us_market_date(now_ny: datetime) -> Any:
    """Expected latest US market date without relying on an exchange calendar.

    This deliberately handles the common failure mode for the dashboard:
    showing an old prior close during a normal trading session. It is not a full
    holiday calendar, but it prevents clearly stale multi-day data from being
    labelled as fresh or simply closed.
    """
    today = now_ny.date()
    if now_ny.weekday() >= 5:
        return _previous_business_day(today - timedelta(days=1))
    if now_ny.time() < dt_time(9, 30):
        return _previous_business_day(today - timedelta(days=1))
    return today


def _dashboard_freshness_is_decision_usable(status: Any) -> bool:
    return str(status or "").lower() in {"fresh", "delayed", "closed"}


def _us_market_freshness(as_of: str) -> dict[str, Any]:
    try:
        latest = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    except Exception:
        return {"freshness_status": "unknown", "age_minutes": None, "is_intraday": False}

    ny_tz = ZoneInfo("America/New_York")
    latest_ny = latest.astimezone(ny_tz) if latest.tzinfo else latest.replace(tzinfo=ny_tz)
    now_ny = datetime.now(ny_tz)
    age_minutes = max(0.0, round((now_ny - latest_ny).total_seconds() / 60.0, 1))
    expected_date = _expected_latest_us_market_date(now_ny)
    market_open = (
        now_ny.weekday() < 5
        and dt_time(9, 30) <= now_ny.time() <= dt_time(16, 15)
    )
    is_intraday = latest_ny.date() == expected_date
    if latest_ny.date() < expected_date:
        status = "stale_prior_close"
    elif market_open and age_minutes <= 25:
        status = "fresh"
    elif market_open and age_minutes <= 90:
        status = "delayed"
    elif market_open:
        status = "stale"
    else:
        status = "closed"
    return {
        "freshness_status": status,
        "age_minutes": age_minutes,
        "is_intraday": is_intraday,
        "market_clock": now_ny.isoformat(),
        "expected_market_date": expected_date.isoformat(),
    }


def _tile_span(weight: float) -> dict[str, int]:
    if weight >= 8:
        return {"col": 4, "row": 4}
    if weight >= 4:
        return {"col": 3, "row": 3}
    if weight >= 2:
        return {"col": 2, "row": 2}
    return {"col": 1, "row": 1}


def _batched_symbols(symbols: list[str], batch_size: int) -> list[list[str]]:
    size = max(1, int(batch_size or 1))
    return [symbols[idx:idx + size] for idx in range(0, len(symbols), size)]


def _extract_yfinance_symbol_frame(raw: Any, pd: Any, symbol: str) -> Any:
    if raw is None or getattr(raw, "empty", False):
        raise RuntimeError("empty intraday download")
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = list(raw.columns.get_level_values(0))
        if symbol in level0:
            return raw[symbol]
        return raw.xs(symbol, axis=1, level=0)
    return raw


def _download_equity_heatmap_frames(yf: Any, pd: Any, symbols: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
    frames: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for batch in _batched_symbols(symbols, _EQUITY_HEATMAP_BATCH_SIZE):
        try:
            raw = yf.download(
                tickers=batch,
                period="5d",
                interval="5m",
                auto_adjust=False,
                prepost=False,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as exc:  # noqa: BLE001
            for symbol in batch:
                errors[symbol] = f"batch download failed: {exc}"
            continue
        for symbol in batch:
            try:
                frames[symbol] = _extract_yfinance_symbol_frame(raw, pd, symbol)
            except Exception as exc:  # noqa: BLE001
                errors[symbol] = str(exc)
    return frames, errors


def _collect_equity_heatmap_snapshot() -> Dict[str, Any]:
    import pandas as pd
    import yfinance as yf

    symbols = [item["symbol"] for item in _EQUITY_HEATMAP_UNIVERSE]
    frames_by_symbol, download_errors = _download_equity_heatmap_frames(yf, pd, symbols)
    now_utc = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []

    for meta in _EQUITY_HEATMAP_UNIVERSE:
        symbol = str(meta["symbol"])
        try:
            if symbol in download_errors:
                raise RuntimeError(download_errors[symbol])
            frame = frames_by_symbol.get(symbol)
            if frame is None or frame.empty or "Close" not in frame:
                raise RuntimeError("no intraday close data")
            close = frame["Close"].dropna()
            if close.empty:
                raise RuntimeError("empty intraday close series")
            daily_last = close.groupby(close.index.date).last().dropna()
            if len(daily_last) < 2:
                raise RuntimeError("not enough intraday days for previous-close comparison")
            latest_idx = close.index[-1]
            latest_price = float(close.iloc[-1])
            previous_close = float(daily_last.iloc[-2])
            if previous_close == 0:
                raise RuntimeError("previous close is zero")
            change_pct = round((latest_price / previous_close - 1.0) * 100.0, 2)
            if hasattr(latest_idx, "isoformat"):
                as_of = latest_idx.isoformat()
            else:
                as_of = str(latest_idx)
            freshness = _us_market_freshness(as_of)
            usable = _dashboard_freshness_is_decision_usable(freshness["freshness_status"])
            span = _tile_span(float(meta["weight"]))
            items.append({
                **meta,
                "price": round(latest_price, 4),
                "previous_close": round(previous_close, 4),
                "change_pct": change_pct,
                "as_of": as_of,
                "source": "yfinance_intraday_5m",
                "status": "ok" if usable else "stale",
                "is_decision_usable": usable,
                "freshness_status": freshness["freshness_status"],
                "age_minutes": freshness["age_minutes"],
                "is_intraday": freshness["is_intraday"],
                "tile_span": span,
            })
        except Exception as exc:  # noqa: BLE001
            span = _tile_span(float(meta["weight"]))
            items.append({
                **meta,
                "price": None,
                "previous_close": None,
                "change_pct": None,
                "as_of": "",
                "source": "yfinance_intraday_5m",
                "status": "unavailable",
                "is_decision_usable": False,
                "freshness_status": "unknown",
                "age_minutes": None,
                "is_intraday": False,
                "tile_span": span,
                "error": str(exc),
            })

    usable_items = [item for item in items if item.get("status") == "ok" and item.get("is_decision_usable")]
    freshness_counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("freshness_status") or "unknown")
        freshness_counts[key] = freshness_counts.get(key, 0) + 1
    latest_as_of = max((str(item.get("as_of")) for item in usable_items if item.get("as_of")), default="")
    stale_count = sum(
        1 for item in items
        if not item.get("is_decision_usable")
    )
    return {
        "items": items,
        "generated_at": now_utc.isoformat(),
        "provider": "yfinance",
        "interval": "5m",
        "universe_version": HEATMAP_UNIVERSE_VERSION,
        "universe_size": len(_EQUITY_HEATMAP_UNIVERSE),
        "batch_size": _EQUITY_HEATMAP_BATCH_SIZE,
        "ok_count": len(usable_items),
        "decision_usable_count": len(usable_items),
        "stale_or_unavailable_count": stale_count,
        "latest_as_of": latest_as_of,
        "freshness_counts": freshness_counts,
        "freshness_policy": "US market hours require fresh or delayed 5-minute intraday data; prior-close/stale symbols are excluded from the rendered heatmap.",
        "warning": (
            f"{stale_count}개 종목은 최신/지연 허용 범위의 intraday 데이터가 아니어서 의사결정용 표시에서 제외했습니다."
            if stale_count else ""
        ),
    }


@app.get("/api/v1/dashboard/equity-heatmap")
async def dashboard_equity_heatmap(force: bool = False) -> Dict[str, Any]:
    """Intraday, auditable US equity sector heatmap for the dashboard.

    TradingView's embeddable heatmap cannot expose the timestamp/freshness of
    the prices it renders. This endpoint keeps the dashboard decision-useful by
    computing 5-minute Yahoo/yfinance returns locally and returning explicit
    ``as_of`` and stale status per symbol.
    """
    now = time.time()
    cached = _dashboard_equity_heatmap_cache.get("payload")
    if cached and not force and now - float(_dashboard_equity_heatmap_cache.get("ts") or 0) < _DASHBOARD_EQUITY_HEATMAP_CACHE_TTL_SEC:
        payload = dict(cached)
        payload["cache_hit"] = True
        return payload

    payload = await asyncio.to_thread(_collect_equity_heatmap_snapshot)
    payload["cache_hit"] = False
    _dashboard_equity_heatmap_cache["ts"] = now
    _dashboard_equity_heatmap_cache["payload"] = dict(payload)
    return payload


@app.get("/api/v1/config/legacy")
async def get_config_legacy() -> Dict[str, Any]:
    """Legacy alias kept for debugging old UI bundles."""
    return {
        "models": list(SUPPORTED_INFERENCE_ROUTES),
        "default_model": "qwen",
        "presets": [
            {
                "id": "risk",
                "label": "단기 리스크",
                "question": "최근 실적 발표와 뉴스에서 확인되는 가장 중요한 단기 리스크는 무엇인가요?",
            },
            {
                "id": "catalyst",
                "label": "성장 촉매",
                "question": "향후 6~12개월 동안 주목해야 할 핵심 성장 촉매와 상승 동인은 무엇인가요?",
            },
            {
                "id": "thesis",
                "label": "12개월 투자 가설",
                "question": "최신 공개 정보를 기준으로 12개월 관점의 핵심 투자 가설은 무엇인가요?",
            },
            {
                "id": "earnings",
                "label": "실적 신호",
                "question": "최근 실적 발표에서 가이던스 변화와 경영진 톤을 포함해 가장 중요한 신호를 요약해주세요.",
            },
            {
                "id": "competitive",
                "label": "경쟁 구도",
                "question": "최근 경쟁 구도는 어떻게 변했고, 해당 기업의 포지셔닝에는 어떤 영향을 주나요?",
            },
        ],
    }


def _read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to read JSON at {path}: {exc}")
        return None


@app.get("/api/v1/outputs/latest")
async def get_latest_outputs() -> Dict[str, Any]:
    """Aggregate the last run's artifacts for the UI (response + collection + request)."""
    payload = {
        "response": _read_json(OUTPUTS_DIR / "latest_response.json"),
        "collection": _read_json(OUTPUTS_DIR / "latest_collection.json"),
        "request": _read_json(OUTPUTS_DIR / "latest_request.json"),
        "has_markdown": (OUTPUTS_DIR / "latest_report.md").exists(),
        "has_html": (OUTPUTS_DIR / "latest_report.html").exists(),
    }
    return JSONResponse(payload)


@app.get("/api/v1/outputs/report.md", response_class=PlainTextResponse)
async def get_latest_markdown():
    path = OUTPUTS_DIR / "latest_report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No markdown report available yet.")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@app.get("/api/v1/outputs/report.html")
async def get_latest_html():
    path = OUTPUTS_DIR / "latest_report.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No HTML report available yet.")
    return FileResponse(path, media_type="text/html")


def _load_response_payload(run_id: str | None) -> Dict[str, Any]:
    """Return the response dict for an export — either a specific run or the latest."""
    if run_id:
        entry = history_get_run(outputs_dir=OUTPUTS_DIR, run_id=run_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
        resp = entry.get("response") if isinstance(entry, dict) else None
        if not resp:
            raise HTTPException(status_code=404, detail=f"run '{run_id}' has no response payload")
        return resp
    latest = _read_json(OUTPUTS_DIR / "latest_response.json")
    if not latest:
        raise HTTPException(status_code=404, detail="No analysis response available yet.")
    return latest


def _export_filename(payload: Dict[str, Any], run_id: str | None, ext: str) -> str:
    ticker = str(payload.get("ticker") or "analysis").strip().upper()
    stamp = run_id or time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    safe_stamp = stamp.replace(":", "").replace("/", "_")
    return f"fingpt_{ticker}_{safe_stamp}.{ext}"


@app.get("/api/v1/outputs/export/csv", response_class=PlainTextResponse)
async def export_csv(run_id: str | None = None):
    """Download the latest (or a specific) run as a Bull/Bear CSV with evidence ids."""
    payload = _load_response_payload(run_id)
    body = response_to_csv(payload)
    return PlainTextResponse(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_export_filename(payload, run_id, "csv")}"'},
    )


@app.get("/api/v1/outputs/export/jsonl", response_class=PlainTextResponse)
async def export_jsonl(run_id: str | None = None, include_raw_context: bool = True):
    """Download the latest (or a specific) run as JSONL for the eval pipeline."""
    payload = _load_response_payload(run_id)
    body = response_to_jsonl(payload, include_raw_context=include_raw_context)
    return PlainTextResponse(
        body,
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_export_filename(payload, run_id, "jsonl")}"'},
    )


@app.get("/api/v1/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "version": app.version}


@app.get("/api/v1/runs")
async def list_runs(
    ticker: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Server-persisted run history. Indexed by SQLite for cheap queries."""
    try:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="limit/offset must be integers")
    items = history_list_runs(outputs_dir=OUTPUTS_DIR, ticker=ticker, limit=limit, offset=offset)
    return {"count": len(items), "items": items}


@app.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    entry = history_get_run(outputs_dir=OUTPUTS_DIR, run_id=run_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
    return entry


_FAILURE_MODES_RUNBOOK = [
    {
        "code": "QDRANT_SERVICE",
        "label": "Qdrant vector DB unreachable",
        "symptom": "retrieval returns empty / pipeline fails before inference.",
        "remediation": [
            "`docker ps` to confirm the `fingpt-qdrant` container is running.",
            "`docker start fingpt-qdrant` or re-run `scripts/bootstrap_local.ps1`.",
            "Check QDRANT_URL in .env (default http://localhost:6333).",
        ],
        "docs": ["docs/quickstart.md", "docs/runbook.md"],
    },
    {
        "code": "QDRANT_QUERY_STACK",
        "label": "Embedding / query stack not ready",
        "symptom": "Qdrant is up but embedding/add/query smoke test fails.",
        "remediation": [
            "Ensure fastembed model files finished downloading (first run is slow).",
            "Delete the stale collection and let pipeline recreate it.",
            "Re-run preflight once the embedder finishes warming up.",
        ],
        "docs": ["docs/runbook.md"],
    },
    {
        "code": "OLLAMA_SERVICE",
        "label": "Ollama daemon unreachable",
        "symptom": "inference stage raises ConnectionError to 11434.",
        "remediation": [
            "Start the Ollama app / service (`ollama serve`).",
            "Verify `curl http://localhost:11434/api/tags` returns JSON.",
            "Check OLLAMA_BASE_URL in .env.",
        ],
        "docs": ["docs/quickstart.md"],
    },
    {
        "code": "OLLAMA_MODEL",
        "label": "Primary model missing",
        "symptom": "model '{primary_model}' not installed.",
        "remediation": [
            "`ollama pull qwen2.5:7b` for the production baseline.",
            "Optionally enable experimental fallback in .env.",
        ],
        "docs": ["docs/quickstart.md"],
    },
    {
        "code": "FMP_API_KEY",
        "label": "FMP API key missing",
        "symptom": "transcript + stock news sources silently return empty.",
        "remediation": [
            "Set FMP_API_KEY in .env.",
            "Disable news/transcript sources in the UI if you cannot provide a key.",
        ],
        "docs": ["docs/quickstart.md"],
    },
    {
        "code": "TRANSCRIPT_PROVIDER",
        "label": "Transcript endpoint rejected",
        "symptom": "402 entitlement required or 4xx from FMP.",
        "remediation": [
            "Confirm the FMP plan covers earning_call_transcript.",
            "Run without transcripts (toggle off in the UI) until entitlement is resolved.",
        ],
        "docs": ["docs/runbook.md"],
    },
    {
        "code": "SEC_FILINGS",
        "label": "SEC EDGAR rate-limited",
        "symptom": "429 from data.sec.gov.",
        "remediation": [
            "SEC requires a User-Agent header; ensure SEC_USER_AGENT is populated.",
            "Back off and re-run — EDGAR caps aggressive polling.",
        ],
        "docs": ["docs/runbook.md"],
    },
    {
        "code": "YFINANCE_FEED",
        "label": "Yahoo Finance feed offline",
        "symptom": "news source returns empty context.",
        "remediation": [
            "Retry — yfinance is unofficial and occasionally rate-limits.",
            "Check outbound network / corporate proxy settings.",
        ],
        "docs": ["docs/runbook.md"],
    },
    {
        "code": "HF_TOKEN",
        "label": "HF_TOKEN missing",
        "symptom": "some optional embeddings / models skip.",
        "remediation": [
            "Set HF_TOKEN in .env if gated models are required.",
            "Non-blocking when using default local embeddings.",
        ],
        "docs": ["docs/quickstart.md"],
    },
]


def _run_preflight_sync() -> Dict[str, Any]:
    """Wrap core.preflight.run_preflight for async execution."""
    return run_preflight()


async def _get_preflight_report(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if (
        not force
        and _preflight_cache["report"] is not None
        and (now - _preflight_cache["ts"]) < _PREFLIGHT_CACHE_TTL_SEC
    ):
        return _preflight_cache["report"]

    async with _preflight_lock:
        now = time.time()
        if (
            not force
            and _preflight_cache["report"] is not None
            and (now - _preflight_cache["ts"]) < _PREFLIGHT_CACHE_TTL_SEC
        ):
            return _preflight_cache["report"]
        loop = asyncio.get_running_loop()
        report = await loop.run_in_executor(None, _run_preflight_sync)
        report = dict(report)
        report["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report["ttl_seconds"] = _PREFLIGHT_CACHE_TTL_SEC
        _preflight_cache["report"] = report
        _preflight_cache["ts"] = time.time()
        return report


@app.get("/api/v1/preflight")
async def preflight_status(force: bool = False) -> Dict[str, Any]:
    """
    Run the same dependency probe that CLI/ops uses. Results are cached for
    a short TTL so the UI status badge can poll without thrashing services.
    Pass ?force=true to bypass the cache.
    """
    return await _get_preflight_report(force=force)


@app.get("/api/v1/runbook/failure-modes")
async def runbook_failure_modes() -> Dict[str, Any]:
    """Static remediation playbook keyed by preflight check name."""
    return {
        "version": 1,
        "modes": _FAILURE_MODES_RUNBOOK,
    }


@app.get("/api/v1/watchlist")
async def watchlist_list() -> Dict[str, Any]:
    items = [item.to_dict() for item in watchlist_store.list_items()]
    return {"items": items, "scheduler": get_watchlist_scheduler().status()}


@app.post("/api/v1/watchlist")
async def watchlist_create(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        item = watchlist_store.upsert_item(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item.to_dict()


@app.put("/api/v1/watchlist/{item_id}")
async def watchlist_update(item_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        item = watchlist_store.upsert_item(payload, item_id=item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item.to_dict()


@app.delete("/api/v1/watchlist/{item_id}")
async def watchlist_delete(item_id: str) -> Dict[str, Any]:
    dropped = watchlist_store.delete_item(item_id)
    if not dropped:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    return {"deleted": True, "id": item_id}


@app.post("/api/v1/watchlist/{item_id}/run")
async def watchlist_run_now(item_id: str) -> Dict[str, Any]:
    """Execute a watchlist item immediately. Returns the full AnalysisResponse
    and stamps the item's last-run metadata so the UI reflects freshness."""
    item = watchlist_store.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    try:
        request = AnalysisRequest(
            ticker=item.ticker,
            question=item.question,
            sources=list(item.sources),
            lookback_days=item.lookback_days,
            top_k=item.top_k,
            model=item.model,
        )
        response = await run_pipeline_async(request)
        watchlist_store.mark_run(item.id, status=response.status, error=response.error_metadata)
        return {"item": watchlist_store.get_item(item_id).to_dict() if watchlist_store.get_item(item_id) else None, "response": response.model_dump(mode="json")}
    except Exception as exc:
        watchlist_store.mark_run(item.id, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/collection/cache")
async def collection_cache_stats() -> Dict[str, Any]:
    """Inspect the process-local collection cache (hits/misses/size/ttl)."""
    return get_collection_cache(_settings).stats()


@app.post("/api/v1/collection/cache/invalidate")
async def collection_cache_invalidate(ticker: str | None = None) -> Dict[str, Any]:
    """Drop cache entries for a specific ticker, or the whole cache when omitted."""
    dropped = get_collection_cache(_settings).invalidate(ticker)
    return {"dropped": dropped, "ticker": ticker}


@app.get("/api/v1/eval/dashboard")
async def eval_dashboard() -> Dict[str, Any]:
    """Aggregate the latest quality review + eval report for the UI Quality tab."""
    try:
        return await asyncio.to_thread(load_eval_dashboard, PROJECT_ROOT)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[EVAL_DASHBOARD] failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/qdrant/collection")
async def qdrant_collection_info() -> Dict[str, Any]:
    """Return Qdrant collection stats + per-ticker breakdown for the admin panel."""
    try:
        # Offload the synchronous qdrant_client calls so FastAPI's event loop
        # isn't blocked for large collections.
        info = await asyncio.to_thread(get_collection_info)
        return info
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[QDRANT_ADMIN] info failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/qdrant/purge")
async def qdrant_purge(
    older_than_days: int | None = None,
    ticker: str | None = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Purge embeddings by age and/or ticker. Requires at least one filter.

    Deliberately refuses an "empty" purge so no one accidentally nukes the
    entire collection through the UI. Pass ``dry_run=true`` to preview counts.
    """
    if older_than_days is None and not ticker:
        raise HTTPException(
            status_code=400,
            detail="Provide older_than_days and/or ticker — refusing to purge the entire collection.",
        )
    try:
        return await asyncio.to_thread(
            purge_points,
            older_than_days=older_than_days,
            ticker=ticker,
            dry_run=dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[QDRANT_ADMIN] purge failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/runs/summary/{ticker}")
async def run_summary_for_ticker(ticker: str, limit: int = 10) -> Dict[str, Any]:
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="limit must be an integer")
    series = history_ticker_summary(outputs_dir=OUTPUTS_DIR, ticker=ticker, limit=limit)
    return {"ticker": ticker.upper(), "points": list(reversed(series))}


if WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/ui/")
else:  # pragma: no cover - only triggered if web assets removed
    logger.warning(f"Web UI directory not found at {WEB_DIR}; serving API only.")
