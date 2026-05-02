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
