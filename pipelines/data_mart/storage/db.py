from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.settings import load_settings
from pipelines.data_mart.models import utc_now_iso
from pipelines.data_mart.storage.schema import DDL_STATEMENTS, SCHEMA_VERSION


def default_db_path() -> Path:
    settings = load_settings()
    configured = str(getattr(settings, "data_mart_db_path", "") or "").strip()
    return Path(configured) if configured else settings.data_dir / "research_mart.db"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db(db_path: str | Path | None = None) -> Path:
    path = Path(db_path) if db_path is not None else default_db_path()
    with connect(path) as conn:
        for statement in DDL_STATEMENTS:
            conn.execute(statement)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, utc_now_iso()),
        )
        conn.commit()
    return path
