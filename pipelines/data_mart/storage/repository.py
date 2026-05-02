from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from pipelines.data_mart.models import MacroObservation, NewsArticle, PriceBar, utc_now_iso
from pipelines.data_mart.storage.db import connect, init_db


def _conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    init_db(db_path)
    return connect(db_path)


def _asset_id(ticker: str) -> str:
    return ticker.upper().strip()


def ensure_assets(
    tickers: Iterable[str],
    *,
    market: str = "",
    asset_class: str = "",
    source: str = "watchlist",
    db_path: str | Path | None = None,
) -> None:
    now = utc_now_iso()
    with _conn(db_path) as conn:
        for raw in tickers:
            ticker = str(raw or "").upper().strip()
            if not ticker:
                continue
            conn.execute(
                """
                INSERT INTO assets(asset_id, ticker, market, asset_class, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    market=COALESCE(NULLIF(excluded.market, ''), assets.market),
                    asset_class=COALESCE(NULLIF(excluded.asset_class, ''), assets.asset_class),
                    updated_at=excluded.updated_at
                """,
                (_asset_id(ticker), ticker, market, asset_class, source, now, now),
            )
        conn.commit()


def upsert_prices(prices: Iterable[PriceBar], *, db_path: str | Path | None = None) -> dict[str, int]:
    inserted = 0
    updated = 0
    with _conn(db_path) as conn:
        for price in prices:
            ticker = price.ticker.upper().strip()
            if not ticker or not price.date:
                continue
            asset_id = price.asset_id or _asset_id(ticker)
            existing = conn.execute(
                "SELECT 1 FROM prices_daily WHERE ticker=? AND date=? AND source=?",
                (ticker, price.date, price.source),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO prices_daily(
                    asset_id, ticker, date, open, high, low, close, adjusted_close, volume, source, collected_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, date, source) DO UPDATE SET
                    asset_id=excluded.asset_id,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    adjusted_close=excluded.adjusted_close,
                    volume=excluded.volume,
                    collected_at=excluded.collected_at
                """,
                (
                    asset_id,
                    ticker,
                    price.date,
                    price.open,
                    price.high,
                    price.low,
                    price.close,
                    price.adjusted_close,
                    price.volume,
                    price.source,
                    price.collected_at,
                ),
            )
            inserted += 0 if existing else 1
            updated += 1 if existing else 0
        conn.commit()
    return {"inserted": inserted, "updated": updated}


def get_prices(
    ticker: str,
    *,
    limit: int = 252,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ticker, date, open, high, low, close, adjusted_close, volume, source, collected_at
            FROM prices_daily
            WHERE ticker=?
            ORDER BY date DESC
            LIMIT ?
            """,
            (ticker.upper().strip(), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows][::-1]


def latest_price(ticker: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with _conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT ticker, date, close, adjusted_close, volume, source, collected_at
            FROM prices_daily
            WHERE ticker=?
            ORDER BY date DESC
            LIMIT 1
            """,
            (ticker.upper().strip(),),
        ).fetchone()
    return dict(row) if row else None


def upsert_macro_observations(
    observations: Iterable[MacroObservation],
    *,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    inserted = 0
    updated = 0
    now = utc_now_iso()
    with _conn(db_path) as conn:
        for obs in observations:
            series_id = obs.series_id.upper().strip()
            if not series_id or not obs.date:
                continue
            conn.execute(
                """
                INSERT INTO macro_series(series_id, title, units, frequency, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(series_id) DO UPDATE SET
                    title=COALESCE(NULLIF(excluded.title, ''), macro_series.title),
                    units=COALESCE(NULLIF(excluded.units, ''), macro_series.units),
                    frequency=COALESCE(NULLIF(excluded.frequency, ''), macro_series.frequency),
                    updated_at=excluded.updated_at
                """,
                (series_id, obs.title, obs.units, obs.frequency, obs.source, now, now),
            )
            existing = conn.execute(
                "SELECT 1 FROM macro_observations WHERE series_id=? AND date=? AND source=?",
                (series_id, obs.date, obs.source),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO macro_observations(series_id, date, value, source, collected_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(series_id, date, source) DO UPDATE SET
                    value=excluded.value,
                    collected_at=excluded.collected_at
                """,
                (series_id, obs.date, obs.value, obs.source, obs.collected_at),
            )
            inserted += 0 if existing else 1
            updated += 1 if existing else 0
        conn.commit()
    return {"inserted": inserted, "updated": updated}


def latest_macro(series_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with _conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT o.series_id, o.date, o.value, o.source, o.collected_at, s.title, s.units, s.frequency
            FROM macro_observations o
            LEFT JOIN macro_series s ON s.series_id = o.series_id
            WHERE o.series_id=?
            ORDER BY o.date DESC
            LIMIT 1
            """,
            (series_id.upper().strip(),),
        ).fetchone()
    return dict(row) if row else None


def upsert_news_articles(articles: Iterable[NewsArticle], *, db_path: str | Path | None = None) -> dict[str, int]:
    inserted = 0
    updated = 0
    with _conn(db_path) as conn:
        for article in articles:
            ticker = article.ticker.upper().strip()
            if not ticker or not article.title:
                continue
            seed = "|".join([ticker, article.title, article.url, article.published_at])
            article_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]
            existing = conn.execute("SELECT 1 FROM news_articles WHERE article_id=?", (article_id,)).fetchone()
            conn.execute(
                """
                INSERT INTO news_articles(article_id, ticker, title, url, source, published_at, summary, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    title=excluded.title,
                    summary=excluded.summary,
                    collected_at=excluded.collected_at
                """,
                (
                    article_id,
                    ticker,
                    article.title,
                    article.url,
                    article.source,
                    article.published_at,
                    article.summary,
                    article.collected_at,
                ),
            )
            inserted += 0 if existing else 1
            updated += 1 if existing else 0
        conn.commit()
    return {"inserted": inserted, "updated": updated}


def start_update_run(
    *,
    market: str = "",
    provider: str = "",
    run_id: str | None = None,
    db_path: str | Path | None = None,
) -> str:
    run_id = run_id or uuid.uuid4().hex
    with _conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO data_update_runs(run_id, started_at, status, market, provider)
            VALUES (?, ?, 'running', ?, ?)
            """,
            (run_id, utc_now_iso(), market, provider),
        )
        conn.commit()
    return run_id


def finish_update_run(
    run_id: str,
    *,
    status: str,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    error_message: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            """
            UPDATE data_update_runs
            SET finished_at=?, status=?, rows_inserted=?, rows_updated=?, error_message=?
            WHERE run_id=?
            """,
            (utc_now_iso(), status, int(rows_inserted), int(rows_updated), error_message, run_id),
        )
        conn.commit()


def record_provider_status(
    run_id: str,
    *,
    provider: str,
    status: str,
    market: str = "",
    ticker: str | None = None,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    error_message: str | None = None,
    details: dict[str, Any] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_status(
                run_id, provider, status, market, ticker, rows_inserted, rows_updated,
                error_message, started_at, finished_at, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                provider,
                status,
                market,
                ticker,
                int(rows_inserted),
                int(rows_updated),
                error_message,
                started_at or utc_now_iso(),
                finished_at or utc_now_iso(),
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()


def record_quality_check(
    *,
    check_name: str,
    status: str,
    message: str,
    run_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    observed_value: float | None = None,
    threshold_value: float | None = None,
    db_path: str | Path | None = None,
) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO data_quality_checks(
                run_id, check_name, status, entity_type, entity_id, observed_value,
                threshold_value, message, checked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                check_name,
                status,
                entity_type,
                entity_id,
                observed_value,
                threshold_value,
                message,
                utc_now_iso(),
            ),
        )
        conn.commit()


def data_health(*, db_path: str | Path | None = None) -> dict[str, Any]:
    with _conn(db_path) as conn:
        table_counts = {
            name: int(conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"])
            for name in (
                "assets",
                "prices_daily",
                "macro_observations",
                "news_articles",
                "filings",
                "data_update_runs",
                "provider_status",
                "data_quality_checks",
            )
        }
        latest_run = conn.execute(
            "SELECT * FROM data_update_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        provider_rows = conn.execute(
            """
            SELECT provider, status, market, ticker, error_message, finished_at, details_json
            FROM provider_status
            ORDER BY finished_at DESC
            LIMIT 20
            """
        ).fetchall()
        quality_rows = conn.execute(
            """
            SELECT check_name, status, entity_type, entity_id, message, checked_at
            FROM data_quality_checks
            ORDER BY checked_at DESC
            LIMIT 20
            """
        ).fetchall()
    return {
        "status": "ok",
        "database": str(Path(db_path) if db_path else "default"),
        "table_counts": table_counts,
        "latest_run": dict(latest_run) if latest_run else None,
        "recent_provider_status": [dict(row) for row in provider_rows],
        "recent_quality_checks": [dict(row) for row in quality_rows],
    }
