from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.schemas.macro import MacroBriefRequest, MacroRefreshRequest
from pipelines.data_mart.jobs.update_macro_daily import update_macro_platform_data
from pipelines.data_mart.scheduler import get_scheduler as get_data_mart_scheduler
from pipelines.macro import macro_service as service


router = APIRouter(tags=["macro"])


def _not_found(entity: str, key: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity}_not_found:{key}")


def _update_result_payload(result) -> dict[str, Any]:
    return {
        "status": result.status,
        "run_id": result.run_id,
        "market": result.market,
        "provider": result.provider,
        "rows_inserted": result.rows_inserted,
        "rows_updated": result.rows_updated,
        "error_message": result.error_message,
        "providers": [
            {
                "provider": item.provider,
                "status": item.status,
                "rows": item.rows,
                "error": item.error,
                "detail": item.detail,
            }
            for item in result.providers
        ],
    }


@router.get("/series")
async def list_series(include_disabled: bool = False) -> dict[str, Any]:
    return service.list_macro_series(include_disabled=include_disabled)


@router.get("/series/search")
async def search_series(
    q: str = Query(default=""),
    limit: int = Query(default=12, ge=1, le=50),
    include_disabled: bool = False,
) -> dict[str, Any]:
    return service.search_macro_series(q, limit=limit, include_disabled=include_disabled).model_dump(mode="json")


@router.get("/series/{series_id}")
async def get_series(series_id: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    try:
        return service.get_macro_series(series_id, start_date=start_date, end_date=end_date).model_dump(mode="json")
    except KeyError:
        raise _not_found("macro_series", series_id)


@router.get("/series/{series_id}/detail")
async def get_series_detail(
    series_id: str,
    observation_limit: int = Query(default=240, ge=0, le=5000),
) -> dict[str, Any]:
    try:
        return service.get_macro_series_detail(series_id, observation_limit=observation_limit).model_dump(mode="json")
    except KeyError:
        raise _not_found("macro_series", series_id)


@router.get("/overview")
async def get_overview(
    engine: str = Query(default="rules", pattern="^(rules|factor)$"),
    compact: bool = False,
    observation_limit: int = Query(default=120, ge=0, le=1000),
) -> dict[str, Any]:
    overview = service.get_macro_overview(regime_engine=engine)
    if compact:
        return service.compact_macro_payload(overview, observation_limit=observation_limit)
    return overview.model_dump(mode="json")


@router.get("/category/{category}")
async def get_category(
    category: str,
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    try:
        payload = service.get_macro_category(category)
        return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload
    except KeyError:
        raise _not_found("macro_category", category)


@router.get("/interest-rates")
async def get_interest_rates(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_interest_rates()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/inflation")
async def get_inflation(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_inflation()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/growth-labor")
async def get_growth_labor(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_growth_labor()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/housing-consumer")
async def get_housing_consumer(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_housing_consumer()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/yield-curve")
async def get_yield_curve(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_yield_curve()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/liquidity-credit")
async def get_liquidity_credit(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_macro_category("liquidity_credit")
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/financial-conditions")
async def get_financial_conditions(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_financial_conditions()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/fx-dollar")
async def get_fx_dollar(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_fx_dollar()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/commodities")
async def get_commodities(
    compact: bool = False,
    observation_limit: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    payload = service.get_commodities()
    return service.compact_macro_payload(payload, observation_limit=observation_limit) if compact else payload


@router.get("/regime")
async def get_regime(engine: str = Query(default="rules", pattern="^(rules|factor)$")) -> dict[str, Any]:
    return service.get_macro_regime(engine=engine)


@router.get("/asset-impact")
async def get_asset_impact() -> dict[str, Any]:
    return service.get_asset_impact()


@router.get("/portfolio-policy-hints")
async def get_portfolio_policy_hints() -> dict[str, Any]:
    return service.get_portfolio_policy_hints().model_dump(mode="json")


@router.get("/research-context")
async def get_research_context(ticker: str | None = Query(default=None)) -> dict[str, Any]:
    return service.get_macro_research_context(ticker=ticker).model_dump(mode="json")


@router.post("/brief")
async def post_brief(request: MacroBriefRequest | None = None) -> dict[str, Any]:
    request = request or MacroBriefRequest()
    return service.generate_macro_brief(
        include_prompt=request.include_prompt,
        use_llm=request.use_llm,
        model=request.model,
        timeout_s=request.timeout_s,
    ).model_dump(mode="json")


@router.get("/report")
async def get_report() -> dict[str, Any]:
    return service.generate_macro_report().model_dump(mode="json")


@router.get("/data-quality")
async def get_data_quality() -> dict[str, Any]:
    return service.get_data_quality()


@router.get("/providers")
async def get_providers() -> dict[str, Any]:
    return service.get_provider_metadata()


@router.get("/countries")
async def get_countries() -> dict[str, Any]:
    return service.get_country_metadata()


@router.get("/health")
async def get_health() -> dict[str, Any]:
    return service.get_health()


@router.post("/refresh")
async def post_refresh(request: MacroRefreshRequest | None = None) -> dict[str, Any]:
    request = request or MacroRefreshRequest()
    try:
        result = await asyncio.to_thread(
            update_macro_platform_data,
            request.series_ids or None,
            providers=request.providers or None,
            include_disabled=request.include_disabled,
            start_date=request.start_date,
            end_date=request.end_date,
            lookback_days=request.lookback_days,
            dry_run=request.dry_run,
        )
    except KeyError as exc:
        raise _not_found("macro_series", str(exc).strip("'"))
    service.clear_macro_caches()
    return {
        "status": result.status,
        "refresh": _update_result_payload(result),
        "data_quality": service.get_data_quality().get("data_quality"),
    }


@router.get("/refresh/status")
async def get_refresh_status() -> dict[str, Any]:
    return {
        "status": "ok",
        "scheduler": get_data_mart_scheduler().status(),
        "data_quality": service.get_data_quality().get("data_quality"),
    }
