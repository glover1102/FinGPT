from __future__ import annotations

import concurrent.futures
import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

from core.schemas.fundamentals import FundamentalsCard
from core.schemas.retrieval import RetrievalItem
from core.utils.asset_classifier import classify
from core.utils.logger import get_logger
from core.utils.technical_indicators import freshness_status
from pipelines.data_mart.storage import repository

logger = get_logger("pipelines.collect.fundamentals")


def _run_with_timeout(func, *args, timeout_s: float):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, *args)
    try:
        return future.result(timeout=timeout_s)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _float_or_none(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _fetch_info(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info or {}
    if not isinstance(info, dict):
        return {}
    return info


def _build_card(ticker: str, info: dict[str, Any]) -> FundamentalsCard:
    price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("previousClose")
        or info.get("navPrice")
    )
    yield_value = info.get("yield") if info.get("yield") is not None else info.get("dividendYield")
    total_assets = info.get("totalAssets")
    if total_assets is None:
        total_assets = info.get("netAssets")
    return FundamentalsCard(
        ticker=ticker.upper(),
        as_of=date.today().isoformat(),
        asset_class=_str_or_none(info.get("assetClass")),
        quote_type=_str_or_none(info.get("quoteType")),
        currency=_str_or_none(info.get("currency") or info.get("financialCurrency")),
        exchange=_str_or_none(info.get("exchange") or info.get("fullExchangeName")),
        name=_str_or_none(info.get("longName") or info.get("shortName")),
        sector=_str_or_none(info.get("sector")),
        industry=_str_or_none(info.get("industry")),
        market_cap=_float_or_none(info.get("marketCap")),
        price=_float_or_none(price),
        week52_high=_float_or_none(info.get("fiftyTwoWeekHigh")),
        week52_low=_float_or_none(info.get("fiftyTwoWeekLow")),
        trailing_pe=_float_or_none(info.get("trailingPE")),
        forward_pe=_float_or_none(info.get("forwardPE")),
        price_to_book=_float_or_none(info.get("priceToBook")),
        profit_margin=_float_or_none(info.get("profitMargins")),
        gross_margin=_float_or_none(info.get("grossMargins")),
        operating_margin=_float_or_none(info.get("operatingMargins")),
        return_on_equity=_float_or_none(info.get("returnOnEquity")),
        revenue_growth=_float_or_none(info.get("revenueGrowth")),
        earnings_growth=_float_or_none(info.get("earningsGrowth")),
        total_revenue=_float_or_none(info.get("totalRevenue")),
        revenue_per_share=_float_or_none(info.get("revenuePerShare")),
        trailing_eps=_float_or_none(info.get("trailingEps")),
        forward_eps=_float_or_none(info.get("forwardEps")),
        book_value=_float_or_none(info.get("bookValue")),
        enterprise_value=_float_or_none(info.get("enterpriseValue")),
        ebitda=_float_or_none(info.get("ebitda")),
        free_cashflow=_float_or_none(info.get("freeCashflow")),
        total_cash=_float_or_none(info.get("totalCash")),
        total_debt=_float_or_none(info.get("totalDebt")),
        debt_to_equity=_float_or_none(info.get("debtToEquity")),
        shares_outstanding=_float_or_none(info.get("sharesOutstanding")),
        dividend_yield=_float_or_none(info.get("dividendYield")),
        yield_value=_float_or_none(yield_value),
        beta=_float_or_none(info.get("beta")),
        analyst_rating_mean=_float_or_none(info.get("recommendationMean")),
        analyst_target_mean=_float_or_none(info.get("targetMeanPrice")),
        num_analysts=_int_or_none(info.get("numberOfAnalystOpinions")),
        total_assets=_float_or_none(total_assets),
        net_assets=_float_or_none(info.get("netAssets")),
        nav_price=_float_or_none(info.get("navPrice")),
        expense_ratio=_float_or_none(info.get("annualReportExpenseRatio") or info.get("expenseRatio")),
        average_volume=_float_or_none(info.get("averageVolume") or info.get("averageVolume10days")),
    )


def collect_fundamentals_card(
    ticker: str,
    timeout_s: float = 5.0,
    *,
    persist: bool = True,
    db_path: str | Path | None = None,
) -> Optional[FundamentalsCard]:
    """Collect and optionally persist a deterministic yfinance fundamentals snapshot."""

    profile = classify(ticker)
    if profile.asset_class in {"forex", "futures"}:
        logger.info(
            "[FUNDAMENTALS] skipped ticker=%s asset_class=%s is_etf=%s",
            profile.ticker,
            profile.asset_class,
            profile.is_etf,
        )
        return None

    try:
        info = _run_with_timeout(_fetch_info, profile.ticker, timeout_s=timeout_s)
        if not info:
            return None
        card = _build_card(profile.ticker, info)
        if not card.asset_class:
            card.asset_class = profile.asset_class
        if persist:
            try:
                repository.upsert_fundamentals_card(card, db_path=db_path)
            except Exception as exc:  # noqa: BLE001 - storage must not block research answers.
                logger.warning("[FUNDAMENTALS] data-mart persistence failed for %s: %s", profile.ticker, exc)
        return card
    except concurrent.futures.TimeoutError:
        logger.warning("[FUNDAMENTALS] skip for %s: timeout after %.1fs", profile.ticker, timeout_s)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FUNDAMENTALS] skip for %s: %s", profile.ticker, exc)
        return None


def _metric_value(value: float | int | None, *, percent: bool = False, digits: int = 2) -> str | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if percent:
        parsed *= 100.0
        return f"{parsed:.{digits}f}%"
    if abs(parsed) >= 1_000_000_000_000:
        return f"{parsed / 1_000_000_000_000:.2f}T"
    if abs(parsed) >= 1_000_000_000:
        return f"{parsed / 1_000_000_000:.2f}B"
    if abs(parsed) >= 1_000_000:
        return f"{parsed / 1_000_000:.2f}M"
    return f"{parsed:.{digits}f}"


def _fundamental_metric(
    card: FundamentalsCard,
    name: str,
    value: str | None,
    *,
    unit: str,
    context: str,
) -> dict[str, Any] | None:
    if not value:
        return None
    doc_id = fundamentals_doc_id(card)
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "as_of": card.as_of,
        "context": context,
        "source": "yfinance:fundamentals",
        "source_type": "provider_data",
        "calculation_method": "provider_snapshot",
        "is_deterministic": True,
        "grounding_status": "grounded",
        "freshness_status": freshness_status(card.as_of),
        "evidence_doc_ids": [doc_id],
    }


def fundamentals_doc_id(card: FundamentalsCard) -> str:
    safe_as_of = str(card.as_of or "unknown").replace(":", "").replace("/", "-")
    return f"fundamentals:{card.ticker.upper()}:{safe_as_of}"


def fundamentals_card_metrics(card: FundamentalsCard | None) -> list[dict[str, Any]]:
    if card is None:
        return []
    ticker = card.ticker.upper()
    metrics: list[dict[str, Any]] = []

    def add(name: str, raw: float | int | None, *, unit: str, context: str, percent: bool = False, digits: int = 2) -> None:
        metric = _fundamental_metric(
            card,
            name,
            _metric_value(raw, percent=percent, digits=digits),
            unit=unit,
            context=context,
        )
        if metric:
            metrics.append(metric)

    add(f"{ticker} 현재가", card.price, unit="price", context="yfinance가 제공한 최근 가격 스냅샷입니다.")
    add(f"{ticker} 시가총액", card.market_cap, unit=card.currency or "currency", context="기업 규모와 밸류에이션 해석의 기준입니다.")
    add(f"{ticker} 52주 고가", card.week52_high, unit="price", context="최근 1년 가격 범위의 상단입니다.")
    add(f"{ticker} 52주 저가", card.week52_low, unit="price", context="최근 1년 가격 범위의 하단입니다.")
    add(f"{ticker} TTM PER", card.trailing_pe, unit="x", context="최근 이익 대비 가격 배수입니다.", digits=1)
    add(f"{ticker} Forward PER", card.forward_pe, unit="x", context="예상 이익 대비 가격 배수입니다.", digits=1)
    add(f"{ticker} PBR", card.price_to_book, unit="x", context="장부가 대비 가격 배수입니다.", digits=2)
    add(f"{ticker} 매출 성장률", card.revenue_growth, unit="%", context="최근 매출 성장 방향을 보여줍니다.", percent=True)
    add(f"{ticker} EPS 성장률", card.earnings_growth, unit="%", context="이익 성장 방향을 보여줍니다.", percent=True)
    add(f"{ticker} 매출액", card.total_revenue, unit=card.currency or "currency", context="최근 환산된 매출 규모입니다.")
    add(f"{ticker} 순이익률", card.profit_margin, unit="%", context="매출이 순이익으로 전환되는 비율입니다.", percent=True)
    add(f"{ticker} 매출총이익률", card.gross_margin, unit="%", context="제품/서비스 원가 구조를 보여줍니다.", percent=True)
    add(f"{ticker} 영업이익률", card.operating_margin, unit="%", context="영업 레버리지와 비용 통제력을 보여줍니다.", percent=True)
    add(f"{ticker} ROE", card.return_on_equity, unit="%", context="자본 효율성을 보여주는 지표입니다.", percent=True)
    add(f"{ticker} 총현금", card.total_cash, unit=card.currency or "currency", context="재무 유동성 판단의 기준입니다.")
    add(f"{ticker} 총부채", card.total_debt, unit=card.currency or "currency", context="레버리지와 금리 민감도 판단의 기초입니다.")
    add(f"{ticker} FCF", card.free_cashflow, unit=card.currency or "currency", context="주주환원과 재투자 여력 판단의 기준입니다.")
    add(f"{ticker} 베타", card.beta, unit="x", context="시장 민감도를 보여주는 보조 위험 지표입니다.", digits=2)
    add(f"{ticker} 배당수익률", card.dividend_yield, unit="%", context="현금수익률과 방어성 판단의 입력입니다.", percent=True)
    add(f"{ticker} 애널리스트 목표가", card.analyst_target_mean, unit="price", context="컨센서스 기대치의 참고값입니다.")
    add(f"{ticker} ETF/펀드 총자산", card.total_assets or card.net_assets, unit=card.currency or "currency", context="펀드 규모와 유동성 판단의 기준입니다.")
    add(f"{ticker} NAV", card.nav_price, unit="price", context="ETF/펀드의 순자산가치 기준 가격입니다.")
    add(f"{ticker} 보수율", card.expense_ratio, unit="%", context="ETF/펀드 장기 보유 비용입니다.", percent=True)
    add(f"{ticker} 평균 거래량", card.average_volume, unit="shares", context="거래 유동성 판단의 보조 지표입니다.")
    return metrics


def fundamentals_card_to_retrieval_item(card: FundamentalsCard | None) -> RetrievalItem | None:
    if card is None:
        return None
    doc_id = fundamentals_doc_id(card)
    payload = card.model_dump(exclude_none=True)
    metrics = fundamentals_card_metrics(card)
    lines = [
        f"FINANCIAL FUNDAMENTALS SNAPSHOT for {card.ticker.upper()} as of {card.as_of}.",
        "This provider-backed block is deterministic context from yfinance and should be used before narrative guesses.",
        "Use it for valuation, quality, liquidity, ETF, and balance-sheet checks. Do not invent missing fields.",
        f"Name: {card.name or card.ticker} | Quote type: {card.quote_type or 'unknown'} | Currency: {card.currency or 'unknown'} | Exchange: {card.exchange or 'unknown'}",
        "FUNDAMENTALS_CARD_JSON: " + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "FUNDAMENTALS_METRICS_JSON: " + json.dumps(metrics, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    ]
    return RetrievalItem(
        source="yfinance:fundamentals",
        title=f"{card.ticker.upper()} 재무/밸류에이션 스냅샷",
        date=card.as_of,
        chunk="\n".join(lines),
        score=1.0,
        metadata={
            "doc_id": doc_id,
            "parent_doc_id": doc_id,
            "ticker": card.ticker.upper(),
            "doc_type": "fundamentals_snapshot",
            "source": "yfinance:fundamentals",
            "published_at": card.as_of,
            "retrieval_mode": "deterministic_provider_snapshot",
        },
    )


def fundamentals_metrics_from_retrieval_items(items: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        for line in str(getattr(item, "chunk", "") or "").splitlines():
            if not line.startswith("FUNDAMENTALS_METRICS_JSON:"):
                continue
            payload = line.split("FUNDAMENTALS_METRICS_JSON:", 1)[1].strip()
            try:
                metrics = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(metrics, list):
                continue
            for metric in metrics:
                if not isinstance(metric, dict):
                    continue
                name = str(metric.get("name") or "").strip()
                value = str(metric.get("value") or "").strip()
                if not name or not value:
                    continue
                key = f"{name.lower()}|{metric.get('as_of')}|{value}"
                if key in seen:
                    continue
                seen.add(key)
                out.append(metric)
    return out
