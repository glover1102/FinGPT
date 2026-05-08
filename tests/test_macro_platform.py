from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.server import app
from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesResponse
from pipelines.macro import macro_service
from pipelines.macro.asset_impact import ASSET_CLASSES, get_asset_impacts
from pipelines.macro.research_context import macro_research_context_to_retrieval_item
from pipelines.macro.portfolio_hints import get_portfolio_policy_hint
from pipelines.macro.providers.ecos import EcosProvider
from pipelines.macro.providers.oecd import OecdProvider
from pipelines.macro.providers.worldbank import WorldBankProvider
from pipelines.macro.providers.yahoo import YahooFinanceProvider
from pipelines.macro.regime_engine import classify_macro_regime
from pipelines.macro.series_registry import get_series_definition, list_macro_series


def _contains_chinese_japanese_or_hanja(text: str) -> bool:
    return any(0x4E00 <= ord(ch) <= 0x9FFF or 0x3040 <= ord(ch) <= 0x30FF for ch in text)


def _reset_macro_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATA_MART_DB_PATH", str(tmp_path / "macro_test.db"))
    monkeypatch.setenv("FRED_API_KEY", "")
    macro_service._SERIES_CACHE.clear()
    macro_service._OVERVIEW_CACHE.clear()


def _series(series_id: str, value: float, *, change_3: float = 0.0) -> MacroSeriesResponse:
    definition = get_series_definition(series_id)
    observation = MacroObservation(date="2026-04-30", value=value, raw_value=value, source="test")
    return MacroSeriesResponse(
        series_id=definition.series_id,
        display_name=definition.display_name,
        category=definition.category,
        unit=definition.unit,
        frequency=definition.frequency,
        provider="test",
        observations=[observation],
        latest=observation,
        changes={
            "latest_date": observation.date,
            "latest_value": value,
            "change_1_period": change_3,
            "change_3_period": change_3,
            "change_12_period": change_3,
        },
        data_quality=MacroDataQuality(status="ok", provider="test", last_updated=observation.date),
    )


def test_macro_registry_loads_required_series() -> None:
    ids = {item.series_id for item in list_macro_series(include_disabled=True)}
    for required in ["FEDFUNDS", "DGS3MO", "DGS2", "DGS10", "DGS30", "T10Y2Y", "T10Y3M", "DFII10", "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "GDPC1", "INDPRO", "RSAFS", "UMCSENT", "UNRATE", "PAYEMS", "ICSA", "JTSJOL", "M2SL", "WALCL", "RRPONTSYD", "BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS"]:
        assert required in ids
    for extension in ["ECOS_KR_POLICY_RATE", "OECD_CLI", "WORLD_BANK_GDP", "YAHOO_DXY_PROXY", "YAHOO_GLD", "YAHOO_USO"]:
        assert extension in ids


def test_provider_unavailable_returns_no_fake_observations(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    response = macro_service.get_macro_series("FEDFUNDS")
    assert response.observations == []
    assert response.latest is None
    assert response.data_quality.status == "unavailable"
    assert "FEDFUNDS" in response.data_quality.missing_series


def test_unknown_series_is_controlled_404(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get("/api/v1/macro/series/NOT_A_SERIES")
    assert response.status_code == 404
    assert response.json()["detail"] == "macro_series_not_found:NOT_A_SERIES"


def test_macro_overview_schema_and_unknown_regime_on_insufficient_data(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    overview = macro_service.get_macro_overview()
    assert overview.data_quality.status == "unavailable"
    assert overview.regime.name == "unknown"
    assert overview.regime.confidence <= 0.25
    assert overview.key_indicators
    assert all(item.data_quality for item in overview.key_indicators)


def test_api_responses_include_data_quality(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    for path in ["/api/v1/macro/overview", "/api/v1/macro/series", "/api/v1/macro/interest-rates", "/api/macro/data-quality"]:
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert "data_quality" in body


def test_synthetic_goldilocks_regime_classification() -> None:
    series = {
        "GDPC1": _series("GDPC1", 3.0),
        "INDPRO": _series("INDPRO", 2.0),
        "RSAFS": _series("RSAFS", 4.0),
        "UMCSENT": _series("UMCSENT", 92.0),
        "CPIAUCSL": _series("CPIAUCSL", 2.2, change_3=-0.2),
        "CPILFESL": _series("CPILFESL", 2.4, change_3=-0.1),
        "PCEPI": _series("PCEPI", 2.2, change_3=-0.1),
        "PCEPILFE": _series("PCEPILFE", 2.3, change_3=-0.1),
        "FEDFUNDS": _series("FEDFUNDS", 4.0),
        "DGS2": _series("DGS2", 3.7),
        "DFII10": _series("DFII10", 1.2),
        "UNRATE": _series("UNRATE", 3.8),
        "PAYEMS": _series("PAYEMS", 1.8),
        "ICSA": _series("ICSA", 210000.0),
        "BAMLH0A0HYM2": _series("BAMLH0A0HYM2", 3.2),
        "BAMLC0A0CM": _series("BAMLC0A0CM", 1.1),
        "VIXCLS": _series("VIXCLS", 14.0),
    }
    regime, signals = classify_macro_regime(series)
    assert regime.name == "goldilocks"
    assert regime.confidence > 0.5
    assert {signal.name for signal in signals} >= {"growth_signal", "inflation_signal", "policy_signal"}


def test_asset_impact_mapping_returns_required_assets() -> None:
    regime, signals = classify_macro_regime({
        "GDPC1": _series("GDPC1", -1.0),
        "UNRATE": _series("UNRATE", 6.5),
        "ICSA": _series("ICSA", 350000.0),
        "BAMLH0A0HYM2": _series("BAMLH0A0HYM2", 7.5),
        "BAMLC0A0CM": _series("BAMLC0A0CM", 3.0),
        "VIXCLS": _series("VIXCLS", 35.0),
    })
    impacts = get_asset_impacts(regime, signals)
    assert {item.asset_class for item in impacts} == set(ASSET_CLASSES)
    assert all(item.confidence >= 0 for item in impacts)


def test_portfolio_policy_hint_is_advisory_only() -> None:
    overview_quality = MacroDataQuality(status="partial", provider="test", missing_series=["CPIAUCSL"])
    regime, _signals = classify_macro_regime({})
    hint = get_portfolio_policy_hint(regime, overview_quality)
    assert hint.advisory_only is True
    assert "no trade order" in " ".join(hint.warnings).lower()
    assert hint.data_quality.status == "partial"


def test_research_context_and_brief_fallback_do_not_fabricate(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    context = macro_service.get_macro_research_context(ticker="TLT")
    assert "TLT" in context.ticker_relevance
    assert context.regime.name == "unknown"
    brief = macro_service.generate_macro_brief(include_prompt=True)
    assert brief.is_fallback is True
    assert "No key indicators are available" not in brief.content
    assert "누락되거나 오래된 데이터는 중립 신호가 아니라 증거 부족" in brief.content
    assert "경제 지표 값을 지어내지 마세요" in (brief.prompt_template or "")
    assert "중국어" in (brief.prompt_template or "")


def test_macro_research_context_can_be_injected_as_retrieval_item(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    context = macro_service.get_macro_research_context(ticker="QQQ")
    item = macro_research_context_to_retrieval_item(context, ticker="QQQ")
    assert item.source == "macro:platform"
    assert item.metadata["doc_type"] == "macro_platform_context"
    assert item.metadata["advisory_only"] is True
    assert "STRUCTURED MACRO PLATFORM CONTEXT" in item.chunk
    assert "Do not invent economic indicator values" in item.chunk


def test_live_macro_brief_rejected_when_llm_invents_numbers(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)

    class Response:
        status_code = 200
        text = "{}"

        def json(self):
            return {"response": "1. 현재 매크로 레짐\n이 브리프는 가짜 지표 9999.12를 지어냅니다."}

    monkeypatch.setattr("pipelines.macro.ai_brief.httpx.post", lambda *_, **__: Response())
    brief = macro_service.generate_macro_brief(use_llm=True, model="qwen", timeout_s=1)
    assert brief.is_fallback is True
    assert brief.provider == "rule_based_fallback"
    assert any("grounding guard rejected" in warning.lower() for warning in brief.warnings)


def test_live_macro_brief_can_use_grounded_llm_response(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    original_overview = macro_service.get_macro_overview

    def fake_overview():
        overview = original_overview()
        observation = MacroObservation(date="2026-04-30", value=3.0, raw_value=3.0, source="test")
        overview.key_indicators[0].observations = [observation]
        overview.key_indicators[0].latest = observation
        overview.key_indicators[0].data_quality = MacroDataQuality(status="ok", provider="test")
        overview.data_quality = MacroDataQuality(status="ok", provider="test")
        return overview

    class Response:
        status_code = 200
        text = "{}"

        def json(self):
            return {"response": "1. 현재 매크로 레짐\n제공된 데이터는 3.0만 보여주며, 주문은 생성하지 않습니다."}

    monkeypatch.setattr(macro_service, "get_macro_overview", fake_overview)
    monkeypatch.setattr("pipelines.macro.ai_brief.httpx.post", lambda *_, **__: Response())
    brief = macro_service.generate_macro_brief(use_llm=True, model="qwen", timeout_s=1)
    assert brief.is_fallback is False
    assert brief.provider.startswith("ollama:")
    assert "3.0" in brief.content


def test_live_macro_brief_rejects_non_korean_llm_response(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    original_overview = macro_service.get_macro_overview

    def fake_overview():
        overview = original_overview()
        observation = MacroObservation(date="2026-04-30", value=3.0, raw_value=3.0, source="test")
        overview.key_indicators[0].observations = [observation]
        overview.key_indicators[0].latest = observation
        overview.key_indicators[0].data_quality = MacroDataQuality(status="ok", provider="test")
        overview.data_quality = MacroDataQuality(status="ok", provider="test")
        return overview

    class Response:
        status_code = 200
        text = "{}"

        def json(self):
            return {"response": "当前宏观环境显示增长稳定，通胀压力有限，资产配置应保持谨慎。3.0"}

    monkeypatch.setattr(macro_service, "get_macro_overview", fake_overview)
    monkeypatch.setattr("pipelines.macro.ai_brief.httpx.post", lambda *_, **__: Response())
    brief = macro_service.generate_macro_brief(use_llm=True, model="qwen", timeout_s=1)
    assert brief.is_fallback is True
    assert any("language guard" in warning.lower() for warning in brief.warnings)


def test_macro_report_endpoint_returns_markdown(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get("/api/v1/macro/report")
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "markdown"
    assert body["content"].startswith("# FinGPT 매크로 리포트")
    assert "## AI 매크로 브리프" in body["content"]
    assert not _contains_chinese_japanese_or_hanja(body["content"])
    assert not _contains_chinese_japanese_or_hanja(" ".join(body["warnings"]))
    assert body["data_quality"]["status"] in {"ok", "partial", "stale", "unavailable"}


def test_factor_regime_classifier_uses_same_signal_contract() -> None:
    series = {
        "GDPC1": _series("GDPC1", -1.0),
        "INDPRO": _series("INDPRO", -2.0),
        "CPIAUCSL": _series("CPIAUCSL", 2.2, change_3=-0.2),
        "CPILFESL": _series("CPILFESL", 2.4, change_3=-0.1),
        "UNRATE": _series("UNRATE", 6.5),
        "ICSA": _series("ICSA", 350000.0),
        "BAMLH0A0HYM2": _series("BAMLH0A0HYM2", 7.5),
        "BAMLC0A0CM": _series("BAMLC0A0CM", 3.0),
        "VIXCLS": _series("VIXCLS", 35.0),
    }
    regime, signals = classify_macro_regime(series, engine="factor")
    assert regime.name in {"recession_risk", "disinflation", "unknown"}
    assert "factor_distance" in regime.scores or regime.name == "unknown"
    assert {signal.name for signal in signals} >= {"growth_signal", "credit_signal"}


def test_macro_regime_api_supports_factor_engine(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get("/api/v1/macro/regime?engine=factor")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "factor"
    assert "data_quality" in body


def test_worldbank_provider_parses_indicator_payload(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [{}, [{"date": "2024", "value": "2.8"}, {"date": "2023", "value": None}]]

    monkeypatch.setattr("pipelines.macro.providers.worldbank.httpx.get", lambda *_, **__: Response())
    result = WorldBankProvider().fetch_series(get_series_definition("WORLD_BANK_GDP"))
    assert result.data_quality.status == "ok"
    assert len(result.observations) == 1
    assert result.observations[0].date == "2024-01-01"
    assert result.observations[0].value == 2.8


def test_oecd_provider_parses_sdmx_json(monkeypatch) -> None:
    payload = {
        "dataSets": [{"observations": {"0:0": [99.1], "0:1": [100.2]}}],
        "structure": {
            "dimensions": {
                "observation": [
                    {"id": "LOCATION", "values": [{"id": "USA"}]},
                    {"id": "TIME_PERIOD", "values": [{"id": "2025-01"}, {"id": "2025-02"}]},
                ]
            }
        },
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr("pipelines.macro.providers.oecd.httpx.get", lambda *_, **__: Response())
    result = OecdProvider().fetch_series(get_series_definition("OECD_CLI"))
    assert result.data_quality.status == "ok"
    assert [item.date for item in result.observations] == ["2025-01-01", "2025-02-01"]


def test_ecos_provider_requires_api_key_without_fake_data(monkeypatch) -> None:
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    result = EcosProvider(api_key="").fetch_series(get_series_definition("ECOS_KR_POLICY_RATE"))
    assert result.observations == []
    assert result.data_quality.status == "unavailable"
    assert "ECOS_API_KEY is missing." in result.data_quality.errors


def test_yahoo_provider_parses_price_proxy(monkeypatch) -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {"Close": [100.0, 101.5], "Adj Close": [99.5, 101.0], "Volume": [10, 20]},
        index=pd.to_datetime(["2026-04-01", "2026-04-02"]),
    )
    monkeypatch.setattr("pipelines.macro.providers.yahoo.yf.download", lambda **_: frame)
    result = YahooFinanceProvider().fetch_series(get_series_definition("YAHOO_GLD"))
    assert result.data_quality.status == "ok"
    assert len(result.observations) == 2
    assert result.observations[-1].value == 101.0
    assert result.observations[-1].metadata["symbol"] == "GLD"


def test_fx_and_commodities_categories_use_enabled_market_proxies(monkeypatch, tmp_path) -> None:
    import pandas as pd

    _reset_macro_runtime(monkeypatch, tmp_path)
    frame = pd.DataFrame(
        {"Close": [100.0, 101.0], "Adj Close": [100.0, 101.0]},
        index=pd.to_datetime(["2026-04-01", "2026-04-02"]),
    )
    monkeypatch.setattr("pipelines.macro.providers.yahoo.yf.download", lambda **_: frame)
    fx = macro_service.get_fx_dollar()
    commodities = macro_service.get_commodities()
    assert fx["count"] >= 1
    assert commodities["count"] >= 2
    assert all(item["provider"] == "yahoo" for item in fx["items"])
    assert all(item["observations"] for item in commodities["items"])
