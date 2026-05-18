from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from core.schemas.response import EvidenceQuality


SOURCE_RELIABILITY: dict[str, float] = {
    "sec_filing": 0.95,
    "fred": 0.95,
    "provider_data": 0.90,
    "earnings_transcript": 0.90,
    "official_ir": 0.85,
    "reputable_news": 0.75,
    "yahoo_news": 0.65,
    "rss_news": 0.55,
    "unknown": 0.30,
}

_REPUTABLE_NEWS = (
    "bloomberg",
    "cnbc",
    "reuters",
    "wall street journal",
    "wsj",
    "financial times",
    "ft.com",
    "nytimes",
    "new york times",
    "marketwatch",
    "barron",
)


def _get(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        if key in item:
            return item.get(key, default)
        metadata = item.get("metadata") or {}
        return metadata.get(key, default) if isinstance(metadata, dict) else default
    value = getattr(item, key, default)
    if value not in (None, ""):
        return value
    metadata = getattr(item, "metadata", None) or {}
    return metadata.get(key, default) if isinstance(metadata, dict) else default


def _metadata(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        metadata = item.get("metadata") or {}
    else:
        metadata = getattr(item, "metadata", None) or {}
    return metadata if isinstance(metadata, dict) else {}


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text or text.lower() in {"unknown", "n/a", "none"}:
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized[:10]):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", text)
    if match:
        y, m, d = (int(x) for x in match.groups())
        return datetime(y, m, d, tzinfo=timezone.utc)
    return None


def infer_source_type(item: Any) -> str:
    raw = " ".join(
        str(_get(item, key, ""))
        for key in ("source_type", "source", "provider", "url", "title")
    ).lower()
    if "sec" in raw or "10-k" in raw or "10-q" in raw or "8-k" in raw:
        return "sec_filing"
    if "fred" in raw:
        return "fred"
    if "transcript" in raw or "earnings call" in raw:
        return "earnings_transcript"
    if "investor relations" in raw or "ir." in raw or "official" in raw:
        return "official_ir"
    if "yfinance" in raw or "yahoo price" in raw or "openbb" in raw or "provider" in raw:
        return "provider_data"
    if "yahoo" in raw:
        return "yahoo_news"
    if any(name in raw for name in _REPUTABLE_NEWS):
        return "reputable_news"
    if "rss" in raw or "google news" in raw or "news" in raw:
        return "rss_news"
    return "unknown"


def freshness_score(item: Any, *, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    date = _parse_date(_get(item, "date") or _get(item, "published_at") or _get(item, "as_of") or _get(item, "collected_at"))
    if date is None:
        return 0.25
    age_days = max(0, (now - date.astimezone(timezone.utc)).days)
    source_type = infer_source_type(item)
    if age_days <= 7:
        return 0.95
    if age_days <= 30:
        return 0.80
    if age_days <= 90:
        return 0.60
    if age_days <= 365:
        return 0.35 if source_type not in {"sec_filing", "official_ir"} else 0.55
    return 0.15 if source_type not in {"sec_filing", "official_ir"} else 0.40


def specificity_score(item: Any, *, ticker: str = "", question: str = "") -> float:
    ticker = str(ticker or "").upper().strip()
    text = " ".join(str(_get(item, key, "")) for key in ("title", "chunk", "source", "url")).lower()
    question_terms = [term.lower() for term in re.findall(r"[A-Za-z가-힣]{3,}", str(question or ""))[:10]]
    has_ticker = bool(ticker and ticker.lower() in text)
    has_date = bool(re.search(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}", text))
    has_metric = bool(re.search(r"\d+(?:\.\d+)?\s*(%|bp|bps|x|달러|usd|billion|million|yield|margin|revenue|eps)", text))
    overlaps = sum(1 for term in question_terms if term in text)
    if has_ticker and has_metric and (has_date or overlaps >= 2):
        return 0.95
    if has_ticker and (has_metric or overlaps >= 2):
        return 0.80
    if has_ticker or overlaps >= 2:
        return 0.60
    if overlaps == 1:
        return 0.45
    return 0.30


def fingpt_annotation_quality_bonus(metadata: dict) -> float:
    annotations = metadata.get("fingpt_annotations") or []
    if not isinstance(annotations, list):
        return 0.0
    high_confidence = []
    for ann in annotations:
        if not isinstance(ann, dict):
            continue
        try:
            confidence = float(ann.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
        if confidence >= 0.75:
            high_confidence.append(ann)
    return min(0.1, 0.025 * len(high_confidence))


def score_evidence_item(item: Any, *, ticker: str = "", question: str = "", now: datetime | None = None) -> EvidenceQuality:
    source_type = infer_source_type(item)
    reliability = SOURCE_RELIABILITY.get(source_type, SOURCE_RELIABILITY["unknown"])
    freshness = freshness_score(item, now=now)
    specificity = specificity_score(item, ticker=ticker, question=question)
    annotation_bonus = fingpt_annotation_quality_bonus(_metadata(item))
    overall = round(min(1.0, (reliability * 0.45) + (freshness * 0.30) + (specificity * 0.25) + annotation_bonus), 4)
    rationale = (
        f"source_type={source_type}; reliability={reliability:.2f}; "
        f"freshness={freshness:.2f}; specificity={specificity:.2f}; "
        f"fingpt_annotation_bonus={annotation_bonus:.3f}"
    )
    return EvidenceQuality(
        source_type=source_type,
        reliability_score=round(reliability, 4),
        freshness_score=round(freshness, 4),
        specificity_score=round(specificity, 4),
        overall_score=overall,
        quality_rationale=rationale,
    )


def evidence_doc_id(item: Any, fallback: str) -> str:
    doc_id = _get(item, "doc_id") or _get(item, "parent_doc_id") or _get(item, "id")
    return str(doc_id or fallback)


def score_evidence_items(items: Iterable[Any], *, ticker: str = "", question: str = "") -> dict[str, EvidenceQuality]:
    scored: dict[str, EvidenceQuality] = {}
    for index, item in enumerate(items or []):
        doc_id = evidence_doc_id(item, f"doc_{index + 1}")
        scored[doc_id] = score_evidence_item(item, ticker=ticker, question=question)
    return scored


def average_evidence_quality(scored: dict[str, EvidenceQuality]) -> float:
    values = [item.overall_score for item in scored.values()]
    return round(sum(values) / len(values), 4) if values else 0.0


def freshness_coverage(scored: dict[str, EvidenceQuality], threshold: float = 0.60) -> float:
    values = list(scored.values())
    if not values:
        return 0.0
    fresh = sum(1 for item in values if item.freshness_score >= threshold)
    return round(fresh / len(values), 4)


def source_diversity(scored: dict[str, EvidenceQuality]) -> int:
    return len({item.source_type for item in scored.values() if item.source_type})
