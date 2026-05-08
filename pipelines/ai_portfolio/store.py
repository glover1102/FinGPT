from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from pipelines.ai_portfolio.engine import now_iso


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE_ROOT = PROJECT_ROOT / "data" / "ai_portfolio"


COLLECTIONS = {
    "policies": "policies.json",
    "recommendations": "recommendations.json",
    "snapshots": "snapshots.json",
    "signals": "signals.json",
    "history": "history.json",
    "reports": "reports.json",
    "operations": "operations.json",
}

COLLECTION_KEYS = {
    "policies": "policy_id",
    "recommendations": "recommendation_id",
    "snapshots": "snapshot_id",
    "signals": "signal_id",
    "history": "event_id",
    "reports": "report_id",
    "operations": "operation_id",
}


class _ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def store_root() -> Path:
    override = os.getenv("AI_PORTFOLIO_DATA_DIR", "").strip()
    return Path(override) if override else DEFAULT_STORE_ROOT


def db_path() -> Path:
    override = os.getenv("AI_PORTFOLIO_DB_PATH", "").strip()
    if override:
        return Path(override)
    return store_root() / "ai_portfolio.sqlite3"


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, factory=_ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_portfolio_items (
            collection TEXT NOT NULL,
            item_key TEXT NOT NULL,
            item_value TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (collection, item_key, item_value)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_portfolio_collection
        ON ai_portfolio_items(collection, updated_at)
        """
    )
    conn.commit()
    _migrate_legacy_json(conn)
    return conn


def _legacy_json_path(collection: str) -> Path:
    return store_root() / COLLECTIONS[collection]


def _read_legacy_json(collection: str) -> list[dict[str, Any]]:
    path = _legacy_json_path(collection)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _legacy_json_status(collection: str) -> dict[str, Any]:
    path = _legacy_json_path(collection)
    items = _read_legacy_json(collection)
    return {
        "collection": collection,
        "path": str(path),
        "exists": path.exists(),
        "item_count": len(items),
        "role": "legacy_migration_seed",
        "write_target": False,
    }


def _migrate_legacy_json(conn: sqlite3.Connection) -> None:
    for collection in COLLECTIONS:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM ai_portfolio_items WHERE collection=?",
            (collection,),
        ).fetchone()
        if row and int(row["n"] or 0) > 0:
            continue
        items = _read_legacy_json(collection)
        if not items:
            continue
        key = COLLECTION_KEYS[collection]
        for item in items:
            if isinstance(item, dict):
                _upsert_with_conn(conn, collection, key, item)
    conn.commit()


def _payload(item: dict[str, Any]) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _item_key_value(collection: str, key: str | None, item: dict[str, Any]) -> tuple[str, str]:
    item_key = key or COLLECTION_KEYS.get(collection, "id")
    value = str(item.get(item_key, "")).strip()
    if not value:
        value = f"item_{uuid.uuid4().hex[:16]}"
        item[item_key] = value
    return item_key, value


def _upsert_with_conn(conn: sqlite3.Connection, collection: str, key: str | None, item: dict[str, Any]) -> dict[str, Any]:
    if collection not in COLLECTIONS:
        raise ValueError(f"unknown ai portfolio collection: {collection}")
    now = now_iso()
    item_key, item_value = _item_key_value(collection, key, item)
    existing = conn.execute(
        """
        SELECT created_at FROM ai_portfolio_items
        WHERE collection=? AND item_key=? AND item_value=?
        """,
        (collection, item_key, item_value),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO ai_portfolio_items(collection, item_key, item_value, payload, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(collection, item_key, item_value) DO UPDATE SET
            payload=excluded.payload,
            updated_at=excluded.updated_at
        """,
        (collection, item_key, item_value, _payload(item), existing["created_at"] if existing else now, now),
    )
    return item


def list_items(collection: str) -> list[dict[str, Any]]:
    if collection not in COLLECTIONS:
        raise ValueError(f"unknown ai portfolio collection: {collection}")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM ai_portfolio_items
            WHERE collection=?
            ORDER BY updated_at DESC, rowid DESC
            """,
            (collection,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            parsed = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            items.append(parsed)
    return items


def get_item(collection: str, key: str, value: str) -> dict[str, Any] | None:
    if collection not in COLLECTIONS:
        raise ValueError(f"unknown ai portfolio collection: {collection}")
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT payload FROM ai_portfolio_items
            WHERE collection=? AND item_key=? AND item_value=?
            """,
            (collection, key, str(value)),
        ).fetchone()
    if not row:
        return None
    try:
        parsed = json.loads(row["payload"])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def upsert_item(collection: str, key: str, item: dict[str, Any]) -> dict[str, Any]:
    with _connect() as conn:
        _upsert_with_conn(conn, collection, key, item)
        conn.commit()
    return item


def append_item(collection: str, item: dict[str, Any]) -> dict[str, Any]:
    with _connect() as conn:
        _upsert_with_conn(conn, collection, COLLECTION_KEYS.get(collection), item)
        conn.commit()
    return item


def filter_items(collection: str, **filters: str) -> list[dict[str, Any]]:
    items = list_items(collection)
    if not filters:
        return items
    out: list[dict[str, Any]] = []
    for item in items:
        if all(str(item.get(key, "")) == str(value) for key, value in filters.items()):
            out.append(item)
    return out


def update_item(collection: str, key: str, value: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_item(collection, key, value)
    if not existing:
        return None
    merged = {**existing, **updates}
    return upsert_item(collection, key, merged)


def store_status() -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT collection, COUNT(*) AS item_count, MAX(updated_at) AS latest_updated_at
            FROM ai_portfolio_items
            GROUP BY collection
            ORDER BY collection
            """
        ).fetchall()
    counts = {
        str(row["collection"]): {
            "count": int(row["item_count"] or 0),
            "item_count": int(row["item_count"] or 0),
            "latest_updated_at": row["latest_updated_at"],
        }
        for row in rows
    }
    return {
        "status": "ok",
        "primary_store": "sqlite",
        "db_path": str(db_path()),
        "write_path": str(db_path()),
        "legacy_json_policy": "read_once_only_when_sqlite_collection_empty",
        "collections": {
            collection: counts.get(collection, {"count": 0, "item_count": 0, "latest_updated_at": None})
            for collection in COLLECTIONS
        },
        "legacy_json": [_legacy_json_status(collection) for collection in COLLECTIONS],
        "migration_note": (
            "history.json, policies.json, recommendations.json and sibling JSON files are legacy seed files. "
            "The current runtime writes to SQLite and only reads JSON when a matching SQLite collection is empty."
        ),
    }
