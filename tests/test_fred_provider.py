from __future__ import annotations

from pipelines.data_mart.providers.fred_provider import fetch_macro_series


class _Response:
    def __init__(self, status_code: int = 200, *, text: str = "", payload: dict | None = None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_fred_fetch_uses_csv_fallback_for_failed_api_series() -> None:
    calls: list[tuple[str, dict]] = []

    def fake_get(url: str, params: dict):
        calls.append((url, dict(params)))
        if "series/observations" in url:
            if params["series_id"] == "DGS10":
                return _Response(500)
            return _Response(payload={"observations": [{"date": "2026-05-08", "value": "4.11"}]})
        return _Response(text="observation_date,DGS10\n2026-05-08,4.12\n")

    result = fetch_macro_series(
        ["DGS2", "DGS10"],
        api_key="test-key",
        allow_csv_fallback=True,
        http_get=fake_get,
    )

    assert result.status == "ok"
    assert result.error is None
    assert result.rows == 2
    assert {record.series_id for record in result.records} == {"DGS2", "DGS10"}
    assert {record.source for record in result.records} == {"fred", "fred_csv"}
    assert result.detail["fallback_provider"] == "fred_csv"
    assert result.detail["fallback_recovered_series"] == ["DGS10"]
    assert any("fredgraph.csv" in url for url, _ in calls)
