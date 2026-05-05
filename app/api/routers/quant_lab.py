from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.schemas.quant import (
    QuantBacktestRequest,
    QuantBacktestResponse,
    QuantFeaturePreviewRequest,
    QuantFeaturePreviewResponse,
    QuantSignalGenerateRequest,
    QuantSignalGenerateResponse,
)
from pipelines.orchestration.quant_lab_pipeline import (
    ARTIFACT_ROOT,
    cleanup_backtest_exports,
    cleanup_cross_run_exports,
    compare_backtest_replay,
    export_storage_report,
    export_backtest_artifacts,
    feature_preview,
    load_backtest_artifact,
    list_backtest_runs,
    list_backtest_exports,
    list_replay_reports,
    preview_backtest_export_cleanup,
    preview_cross_run_export_cleanup,
    quant_config,
    run_quant_backtest,
    signal_preview,
    verify_backtest_export,
)
from pipelines.adapters.qlib_adapter import qlib_export_preview, qlib_status
from pipelines.strategies.registry import get_strategy, list_strategies
from pipelines.strategies.storage import delete_strategy, load_strategy, migrate_strategy, save_strategy, validate_strategy


router = APIRouter(prefix="/api/v1/quant", tags=["quant_lab"])


@router.get("/config")
async def get_quant_config() -> dict[str, Any]:
    return quant_config()


@router.get("/qlib/status")
async def get_qlib_status() -> dict[str, Any]:
    return qlib_status()


@router.post("/qlib/export")
async def post_qlib_export_preview(payload: dict[str, Any]) -> dict[str, Any]:
    tickers = payload.get("tickers") or []
    if isinstance(tickers, str):
        tickers = tickers.replace(",", " ").split()
    return qlib_export_preview(
        tickers=list(tickers),
        start_date=payload.get("start_date"),
        end_date=payload.get("end_date"),
        provider_uri=payload.get("provider_uri"),
        dry_run=bool(payload.get("dry_run", True)),
    )


@router.post("/features/preview", response_model=QuantFeaturePreviewResponse)
async def post_feature_preview(request: QuantFeaturePreviewRequest) -> QuantFeaturePreviewResponse:
    return feature_preview(request)


@router.post("/signals/generate", response_model=QuantSignalGenerateResponse)
async def post_signal_generate(request: QuantSignalGenerateRequest) -> QuantSignalGenerateResponse:
    return signal_preview(request)


@router.post("/backtest", response_model=QuantBacktestResponse)
async def post_quant_backtest(request: QuantBacktestRequest) -> QuantBacktestResponse:
    return run_quant_backtest(request)


@router.get("/backtests")
async def get_quant_backtests(limit: int = 20) -> dict[str, Any]:
    return list_backtest_runs(limit=limit)


@router.get("/exports/storage")
async def get_quant_export_storage(limit: int = 20, stale_after_days: int = 30) -> dict[str, Any]:
    return export_storage_report(limit=limit, stale_after_days=stale_after_days)


@router.get("/exports/cleanup-preview")
async def get_quant_cross_run_export_cleanup_preview(
    keep_last_exports: int = 5,
    stale_after_days: int = 30,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        return preview_cross_run_export_cleanup(
            keep_last_exports=keep_last_exports,
            stale_after_days=stale_after_days,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/exports/cleanup")
async def post_quant_cross_run_export_cleanup(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = payload or {}
        candidate_ids = payload.get("candidate_ids")
        if candidate_ids is None:
            candidate_ids = payload.get("candidates")
        return cleanup_cross_run_exports(
            preview_id=str(payload.get("preview_id") or ""),
            candidate_ids=candidate_ids if isinstance(candidate_ids, list) else [],
            keep_last_exports=payload.get("keep_last_exports", 5),
            stale_after_days=payload.get("stale_after_days", 30),
            limit=payload.get("limit", 100),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/backtest/{run_id}")
async def get_quant_backtest(run_id: str) -> dict[str, Any]:
    return _load_or_404(run_id, "manifest")


@router.get("/backtest/{run_id}/bundle")
async def get_quant_backtest_bundle(run_id: str) -> dict[str, Any]:
    manifest = _load_or_404(run_id, "manifest")
    return {
        "status": "success",
        "run_id": manifest.get("run_id") or run_id,
        "manifest": manifest,
        "config": _load_or_empty(run_id, "config", default={}),
        "metrics": _load_or_empty(run_id, "metrics", default={}),
        "diagnostics": _load_or_empty(run_id, "diagnostics", default={}),
        "equity_curve": _load_or_empty(run_id, "equity_curve", default=[]),
        "drawdown_curve": _load_or_empty(run_id, "drawdown_curve", default=[]),
        "trades": _load_or_empty(run_id, "trades", default=[]),
        "signals": _load_or_empty(run_id, "signals", default=[]),
        "weights": _load_or_empty(run_id, "weights", default=[]),
        "replay_report": _load_or_empty(run_id, "replay_report", default={}),
        "replay_reports": _replay_reports_or_empty(run_id),
    }


@router.post("/backtest/{run_id}/replay")
async def post_quant_backtest_replay(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = payload or {}
        return compare_backtest_replay(
            run_id,
            tolerances=payload.get("tolerances") if isinstance(payload.get("tolerances"), dict) else None,
            persist_report=bool(payload.get("persist_report", True)),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest artifact not found: {run_id}")


@router.get("/backtest/{run_id}/replay-reports")
async def get_quant_backtest_replay_reports(run_id: str, limit: int = 20) -> dict[str, Any]:
    try:
        return list_replay_reports(run_id, limit=limit)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest artifact not found: {run_id}")


@router.post("/backtest/{run_id}/export")
async def post_quant_backtest_export(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = payload or {}
        return export_backtest_artifacts(
            run_id,
            export_format=str(payload.get("format") or "jsonl"),
            keep_last_exports=payload.get("keep_last_exports"),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest artifact not found: {run_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/backtest/{run_id}/exports")
async def get_quant_backtest_exports(run_id: str, limit: int = 20) -> dict[str, Any]:
    try:
        return list_backtest_exports(run_id, limit=limit)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest artifact not found: {run_id}")


@router.get("/backtest/{run_id}/exports/cleanup-preview")
async def get_quant_backtest_export_cleanup_preview(run_id: str, keep_last_exports: int = 5) -> dict[str, Any]:
    try:
        return preview_backtest_export_cleanup(run_id, keep_last_exports=keep_last_exports)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest export not found: {run_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/backtest/{run_id}/exports/cleanup")
async def post_quant_backtest_export_cleanup(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = payload or {}
        return cleanup_backtest_exports(
            run_id,
            keep_last_exports=payload.get("keep_last_exports", 5),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest export not found: {run_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/backtest/{run_id}/export/verify")
async def post_quant_backtest_export_verify(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = payload or {}
        return verify_backtest_export(
            run_id,
            export_manifest_path=payload.get("export_manifest_path") or payload.get("manifest_path"),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest export not found: {run_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/backtest/{run_id}/metrics")
async def get_quant_backtest_metrics(run_id: str) -> dict[str, Any]:
    return _load_or_404(run_id, "metrics")


@router.get("/backtest/{run_id}/diagnostics")
async def get_quant_backtest_diagnostics(run_id: str) -> dict[str, Any]:
    return _load_or_404(run_id, "diagnostics")


@router.get("/backtest/{run_id}/equity-curve")
async def get_quant_backtest_equity_curve(run_id: str) -> list[dict[str, Any]]:
    payload = _load_or_404(run_id, "equity_curve")
    return payload if isinstance(payload, list) else []


@router.get("/backtest/{run_id}/drawdown-curve")
async def get_quant_backtest_drawdown_curve(run_id: str) -> list[dict[str, Any]]:
    payload = _load_or_404(run_id, "drawdown_curve")
    return payload if isinstance(payload, list) else []


@router.get("/backtest/{run_id}/trades")
async def get_quant_backtest_trades(run_id: str) -> list[dict[str, Any]]:
    payload = _load_or_404(run_id, "trades")
    return payload if isinstance(payload, list) else []


@router.get("/backtest/{run_id}/signals")
async def get_quant_backtest_signals(run_id: str) -> list[dict[str, Any]]:
    payload = _load_or_404(run_id, "signals")
    return payload if isinstance(payload, list) else []


@router.get("/backtest/{run_id}/weights")
async def get_quant_backtest_weights(run_id: str) -> list[dict[str, Any]]:
    payload = _load_or_404(run_id, "weights")
    return payload if isinstance(payload, list) else []


@router.post("/strategy/save")
async def post_strategy_save(payload: dict[str, Any]) -> dict[str, Any]:
    path = save_strategy(payload, ARTIFACT_ROOT.parent / "strategies")
    strategy = load_strategy(path.stem, ARTIFACT_ROOT.parent / "strategies") or payload
    return {"status": "success", "path": str(path), "strategy": strategy}


@router.post("/strategy/dry-run")
async def post_strategy_dry_run(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        strategy = validate_strategy(payload)
    except ValueError as exc:
        return {"status": "failed", "valid": False, "warnings": [str(exc)]}
    features = strategy.get("features") if isinstance(strategy.get("features"), dict) else {}
    feature_ids = [
        str(spec.get("id") or feature_id).strip().lower()
        for feature_id, spec in features.items()
        if isinstance(spec, dict)
    ]
    supported = {item.get("factor_id") for item in quant_config()["factors"]}
    missing_features = [feature_id for feature_id in feature_ids if feature_id not in supported and feature_id != "research_score"]
    return {
        "status": "success" if not missing_features else "partial",
        "valid": not missing_features,
        "strategy": strategy,
        "diagnostics": {
            "feature_ids": feature_ids,
            "missing_features": missing_features,
            "execution_trade_at": (strategy.get("execution") or {}).get("trade_at"),
            "lookahead_safe": (strategy.get("execution") or {}).get("trade_at") == "next_bar_close",
            "schema_version": strategy.get("schema_version"),
            "strategy_version": strategy.get("strategy_version"),
            "migration_history": strategy.get("migration_history") or [],
        },
    }


@router.post("/strategy/migrate")
async def post_strategy_migrate(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        strategy = migrate_strategy(payload, touch=False)
    except ValueError as exc:
        return {"status": "failed", "valid": False, "warnings": [str(exc)]}
    return {
        "status": "success",
        "valid": True,
        "strategy": strategy,
        "migrations": strategy.get("migration_history") or [],
    }


@router.get("/strategy/list")
async def get_strategy_list() -> dict[str, Any]:
    user_root = ARTIFACT_ROOT.parent / "strategies"
    defaults = list_strategies()
    user_items = []
    if user_root.exists():
        for path in sorted(user_root.glob("*.json")):
            item = load_strategy(path.stem, user_root)
            if item:
                user_items.append(item)
    return {"status": "success", "items": defaults + user_items}


@router.get("/strategy/{strategy_id}")
async def get_strategy_detail(strategy_id: str) -> dict[str, Any]:
    user_strategy = load_strategy(strategy_id, ARTIFACT_ROOT.parent / "strategies")
    strategy = user_strategy or get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"strategy not found: {strategy_id}")
    return strategy


@router.delete("/strategy/{strategy_id}")
async def delete_strategy_detail(strategy_id: str) -> dict[str, Any]:
    deleted = delete_strategy(strategy_id, ARTIFACT_ROOT.parent / "strategies")
    if not deleted:
        raise HTTPException(status_code=404, detail=f"strategy not found: {strategy_id}")
    return {"status": "success", "deleted": True, "strategy_id": strategy_id}


def _load_or_404(run_id: str, name: str) -> Any:
    try:
        return load_backtest_artifact(run_id, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"quant backtest artifact not found: {run_id}/{name}")


def _load_or_empty(run_id: str, name: str, *, default: Any) -> Any:
    try:
        return load_backtest_artifact(run_id, name)
    except FileNotFoundError:
        return default


def _replay_reports_or_empty(run_id: str) -> dict[str, Any]:
    try:
        return list_replay_reports(run_id, limit=10)
    except FileNotFoundError:
        return {"status": "success", "run_id": run_id, "count": 0, "latest": {}, "items": []}
