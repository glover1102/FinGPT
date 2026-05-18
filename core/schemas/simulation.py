from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ScenarioType = Literal["base", "bull", "bear", "tail"]
ScenarioDirection = Literal["bullish", "bearish", "neutral", "mixed"]
SimulationStatus = Literal["success", "partial", "failed"]
AgentStance = Literal["support", "oppose", "neutral", "mixed"]
DecisionBias = Literal[
    "avoid",
    "watchlist",
    "partial_position",
    "constructive",
    "aggressive",
    "mixed",
]
UncertaintyLevel = Literal["low", "medium", "high"]


class AgentPersona(BaseModel):
    id: str
    name: str
    role: str
    horizon: str
    risk_preference: str
    bias: str
    evidence_focus: list[str] = Field(default_factory=list)
    decision_rule: str


class ScenarioCase(BaseModel):
    id: str
    name: str
    type: ScenarioType
    probability: float = Field(ge=0.0, le=1.0)
    direction: ScenarioDirection
    time_horizon: str
    assumptions: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    invalidation_signals: list[str] = Field(default_factory=list)
    expected_reaction: str
    evidence_doc_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AgentView(BaseModel):
    agent_id: str
    scenario_id: str
    stance: AgentStance
    confidence: float = Field(ge=0.0, le=1.0)
    thesis: str
    key_evidence_doc_ids: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    change_mind_conditions: list[str] = Field(default_factory=list)


class RiskTrigger(BaseModel):
    category: str
    trigger: str
    direction: ScenarioDirection
    monitoring_data: str
    response: str
    evidence_doc_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class DecisionImplication(BaseModel):
    bias: DecisionBias
    entry_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    monitoring_indicators: list[str] = Field(default_factory=list)
    risk_management: list[str] = Field(default_factory=list)
    uncertainty: UncertaintyLevel
    disclaimer: str = "This is a scenario-based research aid, not personalized financial advice."


class ScenarioScores(BaseModel):
    evidence_strength: float = Field(ge=0.0, le=1.0)
    consensus_score: float = Field(ge=0.0, le=1.0)
    disagreement_score: float = Field(ge=0.0, le=1.0)
    asymmetry_score: float = Field(ge=0.0, le=1.0)
    timing_score: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)


class ScenarioSimulationDiagnostics(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    llm_used: bool = False
    evidence_doc_id_coverage: float | None = None
    scenario_probability_sum_before_normalization: float | None = None
    scenario_probability_sum_after_normalization: float | None = None


class ScenarioSimulationResult(BaseModel):
    status: SimulationStatus
    personas: list[AgentPersona] = Field(default_factory=list)
    scenarios: list[ScenarioCase] = Field(default_factory=list)
    agent_views: list[AgentView] = Field(default_factory=list)
    consensus: dict[str, Any] = Field(default_factory=dict)
    disagreement_map: dict[str, Any] = Field(default_factory=dict)
    market_reaction_table: list[dict[str, Any]] = Field(default_factory=list)
    risk_triggers: list[RiskTrigger] = Field(default_factory=list)
    decision_implication: DecisionImplication | None = None
    scores: ScenarioScores | None = None
    diagnostics: ScenarioSimulationDiagnostics = Field(default_factory=ScenarioSimulationDiagnostics)
