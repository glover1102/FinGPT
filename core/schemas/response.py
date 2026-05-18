from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from core.schemas.fundamentals import FundamentalsCard
from core.schemas.retrieval import RetrievalItem


class ExecutionMeta(BaseModel):
    """
    Observability snapshot for a single pipeline run. Populated by the
    orchestration layer so the UI / reports can reason about how the answer
    was produced without re-parsing server logs.
    """
    primary_model: Optional[str] = Field(default=None, description="Model initially requested (e.g. qwen2.5:7b).")
    producing_model: Optional[str] = Field(default=None, description="Model whose output actually survived validation.")
    fallback_enabled: Optional[bool] = Field(default=None, description="Whether the experimental fallback route was enabled for this run.")
    fallback_model: Optional[str] = Field(default=None, description="Configured fallback model name (if any).")
    fallback_available: Optional[bool] = Field(default=None, description="Whether the fallback model was installed at runtime.")
    fallback_used: Optional[bool] = Field(default=None, description="Whether the fallback actually produced this answer.")
    retry_count: Optional[int] = Field(default=None, description="Number of structured-output retries consumed.")
    total_latency_s: Optional[float] = Field(default=None, description="End-to-end inference latency in seconds.")
    primary_latency_s: Optional[float] = Field(default=None, description="Latency spent in the primary model calls.")
    fallback_latency_s: Optional[float] = Field(default=None, description="Latency spent in the fallback model calls.")
    prompt_char_count: Optional[int] = Field(default=None, description="Final prompt size in characters.")
    chunks_used: Optional[int] = Field(default=None, description="Number of retrieval chunks that fit the prompt budget.")
    lens: Optional[str] = Field(default=None, description="Analytical lens detected from the user question (task_type).")
    context_horizon: Optional[str] = Field(default=None, description="Horizon classification used for the prompt.")
    pipeline_latency_s: Optional[float] = Field(default=None, description="Wall-clock latency for the whole pipeline run.")
    stages_ran: List[str] = Field(default_factory=list, description="Pipeline stages that actually executed (subset of collect/ingest/retrieve/infer/analyze/report).")
    extras: Dict[str, Any] = Field(default_factory=dict, description="Reserved for future additions without schema breakage.")


class Citation(BaseModel):
    source: str = Field(..., description="The type or source name.)")
    title: str = Field(..., description="The title of the source text.)")
    date: str = Field(..., description="The date the content was published.)")
    doc_id: Optional[str] = Field(default=None, description="Anchor id to the retrieved document that produced this citation.")


class KeyMetric(BaseModel):
    """Quantitative evidence extracted by the LLM from the retrieved context.

    ``value`` is kept as a free-form string so the model can return "12.4%",
    "$3.2B", "+15 bps", or raw integers without post-processing loss.
    """
    name: str = Field(..., description="Metric name, e.g. 'Revenue growth YoY'.")
    value: str = Field(..., description="Metric value copied or derived from the retrieved context.")
    unit: str = Field(default="", description="Unit for the value when known, e.g. %, bp, USD, years.")
    as_of: Optional[str] = Field(default=None, description="Date or timestamp the metric value is based on.")
    context: str = Field(default="", description="Short phrase explaining why the metric matters (<= 20 words).")
    source: str = Field(default="", description="Provider or deterministic engine that produced the metric.")
    source_type: str = Field(default="", description="Normalized source type, e.g. fred, provider_data, reputable_news.")
    calculation_method: Optional[str] = Field(default=None, description="Deterministic calculation method when this metric is derived.")
    is_deterministic: bool = Field(default=False, description="Whether this value was produced by deterministic code rather than the LLM.")
    grounding_status: str = Field(default="unknown", description="grounded, partially_grounded, ungrounded, or unknown.")
    freshness_status: str = Field(default="unknown", description="fresh, stale, or unknown.")
    evidence_doc_ids: List[str] = Field(default_factory=list, description="Doc ids that support this metric.")


class EvidenceQuality(BaseModel):
    source_type: str = Field(default="unknown", description="Normalized evidence source type.")
    reliability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    specificity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    quality_rationale: str = Field(default="")


class DecisionView(BaseModel):
    rating: Literal[
        "strong_bullish",
        "bullish",
        "neutral",
        "bearish",
        "strong_bearish",
        "avoid",
        "watchlist",
    ] = "neutral"
    time_horizon: Literal["short_term", "medium_term", "long_term", "unspecified"] = "unspecified"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    decision_summary: str = Field(default="")
    primary_thesis: str = Field(default="")
    what_would_change_my_view: List[str] = Field(default_factory=list)


class ScenarioCase(BaseModel):
    probability: float = Field(default=0.0, ge=0.0, le=1.0)
    thesis: str = Field(default="")
    drivers: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    evidence_doc_ids: List[str] = Field(default_factory=list)


class ScenarioAnalysisBundle(BaseModel):
    base_case: ScenarioCase = Field(default_factory=ScenarioCase)
    bull_case: ScenarioCase = Field(default_factory=ScenarioCase)
    bear_case: ScenarioCase = Field(default_factory=ScenarioCase)


class MonitoringPlan(BaseModel):
    next_events: List[str] = Field(default_factory=list)
    key_indicators: List[str] = Field(default_factory=list)
    alert_conditions: List[str] = Field(default_factory=list)
    review_cadence: str = Field(default="")


class RiskManagement(BaseModel):
    main_risks: List[str] = Field(default_factory=list)
    invalidating_conditions: List[str] = Field(default_factory=list)
    position_sizing_comment: str = Field(default="")
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"


class ConfidenceRationale(BaseModel):
    raw_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    final_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    positive_factors: List[str] = Field(default_factory=list)
    negative_factors: List[str] = Field(default_factory=list)
    caps_applied: List[str] = Field(default_factory=list)
    evidence_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    numeric_grounding_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quality_average: float = Field(default=0.0, ge=0.0, le=1.0)


class QualityMetrics(BaseModel):
    claim_support_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    numeric_grounding_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quality_average: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    stale_context_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    source_diversity: int = Field(default=0, ge=0)
    required_bucket_coverage: float = Field(default=0.0, ge=0.0, le=1.0)


class CatalystTimeline(BaseModel):
    """Catalysts/risks bucketed by when they are expected to matter."""
    near_term: List[str] = Field(default_factory=list, description="Items expected to matter within 0–3 months.")
    mid_term: List[str] = Field(default_factory=list, description="Items expected to matter within 3–12 months.")
    long_term: List[str] = Field(default_factory=list, description="Items expected to matter beyond 12 months.")


class AnalysisResponse(BaseModel):
    ticker: str
    question: str
    status: Literal["success", "partial", "failed"] = Field(default="success", description="Execution status of the pipeline.")
    error_metadata: Optional[str] = Field(default=None, description="Reason for partial or failed status.")
    summary: str = Field(..., description="High-level answer summary.")
    bull_points: List[str] = Field(default_factory=list, description="Extracted positive factors or catalysts.")
    bear_points: List[str] = Field(default_factory=list, description="Extracted negative factors or risks.")
    # Evidence arrays are parallel to bull_points/bear_points. Index i of
    # bull_evidence_ids carries the doc_ids that ground bull_points[i]. Lists
    # may be empty when the inference layer does not supply linkage.
    bull_evidence_ids: List[List[str]] = Field(default_factory=list, description="Per-bullet evidence doc_ids, parallel to bull_points.")
    bear_evidence_ids: List[List[str]] = Field(default_factory=list, description="Per-bullet evidence doc_ids, parallel to bear_points.")
    # Extended deep-analysis fields. Populated by the Ollama adapter when the
    # LLM follows the v2 schema; safe defaults keep older adapters and legacy
    # cached responses readable without migration.
    key_metrics: List[KeyMetric] = Field(default_factory=list, description="Quantitative evidence extracted from the retrieved context.")
    fundamentals: Optional[FundamentalsCard] = Field(default=None, description="Verified yfinance fundamentals snapshot injected outside RAG.")
    catalyst_timeline: CatalystTimeline = Field(default_factory=CatalystTimeline, description="Catalysts/risks bucketed by time horizon.")
    open_questions: List[str] = Field(default_factory=list, description="Concrete unresolved questions for follow-up research.")
    uncertainty: str = Field(default="", description="Model-reported narrative on evidence gaps or contradictions.")
    sentiment: str = Field(..., description="The derived sentiment label, e.g., 'Positive', 'Neutral', 'Negative'.")
    confidence: float = Field(default=0.0, description="A confidence score between 0 and 1.")
    conclusion: str = Field(..., description="The final concluding thought or recommendation.")
    citations: List[Citation] = Field(default_factory=list, description="Citations used in the response.")
    raw_context: List[RetrievalItem] = Field(default_factory=list, description="The raw retrieved items that were fed into the model.")
    execution_meta: Optional[ExecutionMeta] = Field(default=None, description="Observability metadata captured during pipeline execution.")
    decision_view: DecisionView = Field(default_factory=DecisionView, description="Decision-oriented investment view.")
    scenario_analysis: ScenarioAnalysisBundle = Field(default_factory=ScenarioAnalysisBundle, description="Base, bull, and bear scenario bundle.")
    monitoring_plan: MonitoringPlan = Field(default_factory=MonitoringPlan, description="Events and indicators to monitor after the run.")
    risk_management: RiskManagement = Field(default_factory=RiskManagement, description="Risk management and invalidation conditions.")
    confidence_rationale: ConfidenceRationale = Field(default_factory=ConfidenceRationale, description="Defensible confidence inputs and caps.")
    quality_metrics: QualityMetrics = Field(default_factory=QualityMetrics, description="Deterministic output quality metrics.")
    evidence_quality: Dict[str, EvidenceQuality] = Field(default_factory=dict, description="Evidence quality scores keyed by doc_id.")
    warnings: List[str] = Field(default_factory=list, description="Grounding, evidence, freshness, or execution warnings.")


class CompareResponse(BaseModel):
    """
    Batch result for ``POST /api/v1/research/compare``.

    Returned as a single JSON document (no streaming) so the UI can render a
    consolidated comparison view atomically. Individual errors are surfaced via
    each ticker's AnalysisResponse.status/error_metadata rather than failing the
    whole batch.
    """
    question: str
    tickers: List[str]
    results: Dict[str, AnalysisResponse] = Field(
        default_factory=dict,
        description="Ticker -> AnalysisResponse. Failures show up as status='failed' responses.",
    )
    elapsed_s: float = Field(default=0.0, description="Wall-clock latency for the whole batch.")
    concurrency: int = Field(default=1, description="Parallelism that was actually used.")
