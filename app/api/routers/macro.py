from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.schemas.macro import MacroBriefRequest
from pipelines.macro import macro_service as service


router = APIRouter(tags=["macro"])


def _not_found(entity: str, key: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity}_not_found:{key}")


@router.get("/series")
async def list_series(include_disabled: bool = False) -> dict[str, Any]:
    return service.list_macro_series(include_disabled=include_disabled)


@router.get("/series/{series_id}")
async def get_series(series_id: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    try:
        return service.get_macro_series(series_id, start_date=start_date, end_date=end_date).model_dump(mode="json")
    except KeyError:
        raise _not_found("macro_series", series_id)


@router.get("/overview")
async def get_overview(engine: str = Query(default="rules", pattern="^(rules|factor)$")) -> dict[str, Any]:
    return service.get_macro_overview(regime_engine=engine).model_dump(mode="json")


@router.get("/category/{category}")
async def get_category(category: str) -> dict[str, Any]:
    try:
        return service.get_macro_category(category)
    except KeyError:
        raise _not_found("macro_category", category)


@router.get("/interest-rates")
async def get_interest_rates() -> dict[str, Any]:
    return service.get_interest_rates()


@router.get("/inflation")
async def get_inflation() -> dict[str, Any]:
    return service.get_inflation()


@router.get("/growth-labor")
async def get_growth_labor() -> dict[str, Any]:
    return service.get_growth_labor()


@router.get("/yield-curve")
async def get_yield_curve() -> dict[str, Any]:
    return service.get_yield_curve()


@router.get("/liquidity-credit")
async def get_liquidity_credit() -> dict[str, Any]:
    return service.get_macro_category("liquidity_credit")


@router.get("/fx-dollar")
async def get_fx_dollar() -> dict[str, Any]:
    return service.get_fx_dollar()


@router.get("/commodities")
async def get_commodities() -> dict[str, Any]:
    return service.get_commodities()


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
