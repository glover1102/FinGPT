from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FinGPTTask = Literal["sentiment", "headline", "ner", "relation", "fiqa_qa", "forecaster"]
FinGPTEvaluationTask = FinGPTTask | Literal["mixed"]


class FinGPTDatasetSpec(BaseModel):
    task: FinGPTTask
    hf_id: str
    default_split: str = "train"
    local_archive_hint: str = ""
    expected_columns: list[str] = Field(default_factory=list)
    use_case: str


class FinGPTModelSpec(BaseModel):
    task: FinGPTTask
    hf_id: str
    base_model: str = ""
    requires_gpu: bool = True
    recommended_for: list[str] = Field(default_factory=list)


class FinGPTAnnotation(BaseModel):
    article_id: str
    ticker: str = ""
    task: FinGPTTask
    label: str
    confidence: float = Field(default=0, ge=0, le=1)
    source: str = "fingpt"
    model_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinGPTForecasterSignal(BaseModel):
    ticker: str
    horizon: str = "1w"
    direction: Literal["up", "down", "neutral"]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_doc_ids: list[str] = Field(default_factory=list)
    source: str = "fingpt-forecaster-auxiliary"


class FinGPTEvaluationCase(BaseModel):
    case_id: str
    task: FinGPTTask
    input_text: str
    expected_label: str
    ticker: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinGPTEvaluationResult(BaseModel):
    route: str
    task: FinGPTEvaluationTask
    total: int
    correct: int
    accuracy: float
    invalid_outputs: int = 0
    latency_s: float = 0.0
