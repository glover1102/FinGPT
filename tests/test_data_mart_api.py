from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.server import app
from pipelines.data_mart.models import PriceBar
from pipelines.data_mart.storage import repository
from pipelines.data_mart.storage.db import init_db


def test_data_health_and_prices_endpoint_use_structured_store(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "research_mart.db"
    monkeypatch.setenv("DATA_MART_DB_PATH", str(db_path))
    init_db(db_path)
    repository.ensure_assets(["SPY"], market="us", db_path=db_path)
    repository.upsert_prices(
        [
            PriceBar(ticker="SPY", date="2026-01-02", close=100, adjusted_close=100, source="test"),
            PriceBar(ticker="SPY", date="2026-01-03", close=101, adjusted_close=101, source="test"),
        ],
        db_path=db_path,
    )
    run_id = repository.start_update_run(market="us", provider="test", db_path=db_path)
    repository.finish_update_run(run_id, status="success", rows_inserted=2, db_path=db_path)

    client = TestClient(app)
    health = client.get("/api/v1/data/health")
    prices = client.get("/api/v1/data/prices/SPY?limit=10")

    assert health.status_code == 200
    assert health.json()["table_counts"]["prices_daily"] == 2
    assert health.json()["summary"]["decision_status"] == "ok"
    assert prices.status_code == 200
    assert prices.json()["status"] == "ok"
    assert prices.json()["latest"]["date"] == "2026-01-03"


def test_backtest_endpoint_accepts_request_price_rows() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/backtest/run",
        json={
            "ticker": "SPY",
            "strategy": "buy_and_hold",
            "transaction_cost_bps": 0,
            "slippage_bps": 0,
            "price_rows": [
                {"date": "2026-01-02", "adjusted_close": 100},
                {"date": "2026-01-03", "adjusted_close": 110},
                {"date": "2026-01-04", "adjusted_close": 121},
            ],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data_status"] == "request_rows"
    assert body["equity_curve"][-1]["equity"] == 1.21


def test_portfolio_optimize_endpoint_accepts_request_returns() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/portfolio/optimize",
        json={
            "method": "inverse_volatility",
            "returns_by_asset": {
                "LOW": [0.001, 0.002, 0.001, 0.002],
                "HIGH": [0.05, -0.04, 0.03, -0.02],
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data_status"] == "request_returns"
    assert body["weights"]["LOW"] > body["weights"]["HIGH"]
