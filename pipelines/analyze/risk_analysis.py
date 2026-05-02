from typing import Dict, Any, List
import asyncio
import re
from core.interfaces.risk import BaseRiskEngine, RiskEvaluationResult


_SENTENCE_SPLIT_RE = re.compile(r"(?:[.!?。！？]|다\.)\s+")
_BULL_HINTS = (
    "상승",
    "강세",
    "긍정",
    "성장",
    "개선",
    "확대",
    "수익화",
    "경쟁력",
    "기회",
    "촉매",
    "매력",
    "ai",
    "cloud",
    "growth",
    "positive",
    "upside",
    "strong",
    "catalyst",
    "opportunity",
)
_BEAR_HINTS = (
    "하락",
    "약세",
    "부정",
    "리스크",
    "위험",
    "압박",
    "둔화",
    "불확실",
    "위협",
    "경쟁",
    "마진",
    "risk",
    "headwind",
    "negative",
    "downside",
    "pressure",
    "uncertain",
    "competition",
)


def _clean_points(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


def _candidate_sentences(raw_output: dict, *, hints: tuple[str, ...]) -> list[str]:
    candidates: list[str] = []
    for field in ("summary", "uncertainty"):
        value = raw_output.get(field)
        if not isinstance(value, str):
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(value):
            text = " ".join(sentence.split()).strip()
            if len(text) < 18:
                continue
            lower = text.lower()
            if any(hint in lower for hint in hints):
                candidates.append(text)

    timeline = raw_output.get("catalyst_timeline") or {}
    if isinstance(timeline, dict) and hints is _BULL_HINTS:
        for bucket in ("near_term", "mid_term", "long_term"):
            for item in timeline.get(bucket) or []:
                text = " ".join(str(item or "").split()).strip()
                if text:
                    candidates.append(text)

    for metric in raw_output.get("key_metrics") or []:
        if not isinstance(metric, dict):
            continue
        context = " ".join(str(metric.get("context") or "").split()).strip()
        name = " ".join(str(metric.get("name") or "").split()).strip()
        value = " ".join(str(metric.get("value") or "").split()).strip()
        if context and any(hint in context.lower() for hint in hints):
            candidates.append(f"{name} {value}: {context}".strip())
    return candidates


def _append_until(points: list[str], candidates: list[str], *, prefix: str, minimum: int) -> list[str]:
    seen = {point.lower() for point in points}
    for candidate in candidates:
        text = candidate
        if prefix and not candidate.startswith(prefix):
            text = f"{prefix}: {candidate}"
        normalized = text.lower()
        if normalized in seen:
            continue
        points.append(text)
        seen.add(normalized)
        if len(points) >= minimum:
            break
    return points

class HeuristicRiskEngine(BaseRiskEngine):
    """
    V1 Risk Engine.
    Uses simple string heuristics to separate lists inside raw_output into bull vs bear.
    This logic wraps fundamentally synchronous data transformations,
    but honors the async BaseRiskEngine contract perfectly.
    """
    
    async def evaluate_risk(self, raw_output: dict) -> RiskEvaluationResult:
        # ── 1. Priority: Model-provided structured points
        bull_points = _clean_points(raw_output.get("bull_points", []))
        bear_points = _clean_points(raw_output.get("bear_points", []))
        
        # ── 2. Secondary: If empty, try to extract from legacy/heuristic risk_flags
        if not bull_points and not bear_points:
            risk_flags = raw_output.get("risk_flags", [])
            if isinstance(risk_flags, list):
                for flag in risk_flags:
                    f_lower = str(flag).lower()
                    if any(kw in f_lower for kw in ["growth", "opportunity", "positive", "bull", "upside", "catalyst"]):
                        bull_points.append(flag)
                    else:
                        bear_points.append(flag)

        if bull_points and len(bull_points) < 2:
            _append_until(
                bull_points,
                _candidate_sentences(raw_output, hints=_BULL_HINTS),
                prefix="보조 상방 논점",
                minimum=2,
            )
        if bear_points and len(bear_points) < 2:
            _append_until(
                bear_points,
                _candidate_sentences(raw_output, hints=_BEAR_HINTS),
                prefix="보조 하방 리스크",
                minimum=2,
            )

        # ── 3. Final Fallback: Ensure types are clean
        return RiskEvaluationResult(
            bull_points=[str(p) for p in bull_points],
            bear_points=[str(p) for p in bear_points]
        )
