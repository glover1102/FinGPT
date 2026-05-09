from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


InvestmentTypeId = Literal[
    "conservative",
    "moderate_conservative",
    "balanced",
    "balanced_growth",
    "growth",
    "aggressive",
    "income",
    "defensive",
    "momentum",
    "quant_balanced",
]

AutomationLevel = Literal["manual", "alert_only", "confirm_before_apply", "auto_paper_rebalance"]
PolicyStatus = Literal["draft", "active", "inactive", "archived"]
RecommendationStatus = Literal["generated", "partial", "failed", "activated"]
RebalanceStatus = Literal["pending_user_approval", "approved", "rejected", "deferred", "applied_paper", "expired"]
ConstraintStatus = Literal["pass", "warning", "fail"]


class AllocationRange(BaseModel):
    min: float = Field(ge=0, le=100)
    max: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _validate_order(self) -> "AllocationRange":
        if self.min > self.max:
            raise ValueError("allocation range min cannot exceed max")
        return self


class RiskLimits(BaseModel):
    target_volatility: float = Field(ge=0, le=100)
    max_drawdown_alert: float = Field(le=0)
    max_single_asset_weight: float = Field(gt=0, le=100)
    max_sector_weight: float = Field(gt=0, le=100)
    min_cash_weight: float = Field(ge=0, le=100)


class RebalancePolicy(BaseModel):
    frequency: str = "monthly"
    weight_drift_threshold: float = Field(default=5, ge=0, le=100)
    max_turnover: float = Field(default=20, ge=0, le=100)


class QuantSettings(BaseModel):
    optimization_method: str = "risk_parity"
    lookback_window_months: int = Field(default=12, ge=1, le=120)
    risk_model: str = "sample"
    expected_return_model: str = "historical"


class InvestmentType(BaseModel):
    id: str
    display_name: str
    description: str
    suitable_horizon: str
    risk_level: str
    asset_allocation_ranges: dict[str, AllocationRange]
    risk_limits: RiskLimits
    rebalance_policy: RebalancePolicy
    quant_settings: QuantSettings
    allowed_advanced_settings: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class PortfolioPolicy(BaseModel):
    policy_id: str
    user_id: str | None = None
    portfolio_name: str
    investment_type: str
    universe_id: str = "default_multi_asset"
    initial_capital: float = Field(default=10_000_000, ge=0)
    monthly_contribution: float = Field(default=0, ge=0)
    target_return: float | None = None
    asset_allocation_ranges: dict[str, AllocationRange]
    target_volatility: float = Field(ge=0, le=100)
    max_drawdown_alert: float = Field(le=0)
    min_cash_weight: float = Field(ge=0, le=100)
    max_single_asset_weight: float = Field(gt=0, le=100)
    max_sector_weight: float = Field(gt=0, le=100)
    rebalance_frequency: str = "monthly"
    weight_drift_threshold: float = Field(default=5, ge=0, le=100)
    max_turnover: float = Field(default=20, ge=0, le=100)
    optimization_method: str = "risk_parity"
    lookback_window_months: int = Field(default=12, ge=1, le=120)
    risk_model: str = "sample"
    expected_return_model: str = "historical"
    automation_level: AutomationLevel = "alert_only"
    benchmark: str = "SPY"
    status: PolicyStatus = "draft"
    created_at: str
    updated_at: str
    audit: dict[str, Any] = Field(default_factory=dict)

    @field_validator("investment_type", "universe_id", "optimization_method", "risk_model", "expected_return_model", mode="before")
    @classmethod
    def _clean_lower(cls, value: Any) -> str:
        return str(value or "").strip().lower()

    @field_validator("benchmark", mode="before")
    @classmethod
    def _clean_benchmark(cls, value: Any) -> str:
        cleaned = str(value or "SPY").strip().upper()
        return cleaned or "SPY"


class PolicyCreateRequest(BaseModel):
    portfolio_name: str = "AI Portfolio"
    investment_type: str = "balanced_growth"
    universe_id: str = "default_multi_asset"
    initial_capital: float = Field(default=10_000_000, ge=0)
    monthly_contribution: float = Field(default=0, ge=0)
    target_return: float | None = None
    policy_overrides: dict[str, Any] = Field(default_factory=dict)
    automation_level: AutomationLevel = "alert_only"
    benchmark: str = "SPY"


class PolicyUpdateRequest(BaseModel):
    portfolio_name: str | None = None
    universe_id: str | None = None
    initial_capital: float | None = Field(default=None, ge=0)
    monthly_contribution: float | None = Field(default=None, ge=0)
    target_return: float | None = None
    policy_overrides: dict[str, Any] = Field(default_factory=dict)
    automation_level: AutomationLevel | None = None
    benchmark: str | None = None
    status: PolicyStatus | None = None


class PortfolioWeight(BaseModel):
    ticker: str
    name: str = ""
    asset_class: str = ""
    sector: str | None = None
    weight: float = Field(description="Weight in percent.")
    weight_decimal: float = Field(description="Weight as decimal.")
    role: str = ""
    key_risk: str = ""
    constraint_status: str = "unchecked"


class ConstraintViolation(BaseModel):
    rule: str
    severity: Literal["warning", "fail"]
    message: str
    ticker: str | None = None
    actual: float | None = None
    limit: float | None = None


class ConstraintCheck(BaseModel):
    status: ConstraintStatus
    violations: list[ConstraintViolation] = Field(default_factory=list)
    allocation_by_asset_class: dict[str, float] = Field(default_factory=dict)


class DataQuality(BaseModel):
    universe_id: str = "default_multi_asset"
    universe_source: Literal["preset", "direct_input", "unknown"] = "preset"
    universe_label: str = "Default Multi-Asset"
    asset_count: int = 0
    available_asset_count: int = 0
    universe_available: bool = True
    price_data_available: bool = True
    backtest_available: bool = True
    missing_assets: list[str] = Field(default_factory=list)
    insufficient_assets: list[str] = Field(default_factory=list)
    used_assets: list[str] = Field(default_factory=list)
    metadata_coverage: dict[str, Any] = Field(default_factory=dict)
    hydration: dict[str, Any] = Field(default_factory=dict)
    unavailable_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class UniversePreset(BaseModel):
    id: str
    display_name: str
    source_type: Literal["preset", "direct_input"] = "preset"
    description: str = ""
    asset_count: int = 0
    asset_class_mix: dict[str, int] = Field(default_factory=dict)
    sample_assets: list[str] = Field(default_factory=list)
    request_hint: str = ""


class PortfolioRecommendation(BaseModel):
    recommendation_id: str
    policy_id: str
    created_at: str
    method: str
    universe_id: str
    weights: list[PortfolioWeight] = Field(default_factory=list)
    expected_metrics: dict[str, Any] = Field(default_factory=dict)
    backtest_metrics: dict[str, Any] = Field(default_factory=dict)
    risk_metrics: dict[str, Any] = Field(default_factory=dict)
    constraint_check: ConstraintCheck
    ai_explanation: str = ""
    status: RecommendationStatus = "generated"
    data_quality: DataQuality = Field(default_factory=DataQuality)
    audit: dict[str, Any] = Field(default_factory=dict)


class PortfolioSnapshot(BaseModel):
    snapshot_id: str
    policy_id: str
    date: str
    current_weights: dict[str, float] = Field(default_factory=dict)
    portfolio_value: float | None = None
    return_since_inception: float | None = None
    period_return: float | None = None
    benchmark_return: float | None = None
    volatility: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    asset_contribution: dict[str, float] = Field(default_factory=dict)
    risk_contribution: dict[str, float] = Field(default_factory=dict)
    created_at: str
    audit: dict[str, Any] = Field(default_factory=dict)


class RecommendedChange(BaseModel):
    ticker: str
    current_weight: float
    target_weight: float
    change: float
    action: Literal["increase", "reduce", "hold"]


class RebalanceSignal(BaseModel):
    signal_id: str
    policy_id: str
    created_at: str
    rebalance_required: bool
    trigger_type: list[str] = Field(default_factory=list)
    current_weights: dict[str, float] = Field(default_factory=dict)
    target_weights: dict[str, float] = Field(default_factory=dict)
    recommended_changes: list[RecommendedChange] = Field(default_factory=list)
    risk_before: dict[str, Any] = Field(default_factory=dict)
    estimated_risk_after: dict[str, Any] = Field(default_factory=dict)
    status: RebalanceStatus = "pending_user_approval"
    ai_explanation: str = ""
    expires_at: str | None = None
    next_review_at: str | None = None
    decision_reason: str | None = None
    approved_by: str | None = None
    rejected_reason: str | None = None
    deferred_until: str | None = None
    turnover_estimate: float | None = None
    post_trade_policy_check: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)


class PortfolioHistoryEvent(BaseModel):
    event_id: str
    policy_id: str
    event_type: str
    event_time: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    summary: str = ""
    actor: str = "system"
    request_id: str | None = None
    config_hash: str | None = None
    universe_hash: str | None = None
    audit: dict[str, Any] = Field(default_factory=dict)


class GeneratePortfolioRequest(PolicyCreateRequest):
    policy_id: str | None = None


class GeneratePortfolioResponse(BaseModel):
    policy: PortfolioPolicy
    recommendation: PortfolioRecommendation
    warnings: list[str] = Field(default_factory=list)
    data_quality: DataQuality


class RebalanceCheckRequest(BaseModel):
    policy_id: str
    current_weights: dict[str, float] = Field(default_factory=dict)


class RebalanceActionRequest(BaseModel):
    reason: str | None = None
    actor: str = "user"
    deferred_until: str | None = None


class DataActivationRequest(BaseModel):
    policy_id: str | None = None
    universe_id: str | None = None
    tickers: list[str] = Field(default_factory=list)
    hydrate_prices: bool = True
    hydrate_fundamentals: bool = True
    dry_run: bool = False
    max_assets: int = Field(default=250, ge=1, le=1000)
    min_price_rows: int = Field(default=42, ge=2, le=5000)


class SecDataRefreshRequest(BaseModel):
    policy_id: str | None = None
    universe_id: str | None = None
    tickers: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=lambda: ["10-K", "10-Q", "8-K"])
    lookback_days: int = Field(default=365 * 3, ge=1, le=365 * 15)
    max_assets: int = Field(default=250, ge=1, le=1000)
    hydrate_financials: bool = True
    dry_run: bool = False

    @field_validator("forms", mode="before")
    @classmethod
    def _normalize_forms(cls, value: Any) -> list[str]:
        if value is None:
            return ["10-K", "10-Q", "8-K"]
        raw_values = value if isinstance(value, list) else str(value).split(",")
        forms = []
        for raw in raw_values:
            form = str(raw or "").upper().strip()
            if not form:
                continue
            canonical = form.split("/", 1)[0]
            if canonical not in {"10-K", "10-Q", "8-K"}:
                raise ValueError(f"unsupported SEC form: {form}")
            if canonical not in forms:
                forms.append(canonical)
        return forms or ["10-K", "10-Q", "8-K"]


class SnapshotJobRequest(BaseModel):
    policy_id: str | None = None
    active_only: bool = True


class ReportGenerateRequest(BaseModel):
    policy_id: str
    report_type: Literal["weekly", "monthly", "rebalance"] = "weekly"
