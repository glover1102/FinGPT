from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipelines.forecast.common import now_iso, stable_hash
from pipelines.forecast.experiment_store import forecast_root

_SAFE_TICKER_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def get_macro_context(ticker: str) -> dict[str, Any]:
    try:
        from pipelines.macro import macro_service
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"macro_service_import_failed:{exc}"}
    try:
        context = macro_service.get_macro_research_context(ticker=ticker)
        payload = context.model_dump(mode="json") if hasattr(context, "model_dump") else dict(context)
        return {"status": "success", "ticker": ticker, "context": payload}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"macro_context_unavailable:{exc}"}


def build_macro_regime_artifact(ticker: str, macro_context: dict[str, Any], feature_payload: dict[str, Any]) -> dict[str, Any]:
    generated_at = now_iso()
    if macro_context.get("status") != "success":
        return {
            "status": "unavailable",
            "schema_version": "macro_regime_classifier_v1",
            "ticker": ticker,
            "generated_at": generated_at,
            "reason": macro_context.get("reason", "macro_context_unavailable"),
            "artifact_path": "",
        }
    context = macro_context.get("context") or {}
    regime = context.get("regime") or {}
    signals = {str(item.get("name") or ""): str(item.get("value") or "unknown") for item in context.get("signals") or []}
    asset_class = _asset_class(ticker)
    risk_level = str(regime.get("risk_level") or "unknown").lower()
    regime_name = str(regime.get("name") or "unknown").lower()
    risk_score = _risk_score(regime_name, risk_level, signals)
    sensitivity = _asset_sensitivity(asset_class, risk_score, signals)
    trend_features = _latest_trend_features(feature_payload)
    artifact = {
        "status": "success",
        "schema_version": "macro_regime_classifier_v1",
        "ticker": ticker,
        "asset_class": asset_class,
        "generated_at": generated_at,
        "regime": {
            "name": regime_name,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "source": "macro_context_adapter",
        },
        "signals": signals,
        "asset_class_sensitivity": sensitivity,
        "trend_features": trend_features,
        "policy": "context_only_no_signal_flip",
        "warnings": [] if signals else ["macro_signals_missing"],
    }
    artifact["artifact_id"] = f"macro_{stable_hash({'ticker': ticker, 'generated_at': generated_at, 'regime': artifact['regime']}, length=16)}"
    path = _macro_regime_path(str(artifact["artifact_id"]))
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    artifact["artifact_path"] = str(path)
    return artifact


def _macro_regime_path(artifact_id: str) -> Path:
    root = forecast_root() / "macro_regime"
    root.mkdir(parents=True, exist_ok=True)
    clean = _SAFE_TICKER_RE.sub("_", artifact_id)[:128]
    return root / f"{clean}.json"


def _asset_class(ticker: str) -> str:
    value = str(ticker or "").upper()
    if value in {"TLT", "IEF", "SHY", "BND", "AGG", "LQD", "HYG"}:
        return "rates_or_credit"
    if value in {"GLD", "IAU", "SLV", "USO"}:
        return "real_assets"
    if value in {"UUP", "FXE", "FXY"}:
        return "currency"
    return "equity"


def _risk_score(regime_name: str, risk_level: str, signals: dict[str, str]) -> float:
    score = {
        "low": 0.20,
        "moderate": 0.40,
        "medium": 0.45,
        "elevated": 0.65,
        "high": 0.80,
    }.get(risk_level, 0.50)
    if regime_name in {"recession_risk", "stagflation"}:
        score += 0.15
    if regime_name in {"goldilocks", "recovery"}:
        score -= 0.10
    if signals.get("credit_signal") == "stress":
        score += 0.12
    if signals.get("policy_signal") == "restrictive":
        score += 0.06
    if signals.get("inflation_signal") in {"rising", "reaccelerating", "sticky"}:
        score += 0.06
    if signals.get("growth_signal") in {"contracting", "weakening"}:
        score += 0.08
    return round(max(0.0, min(1.0, score)), 4)


def _asset_sensitivity(asset_class: str, risk_score: float, signals: dict[str, str]) -> dict[str, Any]:
    if asset_class == "equity":
        directional_bias = "macro_headwind" if risk_score >= 0.65 else "macro_supportive" if risk_score <= 0.35 else "mixed"
        sensitivity_score = -risk_score
    elif asset_class == "rates_or_credit":
        restrictive = signals.get("policy_signal") == "restrictive"
        stress = signals.get("credit_signal") == "stress"
        sensitivity_score = (0.25 if risk_score >= 0.65 else 0.0) - (0.25 if restrictive else 0.0) - (0.20 if stress else 0.0)
        directional_bias = "mixed_duration_credit" if restrictive or stress else "defensive_support"
    elif asset_class == "real_assets":
        inflation = signals.get("inflation_signal") in {"rising", "reaccelerating", "sticky"}
        sensitivity_score = (0.35 if inflation else 0.0) + (0.15 if risk_score >= 0.65 else 0.0)
        directional_bias = "inflation_or_stress_support" if sensitivity_score > 0 else "mixed"
    else:
        sensitivity_score = 0.0
        directional_bias = "macro_translation_required"
    return {
        "score": round(max(-1.0, min(1.0, sensitivity_score)), 4),
        "directional_bias": directional_bias,
        "asset_class": asset_class,
        "inputs": {
            "risk_score": risk_score,
            "policy_signal": signals.get("policy_signal", "unknown"),
            "inflation_signal": signals.get("inflation_signal", "unknown"),
            "growth_signal": signals.get("growth_signal", "unknown"),
            "credit_signal": signals.get("credit_signal", "unknown"),
        },
    }


def _latest_trend_features(feature_payload: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in feature_payload.get("rows") or [] if row.get("features")]
    if not rows:
        return {}
    features = rows[-1].get("features") or {}
    return {
        "price_above_ma200": features.get("price_above_ma200"),
        "price_distance_from_ma200": features.get("price_distance_from_ma200"),
        "realized_vol_20d": features.get("realized_vol_20d"),
    }
