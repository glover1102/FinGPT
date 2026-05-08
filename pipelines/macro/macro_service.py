from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.config.settings import load_settings
from core.schemas.macro import MacroBriefResponse, MacroDataQuality, MacroOverview, MacroReportResponse, MacroSeriesResponse
from pipelines.macro.ai_brief import generate_brief
from pipelines.macro.asset_impact import get_asset_impacts
from pipelines.macro.data_quality import aggregate_quality, evaluate_series_quality
from pipelines.macro.portfolio_hints import get_portfolio_policy_hint
from pipelines.macro.providers.ecos import EcosProvider
from pipelines.macro.providers.fred import FredProvider
from pipelines.macro.providers.oecd import OecdProvider
from pipelines.macro.providers.storage import DataMartMacroProvider
from pipelines.macro.providers.unavailable import UnavailableProvider
from pipelines.macro.providers.worldbank import WorldBankProvider
from pipelines.macro.providers.yahoo import YahooFinanceProvider
from pipelines.macro.regime_engine import classify_macro_regime
from pipelines.macro.research_context import get_research_context
from pipelines.macro.series_registry import (
    category_names,
    country_names,
    get_series_definition,
    list_macro_series as _list_macro_series,
    normalize_category,
    provider_names,
    series_by_category,
)
from pipelines.macro.transforms import apply_transform, compute_changes


KEY_INDICATOR_IDS = [
    "FEDFUNDS",
    "DGS3MO",
    "DGS2",
    "DGS10",
    "DGS30",
    "T10Y2Y",
    "T10Y3M",
    "DFII10",
    "CPIAUCSL",
    "CPILFESL",
    "PCEPI",
    "PCEPILFE",
    "UNRATE",
    "GDPC1",
    "VIXCLS",
]

REGIME_INPUT_IDS = [
    "FEDFUNDS",
    "DGS2",
    "DFII10",
    "CPIAUCSL",
    "CPILFESL",
    "PCEPI",
    "PCEPILFE",
    "T5YIE",
    "T10YIE",
    "PPIACO",
    "GDPC1",
    "INDPRO",
    "RSAFS",
    "UMCSENT",
    "UNRATE",
    "PAYEMS",
    "ICSA",
    "JTSJOL",
    "M2SL",
    "WALCL",
    "RRPONTSYD",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "VIXCLS",
]

_SERIES_CACHE_TTL_S = 300.0
_OVERVIEW_CACHE_TTL_S = 120.0
_SERIES_CACHE: dict[tuple[str, str, str | None, str | None], tuple[float, MacroSeriesResponse]] = {}
_OVERVIEW_CACHE: dict[str, tuple[float, MacroOverview]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _cache_time() -> float:
    return datetime.now(timezone.utc).timestamp()


def _cache_key() -> str:
    settings = load_settings()
    provider_state = ";".join(f"{name}:{int(provider.is_available())}" for name, provider in _live_providers().items())
    return f"{settings.data_mart_db_path}|{provider_state}"


def _live_providers():
    return {
        "fred": FredProvider(),
        "ecos": EcosProvider(),
        "oecd": OecdProvider(),
        "worldbank": WorldBankProvider(),
        "yahoo": YahooFinanceProvider(),
    }


def _fetch_raw_series(definition, *, start_date: str | None = None, end_date: str | None = None):
    storage = DataMartMacroProvider()
    storage_result = storage.fetch_series(definition, start_date=start_date, end_date=end_date)
    if storage_result.observations:
        return storage_result
    provider = _live_providers().get(str(definition.provider or "").lower())
    if provider is not None and provider.supports(definition):
        return provider.fetch_series(definition, start_date=start_date, end_date=end_date)
    return UnavailableProvider("No cached data and live provider is not configured.").fetch_series(
        definition,
        start_date=start_date,
        end_date=end_date,
    )


def list_macro_series(*, include_disabled: bool = False) -> dict[str, Any]:
    items = _list_macro_series(include_disabled=include_disabled)
    return {
        "status": "success",
        "count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
        "data_quality": MacroDataQuality(status="ok", provider="registry", notes=["Registry metadata only."]).model_dump(mode="json"),
    }


def get_macro_series(series_id: str, *, start_date: str | None = None, end_date: str | None = None) -> MacroSeriesResponse:
    definition = get_series_definition(series_id)
    cache_key = (_cache_key(), definition.series_id, start_date, end_date)
    cached = _SERIES_CACHE.get(cache_key)
    now = _cache_time()
    if cached and now - cached[0] <= _SERIES_CACHE_TTL_S:
        return cached[1].model_copy(deep=True)
    raw_result = _fetch_raw_series(definition, start_date=start_date, end_date=end_date)
    observations, transform_errors = apply_transform(definition, raw_result.observations)
    quality = evaluate_series_quality(definition, observations, raw_result.data_quality, transform_errors=transform_errors)
    latest = observations[-1] if observations else None
    response = MacroSeriesResponse(
        series_id=definition.series_id,
        display_name=definition.display_name,
        category=definition.category,
        unit=definition.unit,
        frequency=definition.frequency,
        provider=raw_result.provider,
        observations=observations,
        latest=latest,
        changes=compute_changes(observations),
        data_quality=quality,
    )
    _SERIES_CACHE[cache_key] = (now, response.model_copy(deep=True))
    return response


def _series_map(series_ids: list[str] | None = None) -> dict[str, MacroSeriesResponse]:
    ids = series_ids or [item.series_id for item in _list_macro_series()]
    out: dict[str, MacroSeriesResponse] = {}
    for series_id in ids:
        try:
            out[series_id] = get_macro_series(series_id)
        except KeyError:
            continue
    return out


def get_macro_category(category: str) -> dict[str, Any]:
    slug = normalize_category(category)
    definitions = series_by_category(slug)
    if not definitions:
        raise KeyError(slug)
    items = [get_macro_series(item.series_id) for item in definitions]
    return {
        "status": "success",
        "category": slug,
        "count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
        "data_quality": aggregate_quality(items, provider="macro_category").model_dump(mode="json"),
    }


def get_interest_rates() -> dict[str, Any]:
    return get_macro_category("interest_rates")


def get_inflation() -> dict[str, Any]:
    return get_macro_category("inflation")


def get_growth_labor() -> dict[str, Any]:
    items = [get_macro_series(item.series_id) for item in [*series_by_category("growth"), *series_by_category("labor")]]
    return {
        "status": "success",
        "category": "growth_labor",
        "count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
        "data_quality": aggregate_quality(items, provider="macro_category").model_dump(mode="json"),
    }


def get_yield_curve() -> dict[str, Any]:
    ids = ["DGS3MO", "DGS2", "DGS10", "DGS30", "T10Y2Y", "T10Y3M", "DFII10"]
    items = [get_macro_series(item) for item in ids]
    return {
        "status": "success",
        "category": "yield_curve",
        "count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
        "data_quality": aggregate_quality(items, provider="macro_category").model_dump(mode="json"),
    }


def _empty_category(category: str, missing_series: list[str], note: str) -> dict[str, Any]:
    return {
        "status": "success",
        "category": category,
        "count": 0,
        "items": [],
        "data_quality": MacroDataQuality(
            status="unavailable",
            provider="registry",
            missing_series=missing_series,
            notes=[note],
        ).model_dump(mode="json"),
    }


def get_fx_dollar() -> dict[str, Any]:
    try:
        return get_macro_category("fx_dollar")
    except KeyError:
        return _empty_category("fx_dollar", ["ECOS_USDKRW", "YAHOO_DXY_PROXY"], "FX/dollar provider entries are not enabled; no fake data returned.")


def get_commodities() -> dict[str, Any]:
    try:
        return get_macro_category("commodities")
    except KeyError:
        return _empty_category("commodities", ["YAHOO_GLD", "YAHOO_USO"], "Commodity provider entries are not enabled; no fake data returned.")


def get_macro_overview(*, regime_engine: str = "rules") -> MacroOverview:
    engine = str(regime_engine or "rules").strip().lower()
    cache_key = f"{_cache_key()}|engine:{engine}"
    now = _cache_time()
    cached = _OVERVIEW_CACHE.get(cache_key)
    if cached and now - cached[0] <= _OVERVIEW_CACHE_TTL_S:
        return cached[1].model_copy(deep=True)
    needed = sorted(set([*KEY_INDICATOR_IDS, *REGIME_INPUT_IDS]))
    series = _series_map(needed)
    regime, signals = classify_macro_regime(series, engine=engine)
    key_indicators = [series[item] for item in KEY_INDICATOR_IDS if item in series]
    quality = aggregate_quality(list(series.values()), provider="macro_overview")
    overview = MacroOverview(
        as_of=_now_iso(),
        key_indicators=key_indicators,
        signals=signals,
        regime=regime,
        asset_impact_summary=get_asset_impacts(regime, signals),
        data_quality=quality,
    )
    _OVERVIEW_CACHE[cache_key] = (now, overview.model_copy(deep=True))
    return overview


def get_macro_regime(*, engine: str = "rules") -> dict[str, Any]:
    selected_engine = str(engine or "rules").strip().lower()
    if selected_engine not in {"rules", "factor"}:
        selected_engine = "rules"
    overview = get_macro_overview(regime_engine=selected_engine)
    return {
        "status": "success",
        "engine": selected_engine,
        "regime": overview.regime.model_dump(mode="json"),
        "signals": [item.model_dump(mode="json") for item in overview.signals],
        "data_quality": overview.data_quality.model_dump(mode="json"),
    }


def get_asset_impact() -> dict[str, Any]:
    overview = get_macro_overview()
    impacts = get_asset_impacts(overview.regime, overview.signals)
    return {
        "status": "success",
        "items": [item.model_dump(mode="json") for item in impacts],
        "count": len(impacts),
        "data_quality": overview.data_quality.model_dump(mode="json"),
    }


def get_portfolio_policy_hints():
    overview = get_macro_overview()
    return get_portfolio_policy_hint(overview.regime, overview.data_quality)


def get_macro_research_context(ticker: str | None = None):
    return get_research_context(get_macro_overview(), ticker=ticker)


def generate_macro_brief(
    *,
    include_prompt: bool = False,
    use_llm: bool = False,
    model: str | None = None,
    timeout_s: float = 45.0,
) -> MacroBriefResponse:
    return generate_brief(
        get_macro_overview(),
        include_prompt=include_prompt,
        use_llm=use_llm,
        model=model,
        timeout_s=timeout_s,
    )


def generate_macro_report() -> MacroReportResponse:
    overview = get_macro_overview()
    impacts = get_asset_impacts(overview.regime, overview.signals)
    hint = get_portfolio_policy_hint(overview.regime, overview.data_quality)
    context = get_research_context(overview)
    brief = generate_brief(overview, include_prompt=False, use_llm=False)
    generated_at = _now_iso()
    warnings = [
        "리포트는 구조화된 Macro payload와 규칙 기반 폴백 브리프에서 생성됩니다.",
        "포트폴리오 정책 힌트는 자문 전용이며 주문을 생성하지 않습니다.",
    ]
    if overview.data_quality.status != "ok":
        warnings.append(f"매크로 데이터 품질은 {overview.data_quality.status}이며 누락/지연 데이터는 불확실성으로 남습니다.")
    content = "\n".join(
        [
            "# FinGPT 매크로 리포트",
            "",
            f"- 생성 시각: {generated_at}",
            f"- 데이터 품질: {overview.data_quality.status}",
            f"- 레짐: {overview.regime.display_name} ({overview.regime.name})",
            f"- 신뢰도: {overview.regime.confidence:.2f}",
            f"- 위험 수준: {overview.regime.risk_level}",
            "",
            "## 핵심 지표",
            "",
            "| 시계열 | 최근값 | 날짜 | 품질 | 공급자 |",
            "|---|---:|---|---|---|",
            *[
                (
                    f"| {item.series_id} - {item.display_name} | "
                    f"{item.latest.value if item.latest and item.latest.value is not None else '사용 불가'} {item.unit} | "
                    f"{item.latest.date if item.latest else '사용 불가'} | "
                    f"{item.data_quality.status} | {item.provider} |"
                )
                for item in overview.key_indicators
            ],
            "",
            "## 신호",
            "",
            "| 신호 | 값 | 점수 | 신뢰도 | 증거 |",
            "|---|---|---:|---:|---|",
            *[
                f"| {item.name} | {item.value} | {item.score:.1f} | {item.confidence:.2f} | {'; '.join(item.evidence[:3]) or '데이터 부족'} |"
                for item in overview.signals
            ],
            "",
            "## 레짐 해석",
            "",
            overview.regime.interpretation or "입력이 부족해 레짐 해석을 보류합니다.",
            "",
            "## 자산군 영향",
            "",
            "| 자산군 | 영향 | 신뢰도 | 근거 | 핵심 리스크 |",
            "|---|---|---:|---|---|",
            *[
                f"| {item.asset_class} | {item.impact} | {item.confidence:.2f} | {item.reason} | {'; '.join(item.key_risks) or '-'} |"
                for item in impacts
            ],
            "",
            "## 포트폴리오 정책 힌트",
            "",
            f"- 자문 전용: {hint.advisory_only}",
            f"- 주식 편향: {hint.equity_bias}",
            f"- 채권 편향: {hint.bond_bias}",
            f"- 현금 편향: {hint.cash_bias}",
            f"- 듀레이션 편향: {hint.duration_bias}",
            f"- 신용 편향: {hint.credit_bias}",
            f"- 위험 수준: {hint.risk_level}",
            f"- 리밸런싱 주의: {hint.rebalance_attention}",
            f"- 설명: {hint.explanation}",
            "",
            "## 리서치 맥락",
            "",
            f"- 티커 관련 항목: {', '.join(sorted(context.ticker_relevance.keys()))}",
            f"- 데이터 품질 경고: {', '.join(context.data_quality_warnings[:20]) or '없음'}",
            "",
            "## AI 매크로 브리프",
            "",
            brief.content,
            "",
            "## 데이터 품질",
            "",
            f"- 누락 시계열: {', '.join(overview.data_quality.missing_series) or '없음'}",
            f"- 지연 시계열: {', '.join(overview.data_quality.stale_series) or '없음'}",
            f"- 오류: {', '.join(overview.data_quality.errors) or '없음'}",
            f"- 메모: {', '.join(overview.data_quality.notes[:20]) or '없음'}",
        ]
    )
    return MacroReportResponse(
        status="success",
        generated_at=generated_at,
        filename=f"fingpt_macro_report_{generated_at.replace(':', '').replace('-', '')}.md",
        content=content,
        data_quality=overview.data_quality,
        warnings=warnings,
    )


def get_data_quality() -> dict[str, Any]:
    overview = get_macro_overview()
    return {
        "status": overview.data_quality.status,
        "data_quality": overview.data_quality.model_dump(mode="json"),
        "series": [
            {
                "series_id": item.series_id,
                "display_name": item.display_name,
                "status": item.data_quality.status,
                "latest_date": item.latest.date if item.latest else None,
                "provider": item.provider,
                "errors": item.data_quality.errors,
                "notes": item.data_quality.notes,
            }
            for item in overview.key_indicators
        ],
    }


def get_provider_metadata() -> dict[str, Any]:
    storage = DataMartMacroProvider()
    live = _live_providers()
    return {
        "status": "success",
        "providers": [
            storage.health_check(),
            *[provider.health_check() for provider in live.values()],
            UnavailableProvider("fallback").health_check(),
        ],
        "registry_providers": provider_names(include_disabled=True),
        "data_quality": MacroDataQuality(status="ok", provider="registry", notes=["Provider metadata only."]).model_dump(mode="json"),
    }


def get_country_metadata() -> dict[str, Any]:
    return {
        "status": "success",
        "countries": country_names(include_disabled=True),
        "data_quality": MacroDataQuality(status="ok", provider="registry", notes=["Country metadata only."]).model_dump(mode="json"),
    }


def get_health() -> dict[str, Any]:
    storage = DataMartMacroProvider()
    live = _live_providers()
    return {
        "status": "ok",
        "registry_series": len(_list_macro_series()),
        "categories": category_names(),
        "data_mart_available": storage.is_available(),
        "providers": {name: provider.is_available() for name, provider in live.items()},
        "data_quality": MacroDataQuality(status="ok", provider="macro_health").model_dump(mode="json"),
    }
