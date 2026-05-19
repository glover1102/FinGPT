from __future__ import annotations

import json
from datetime import date, timedelta

from pipelines.adapters.qlib_adapter import qlib_export_preview
from pipelines.data_mart.models import PriceBar
from pipelines.data_mart.storage import repository
from pipelines.data_mart.storage.db import init_db


def _seed_prices(db_path) -> None:
    init_db(db_path)
    rows = []
    for idx in range(6):
        day = (date(2026, 1, 1) + timedelta(days=idx)).isoformat()
        rows.append(
            PriceBar(
                ticker="SPY",
                date=day,
                open=99 + idx,
                high=101 + idx,
                low=98 + idx,
                close=100 + idx,
                adjusted_close=100 + idx,
                volume=1_000_000 + idx,
                source="test",
            )
        )
    repository.upsert_prices(rows, db_path=db_path)


def test_qlib_export_writes_data_mart_csv_seed_when_enabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "research_mart.db"
    export_root = tmp_path / "qlib_provider"
    _seed_prices(db_path)
    monkeypatch.setenv("DATA_MART_DB_PATH", str(db_path))
    monkeypatch.setenv("QUANT_LAB_QLIB_ENABLED", "true")
    monkeypatch.setenv("QLIB_PROVIDER_URI", str(export_root))

    result = qlib_export_preview(tickers=["SPY"], start_date="2026-01-01", end_date="2026-01-06", dry_run=False)

    assert result["enabled"] is True
    assert result["export_written"] is True
    assert result["row_counts"] == {"SPY": 6}
    assert result["status"] in {"exported", "exported_dependency_missing"}
    assert (export_root / "calendars" / "day.txt").exists()
    assert (export_root / "instruments" / "all.txt").exists()
    assert (export_root / "features" / "SPY.csv").exists()
    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "qlib_csv_provider_seed_v1"
    assert manifest["files"]["features"]["SPY"].endswith("SPY.csv")


def test_qlib_export_does_not_write_when_disabled(tmp_path, monkeypatch) -> None:
    export_root = tmp_path / "disabled_provider"
    monkeypatch.setenv("QUANT_LAB_QLIB_ENABLED", "false")
    monkeypatch.setenv("QLIB_PROVIDER_URI", str(export_root))

    result = qlib_export_preview(tickers=["SPY"], dry_run=False)

    assert result["status"] == "disabled"
    assert result["export_written"] is False
    assert not export_root.exists()
