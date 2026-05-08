from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MacroQualityStatus = Literal["ok", "partial", "stale", "unavailable"]


class MacroSeriesDefinition(BaseModel):
    series_id: str
    display_name: str
    category: str
    subcategory: str = ""
    provider: str
    provider_series_id: str
    country: str = "US"
    region: str = "US"
    frequency: str
    unit: str
    transform: str = "level"
    stale_after_days: int = 30
    importance: str = "medium"
    description: str = ""
    interpretation_hint: str = ""
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class MacroObservation(BaseModel):
    date: str
    value: float | None = None
    raw_value: float | None = None
    source: str = "unknown"
    revised: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MacroDataQuality(BaseModel):
    status: MacroQualityStatus = "unavailable"
    provider: str = "unknown"
    last_updated: str | None = None
    missing_series: list[str] = Field(default_factory=list)
    stale_series: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MacroSeriesResponse(BaseModel):
    series_id: str
    display_name: str
    category: str
    unit: str
    frequency: str
    provider: str
    observations: list[MacroObservation] = Field(default_factory=list)
    latest: MacroObservation | None = None
    changes: dict[str, float | str | None] = Field(default_factory=dict)
    data_quality: MacroDataQuality


class MacroSignal(BaseModel):
    name: str
    value: str
    score: float
    direction: str = "unknown"
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    data_quality: MacroDataQuality


class MacroRegime(BaseModel):
    name: str
    display_name: str
    confidence: float
    risk_level: str
    scores: dict[str, float] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    interpretation: str = ""


class AssetImpact(BaseModel):
    asset_class: str
    impact: str
    confidence: float
    reason: str
    key_risks: list[str] = Field(default_factory=list)
    related_indicators: list[str] = Field(default_factory=list)


class PortfolioPolicyHint(BaseModel):
    regime: str
    equity_bias: str
    bond_bias: str
    cash_bias: str
    alternative_bias: str
    duration_bias: str
    credit_bias: str
    risk_level: str
    rebalance_attention: bool
    explanation: str
    warnings: list[str] = Field(default_factory=list)
    data_quality: MacroDataQuality
    advisory_only: bool = True


class MacroOverview(BaseModel):
    as_of: str
    key_indicators: list[MacroSeriesResponse] = Field(default_factory=list)
    signals: list[MacroSignal] = Field(default_factory=list)
    regime: MacroRegime
    asset_impact_summary: list[AssetImpact] = Field(default_factory=list)
    data_quality: MacroDataQuality


class MacroResearchContext(BaseModel):
    regime: MacroRegime
    risk_level: str
    key_indicators: list[MacroSeriesResponse] = Field(default_factory=list)
    signals: list[MacroSignal] = Field(default_factory=list)
    asset_impacts: list[AssetImpact] = Field(default_factory=list)
    portfolio_hints: PortfolioPolicyHint
    ticker_relevance: dict[str, list[str]] = Field(default_factory=dict)
    data_quality_warnings: list[str] = Field(default_factory=list)


class MacroBriefRequest(BaseModel):
    audience: str = "research"
    include_prompt: bool = False
    use_llm: bool = False
    model: str | None = None
    timeout_s: float = Field(default=45.0, ge=1.0, le=180.0)


class MacroBriefResponse(BaseModel):
    status: str
    provider: str
    is_fallback: bool
    content: str
    prompt_template: str | None = None
    data_quality: MacroDataQuality
    warnings: list[str] = Field(default_factory=list)


class MacroReportResponse(BaseModel):
    status: str
    format: str = "markdown"
    generated_at: str
    filename: str
    content: str
    data_quality: MacroDataQuality
    warnings: list[str] = Field(default_factory=list)
