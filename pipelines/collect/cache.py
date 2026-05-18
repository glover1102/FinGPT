"""
Small, process-local TTL cache for ``collect_data`` results.

Purpose
-------
The collect stage hits external APIs (FMP, SEC EDGAR, Yahoo Finance) that are
rate-limited and often identical across back-to-back user runs (e.g. retrying
the same ticker with a different question, or the SSE stream re-running a cell).
This cache trades a tiny bit of staleness for a massive reduction in external
load while keeping the pipeline unchanged.

Design
------
- **Key**: ``(TICKER_UPPER, tuple(sorted(sources)), lookback_days)``. Lookback
  defines the freshness window, so different windows must not collide.
- **Value**: the full ``CollectionOutcome`` plus the UTC timestamp it was cached
  at.
- **TTL**: configurable via ``settings.collection_cache_ttl_s``; 0 disables the
  cache.
- **Capacity**: configurable via ``settings.collection_cache_max_entries``; LRU
  eviction. Process-local only — the cache is *never* written to disk because
  the collection stage already archives raw documents under ``data/raw/``.
- **Negative caching**: we only cache outcomes that produced at least one usable
  document. Empty results are almost always transient (rate limit / entitlement)
  and caching them would starve future runs.
- **Thread-safety**: protected by a single ``threading.Lock`` since
  ``collect_data`` is invoked from ``asyncio.to_thread`` and may run in
  parallel for multi-ticker batches.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable

from pipelines.collect.models import CollectionOutcome
from core.utils.logger import get_logger

logger = get_logger("pipelines.collect.cache")


CacheKey = tuple[str, tuple[str, ...], int]


class CollectionCache:
    """TTL + LRU cache protecting the external data-collection stage."""

    def __init__(self, *, ttl_s: int, max_entries: int) -> None:
        self._ttl_s = max(0, int(ttl_s))
        self._max_entries = max(1, int(max_entries))
        self._store: "OrderedDict[CacheKey, tuple[float, CollectionOutcome]]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(ticker: str, sources: Iterable[str], lookback_days: int) -> CacheKey:
        sources = sources or ()
        normalized_sources = tuple(sorted({str(s).strip().lower() for s in sources if str(s).strip()}))
        return (str(ticker).upper().strip(), normalized_sources, int(lookback_days))

    @property
    def enabled(self) -> bool:
        return self._ttl_s > 0

    def get(self, key: CacheKey) -> CollectionOutcome | None:
        if not self.enabled:
            return None
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            cached_at_epoch, outcome = entry
            age = time.time() - cached_at_epoch
            if age > self._ttl_s:
                self._store.pop(key, None)
                self._misses += 1
                return None
            # Touch for LRU ordering.
            self._store.move_to_end(key)
            self._hits += 1
            # Stamp the replay with freshly computed age so the UI can show it.
            return replace(
                outcome,
                cache_hit=True,
                cached_at=datetime.fromtimestamp(cached_at_epoch, tz=timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                cache_age_s=round(age, 2),
            )

    def put(self, key: CacheKey, outcome: CollectionOutcome) -> None:
        if not self.enabled:
            return
        # Negative caching guard — only cache meaningful results.
        if not outcome.documents:
            return
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (time.time(), outcome)
            while len(self._store) > self._max_entries:
                evicted_key, _ = self._store.popitem(last=False)
                logger.debug("[COLLECT_CACHE_EVICT] key=%s", evicted_key)

    def invalidate(self, ticker: str | None = None) -> int:
        """Drop all entries for a ticker (or all entries when ticker is None)."""
        with self._lock:
            if ticker is None:
                count = len(self._store)
                self._store.clear()
                return count
            target = str(ticker).upper().strip()
            keys = [k for k in self._store.keys() if k[0] == target]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    def stats(self) -> dict:
        with self._lock:
            return {
                "enabled": self.enabled,
                "ttl_s": self._ttl_s,
                "max_entries": self._max_entries,
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }


_cache_singleton: CollectionCache | None = None
_singleton_lock = threading.Lock()


def get_cache(settings=None) -> CollectionCache:
    """Return (and lazily build) the process-wide cache honoring settings."""
    global _cache_singleton
    if _cache_singleton is not None:
        return _cache_singleton
    with _singleton_lock:
        if _cache_singleton is None:
            if settings is None:
                from core.config.settings import load_settings
                settings = load_settings()
            _cache_singleton = CollectionCache(
                ttl_s=getattr(settings, "collection_cache_ttl_s", 300),
                max_entries=getattr(settings, "collection_cache_max_entries", 32),
            )
        return _cache_singleton


def reset_cache() -> None:
    """Test-only hook: reset the singleton so each test gets a clean slate."""
    global _cache_singleton
    with _singleton_lock:
        _cache_singleton = None
