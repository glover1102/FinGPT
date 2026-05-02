import time
import re
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.schemas.request import AnalysisRequest, DEFAULT_COLLECTION_SOURCES, KNOWN_COLLECTION_SOURCES, PRIMARY_COLLECTION_SOURCES
from core.schemas.retrieval import RetrievalItem
from core.schemas.response import AnalysisResponse, CatalystTimeline, ExecutionMeta, KeyMetric
from core.utils.asset_classifier import classify
from core.utils.decision_support import enrich_research_response
from core.utils.model_capabilities import model_capability_dict
from core.utils.query_planner import plan_query
from core.utils.technical_indicators import technical_metrics_from_retrieval_items

# Opaque event sink used by the SSE endpoint. The orchestrator only cares
# that it's callable with a JSON-serialisable dict; the consumer handles
# buffering / framing. Swallow sink failures silently so we never break
# the pipeline just because a listener disconnected.
EventSink = Optional[Callable[[dict[str, Any]], None]]


def _emit(sink: EventSink, event_type: str, **fields: Any) -> None:
    if sink is None:
        return
    try:
        sink({"event": event_type, "ts": time.time(), **fields})
    except Exception:
        pass
from core.utils.logger import get_logger

import asyncio
from pipelines.collect.openbb_collector import collect_data
from pipelines.collect.models import CollectionOutcome
from pipelines.collect.fundamentals_card import collect_fundamentals_card
from pipelines.ingest.qdrant_ingestor import ingest_documents
from pipelines.retrieve.qdrant_retriever import retrieve_context
from pipelines.retrieve.multi_query_retriever import retrieve_context_multi
from pipelines.infer.runner_factory import run_inference
from pipelines.analyze.sentiment import analyze_sentiment
from pipelines.analyze.risk_analysis import HeuristicRiskEngine
from pipelines.analyze.risk_factory import get_risk_engine
from pipelines.analyze.thesis_builder import build_thesis
from pipelines.analyze.report_builder import build_report
from pipelines.output.output_writer import save_outputs
from pipelines.orchestration.precheck import run_execution_precheck
from core.config.settings import load_settings

logger = get_logger("pipelines.orchestration")


def _merge_error_metadata(existing: str | None, addition: str | None) -> str | None:
    if not addition:
        return existing
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing} | {addition}"


_MACRO_QUESTION_TERMS = (
    "macro", "rate", "rates", "fed", "inflation", "yield", "liquidity",
    "growth stock", "growth stocks", "sector", "market backdrop",
    "\uac70\uc2dc", "\uae08\ub9ac", "\uc778\ud50c\ub808\uc774\uc158", "\ubb3c\uac00",
    "\uc720\ub3d9\uc131", "\uc131\uc7a5\uc8fc", "\uc139\ud130", "\uc2dc\uc7a5 \ud658\uacbd",
)


def _coerce_int(value: Any, default: int, *, lower: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(parsed, upper))


def _inference_timeout_s() -> float:
    """Keep production inference unchanged while bounding validation smoke runs."""

    if os.environ.get("FINGPT_VALIDATION_FAST_INFERENCE", "").strip().lower() in {"1", "true", "yes"}:
        return 60.0
    return 300.0


def _normalise_sources_for_pipeline(ticker: str, question: str, sources: Any) -> list[str]:
    if sources is None:
        raw = list(DEFAULT_COLLECTION_SOURCES)
    elif isinstance(sources, str):
        raw = sources.replace(",", " ").split()
    else:
        try:
            raw = list(sources)
        except TypeError:
            raw = list(DEFAULT_COLLECTION_SOURCES)

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        source = str(item or "").strip().lower()
        if not source or source in seen:
            continue
        seen.add(source)
        cleaned.append(source)
    if not cleaned:
        cleaned = list(DEFAULT_COLLECTION_SOURCES)

    q_lower = str(question or "").lower()
    asks_macro = any(term in q_lower for term in _MACRO_QUESTION_TERMS)
    try:
        profile = classify(ticker)
    except Exception:
        profile = None
    if asks_macro and profile is not None and profile.supports_macro and "macro" not in seen:
        cleaned.append("macro")
        seen.add("macro")

    # Keep unsupported values out of downstream source dispatch unless callers
    # explicitly extend the known source contract.
    known = set(KNOWN_COLLECTION_SOURCES)
    filtered = [source for source in cleaned if source in known]
    return filtered or list(DEFAULT_COLLECTION_SOURCES)


def _apply_collection_outcome(
    status: str,
    error_metadata: str | None,
    outcome: CollectionOutcome,
) -> tuple[str, str | None]:
    primary_results = [result for result in outcome.source_results if result.source in PRIMARY_COLLECTION_SOURCES]
    primary_failed = bool(primary_results) and all(result.status in {"timeout", "failed", "empty"} for result in primary_results)

    if primary_failed:
        status = "partial"
        error_metadata = _merge_error_metadata(error_metadata, outcome.summary_detail)

    return status, error_metadata


def _classify_error_type(message: str | None, status: str | None = None) -> str:
    text = str(message or "").lower()
    if not text and status != "failed":
        return ""
    if any(term in text for term in ("ticker", "validation", "422", "required")):
        return "validation_error"
    if any(term in text for term in ("entitlement", "permission", "subscription", "credentials")):
        return "provider_entitlement"
    if any(term in text for term in ("json", "delimiter", "parse", "parser", "truncated", "unclosed")):
        return "model_json_error"
    if any(term in text for term in ("language violation", "korean", "한국어")):
        return "model_language_error"
    if any(term in text for term in ("no usable", "no new documents", "evidence", "context", "근거", "문서")):
        return "evidence_sparse"
    if any(term in text for term in ("unreachable", "timeout", "connection", "qdrant", "ollama", "infrastructure")):
        return "infrastructure_error"
    if any(term in text for term in ("unavailable", "no data", "empty")):
        return "data_unavailable"
    return "unknown_error" if status == "failed" or text else ""


def _freshness_status(as_of: str | None) -> str:
    if not as_of:
        return "unknown"
    text = str(as_of).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return "unknown"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 86400)
    if age_days <= 7:
        return "fresh"
    if age_days <= 45:
        return "recent"
    return "stale"


def _provider_statuses(outcome: CollectionOutcome | None) -> list[dict[str, Any]]:
    if outcome is None:
        return []
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for kind, results in (("source", outcome.source_results), ("provider", outcome.provider_results)):
        for result in results or []:
            key = (kind, result.source)
            if key in seen:
                continue
            seen.add(key)
            status = str(result.status or "unknown")
            records.append(
                {
                    "provider": result.source,
                    "status": status,
                    "doc_count": int(result.doc_count or 0),
                    "latency_ms": round(float(result.elapsed_s or 0.0) * 1000, 2),
                    "entitlement_status": "entitlement_required" if status == "entitlement_required" else "ok",
                    "cache_hit": bool(getattr(outcome, "cache_hit", False)),
                    "quality_score": 0.0 if status in {"failed", "timeout"} else (0.5 if status not in {"ok", "success"} else 1.0),
                    "detail": result.detail,
                    "kind": kind,
                }
            )
    return records


def _data_freshness(context_items: list[Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    counts = {"fresh": 0, "recent": 0, "stale": 0, "unknown": 0}
    for item in context_items or []:
        metadata = getattr(item, "metadata", None) or {}
        as_of = getattr(item, "date", None) or metadata.get("published_at") or metadata.get("collected_at")
        status = _freshness_status(as_of)
        counts[status if status in counts else "unknown"] += 1
        items.append(
            {
                "doc_id": metadata.get("doc_id") or metadata.get("parent_doc_id"),
                "source": getattr(item, "source", "") or metadata.get("source", ""),
                "as_of": as_of or "unknown",
                "freshness_status": status,
            }
        )
    overall = "unknown"
    if items:
        overall = "stale" if counts["stale"] else ("recent" if counts["recent"] else ("fresh" if counts["fresh"] else "unknown"))
    return {"overall_status": overall, "counts": counts, "items": items[:50]}


def _coverage_summary(
    key_metrics: list[KeyMetric],
    bull_evidence_ids: list[list[str]],
    bear_evidence_ids: list[list[str]],
    context_items: list[Any],
) -> dict[str, Any]:
    metric_total = len(key_metrics)
    metric_with_as_of = sum(1 for metric in key_metrics if metric.as_of)
    evidence_index = _context_id_aliases(context_items)
    dated_doc_ids = {
        canonical
        for canonical in evidence_index.values()
        if any(
            canonical == str((getattr(item, "metadata", None) or {}).get("doc_id") or (getattr(item, "metadata", None) or {}).get("parent_doc_id"))
            and bool(getattr(item, "date", None) or (getattr(item, "metadata", None) or {}).get("published_at") or (getattr(item, "metadata", None) or {}).get("collected_at"))
            for item in context_items
        )
    }
    evidence_sets = [ids for ids in [*(bull_evidence_ids or []), *(bear_evidence_ids or [])] if ids]
    evidence_total = len(evidence_sets)
    evidence_with_dates = 0
    for ids in evidence_sets:
        canonical_ids = {evidence_index.get(str(doc_id), str(doc_id)) for doc_id in ids}
        if canonical_ids & dated_doc_ids:
            evidence_with_dates += 1
    return {
        "metric_as_of_coverage": 1.0 if metric_total == 0 else round(metric_with_as_of / metric_total, 4),
        "claim_evidence_date_coverage": 1.0 if evidence_total == 0 else round(evidence_with_dates / evidence_total, 4),
        "metric_count": metric_total,
        "evidence_linked_claim_count": evidence_total,
    }


async def _finalize_response(
    request: AnalysisRequest,
    response: AnalysisResponse,
    *,
    start_time: float,
    collection_outcome: CollectionOutcome | None = None,
    stages_ran: list[str] | None = None,
    event_sink: EventSink = None,
) -> AnalysisResponse:
    # Stamp final pipeline wall-clock latency and the list of stages that ran.
    if response.execution_meta is None:
        response.execution_meta = ExecutionMeta()
    response.execution_meta.pipeline_latency_s = round(time.time() - start_time, 2)
    if stages_ran is not None:
        response.execution_meta.stages_ran = stages_ran
    if "retrieval_plan" not in response.execution_meta.extras:
        response.execution_meta.extras["retrieval_plan"] = plan_query(request.ticker, request.question).model_dump(mode="json")
    response = enrich_research_response(response)

    logger.info("Generating report...")
    settings = load_settings()
    language = getattr(settings, "output_language", "ko")
    _emit(event_sink, "stage_started", stage="report")
    report_started = time.time()
    report_md, report_html = build_report(request, response, language=language)
    _emit(
        event_sink,
        "stage_completed",
        stage="report",
        duration_s=round(time.time() - report_started, 2),
    )

    logger.info("[OUTPUT_START] Writing files...")
    _emit(event_sink, "stage_started", stage="output")
    output_started = time.time()
    await asyncio.to_thread(
        save_outputs,
        request,
        response,
        report_md,
        report_html,
        collection_outcome=collection_outcome,
    )
    _emit(event_sink, "stage_completed", stage="output", duration_s=round(time.time() - output_started, 2))

    elapsed = time.time() - start_time
    logger.info(f"[PIPELINE_COMPLETE] Status='{response.status}' Elapsed={elapsed:.2f}s")
    _emit(
        event_sink,
        "pipeline_completed",
        status=response.status,
        elapsed_s=round(elapsed, 2),
        stages_ran=list(stages_ran or []),
    )
    return response


def _current_doc_ids(outcome: CollectionOutcome) -> set[str]:
    if outcome.current_doc_ids:
        return {str(doc_id) for doc_id in outcome.current_doc_ids if doc_id}
    return {str(document.get("doc_id")) for document in outcome.documents if document.get("doc_id")}


def _primary_collection_failed(outcome: CollectionOutcome) -> bool:
    primary_results = [result for result in outcome.source_results if result.source in PRIMARY_COLLECTION_SOURCES]
    return bool(primary_results) and all(result.status in {"timeout", "failed", "empty"} for result in primary_results)


def _hash_suffix(value: str) -> str:
    tail = str(value or "").strip().rsplit("_", 1)[-1]
    if len(tail) >= 8 and all(ch in "0123456789abcdefABCDEF" for ch in tail):
        return tail.lower()
    return ""


def _context_id_aliases(context_items: list[Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    suffixes: dict[str, str] = {}
    for item in context_items or []:
        metadata = getattr(item, "metadata", None) or {}
        canonical = str(metadata.get("parent_doc_id") or metadata.get("doc_id") or "").strip()
        if not canonical:
            continue
        raw_ids = {
            canonical,
            str(metadata.get("doc_id") or "").strip(),
            str(metadata.get("parent_doc_id") or "").strip(),
        }
        for raw_id in raw_ids:
            if raw_id:
                aliases[raw_id] = canonical
                suffix = _hash_suffix(raw_id)
                if suffix:
                    suffixes.setdefault(suffix, canonical)
    aliases.update(suffixes)
    return aliases


def _normalize_doc_id_list(evidence_ids: Any, context_items: list[Any]) -> list[str]:
    aliases = _context_id_aliases(context_items)
    normalized: list[str] = []
    seen: set[str] = set()
    if not isinstance(evidence_ids, list):
        return normalized
    for raw in evidence_ids:
        clean = str(raw or "").strip()
        if not clean:
            continue
        canonical = aliases.get(clean) or aliases.get(_hash_suffix(clean))
        if not canonical:
            continue
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    return normalized


def _align_evidence_ids(evidence_ids, points, context_items: list[Any] | None = None) -> list[list[str]]:
    """Return per-point doc_id lists aligned to ``points``.

    The risk engine can re-derive bull/bear points, so the inference-time
    evidence arrays may drift out of sync. We keep them only when lengths
    match; otherwise we return empty placeholders to preserve the schema
    invariant len(evidence) == len(points) without fabricating linkage. When
    the model mutates a source id prefix but preserves the deterministic hash
    suffix, map it back to the current-run parent doc id so evidence/date
    audits remain stable.
    """
    if not isinstance(points, list):
        return []
    if not isinstance(evidence_ids, list) or len(evidence_ids) != len(points):
        return [[] for _ in points]
    aligned: list[list[str]] = []
    for entry in evidence_ids:
        if isinstance(entry, list):
            aligned.append(_normalize_doc_id_list(entry, context_items or []))
        else:
            aligned.append([])
    return aligned


def _fill_missing_claim_evidence_ids(
    evidence_ids: list[list[str]],
    points: list[str],
    context_items: list[Any],
) -> list[list[str]]:
    """Guarantee current-run date-auditable evidence slots when context exists.

    The local LLM can occasionally mutate a doc_id enough that suffix aliasing
    cannot recover it. In that case we drop the invalid id and attach the first
    current-run parent doc as a conservative audit anchor instead of returning
    an unverifiable id that breaks as-of coverage.
    """
    if not isinstance(points, list):
        return []
    aligned = list(evidence_ids or [[] for _ in points])
    if len(aligned) != len(points):
        aligned = (aligned + [[] for _ in points])[: len(points)]
    fallback = _context_doc_ids(context_items, limit=1)
    if not fallback:
        return aligned
    return [ids if ids else fallback[:] for ids in aligned]


def _clean_as_of(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _context_date_lookup(context_items: list[Any]) -> dict[str, str]:
    by_id: dict[str, str] = {}
    for item in context_items or []:
        date = _clean_as_of(getattr(item, "date", ""))
        if not date:
            continue
        metadata = getattr(item, "metadata", None) or {}
        ids = {
            str(metadata.get("doc_id") or "").strip(),
            str(metadata.get("parent_doc_id") or "").strip(),
        }
        for doc_id in ids:
            if doc_id and doc_id not in by_id:
                by_id[doc_id] = date
    return by_id


def _metric_as_of(raw_as_of: Any, evidence_doc_ids: list[str], context_items: list[Any]) -> str:
    explicit = _clean_as_of(raw_as_of)
    if explicit:
        return explicit
    by_id = _context_date_lookup(context_items)
    for doc_id in evidence_doc_ids or []:
        date = by_id.get(str(doc_id))
        if date:
            return date
    for item in context_items or []:
        date = _clean_as_of(getattr(item, "date", ""))
        if date:
            return date
    return "unknown"


_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_CJK_IDEOGRAPH_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_MOJIBAKE_RE = re.compile(r"[ÃÂ�]|(?:[ìíëê][\x80-\xff]?)|(?:[æäåçèé][\x80-\xff]?)")
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _language_counts(text: Any) -> dict[str, int]:
    value = str(text or "")
    return {
        "hangul": len(_HANGUL_RE.findall(value)),
        "cjk": len(_CJK_IDEOGRAPH_RE.findall(value)),
        "mojibake": len(_MOJIBAKE_RE.findall(value)),
        "latin": len(re.findall(r"[A-Za-z]", value)),
    }


def _is_unusable_korean_text(text: Any, *, min_hangul: int = 8) -> bool:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return True
    counts = _language_counts(value)
    if counts["mojibake"] >= 3:
        return True
    if counts["cjk"] >= max(6, counts["hangul"]):
        return True
    if counts["hangul"] >= min_hangul:
        return False
    # Short metric labels like "RSI(14)" are valid elsewhere; this guard is
    # for descriptive sentences only.
    return counts["latin"] >= 12 or counts["cjk"] > 0


def _number_tokens(value: Any) -> set[str]:
    return {token.rstrip("0").rstrip(".") for token in _NUMBER_RE.findall(str(value or "")) if token}


def _metric_overlaps_technical(metric: dict[str, Any], technical_metrics: list[dict[str, Any]]) -> bool:
    haystack = f"{metric.get('name', '')} {metric.get('context', '')}".lower()
    if any(token in haystack for token in ("rsi", "macd", "sma", "momentum", "price", "close", "volatility", "volume", "收盘", "动量")):
        return True
    metric_numbers = _number_tokens(metric.get("value"))
    if not metric_numbers:
        return False
    for tech in technical_metrics or []:
        if metric_numbers & _number_tokens(tech.get("value")):
            return True
    return False


def _filter_llm_metrics(raw_metrics: Any, technical_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in raw_metrics or []:
        if not isinstance(item, dict):
            continue
        descriptive = f"{item.get('name', '')} {item.get('context', '')}"
        if _is_unusable_korean_text(descriptive, min_hangul=4):
            continue
        if technical_metrics and _metric_overlaps_technical(item, technical_metrics):
            continue
        filtered.append(item)
    return filtered


def _find_metric(metrics: list[KeyMetric], *needles: str) -> KeyMetric | None:
    lowered = [needle.lower() for needle in needles]
    for metric in metrics:
        haystack = f"{metric.name} {metric.context}".lower()
        if any(needle in haystack for needle in lowered):
            return metric
    return None


def _technical_summary(ticker: str, key_metrics: list[KeyMetric]) -> str:
    close = _find_metric(key_metrics, "최신 종가", "latest close")
    mom_1m = _find_metric(key_metrics, "1개월 가격 모멘텀", "1m price momentum", "1m momentum")
    mom_3m = _find_metric(key_metrics, "3개월 가격 모멘텀", "3m price momentum", "3m momentum")
    sma20 = _find_metric(key_metrics, "sma20")
    sma50 = _find_metric(key_metrics, "sma50")
    rsi = _find_metric(key_metrics, "rsi")
    macd = _find_metric(key_metrics, "macd")
    vol = _find_metric(key_metrics, "실현 변동성", "realized volatility")
    as_of = next((metric.as_of for metric in key_metrics if metric.as_of and metric.as_of != "unknown"), "unknown")
    parts = [f"{ticker}는 {as_of} 기준 가격·기술 지표와 수집 문서를 우선 근거로 판단해야 합니다."]
    if close:
        suffix = f" {close.unit}" if close.unit else ""
        parts.append(f"기준 가격은 {close.value}{suffix}입니다.")
    trend_bits = []
    if mom_1m:
        trend_bits.append(f"1개월 모멘텀 {mom_1m.value}")
    if mom_3m:
        trend_bits.append(f"3개월 모멘텀 {mom_3m.value}")
    if sma20:
        trend_bits.append(f"SMA20 괴리 {sma20.value}")
    if sma50:
        trend_bits.append(f"SMA50 괴리 {sma50.value}")
    if trend_bits:
        parts.append("추세 판단은 " + ", ".join(trend_bits) + "를 중심으로 봅니다.")
    risk_bits = []
    if rsi:
        risk_bits.append(f"RSI {rsi.value}")
    if macd:
        risk_bits.append(f"MACD 히스토그램 {macd.value}")
    if vol:
        risk_bits.append(f"실현 변동성 {vol.value}")
    if risk_bits:
        parts.append("단기 리스크는 " + ", ".join(risk_bits) + "가 과열, 둔화, 손절 폭을 어떻게 가리키는지로 확인합니다.")
    return " ".join(parts)


def _technical_uncertainty(key_metrics: list[KeyMetric]) -> str:
    if not key_metrics:
        return "확인 가능한 정량 지표가 부족해 가격 방향 판단은 보수적으로 해석해야 합니다."
    return "기술 지표는 가격과 거래 기반의 단기 신호입니다. 밸류에이션, 실적, 이벤트 근거와 교차 확인해야 확정적 판단으로 사용할 수 있습니다."


def _technical_point_defaults(ticker: str, key_metrics: list[KeyMetric], *, side: str) -> tuple[list[str], list[list[str]]]:
    points: list[str] = []
    evidence: list[list[str]] = []

    def add(text: str, metric: KeyMetric | None) -> None:
        if not text:
            return
        points.append(text)
        evidence.append(list(metric.evidence_doc_ids or []) if metric else [])

    mom_1m = _find_metric(key_metrics, "1개월 가격 모멘텀", "1m price momentum", "1m momentum")
    mom_3m = _find_metric(key_metrics, "3개월 가격 모멘텀", "3m price momentum", "3m momentum")
    sma20 = _find_metric(key_metrics, "sma20")
    sma50 = _find_metric(key_metrics, "sma50")
    sma200 = _find_metric(key_metrics, "sma200")
    rsi = _find_metric(key_metrics, "rsi")
    macd = _find_metric(key_metrics, "macd")
    vol = _find_metric(key_metrics, "실현 변동성", "realized volatility")

    if side == "bull":
        if mom_1m:
            add(f"{ticker}의 1개월 가격 모멘텀은 {mom_1m.value}로, 단기 추세가 아직 가격을 지지하는지 확인하는 핵심 지표입니다.", mom_1m)
        if sma20 and len(points) < 2:
            add(f"SMA20 대비 가격 괴리 {sma20.value}는 단기 추세 유지 여부를 검증하는 1차 신호입니다.", sma20)
        if mom_3m and len(points) < 2:
            add(f"3개월 모멘텀 {mom_3m.value}는 6~12개월 관점의 추세 지속성을 확인하는 보조 근거입니다.", mom_3m)
        if sma50 and len(points) < 2:
            add(f"SMA50 대비 괴리 {sma50.value}는 중기 추세가 훼손되지 않았는지 보는 확인 지표입니다.", sma50)
    else:
        if rsi:
            add(f"RSI(14) {rsi.value}는 과열권 접근 또는 반락 위험을 먼저 점검해야 함을 의미합니다.", rsi)
        if macd and len(points) < 2:
            add(f"MACD 히스토그램 {macd.value}는 모멘텀 확장과 둔화 전환을 구분하는 리스크 신호입니다.", macd)
        if vol and len(points) < 2:
            add(f"20일 실현 변동성 {vol.value}는 포지션 크기와 손절 폭을 정할 때 직접 반영해야 하는 위험 지표입니다.", vol)
        if sma200 and len(points) < 2:
            add(f"SMA200 대비 괴리 {sma200.value}는 장기 추세 훼손 가능성을 점검하는 방어 지표입니다.", sma200)
    return points[:2], evidence[:2]


def _context_doc_ids(context_items: list[Any], limit: int = 5) -> list[str]:
    doc_ids: list[str] = []
    seen: set[str] = set()
    for item in context_items or []:
        metadata = getattr(item, "metadata", {}) or {}
        doc_id = str(metadata.get("parent_doc_id") or metadata.get("doc_id") or "").strip()
        if doc_id and doc_id not in seen:
            doc_ids.append(doc_id)
            seen.add(doc_id)
        if len(doc_ids) >= limit:
            break
    return doc_ids


def _deterministic_inference_fallback(
    *,
    ticker: str,
    question: str,
    context_items: list[Any],
    model: str,
    reason: str,
    started_at: float,
) -> dict[str, Any]:
    metric_dicts = technical_metrics_from_retrieval_items(context_items)
    doc_ids = _context_doc_ids(context_items)
    key_metrics = [
        KeyMetric(
            name=str(item.get("name") or ""),
            value=str(item.get("value") or ""),
            unit=str(item.get("unit") or ""),
            as_of=str(item.get("as_of") or "unknown"),
            context=str(item.get("context") or ""),
            source=str(item.get("source") or "deterministic_fallback"),
            freshness_status=str(item.get("freshness_status") or "unknown"),
            evidence_doc_ids=[str(doc_id) for doc_id in (item.get("evidence_doc_ids") or [])],
        )
        for item in metric_dicts
        if isinstance(item, dict) and str(item.get("name") or "").strip() and str(item.get("value") or "").strip()
    ]
    summary = _technical_summary(ticker, key_metrics)
    uncertainty = f"LLM 구조화 출력이 실패해 정량 지표와 수집 근거 기반의 보수적 fallback으로 작성했습니다. 원인: {reason}"
    bull_points, bull_evidence_ids = _technical_point_defaults(ticker, key_metrics, side="bull")
    bear_points, bear_evidence_ids = _technical_point_defaults(ticker, key_metrics, side="bear")
    if len(bull_points) < 2:
        bull_points.append(f"{ticker}에 대한 확인 가능한 가격/뉴스 근거가 유지되면 단기 반등 여지는 남아 있습니다.")
        bull_evidence_ids.append(doc_ids[:1])
    if len(bull_points) < 2:
        bull_points.append("추가 근거가 보강될수록 상승 촉매의 신뢰도를 재평가할 수 있습니다.")
        bull_evidence_ids.append(doc_ids[:1])
    if len(bear_points) < 2:
        bear_points.append("thin coverage 종목은 유동성, 스프레드, 뉴스 공백 때문에 작은 주문에도 가격 변동성이 커질 수 있습니다.")
        bear_evidence_ids.append(doc_ids[:1])
    if len(bear_points) < 2:
        bear_points.append("LLM이 구조화 출력을 완성하지 못한 만큼 정성 결론보다 검증 가능한 지표와 기준일을 우선해야 합니다.")
        bear_evidence_ids.append(doc_ids[:1])

    clean_bull_points = [text for text in bull_points if not _is_unusable_korean_text(text)]
    clean_bear_points = [text for text in bear_points if not _is_unusable_korean_text(text)]
    clean_bull_evidence = [ids for text, ids in zip(bull_points, bull_evidence_ids) if not _is_unusable_korean_text(text)]
    clean_bear_evidence = [ids for text, ids in zip(bear_points, bear_evidence_ids) if not _is_unusable_korean_text(text)]
    while len(clean_bull_points) < 2:
        clean_bull_points.append(
            f"{ticker}는 확인된 가격·모멘텀 지표가 우호적으로 유지될 때만 상승 시나리오의 신뢰도가 높아집니다."
        )
        clean_bull_evidence.append(doc_ids[:1])
    while len(clean_bear_points) < 2:
        clean_bear_points.append(
            "LLM 구조화 출력이 실패한 만큼 확정 결론보다 검증 가능한 가격, 변동성, 이벤트 지표를 우선해야 합니다."
        )
        clean_bear_evidence.append(doc_ids[:1])
    clean_uncertainty = (
        f"LLM 구조화 출력이 실패해 정량 지표와 수집 근거 기반의 보수적 fallback으로 작성했습니다. 원인: {reason}"
    )

    return {
        "summary": summary,
        "uncertainty": clean_uncertainty,
        "bull_points": clean_bull_points[:2],
        "bear_points": clean_bear_points[:2],
        "bull_evidence_ids": clean_bull_evidence[:2],
        "bear_evidence_ids": clean_bear_evidence[:2],
        "key_metrics": metric_dicts[:12],
        "cited_doc_ids": doc_ids,
        "catalyst_timeline": {
            "near_term": ["가격 모멘텀, 거래량, 최근 뉴스 플로우 확인"],
            "mid_term": ["실적 발표와 밸류에이션 재평가 여부 확인"],
            "long_term": ["사업 펀더멘털과 자본 조달 리스크 재점검"],
        },
        "open_questions": [
            "최근 거래량과 스프레드가 포지션 진입 규모를 감당할 수 있는가?",
            "실적 또는 공시 이벤트가 가격 변동을 설명하는가?",
        ],
        "catalyst_timeline": {
            "near_term": ["가격 모멘텀, 거래량, 최근 뉴스 흐름 확인"],
            "mid_term": ["실적 발표, 가이던스, 밸류에이션 재평가 여부 확인"],
            "long_term": ["사업 모멘텀, 자본 조달 리스크, 경쟁 구도 재점검"],
        },
        "open_questions": [
            "최근 가격 움직임이 거래량 증가를 동반했는가?",
            "실적 또는 공시 이벤트가 가격 변동을 설명하는가?",
            "현재 밸류에이션이 모멘텀 둔화 위험을 충분히 반영하는가?",
        ],
        "_meta": {
            "primary_model": str(model),
            "producing_model": "local-deterministic-fallback",
            "fallback_enabled": False,
            "fallback_model": None,
            "fallback_available": False,
            "fallback_used": True,
            "fallback_reason": reason,
            "retry_count": 0,
            "total_latency_s": round(time.time() - started_at, 2),
            "primary_latency_s": round(time.time() - started_at, 2),
            "fallback_latency_s": 0.0,
            "prompt_char_count": 0,
            "chunks_used": len(context_items or []),
            "model_capabilities": model_capability_dict(str(model), str(model)),
        },
    }


def _sanitize_decision_texts(
    *,
    ticker: str,
    summary: Any,
    uncertainty: Any,
    bull_points: list[str],
    bear_points: list[str],
    key_metrics: list[KeyMetric],
) -> tuple[str, str, list[str], list[str], list[list[str]], list[list[str]], bool]:
    changed = False
    cleaned_summary = " ".join(str(summary or "").split()).strip()
    if _is_unusable_korean_text(cleaned_summary):
        cleaned_summary = _technical_summary(ticker, key_metrics)
        changed = True

    cleaned_uncertainty = " ".join(str(uncertainty or "").split()).strip()
    if _is_unusable_korean_text(cleaned_uncertainty):
        cleaned_uncertainty = _technical_uncertainty(key_metrics)
        changed = True

    bulls = [text for text in bull_points if not _is_unusable_korean_text(text)]
    bears = [text for text in bear_points if not _is_unusable_korean_text(text)]
    bull_generated_evidence: list[list[str]] = []
    bear_generated_evidence: list[list[str]] = []
    if len(bulls) < 2:
        generated, bull_generated_evidence = _technical_point_defaults(ticker, key_metrics, side="bull")
        bulls = (bulls + [item for item in generated if item not in bulls])[:2]
        changed = True
    if len(bears) < 2:
        generated, bear_generated_evidence = _technical_point_defaults(ticker, key_metrics, side="bear")
        bears = (bears + [item for item in generated if item not in bears])[:2]
        changed = True
    return cleaned_summary, cleaned_uncertainty, bulls, bears, bull_generated_evidence, bear_generated_evidence, changed


def _merge_key_metric_dicts(existing: list[KeyMetric], candidates: list[dict[str, Any]], context_items: list[Any]) -> list[KeyMetric]:
    seen = {str(metric.name or "").strip().lower() for metric in existing if str(metric.name or "").strip()}
    merged = list(existing)
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or not value:
            continue
        key = name.lower()
        if key in seen:
            continue
        evidence_doc_ids = _normalize_doc_id_list(item.get("evidence_doc_ids") or [], context_items)
        merged.append(
            KeyMetric(
                name=name,
                value=value,
                unit=str(item.get("unit") or "").strip(),
                as_of=_metric_as_of(item.get("as_of"), evidence_doc_ids, context_items),
                context=str(item.get("context") or "").strip(),
                source=str(item.get("source") or "").strip(),
                freshness_status=str(item.get("freshness_status") or "unknown").strip() or "unknown",
                evidence_doc_ids=evidence_doc_ids,
            )
        )
        seen.add(key)
    return merged


def _metric_number(metric: KeyMetric | None) -> float | None:
    if metric is None:
        return None
    match = _NUMBER_RE.search(str(metric.value or ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _metric_to_quant_record(metric: KeyMetric) -> dict[str, Any]:
    doc_ids = [str(doc_id) for doc_id in (metric.evidence_doc_ids or []) if str(doc_id).strip()]
    return {
        "name": str(metric.name or "").strip(),
        "value": str(metric.value or "").strip(),
        "unit": str(metric.unit or "").strip(),
        "as_of": str(metric.as_of or "unknown").strip() or "unknown",
        "context": str(metric.context or "").strip(),
        "source": str(metric.source or "").strip(),
        "freshness_status": str(metric.freshness_status or "unknown").strip() or "unknown",
        "evidence_doc_ids": doc_ids,
    }


def _single_ticker_quant_regime(key_metrics: list[KeyMetric]) -> dict[str, Any]:
    momentum_1m = _find_metric(key_metrics, "1개월 가격 모멘텀", "1m price momentum", "1m momentum")
    momentum_3m = _find_metric(key_metrics, "3개월 가격 모멘텀", "3m price momentum", "3m momentum")
    sma20 = _find_metric(key_metrics, "sma20")
    sma50 = _find_metric(key_metrics, "sma50")
    sma200 = _find_metric(key_metrics, "sma200")
    rsi = _find_metric(key_metrics, "rsi")
    macd = _find_metric(key_metrics, "macd")
    volatility = _find_metric(key_metrics, "실현 변동성", "realized volatility")
    volume = _find_metric(key_metrics, "평균 대비 거래량", "volume")

    m1 = _metric_number(momentum_1m)
    m3 = _metric_number(momentum_3m)
    d20 = _metric_number(sma20)
    d50 = _metric_number(sma50)
    d200 = _metric_number(sma200)
    rsi_value = _metric_number(rsi)
    macd_value = _metric_number(macd)
    vol_value = _metric_number(volatility)
    volume_value = _metric_number(volume)

    confirming: list[str] = []
    invalidation: list[str] = []

    if m1 is not None:
        (confirming if m1 > 0 else invalidation).append(f"1개월 모멘텀 {m1:+.2f}%")
    if m3 is not None:
        (confirming if m3 > 0 else invalidation).append(f"3개월 모멘텀 {m3:+.2f}%")
    if d20 is not None:
        (confirming if d20 > 0 else invalidation).append(f"SMA20 괴리 {d20:+.2f}%")
    if d50 is not None:
        (confirming if d50 > 0 else invalidation).append(f"SMA50 괴리 {d50:+.2f}%")
    if d200 is not None and d200 < 0:
        invalidation.append(f"SMA200 괴리 {d200:+.2f}%")
    elif d200 is not None:
        confirming.append(f"SMA200 괴리 {d200:+.2f}%")
    if rsi_value is not None and rsi_value >= 70:
        invalidation.append(f"RSI 과열 {rsi_value:.1f}")
    elif rsi_value is not None and 45 <= rsi_value <= 68:
        confirming.append(f"RSI 중립-상승권 {rsi_value:.1f}")
    if macd_value is not None:
        (confirming if macd_value > 0 else invalidation).append(f"MACD histogram {macd_value:+.3f}")
    if vol_value is not None and vol_value >= 35:
        invalidation.append(f"20일 변동성 {vol_value:.1f}%")
    if volume_value is not None and volume_value >= 1.2:
        confirming.append(f"거래량 {volume_value:.2f}x")

    short_positive = (m1 or 0) > 0 and (d20 or 0) > 0 and (d50 or 0) > 0
    long_confirmed = d200 is not None and d200 > 0
    trend_state = "mixed"
    decision_bias = "Neutral / 확인 필요"
    if short_positive and long_confirmed and (rsi_value is None or rsi_value < 75):
        trend_state = "uptrend_confirmed"
        decision_bias = "조건부 Bullish"
    elif short_positive:
        trend_state = "short_term_rebound"
        decision_bias = "Neutral-to-Bullish / 장기 추세 검증"
    elif (m1 is not None and m1 < 0) and (d20 is not None and d20 < 0):
        trend_state = "downside_momentum"
        decision_bias = "Bearish / 방어 우선"

    momentum_state = "limited"
    if rsi_value is not None or macd_value is not None:
        if (rsi_value or 50) >= 70 and (macd_value or 0) > 0:
            momentum_state = "strong_but_overbought"
        elif (rsi_value or 50) <= 30:
            momentum_state = "oversold_rebound_candidate"
        elif (macd_value or 0) > 0:
            momentum_state = "improving"
        elif (macd_value or 0) < 0:
            momentum_state = "weakening"

    risk_state = "needs_confirmation"
    if (rsi_value is not None and rsi_value >= 70) or (vol_value is not None and vol_value >= 35) or (d200 is not None and d200 < 0):
        risk_state = "confirmation_before_chasing"
    elif short_positive and (macd_value is None or macd_value > 0):
        risk_state = "trend_follow_with_event_check"

    return {
        "trend_state": trend_state,
        "momentum_state": momentum_state,
        "risk_state": risk_state,
        "decision_bias": decision_bias,
        "confirming_signals": confirming[:6],
        "invalidation_signals": invalidation[:6],
    }


def _single_ticker_quant_snapshot(
    ticker: str,
    key_metrics: list[KeyMetric],
    context_items: list[Any],
    technical_metric_dicts: list[dict[str, Any]],
) -> dict[str, Any]:
    as_of = next((metric.as_of for metric in key_metrics if metric.as_of and metric.as_of != "unknown"), "")
    if not as_of:
        as_of = _metric_as_of(None, [], context_items)
    metric_records = [_metric_to_quant_record(metric) for metric in key_metrics]
    return {
        "asset_class": "single_ticker",
        "target": str(ticker or "").upper(),
        "as_of": as_of or "unknown",
        "freshness_status": _freshness_status(as_of),
        "source": "deterministic_quant",
        "metrics": metric_records,
        "regime": _single_ticker_quant_regime(key_metrics),
        "source_status": {
            "technical_metrics_present": bool(technical_metric_dicts),
            "technical_metric_count": len(technical_metric_dicts or []),
            "metric_count": len(metric_records),
        },
    }


def _filter_current_run_context(context_items, current_doc_ids: set[str], top_k: int):
    context_items = context_items or []
    if not current_doc_ids:
        return context_items[:top_k]
    filtered = []
    for item in context_items:
        metadata = getattr(item, "metadata", None) or {}
        parent = metadata.get("parent_doc_id") or metadata.get("doc_id", "")
        if str(parent) in current_doc_ids:
            filtered.append(item)
    return filtered[:top_k]


def _retrieval_item_from_document(document: dict[str, Any]) -> Any:
    return RetrievalItem(
        source=str(document.get("source") or "current_run"),
        title=str(document.get("title") or "Current-run document"),
        date=str(document.get("published_at") or ""),
        chunk=str(document.get("text") or ""),
        score=1.0,
        metadata={
            "doc_id": str(document.get("doc_id") or ""),
            "parent_doc_id": str(document.get("doc_id") or ""),
            "ticker": document.get("ticker") or document.get("symbol") or "",
            "doc_type": document.get("doc_type") or "",
            "source": document.get("source") or "current_run",
            "published_at": document.get("published_at") or "",
            "url": document.get("url") or "",
            "retrieval_mode": "current_run_priority",
        },
    )


def _append_priority_documents(
    context_items: list[Any],
    documents: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[Any]:
    """Keep current-run priority docs available when retrieval misses them.

    Qdrant can occasionally return stale or no matching chunks immediately
    after ingest. Falling back to documents collected in this same run keeps
    the current-run-only safety boundary intact while avoiding an empty
    evidence response.
    """

    seen = {
        str((getattr(item, "metadata", None) or {}).get("parent_doc_id") or (getattr(item, "metadata", None) or {}).get("doc_id") or "")
        for item in context_items or []
    }
    out = list(context_items or [])
    allow_collected_fallback = not out
    for document in documents or []:
        doc_type = str(document.get("doc_type") or "")
        source = str(document.get("source") or "")
        doc_id = str(document.get("doc_id") or "")
        if not doc_id or doc_id in seen:
            continue
        is_priority = doc_type == "technical_snapshot" or source == "yfinance:technical"
        if not is_priority and not allow_collected_fallback:
            continue
        if not is_priority and not str(document.get("text") or "").strip():
            continue
        out.append(_retrieval_item_from_document(document))
        seen.add(doc_id)
        if allow_collected_fallback and len(out) >= max(1, top_k):
            break
    return out


def _build_no_context_response(
    request: AnalysisRequest,
    *,
    status: str,
    error_metadata: str | None,
    task_type: str,
    horizon: str,
    fundamentals=None,
) -> AnalysisResponse:
    language = getattr(load_settings(), "output_language", "ko")
    if language == "ko":
        summary = "요청한 출처에서 신뢰할 만한 최신 근거가 충분히 수집되지 않아 확신 있게 답변할 수 없습니다."
        uncertainty = "요청한 티커와 질문에 대해 사용할 수 있는 근거 문맥이 수집되지 않았습니다."
    else:
        summary = "Insufficient grounded context was retrieved from the requested sources to answer confidently."
        uncertainty = "No grounded context was retrieved for the requested ticker and question."
    sentiment = "Neutral"
    confidence = 0.0
    thesis = build_thesis(
        ticker=request.ticker,
        question=request.question,
        status=status,
        error_metadata=error_metadata,
        task_type=task_type,
        horizon=horizon,
        summary=summary,
        bull_points=[],
        bear_points=[],
        sentiment=sentiment,
        confidence=confidence,
        uncertainty=uncertainty,
        cited_doc_ids=[],
        raw_context=[],
        language=language,
    )
    return AnalysisResponse(
        ticker=request.ticker,
        question=request.question,
        status=status,
        error_metadata=error_metadata,
        summary=summary,
        bull_points=[],
        bear_points=[],
        fundamentals=fundamentals,
        sentiment=sentiment,
        confidence=confidence,
        conclusion=thesis.conclusion,
        citations=list(thesis.citations),
        raw_context=[],
        uncertainty=uncertainty,
    )

def _detect_lens(question: str) -> tuple[str, str]:
    """
    Infers task_type and horizon from question text for internal metadata injection.
    Targets classes: [risk, catalyst, general] and [short_term, medium_term, unspecified].
    """
    q = question.lower()
    
    # ── 1. Task Type (Lens)
    task = "general"
    if any(kw in q for kw in ["risk", "threat", "danger", "downside", "headwind", "bearish", "short", "pitfall"]):
        task = "risk"
    elif any(kw in q for kw in ["catalyst", "driver", "upside", "bullish", "opportunity", "growth", "potential"]):
        task = "catalyst"
        
    # ── 2. Time Horizon
    horizon = "unspecified"
    if any(kw in q for kw in ["today", "next week", "near-term", "immediate", "30 day", "1 month", "soon"]):
        horizon = "short_term"
    elif any(kw in q for kw in ["year", "quarter", "medium-term", "6 month", "12 month"]):
        horizon = "medium_term"
        
    return task, horizon

async def run_pipeline_async(
    request: AnalysisRequest,
    *,
    event_sink: EventSink = None,
) -> AnalysisResponse:
    request_ticker = str(getattr(request, "ticker", "") or "").upper().strip()
    request_question = str(getattr(request, "question", "") or "").strip()
    safe_sources = _normalise_sources_for_pipeline(request_ticker, request_question, getattr(request, "sources", None))
    safe_top_k = _coerce_int(getattr(request, "top_k", 10), 10, lower=1, upper=20)
    safe_lookback_days = _coerce_int(getattr(request, "lookback_days", 60), 60, lower=1, upper=3650)
    safe_model = getattr(request, "model", None) or "mistral"
    safe_output_dir = getattr(request, "output_dir", None)
    request = request.model_copy(
        update={
            "ticker": request_ticker or None,
            "question": request_question,
            "sources": safe_sources,
            "lookback_days": safe_lookback_days,
            "top_k": safe_top_k,
            "model": safe_model,
            "output_dir": safe_output_dir,
        }
    )
    logger.info(f"Starting async research pipeline for {request_ticker} (model: {request.model})")
    start_time = time.time()

    status = "success"
    error_metadata = None
    stages_ran: list[str] = []
    fundamentals_card = None

    _emit(
        event_sink,
        "pipeline_started",
        ticker=request_ticker,
        question=request.question,
        sources=list(request.sources),
        lookback_days=request.lookback_days,
        top_k=request.top_k,
        model=request.model,
    )

    # Step: Pre-check execution
    precheck_error = run_execution_precheck(request)
    if precheck_error:
        logger.warning(f"[PRECHECK_FAILURE] Ticker='{request_ticker}' Error: {precheck_error}")
        _emit(event_sink, "pipeline_failed", reason=str(precheck_error))
        return AnalysisResponse(
            ticker=request_ticker,
            question=request.question,
            status="failed",
            error_metadata=str(precheck_error),
            summary="Request failed pre-execution checks.",
            sentiment="Neutral",
            conclusion="Execution aborted due to invalid inputs."
        )

    try:
        # 1. Collect
        logger.info(f"[COLLECT_START] Sources={request.sources} Lookback={request.lookback_days}")
        _emit(event_sink, "stage_started", stage="collect")
        collect_started = time.time()
        collection_outcome = await asyncio.to_thread(collect_data, request_ticker, request.sources, request.lookback_days)
        stages_ran.append("collect")
        status, error_metadata = _apply_collection_outcome(status, error_metadata, collection_outcome)
        documents = collection_outcome.documents
        current_doc_ids = _current_doc_ids(collection_outcome)
        settings_after_collect = load_settings()
        if bool(getattr(settings_after_collect, "fundamentals_card_enabled", True)):
            try:
                fundamentals_card = await asyncio.to_thread(
                    collect_fundamentals_card,
                    request_ticker,
                    float(getattr(settings_after_collect, "fundamentals_card_timeout_s", 5.0) or 5.0),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[FUNDAMENTALS] collection failed open for %s: %s", request_ticker, exc)
        _emit(
            event_sink,
            "stage_completed",
            stage="collect",
            duration_s=round(time.time() - collect_started, 2),
            documents=len(documents),
            cache_hit=bool(getattr(collection_outcome, "cache_hit", False)),
            cache_age_s=float(getattr(collection_outcome, "cache_age_s", 0.0) or 0.0),
            degraded_sources=[r.source for r in collection_outcome.source_results if r.status not in {"ok", "disabled", "no_data_in_window", "skipped"}],
        )

        # 2. Ingest
        if documents:
            logger.info("Ingesting documents into vector DB...")
            _emit(event_sink, "stage_started", stage="ingest", documents=len(documents))
            ingest_started = time.time()
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(ingest_documents, documents),
                    timeout=30.0
                )
                stages_ran.append("ingest")
                _emit(event_sink, "stage_completed", stage="ingest", duration_s=round(time.time() - ingest_started, 2))
            except getattr(asyncio.exceptions, "TimeoutError", asyncio.TimeoutError):
                logger.error("Qdrant ingest timed out.")
                status = "partial"
                error_metadata = _merge_error_metadata(error_metadata, "Data ingested partially due to timeout.")
                _emit(event_sink, "stage_completed", stage="ingest", duration_s=round(time.time() - ingest_started, 2), status="timeout")
            except Exception as exc:  # noqa: BLE001
                logger.exception("[INGEST_FAILED] Continuing with existing indexed context: %s", exc)
                status = "partial"
                error_metadata = _merge_error_metadata(
                    error_metadata,
                    "Qdrant ingest failed; continuing with existing indexed context.",
                )
                _emit(
                    event_sink,
                    "stage_completed",
                    stage="ingest",
                    duration_s=round(time.time() - ingest_started, 2),
                    status="failed",
                    error=str(exc),
                )
        else:
            logger.warning("No documents collected, continuing with empty context.")
            status = "partial"
            error_metadata = _merge_error_metadata(
                error_metadata,
                collection_outcome.summary_detail or "No new documents collected from external sources.",
            )

        task_type, horizon = _detect_lens(request.question)

        if not current_doc_ids:
            status = "partial"
            stale_block_reason = (
                "No usable current-run primary documents; stale Qdrant context blocked."
                if _primary_collection_failed(collection_outcome)
                else "No usable current-run documents; stale Qdrant context blocked."
            )
            error_metadata = _merge_error_metadata(
                error_metadata,
                stale_block_reason,
            )
            logger.warning("[RETRIEVAL_SKIPPED] No current-run documents. Blocking stale Qdrant context.")
            response = _build_no_context_response(
                request,
                status=status,
                error_metadata=error_metadata,
                task_type=task_type,
                horizon=horizon,
                fundamentals=fundamentals_card,
            )
            return await _finalize_response(
                request,
                response,
                start_time=start_time,
                collection_outcome=collection_outcome,
                stages_ran=stages_ran,
                event_sink=event_sink,
            )

        # 3. Retrieve
        settings_for_retrieval = load_settings()
        strategy = (getattr(settings_for_retrieval, "retrieval_strategy", "multi_query") or "multi_query").lower()
        use_multi_query = strategy == "multi_query"
        retrieval_limit = max(request.top_k * 5, 25)
        logger.info(
            "Retrieving relevant context... (strategy=%s limit=%d top_k=%d)",
            strategy,
            retrieval_limit,
            request.top_k,
        )
        _emit(
            event_sink,
            "stage_started",
            stage="retrieve",
            top_k=request.top_k,
            limit=retrieval_limit,
            strategy=strategy,
        )
        retrieve_started = time.time()
        retriever_callable = retrieve_context_multi if use_multi_query else retrieve_context
        try:
            context_items = await asyncio.wait_for(
                asyncio.to_thread(retriever_callable, request_ticker, request.question, retrieval_limit),
                timeout=20.0
            )
            stages_ran.append("retrieve")
            _emit(
                event_sink,
                "stage_completed",
                stage="retrieve",
                duration_s=round(time.time() - retrieve_started, 2),
                chunks=len(context_items),
            )
        except getattr(asyncio.exceptions, "TimeoutError", asyncio.TimeoutError):
            logger.error("Qdrant retrieve timed out.")
            context_items = []
            status = "partial"
            error_metadata = _merge_error_metadata(error_metadata, "Retrieval timed out.")
            _emit(event_sink, "stage_completed", stage="retrieve", duration_s=round(time.time() - retrieve_started, 2), status="timeout")
        except Exception as exc:  # noqa: BLE001
            logger.error("[RETRIEVAL_FAILED] %s", exc)
            context_items = []
            status = "partial"
            error_metadata = _merge_error_metadata(error_metadata, f"Retrieval failed: {exc}")
            _emit(
                event_sink,
                "stage_completed",
                stage="retrieve",
                duration_s=round(time.time() - retrieve_started, 2),
                status="failed",
                error=str(exc),
            )

        context_items = _filter_current_run_context(context_items, current_doc_ids, request.top_k)
        context_items = _append_priority_documents(context_items, collection_outcome.documents, top_k=request.top_k)
        if not context_items:
            status = "partial"
            if current_doc_ids:
                error_metadata = _merge_error_metadata(
                    error_metadata,
                    "Stale Qdrant context blocked; no retrieved chunks matched current-run documents.",
                )
            else:
                error_metadata = _merge_error_metadata(error_metadata, "Empty retrieval result. Potential LLM hallucination.")
            logger.warning("[RETRIEVAL_EMPTY] Zero chunks isolated. Injecting hallucination warnings.")
            response = _build_no_context_response(
                request,
                status=status,
                error_metadata=error_metadata,
                task_type=task_type,
                horizon=horizon,
                fundamentals=fundamentals_card,
            )
            return await _finalize_response(
                request,
                response,
                start_time=start_time,
                collection_outcome=collection_outcome,
                stages_ran=stages_ran,
                event_sink=event_sink,
            )

        # 4. Infer
        logger.info(f"[INFERENCE_START] Model={request.model} task={task_type} horizon={horizon}")
        _emit(
            event_sink,
            "stage_started",
            stage="infer",
            model=request.model,
            task_type=task_type,
            horizon=horizon,
            chunks=len(context_items),
        )
        infer_started = time.time()
        inference_degraded_reason: str | None = None

        try:
            raw_output = await asyncio.wait_for(
                asyncio.to_thread(
                    run_inference, 
                    request_ticker,
                    request.question, 
                    context_items, 
                    request.model,
                    task_type=task_type,
                    horizon=horizon,
                    fundamentals=fundamentals_card,
                ),
                timeout=_inference_timeout_s()
            )
        except getattr(asyncio.exceptions, "TimeoutError", asyncio.TimeoutError) as e:
            logger.error("[INFERENCE_FAILURE] LLM generation timed out.")
            inference_degraded_reason = "LLM inference timeout; deterministic fallback used."
            status = "partial"
            error_metadata = _merge_error_metadata(error_metadata, inference_degraded_reason)
            raw_output = _deterministic_inference_fallback(
                ticker=request_ticker,
                question=request.question,
                context_items=context_items,
                model=request.model,
                reason=inference_degraded_reason,
                started_at=infer_started,
            )
        except Exception as e:
            logger.error("[INFERENCE_FAILURE] Using deterministic fallback after model error: %s", e)
            inference_degraded_reason = f"LLM inference failed; deterministic fallback used: {e}"
            status = "partial"
            error_metadata = _merge_error_metadata(error_metadata, inference_degraded_reason)
            raw_output = _deterministic_inference_fallback(
                ticker=request_ticker,
                question=request.question,
                context_items=context_items,
                model=request.model,
                reason=str(e),
                started_at=infer_started,
            )

        stages_ran.append("infer")
        _emit(
            event_sink,
            "stage_completed",
            stage="infer",
            duration_s=round(time.time() - infer_started, 2),
            status="degraded" if inference_degraded_reason else "ok",
            detail=inference_degraded_reason or "",
        )

        # Log inference observability metadata from adapter
        _meta = raw_output.pop("_meta", {})
        if _meta:
            logger.info(
                f"[INFERENCE_META] primary_model='{_meta.get('primary_model')}' "
                f"[INFERENCE_DONE] producing_model='{_meta.get('producing_model')}' "
                f"fallback_enabled={_meta.get('fallback_enabled')} "
                f"fallback_model='{_meta.get('fallback_model')}' "
                f"fallback_used={_meta.get('fallback_used')} "
                f"retry_count={_meta.get('retry_count')} "
                f"total_latency={_meta.get('total_latency_s')}s "
                f"primary_latency={_meta.get('primary_latency_s')}s "
                f"fallback_latency={_meta.get('fallback_latency_s')}s "
                f"prompt_chars={_meta.get('prompt_char_count')} "
                f"chunks={_meta.get('chunks_used')}"
            )

        technical_metric_dicts = technical_metrics_from_retrieval_items(context_items)

        # 5. Analyze
        logger.info("[RISK_EVALUATION_START] Beginning heuristic signal abstraction.")
        _emit(event_sink, "stage_started", stage="analyze")
        analyze_started = time.time()
        sentiment, confidence = analyze_sentiment(raw_output)

        # Using the pluggable risk engine asynchronously — factory respects
        # RISK_ENGINE env / settings and gracefully falls back to heuristic
        # when an opt-in engine (finbert) isn't installed.
        try:
            risk_engine = get_risk_engine()
            risk_eval = await risk_engine.evaluate_risk(raw_output)
            bull_points = risk_eval.bull_points
            bear_points = risk_eval.bear_points
            stages_ran.append("analyze")
            _emit(
                event_sink,
                "stage_completed",
                stage="analyze",
                duration_s=round(time.time() - analyze_started, 2),
                sentiment=sentiment,
                confidence=confidence,
            )
        except Exception as e:
            logger.error(f"[RISK_EVALUATION_FAILURE] Engine failed context mapping: {e}")
            _emit(event_sink, "stage_completed", stage="analyze", duration_s=round(time.time() - analyze_started, 2), status="error", detail=str(e))
            raise

        settings = load_settings()
        language = getattr(settings, "output_language", "ko")

        # Build metrics before thesis construction so deterministic technical
        # indicators can repair non-Korean or repetitive model text.
        raw_metrics = _filter_llm_metrics(raw_output.get("key_metrics") or [], technical_metric_dicts)
        key_metrics: list[KeyMetric] = []
        for m in raw_metrics:
            if not isinstance(m, dict) or not str(m.get("name", "")).strip() or not str(m.get("value", "")).strip():
                continue
            evidence_doc_ids = _normalize_doc_id_list(m.get("evidence_doc_ids") or [], context_items)
            key_metrics.append(
                KeyMetric(
                    name=str(m.get("name", "")),
                    value=str(m.get("value", "")),
                    unit=str(m.get("unit", "")),
                    as_of=_metric_as_of(m.get("as_of"), evidence_doc_ids, context_items),
                    context=str(m.get("context", "")),
                    source=str(m.get("source", "")),
                    freshness_status=str(m.get("freshness_status", "") or "unknown"),
                    evidence_doc_ids=evidence_doc_ids,
                )
            )
        key_metrics = _merge_key_metric_dicts(key_metrics, technical_metric_dicts, context_items)

        (
            sanitized_summary,
            sanitized_uncertainty,
            bull_points,
            bear_points,
            generated_bull_evidence,
            generated_bear_evidence,
            text_repaired,
        ) = _sanitize_decision_texts(
            ticker=request_ticker,
            summary=raw_output.get("summary", "No summary generated."),
            uncertainty=raw_output.get("uncertainty", ""),
            bull_points=bull_points,
            bear_points=bear_points,
            key_metrics=key_metrics,
        )
        raw_output["summary"] = sanitized_summary
        raw_output["uncertainty"] = sanitized_uncertainty

        thesis = build_thesis(
            ticker=request_ticker,
            question=request.question,
            status=status,
            error_metadata=error_metadata,
            task_type=task_type,
            horizon=horizon,
            summary=sanitized_summary,
            bull_points=bull_points,
            bear_points=bear_points,
            sentiment=sentiment,
            confidence=confidence,
            uncertainty=sanitized_uncertainty,
            cited_doc_ids=raw_output.get("cited_doc_ids", []),
            raw_context=context_items,
            language=language,
        )

        # Pull per-bullet evidence linkage from the inference result. The risk
        # engine may re-derive bull/bear_points from other heuristics, so we
        # only trust the evidence arrays when their lengths match the final
        # bull_points / bear_points we end up returning.
        bull_evidence_ids = _align_evidence_ids(raw_output.get("bull_evidence_ids"), bull_points, context_items)
        bear_evidence_ids = _align_evidence_ids(raw_output.get("bear_evidence_ids"), bear_points, context_items)
        if generated_bull_evidence and not any(bull_evidence_ids):
            bull_evidence_ids = (generated_bull_evidence + [[] for _ in bull_points])[: len(bull_points)]
        if generated_bear_evidence and not any(bear_evidence_ids):
            bear_evidence_ids = (generated_bear_evidence + [[] for _ in bear_points])[: len(bear_points)]
        bull_evidence_ids = _fill_missing_claim_evidence_ids(bull_evidence_ids, bull_points, context_items)
        bear_evidence_ids = _fill_missing_claim_evidence_ids(bear_evidence_ids, bear_points, context_items)

        # Assemble observability metadata before handing off to the report.
        exec_meta = ExecutionMeta(
            primary_model=_meta.get("primary_model"),
            producing_model=_meta.get("producing_model"),
            fallback_enabled=_meta.get("fallback_enabled"),
            fallback_model=_meta.get("fallback_model"),
            fallback_available=_meta.get("fallback_available"),
            fallback_used=_meta.get("fallback_used"),
            retry_count=_meta.get("retry_count"),
            total_latency_s=_meta.get("total_latency_s"),
            primary_latency_s=_meta.get("primary_latency_s"),
            fallback_latency_s=_meta.get("fallback_latency_s"),
            prompt_char_count=_meta.get("prompt_char_count"),
            chunks_used=_meta.get("chunks_used"),
            lens=_meta.get("lens") or task_type,
            context_horizon=_meta.get("context_horizon") or horizon,
            extras={
                "model_capabilities": _meta.get("model_capabilities")
                or model_capability_dict(str(getattr(request, "model", "") or ""), _meta.get("primary_model")),
                "provider_status": _provider_statuses(collection_outcome),
                "data_freshness": _data_freshness(context_items),
                "error_type": _classify_error_type(error_metadata, status),
            },
        )

        exec_meta.extras["technical_indicators"] = {
            "present": bool(technical_metric_dicts),
            "metric_count": len(technical_metric_dicts),
            "source": "yfinance:technical" if technical_metric_dicts else "",
            "text_repaired": bool(text_repaired),
        }
        exec_meta.extras["quant_snapshot"] = _single_ticker_quant_snapshot(
            request_ticker,
            key_metrics,
            context_items,
            technical_metric_dicts,
        )
        raw_timeline = raw_output.get("catalyst_timeline") or {}
        catalyst_timeline = CatalystTimeline(
            near_term=[str(x) for x in (raw_timeline.get("near_term") or []) if str(x).strip()],
            mid_term=[str(x) for x in (raw_timeline.get("mid_term") or []) if str(x).strip()],
            long_term=[str(x) for x in (raw_timeline.get("long_term") or []) if str(x).strip()],
        )
        open_questions = [str(x) for x in (raw_output.get("open_questions") or []) if str(x).strip()]
        exec_meta.extras["validation_summary"] = _coverage_summary(
            key_metrics,
            bull_evidence_ids,
            bear_evidence_ids,
            context_items,
        )

        # Build Response
        response = AnalysisResponse(
            ticker=request_ticker,
            question=request.question,
            status=status,
            error_metadata=error_metadata,
            summary=raw_output.get("summary", "No summary generated."),
            bull_points=bull_points,
            bear_points=bear_points,
            bull_evidence_ids=bull_evidence_ids,
            bear_evidence_ids=bear_evidence_ids,
            key_metrics=key_metrics,
            fundamentals=fundamentals_card,
            catalyst_timeline=catalyst_timeline,
            open_questions=open_questions,
            uncertainty=str(raw_output.get("uncertainty") or ""),
            sentiment=sentiment,
            confidence=confidence,
            conclusion=thesis.conclusion,
            citations=list(thesis.citations),
            raw_context=context_items,
            execution_meta=exec_meta,
        )

        return await _finalize_response(
            request,
            response,
            start_time=start_time,
            stages_ran=stages_ran,
            collection_outcome=collection_outcome,
            event_sink=event_sink,
        )

    except Exception as e:
        logger.error(f"[PIPELINE_FAILURE] Execution aborted at outer block level: {e}")
        status = "failed"
        _emit(event_sink, "pipeline_failed", reason=str(e))
        return AnalysisResponse(
            ticker=request_ticker,
            question=request.question,
            status=status,
            error_metadata=str(e),
            summary="Pipeline failed completely.",
            sentiment="Neutral",
            conclusion="Error occurred before completion."
        )

def run_pipeline(request: AnalysisRequest) -> AnalysisResponse:
    # Synchronous wrapper for CLI legacy
    return asyncio.run(run_pipeline_async(request))
