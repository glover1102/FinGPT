from __future__ import annotations

from typing import Any

from core.schemas.ai_portfolio import ConstraintCheck, ConstraintViolation, PortfolioPolicy, PortfolioWeight


ASSET_CLASS_ORDER = ("equity", "bond", "cash", "alternative")


def allocation_by_class(weights: list[PortfolioWeight]) -> dict[str, float]:
    out = {key: 0.0 for key in ASSET_CLASS_ORDER}
    for item in weights:
        asset_class = normalize_asset_class(item.asset_class)
        out[asset_class] = out.get(asset_class, 0.0) + float(item.weight or 0.0)
    return {key: round(value, 4) for key, value in out.items() if value or key in ASSET_CLASS_ORDER}


def normalize_asset_class(value: str | None) -> str:
    clean = str(value or "").strip().lower()
    if clean in {"bond", "fixed_income", "rates", "credit"}:
        return "bond"
    if clean in {"cash", "money_market", "t_bill", "treasury_bill"}:
        return "cash"
    if clean in {"alternative", "commodity", "real_asset", "crypto", "real_estate"}:
        return "alternative"
    return "equity"


def check_constraints(
    weights: list[PortfolioWeight],
    policy: PortfolioPolicy,
    *,
    universe_metadata: dict[str, dict[str, Any]] | None = None,
    missing_assets: list[str] | None = None,
    current_weights: dict[str, float] | None = None,
    restricted_assets: list[str] | None = None,
) -> ConstraintCheck:
    violations: list[ConstraintViolation] = []
    missing_assets = list(missing_assets or [])
    restricted_assets = [str(item).upper().strip() for item in (restricted_assets or []) if str(item).strip()]
    total = sum(float(item.weight or 0.0) for item in weights)
    if abs(total - 100.0) > 0.5:
        violations.append(
            ConstraintViolation(
                rule="weight_sum",
                severity="fail",
                message=f"비중 합계가 100%가 아닙니다: {total:.2f}%.",
                actual=round(total, 4),
                limit=100.0,
            )
        )

    allocations = allocation_by_class(weights)
    for asset_class, allowed in policy.asset_allocation_ranges.items():
        normalized_class = normalize_asset_class(asset_class)
        actual = allocations.get(normalized_class, 0.0)
        if actual < allowed.min - 0.5 or actual > allowed.max + 0.5:
            violations.append(
                ConstraintViolation(
                    rule=f"asset_class_range:{asset_class}",
                    severity="fail",
                    message=f"{asset_class} 비중 {actual:.2f}%가 허용 범위 {allowed.min:.2f}%~{allowed.max:.2f}%를 벗어났습니다.",
                    actual=round(actual, 4),
                    limit=allowed.max if actual > allowed.max else allowed.min,
                )
            )

    for item in weights:
        if item.weight > policy.max_single_asset_weight + 1e-6:
            violations.append(
                ConstraintViolation(
                    rule="max_single_asset_weight",
                    severity="fail",
                    ticker=item.ticker,
                    message=f"{item.ticker} 비중 {item.weight:.2f}%가 단일 자산 한도 {policy.max_single_asset_weight:.2f}%를 초과했습니다.",
                    actual=round(item.weight, 4),
                    limit=policy.max_single_asset_weight,
                )
            )

    cash_weight = allocations.get("cash", 0.0)
    if cash_weight + 1e-6 < policy.min_cash_weight:
        violations.append(
            ConstraintViolation(
                rule="min_cash_weight",
                severity="fail",
                message=f"현금성 비중 {cash_weight:.2f}%가 최소 현금 비중 {policy.min_cash_weight:.2f}%보다 낮습니다.",
                actual=round(cash_weight, 4),
                limit=policy.min_cash_weight,
            )
        )

    sector_weights: dict[str, float] = {}
    meta = universe_metadata or {}
    for item in weights:
        sector = str(item.sector or meta.get(item.ticker, {}).get("sector") or "").strip()
        if not sector:
            continue
        sector_weights[sector] = sector_weights.get(sector, 0.0) + item.weight
    for sector, actual in sector_weights.items():
        if actual > policy.max_sector_weight + 1e-6:
            violations.append(
                ConstraintViolation(
                    rule="max_sector_weight",
                    severity="fail",
                    message=f"{sector} 섹터 비중 {actual:.2f}%가 섹터 한도 {policy.max_sector_weight:.2f}%를 초과했습니다.",
                    actual=round(actual, 4),
                    limit=policy.max_sector_weight,
                )
            )

    restricted_hit = sorted({item.ticker for item in weights if item.ticker in restricted_assets})
    for ticker in restricted_hit:
        violations.append(
            ConstraintViolation(
                rule="restricted_asset",
                severity="fail",
                ticker=ticker,
                message=f"{ticker}는 정책상 제한 자산인데 추천 비중에 포함되었습니다.",
            )
        )

    for ticker in missing_assets:
        violations.append(
            ConstraintViolation(
                rule="missing_asset_reported",
                severity="warning",
                ticker=ticker,
                message=f"{ticker}는 가격 데이터가 부족해 정량 계산에서 제외되었습니다.",
            )
        )

    if current_weights:
        turnover = 0.0
        target_map = {item.ticker: item.weight for item in weights}
        for ticker in sorted(set(current_weights) | set(target_map)):
            turnover += abs(float(target_map.get(ticker, 0.0)) - float(current_weights.get(ticker, 0.0)))
        turnover /= 2.0
        if turnover > policy.max_turnover + 1e-6:
            violations.append(
                ConstraintViolation(
                    rule="max_turnover",
                    severity="warning",
                    message=f"예상 회전율 {turnover:.2f}%가 회전율 경고 기준 {policy.max_turnover:.2f}%를 초과했습니다.",
                    actual=round(turnover, 4),
                    limit=policy.max_turnover,
                )
            )

    has_fail = any(item.severity == "fail" for item in violations)
    material_warnings = [item for item in violations if item.severity == "warning" and item.rule != "missing_asset_reported"]
    status = "fail" if has_fail else ("warning" if material_warnings else "pass")
    return ConstraintCheck(status=status, violations=violations, allocation_by_asset_class=allocations)


def apply_constraint_status(weights: list[PortfolioWeight], check: ConstraintCheck) -> list[PortfolioWeight]:
    failed_tickers = {
        str(item.ticker)
        for item in check.violations
        if item.ticker and item.severity == "fail"
    }
    warned_tickers = {
        str(item.ticker)
        for item in check.violations
        if item.ticker and item.severity == "warning"
    }
    out: list[PortfolioWeight] = []
    for item in weights:
        status = "pass"
        if item.ticker in failed_tickers:
            status = "fail"
        elif item.ticker in warned_tickers:
            status = "warning"
        out.append(item.model_copy(update={"constraint_status": status}))
    return out
