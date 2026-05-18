from __future__ import annotations

import math
from typing import Iterable


def optimize_portfolio(
    returns_by_asset: dict[str, Iterable[float]],
    *,
    method: str = "equal_weight",
    max_weight: float = 1.0,
    covariance_method: str = "sample",
    shrinkage_alpha: float = 0.1,
    benchmark: str | None = None,
    benchmark_returns: Iterable[float] | None = None,
) -> dict[str, object]:
    returns_table, warnings = _aligned_returns_table(returns_by_asset)
    assets = list(returns_table)
    if not assets:
        return {"status": "failed", "weights": {}, "method": method, "warnings": ["No assets supplied."]}
    method = str(method or "equal_weight").lower()
    matrix = [returns_table[asset] for asset in assets]
    means = [_mean(rows) for rows in matrix]
    sample_covariance = _covariance_matrix(matrix)
    covariance_method = str(covariance_method or "sample").strip().lower()
    shrinkage_alpha = max(0.0, min(float(shrinkage_alpha), 1.0))
    covariance = _apply_covariance_method(sample_covariance, method=covariance_method, shrinkage_alpha=shrinkage_alpha)
    uses_covariance = False
    if method == "equal_weight":
        raw = {asset: 1.0 for asset in assets}
    elif method in {"inverse_volatility", "risk_parity", "equal_risk_contribution"}:
        if method in {"risk_parity", "equal_risk_contribution"}:
            uses_covariance = True
            raw_weights = _risk_parity_weights(covariance)
            raw = {asset: raw_weights[idx] for idx, asset in enumerate(assets)}
        else:
            raw = {asset: 1.0 / max(_vol(returns_table[asset]), 1e-9) for asset in assets}
    elif method in {"minimum_volatility", "min_volatility"}:
        uses_covariance = True
        raw_weights = _minimum_variance_weights(covariance)
        raw = {asset: raw_weights[idx] for idx, asset in enumerate(assets)}
    elif method == "momentum_tilt":
        raw = {}
        for asset in assets:
            rows = returns_table[asset]
            cumulative = 1.0
            for row in rows:
                try:
                    cumulative *= 1.0 + float(row)
                except (TypeError, ValueError):
                    continue
            raw[asset] = max(cumulative - 1.0, 0.0)
        if not any(raw.values()):
            raw = {asset: 1.0 for asset in assets}
    elif method in {"max_sharpe", "sharpe_tilt"}:
        uses_covariance = True
        raw_weights = _max_sharpe_weights(covariance, means)
        raw = {asset: raw_weights[idx] for idx, asset in enumerate(assets)}
        if not any(value > 0 for value in raw.values()):
            warnings.append("All covariance-adjusted Sharpe scores were non-positive; fell back to equal weight.")
            raw = {asset: 1.0 for asset in assets}
    else:
        raise ValueError(f"unsupported optimizer method: {method}")
    weights, effective_cap, cap_warnings = _normalize_with_cap(raw, max_weight=max_weight)
    warnings.extend(cap_warnings)
    portfolio_metrics = _portfolio_metrics(weights, assets, means, covariance)
    portfolio_metrics.update(
        _benchmark_relative_metrics(
            weights,
            returns_table,
            benchmark_returns=_resolve_benchmark_returns(
                benchmark=benchmark,
                returns_table=returns_table,
                benchmark_returns=benchmark_returns,
            ),
        )
    )
    risk_contributions = _risk_contributions(weights, assets, covariance)
    return {
        "status": "success",
        "method": method,
        "weights": weights,
        "sum_weights": round(sum(weights.values()), 8),
        "max_weight": effective_cap,
        "warnings": warnings,
        "portfolio_metrics": portfolio_metrics,
        "risk_contributions": risk_contributions,
        "correlation_matrix": _correlation_matrix(covariance, assets),
        "diagnostics": {
            "asset_count": len(assets),
            "sample_count": len(next(iter(returns_table.values()), [])),
            "uses_covariance": uses_covariance,
            "covariance_method": covariance_method,
            "shrinkage_alpha": shrinkage_alpha if covariance_method == "diagonal_shrinkage" else 0.0,
            "covariance_shrinkage_used": covariance_method == "diagonal_shrinkage",
            "benchmark": str(benchmark or "").upper(),
            "benchmark_sample_count": portfolio_metrics.get("benchmark_sample_count", 0),
            "optimizer": "closed_form_covariance_long_only" if uses_covariance else "deterministic_score_weighting",
            "max_weight_actual": round(max(weights.values()) if weights else 0.0, 8),
            "capped_assets": [asset for asset, weight in weights.items() if weight >= effective_cap - 1e-8],
            "concentration_hhi": round(sum(weight * weight for weight in weights.values()), 8),
            "effective_number_of_positions": round(1.0 / max(sum(weight * weight for weight in weights.values()), 1e-12), 6),
            "risk_contribution_sum": round(sum(risk_contributions.values()), 6),
            "risk_contribution_method": "component_variance",
        },
    }


def _aligned_returns_table(returns_by_asset: dict[str, Iterable[float]]) -> tuple[dict[str, list[float]], list[str]]:
    warnings: list[str] = []
    cleaned: dict[str, list[float]] = {}
    for raw_asset, raw_values in returns_by_asset.items():
        asset = str(raw_asset or "").strip().upper()
        if not asset:
            continue
        values: list[float] = []
        for value in raw_values:
            try:
                val = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(val):
                values.append(val)
        if len(values) >= 2:
            cleaned[asset] = values
        else:
            warnings.append(f"{asset} excluded: fewer than 2 finite returns.")
    if not cleaned:
        return {}, warnings
    min_len = min(len(values) for values in cleaned.values())
    if len({len(values) for values in cleaned.values()}) > 1:
        warnings.append(f"Return histories had different lengths; aligned on the most recent {min_len} observations.")
    return {asset: values[-min_len:] for asset, values in cleaned.items()}, warnings


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


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


def _covariance_matrix(matrix: list[list[float]]) -> list[list[float]]:
    if not matrix:
        return []
    n_assets = len(matrix)
    n_obs = min(len(row) for row in matrix)
    if n_obs < 2:
        return [[0.0 for _ in range(n_assets)] for _ in range(n_assets)]
    means = [_mean(row[-n_obs:]) for row in matrix]
    cov = [[0.0 for _ in range(n_assets)] for _ in range(n_assets)]
    for i in range(n_assets):
        for j in range(i, n_assets):
            value = sum((matrix[i][-n_obs + k] - means[i]) * (matrix[j][-n_obs + k] - means[j]) for k in range(n_obs)) / (n_obs - 1)
            cov[i][j] = value
            cov[j][i] = value
    avg_var = sum(max(cov[i][i], 0.0) for i in range(n_assets)) / max(n_assets, 1)
    ridge = max(avg_var * 1e-6, 1e-12)
    for i in range(n_assets):
        cov[i][i] += ridge
    return cov


def _apply_covariance_method(
    covariance: list[list[float]],
    *,
    method: str,
    shrinkage_alpha: float,
) -> list[list[float]]:
    if method in {"sample", ""}:
        return covariance
    if method != "diagonal_shrinkage":
        raise ValueError(f"unsupported covariance method: {method}")
    alpha = max(0.0, min(float(shrinkage_alpha), 1.0))
    shrunk: list[list[float]] = []
    for i, row in enumerate(covariance):
        next_row: list[float] = []
        for j, value in enumerate(row):
            next_row.append(float(value) if i == j else float(value) * (1.0 - alpha))
        shrunk.append(next_row)
    return shrunk


def _minimum_variance_weights(covariance: list[list[float]]) -> list[float]:
    n_assets = len(covariance)
    if n_assets == 0:
        return []
    solution = _solve_linear_system(covariance, [1.0 for _ in range(n_assets)])
    if not solution:
        return [1.0 / n_assets for _ in range(n_assets)]
    return _normalize_positive(solution)


def _max_sharpe_weights(covariance: list[list[float]], means: list[float]) -> list[float]:
    n_assets = len(covariance)
    if n_assets == 0:
        return []
    positive_means = [max(value, 0.0) for value in means]
    if not any(positive_means):
        return [1.0 / n_assets for _ in range(n_assets)]
    solution = _solve_linear_system(covariance, positive_means)
    if not solution:
        return _normalize_positive(positive_means)
    return _normalize_positive([max(value, 0.0) for value in solution])


def _risk_parity_weights(covariance: list[list[float]], *, iterations: int = 300) -> list[float]:
    n_assets = len(covariance)
    if n_assets == 0:
        return []
    weights = [1.0 / n_assets for _ in range(n_assets)]
    for _ in range(iterations):
        variance = _portfolio_variance_vec(weights, covariance)
        if variance <= 0:
            break
        target = variance / n_assets
        cov_weight = _mat_vec(covariance, weights)
        next_weights = []
        for weight, marginal in zip(weights, cov_weight):
            contribution = weight * marginal
            if contribution <= 0:
                next_weights.append(weight)
            else:
                next_weights.append(weight * math.sqrt(target / contribution))
        weights = _normalize_positive(next_weights)
    return weights


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    n = len(vector)
    if n == 0:
        return []
    a = [list(row[:n]) + [float(vector[idx])] for idx, row in enumerate(matrix[:n])]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-18:
            return None
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
        pivot_value = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= pivot_value
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if factor == 0:
                continue
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    return [a[row][n] for row in range(n)]


def _normalize_positive(values: list[float]) -> list[float]:
    clean = [max(float(value), 0.0) if math.isfinite(float(value)) else 0.0 for value in values]
    total = sum(clean)
    if total <= 0:
        return [1.0 / len(values) for _ in values] if values else []
    return [value / total for value in clean]


def _mat_vec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(row[j] * vector[j] for j in range(len(vector))) for row in matrix]


def _portfolio_variance_vec(weights: list[float], covariance: list[list[float]]) -> float:
    cov_weight = _mat_vec(covariance, weights)
    return sum(weight * marginal for weight, marginal in zip(weights, cov_weight))


def _portfolio_metrics(
    weights: dict[str, float],
    assets: list[str],
    means: list[float],
    covariance: list[list[float]],
) -> dict[str, float]:
    weight_vec = [float(weights.get(asset, 0.0)) for asset in assets]
    daily_return = sum(weight * mean for weight, mean in zip(weight_vec, means))
    variance = max(_portfolio_variance_vec(weight_vec, covariance), 0.0)
    annual_return = daily_return * 252
    annual_vol = math.sqrt(variance) * math.sqrt(252) if variance else 0.0
    return {
        "expected_annual_return": round(annual_return, 6),
        "annualized_volatility": round(annual_vol, 6),
        "sharpe": round(annual_return / annual_vol, 6) if annual_vol else 0.0,
    }


def _resolve_benchmark_returns(
    *,
    benchmark: str | None,
    returns_table: dict[str, list[float]],
    benchmark_returns: Iterable[float] | None,
) -> list[float]:
    clean = str(benchmark or "").strip().upper()
    if clean and clean in returns_table:
        return list(returns_table[clean])
    if benchmark_returns is None:
        return []
    out: list[float] = []
    for value in benchmark_returns:
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(val):
            out.append(val)
    return out


def _benchmark_relative_metrics(
    weights: dict[str, float],
    returns_table: dict[str, list[float]],
    *,
    benchmark_returns: list[float],
) -> dict[str, float]:
    if not benchmark_returns or not returns_table:
        return {
            "benchmark_annual_return": 0.0,
            "active_annual_return": 0.0,
            "tracking_error": 0.0,
            "information_ratio": 0.0,
            "beta_to_benchmark": 0.0,
            "benchmark_sample_count": 0,
        }
    n_obs = min([len(benchmark_returns), *[len(values) for values in returns_table.values()]])
    if n_obs < 2:
        return {
            "benchmark_annual_return": 0.0,
            "active_annual_return": 0.0,
            "tracking_error": 0.0,
            "information_ratio": 0.0,
            "beta_to_benchmark": 0.0,
            "benchmark_sample_count": n_obs,
        }
    assets = list(returns_table)
    portfolio_returns = []
    for idx in range(n_obs):
        portfolio_returns.append(
            sum(float(weights.get(asset, 0.0)) * returns_table[asset][-n_obs + idx] for asset in assets)
        )
    bench = benchmark_returns[-n_obs:]
    active = [p - b for p, b in zip(portfolio_returns, bench)]
    active_return = _mean(active) * 252
    tracking_error = _vol(active) * math.sqrt(252)
    bench_var = _variance(bench)
    beta = _covariance(portfolio_returns, bench) / bench_var if bench_var > 0 else 0.0
    benchmark_annual_return = _mean(bench) * 252
    return {
        "benchmark_annual_return": round(benchmark_annual_return, 6),
        "active_annual_return": round(active_return, 6),
        "tracking_error": round(tracking_error, 6),
        "information_ratio": round(active_return / tracking_error, 6) if tracking_error else 0.0,
        "beta_to_benchmark": round(beta, 6),
        "benchmark_sample_count": n_obs,
    }


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _covariance(left: list[float], right: list[float]) -> float:
    n_obs = min(len(left), len(right))
    if n_obs < 2:
        return 0.0
    left_tail = left[-n_obs:]
    right_tail = right[-n_obs:]
    left_mean = _mean(left_tail)
    right_mean = _mean(right_tail)
    return sum((lval - left_mean) * (rval - right_mean) for lval, rval in zip(left_tail, right_tail)) / (n_obs - 1)


def _risk_contributions(weights: dict[str, float], assets: list[str], covariance: list[list[float]]) -> dict[str, float]:
    weight_vec = [float(weights.get(asset, 0.0)) for asset in assets]
    variance = _portfolio_variance_vec(weight_vec, covariance)
    if variance <= 0:
        return {asset: 0.0 for asset in assets}
    marginal = _mat_vec(covariance, weight_vec)
    return {
        asset: round(max(weight_vec[idx] * marginal[idx] / variance, 0.0), 6)
        for idx, asset in enumerate(assets)
    }


def _correlation_matrix(covariance: list[list[float]], assets: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i, asset_i in enumerate(assets):
        row: dict[str, float] = {}
        var_i = covariance[i][i] if i < len(covariance) and i < len(covariance[i]) else 0.0
        for j, asset_j in enumerate(assets):
            var_j = covariance[j][j] if j < len(covariance) and j < len(covariance[j]) else 0.0
            denom = math.sqrt(max(var_i, 0.0) * max(var_j, 0.0))
            cov = covariance[i][j] if i < len(covariance) and j < len(covariance[i]) else 0.0
            row[asset_j] = round(cov / denom, 6) if denom else 0.0
        out[asset_i] = row
    return out


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
