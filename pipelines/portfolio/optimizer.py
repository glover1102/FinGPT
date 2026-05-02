from __future__ import annotations

import math
from typing import Iterable


def optimize_portfolio(
    returns_by_asset: dict[str, Iterable[float]],
    *,
    method: str = "equal_weight",
    max_weight: float = 1.0,
) -> dict[str, object]:
    assets = [asset for asset in returns_by_asset if str(asset).strip()]
    if not assets:
        return {"status": "failed", "weights": {}, "method": method, "warnings": ["No assets supplied."]}
    method = str(method or "equal_weight").lower()
    if method == "equal_weight":
        raw = {asset: 1.0 for asset in assets}
    elif method in {"inverse_volatility", "risk_parity"}:
        raw = {asset: 1.0 / max(_vol(list(returns_by_asset[asset])), 1e-9) for asset in assets}
    elif method == "max_sharpe":
        raw = {}
        for asset in assets:
            rows = list(returns_by_asset[asset])
            vol = max(_vol(rows), 1e-9)
            mean = sum(rows) / len(rows) if rows else 0.0
            raw[asset] = max(mean / vol, 0.0)
        if not any(raw.values()):
            raw = {asset: 1.0 for asset in assets}
    else:
        raise ValueError(f"unsupported optimizer method: {method}")
    weights, effective_cap, warnings = _normalize_with_cap(raw, max_weight=max_weight)
    return {
        "status": "success",
        "method": method,
        "weights": weights,
        "sum_weights": round(sum(weights.values()), 8),
        "max_weight": effective_cap,
        "warnings": warnings,
        "diagnostics": {
            "asset_count": len(assets),
            "uses_covariance": False,
        },
    }


def _vol(values: list[float]) -> float:
    clean: list[float] = []
    for value in values:
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(val):
            clean.append(val)
    if len(clean) < 2:
        return 0.0
    mean = sum(clean) / len(clean)
    return math.sqrt(sum((value - mean) ** 2 for value in clean) / (len(clean) - 1))


def _normalize_with_cap(raw: dict[str, float], *, max_weight: float) -> tuple[dict[str, float], float, list[str]]:
    warnings: list[str] = []
    max_weight = max(0.0, min(float(max_weight), 1.0))
    if max_weight <= 0:
        max_weight = 1.0
    feasible_floor = 1.0 / max(len(raw), 1)
    if max_weight < feasible_floor:
        warnings.append(
            f"max_weight {max_weight:.4f} is infeasible for {len(raw)} assets; raised to {feasible_floor:.4f}."
        )
        max_weight = feasible_floor
    remaining = dict(raw)
    capped: dict[str, float] = {}
    remaining_weight = 1.0
    while remaining:
        total = sum(max(value, 0.0) for value in remaining.values()) or float(len(remaining))
        progressed = False
        for asset, value in list(remaining.items()):
            weight = remaining_weight * (max(value, 0.0) / total if total else 1.0 / len(remaining))
            if weight > max_weight:
                capped[asset] = max_weight
                remaining_weight -= max_weight
                remaining.pop(asset)
                progressed = True
        if not progressed:
            total = sum(max(value, 0.0) for value in remaining.values()) or float(len(remaining))
            for asset, value in remaining.items():
                capped[asset] = remaining_weight * (max(value, 0.0) / total if total else 1.0 / len(remaining))
            break
    total_weight = sum(capped.values()) or 1.0
    weights = {asset: round(weight / total_weight, 8) for asset, weight in sorted(capped.items())}
    if weights:
        last = next(reversed(weights))
        weights[last] = round(weights[last] + (1.0 - sum(weights.values())), 8)
    return weights, max_weight, warnings
