from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PortfolioPosition(BaseModel):
    """Single portfolio line item used by the deterministic risk engine."""

    ticker: str = Field(..., description="Ticker or proxy symbol, e.g. MSFT, TLT, GLD, BTC-USD.")
    weight: float = Field(..., description="Portfolio weight as decimal, e.g. 0.25 for 25%.")
    asset_class: str | None = Field(default=None, description="Optional explicit asset class override.")
    quantity: float | None = Field(default=None, description="Optional quantity for future P&L extension.")
    price: float | None = Field(default=None, description="Optional latest price for audit display.")

    @field_validator("ticker", mode="before")
    @classmethod
    def _clean_ticker(cls, value: Any) -> str:
        return str(value or "").strip().upper()

    @field_validator("asset_class", mode="before")
    @classmethod
    def _clean_asset_class(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip().lower()
        return cleaned or None


class PortfolioRiskRequest(BaseModel):
    """Internal/API request for portfolio-level quant risk analysis."""

    positions: list[PortfolioPosition] = Field(..., min_length=1, max_length=100)
    base_currency: str = Field(default="USD")
    lookback_days: int = Field(default=90, ge=20, le=756)
    shocks: dict[str, dict[str, float]] | None = Field(
        default=None,
        description="Optional scenario -> asset_class/ticker shock return overrides as decimals.",
    )

    @field_validator("base_currency", mode="before")
    @classmethod
    def _clean_currency(cls, value: Any) -> str:
        return str(value or "USD").strip().upper() or "USD"


class PortfolioPositionRisk(BaseModel):
    ticker: str
    asset_class: str
    weight: float
    normalized_weight: float
    risk_contribution_pct: float
    concentration_flag: bool = False
    duration_proxy: float | None = None
    notes: list[str] = Field(default_factory=list)


class PortfolioStressRow(BaseModel):
    scenario: str
    portfolio_impact_pct: float
    direction: Literal["positive", "negative", "mixed", "flat"]
    largest_loss_ticker: str = ""
    largest_loss_pct: float = 0.0
    position_impacts: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""


class PortfolioRiskResponse(BaseModel):
    status: Literal["success", "partial", "failed"] = "success"
    as_of: str
    base_currency: str = "USD"
    total_weight: float
    gross_exposure: float
    net_exposure: float
    hhi_concentration: float
    max_position_weight: float
    concentration_level: Literal["low", "medium", "high"]
    positions: list[PortfolioPositionRisk]
    factor_exposures: dict[str, float] = Field(default_factory=dict)
    stress_table: list[PortfolioStressRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_meta: dict[str, Any] = Field(default_factory=dict)


class PortfolioOptimizeV2Request(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    method: str = "equal_weight"
    benchmark: str = "SPY"
    lookback_days: int = Field(default=252, ge=2, le=5000)
    start_date: str | None = None
    end_date: str | None = None
    max_weight: float = Field(default=1.0, gt=0, le=1.0)
    covariance_method: str = "sample"
    shrinkage_alpha: float = Field(default=0.1, ge=0.0, le=1.0)
    returns_by_asset: dict[str, list[float]] | None = None

    @field_validator("tickers", mode="before")
    @classmethod
    def _clean_tickers(cls, value: Any) -> list[str]:
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

    @field_validator("method", mode="before")
    @classmethod
    def _clean_method(cls, value: Any) -> str:
        return str(value or "equal_weight").strip().lower() or "equal_weight"

    @field_validator("benchmark", mode="before")
    @classmethod
    def _clean_benchmark(cls, value: Any) -> str:
        return str(value or "SPY").strip().upper() or "SPY"

    @field_validator("covariance_method", mode="before")
    @classmethod
    def _clean_covariance_method(cls, value: Any) -> str:
        return str(value or "sample").strip().lower() or "sample"


class PortfolioOptimizeV2Response(BaseModel):
    status: Literal["success", "partial", "failed"] = "failed"
    method: str = "equal_weight"
    weights: dict[str, float] = Field(default_factory=dict)
    sum_weights: float = 0.0
    missing_assets: list[str] = Field(default_factory=list)
    capped_assets: list[str] = Field(default_factory=list)
    risk_contributions: dict[str, float] = Field(default_factory=dict)
    expected_annual_return: float = 0.0
    annualized_volatility: float = 0.0
    sharpe: float = 0.0
    correlation_matrix: dict[str, dict[str, float]] = Field(default_factory=dict)
    data_range: dict[str, str] = Field(default_factory=dict)
    return_counts: dict[str, int] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
