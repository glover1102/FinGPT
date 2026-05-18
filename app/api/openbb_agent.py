from __future__ import annotations

import asyncio
import json
import queue as threadqueue
import re
from typing import Any, Iterable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core.config.settings import load_settings
from core.schemas.request import UniversalRequest
from core.schemas.response import AnalysisResponse, Citation, CompareResponse, ExecutionMeta, KeyMetric
from core.schemas.topic import TopicResponse
from core.utils.logger import get_logger
from core.utils.openbb_agent_compat import build_agents_json
from pipelines.orchestration.dispatch import dispatch_async


router = APIRouter()
logger = get_logger("api.openbb_agent")

_TICKER_RE = re.compile(r"^\$?[\^A-Z0-9][A-Z0-9.\-=]{0,14}$", re.IGNORECASE)
_TICKER_KEYS = {
    "ticker",
    "tickers",
    "symbol",
    "symbols",
    "selected_ticker",
    "selected_symbol",
    "underlying_symbol",
}
_NON_TICKER_VALUES = {"", "MARKET", "MACRO", "NEWS", "INDEX", "WATCHLIST"}
_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _clip(value: Any, limit: int = 4000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in _TRUTHY_VALUES


def _normalize_ticker(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            normalized = _normalize_ticker(item)
            if normalized:
                return normalized
        return None
    raw = str(value or "").strip().upper()
    if raw.startswith("$"):
        raw = raw[1:]
    if raw in _NON_TICKER_VALUES:
        return None
    if _TICKER_RE.match(raw):
        return raw
    return None


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        for key in ("text", "content", "value", "message"):
            text = _content_to_text(content.get(key))
            if text:
                return text
        return ""
    if isinstance(content, list):
        parts = [_content_to_text(item) for item in content]
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def extract_latest_human_question(payload: dict[str, Any]) -> str:
    """Extract the latest user/human message from a flexible OpenBB payload."""

    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or message.get("type") or "").lower()
            if role in {"human", "user"}:
                text = _content_to_text(message.get("content") or message.get("message"))
                if text:
                    return text

    for key in ("query", "question", "prompt", "input"):
        text = _content_to_text(payload.get(key))
        if text:
            return text
    return ""


def _walk_for_tickers(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _TICKER_KEYS:
                normalized = _normalize_ticker(item)
                if normalized:
                    yield normalized
            yield from _walk_for_tickers(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_for_tickers(item)


def extract_ticker_hint(payload: dict[str, Any]) -> str | None:
    """Extract selected widget/dashboard ticker hints without trusting prose."""

    preferred_paths = (
        payload.get("selected_widget"),
        payload.get("widget"),
        payload.get("widgets"),
        payload.get("dashboard"),
        payload.get("context"),
        payload.get("metadata"),
    )
    for section in preferred_paths:
        for ticker in _walk_for_tickers(section):
            return ticker
    for key in ("ticker", "symbol"):
        normalized = _normalize_ticker(payload.get(key))
        if normalized:
            return normalized
    return None


def build_universal_request_from_openbb(payload: dict[str, Any]) -> UniversalRequest:
    question = extract_latest_human_question(payload)
    if not question:
        raise ValueError("OpenBB query payload must include a human/user question.")
    ticker = extract_ticker_hint(payload)
    mode_hint = "auto" if ticker else "topic"
    return UniversalRequest(
        question=question,
        ticker=ticker,
        mode_hint=mode_hint,
        lookback_days=int(payload.get("lookback_days") or payload.get("lookback") or 60),
        top_k=int(payload.get("top_k") or 10),
        model=str(payload.get("model") or "qwen"),
    )


def _dry_run_response(universal_request: UniversalRequest) -> AnalysisResponse:
    ticker = universal_request.ticker or "MARKET"
    return AnalysisResponse(
        ticker=ticker,
        question=universal_request.question,
        status="success",
        summary=(
            "OpenBB Workspace 연결 점검용 응답입니다. FinGPT adapter가 질문, ticker hint, "
            "metric table, citation artifact를 SSE로 스트리밍할 수 있는지 확인했습니다."
        ),
        sentiment="Neutral",
        confidence=0.0,
        conclusion=(
            "Dry-run은 실제 투자 분석을 실행하지 않습니다. 같은 payload에서 "
            "X-FinGPT-OpenBB-Dry-Run 헤더를 제거하면 FinGPT universal pipeline으로 라우팅됩니다."
        ),
        key_metrics=[
            KeyMetric(
                name="OpenBB adapter contract",
                value="ok",
                unit="diagnostic",
                as_of="runtime",
                context="Workspace HTTP/SSE contract probe",
                source="FinGPT local server",
                freshness_status="fresh",
                evidence_doc_ids=["openbb-dry-run"],
            )
        ],
        citations=[
            Citation(
                source="FinGPT local server",
                title="OpenBB Workspace dry-run contract probe",
                date="runtime",
                doc_id="openbb-dry-run",
            )
        ],
        execution_meta=ExecutionMeta(
            extras={
                "openbb_dry_run": True,
                "mode_hint": universal_request.mode_hint,
                "ticker_hint": universal_request.ticker,
                "lookback_days": universal_request.lookback_days,
                "top_k": universal_request.top_k,
            }
        ),
    )


def _manual_event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": event, "data": {"type": event, **data}}


def _sdk_or_manual(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Use openbb-ai helpers when available, otherwise return manual SSE data."""

    fallback = _manual_event(event, data)
    try:
        import openbb_ai  # type: ignore

        if event == "message_chunk":
            produced = openbb_ai.message_chunk(str(data.get("content") or data.get("message") or ""))
        elif event == "reasoning_step":
            status = str(data.get("status") or "running").lower()
            event_type = "ERROR" if status == "error" else "WARNING" if status == "warning" else "INFO"
            produced = openbb_ai.reasoning_step(
                str(data.get("content") or data.get("message") or ""),
                event_type=event_type,
                details=data.get("details") or None,
            )
        elif event == "table":
            produced = openbb_ai.table(
                list(data.get("rows") or []),
                name=str(data.get("title") or "FinGPT table"),
                description=", ".join(str(col) for col in data.get("columns") or []) or None,
            )
        elif event == "citations":
            from openbb_ai import models as openbb_models  # type: ignore

            citations = []
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or item.get("source") or "FinGPT evidence")
                source_info = openbb_models.SourceInfo(
                    type="web" if url else "direct retrieval",
                    origin=url or None,
                    name=title,
                    description=str(item.get("source") or item.get("doc_id") or ""),
                    metadata={k: v for k, v in item.items() if v is not None},
                    citable=True,
                )
                citations.append(openbb_models.Citation(source_info=source_info, details=[item]))
            produced = openbb_ai.citations(citations)
        else:
            factory = getattr(openbb_ai, event, None)
            if not callable(factory):
                return fallback
            produced = factory(data)
        if hasattr(produced, "model_dump"):
            dumped = produced.model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else fallback
        if isinstance(produced, dict):
            return produced
    except Exception:
        return fallback
    return fallback


def message_chunk(content: str) -> dict[str, Any]:
    return _sdk_or_manual("message_chunk", {"content": content})


def reasoning_step(content: str, *, status: str = "running", details: dict[str, Any] | None = None) -> dict[str, Any]:
    return _sdk_or_manual("reasoning_step", {"content": content, "status": status, "details": details or {}})


def table_event(title: str, rows: list[dict[str, Any]], *, columns: list[str] | None = None) -> dict[str, Any]:
    return _sdk_or_manual("table", {"title": title, "columns": columns or [], "rows": rows})


def citations_event(items: list[dict[str, Any]]) -> dict[str, Any]:
    return _sdk_or_manual("citations", {"items": items})


def done_event() -> dict[str, Any]:
    return _manual_event("done", {"status": "complete"})


def error_event(error_type: str, message: str) -> dict[str, Any]:
    return _manual_event(
        "error",
        {
            "error_type": error_type,
            "message": message,
            "next_action": "FinGPT server logs and local dependency preflight should be checked.",
        },
    )


def _event_to_sse(event: dict[str, Any]) -> bytes:
    event_name = str(event.get("event") or event.get("type") or "message")
    data = event.get("data", event)
    if isinstance(data, str):
        payload = data
    else:
        payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_name}\ndata: {payload}\n\n".encode("utf-8")


def _mode_for_result(result: AnalysisResponse | CompareResponse | TopicResponse) -> str:
    if isinstance(result, TopicResponse):
        return result.mode
    if isinstance(result, CompareResponse):
        return "multi_ticker"
    return "single_ticker"


def _status_for_result(result: AnalysisResponse | CompareResponse | TopicResponse) -> str:
    if isinstance(result, CompareResponse):
        statuses = {str(item.status).lower() for item in result.results.values()}
        return "failed" if "failed" in statuses and len(statuses) == 1 else "partial" if "failed" in statuses else "success"
    return str(result.status)


def _response_text(result: AnalysisResponse | CompareResponse | TopicResponse) -> str:
    if isinstance(result, TopicResponse):
        parts = [
            f"**요약**\n{result.executive_summary}",
            f"**핵심 논지**\n{result.core_thesis}",
        ]
        if result.uncertainty:
            parts.append(f"**불확실성**\n{result.uncertainty}")
        return "\n\n".join(part for part in parts if part.strip())
    if isinstance(result, CompareResponse):
        tickers = ", ".join(result.tickers)
        return f"**비교 분석 완료**\n대상: {tickers}\n소요시간: {result.elapsed_s}s"
    return "\n\n".join(
        part
        for part in (
            f"**요약**\n{result.summary}",
            f"**결론**\n{result.conclusion}",
            f"**불확실성**\n{result.uncertainty}" if result.uncertainty else "",
        )
        if part.strip()
    )


def _metric_rows(result: AnalysisResponse | TopicResponse) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric in getattr(result, "key_metrics", []) or []:
        rows.append(
            {
                "지표": metric.name,
                "값": metric.value,
                "단위": metric.unit or "",
                "기준일": metric.as_of or "unknown",
                "source": metric.source or "unknown",
                "freshness": metric.freshness_status or "unknown",
                "doc_id": ", ".join(metric.evidence_doc_ids or []),
                "맥락": metric.context or "",
            }
        )
    return rows


def _scenario_rows(result: TopicResponse) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in result.scenario_analysis or []:
        rows.append(
            {
                "시나리오": item.scenario,
                "확률": item.probability,
                "예상 결과": item.expected_outcome,
                "자산 영향": item.asset_implication,
                "판단": item.decision_read,
                "doc_id": ", ".join(item.evidence_doc_ids or []),
            }
        )
    return rows


def _execution_rows(result: TopicResponse) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in result.execution_strategy or []:
        rows.append(
            {
                "전략": item.strategy,
                "트리거": item.trigger,
                "근거": item.rationale,
                "리스크 통제": item.risk_control,
                "doc_id": ", ".join(item.evidence_doc_ids or []),
            }
        )
    return rows


def _comparison_rows(result: CompareResponse) -> list[dict[str, Any]]:
    return [
        {
            "ticker": ticker,
            "status": response.status,
            "sentiment": response.sentiment,
            "confidence": response.confidence,
            "summary": _clip(response.summary, 500),
            "conclusion": _clip(response.conclusion, 500),
        }
        for ticker, response in result.results.items()
    ]


def _citation_items(result: AnalysisResponse | TopicResponse) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in getattr(result, "citations", []) or []:
        key = citation.doc_id or f"{citation.source}:{citation.title}:{citation.date}"
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "doc_id": citation.doc_id or "",
                "source": citation.source,
                "title": citation.title,
                "date": citation.date,
                "url": "",
            }
        )

    for item in getattr(result, "raw_context", []) or []:
        doc_id = str(item.metadata.get("doc_id") or item.metadata.get("id") or item.title or "")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        items.append(
            {
                "doc_id": doc_id,
                "source": item.source,
                "title": item.title,
                "date": item.date,
                "url": item.metadata.get("url") or item.metadata.get("link") or "",
            }
        )
    return items


def response_to_openbb_events(result: AnalysisResponse | CompareResponse | TopicResponse) -> list[dict[str, Any]]:
    mode = _mode_for_result(result)
    status = _status_for_result(result)
    events: list[dict[str, Any]] = [
        reasoning_step(
            "FinGPT 분석 결과를 OpenBB Workspace artifact로 변환했습니다.",
            status="complete",
            details={"mode": mode, "status": status},
        )
    ]

    if status == "partial":
        error_metadata = getattr(result, "error_metadata", None) or getattr(result, "uncertainty", "")
        events.append(
            reasoning_step(
                "결과가 partial 상태입니다. 근거 부족 축은 memo와 diagnostics를 함께 확인해야 합니다.",
                status="warning",
                details={"reason": error_metadata or "partial"},
            )
        )
    elif status == "failed":
        events.append(
            reasoning_step(
                "FinGPT pipeline이 failed 상태를 반환했습니다.",
                status="error",
                details={"reason": getattr(result, "error_metadata", "")},
            )
        )

    events.append(message_chunk(_response_text(result)))

    if isinstance(result, CompareResponse):
        events.append(table_event("FinGPT 비교 분석", _comparison_rows(result)))
    else:
        metric_rows = _metric_rows(result)
        if metric_rows:
            events.append(table_event("핵심 수치 / 기준일 / 출처", metric_rows))
        if isinstance(result, TopicResponse):
            scenario_rows = _scenario_rows(result)
            if scenario_rows:
                events.append(table_event("시나리오 분석", scenario_rows))
            execution_rows = _execution_rows(result)
            if execution_rows:
                events.append(table_event("실행 전략", execution_rows))
        citation_rows = _citation_items(result)
        if citation_rows:
            events.append(citations_event(citation_rows))
            events.append(table_event("근거 문서", citation_rows))

    events.append(done_event())
    return events


def _progress_event_to_openbb(item: dict[str, Any]) -> dict[str, Any] | None:
    event = str(item.get("event") or "")
    if event in {"pipeline_started", "stage_started"}:
        stage = item.get("stage") or item.get("payload", {}).get("stage") or "pipeline"
        return reasoning_step(f"FinGPT {stage} 단계 실행 중", status="running", details=item)
    if event in {"stage_completed", "pipeline_completed"}:
        stage = item.get("stage") or item.get("payload", {}).get("stage") or "pipeline"
        return reasoning_step(f"FinGPT {stage} 단계 완료", status="complete", details=item)
    if event == "partial_result":
        payload = item.get("payload") or {}
        text = payload.get("executive_summary") or payload.get("summary") or "초기 판단 결과가 생성되었습니다."
        return message_chunk(f"**초기 판단**\n{text}")
    return None


@router.get("/agents.json")
async def agents_json() -> JSONResponse:
    settings = load_settings()
    return JSONResponse(build_agents_json(settings))


@router.post("/query")
async def openbb_query(request: Request) -> StreamingResponse:
    settings = load_settings()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    async def event_generator():
        if not bool(getattr(settings, "openbb_agent_enabled", False)):
            yield _event_to_sse(
                error_event(
                    "openbb_contract_error",
                    "OpenBB agent adapter is disabled. Set OPENBB_AGENT_ENABLED=true to expose FinGPT to OpenBB Workspace.",
                )
            )
            yield _event_to_sse(done_event())
            return

        try:
            universal_request = build_universal_request_from_openbb(payload if isinstance(payload, dict) else {})
        except Exception as exc:  # noqa: BLE001
            yield _event_to_sse(error_event("validation_error", _clip(exc, 500)))
            yield _event_to_sse(done_event())
            return

        if _truthy(request.headers.get("x-fingpt-openbb-dry-run")):
            yield _event_to_sse(
                reasoning_step(
                    "OpenBB query를 FinGPT universal request로 변환했습니다.",
                    status="complete",
                    details={
                        "ticker": universal_request.ticker,
                        "mode_hint": universal_request.mode_hint,
                        "question": universal_request.question,
                        "dry_run": True,
                    },
                )
            )
            for openbb_event in response_to_openbb_events(_dry_run_response(universal_request)):
                yield _event_to_sse(openbb_event)
            return

        q: threadqueue.Queue = threadqueue.Queue(maxsize=512)
        sentinel = object()

        def sink(event: dict[str, Any]) -> None:
            try:
                q.put_nowait(event)
            except threadqueue.Full:
                pass

        async def run_pipeline() -> None:
            try:
                result = await dispatch_async(universal_request, event_sink=sink)
                q.put_nowait({"event": "result", "payload": result})
            except Exception as exc:  # noqa: BLE001
                logger.error("[OPENBB_AGENT] query failed: %s", exc)
                q.put_nowait({"event": "pipeline_failed", "error": exc})
            finally:
                q.put_nowait(sentinel)

        task = asyncio.create_task(run_pipeline())
        try:
            yield _event_to_sse(
                reasoning_step(
                    "OpenBB query를 FinGPT universal request로 변환했습니다.",
                    status="complete",
                    details={
                        "ticker": universal_request.ticker,
                        "mode_hint": universal_request.mode_hint,
                        "question": universal_request.question,
                    },
                )
            )
            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 15.0)
                except threadqueue.Empty:
                    yield b": heartbeat\n\n"
                    continue
                if item is sentinel:
                    break
                if not isinstance(item, dict):
                    continue
                if item.get("event") == "result":
                    result = item.get("payload")
                    if isinstance(result, (AnalysisResponse, CompareResponse, TopicResponse)):
                        for openbb_event in response_to_openbb_events(result):
                            yield _event_to_sse(openbb_event)
                    else:
                        yield _event_to_sse(error_event("openbb_contract_error", "FinGPT result payload was not structured."))
                    continue
                if item.get("event") == "pipeline_failed":
                    yield _event_to_sse(
                        error_event(
                            "infrastructure_error",
                            "FinGPT pipeline failed while processing the OpenBB query. Check server logs for the traceback.",
                        )
                    )
                    continue
                converted = _progress_event_to_openbb(item)
                if converted:
                    yield _event_to_sse(converted)
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
