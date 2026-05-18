from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Iterable


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_hash(payload: Any, *, length: int = 16) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def mean(values: Iterable[Any]) -> float | None:
    clean = [float(value) for value in values if finite_float(value) is not None]
    return sum(clean) / len(clean) if clean else None


def stdev(values: Iterable[Any], *, sample: bool = True) -> float:
    clean = [float(value) for value in values if finite_float(value) is not None]
    if len(clean) < 2:
        return 0.0
    avg = sum(clean) / len(clean)
    denominator = len(clean) - 1 if sample and len(clean) > 1 else len(clean)
    return math.sqrt(sum((value - avg) ** 2 for value in clean) / max(denominator, 1))


def percentile(values: Iterable[Any], q: float) -> float | None:
    clean = sorted(float(value) for value in values if finite_float(value) is not None)
    if not clean:
        return None
    q = max(0.0, min(1.0, float(q)))
    pos = q * (len(clean) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return clean[lo]
    weight = pos - lo
    return clean[lo] * (1.0 - weight) + clean[hi] * weight


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def clean_ticker(value: Any, default: str = "SPY") -> str:
    ticker = str(value or default).upper().strip()
    return ticker or default


def price_from_row(row: dict[str, Any], *, adjusted: bool = True) -> float | None:
    value = row.get("adjusted_close") if adjusted else None
    if value is None:
        value = row.get("close")
    return finite_float(value)
