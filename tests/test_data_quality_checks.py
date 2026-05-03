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


def test_quality_checks_use_series_specific_macro_freshness_thresholds(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    repository.upsert_macro_observations(
        [
            MacroObservation(series_id="CPIAUCSL", date="2026-03-01", value=320.0),
            MacroObservation(series_id="DTWEXBGS", date="2026-04-24", value=125.0),
        ],
        db_path=db_path,
    )

    checks = run_data_quality_checks(db_path=db_path, stale_macro_days=7)
    macro = {
        check["entity_id"]: check
        for check in checks
        if check["check_name"] == "macro_series_freshness"
    }

    assert macro["CPIAUCSL"]["status"] == "pass"
    assert macro["CPIAUCSL"]["threshold_value"] == 95
    assert macro["DTWEXBGS"]["status"] == "pass"
    assert macro["DTWEXBGS"]["threshold_value"] == 14


def test_quality_checks_separate_missing_close_from_adjusted_close(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    repository.upsert_prices(
        [
            PriceBar(ticker="TLT", date="2026-05-01", close=None, adjusted_close=None, source="test"),
            PriceBar(ticker="AAPL", date="2026-05-01", close=100, adjusted_close=100, source="test"),
        ],
        db_path=db_path,
    )

    checks = run_data_quality_checks(db_path=db_path, stale_price_days=9999)
    by_name = {check["check_name"]: check for check in checks}

    assert by_name["prices_close_not_null"]["status"] == "warn"
    assert by_name["prices_adjusted_close_not_null_for_us_equities"]["status"] == "pass"
