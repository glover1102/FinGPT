from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


FreshnessStatus = Literal["fresh", "stale", "unknown"]
ProviderEntitlementStatus = Literal["ok", "warning", "entitlement_required", "unavailable", "unknown"]


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
