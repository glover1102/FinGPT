from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.schemas.ai_portfolio import PortfolioPolicy, PortfolioRecommendation, RebalanceSignal, RecommendedChange
from pipelines.ai_portfolio.audit import (
    ENGINE_VERSION,
    constraint_policy_hash,
    policy_config_hash,
    request_id,
    stable_hash,
    ticker_universe_hash,
)
from pipelines.ai_portfolio.engine import new_id, now_iso
from pipelines.ai_portfolio.explainer import rebalance_explanation


def target_weight_map(recommendation: PortfolioRecommendation) -> dict[str, float]:
    return {item.ticker: float(item.weight) for item in recommendation.weights}


def _future_iso(days: int) -> str:
    return (datetime.now(UTC).replace(microsecond=0) + timedelta(days=max(1, days))).isoformat().replace("+00:00", "Z")


def _next_review_iso(frequency: str) -> str:
    clean = str(frequency or "monthly").lower().strip()
    if clean == "weekly":
        return _future_iso(7)
    if clean == "quarterly":
        return _future_iso(90)
    return _future_iso(30)


def calculate_rebalance_signal(
    *,
    policy: PortfolioPolicy,
    recommendation: PortfolioRecommendation,
    current_weights: dict[str, float],
) -> RebalanceSignal:
    target = target_weight_map(recommendation)
    current = {str(ticker).upper().strip(): float(weight or 0.0) for ticker, weight in (current_weights or {}).items() if str(ticker).strip()}
    if not current:
        current = dict(target)

    triggers: list[str] = []
    changes: list[RecommendedChange] = []
    drift_threshold = float(policy.weight_drift_threshold)
    turnover = 0.0
    for ticker in sorted(set(current) | set(target)):
        cur = float(current.get(ticker, 0.0))
        tar = float(target.get(ticker, 0.0))
        diff = tar - cur
        turnover += abs(diff)
        if abs(diff) >= drift_threshold:
            action = "increase" if diff > 0 else "reduce"
            changes.append(
                RecommendedChange(
                    ticker=ticker,
                    current_weight=round(cur, 4),
                    target_weight=round(tar, 4),
                    change=round(diff, 4),
                    action=action,
                )
            )
    turnover /= 2.0
    if changes:
        triggers.append("weight_drift")
    cash_current = sum(weight for ticker, weight in current.items() if ticker in {"CASH", "SGOV", "BIL", "SHV", "MINT", "JPST"})
    cash_target = sum(weight for ticker, weight in target.items() if ticker in {"CASH", "SGOV", "BIL", "SHV", "MINT", "JPST"})
    if cash_current + 1e-6 < policy.min_cash_weight and cash_target > cash_current + 1e-6:
        triggers.append("cash_minimum_violation")
    over_single = [
        ticker
        for ticker, weight in current.items()
        if weight > policy.max_single_asset_weight + 1e-6 and target.get(ticker, weight) < weight - 1e-6
    ]
    if over_single:
        triggers.append("single_asset_limit_violation")
    if turnover > policy.max_turnover + 1e-6:
        triggers.append("turnover_limit_warning")

    required = bool(triggers) and policy.automation_level != "manual"
    status = "pending_user_approval" if required else "deferred"
    audit = {
        **(recommendation.audit or {}),
        "request_id": request_id("reb"),
        "config_hash": policy_config_hash(policy),
        "constraint_policy_hash": constraint_policy_hash(policy),
        "universe_hash": ticker_universe_hash(target.keys()),
        "input_current_weights_hash": stable_hash(current),
        "model_or_engine_version": ENGINE_VERSION,
        "rebalance_rule_version": "rule_engine_v2",
        "data_snapshot_timestamp": now_iso(),
    }
    signal = RebalanceSignal(
        signal_id=new_id("reb"),
        policy_id=policy.policy_id,
        created_at=now_iso(),
        rebalance_required=required,
        trigger_type=sorted(set(triggers)),
        current_weights={ticker: round(weight, 4) for ticker, weight in current.items()},
        target_weights={ticker: round(weight, 4) for ticker, weight in target.items()},
        recommended_changes=sorted(changes, key=lambda item: abs(item.change), reverse=True),
        risk_before={"turnover_to_target_pct": round(turnover, 4)},
        estimated_risk_after={
            "turnover_to_target_pct": 0.0 if required else round(turnover, 4),
            "broker_execution": "not_supported",
        },
        status=status,
        ai_explanation="",
        expires_at=_future_iso(7) if required else None,
        next_review_at=_next_review_iso(policy.rebalance_frequency),
        turnover_estimate=round(turnover, 4),
        post_trade_policy_check=recommendation.constraint_check.model_dump(mode="json"),
        audit=audit,
    )
    signal.ai_explanation = rebalance_explanation(signal)
    return signal
