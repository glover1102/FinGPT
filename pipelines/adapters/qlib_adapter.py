from __future__ import annotations

import importlib.util
from typing import Any

from core.config.settings import Settings, load_settings
from pipelines.adapters.qlib_export import build_qlib_csv_export


def qlib_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    enabled = bool(settings.quant_lab_qlib_enabled)
    if not enabled:
        return {
            "status": "disabled",
            "enabled": False,
            "provider_uri": settings.qlib_provider_uri,
            "dependency": "not_checked",
            "data_source_policy": "data_mart_export_only",
            "startup_required": False,
            "message": "Qlib adapter is disabled; deterministic Quant Lab engine remains the default.",
        }
    if importlib.util.find_spec("qlib") is None:
        return {
            "status": "dependency_missing",
            "enabled": True,
            "provider_uri": settings.qlib_provider_uri,
            "dependency": "missing",
            "data_source_policy": "data_mart_export_only",
            "startup_required": False,
            "message": "Install qlib and configure QLIB_PROVIDER_URI before enabling provider-specific runs.",
        }
    return {
        "status": "available",
        "enabled": True,
        "provider_uri": settings.qlib_provider_uri,
        "dependency": "installed",
        "data_source_policy": "data_mart_export_only",
        "startup_required": False,
        "message": "Qlib is available for explicit adapter workflows only.",
    }


def qlib_export_preview(
    *,
    tickers: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    provider_uri: str | None = None,
    dry_run: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Prepare or write a data-mart export without making Qlib a startup dependency."""

    settings = settings or load_settings()
    status = qlib_status(settings)
    return build_qlib_csv_export(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        provider_uri=provider_uri,
        dry_run=dry_run,
        settings=settings,
        runtime_status=status,
    )
