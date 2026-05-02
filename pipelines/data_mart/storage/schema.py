from __future__ import annotations

SCHEMA_VERSION = 1

DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assets (
        asset_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL UNIQUE,
        name TEXT,
        market TEXT,
        asset_class TEXT,
        currency TEXT,
        exchange TEXT,
        source TEXT NOT NULL DEFAULT 'manual',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prices_daily (
        asset_id TEXT,
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        adjusted_close REAL,
        volume REAL,
        source TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        PRIMARY KEY (ticker, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS macro_series (
        series_id TEXT PRIMARY KEY,
        title TEXT,
        units TEXT,
        frequency TEXT,
        source TEXT NOT NULL DEFAULT 'fred',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS macro_observations (
        series_id TEXT NOT NULL,
        date TEXT NOT NULL,
        value REAL,
        source TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        PRIMARY KEY (series_id, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_articles (
        article_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT,
        source TEXT NOT NULL,
        published_at TEXT,
        summary TEXT,
        collected_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS filings (
        filing_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        form_type TEXT NOT NULL,
        filed_at TEXT,
        url TEXT,
        source TEXT NOT NULL DEFAULT 'sec',
        collected_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_update_runs (
        run_id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        market TEXT,
        provider TEXT,
        rows_inserted INTEGER NOT NULL DEFAULT 0,
        rows_updated INTEGER NOT NULL DEFAULT 0,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        status TEXT NOT NULL,
        market TEXT,
        ticker TEXT,
        rows_inserted INTEGER NOT NULL DEFAULT 0,
        rows_updated INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_quality_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        check_name TEXT NOT NULL,
        status TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        observed_value REAL,
        threshold_value REAL,
        message TEXT NOT NULL,
        checked_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices_daily(ticker, date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_macro_series_date ON macro_observations(series_id, date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_provider_status_run ON provider_status(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_quality_entity ON data_quality_checks(entity_type, entity_id, checked_at DESC)",
)
