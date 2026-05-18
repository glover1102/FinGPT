from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd

from pipelines.data_mart.jobs.update_filings_daily import update_filings_daily
from pipelines.data_mart.jobs.update_macro_daily import update_macro_daily
from pipelines.data_mart.jobs.update_prices_daily import update_prices_daily
from pipelines.data_mart.models import MacroObservation, PriceBar, ProviderFetchResult
from pipelines.data_mart.providers.yfinance_provider import fetch_daily_prices
from pipelines.data_mart.storage import repository
from scripts.daily_update import parse_watchlist


def _price_fetcher(tickers, **kwargs):
    return ProviderFetchResult(
        provider="unit_price",
        status="ok",
        rows=len(tickers),
        records=[
            PriceBar(
                ticker=ticker,
                date="2026-05-01",
                open=100,
                high=110,
                low=99,
                close=105,
                adjusted_close=104,
                volume=1000,
                source="unit_price",
            )
            for ticker in tickers
        ],
    )


def _failing_price_fetcher(tickers, **kwargs):
    return ProviderFetchResult(
        provider="unit_price",
        status="failed",
        rows=0,
        records=[],
        error="provider offline",
        detail={"failed_tickers": {ticker: "offline" for ticker in tickers}},
    )


def _macro_fetcher(series_ids, **kwargs):
    return ProviderFetchResult(
        provider="unit_macro",
        status="ok",
        rows=len(series_ids),
        records=[
            MacroObservation(
                series_id=series_id,
                date="2026-05-01",
                value=4.5,
                source="unit_macro",
            )
            for series_id in series_ids
        ],
    )


def _sec_collector(ticker, lookback_days, sec_user_agent, limit=5):
    result = SimpleNamespace(status="ok", detail="ok")
    return result, [
        {
            "title": f"SEC 10-Q filing for {ticker}",
            "text": f"{ticker} filed SEC form 10-Q.",
            "published_at": "2026-04-25",
            "url": f"https://sec.example/{ticker}/10q",
        }
    ]


def test_daily_price_update_is_idempotent_and_logs_provider(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"

    first = update_prices_daily(["AAPL", "MSFT"], market="us", db_path=db_path, fetcher=_price_fetcher)
    second = update_prices_daily(["AAPL", "MSFT"], market="us", db_path=db_path, fetcher=_price_fetcher)

    assert first.status == "success"
    assert first.rows_inserted == 2
    assert second.rows_inserted == 0
    assert second.rows_updated == 2
    health = repository.data_health(db_path=db_path)
    assert health["table_counts"]["prices_daily"] == 2
    assert health["table_counts"]["provider_status"] == 2


def test_failed_provider_records_status_without_prices(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"

    result = update_prices_daily(["AAPL"], market="us", db_path=db_path, fetcher=_failing_price_fetcher)

    assert result.status == "failed"
    health = repository.data_health(db_path=db_path)
    assert health["table_counts"]["prices_daily"] == 0
    assert health["recent_provider_status"][0]["status"] == "failed"
    assert "provider offline" in health["latest_run"]["error_message"]


def test_macro_update_records_observations(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"

    result = update_macro_daily(["DGS10", "DGS2"], market="us", db_path=db_path, fetcher=_macro_fetcher)

    assert result.status == "success"
    assert result.rows_inserted == 2
    assert repository.latest_macro("DGS10", db_path=db_path)["value"] == 4.5


def test_filings_update_records_sec_filings(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"

    result = update_filings_daily(["MSFT"], market="us", db_path=db_path, collector=_sec_collector)
    second = update_filings_daily(["MSFT"], market="us", db_path=db_path, collector=_sec_collector)
    health = repository.data_health(db_path=db_path)

    assert result.status == "success"
    assert result.rows_inserted == 1
    assert second.rows_updated == 1
    assert health["table_counts"]["filings"] == 1


def test_yfinance_provider_skips_rows_without_close(monkeypatch) -> None:
    class FakeTicker:
        def history(self, **kwargs):
            return pd.DataFrame(
                [
                    {"Open": None, "High": None, "Low": None, "Close": None, "Adj Close": None, "Volume": 0},
                    {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Adj Close": None, "Volume": 1000},
                ],
                index=pd.to_datetime(["2026-05-01", "2026-05-02"]),
            )

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: FakeTicker()))

    result = fetch_daily_prices(["TLT"], start_date="2026-05-01", end_date="2026-05-03")

    assert result.status == "ok"
    assert len(result.records) == 1
    assert result.records[0].adjusted_close == result.records[0].close
    assert result.detail["skipped_empty_price_rows"] == {"TLT": 1}


def test_parse_simple_watchlist_yaml(tmp_path) -> None:
    path = tmp_path / "core_us.yaml"
    path.write_text("watchlist:\n  - AAPL\n  - tlt\n", encoding="utf-8")

    assert parse_watchlist(path) == ["AAPL", "TLT"]
