"""Qdrant admin helpers — collection introspection and age-based purge.

Why this exists
---------------
Long-lived local installs accumulate embeddings from every research run. Stale
documents can (1) bloat disk usage and (2) pollute retrieval if date filters
fail. The UI needs a small admin surface to:

- See how big the collection is (points, vectors, disk size if available).
- Drop documents older than a user-chosen horizon (e.g. 30 days) or scoped to
  a single ticker.

The purge path intentionally prefers **payload-based filters** over deleting
entire collections so we never nuke data the user still wants.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable

from core.config.settings import load_settings
from core.utils.logger import get_logger
from core.utils.qdrant_helpers import get_qdrant_client

logger = get_logger("core.utils.qdrant_admin")


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Best-effort conversion of qdrant_client response objects to plain dicts."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for method in ("model_dump", "dict"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                return fn()  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                pass
    try:
        return dict(obj.__dict__)
    except Exception:  # noqa: BLE001
        return {"repr": repr(obj)}


def get_collection_info(collection_name: str | None = None) -> Dict[str, Any]:
    """Return a compact summary for the UI — points, vectors, status."""
    settings = load_settings()
    name = collection_name or settings.collection_name
    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key, enable_embeddings=False)

    result: Dict[str, Any] = {
        "collection": name,
        "exists": False,
    }
    try:
        exists = (
            client.collection_exists(name)
            if hasattr(client, "collection_exists")
            else any(c.name == name for c in client.get_collections().collections)
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[QDRANT_ADMIN] exists check failed: {exc}")
        result["error"] = str(exc)
        return result

    result["exists"] = bool(exists)
    if not exists:
        return result

    try:
        info = client.get_collection(name)
        info_d = _to_dict(info)
        # Extract the numbers the UI actually cares about.
        result["status"] = info_d.get("status")
        result["points_count"] = info_d.get("points_count") or info_d.get("vectors_count")
        result["vectors_count"] = info_d.get("vectors_count")
        result["indexed_vectors_count"] = info_d.get("indexed_vectors_count")
        result["segments_count"] = info_d.get("segments_count")
        # qdrant 1.10+ returns payload_schema as dict of fields.
        schema = info_d.get("payload_schema") or {}
        result["payload_fields"] = sorted(list(schema.keys())) if isinstance(schema, dict) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[QDRANT_ADMIN] get_collection failed: {exc}")
        result["error"] = str(exc)

    # Fast ticker breakdown via a cheap scroll — we cap at 2000 points because
    # anything larger means the user should just re-embed anyway.
    try:
        breakdown: Dict[str, int] = {}
        offset = None
        seen = 0
        while seen < 2000:
            points, offset = client.scroll(
                collection_name=name,
                limit=256,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for p in points:
                payload = getattr(p, "payload", None) or {}
                ticker = (payload.get("ticker") or payload.get("symbol") or "").upper()
                if ticker:
                    breakdown[ticker] = breakdown.get(ticker, 0) + 1
                seen += 1
            if offset is None:
                break
        # Flatten to a sorted list so the UI renders deterministically.
        result["ticker_breakdown"] = sorted(
            [{"ticker": t, "count": c} for t, c in breakdown.items()],
            key=lambda x: (-x["count"], x["ticker"]),
        )
        result["ticker_breakdown_truncated"] = seen >= 2000
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[QDRANT_ADMIN] scroll breakdown failed: {exc}")
        result["ticker_breakdown"] = []
        result["ticker_breakdown_error"] = str(exc)

    return result


def _iterate_points(client: Any, collection_name: str, limit_per_scroll: int = 256) -> Iterable[Any]:
    """Yield every point in the collection via repeated ``scroll`` calls."""
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=limit_per_scroll,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        for p in points:
            yield p
        if offset is None:
            break


def _parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def purge_points(
    *,
    older_than_days: int | None = None,
    ticker: str | None = None,
    collection_name: str | None = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Delete points by age and/or ticker.

    At least one of ``older_than_days`` or ``ticker`` must be provided — we
    refuse to purge an entire collection through this endpoint because that is
    almost always a mistake and there is no undo.

    ``older_than_days`` is evaluated against ``collected_at`` first (set by the
    ingest stage for every document) and falls back to ``published_at`` when
    the collection timestamp is missing. Points with no parseable timestamp
    are **kept** — we would rather under-purge than delete something the user
    meant to keep.
    """
    if older_than_days is None and not ticker:
        raise ValueError("purge_points requires older_than_days and/or ticker")

    settings = load_settings()
    name = collection_name or settings.collection_name
    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key, enable_embeddings=False)

    try:
        exists = (
            client.collection_exists(name)
            if hasattr(client, "collection_exists")
            else any(c.name == name for c in client.get_collections().collections)
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[QDRANT_ADMIN] exists check failed: {exc}")
        raise

    if not exists:
        return {
            "collection": name,
            "exists": False,
            "scanned": 0,
            "matched": 0,
            "deleted": 0,
            "dry_run": dry_run,
        }

    cutoff: datetime | None = None
    if older_than_days is not None and older_than_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(older_than_days))

    target_ticker = (ticker or "").strip().upper() or None

    matched_ids: list[Any] = []
    scanned = 0
    for point in _iterate_points(client, name):
        scanned += 1
        payload = getattr(point, "payload", None) or {}
        point_ticker = (payload.get("ticker") or payload.get("symbol") or "").upper()
        if target_ticker and point_ticker != target_ticker:
            continue
        if cutoff is not None:
            collected = _parse_iso(payload.get("collected_at")) or _parse_iso(payload.get("published_at"))
            if collected is None:
                continue  # keep rows we cannot date
            # Normalize tz-naive timestamps to UTC so comparisons are safe.
            if collected.tzinfo is None:
                collected = collected.replace(tzinfo=timezone.utc)
            if collected >= cutoff:
                continue
        matched_ids.append(getattr(point, "id", None))

    matched_ids = [pid for pid in matched_ids if pid is not None]
    deleted = 0
    if matched_ids and not dry_run:
        try:
            from qdrant_client import models as qm

            client.delete(collection_name=name, points_selector=qm.PointIdsList(points=matched_ids))
            deleted = len(matched_ids)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[QDRANT_ADMIN] delete failed: {exc}")
            raise

    return {
        "collection": name,
        "exists": True,
        "scanned": scanned,
        "matched": len(matched_ids),
        "deleted": deleted,
        "dry_run": dry_run,
        "older_than_days": older_than_days,
        "ticker": target_ticker,
    }
