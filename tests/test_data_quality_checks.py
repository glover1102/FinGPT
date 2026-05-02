from __future__ import annotations

from pipelines.data_mart.jobs.quality_checks import run_data_quality_checks
from pipelines.data_mart.models import MacroObservation, PriceBar
from pipelines.data_mart.storage import repository


def test_quality_checks_pass_for_fresh_complete_prices(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    repository.upsert_prices(
        [
            PriceBar(
                ticker="AAPL",
                date="2026-05-01",
                close=100,
                adjusted_close=100,
                source="test",
            )
        ],
        db_path=db_path,
    )

    checks = run_data_quality_checks(db_path=db_path, stale_price_days=9999)

    by_name = {check["check_name"]: check for check in checks}
    assert by_name["prices_no_duplicate_dates"]["status"] == "pass"
    assert by_name["prices_adjusted_close_not_null_for_us_equities"]["status"] == "pass"


def test_quality_checks_warn_for_stale_macro(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    repository.upsert_macro_observations(
        [MacroObservation(series_id="DGS10", date="2020-01-01", value=1.5)],
        db_path=db_path,
    )

    checks = run_data_quality_checks(db_path=db_path, stale_macro_days=1)

    macro = [check for check in checks if check["check_name"] == "macro_series_freshness"][0]
    assert macro["status"] == "warn"
    assert macro["entity_id"] == "DGS10"
    health = repository.data_health(db_path=db_path)
    assert health["table_counts"]["data_quality_checks"] >= 2
