from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Iterable

from core.schemas.ai_portfolio import DataQuality, PortfolioPolicy


ENGINE_VERSION = "ai_portfolio_engine_v2"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def request_id(prefix: str = "req") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ticker_universe_hash(tickers: Iterable[str]) -> str:
    clean = sorted({str(ticker or "").upper().strip() for ticker in tickers if str(ticker or "").strip()})
    return stable_hash(clean)


def policy_config_hash(policy: PortfolioPolicy) -> str:
    payload = policy.model_dump(mode="json")
    for key in ("created_at", "updated_at"):
        payload.pop(key, None)
    return stable_hash(payload)


def constraint_policy_hash(policy: PortfolioPolicy) -> str:
    return stable_hash(
        {
            "asset_allocation_ranges": {
                key: value.model_dump(mode="json") for key, value in sorted(policy.asset_allocation_ranges.items())
            },
            "target_volatility": policy.target_volatility,
            "max_drawdown_alert": policy.max_drawdown_alert,
            "min_cash_weight": policy.min_cash_weight,
            "max_single_asset_weight": policy.max_single_asset_weight,
            "max_sector_weight": policy.max_sector_weight,
            "weight_drift_threshold": policy.weight_drift_threshold,
            "max_turnover": policy.max_turnover,
        }
    )


def data_quality_audit(data_quality: DataQuality) -> dict[str, Any]:
    coverage = data_quality.metadata_coverage or {}
    hydration = data_quality.hydration or {}
    return {
        "price_data_coverage": {
            "asset_count": data_quality.asset_count,
            "available_asset_count": data_quality.available_asset_count,
            "missing_count": len(data_quality.missing_assets),
            "insufficient_count": len(data_quality.insufficient_assets),
            "available_pct": round(data_quality.available_asset_count / data_quality.asset_count * 100, 2)
            if data_quality.asset_count
            else 0.0,
        },
        "fundamentals_coverage": {
            "fundamentals_count": int(coverage.get("fundamentals_count") or 0),
            "fundamentals_pct": float(coverage.get("fundamentals_pct") or 0.0),
            "missing_sample": list(coverage.get("fundamentals_missing") or [])[:20],
        },
        "metadata_coverage": coverage,
        "hydration": hydration,
        "data_snapshot_timestamp": now_iso(),
    }


def recommendation_audit(policy: PortfolioPolicy, data_quality: DataQuality, *, request: str | None = None) -> dict[str, Any]:
    tickers = data_quality.used_assets or []
    return {
        "request_id": request or request_id("gen"),
        "config_hash": policy_config_hash(policy),
        "constraint_policy_hash": constraint_policy_hash(policy),
        "universe_hash": ticker_universe_hash(tickers),
        "model_or_engine_version": ENGINE_VERSION,
        "optimizer_method": policy.optimization_method,
        **data_quality_audit(data_quality),
    }
