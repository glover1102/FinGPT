from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceCollectionResult:
    source: str
    status: str
    doc_count: int
    elapsed_s: float
    detail: str


@dataclass(frozen=True, slots=True)
class CollectionOutcome:
    documents: list[dict[str, Any]] = field(default_factory=list)
    source_results: list[SourceCollectionResult] = field(default_factory=list)
    provider_results: list[SourceCollectionResult] = field(default_factory=list)
    degraded: bool = False
    summary_detail: str = ""
    current_doc_ids: list[str] = field(default_factory=list)
    run_started_at: str = ""
    freshness_cutoff: str = ""
    retrieval_policy: str = "current_run_only"
    cache_hit: bool = False
    cached_at: str = ""
    cache_age_s: float = 0.0
