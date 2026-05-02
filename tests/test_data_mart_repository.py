from __future__ import annotations

from pipelines.data_mart.models import MacroObservation, NewsArticle, PriceBar
from pipelines.data_mart.storage import repository


def test_price_upsert_is_idempotent_and_keeps_runs_db_separate(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    repository.ensure_assets(["AAPL"], market="us", db_path=db_path)

    first = repository.upsert_prices(
        [
            PriceBar(
                ticker="AAPL",
                date="2026-05-01",
                open=100,
                high=110,
                low=99,
                close=108,
                adjusted_close=107.5,
                volume=12345,
                source="test",
            )
        ],
        db_path=db_path,
    )
    second = repository.upsert_prices(
        [
            PriceBar(
                ticker="AAPL",
                date="2026-05-01",
                open=101,
                high=111,
                low=100,
                close=109,
                adjusted_close=108.5,
                volume=54321,
                source="test",
            )
        ],
        db_path=db_path,
    )

    assert first == {"inserted": 1, "updated": 0}
    assert second == {"inserted": 0, "updated": 1}
    rows = repository.get_prices("AAPL", db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["close"] == 109
    assert not (tmp_path / "runs.db").exists()


def test_macro_and_news_upserts_have_stable_keys(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"

    macro_result = repository.upsert_macro_observations(
        [
            MacroObservation(
                series_id="DGS10",
                date="2026-05-01",
                value=4.25,
                title="10-Year Treasury Constant Maturity Rate",
                units="percent",
            )
        ],
        db_path=db_path,
    )
    news_first = repository.upsert_news_articles(
        [
            NewsArticle(
                ticker="TLT",
                title="Treasury yields fall",
                url="https://example.com/tlt",
                source="Example",
                published_at="2026-05-01T12:00:00Z",
                summary="Long-duration bonds rose as yields fell.",
            )
        ],
        db_path=db_path,
    )
    news_second = repository.upsert_news_articles(
        [
            NewsArticle(
                ticker="TLT",
                title="Treasury yields fall",
                url="https://example.com/tlt",
                source="Example",
                published_at="2026-05-01T12:00:00Z",
                summary="Updated summary",
            )
        ],
        db_path=db_path,
    )

    assert macro_result == {"inserted": 1, "updated": 0}
    assert repository.latest_macro("DGS10", db_path=db_path)["value"] == 4.25
    assert news_first == {"inserted": 1, "updated": 0}
    assert news_second == {"inserted": 0, "updated": 1}


def test_update_run_provider_status_and_health(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    run_id = repository.start_update_run(market="us", provider="yfinance", db_path=db_path)
    repository.record_provider_status(
        run_id,
        provider="yfinance",
        status="ok",
        market="us",
        ticker="AAPL",
        rows_inserted=2,
        details={"source": "unit-test"},
        db_path=db_path,
    )
    repository.record_quality_check(
        run_id=run_id,
        check_name="coverage",
        status="pass",
        entity_type="ticker",
        entity_id="AAPL",
        message="AAPL has fresh prices.",
        db_path=db_path,
    )
    repository.finish_update_run(run_id, status="success", rows_inserted=2, db_path=db_path)

    health = repository.data_health(db_path=db_path)

    assert health["latest_run"]["status"] == "success"
    assert health["table_counts"]["provider_status"] == 1
    assert health["recent_provider_status"][0]["provider"] == "yfinance"
    assert health["recent_quality_checks"][0]["check_name"] == "coverage"
