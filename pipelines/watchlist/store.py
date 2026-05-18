"""Watchlist persistence layer.

Design goals
------------
- **Keep it local.** Store the watchlist as a single JSON file under
  ``data/watchlist.json``. No database, no cloud — matches the project's
  "single-workstation, privacy-preserving" stance.
- **Atomic writes.** Write to ``watchlist.json.tmp`` then rename; avoids
  half-written files if the process dies mid-save.
- **Thread-safe.** One RLock guards all reads and writes so the scheduler loop
  and the FastAPI request handlers can share state safely.
- **Schema-tolerant reads.** Older installs may have watchlists missing new
  optional fields — ``_normalize`` fills them in so the server never crashes on
  an old file.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from core.config.settings import load_settings
from core.utils.logger import get_logger

logger = get_logger("pipelines.watchlist")

_WATCHLIST_FILENAME = "watchlist.json"
_DEFAULT_SOURCES = ["news", "transcript"]
_MAX_ITEMS = 32  # Sanity cap to protect local Ollama/FMP from runaway schedules.


@dataclass
class WatchlistItem:
    """One saved monitoring intent. Optional ``interval_hours`` enables
    scheduled auto-runs. ``enabled=False`` temporarily pauses an item without
    deleting it."""
    id: str
    ticker: str
    question: str
    sources: list[str] = field(default_factory=lambda: list(_DEFAULT_SOURCES))
    lookback_days: int = 30
    top_k: int = 5
    model: str = "mistral"
    interval_hours: float | None = None
    enabled: bool = True
    notes: str | None = None
    created_at: str = ""
    last_run_at: str | None = None
    last_run_status: str | None = None
    last_run_error: str | None = None
    last_run_id: str | None = None
    run_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_lock = threading.RLock()


def _watchlist_path() -> Path:
    return load_settings().data_dir / _WATCHLIST_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize(raw: dict[str, Any]) -> WatchlistItem:
    # Tolerate missing optional fields from older watchlist.json writes so a
    # schema bump never bricks a long-running install.
    return WatchlistItem(
        id=str(raw.get("id") or uuid.uuid4().hex),
        ticker=str(raw.get("ticker", "")).upper().strip(),
        question=str(raw.get("question", "")).strip(),
        sources=list(raw.get("sources") or _DEFAULT_SOURCES),
        lookback_days=int(raw.get("lookback_days") or 30),
        top_k=int(raw.get("top_k") or 5),
        model=str(raw.get("model") or "mistral"),
        interval_hours=(float(raw["interval_hours"]) if raw.get("interval_hours") not in (None, "") else None),
        enabled=bool(raw.get("enabled", True)),
        notes=raw.get("notes") or None,
        created_at=str(raw.get("created_at") or _now_iso()),
        last_run_at=raw.get("last_run_at") or None,
        last_run_status=raw.get("last_run_status") or None,
        last_run_error=raw.get("last_run_error") or None,
        last_run_id=raw.get("last_run_id") or None,
        run_count=int(raw.get("run_count") or 0),
    )


def _read_all() -> list[WatchlistItem]:
    path = _watchlist_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("[WATCHLIST] corrupt %s: %s — ignoring", path, exc)
        return []
    items = raw.get("items", []) if isinstance(raw, dict) else (raw or [])
    return [_normalize(x) for x in items if isinstance(x, dict)]


def _write_all(items: Iterable[WatchlistItem]) -> None:
    path = _watchlist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "saved_at": _now_iso(), "items": [it.to_dict() for it in items]}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def list_items() -> list[WatchlistItem]:
    with _lock:
        return list(_read_all())


def get_item(item_id: str) -> WatchlistItem | None:
    with _lock:
        for it in _read_all():
            if it.id == item_id:
                return it
        return None


def upsert_item(payload: dict[str, Any], *, item_id: str | None = None) -> WatchlistItem:
    """Create or update a watchlist entry. Raises ValueError on invalid payload."""
    ticker = str(payload.get("ticker", "")).upper().strip()
    question = str(payload.get("question", "")).strip()
    if not ticker:
        raise ValueError("ticker is required")
    if not question:
        raise ValueError("question is required")

    with _lock:
        items = _read_all()

        if item_id:
            # Update path: preserve created_at, run history, etc.
            for idx, existing in enumerate(items):
                if existing.id == item_id:
                    merged = _normalize(
                        {
                            **existing.to_dict(),
                            **payload,
                            "id": existing.id,
                            "created_at": existing.created_at,
                        }
                    )
                    items[idx] = merged
                    _write_all(items)
                    return merged
            raise KeyError(f"watchlist item not found: {item_id}")

        if len(items) >= _MAX_ITEMS:
            raise ValueError(f"watchlist is full (max {_MAX_ITEMS} items)")

        # Prevent duplicate (ticker, question) rows — surprising UX otherwise.
        for existing in items:
            if existing.ticker == ticker and existing.question == question:
                merged = _normalize({**existing.to_dict(), **payload, "id": existing.id})
                items = [merged if i.id == existing.id else i for i in items]
                _write_all(items)
                return merged

        new_item = _normalize({**payload, "id": uuid.uuid4().hex, "created_at": _now_iso()})
        items.append(new_item)
        _write_all(items)
        return new_item


def delete_item(item_id: str) -> bool:
    with _lock:
        items = _read_all()
        remaining = [it for it in items if it.id != item_id]
        if len(remaining) == len(items):
            return False
        _write_all(remaining)
        return True


def mark_run(
    item_id: str,
    *,
    status: str,
    error: str | None = None,
    run_id: str | None = None,
) -> WatchlistItem | None:
    """Stamp the last-run metadata for an item. Called by the scheduler and
    the ``/run`` endpoint after each execution so the UI can show freshness."""
    with _lock:
        items = _read_all()
        for idx, existing in enumerate(items):
            if existing.id == item_id:
                updated = WatchlistItem(**{
                    **existing.to_dict(),
                    "last_run_at": _now_iso(),
                    "last_run_status": status,
                    "last_run_error": error,
                    "last_run_id": run_id,
                    "run_count": int(existing.run_count or 0) + 1,
                })
                items[idx] = updated
                _write_all(items)
                return updated
        return None


def due_items(reference_ts: float | None = None) -> list[WatchlistItem]:
    """Return items whose schedule has elapsed and that are enabled."""
    if reference_ts is None:
        reference_ts = time.time()
    due: list[WatchlistItem] = []
    with _lock:
        for it in _read_all():
            if not it.enabled or not it.interval_hours:
                continue
            if not it.last_run_at:
                due.append(it)
                continue
            try:
                last = datetime.fromisoformat(it.last_run_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                due.append(it)
                continue
            if reference_ts - last >= it.interval_hours * 3600:
                due.append(it)
    return due
