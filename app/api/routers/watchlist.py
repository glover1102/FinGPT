from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.schemas.request import AnalysisRequest
from pipelines.orchestration.research_pipeline import run_pipeline_async
from pipelines.watchlist import store as watchlist_store
from pipelines.watchlist.scheduler import get_scheduler as get_watchlist_scheduler


router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


@router.get("")
async def watchlist_list() -> dict[str, Any]:
    items = [item.to_dict() for item in watchlist_store.list_items()]
    return {"items": items, "scheduler": get_watchlist_scheduler().status()}


@router.post("")
async def watchlist_create(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        item = watchlist_store.upsert_item(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item.to_dict()


@router.put("/{item_id}")
async def watchlist_update(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        item = watchlist_store.upsert_item(payload, item_id=item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item.to_dict()


@router.delete("/{item_id}")
async def watchlist_delete(item_id: str) -> dict[str, Any]:
    dropped = watchlist_store.delete_item(item_id)
    if not dropped:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    return {"deleted": True, "id": item_id}


@router.post("/{item_id}/run")
async def watchlist_run_now(item_id: str) -> dict[str, Any]:
    item = watchlist_store.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    try:
        request = AnalysisRequest(
            ticker=item.ticker,
            question=item.question,
            sources=list(item.sources),
            lookback_days=item.lookback_days,
            top_k=item.top_k,
            model=item.model,
        )
        response = await run_pipeline_async(request)
        watchlist_store.mark_run(item.id, status=response.status, error=response.error_metadata)
        current = watchlist_store.get_item(item_id)
        return {"item": current.to_dict() if current else None, "response": response.model_dump(mode="json")}
    except Exception as exc:
        watchlist_store.mark_run(item.id, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
