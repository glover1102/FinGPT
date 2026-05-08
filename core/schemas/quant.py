from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


FreshnessStatus = Literal["fresh", "stale", "unknown"]
ProviderEntitlementStatus = Literal["ok", "warning", "entitlement_required", "unavailable", "unknown"]
QuantStatus = Literal["success", "partial", "failed", "empty"]
ResearchScoreStatus = Literal["disabled", "fresh", "expired", "sparse_evidence", "unavailable", "invalid"]
FreshnessProfile = Literal["research_default", "decision_review", "historical_lab"]


class ProviderStatus(BaseModel):
    provider: str
    status: str = "unknown"
    entitlement_status: ProviderEntitlementStatus = "unknown"
    latency_ms: Optional[float] = None
    cache_hit: Optional[bool] = None
    stale_after: Optional[str] = None
    quality_score: Optional[float] = None
    detail: str = ""


class DataFreshnessAudit(BaseModel):
    as_of: str = "unknown"
    freshness_status: FreshnessStatus = "unknown"
    source: str = ""
    evidence_doc_ids: list[str] = Field(default_factory=list)
    missing_reason: str = ""


class QuantMetric(BaseModel):
    name: str
    value: str
    unit: str = ""
    as_of: str = "unknown"
    context: str = ""
    source: str = "deterministic_quant"
    freshness_status: FreshnessStatus = "unknown"
    evidence_doc_ids: list[str] = Field(default_factory=list)


class QuantSnapshot(BaseModel):
    asset_class: str
    target: str
    generated_at: str
    metrics: list[QuantMetric] = Field(default_factory=list)
    duration_or_proxy: Optional[dict[str, Any]] = None
    rate_shock_scenarios: list[dict[str, Any]] = Field(default_factory=list)
    factor_exposures: dict[str, Any] = Field(default_factory=dict)
    stress_table: list[dict[str, Any]] = Field(default_factory=list)
    substituted_buckets: list[str] = Field(default_factory=list)
    missing_axes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ModelCapabilityProfile(BaseModel):
    route: str
    resolved_model: str
    json_reliability: Literal["high", "medium", "low"]
    korean_reliability: Literal["high", "medium", "low"]
    context_window: int
    structured_output_support: bool
    finance_reasoning: Literal["high", "medium", "low"]
    latency_profile: Literal["fast", "medium", "slow", "unknown"]
    gpu_required: bool = False
    recommended_tasks: list[str] = Field(default_factory=list)
    restricted_tasks: list[str] = Field(default_factory=list)


class RunManifest(BaseModel):
    run_kind: str
    route: str
    asset_class: str = ""
    target: str = ""
    question_hash: str = ""
    generated_at: str = ""
    data_sources: list[str] = Field(default_factory=list)
    model_route: str = ""
    validation_checks: dict[str, Any] = Field(default_factory=dict)


def _clean_tickers(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value.replace(",", " ").split() if isinstance(value, str) else list(value)
    seen: set[str] = set()
    tickers: list[str] = []
    for item in raw:
        ticker = str(item or "").strip().upper()
        if ticker and ticker not in seen:
            tickers.append(ticker)
            seen.add(ticker)
    return tickers


class QuantRunDiagnostics(BaseModel):
    lookahead_safe: bool = True
    signal_shift_bars: int = 1
    execution_assumption: str = "next_bar_close"
    data_source: str = "data_mart:prices_daily"
    freshness_policy: dict[str, Any] = Field(default_factory=dict)
    missing_assets: list[str] = Field(default_factory=list)
    stale_assets: list[str] = Field(default_factory=list)
    excluded_assets: list[str] = Field(default_factory=list)
    price_counts: dict[str, int] = Field(default_factory=dict)
    latest_price_dates: dict[str, str] = Field(default_factory=dict)
    expected_latest_date: str = "unknown"
    market_calendar_lag_days: dict[str, int] = Field(default_factory=dict)
    asset_freshness: dict[str, dict[str, Any]] = Field(default_factory=dict)
    research_score_used: bool = False
    research_score_status: ResearchScoreStatus = "disabled"
    research_score_provenance: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fingpt_forecaster_signals: dict[str, dict[str, Any]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class QuantTradeEvent(BaseModel):
    signal_date: str
    execution_date: str
    ticker: str
    previous_weight: float = 0.0
    target_weight: float = 0.0
    delta_weight: float = 0.0
    price: float | None = None
    cost: float = 0.0
    slippage_bps: float = 0.0
    transaction_cost_bps: float = 0.0
    reason: str = "rebalance"
    selected: bool | None = None
    score: float | None = None
    diagnostics: list[str] = Field(default_factory=list)


class QuantArtifactManifest(BaseModel):
    run_id: str
    root: str
    manifest: str
    config: str = ""
    metrics: str = ""
    diagnostics: str = ""
    equity_curve: str = ""
    drawdown_curve: str = ""
    trades: str = ""
    signals: str = ""
    weights: str = ""


class QuantFeatureSpec(BaseModel):
    id: str
    lookback: int | None = Field(default=None, ge=1, le=5000)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", mode="before")
    @classmethod
    def _clean_id(cls, value: Any) -> str:
        return str(value or "").strip().lower()


class QuantFeaturePreviewRequest(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    benchmark: str = "SPY"
    start_date: str | None = None
    end_date: str | None = None
    features: list[QuantFeatureSpec] = Field(default_factory=list)
    freshness_profile: FreshnessProfile = "research_default"
    require_fresh_prices: bool = False
    max_market_calendar_lag_days: int = Field(default=3, ge=0, le=30)

    @field_validator("tickers", mode="before")
    @classmethod
    def _clean_request_tickers(cls, value: Any) -> list[str]:
        return _clean_tickers(value)

    @field_validator("benchmark", mode="before")
    @classmethod
    def _clean_benchmark(cls, value: Any) -> str:
        return str(value or "SPY").strip().upper() or "SPY"

    @field_validator("freshness_profile", mode="before")
    @classmethod
    def _clean_freshness_profile(cls, value: Any) -> str:
        clean = str(value or "research_default").strip().lower()
        return clean if clean in {"research_default", "decision_review", "historical_lab"} else "research_default"

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _clean_date(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None


class QuantFeatureRow(BaseModel):
    ticker: str
    as_of: str
    source: str = "data_mart:prices_daily"
    features: dict[str, float | None] = Field(default_factory=dict)
    freshness_status: FreshnessStatus = "unknown"
    diagnostics: list[str] = Field(default_factory=list)


class QuantFeaturePreviewResponse(BaseModel):
    status: QuantStatus = "empty"
    as_of: str = "unknown"
    rows: list[QuantFeatureRow] = Field(default_factory=list)
    diagnostics: QuantRunDiagnostics = Field(default_factory=QuantRunDiagnostics)
    warnings: list[str] = Field(default_factory=list)


class QuantSignalGenerateRequest(QuantFeaturePreviewRequest):
    template: str = "momentum_ranking"
    use_research_score: bool = False
    research_max_age_days: int = Field(default=7, ge=1, le=365)

    @field_validator("template", mode="before")
    @classmethod
    def _clean_template(cls, value: Any) -> str:
        return str(value or "momentum_ranking").strip().lower()


class QuantSignalRow(BaseModel):
    date: str
    ticker: str
    factor_values: dict[str, float | None] = Field(default_factory=dict)
    research_score: float | None = None
    final_score: float | None = None
    signal: float = 0.0
    execution_date: str | None = None
    lookahead_policy: str = "close_signal_next_bar_execution"
    diagnostics: list[str] = Field(default_factory=list)


class QuantSignalGenerateResponse(BaseModel):
    status: QuantStatus = "empty"
    as_of: str = "unknown"
    rows: list[QuantSignalRow] = Field(default_factory=list)
    diagnostics: QuantRunDiagnostics = Field(default_factory=QuantRunDiagnostics)
    warnings: list[str] = Field(default_factory=list)


class QuantBacktestRequest(BaseModel):
    strategy_id: str | None = None
    template: str = "momentum_ranking"
    tickers: list[str] = Field(default_factory=list)
    benchmark: str = "SPY"
    start_date: str | None = None
    end_date: str | None = None
    freshness_profile: FreshnessProfile = "research_default"
    rebalance_every: int = Field(default=21, ge=1, le=252)
    lookback: int = Field(default=63, ge=2, le=5000)
    top_n: int = Field(default=2, ge=1, le=50)
    portfolio_method: str = "equal_weight"
    transaction_cost_bps: float = Field(default=5.0, ge=0, le=1000)
    slippage_bps: float = Field(default=2.0, ge=0, le=1000)
    use_research_score: bool = False
    research_max_age_days: int = Field(default=7, ge=1, le=365)
    require_fresh_prices: bool = False
    max_market_calendar_lag_days: int = Field(default=3, ge=0, le=30)

    @field_validator("tickers", mode="before")
    @classmethod
    def _clean_backtest_tickers(cls, value: Any) -> list[str]:
        return _clean_tickers(value)

    @field_validator("benchmark", mode="before")
    @classmethod
    def _clean_backtest_benchmark(cls, value: Any) -> str:
        return str(value or "SPY").strip().upper() or "SPY"

    @field_validator("freshness_profile", mode="before")
    @classmethod
    def _clean_backtest_freshness_profile(cls, value: Any) -> str:
        clean = str(value or "research_default").strip().lower()
        return clean if clean in {"research_default", "decision_review", "historical_lab"} else "research_default"

    @field_validator("template", mode="before")
    @classmethod
    def _clean_template(cls, value: Any) -> str:
        return str(value or "momentum_ranking").strip().lower() or "momentum_ranking"

    @field_validator("portfolio_method", mode="before")
    @classmethod
    def _clean_portfolio_method(cls, value: Any) -> str:
        return str(value or "equal_weight").strip().lower() or "equal_weight"

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _clean_backtest_date(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None


class QuantBacktestResponse(BaseModel):
    run_id: str
    status: QuantStatus
    template: str
    tickers: list[str] = Field(default_factory=list)
    benchmark: str = "SPY"
    date_range: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    drawdown_curve: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    weights: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: QuantRunDiagnostics = Field(default_factory=QuantRunDiagnostics)
    artifacts: QuantArtifactManifest | None = None
