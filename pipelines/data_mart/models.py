from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class PriceBar:
    ticker: str
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adjusted_close: float | None = None
    volume: float | None = None
    source: str = "unknown"
    asset_id: str | None = None
    collected_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class MacroObservation:
    series_id: str
    date: str
    value: float | None
    source: str = "fred"
    title: str = ""
    units: str = ""
    frequency: str = ""
    collected_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class NewsArticle:
    ticker: str
    title: str
    url: str = ""
    source: str = "unknown"
    published_at: str = ""
    summary: str = ""
    collected_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class ProviderFetchResult:
    provider: str
    status: str
    rows: int = 0
    records: list[Any] = field(default_factory=list)
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class UpdateRunResult:
    run_id: str
    status: str
    market: str
    provider: str
    rows_inserted: int = 0
    rows_updated: int = 0
    error_message: str | None = None
    providers: list[ProviderFetchResult] = field(default_factory=list)
