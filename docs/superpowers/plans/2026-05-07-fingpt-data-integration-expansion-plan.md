# FinGPT Data Integration Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the archived/original FinGPT assets into efficient, task-specific data, labeling, evaluation, and auxiliary signal components inside the current local research assistant without replacing the qwen production baseline.

**Architecture:** Keep the current `Ollama/qwen + RAG + data_mart + Quant Lab` path as the production route. Add FinGPT as a bounded auxiliary subsystem: dataset registry, optional local task adapters, persisted article annotations, retrieval/query enrichment, benchmark evaluation, and Forecaster-style auxiliary signals. Heavy Hugging Face model loading must stay lazy and opt-in so startup, UI rendering, and default analysis remain stable.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLite data mart, Qdrant metadata, pytest, optional Hugging Face `datasets`, optional `transformers`, optional `peft`, optional `torch`, local Ollama routes `qwen` and `gemma4`.

---

## Current Baseline

The current repository is not using original FinGPT LoRA models as the main final report generator. The verified production path is:

- `core/config/settings.py`: `primary_model=qwen2.5:7b`, Korean output default.
- `pipelines/infer/runner_factory.py`: `fingpt` is routed back to `settings.primary_model`.
- `pipelines/infer/fingpt_adapter.py`: legacy adapter exists, but no active call path imports it.
- `requirements.txt`: default install does not include `torch`, `transformers`, `peft`, `accelerate`, or `bitsandbytes`.
- `legacy/archive/fingpt/`: original FinGPT project assets are preserved locally, including Benchmark, Forecaster, RAG, MultiAgentsRAG, FinancialReportAnalysis, and Sentiment Analysis directories.

Official FinGPT assets are most useful here as:

1. Financial task datasets and evaluation suites.
2. Optional task-specific LoRA adapters.
3. Forecaster-style structured training/evaluation examples.
4. RAG/source-processing examples.

They are less suitable as the default final JSON report generator because the current final report contract depends on strict JSON schema, Korean output, evidence IDs, and deterministic fallbacks.

## Ranked Opportunities

### Rank 1: FinGPT Sentiment And Headline Labels For News Quality

Use `fingpt-sentiment-train`, `fingpt-headline`, and the sentiment LoRA model family to label collected news with finance-specific tone and price-movement relevance.

Why this is best:

- It maps directly to the existing `sentiment`, `confidence`, `risk_flags`, `bull_points`, and `bear_points` surfaces.
- It improves retrieval quality before final generation.
- It can fail open without breaking analysis.
- It avoids asking a legacy LoRA model to produce the final report JSON.

Primary integration points:

- `pipelines/collect/*`
- `pipelines/data_mart/storage/schema.py`
- `pipelines/data_mart/storage/repository.py`
- `pipelines/orchestration/research_pipeline.py`
- `pipelines/orchestration/topic_pipeline.py`
- `pipelines/analyze/risk_factory.py`
- `core/utils/evidence_quality.py`

### Rank 2: FinGPT NER And Relation Extraction For Evidence Linking

Use `fingpt-ner` and `fingpt-finred` style labels to attach company/entity/relation metadata to articles and filings.

Why this is valuable:

- The current RAG layer depends heavily on ticker and text matching.
- Better entity/relation metadata reduces irrelevant evidence chunks.
- It strengthens cross-company questions and compare mode.

Primary integration points:

- `pipelines/router/query_router.py`
- `core/utils/query_planner.py`
- `pipelines/retrieve/*`
- `core/schemas/retrieval.py`
- `pipelines/data_mart/context/structured_context.py`

### Rank 3: FinGPT Benchmark As A Local Regression Gate

Use benchmark-style datasets as test and evaluation fixtures for qwen, gemma4, and future FinGPT adapters.

Why this is valuable:

- It turns model changes into measurable decisions.
- It avoids anecdotal model comparisons.
- It protects JSON validity, Korean compliance, citation behavior, and finance task accuracy.

Primary integration points:

- `quality_review.py`
- `core/utils/eval_dashboard.py`
- `scripts/validation_gate.py`
- `tests/test_validation_metrics.py`
- `tests/test_eval_dashboard.py`
- new `scripts/evaluate_fingpt_tasks.py`

### Rank 4: FinGPT Forecaster As An Auxiliary Signal, Not A Trading Oracle

Use Forecaster structure to produce a separate, auditable next-period directional signal from news and fundamentals.

Why this is useful but lower priority:

- The project already has Quant Lab and data mart execution surfaces.
- Forecaster-style output can be helpful as an auxiliary feature.
- It should not override deterministic backtests, portfolio optimization, or risk rules.

Primary integration points:

- `pipelines/orchestration/quant_lab_pipeline.py`
- `pipelines/data_mart/context/structured_context.py`
- `pipelines/output/run_history.py`
- `core/schemas/response.py`
- `app/api/routers/quant_lab.py`

### Rank 5: Original FinGPT LoRA Final Report Route

Keep this last. Only add a full FinGPT generation route after task adapters, labels, and evaluation gates are working.

Why this is last:

- It requires heavy dependencies and likely GPU.
- The current `fingpt_adapter.py` has CPU mock behavior and a narrow legacy schema.
- The production report format is stricter than original FinGPT demos.

Primary integration points:

- `pipelines/infer/fingpt_adapter.py`
- `pipelines/infer/runner_factory.py`
- `core/utils/model_capabilities.py`
- `tests/test_production_routing.py`

## Target File Structure

Create these focused modules:

- `core/schemas/fingpt.py`: Pydantic contracts for FinGPT dataset specs, task labels, annotation records, evaluation cases, and Forecaster signals.
- `pipelines/fingpt/__init__.py`: Package marker.
- `pipelines/fingpt/catalog.py`: Static registry of official FinGPT datasets/models and local archived assets.
- `pipelines/fingpt/datasets.py`: Optional Hugging Face dataset loader with cache, row limits, and offline-safe errors.
- `pipelines/fingpt/task_adapter.py`: Optional local inference adapter for sentiment, headline, NER, and relation extraction.
- `pipelines/fingpt/annotation_service.py`: Orchestrates labeling collected documents and persists labels.
- `pipelines/fingpt/evaluation.py`: Converts FinGPT benchmark-style cases into model evaluation metrics.
- `pipelines/fingpt/forecaster_features.py`: Produces Forecaster-style auxiliary directional signals from current data.
- `scripts/evaluate_fingpt_tasks.py`: CLI to run small evaluation sets against qwen, gemma4, and optional FinGPT task adapters.
- `docs/FINGPT_DATA_INTEGRATION.md`: Operator-facing design and runbook.

Modify these existing files:

- `core/config/settings.py`: Add opt-in flags and model/dataset settings.
- `pipelines/data_mart/storage/schema.py`: Add annotation table and schema version.
- `pipelines/data_mart/storage/repository.py`: Add annotation persistence/query methods.
- `pipelines/orchestration/research_pipeline.py`: Run optional annotation enrichment after collection and before prompt assembly.
- `pipelines/orchestration/topic_pipeline.py`: Use annotations in topic evidence summary.
- `pipelines/infer/ollama_adapter.py`: Include annotation summary in prompt only when present.
- `core/utils/evidence_quality.py`: Account for FinGPT labels in evidence scoring.
- `core/utils/model_capabilities.py`: Add capability metadata for FinGPT auxiliary tasks.
- `app/api/routers/system.py`: Expose FinGPT integration status in `/api/v1/config` or `/api/v1/preflight`.
- `app/web/app.js`: Show annotation coverage only as diagnostics, not as a blocking workflow.
- `tests/*`: Add focused tests per task below.

## Implementation Tasks

### Task 1: Add FinGPT Contracts And Registry

**Files:**

- Create: `core/schemas/fingpt.py`
- Create: `pipelines/fingpt/__init__.py`
- Create: `pipelines/fingpt/catalog.py`
- Test: `tests/test_fingpt_catalog.py`

- [ ] **Step 1: Write the failing catalog tests**

Create `tests/test_fingpt_catalog.py`:

```python
from pipelines.fingpt.catalog import (
    FINGPT_DATASETS,
    FINGPT_MODELS,
    dataset_for_task,
    model_for_task,
)


def test_catalog_contains_core_official_tasks():
    tasks = {item.task for item in FINGPT_DATASETS}
    assert {"sentiment", "headline", "ner", "relation", "fiqa_qa", "forecaster"} <= tasks


def test_dataset_for_task_returns_stable_hf_id():
    spec = dataset_for_task("sentiment")
    assert spec.hf_id == "FinGPT/fingpt-sentiment-train"
    assert spec.task == "sentiment"
    assert spec.default_split in {"train", "test", "validation"}


def test_model_for_task_prefers_task_specific_model():
    spec = model_for_task("sentiment")
    assert spec.hf_id.startswith("FinGPT/")
    assert spec.task == "sentiment"
    assert spec.requires_gpu is True
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_catalog.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'pipelines.fingpt'
```

- [ ] **Step 3: Add Pydantic contracts**

Create `core/schemas/fingpt.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FinGPTTask = Literal[
    "sentiment",
    "headline",
    "ner",
    "relation",
    "fiqa_qa",
    "forecaster",
]


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
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "fingpt"
    model_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinGPTEvaluationCase(BaseModel):
    case_id: str
    task: FinGPTTask
    input_text: str
    expected_label: str
    ticker: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinGPTEvaluationResult(BaseModel):
    route: str
    task: FinGPTTask
    total: int
    correct: int
    accuracy: float
    invalid_outputs: int = 0
    latency_s: float = 0.0
```

- [ ] **Step 4: Add the static catalog**

Create `pipelines/fingpt/__init__.py`:

```python
"""Task-specific FinGPT integration helpers."""
```

Create `pipelines/fingpt/catalog.py`:

```python
from __future__ import annotations

from core.schemas.fingpt import FinGPTDatasetSpec, FinGPTModelSpec, FinGPTTask


FINGPT_DATASETS: tuple[FinGPTDatasetSpec, ...] = (
    FinGPTDatasetSpec(
        task="sentiment",
        hf_id="FinGPT/fingpt-sentiment-train",
        default_split="train",
        local_archive_hint="legacy/archive/fingpt/FinGPT_Sentiment_Analysis_v3",
        expected_columns=["instruction", "input", "output"],
        use_case="Financial sentiment labels for news, tweets, and evidence quality.",
    ),
    FinGPTDatasetSpec(
        task="headline",
        hf_id="FinGPT/fingpt-headline",
        default_split="test",
        local_archive_hint="legacy/archive/fingpt/FinGPT_Benchmark/benchmarks/headline.py",
        expected_columns=["instruction", "input", "output"],
        use_case="Headline price-movement classification and relevance gating.",
    ),
    FinGPTDatasetSpec(
        task="ner",
        hf_id="FinGPT/fingpt-ner",
        default_split="test",
        local_archive_hint="legacy/archive/fingpt/FinGPT_Benchmark/benchmarks/ner.py",
        expected_columns=["instruction", "input", "output"],
        use_case="Entity extraction for company, person, and location linking.",
    ),
    FinGPTDatasetSpec(
        task="relation",
        hf_id="FinGPT/fingpt-finred",
        default_split="test",
        local_archive_hint="legacy/archive/fingpt/FinGPT_Benchmark/benchmarks/finred.py",
        expected_columns=["instruction", "input", "output"],
        use_case="Financial relation extraction for cross-company evidence links.",
    ),
    FinGPTDatasetSpec(
        task="fiqa_qa",
        hf_id="FinGPT/fingpt-fiqa_qa",
        default_split="train",
        local_archive_hint="legacy/archive/fingpt/FinGPT_Benchmark/benchmarks/fiqa.py",
        expected_columns=["instruction", "input", "output"],
        use_case="Question-answering evaluation for finance reasoning.",
    ),
    FinGPTDatasetSpec(
        task="forecaster",
        hf_id="FinGPT/fingpt-forecaster-dow30-202305-202405",
        default_split="train",
        local_archive_hint="legacy/archive/fingpt/FinGPT_Forecaster",
        expected_columns=["prompt", "answer"],
        use_case="Forecaster-style auxiliary directional signal evaluation.",
    ),
)


FINGPT_MODELS: tuple[FinGPTModelSpec, ...] = (
    FinGPTModelSpec(
        task="sentiment",
        hf_id="FinGPT/fingpt-sentiment_llama2-13b_lora",
        base_model="meta-llama/Llama-2-13b-hf",
        requires_gpu=True,
        recommended_for=["sentiment_tagging", "risk_tone_classification"],
    ),
    FinGPTModelSpec(
        task="sentiment",
        hf_id="FinGPT/fingpt-mt_llama3-8b_lora",
        base_model="meta-llama/Meta-Llama-3-8B",
        requires_gpu=True,
        recommended_for=["multi_task_financial_labels"],
    ),
    FinGPTModelSpec(
        task="forecaster",
        hf_id="FinGPT/fingpt-forecaster_dow30_llama2-7b_lora",
        base_model="meta-llama/Llama-2-7b-hf",
        requires_gpu=True,
        recommended_for=["forecaster_auxiliary_signal"],
    ),
)


def dataset_for_task(task: FinGPTTask) -> FinGPTDatasetSpec:
    for spec in FINGPT_DATASETS:
        if spec.task == task:
            return spec
    raise ValueError(f"Unsupported FinGPT dataset task: {task}")


def model_for_task(task: FinGPTTask) -> FinGPTModelSpec:
    for spec in FINGPT_MODELS:
        if spec.task == task:
            return spec
    raise ValueError(f"Unsupported FinGPT model task: {task}")
```

- [ ] **Step 5: Run test and confirm pass**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_catalog.py -q
```

Expected result:

```text
3 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add core/schemas/fingpt.py pipelines/fingpt/__init__.py pipelines/fingpt/catalog.py tests/test_fingpt_catalog.py
git commit -m "feat: add FinGPT task catalog"
```

Expected result:

```text
[branch <sha>] feat: add FinGPT task catalog
```

### Task 2: Add Offline-Safe FinGPT Dataset Loading

**Files:**

- Create: `pipelines/fingpt/datasets.py`
- Modify: `core/config/settings.py`
- Test: `tests/test_fingpt_datasets.py`

- [ ] **Step 1: Write failing dataset loader tests**

Create `tests/test_fingpt_datasets.py`:

```python
from unittest.mock import Mock, patch

import pytest

from pipelines.fingpt.datasets import FinGPTDatasetUnavailable, load_dataset_rows


def test_load_dataset_rows_requires_enablement():
    with pytest.raises(FinGPTDatasetUnavailable) as exc:
        load_dataset_rows("sentiment", enabled=False)
    assert "disabled" in str(exc.value).lower()


def test_load_dataset_rows_limits_rows_and_normalizes_dicts():
    fake_dataset = [
        {"instruction": "What is the sentiment?", "input": "good earnings", "output": "positive"},
        {"instruction": "What is the sentiment?", "input": "weak margin", "output": "negative"},
    ]
    fake_module = Mock()
    fake_module.load_dataset.return_value = {"train": fake_dataset}

    with patch.dict("sys.modules", {"datasets": fake_module}):
        rows = load_dataset_rows("sentiment", enabled=True, max_rows=1)

    assert rows == [{"instruction": "What is the sentiment?", "input": "good earnings", "output": "positive"}]
    fake_module.load_dataset.assert_called_once()


def test_load_dataset_rows_reports_missing_dependency():
    with patch.dict("sys.modules", {"datasets": None}):
        with pytest.raises(FinGPTDatasetUnavailable) as exc:
            load_dataset_rows("sentiment", enabled=True)
    assert "datasets" in str(exc.value).lower()
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_datasets.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'pipelines.fingpt.datasets'
```

- [ ] **Step 3: Add config flags**

Modify `core/config/settings.py` near the inference/model section:

```python
    # FinGPT auxiliary integration. Disabled by default because Hugging Face
    # datasets/models can be large and should not affect local startup.
    fingpt_datasets_enabled: bool = Field(default=False)
    fingpt_dataset_cache_dir: Path = Field(default=DATA_DIR / "fingpt_datasets")
    fingpt_dataset_max_rows: int = Field(default=500)
    fingpt_task_model_enabled: bool = Field(default=False)
    fingpt_task_model_name: str = Field(default="FinGPT/fingpt-mt_llama3-8b_lora")
```

- [ ] **Step 4: Implement offline-safe loader**

Create `pipelines/fingpt/datasets.py`:

```python
from __future__ import annotations

from typing import Any

from pipelines.fingpt.catalog import dataset_for_task


class FinGPTDatasetUnavailable(RuntimeError):
    """Raised when optional FinGPT dataset loading is disabled or unavailable."""


def _coerce_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "items"):
        return dict(row.items())
    raise FinGPTDatasetUnavailable(f"Unsupported dataset row type: {type(row).__name__}")


def load_dataset_rows(
    task: str,
    *,
    enabled: bool,
    split: str | None = None,
    max_rows: int = 500,
    cache_dir: str | None = None,
) -> list[dict[str, Any]]:
    if not enabled:
        raise FinGPTDatasetUnavailable("FinGPT dataset loading is disabled.")

    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise FinGPTDatasetUnavailable(
            f"Hugging Face datasets is not installed: {exc}. Install `datasets` to enable this path."
        ) from exc

    spec = dataset_for_task(task)  # type: ignore[arg-type]
    selected_split = split or spec.default_split
    try:
        loaded = load_dataset(spec.hf_id, cache_dir=cache_dir)
    except Exception as exc:  # noqa: BLE001
        raise FinGPTDatasetUnavailable(f"Failed to load {spec.hf_id}: {exc}") from exc

    if isinstance(loaded, dict):
        if selected_split not in loaded:
            available = ", ".join(sorted(str(key) for key in loaded.keys()))
            raise FinGPTDatasetUnavailable(
                f"Split '{selected_split}' not found for {spec.hf_id}. Available: {available}"
            )
        dataset = loaded[selected_split]
    else:
        dataset = loaded

    limit = max(0, int(max_rows))
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(dataset):
        if index >= limit:
            break
        rows.append(_coerce_row(row))
    return rows
```

- [ ] **Step 5: Run test and confirm pass**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_datasets.py -q
```

Expected result:

```text
3 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add core/config/settings.py pipelines/fingpt/datasets.py tests/test_fingpt_datasets.py
git commit -m "feat: add offline-safe FinGPT dataset loader"
```

Expected result:

```text
[branch <sha>] feat: add offline-safe FinGPT dataset loader
```

### Task 3: Persist FinGPT Article Annotations In The Data Mart

**Files:**

- Modify: `pipelines/data_mart/storage/schema.py`
- Modify: `pipelines/data_mart/storage/repository.py`
- Test: `tests/test_fingpt_annotation_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/test_fingpt_annotation_repository.py`:

```python
from pathlib import Path

from core.schemas.fingpt import FinGPTAnnotation
from pipelines.data_mart.storage.db import connect
from pipelines.data_mart.storage.repository import (
    get_fingpt_annotations,
    init_data_mart,
    upsert_fingpt_annotations,
)


def test_upsert_and_get_fingpt_annotations(tmp_path: Path):
    db_path = tmp_path / "mart.db"
    with connect(db_path) as conn:
        init_data_mart(conn)
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="MSFT",
                    task="sentiment",
                    label="positive",
                    confidence=0.91,
                    model_id="FinGPT/fingpt-sentiment_llama2-13b_lora",
                    metadata={"source_title": "MSFT earnings"},
                )
            ],
        )
        rows = get_fingpt_annotations(conn, ticker="MSFT", task="sentiment")

    assert len(rows) == 1
    assert rows[0].article_id == "article-1"
    assert rows[0].label == "positive"
    assert rows[0].confidence == 0.91
    assert rows[0].metadata["source_title"] == "MSFT earnings"


def test_annotation_upsert_replaces_same_article_task_model(tmp_path: Path):
    db_path = tmp_path / "mart.db"
    with connect(db_path) as conn:
        init_data_mart(conn)
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(article_id="article-1", ticker="MSFT", task="sentiment", label="neutral", confidence=0.4, model_id="m1"),
                FinGPTAnnotation(article_id="article-1", ticker="MSFT", task="sentiment", label="negative", confidence=0.8, model_id="m1"),
            ],
        )
        rows = get_fingpt_annotations(conn, ticker="MSFT", task="sentiment")

    assert len(rows) == 1
    assert rows[0].label == "negative"
    assert rows[0].confidence == 0.8
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_annotation_repository.py -q
```

Expected result:

```text
ImportError: cannot import name 'get_fingpt_annotations'
```

- [ ] **Step 3: Add schema table**

Modify `pipelines/data_mart/storage/schema.py`:

```python
SCHEMA_VERSION = 2
```

Add this DDL before the index statements:

```python
    """
    CREATE TABLE IF NOT EXISTS fingpt_article_annotations (
        article_id TEXT NOT NULL,
        ticker TEXT,
        task TEXT NOT NULL,
        label TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.0,
        source TEXT NOT NULL DEFAULT 'fingpt',
        model_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        PRIMARY KEY (article_id, task, source, model_id)
    )
    """,
```

Add indexes:

```python
    "CREATE INDEX IF NOT EXISTS idx_fingpt_annotations_ticker_task ON fingpt_article_annotations(ticker, task, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fingpt_annotations_article ON fingpt_article_annotations(article_id)",
```

- [ ] **Step 4: Add repository methods**

Modify `pipelines/data_mart/storage/repository.py` with imports:

```python
import json
from datetime import datetime, timezone

from core.schemas.fingpt import FinGPTAnnotation
```

Add helper:

```python
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
```

Add methods:

```python
def upsert_fingpt_annotations(conn, annotations: list[FinGPTAnnotation]) -> int:
    now = _utc_now_iso()
    rows = [
        {
            "article_id": item.article_id,
            "ticker": item.ticker,
            "task": item.task,
            "label": item.label,
            "confidence": float(item.confidence),
            "source": item.source,
            "model_id": item.model_id,
            "metadata_json": json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
            "created_at": now,
        }
        for item in annotations
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO fingpt_article_annotations
            (article_id, ticker, task, label, confidence, source, model_id, metadata_json, created_at)
        VALUES
            (:article_id, :ticker, :task, :label, :confidence, :source, :model_id, :metadata_json, :created_at)
        ON CONFLICT(article_id, task, source, model_id) DO UPDATE SET
            ticker=excluded.ticker,
            label=excluded.label,
            confidence=excluded.confidence,
            metadata_json=excluded.metadata_json,
            created_at=excluded.created_at
        """,
        rows,
    )
    return len(rows)


def get_fingpt_annotations(conn, *, ticker: str | None = None, task: str | None = None, limit: int = 100) -> list[FinGPTAnnotation]:
    clauses: list[str] = []
    params: dict[str, object] = {"limit": max(1, min(int(limit), 1000))}
    if ticker:
        clauses.append("ticker = :ticker")
        params["ticker"] = ticker.upper()
    if task:
        clauses.append("task = :task")
        params["task"] = task
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT article_id, ticker, task, label, confidence, source, model_id, metadata_json
        FROM fingpt_article_annotations
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        params,
    ).fetchall()
    result: list[FinGPTAnnotation] = []
    for row in rows:
        metadata_raw = row["metadata_json"] if "metadata_json" in row.keys() else "{}"
        try:
            metadata = json.loads(metadata_raw or "{}")
        except json.JSONDecodeError:
            metadata = {"raw": metadata_raw}
        result.append(
            FinGPTAnnotation(
                article_id=row["article_id"],
                ticker=row["ticker"] or "",
                task=row["task"],
                label=row["label"],
                confidence=float(row["confidence"] or 0.0),
                source=row["source"] or "fingpt",
                model_id=row["model_id"] or "",
                metadata=metadata,
            )
        )
    return result
```

- [ ] **Step 5: Run repository tests**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_annotation_repository.py tests\test_data_mart_schema.py tests\test_data_mart_repository.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add pipelines/data_mart/storage/schema.py pipelines/data_mart/storage/repository.py tests/test_fingpt_annotation_repository.py
git commit -m "feat: persist FinGPT article annotations"
```

Expected result:

```text
[branch <sha>] feat: persist FinGPT article annotations
```

### Task 4: Add Optional FinGPT Task Adapter

**Files:**

- Create: `pipelines/fingpt/task_adapter.py`
- Modify: `pipelines/analyze/risk_factory.py`
- Test: `tests/test_fingpt_task_adapter.py`
- Test: `tests/test_risk_factory.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_fingpt_task_adapter.py`:

```python
from unittest.mock import Mock, patch

import pytest

from pipelines.fingpt.task_adapter import FinGPTTaskAdapter, FinGPTTaskUnavailable


def test_adapter_disabled_raises_without_importing_transformers():
    adapter = FinGPTTaskAdapter(enabled=False, model_name="FinGPT/fingpt-mt_llama3-8b_lora")
    with pytest.raises(FinGPTTaskUnavailable):
        adapter.label_texts("sentiment", ["strong earnings"])


def test_adapter_maps_pipeline_labels_to_annotations():
    fake_pipeline = Mock(return_value=[[{"label": "positive", "score": 0.88}]])
    fake_transformers = Mock()
    fake_transformers.pipeline.return_value = fake_pipeline

    with patch.dict("sys.modules", {"transformers": fake_transformers}):
        adapter = FinGPTTaskAdapter(enabled=True, model_name="FinGPT/fingpt-mt_llama3-8b_lora")
        labels = adapter.label_texts("sentiment", ["strong earnings"])

    assert labels[0].label == "positive"
    assert labels[0].confidence == 0.88
    assert labels[0].model_id == "FinGPT/fingpt-mt_llama3-8b_lora"


def test_adapter_reports_missing_transformers():
    with patch.dict("sys.modules", {"transformers": None}):
        adapter = FinGPTTaskAdapter(enabled=True, model_name="FinGPT/fingpt-mt_llama3-8b_lora")
        with pytest.raises(FinGPTTaskUnavailable) as exc:
            adapter.label_texts("sentiment", ["text"])
    assert "transformers" in str(exc.value).lower()
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_task_adapter.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'pipelines.fingpt.task_adapter'
```

- [ ] **Step 3: Implement lazy adapter**

Create `pipelines/fingpt/task_adapter.py`:

```python
from __future__ import annotations

import threading
from dataclasses import dataclass

from core.schemas.fingpt import FinGPTAnnotation, FinGPTTask


class FinGPTTaskUnavailable(RuntimeError):
    """Raised when optional FinGPT task model inference cannot run."""


@dataclass
class _RawLabel:
    label: str
    confidence: float


class FinGPTTaskAdapter:
    _pipeline = None
    _lock = threading.Lock()

    def __init__(self, *, enabled: bool, model_name: str, device: int = -1) -> None:
        self.enabled = bool(enabled)
        self.model_name = model_name
        self.device = device

    def _load_pipeline(self):
        if not self.enabled:
            raise FinGPTTaskUnavailable("FinGPT task adapter is disabled.")
        if FinGPTTaskAdapter._pipeline is not None:
            return FinGPTTaskAdapter._pipeline
        with FinGPTTaskAdapter._lock:
            if FinGPTTaskAdapter._pipeline is not None:
                return FinGPTTaskAdapter._pipeline
            try:
                from transformers import pipeline  # type: ignore[import-not-found]
            except Exception as exc:  # noqa: BLE001
                raise FinGPTTaskUnavailable(
                    f"transformers is not installed: {exc}. Install transformers/torch/peft for FinGPT task inference."
                ) from exc
            try:
                FinGPTTaskAdapter._pipeline = pipeline(
                    "text-classification",
                    model=self.model_name,
                    top_k=None,
                    device=self.device,
                )
            except Exception as exc:  # noqa: BLE001
                raise FinGPTTaskUnavailable(f"failed to load FinGPT task model {self.model_name}: {exc}") from exc
            return FinGPTTaskAdapter._pipeline

    @staticmethod
    def _best_label(raw) -> _RawLabel:
        if isinstance(raw, list) and raw:
            best = max(raw, key=lambda item: float(item.get("score", 0.0)))
            return _RawLabel(label=str(best.get("label", "neutral")).lower(), confidence=float(best.get("score", 0.0)))
        if isinstance(raw, dict):
            return _RawLabel(label=str(raw.get("label", "neutral")).lower(), confidence=float(raw.get("score", 0.0)))
        return _RawLabel(label="neutral", confidence=0.0)

    def label_texts(self, task: FinGPTTask, texts: list[str]) -> list[FinGPTAnnotation]:
        clean_texts = [text.strip() for text in texts if text and text.strip()]
        if not clean_texts:
            return []
        classifier = self._load_pipeline()
        outputs = classifier(clean_texts, truncation=True, max_length=256)
        annotations: list[FinGPTAnnotation] = []
        for index, raw in enumerate(outputs):
            best = self._best_label(raw)
            annotations.append(
                FinGPTAnnotation(
                    article_id=f"inline-{index}",
                    task=task,
                    label=best.label,
                    confidence=best.confidence,
                    source="fingpt-task-adapter",
                    model_id=self.model_name,
                    metadata={"text_preview": clean_texts[index][:160]},
                )
            )
        return annotations
```

- [ ] **Step 4: Register optional risk engine name**

Modify `pipelines/analyze/risk_factory.py`:

```python
_VALID_ENGINES = {"heuristic", "finbert", "fingpt"}
```

Add before the final return:

```python
    if name == "fingpt":
        try:
            from pipelines.fingpt.task_adapter import FinGPTTaskAdapter, FinGPTTaskUnavailable
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RISK_ENGINE] fingpt module unavailable (%s) - falling back to heuristic", exc)
            return HeuristicRiskEngine()
        try:
            adapter = FinGPTTaskAdapter(
                enabled=bool(getattr(settings, "fingpt_task_model_enabled", False)),
                model_name=getattr(settings, "fingpt_task_model_name", "FinGPT/fingpt-mt_llama3-8b_lora"),
            )
            adapter._load_pipeline()
            logger.info("[RISK_ENGINE] active=fingpt")
            from pipelines.fingpt.risk_engine import FinGPTRiskEngine
            return FinGPTRiskEngine(adapter)
        except FinGPTTaskUnavailable as exc:
            logger.warning("[RISK_ENGINE] fingpt unavailable (%s) - falling back to heuristic", exc)
            return HeuristicRiskEngine()
```

Also create `pipelines/fingpt/risk_engine.py` in this task if using the factory branch:

```python
from __future__ import annotations

import asyncio
from typing import Any

from core.interfaces.risk import BaseRiskEngine, RiskEvaluationResult
from pipelines.fingpt.task_adapter import FinGPTTaskAdapter


class FinGPTRiskEngine(BaseRiskEngine):
    def __init__(self, adapter: FinGPTTaskAdapter) -> None:
        self.adapter = adapter

    async def evaluate_risk(self, raw_output: dict[str, Any]) -> RiskEvaluationResult:
        bull_points = [str(item) for item in raw_output.get("bull_points", []) or []]
        bear_points = [str(item) for item in raw_output.get("bear_points", []) or []]
        if bull_points or bear_points:
            return RiskEvaluationResult(bull_points=bull_points, bear_points=bear_points)
        flags = [str(item) for item in raw_output.get("risk_flags", []) or [] if str(item).strip()]
        annotations = await asyncio.to_thread(self.adapter.label_texts, "sentiment", flags)
        for flag, ann in zip(flags, annotations):
            if ann.label == "positive":
                bull_points.append(flag)
            elif ann.label == "negative":
                bear_points.append(flag)
        return RiskEvaluationResult(bull_points=bull_points, bear_points=bear_points)
```

- [ ] **Step 5: Add risk factory test**

Append to `tests/test_risk_factory.py`:

```python
from core.config.settings import Settings
from pipelines.analyze.risk_analysis import HeuristicRiskEngine
from pipelines.analyze.risk_factory import get_risk_engine


def test_fingpt_risk_engine_falls_back_when_disabled():
    settings = Settings(risk_engine="fingpt", fingpt_task_model_enabled=False)
    engine = get_risk_engine(settings=settings)
    assert isinstance(engine, HeuristicRiskEngine)
```

- [ ] **Step 6: Run adapter and risk tests**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_task_adapter.py tests\test_risk_factory.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add pipelines/fingpt/task_adapter.py pipelines/fingpt/risk_engine.py pipelines/analyze/risk_factory.py tests/test_fingpt_task_adapter.py tests/test_risk_factory.py
git commit -m "feat: add optional FinGPT task adapter"
```

Expected result:

```text
[branch <sha>] feat: add optional FinGPT task adapter
```

### Task 5: Annotate Collected Evidence Without Blocking The Pipeline

**Files:**

- Create: `pipelines/fingpt/annotation_service.py`
- Modify: `pipelines/orchestration/research_pipeline.py`
- Test: `tests/test_fingpt_annotation_service.py`
- Test: `tests/test_collection_reliability.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_fingpt_annotation_service.py`:

```python
from unittest.mock import Mock

from pipelines.fingpt.annotation_service import annotate_documents


def test_annotate_documents_uses_stable_article_ids():
    adapter = Mock()
    adapter.label_texts.return_value = []
    documents = [
        {"id": "doc-1", "ticker": "MSFT", "title": "MSFT earnings beat", "summary": "Margins expanded."},
        {"doc_id": "doc-2", "ticker": "AAPL", "title": "AAPL supplier risk", "content": "Demand is weaker."},
    ]

    result = annotate_documents(documents, adapter=adapter, enabled=True, tasks=["sentiment"])

    assert result.status == "success"
    assert result.documents_seen == 2
    adapter.label_texts.assert_called_once()
    assert "MSFT earnings beat" in adapter.label_texts.call_args.args[1][0]


def test_annotate_documents_fails_open_when_adapter_errors():
    adapter = Mock()
    adapter.label_texts.side_effect = RuntimeError("model unavailable")
    result = annotate_documents([{"id": "doc-1", "title": "x"}], adapter=adapter, enabled=True, tasks=["sentiment"])
    assert result.status == "skipped"
    assert "model unavailable" in result.detail
    assert result.annotations == []
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_annotation_service.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'pipelines.fingpt.annotation_service'
```

- [ ] **Step 3: Implement annotation service**

Create `pipelines/fingpt/annotation_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.schemas.fingpt import FinGPTAnnotation
from pipelines.fingpt.task_adapter import FinGPTTaskAdapter


@dataclass(frozen=True)
class FinGPTAnnotationResult:
    status: str
    detail: str
    documents_seen: int = 0
    annotations: list[FinGPTAnnotation] = field(default_factory=list)


def _document_id(doc: dict[str, Any], index: int) -> str:
    return str(doc.get("id") or doc.get("doc_id") or doc.get("article_id") or f"doc-{index}")


def _document_text(doc: dict[str, Any]) -> str:
    parts = [
        str(doc.get("title") or ""),
        str(doc.get("summary") or ""),
        str(doc.get("content") or ""),
        str(doc.get("document") or ""),
        str(doc.get("chunk") or ""),
    ]
    return " ".join(part for part in parts if part.strip()).strip()


def annotate_documents(
    documents: list[dict[str, Any]],
    *,
    adapter: FinGPTTaskAdapter,
    enabled: bool,
    tasks: list[str],
) -> FinGPTAnnotationResult:
    if not enabled:
        return FinGPTAnnotationResult(status="disabled", detail="FinGPT annotation disabled.", documents_seen=len(documents))
    texts: list[str] = []
    id_map: list[tuple[str, str]] = []
    for index, doc in enumerate(documents):
        text = _document_text(doc)
        if not text:
            continue
        texts.append(text)
        id_map.append((_document_id(doc, index), str(doc.get("ticker") or "").upper()))
    if not texts:
        return FinGPTAnnotationResult(status="skipped", detail="No annotatable document text.", documents_seen=len(documents))
    annotations: list[FinGPTAnnotation] = []
    try:
        for task in tasks:
            labels = adapter.label_texts(task, texts)  # type: ignore[arg-type]
            for label, (article_id, ticker) in zip(labels, id_map):
                annotations.append(
                    label.model_copy(
                        update={
                            "article_id": article_id,
                            "ticker": ticker,
                            "metadata": {**label.metadata, "annotation_task": task},
                        }
                    )
                )
    except Exception as exc:  # noqa: BLE001
        return FinGPTAnnotationResult(
            status="skipped",
            detail=f"FinGPT annotation failed open: {exc}",
            documents_seen=len(documents),
        )
    return FinGPTAnnotationResult(
        status="success",
        detail=f"Annotated {len(annotations)} labels across {len(texts)} documents.",
        documents_seen=len(documents),
        annotations=annotations,
    )
```

- [ ] **Step 4: Integrate into research pipeline**

Modify `pipelines/orchestration/research_pipeline.py`. Initialize the result variable near the existing `fundamentals_card = None` line:

```python
    fingpt_annotation_result = None
```

Then insert the enrichment block immediately after the current lines:

```python
        documents = collection_outcome.documents
        current_doc_ids = _current_doc_ids(collection_outcome)
        settings_after_collect = load_settings()
```

Use this exact fail-open block:

```python
        if bool(getattr(settings_after_collect, "fingpt_task_model_enabled", False)):
            try:
                from pipelines.fingpt.annotation_service import annotate_documents
                from pipelines.fingpt.task_adapter import FinGPTTaskAdapter
                from pipelines.data_mart.storage.db import connect as data_mart_connect
                from pipelines.data_mart.storage.repository import upsert_fingpt_annotations

                def _write_fingpt_annotations(db_path, annotations):
                    with data_mart_connect(db_path) as conn:
                        return upsert_fingpt_annotations(conn, annotations)

                adapter = FinGPTTaskAdapter(
                    enabled=True,
                    model_name=getattr(settings_after_collect, "fingpt_task_model_name", "FinGPT/fingpt-mt_llama3-8b_lora"),
                )
                fingpt_annotation_result = await asyncio.to_thread(
                    annotate_documents,
                    documents,
                    adapter=adapter,
                    enabled=True,
                    tasks=["sentiment"],
                )
                if fingpt_annotation_result.annotations:
                    await asyncio.to_thread(
                        _write_fingpt_annotations,
                        settings_after_collect.data_mart_db_path,
                        fingpt_annotation_result.annotations,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[FINGPT_ANNOTATION] skipped: %s", exc)
                fingpt_annotation_result = {"status": "skipped", "detail": str(exc)}
```

Add execution metadata near existing `extras` construction:

```python
                "fingpt_annotations": (
                    fingpt_annotation_result.__dict__
                    if hasattr(fingpt_annotation_result, "__dict__")
                    else fingpt_annotation_result
                ),
```

- [ ] **Step 5: Add reliability test**

Append this method to `NoContextPipelineTests` in `tests/test_collection_reliability.py`:

```python
    async def test_fingpt_annotation_failure_does_not_fail_pipeline(self):
        request = AnalysisRequest(
            ticker="MSFT",
            question="Is Microsoft a good investment?",
            sources=["news"],
            lookback_days=14,
            top_k=1,
        )
        current_doc = _news_doc("current-doc")
        outcome = collector.CollectionOutcome(
            documents=[current_doc],
            source_results=[collector.SourceCollectionResult("news", "ok", 1, 1.0, "news ok")],
            degraded=False,
            summary_detail="",
            current_doc_ids=["current-doc"],
        )
        retrieved = [
            RetrievalItem(
                source="Yahoo Finance",
                title="Current article",
                date="2026-04-20T00:00:00",
                chunk="Current Microsoft context",
                score=0.75,
                metadata={"doc_id": "current-doc", "ticker": "MSFT"},
            )
        ]
        raw_output = {
            "summary": "Microsoft current-run context only.",
            "bull_points": ["Current-run driver"],
            "bear_points": [],
            "sentiment": "Positive",
            "confidence": 0.8,
            "uncertainty": "",
            "cited_doc_ids": ["current-doc"],
            "_meta": {"primary_model": "qwen2.5:7b", "producing_model": "qwen2.5:7b"},
        }
        settings = Settings(fingpt_task_model_enabled=True)

        with patch.object(research_pipeline, "load_settings", return_value=settings), \
             patch.object(research_pipeline, "run_execution_precheck", return_value=None), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "ingest_documents"), \
             patch.object(research_pipeline, "retrieve_context", return_value=retrieved), \
             patch.object(research_pipeline, "retrieve_context_multi", return_value=retrieved), \
             patch.object(research_pipeline, "run_inference", return_value=raw_output), \
             patch.object(research_pipeline, "build_report", return_value=("md", "html")), \
             patch.object(research_pipeline, "save_outputs"), \
             patch("pipelines.fingpt.annotation_service.annotate_documents", side_effect=RuntimeError("annotation down")):
            response = await research_pipeline.run_pipeline_async(request)

        self.assertIn(response.status, {"success", "partial"})
        self.assertEqual(response.execution_meta.extras["fingpt_annotations"]["status"], "skipped")
        self.assertIn("annotation down", response.execution_meta.extras["fingpt_annotations"]["detail"])
```

- [ ] **Step 6: Run service and collection tests**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_annotation_service.py tests\test_collection_reliability.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add pipelines/fingpt/annotation_service.py pipelines/orchestration/research_pipeline.py tests/test_fingpt_annotation_service.py tests/test_collection_reliability.py
git commit -m "feat: enrich evidence with optional FinGPT annotations"
```

Expected result:

```text
[branch <sha>] feat: enrich evidence with optional FinGPT annotations
```

### Task 6: Use FinGPT Labels In Retrieval And Prompt Context

**Files:**

- Modify: `core/utils/evidence_quality.py`
- Modify: `pipelines/data_mart/context/structured_context.py`
- Modify: `pipelines/infer/ollama_adapter.py`
- Test: `tests/test_fingpt_prompt_context.py`
- Test: `tests/test_evidence_quality.py`

- [ ] **Step 1: Write failing prompt context test**

Create `tests/test_fingpt_prompt_context.py`:

```python
from core.schemas.retrieval import RetrievalItem
from pipelines.infer.ollama_adapter import _build_ollama_prompt


def test_fingpt_annotation_metadata_reaches_prompt():
    item = RetrievalItem(
        source="news",
        title="MSFT earnings beat",
        date="2026-05-01",
        chunk="Microsoft reported margin expansion.",
        score=0.9,
        metadata={
            "doc_id": "doc-1",
            "fingpt_annotations": [
                {"task": "sentiment", "label": "positive", "confidence": 0.91},
                {"task": "headline", "label": "price_up", "confidence": 0.82},
            ],
        },
    )

    prompt, chunks = _build_ollama_prompt("MSFT", "Assess the thesis", [item], "general", "12m")

    assert chunks == 1
    assert "FINGPT ANNOTATIONS" in prompt
    assert "sentiment=positive" in prompt
    assert "headline=price_up" in prompt
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_prompt_context.py -q
```

Expected result:

```text
AssertionError: assert 'FINGPT ANNOTATIONS' in prompt
```

- [ ] **Step 3: Add metadata formatter**

Modify `pipelines/infer/ollama_adapter.py` near prompt formatting helpers:

```python
def _fingpt_annotation_prompt_line(metadata: dict[str, Any]) -> str:
    annotations = metadata.get("fingpt_annotations") or []
    if not isinstance(annotations, list):
        return ""
    parts: list[str] = []
    for ann in annotations[:5]:
        if not isinstance(ann, dict):
            continue
        task = str(ann.get("task") or "").strip()
        label = str(ann.get("label") or "").strip()
        confidence = ann.get("confidence")
        if not task or not label:
            continue
        try:
            conf_text = f"{float(confidence):.2f}"
        except (TypeError, ValueError):
            conf_text = "unknown"
        parts.append(f"{task}={label} confidence={conf_text}")
    if not parts:
        return ""
    return "FINGPT ANNOTATIONS: " + "; ".join(parts)
```

Inside the loop that builds each context block, append:

```python
        fingpt_line = _fingpt_annotation_prompt_line(meta)
        if fingpt_line:
            block_parts.append(fingpt_line)
```

Use the current context block construction style in `_build_ollama_prompt`; do not rewrite unrelated prompt sections.

- [ ] **Step 4: Add evidence quality scoring**

Modify `core/utils/evidence_quality.py`:

```python
def fingpt_annotation_quality_bonus(metadata: dict) -> float:
    annotations = metadata.get("fingpt_annotations") or []
    if not isinstance(annotations, list):
        return 0.0
    high_confidence = [
        ann for ann in annotations
        if isinstance(ann, dict) and float(ann.get("confidence") or 0.0) >= 0.75
    ]
    return min(0.1, 0.025 * len(high_confidence))
```

Call this from the existing quality score function by adding the bonus to the final score and clamping to the existing max.

- [ ] **Step 5: Add evidence quality test**

Append to `tests/test_evidence_quality.py`:

```python
from core.utils.evidence_quality import fingpt_annotation_quality_bonus


def test_fingpt_annotation_quality_bonus_is_capped():
    metadata = {
        "fingpt_annotations": [
            {"task": "sentiment", "label": "positive", "confidence": 0.91},
            {"task": "headline", "label": "price_up", "confidence": 0.88},
            {"task": "ner", "label": "MSFT", "confidence": 0.77},
            {"task": "relation", "label": "supplier", "confidence": 0.93},
            {"task": "sentiment", "label": "neutral", "confidence": 0.80},
        ]
    }
    assert fingpt_annotation_quality_bonus(metadata) == 0.1
```

- [ ] **Step 6: Run prompt and evidence tests**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_prompt_context.py tests\test_evidence_quality.py tests\test_ollama_adapter.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add pipelines/infer/ollama_adapter.py core/utils/evidence_quality.py tests/test_fingpt_prompt_context.py tests/test_evidence_quality.py
git commit -m "feat: use FinGPT annotations in evidence context"
```

Expected result:

```text
[branch <sha>] feat: use FinGPT annotations in evidence context
```

### Task 7: Add FinGPT Evaluation Harness For qwen, gemma4, And Task Adapters

**Files:**

- Create: `pipelines/fingpt/evaluation.py`
- Create: `scripts/evaluate_fingpt_tasks.py`
- Create: `tests/fixtures/fingpt_eval_cases.jsonl`
- Test: `tests/test_fingpt_evaluation.py`

- [ ] **Step 1: Add deterministic fixture cases**

Create `tests/fixtures/fingpt_eval_cases.jsonl`:

```jsonl
{"case_id":"sent-1","task":"sentiment","input_text":"Company revenue rose and margins expanded after strong demand.","expected_label":"positive","ticker":"MSFT"}
{"case_id":"sent-2","task":"sentiment","input_text":"The company cut guidance after weaker orders and higher costs.","expected_label":"negative","ticker":"AAPL"}
{"case_id":"headline-1","task":"headline","input_text":"Shares climb after earnings beat expectations","expected_label":"price_up","ticker":"NVDA"}
{"case_id":"headline-2","task":"headline","input_text":"Stock falls as regulator opens investigation","expected_label":"price_down","ticker":"TSLA"}
```

- [ ] **Step 2: Write failing evaluation tests**

Create `tests/test_fingpt_evaluation.py`:

```python
from pathlib import Path

from pipelines.fingpt.evaluation import evaluate_cases, load_eval_cases


def test_load_eval_cases_reads_jsonl_fixture():
    path = Path("tests/fixtures/fingpt_eval_cases.jsonl")
    cases = load_eval_cases(path)
    assert len(cases) == 4
    assert cases[0].case_id == "sent-1"
    assert cases[0].task == "sentiment"


def test_evaluate_cases_counts_accuracy():
    cases = load_eval_cases(Path("tests/fixtures/fingpt_eval_cases.jsonl"))[:2]

    def predictor(case):
        return "positive" if "rose" in case.input_text else "negative"

    result = evaluate_cases(cases, route="rule-test", predictor=predictor)
    assert result.total == 2
    assert result.correct == 2
    assert result.accuracy == 1.0
    assert result.invalid_outputs == 0
```

- [ ] **Step 3: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_evaluation.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'pipelines.fingpt.evaluation'
```

- [ ] **Step 4: Implement evaluation helpers**

Create `pipelines/fingpt/evaluation.py`:

```python
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from core.schemas.fingpt import FinGPTEvaluationCase, FinGPTEvaluationResult


def load_eval_cases(path: Path) -> list[FinGPTEvaluationCase]:
    cases: list[FinGPTEvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(FinGPTEvaluationCase.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid evaluation case at {path}:{line_number}: {exc}") from exc
    return cases


def normalize_label(label: str) -> str:
    value = str(label or "").strip().lower()
    aliases = {
        "positive": "positive",
        "pos": "positive",
        "bullish": "positive",
        "negative": "negative",
        "neg": "negative",
        "bearish": "negative",
        "neutral": "neutral",
        "mixed": "mixed",
        "yes": "price_up",
        "no": "not_price_up",
        "price up": "price_up",
        "price_up": "price_up",
        "up": "price_up",
        "price down": "price_down",
        "price_down": "price_down",
        "down": "price_down",
    }
    return aliases.get(value, value)


def evaluate_cases(
    cases: list[FinGPTEvaluationCase],
    *,
    route: str,
    predictor: Callable[[FinGPTEvaluationCase], str],
) -> FinGPTEvaluationResult:
    started = time.time()
    correct = 0
    invalid = 0
    task = cases[0].task if cases else "sentiment"
    for case in cases:
        try:
            predicted = normalize_label(predictor(case))
        except Exception:  # noqa: BLE001
            invalid += 1
            continue
        expected = normalize_label(case.expected_label)
        if predicted == expected:
            correct += 1
    total = len(cases)
    return FinGPTEvaluationResult(
        route=route,
        task=task,
        total=total,
        correct=correct,
        accuracy=(correct / total) if total else 0.0,
        invalid_outputs=invalid,
        latency_s=round(time.time() - started, 3),
    )


def result_to_json(result: FinGPTEvaluationResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
```

- [ ] **Step 5: Add CLI harness**

Create `scripts/evaluate_fingpt_tasks.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from pipelines.fingpt.evaluation import evaluate_cases, load_eval_cases, result_to_json


def rule_predictor(case):
    text = case.input_text.lower()
    if any(token in text for token in ("rose", "expanded", "beat", "climb", "strong")):
        return "positive" if case.task == "sentiment" else "price_up"
    if any(token in text for token in ("cut", "weaker", "falls", "investigation", "higher costs")):
        return "negative" if case.task == "sentiment" else "price_down"
    return "neutral"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate FinGPT-style financial task cases.")
    parser.add_argument("--cases", default="tests/fixtures/fingpt_eval_cases.jsonl")
    parser.add_argument("--route", default="rule-baseline")
    args = parser.parse_args()
    cases = load_eval_cases(Path(args.cases))
    result = evaluate_cases(cases, route=args.route, predictor=rule_predictor)
    print(result_to_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run tests and CLI**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_evaluation.py -q
.\venv311\Scripts\python.exe scripts\evaluate_fingpt_tasks.py --cases tests\fixtures\fingpt_eval_cases.jsonl --route rule-baseline
```

Expected result:

```text
2 passed
{"accuracy": 1.0, "correct": 4, "invalid_outputs": 0, "latency_s": <number>, "route": "rule-baseline", "task": "sentiment", "total": 4}
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add pipelines/fingpt/evaluation.py scripts/evaluate_fingpt_tasks.py tests/fixtures/fingpt_eval_cases.jsonl tests/test_fingpt_evaluation.py
git commit -m "feat: add FinGPT task evaluation harness"
```

Expected result:

```text
[branch <sha>] feat: add FinGPT task evaluation harness
```

### Task 8: Add Forecaster-Style Auxiliary Signals

**Files:**

- Create: `pipelines/fingpt/forecaster_features.py`
- Modify: `core/schemas/fingpt.py`
- Modify: `pipelines/orchestration/quant_lab_pipeline.py`
- Test: `tests/test_fingpt_forecaster_features.py`

- [ ] **Step 1: Extend schema**

Add to `core/schemas/fingpt.py`:

```python
class FinGPTForecasterSignal(BaseModel):
    ticker: str
    horizon: str = "1w"
    direction: Literal["up", "down", "neutral"]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_doc_ids: list[str] = Field(default_factory=list)
    source: str = "fingpt-forecaster-auxiliary"
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_fingpt_forecaster_features.py`:

```python
from pipelines.fingpt.forecaster_features import build_forecaster_signal


def test_build_forecaster_signal_uses_sentiment_majority():
    signal = build_forecaster_signal(
        ticker="MSFT",
        annotations=[
            {"task": "sentiment", "label": "positive", "confidence": 0.9, "article_id": "a1"},
            {"task": "headline", "label": "price_up", "confidence": 0.8, "article_id": "a2"},
        ],
        structured_metrics={"price_return_20d": 0.04},
    )
    assert signal.ticker == "MSFT"
    assert signal.direction == "up"
    assert signal.confidence >= 0.5
    assert signal.evidence_doc_ids == ["a1", "a2"]


def test_build_forecaster_signal_is_neutral_when_evidence_is_mixed():
    signal = build_forecaster_signal(
        ticker="AAPL",
        annotations=[
            {"task": "sentiment", "label": "positive", "confidence": 0.7, "article_id": "a1"},
            {"task": "sentiment", "label": "negative", "confidence": 0.7, "article_id": "a2"},
        ],
        structured_metrics={},
    )
    assert signal.direction == "neutral"
```

- [ ] **Step 3: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_forecaster_features.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'pipelines.fingpt.forecaster_features'
```

- [ ] **Step 4: Implement signal builder**

Create `pipelines/fingpt/forecaster_features.py`:

```python
from __future__ import annotations

from typing import Any

from core.schemas.fingpt import FinGPTForecasterSignal


POSITIVE_LABELS = {"positive", "price_up", "up", "bullish"}
NEGATIVE_LABELS = {"negative", "price_down", "down", "bearish"}


def _score_annotation(annotation: dict[str, Any]) -> float:
    label = str(annotation.get("label") or "").lower()
    confidence = float(annotation.get("confidence") or 0.0)
    if label in POSITIVE_LABELS:
        return confidence
    if label in NEGATIVE_LABELS:
        return -confidence
    return 0.0


def build_forecaster_signal(
    *,
    ticker: str,
    annotations: list[dict[str, Any]],
    structured_metrics: dict[str, Any],
    horizon: str = "1w",
) -> FinGPTForecasterSignal:
    annotation_score = sum(_score_annotation(item) for item in annotations)
    metric_score = 0.0
    if float(structured_metrics.get("price_return_20d") or 0.0) > 0.02:
        metric_score += 0.2
    if float(structured_metrics.get("price_return_20d") or 0.0) < -0.02:
        metric_score -= 0.2
    total = annotation_score + metric_score
    if total > 0.25:
        direction = "up"
    elif total < -0.25:
        direction = "down"
    else:
        direction = "neutral"
    evidence_doc_ids = [
        str(item.get("article_id"))
        for item in annotations
        if item.get("article_id")
    ][:10]
    confidence = min(0.95, max(0.1, abs(total) / max(1.0, len(annotations))))
    return FinGPTForecasterSignal(
        ticker=ticker.upper(),
        horizon=horizon,
        direction=direction,
        confidence=round(confidence, 3),
        rationale=f"Auxiliary FinGPT-style signal from {len(annotations)} labels and structured metrics.",
        evidence_doc_ids=evidence_doc_ids,
    )
```

- [ ] **Step 5: Integrate as Quant Lab metadata only**

Modify `pipelines/orchestration/quant_lab_pipeline.py` where research output or latest sentiment is converted into quant metadata. Add a non-blocking optional field:

```python
    forecaster_signal = None
    try:
        from pipelines.fingpt.forecaster_features import build_forecaster_signal
        forecaster_signal = build_forecaster_signal(
            ticker=ticker,
            annotations=list((latest.get("execution_meta") or {}).get("extras", {}).get("fingpt_annotations", {}).get("annotations", []) or []),
            structured_metrics={},
        ).model_dump(mode="json")
    except Exception:
        forecaster_signal = None
```

Attach it under diagnostics/metadata:

```python
    if forecaster_signal:
        diagnostics["fingpt_forecaster_signal"] = forecaster_signal
```

- [ ] **Step 6: Run tests**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_fingpt_forecaster_features.py tests\test_quant_lab_pipeline.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add core/schemas/fingpt.py pipelines/fingpt/forecaster_features.py pipelines/orchestration/quant_lab_pipeline.py tests/test_fingpt_forecaster_features.py
git commit -m "feat: add FinGPT forecaster auxiliary signal"
```

Expected result:

```text
[branch <sha>] feat: add FinGPT forecaster auxiliary signal
```

### Task 9: Expose Status, Diagnostics, And Documentation

**Files:**

- Modify: `app/api/routers/system.py`
- Modify: `app/web/app.js`
- Create: `docs/FINGPT_DATA_INTEGRATION.md`
- Test: `tests/test_api_routing_contract.py`
- Test: `tests/test_ui_routing_contract.py`

- [ ] **Step 1: Add API contract test**

Append to `tests/test_api_routing_contract.py`:

```python
def test_config_exposes_fingpt_integration_status():
    client = TestClient(api_server.app)
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "fingpt" in body
    assert set(body["fingpt"]) >= {"datasets_enabled", "task_model_enabled", "tasks"}
    assert "sentiment" in body["fingpt"]["tasks"]
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_api_routing_contract.py::ApiRoutingContractTests::test_config_exposes_fingpt_integration_status -q
```

Expected result:

```text
AssertionError: assert 'fingpt' in body
```

- [ ] **Step 3: Add API status**

Modify `app/api/routers/system.py` inside `get_config()`:

```python
        "fingpt": {
            "datasets_enabled": bool(getattr(_settings, "fingpt_datasets_enabled", False)),
            "task_model_enabled": bool(getattr(_settings, "fingpt_task_model_enabled", False)),
            "task_model": getattr(_settings, "fingpt_task_model_name", ""),
            "tasks": ["sentiment", "headline", "ner", "relation", "fiqa_qa", "forecaster"],
            "default_behavior": "disabled_fail_open",
        },
```

- [ ] **Step 4: Add UI diagnostic rendering**

Modify `app/web/app.js` near config rendering:

```javascript
function renderFinGPTStatus(config) {
  const status = config?.fingpt;
  const target = document.getElementById("fingptStatus");
  if (!target || !status) return;
  const enabled = status.task_model_enabled || status.datasets_enabled;
  target.textContent = enabled
    ? `FinGPT 보조 기능 활성: ${(status.tasks || []).join(", ")}`
    : "FinGPT 보조 기능 비활성: 기본 분석 경로에는 영향 없음";
  target.classList.toggle("is-enabled", !!enabled);
}
```

Call it after config load:

```javascript
renderFinGPTStatus(state.config);
```

If there is no existing element, add a compact diagnostics line in `app/web/index.html`:

```html
<div id="fingptStatus" class="muted">FinGPT 보조 기능 상태 확인 중</div>
```

- [ ] **Step 5: Add documentation**

Create `docs/FINGPT_DATA_INTEGRATION.md`:

```markdown
# FinGPT Data Integration

## Purpose

This project uses FinGPT as an auxiliary financial-task subsystem, not as the default final report generator.

## Default Behavior

- `qwen2.5:7b` remains the production final JSON/report route.
- `gemma4:e4b` is an explicit experimental comparison route.
- FinGPT datasets and task models are disabled by default.
- FinGPT failures are fail-open and must not block collection, retrieval, UI startup, or final report generation.

## Enable Dataset Evaluation

Set:

```env
FINGPT_DATASETS_ENABLED=true
FINGPT_DATASET_MAX_ROWS=500
```

Run:

```powershell
.\venv311\Scripts\python.exe scripts\evaluate_fingpt_tasks.py --cases tests\fixtures\fingpt_eval_cases.jsonl --route rule-baseline
```

## Enable Task Model Inference

Install optional dependencies in a separate environment profile:

```powershell
.\venv311\Scripts\python.exe -m pip install transformers torch peft accelerate datasets
```

Set:

```env
FINGPT_TASK_MODEL_ENABLED=true
FINGPT_TASK_MODEL_NAME=FinGPT/fingpt-mt_llama3-8b_lora
RISK_ENGINE=fingpt
```

## Acceptance Criteria

- Default startup works with no Hugging Face packages installed.
- `/api/v1/config` reports FinGPT status.
- qwen and gemma4 routes remain selectable.
- Annotation failure never changes a successful analysis into failed.
- Evaluation artifacts report total, correct, accuracy, invalid outputs, and latency.
```

- [ ] **Step 6: Run API/UI/docs tests**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_api_routing_contract.py tests\test_ui_routing_contract.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add app/api/routers/system.py app/web/app.js app/web/index.html docs/FINGPT_DATA_INTEGRATION.md tests/test_api_routing_contract.py tests/test_ui_routing_contract.py
git commit -m "docs: expose FinGPT integration status"
```

Expected result:

```text
[branch <sha>] docs: expose FinGPT integration status
```

### Task 10: Add End-To-End Validation Gate

**Files:**

- Modify: `scripts/validation_gate.py`
- Modify: `docs/RUNBOOK.md`
- Test: `tests/test_validation_gate.py`

- [ ] **Step 1: Add validation gate test**

Append to `tests/test_validation_gate.py`:

```python
def test_validation_gate_includes_fingpt_eval_step(monkeypatch, tmp_path):
    from scripts import validation_gate

    calls = []

    def fake_run_command(*args, **kwargs):
        calls.append(args[0])
        return validation_gate.CommandResult(
            name="fake",
            command=args[0],
            returncode=0,
            stdout='{"accuracy":1.0,"total":4,"correct":4,"invalid_outputs":0}',
            stderr="",
            elapsed_s=0.01,
        )

    monkeypatch.setattr(validation_gate, "run_command", fake_run_command)
    result = validation_gate.run_validation(project_root=tmp_path, include_fingpt_eval=True)
    assert result["status"] == "passed"
    assert any("evaluate_fingpt_tasks.py" in " ".join(cmd) for cmd in calls)
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_validation_gate.py::test_validation_gate_includes_fingpt_eval_step -q
```

Expected result:

```text
TypeError: run_validation() got an unexpected keyword argument 'include_fingpt_eval'
```

- [ ] **Step 3: Add validation gate step**

Modify `scripts/validation_gate.py` by adding a parameter to `run_validation`:

```python
def run_validation(..., include_fingpt_eval: bool = False, ...):
```

Add this command after lightweight unit tests and before browser/UI gates:

```python
    if include_fingpt_eval:
        results.append(
            run_command(
                [
                    sys.executable,
                    "scripts/evaluate_fingpt_tasks.py",
                    "--cases",
                    "tests/fixtures/fingpt_eval_cases.jsonl",
                    "--route",
                    "rule-baseline",
                ],
                cwd=project_root,
                name="fingpt_eval",
            )
        )
```

Add CLI flag:

```python
parser.add_argument("--include-fingpt-eval", action="store_true")
```

Pass it into `run_validation`.

- [ ] **Step 4: Document runbook command**

Modify `docs/RUNBOOK.md`:

```markdown
### FinGPT Auxiliary Evaluation

Run this before promoting changes that touch FinGPT annotations, model routing, evidence scoring, or evaluation:

```powershell
.\venv311\Scripts\python.exe scripts\validation_gate.py --include-fingpt-eval
```

Expected result:

- `fingpt_eval` status is passed.
- `invalid_outputs` is `0`.
- Default qwen route still appears in `/api/v1/config`.
- `gemma4` appears as an experimental route when configured.
```

- [ ] **Step 5: Run validation tests**

Run:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_validation_gate.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 6: Run full focused gate**

Run:

```powershell
.\venv311\Scripts\python.exe scripts\validation_gate.py --include-fingpt-eval
```

Expected result:

```text
status: passed
```

If the project prints JSON instead of text, expected JSON contains:

```json
{
  "status": "passed",
  "checks": {
    "fingpt_eval": "passed"
  }
}
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add scripts/validation_gate.py docs/RUNBOOK.md tests/test_validation_gate.py
git commit -m "test: add FinGPT auxiliary validation gate"
```

Expected result:

```text
[branch <sha>] test: add FinGPT auxiliary validation gate
```

## Validation Matrix

Run these after all tasks are complete:

```powershell
.\venv311\Scripts\python.exe -m pytest `
  tests\test_fingpt_catalog.py `
  tests\test_fingpt_datasets.py `
  tests\test_fingpt_annotation_repository.py `
  tests\test_fingpt_task_adapter.py `
  tests\test_fingpt_annotation_service.py `
  tests\test_fingpt_prompt_context.py `
  tests\test_fingpt_evaluation.py `
  tests\test_fingpt_forecaster_features.py `
  tests\test_risk_factory.py `
  tests\test_data_mart_schema.py `
  tests\test_data_mart_repository.py `
  tests\test_collection_reliability.py `
  tests\test_ollama_adapter.py `
  tests\test_quant_lab_pipeline.py `
  tests\test_api_routing_contract.py `
  tests\test_ui_routing_contract.py `
  tests\test_validation_gate.py -q
```

Expected result:

```text
all selected tests passed
```

Run CLI evaluation:

```powershell
.\venv311\Scripts\python.exe scripts\evaluate_fingpt_tasks.py --cases tests\fixtures\fingpt_eval_cases.jsonl --route rule-baseline
```

Expected result:

```json
{"accuracy": 1.0, "correct": 4, "invalid_outputs": 0, "route": "rule-baseline", "total": 4}
```

Run config smoke:

```powershell
$env:FINGPT_WEB_PORT=8002
powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1
```

In another shell:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/api/v1/config | ConvertTo-Json -Depth 6
```

Expected model status:

```json
{
  "models": [
    {"id": "qwen", "role": "primary"},
    {"id": "gemma4", "role": "experimental"}
  ],
  "fingpt": {
    "default_behavior": "disabled_fail_open"
  }
}
```

Run optional dependency smoke with default environment:

```powershell
$code = @'
import importlib.util
for name in ["torch", "transformers", "peft", "datasets"]:
    print(name, "present" if importlib.util.find_spec(name) else "missing")
'@
$code | .\venv311\Scripts\python.exe -
```

Expected result for the default light install:

```text
torch missing
transformers missing
peft missing
datasets missing
```

The default light install must still pass the selected tests because FinGPT datasets/models are opt-in.

## Rollout Order

1. Merge Task 1 and Task 2 first. They are read-only/catalog additions and do not affect runtime.
2. Merge Task 3 next. It adds durable storage but no pipeline behavior change.
3. Merge Task 4 and Task 5 behind disabled defaults.
4. Merge Task 6 only after annotation metadata shape is stable.
5. Merge Task 7 before using qwen/gemma4 quality claims in release notes.
6. Merge Task 8 only after Quant Lab diagnostics tolerate absent Forecaster signals.
7. Merge Task 9 and Task 10 as the operator-facing completion layer.

## Acceptance Criteria

- Default web startup works without `torch`, `transformers`, `peft`, or `datasets`.
- `/api/v1/config` still exposes `qwen` as default and `gemma4` as experimental.
- FinGPT annotation failure is visible in metadata but does not fail the run.
- Data mart annotation writes are idempotent.
- Prompt context includes FinGPT labels only when labels exist.
- Evaluation harness produces accuracy, total, correct, invalid output, and latency metrics.
- Validation gate can run FinGPT auxiliary checks explicitly.
- Documentation clearly states that FinGPT is auxiliary unless a future task promotes a specific adapter.

## Current Planning-Time Verification

These checks were run before writing this plan and define the baseline this plan must preserve:

- `.\venv311\Scripts\python.exe -m pytest tests\test_production_routing.py tests\test_api_routing_contract.py tests\test_ui_routing_contract.py -q`
  - Result: `30 passed`
- `.\venv311\Scripts\python.exe -m pytest tests\test_ollama_adapter.py -q`
  - Result: `12 passed`
- `/api/v1/config` smoke on `127.0.0.1:8002`
  - Result: `qwen` and `gemma4` model options returned.
- Browser MCP load of `http://127.0.0.1:8002/ui/`
  - Result: select options included `qwen2.5:7b` and `gemma4:e4b`.
- Ollama direct generation smoke:
  - `qwen2.5:7b`: `STATUS=ok`
  - `gemma4:e4b`: `STATUS=ok`

## Self-Review

Spec coverage:

- The plan covers where FinGPT data is useful: sentiment/headline labels, NER/relation extraction, benchmark evaluation, Forecaster auxiliary signals, and a delayed final model route.
- The plan includes concrete file paths, tests, commands, expected failures, expected passes, and commit boundaries.
- The plan keeps code changes fail-open and opt-in to protect the current local workflow.

Placeholder scan:

- No implementation step relies on unspecified behavior.
- Every task has explicit file paths and executable commands.
- Every code-changing step includes concrete code blocks.

Type consistency:

- `FinGPTTask`, `FinGPTAnnotation`, `FinGPTEvaluationCase`, `FinGPTEvaluationResult`, and `FinGPTForecasterSignal` are defined before use.
- Repository, adapter, annotation, evaluation, and Forecaster functions use stable names throughout the plan.
