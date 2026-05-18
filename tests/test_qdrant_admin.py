"""Tests for the Qdrant admin helpers (collection info + age/ticker purge).

We stub ``get_qdrant_client`` rather than spin a real Qdrant instance so the
test runs in under a second on any CI / local box. The stubs mirror the shape
of the qdrant_client responses we depend on (``collection_exists``, ``scroll``,
``delete``, ``get_collection``).
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import patch


@dataclass
class _FakePoint:
    id: str
    payload: dict


@dataclass
class _FakeClient:
    """In-memory stand-in for qdrant_client.QdrantClient used in tests."""
    points: list[_FakePoint] = field(default_factory=list)
    deleted_ids: list[Any] = field(default_factory=list)

    def collection_exists(self, name: str) -> bool:
        return True

    def get_collection(self, name: str):
        class _Info:
            status = "green"
            points_count = 42
            vectors_count = 42
            indexed_vectors_count = 42
            segments_count = 1
            payload_schema: dict = {}

            def model_dump(self_inner):  # noqa: N805
                return {
                    "status": "green",
                    "points_count": 42,
                    "vectors_count": 42,
                    "indexed_vectors_count": 42,
                    "segments_count": 1,
                    "payload_schema": {},
                }

        return _Info()

    def scroll(
        self,
        *,
        collection_name: str,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
        offset: Optional[int] = None,
    ):
        start = int(offset or 0)
        end = start + limit
        batch = self.points[start:end]
        next_offset = end if end < len(self.points) else None
        return batch, next_offset

    def delete(self, *, collection_name: str, points_selector):
        ids = list(points_selector.points)  # PointIdsList
        self.deleted_ids.extend(ids)


def _mk_point(pid: str, ticker: str, collected_days_ago: int) -> _FakePoint:
    ts = datetime.now(timezone.utc) - timedelta(days=collected_days_ago)
    return _FakePoint(
        id=pid,
        payload={
            "ticker": ticker,
            "collected_at": ts.isoformat().replace("+00:00", "Z"),
            "doc_id": f"doc-{pid}",
            "doc_type": "news",
        },
    )


class QdrantAdminTests(unittest.TestCase):
    def _with_client(self, client: _FakeClient):
        return patch("core.utils.qdrant_admin.get_qdrant_client", return_value=client)

    def test_get_collection_info_exposes_ticker_breakdown(self) -> None:
        from core.utils.qdrant_admin import get_collection_info

        client = _FakeClient(points=[
            _mk_point("a", "AAPL", 5),
            _mk_point("b", "AAPL", 2),
            _mk_point("c", "MSFT", 1),
        ])
        with self._with_client(client):
            info = get_collection_info(collection_name="test_collection")
        self.assertTrue(info["exists"])
        self.assertEqual(info["collection"], "test_collection")
        breakdown = {row["ticker"]: row["count"] for row in info["ticker_breakdown"]}
        self.assertEqual(breakdown, {"AAPL": 2, "MSFT": 1})

    def test_purge_requires_any_filter(self) -> None:
        from core.utils.qdrant_admin import purge_points

        with self.assertRaises(ValueError):
            purge_points()  # type: ignore[call-arg]

    def test_purge_by_age_only_targets_old_points(self) -> None:
        from core.utils.qdrant_admin import purge_points

        client = _FakeClient(points=[
            _mk_point("old-1", "AAPL", 45),
            _mk_point("old-2", "MSFT", 60),
            _mk_point("fresh-1", "AAPL", 5),
        ])
        with self._with_client(client):
            result = purge_points(older_than_days=30, collection_name="c")
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(sorted(client.deleted_ids), ["old-1", "old-2"])

    def test_purge_by_ticker_only_scopes_deletion(self) -> None:
        from core.utils.qdrant_admin import purge_points

        client = _FakeClient(points=[
            _mk_point("a", "AAPL", 1),
            _mk_point("b", "AAPL", 50),
            _mk_point("c", "MSFT", 50),
        ])
        with self._with_client(client):
            result = purge_points(ticker="aapl", collection_name="c")
        self.assertEqual(result["matched"], 2)
        self.assertEqual(sorted(client.deleted_ids), ["a", "b"])

    def test_purge_dry_run_does_not_delete(self) -> None:
        from core.utils.qdrant_admin import purge_points

        client = _FakeClient(points=[
            _mk_point("a", "AAPL", 90),
            _mk_point("b", "AAPL", 5),
        ])
        with self._with_client(client):
            result = purge_points(older_than_days=30, dry_run=True, collection_name="c")
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(client.deleted_ids, [])

    def test_purge_keeps_undated_points(self) -> None:
        """Safety net: rows without parseable collected_at/published_at must be preserved."""
        from core.utils.qdrant_admin import purge_points

        undated = _FakePoint(id="undated", payload={"ticker": "AAPL"})  # no timestamp
        old = _mk_point("old", "AAPL", 90)
        client = _FakeClient(points=[undated, old])
        with self._with_client(client):
            result = purge_points(older_than_days=30, collection_name="c")
        self.assertEqual(result["matched"], 1)
        self.assertEqual(client.deleted_ids, ["old"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
