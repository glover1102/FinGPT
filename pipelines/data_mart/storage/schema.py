from __future__ import annotations

SCHEMA_VERSION = 3

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
    CREATE TABLE IF NOT EXISTS fingpt_article_annotations (
        article_id TEXT NOT NULL,
        ticker TEXT,
        task TEXT NOT NULL,
        label TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.0,
        source TEXT NOT NULL DEFAULT 'fingpt',
        model_id TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        PRIMARY KEY (article_id, task, source, model_id)
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
    CREATE TABLE IF NOT EXISTS asset_metadata (
        ticker TEXT PRIMARY KEY,
        name TEXT,
        asset_class TEXT,
        quote_type TEXT,
        market TEXT,
        currency TEXT,
        exchange TEXT,
        sector TEXT,
        industry TEXT,
        country TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        source TEXT NOT NULL DEFAULT 'provider',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asset_identity (
        ticker TEXT PRIMARY KEY,
        name TEXT,
        local_symbol TEXT,
        exchange TEXT,
        currency TEXT,
        country TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        source TEXT NOT NULL DEFAULT 'universe',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asset_classification (
        ticker TEXT PRIMARY KEY,
        asset_class TEXT,
        sector TEXT,
        industry TEXT,
        country TEXT,
        theme TEXT,
        etf_category TEXT,
        source TEXT NOT NULL DEFAULT 'universe',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS etf_exposure (
        ticker TEXT NOT NULL,
        exposure_type TEXT NOT NULL,
        exposure_name TEXT NOT NULL,
        exposure_weight REAL,
        source TEXT NOT NULL DEFAULT 'universe',
        updated_at TEXT NOT NULL,
        PRIMARY KEY (ticker, exposure_type, exposure_name, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kr_equity_profile (
        ticker TEXT PRIMARY KEY,
        korean_name TEXT,
        market TEXT,
        sector TEXT,
        industry TEXT,
        source TEXT NOT NULL DEFAULT 'universe',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crypto_profile (
        ticker TEXT PRIMARY KEY,
        symbol TEXT,
        category TEXT,
        quote_currency TEXT,
        source TEXT NOT NULL DEFAULT 'universe',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fundamentals_snapshots (
        ticker TEXT NOT NULL,
        as_of TEXT NOT NULL,
        source TEXT NOT NULL,
        asset_class TEXT,
        quote_type TEXT,
        currency TEXT,
        exchange_name TEXT,
        name TEXT,
        sector TEXT,
        industry TEXT,
        raw_json TEXT NOT NULL DEFAULT '{}',
        collected_at TEXT NOT NULL,
        PRIMARY KEY (ticker, as_of, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS valuation_metrics (
        ticker TEXT NOT NULL,
        as_of TEXT NOT NULL,
        source TEXT NOT NULL,
        price REAL,
        market_cap REAL,
        enterprise_value REAL,
        week52_high REAL,
        week52_low REAL,
        trailing_pe REAL,
        forward_pe REAL,
        price_to_book REAL,
        dividend_yield REAL,
        yield_value REAL,
        beta REAL,
        analyst_rating_mean REAL,
        analyst_target_mean REAL,
        num_analysts INTEGER,
        shares_outstanding REAL,
        average_volume REAL,
        collected_at TEXT NOT NULL,
        PRIMARY KEY (ticker, as_of, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_statements (
        ticker TEXT NOT NULL,
        as_of TEXT NOT NULL,
        source TEXT NOT NULL,
        statement_type TEXT NOT NULL DEFAULT 'provider_snapshot',
        total_revenue REAL,
        revenue_per_share REAL,
        trailing_eps REAL,
        forward_eps REAL,
        book_value REAL,
        gross_margin REAL,
        operating_margin REAL,
        profit_margin REAL,
        return_on_equity REAL,
        revenue_growth REAL,
        earnings_growth REAL,
        ebitda REAL,
        free_cashflow REAL,
        total_cash REAL,
        total_debt REAL,
        debt_to_equity REAL,
        total_assets REAL,
        net_assets REAL,
        nav_price REAL,
        expense_ratio REAL,
        collected_at TEXT NOT NULL,
        PRIMARY KEY (ticker, as_of, source, statement_type)
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
    "CREATE INDEX IF NOT EXISTS idx_fingpt_annotations_ticker_task ON fingpt_article_annotations(ticker, task, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fingpt_annotations_article ON fingpt_article_annotations(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker_asof ON fundamentals_snapshots(ticker, as_of DESC)",
    "CREATE INDEX IF NOT EXISTS idx_valuation_ticker_asof ON valuation_metrics(ticker, as_of DESC)",
    "CREATE INDEX IF NOT EXISTS idx_financials_ticker_asof ON financial_statements(ticker, as_of DESC)",
    "CREATE INDEX IF NOT EXISTS idx_asset_classification_class_sector ON asset_classification(asset_class, sector)",
    "CREATE INDEX IF NOT EXISTS idx_etf_exposure_ticker ON etf_exposure(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_kr_equity_profile_market ON kr_equity_profile(market)",
    "CREATE INDEX IF NOT EXISTS idx_provider_status_run ON provider_status(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_quality_entity ON data_quality_checks(entity_type, entity_id, checked_at DESC)",
)
