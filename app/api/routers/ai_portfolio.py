from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import ValidationError

from core.schemas.ai_portfolio import (
    DataActivationRequest,
    GeneratePortfolioRequest,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    RebalanceActionRequest,
    RebalanceCheckRequest,
    ReportGenerateRequest,
    SecDataRefreshRequest,
    SnapshotJobRequest,
)
from pipelines.ai_portfolio import service
from pipelines.ai_portfolio.templates import investment_type_or_none, investment_type_templates


router = APIRouter()


def _not_found(entity: str, key: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity}_not_found:{key}")


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/investment-types")
async def list_investment_types() -> dict[str, Any]:
    items = list(investment_type_templates().values())
    return {"status": "success", "items": [item.model_dump(mode="json") for item in items], "count": len(items)}


@router.get("/investment-types/{investment_type_id}")
async def get_investment_type(investment_type_id: str) -> dict[str, Any]:
    item = investment_type_or_none(investment_type_id)
    if not item:
        raise _not_found("investment_type", investment_type_id)
    return item.model_dump(mode="json")


@router.get("/universes")
async def list_universes() -> dict[str, Any]:
    items = service.list_universes()
    return {"status": "success", "items": items, "count": len(items)}


@router.get("/store/status")
async def get_store_status() -> dict[str, Any]:
    return service.storage_status()


@router.get("/operations")
async def list_operations(limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    items = service.list_operations(limit)
    return {"status": "success", "items": items, "count": len(items)}


@router.post("/operations/hydrate")
async def run_data_activation(request: DataActivationRequest) -> dict[str, Any]:
    try:
        return service.run_data_activation(request)
    except KeyError as exc:
        raise _not_found("policy", str(exc).strip("'"))
    except (ValueError, ValidationError) as exc:
        raise _unprocessable(exc)


@router.post("/operations/snapshots")
async def run_snapshot_job(request: SnapshotJobRequest) -> dict[str, Any]:
    try:
        return service.run_snapshot_job(request)
    except KeyError as exc:
        raise _not_found("policy", str(exc).strip("'"))
    except (ValueError, ValidationError) as exc:
        raise _unprocessable(exc)


@router.post("/operations/sec-refresh")
async def run_sec_data_refresh(request: SecDataRefreshRequest) -> dict[str, Any]:
    try:
        return service.run_sec_data_refresh(request)
    except KeyError as exc:
        raise _not_found("policy", str(exc).strip("'"))
    except (ValueError, ValidationError) as exc:
        raise _unprocessable(exc)


@router.get("/policies")
async def list_policies() -> dict[str, Any]:
    items = service.list_policies()
    return {"status": "success", "items": [item.model_dump(mode="json") for item in items], "count": len(items)}


@router.post("/policies")
async def create_policy(request: PolicyCreateRequest) -> dict[str, Any]:
    try:
        policy = service.create_policy(request)
    except (ValueError, ValidationError) as exc:
        raise _unprocessable(exc)
    return policy.model_dump(mode="json")


@router.get("/policies/{policy_id}")
async def get_policy(policy_id: str) -> dict[str, Any]:
    policy = service.get_policy(policy_id)
    if not policy:
        raise _not_found("policy", policy_id)
    return policy.model_dump(mode="json")


@router.put("/policies/{policy_id}")
async def update_policy(policy_id: str, request: PolicyUpdateRequest) -> dict[str, Any]:
    try:
        policy = service.update_policy(policy_id, request)
    except KeyError:
        raise _not_found("policy", policy_id)
    except (ValueError, ValidationError) as exc:
        raise _unprocessable(exc)
    return policy.model_dump(mode="json")


@router.post("/policies/{policy_id}/activate")
async def activate_policy(policy_id: str) -> dict[str, Any]:
    try:
        policy = service.set_policy_status(policy_id, "active")
    except KeyError:
        raise _not_found("policy", policy_id)
    return policy.model_dump(mode="json")


@router.post("/policies/{policy_id}/deactivate")
async def deactivate_policy(policy_id: str) -> dict[str, Any]:
    try:
        policy = service.set_policy_status(policy_id, "inactive")
    except KeyError:
        raise _not_found("policy", policy_id)
    return policy.model_dump(mode="json")


@router.post("/generate")
async def generate_portfolio(request: GeneratePortfolioRequest) -> dict[str, Any]:
    try:
        response = service.generate_portfolio(request)
    except KeyError as exc:
        raise _not_found("policy", str(exc).strip("'"))
    except (ValueError, ValidationError) as exc:
        raise _unprocessable(exc)
    return response.model_dump(mode="json")


@router.get("/recommendations/{policy_id}")
async def list_recommendations(policy_id: str) -> dict[str, Any]:
    items = service.list_recommendations(policy_id)
    return {"status": "success", "items": [item.model_dump(mode="json") for item in items], "count": len(items)}


@router.get("/recommendations")
async def list_recommendations_query(policy_id: str = Query(...)) -> dict[str, Any]:
    return await list_recommendations(policy_id)


@router.get("/recommendations/detail/{recommendation_id}")
async def get_recommendation(recommendation_id: str) -> dict[str, Any]:
    item = service.get_recommendation(recommendation_id)
    if not item:
        raise _not_found("recommendation", recommendation_id)
    return item.model_dump(mode="json")


@router.get("/recommendations/{policy_id}/diff")
async def get_recommendation_diff(policy_id: str) -> dict[str, Any]:
    if not service.get_policy(policy_id):
        raise _not_found("policy", policy_id)
    return service.recommendation_diff(policy_id)


@router.get("/performance/{policy_id}")
async def list_performance(policy_id: str) -> dict[str, Any]:
    if not service.get_policy(policy_id):
        raise _not_found("policy", policy_id)
    items = service.list_snapshots(policy_id)
    return {"status": "success", "items": [item.model_dump(mode="json") for item in items], "count": len(items)}


@router.post("/performance/{policy_id}/snapshot")
async def create_snapshot(policy_id: str) -> dict[str, Any]:
    try:
        snapshot = service.create_snapshot(policy_id)
    except KeyError:
        raise _not_found("policy", policy_id)
    return snapshot.model_dump(mode="json")


@router.post("/rebalance/check")
async def check_rebalance(request: RebalanceCheckRequest) -> dict[str, Any]:
    try:
        signal = service.check_rebalance(request.policy_id, request.current_weights)
    except KeyError:
        raise _not_found("policy", request.policy_id)
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"rebalance_required": signal.rebalance_required, "signal": signal.model_dump(mode="json")}


@router.get("/rebalance/signals/{policy_id}")
async def list_rebalance_signals(policy_id: str) -> dict[str, Any]:
    items = service.list_signals(policy_id)
    return {"status": "success", "items": [item.model_dump(mode="json") for item in items], "count": len(items)}


@router.get("/rebalance/signals")
async def list_rebalance_signals_query(policy_id: str = Query(...)) -> dict[str, Any]:
    return await list_rebalance_signals(policy_id)


@router.post("/rebalance/{signal_id}/approve")
async def approve_rebalance(signal_id: str, request: RebalanceActionRequest | None = Body(default=None)) -> dict[str, Any]:
    try:
        return service.update_signal_status(signal_id, "approved", request).model_dump(mode="json")
    except KeyError:
        raise _not_found("rebalance_signal", signal_id)


@router.post("/rebalance/{signal_id}/reject")
async def reject_rebalance(signal_id: str, request: RebalanceActionRequest | None = Body(default=None)) -> dict[str, Any]:
    try:
        return service.update_signal_status(signal_id, "rejected", request).model_dump(mode="json")
    except KeyError:
        raise _not_found("rebalance_signal", signal_id)


@router.post("/rebalance/{signal_id}/defer")
async def defer_rebalance(signal_id: str, request: RebalanceActionRequest | None = Body(default=None)) -> dict[str, Any]:
    try:
        return service.update_signal_status(signal_id, "deferred", request).model_dump(mode="json")
    except KeyError:
        raise _not_found("rebalance_signal", signal_id)


@router.post("/rebalance/signals/{signal_id}/{action}")
async def update_rebalance_action(signal_id: str, action: str, request: RebalanceActionRequest | None = Body(default=None)) -> dict[str, Any]:
    if action == "approve":
        return await approve_rebalance(signal_id, request)
    if action == "reject":
        return await reject_rebalance(signal_id, request)
    if action == "defer":
        return await defer_rebalance(signal_id, request)
    raise HTTPException(status_code=422, detail=f"unsupported_rebalance_action:{action}")


@router.post("/reports/generate")
async def generate_report(request: ReportGenerateRequest) -> dict[str, Any]:
    try:
        return service.generate_report(request)
    except KeyError:
        raise _not_found("policy", request.policy_id)


@router.post("/reports")
async def generate_report_alias(request: ReportGenerateRequest) -> dict[str, Any]:
    report = await generate_report(request)
    if "markdown" in report and "content" not in report:
        report = {**report, "content": report["markdown"]}
    return report


@router.get("/reports/{policy_id}")
async def list_reports(policy_id: str) -> dict[str, Any]:
    return {"status": "success", "items": service.list_reports(policy_id)}


@router.get("/reports")
async def list_reports_query(policy_id: str = Query(...)) -> dict[str, Any]:
    return await list_reports(policy_id)


@router.get("/history/{policy_id}")
async def list_history(policy_id: str) -> dict[str, Any]:
    items = service.list_history(policy_id)
    return {"status": "success", "items": [item.model_dump(mode="json") for item in items], "count": len(items)}


@router.get("/history")
async def list_history_query(policy_id: str = Query(...)) -> dict[str, Any]:
    return await list_history(policy_id)
