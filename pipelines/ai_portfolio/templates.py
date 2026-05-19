from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.schemas.ai_portfolio import AllocationRange, InvestmentType, QuantSettings, RebalancePolicy, RiskLimits


ADVANCED_SETTINGS = [
    "target_volatility",
    "max_drawdown_alert",
    "min_cash_weight",
    "max_single_asset_weight",
    "max_sector_weight",
    "rebalance_frequency",
    "weight_drift_threshold",
    "max_turnover",
    "optimization_method",
    "lookback_window_months",
    "risk_model",
    "expected_return_model",
    "asset_allocation_ranges",
]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ranges(equity: tuple[float, float], bond: tuple[float, float], cash: tuple[float, float], alternative: tuple[float, float]) -> dict[str, AllocationRange]:
    return {
        "equity": AllocationRange(min=equity[0], max=equity[1]),
        "bond": AllocationRange(min=bond[0], max=bond[1]),
        "cash": AllocationRange(min=cash[0], max=cash[1]),
        "alternative": AllocationRange(min=alternative[0], max=alternative[1]),
    }


def _template(
    *,
    id: str,
    display_name: str,
    description: str,
    suitable_horizon: str,
    risk_level: str,
    ranges: dict[str, AllocationRange],
    target_volatility: float,
    max_drawdown_alert: float,
    max_single_asset_weight: float,
    optimization_method: str,
    max_sector_weight: float = 40,
    min_cash_weight: float | None = None,
    rebalance_frequency: str = "monthly",
    drift_threshold: float = 5,
    max_turnover: float = 20,
    lookback_months: int = 12,
    risk_model: str = "diagonal_shrinkage",
    expected_return_model: str = "momentum_adjusted_historical",
) -> InvestmentType:
    now = _now()
    cash_min = min_cash_weight if min_cash_weight is not None else ranges["cash"].min
    return InvestmentType(
        id=id,
        display_name=display_name,
        description=description,
        suitable_horizon=suitable_horizon,
        risk_level=risk_level,
        asset_allocation_ranges=ranges,
        risk_limits=RiskLimits(
            target_volatility=target_volatility,
            max_drawdown_alert=max_drawdown_alert,
            max_single_asset_weight=max_single_asset_weight,
            max_sector_weight=max_sector_weight,
            min_cash_weight=cash_min,
        ),
        rebalance_policy=RebalancePolicy(
            frequency=rebalance_frequency,
            weight_drift_threshold=drift_threshold,
            max_turnover=max_turnover,
        ),
        quant_settings=QuantSettings(
            optimization_method=optimization_method,
            lookback_window_months=lookback_months,
            risk_model=risk_model,
            expected_return_model=expected_return_model,
        ),
        allowed_advanced_settings=list(ADVANCED_SETTINGS),
        created_at=now,
        updated_at=now,
    )


def investment_type_templates() -> dict[str, InvestmentType]:
    templates = [
        _template(
            id="conservative",
            display_name="Conservative",
            description="자본 보존을 우선하고 현금과 채권 비중을 높게 유지하는 방어형 정책입니다.",
            suitable_horizon="1년 이상",
            risk_level="low",
            ranges=_ranges((0, 20), (50, 80), (10, 40), (0, 10)),
            target_volatility=5,
            max_drawdown_alert=-5,
            max_single_asset_weight=40,
            optimization_method="minimum_volatility",
        ),
        _template(
            id="moderate_conservative",
            display_name="Moderate Conservative",
            description="채권 중심 안정성을 유지하되 제한적인 주식 노출을 허용합니다.",
            suitable_horizon="2년 이상",
            risk_level="low_medium",
            ranges=_ranges((20, 40), (40, 65), (5, 25), (0, 10)),
            target_volatility=7,
            max_drawdown_alert=-8,
            max_single_asset_weight=35,
            optimization_method="minimum_volatility_risk_parity_blend",
        ),
        _template(
            id="balanced",
            display_name="Balanced",
            description="성장 자산과 방어 자산을 균형 있게 배치해 중간 수준의 위험을 목표로 합니다.",
            suitable_horizon="3년 이상",
            risk_level="medium",
            ranges=_ranges((35, 60), (25, 45), (5, 20), (0, 15)),
            target_volatility=9,
            max_drawdown_alert=-10,
            max_single_asset_weight=30,
            optimization_method="risk_parity",
        ),
        _template(
            id="balanced_growth",
            display_name="Balanced Growth",
            description="과도한 포트폴리오 변동성을 제한하면서 중장기 성장을 추구합니다.",
            suitable_horizon="3년 이상",
            risk_level="medium_high",
            ranges=_ranges((50, 75), (15, 35), (0, 15), (0, 15)),
            target_volatility=12,
            max_drawdown_alert=-15,
            max_single_asset_weight=30,
            optimization_method="risk_parity_max_sharpe_blend",
            min_cash_weight=5,
        ),
        _template(
            id="growth",
            display_name="Growth",
            description="높은 주식 비중으로 성장성을 우선하되 기본 리스크 한도를 유지합니다.",
            suitable_horizon="5년 이상",
            risk_level="high",
            ranges=_ranges((70, 90), (0, 20), (0, 10), (0, 15)),
            target_volatility=16,
            max_drawdown_alert=-20,
            max_single_asset_weight=35,
            optimization_method="max_sharpe",
        ),
        _template(
            id="aggressive",
            display_name="Aggressive",
            description="주식과 대체자산 중심의 높은 위험 감내형 정책입니다.",
            suitable_horizon="5년 이상",
            risk_level="very_high",
            ranges=_ranges((80, 100), (0, 10), (0, 10), (0, 20)),
            target_volatility=22,
            max_drawdown_alert=-30,
            max_single_asset_weight=40,
            optimization_method="momentum_tilted_max_sharpe",
        ),
        _template(
            id="income",
            display_name="Income",
            description="현금흐름과 안정성을 중시하는 인컴 지향 정책입니다.",
            suitable_horizon="2년 이상",
            risk_level="medium",
            ranges=_ranges((25, 50), (30, 60), (5, 20), (0, 20)),
            target_volatility=8,
            max_drawdown_alert=-10,
            max_single_asset_weight=30,
            optimization_method="income_stability",
        ),
        _template(
            id="defensive",
            display_name="Defensive",
            description="시장 급락 방어와 현금 여력을 우선하는 보수적 정책입니다.",
            suitable_horizon="1년 이상",
            risk_level="low",
            ranges=_ranges((10, 35), (40, 70), (10, 30), (0, 20)),
            target_volatility=6,
            max_drawdown_alert=-7,
            max_single_asset_weight=35,
            optimization_method="defensive_min_volatility",
        ),
        _template(
            id="momentum",
            display_name="Momentum",
            description="상대 강도와 추세를 반영해 성장 자산 비중을 동적으로 조정합니다.",
            suitable_horizon="3년 이상",
            risk_level="high",
            ranges=_ranges((50, 90), (0, 30), (0, 20), (0, 20)),
            target_volatility=15,
            max_drawdown_alert=-18,
            max_single_asset_weight=35,
            optimization_method="momentum_tilt",
        ),
        _template(
            id="quant_balanced",
            display_name="Quant Balanced",
            description="리스크 패리티와 최소 변동성 신호를 결합한 정량 균형 배분을 추구합니다.",
            suitable_horizon="3년 이상",
            risk_level="medium",
            ranges=_ranges((35, 70), (15, 45), (0, 20), (0, 20)),
            target_volatility=10,
            max_drawdown_alert=-12,
            max_single_asset_weight=30,
            optimization_method="risk_parity_min_vol_blend",
        ),
    ]
    return {item.id: item for item in templates}


def investment_type_or_none(investment_type_id: str) -> InvestmentType | None:
    return investment_type_templates().get(str(investment_type_id or "").strip().lower())


def template_to_policy_defaults(template: InvestmentType) -> dict[str, Any]:
    return {
        "asset_allocation_ranges": template.asset_allocation_ranges,
        "target_volatility": template.risk_limits.target_volatility,
        "max_drawdown_alert": template.risk_limits.max_drawdown_alert,
        "min_cash_weight": template.risk_limits.min_cash_weight,
        "max_single_asset_weight": template.risk_limits.max_single_asset_weight,
        "max_sector_weight": template.risk_limits.max_sector_weight,
        "rebalance_frequency": template.rebalance_policy.frequency,
        "weight_drift_threshold": template.rebalance_policy.weight_drift_threshold,
        "max_turnover": template.rebalance_policy.max_turnover,
        "optimization_method": template.quant_settings.optimization_method,
        "lookback_window_months": template.quant_settings.lookback_window_months,
        "risk_model": template.quant_settings.risk_model,
        "expected_return_model": template.quant_settings.expected_return_model,
    }
