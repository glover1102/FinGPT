from core.schemas.retrieval import RetrievalItem
from pipelines.infer.ollama_adapter import _build_ollama_prompt


def _fingpt_annotation_line(prompt: str) -> str:
    return next(line for line in prompt.splitlines() if line.startswith("FINGPT ANNOTATIONS:"))


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


def test_fingpt_annotation_prompt_counts_valid_entries_after_filtering():
    item = RetrievalItem(
        source="news",
        title="MSFT annotation stress",
        date="2026-05-01",
        chunk="Microsoft reported multiple FinGPT labels.",
        score=0.9,
        metadata={
            "doc_id": "doc-1",
            "fingpt_annotations": [
                "bad-entry",
                {"task": "", "label": "ignored", "confidence": 0.9},
                {"task": "sentiment", "label": "positive", "confidence": 0.91},
                {"task": "headline", "label": "price_up", "confidence": "0.82"},
                {"task": "ner", "label": "MSFT", "confidence": 1},
                {"task": "relation", "label": "supplier", "confidence": 0.76},
                {"task": "forecaster", "label": "up", "confidence": 0.79},
                {"task": "fiqa_qa", "label": "ignored_after_limit", "confidence": 0.99},
            ],
        },
    )

    prompt, chunks = _build_ollama_prompt("MSFT", "Assess the thesis", [item], "general", "12m")

    assert chunks == 1
    assert "sentiment=positive confidence=0.91" in prompt
    assert "headline=price_up confidence=0.82" in prompt
    assert "ner=MSFT confidence=1.00" in prompt
    assert "relation=supplier confidence=0.76" in prompt
    assert "forecaster=up confidence=0.79" in prompt
    assert "fiqa_qa=ignored_after_limit" not in prompt


def test_fingpt_annotation_prompt_formats_non_numeric_confidence_as_unknown():
    item = RetrievalItem(
        source="news",
        title="MSFT annotation malformed confidence",
        date="2026-05-01",
        chunk="Microsoft reported multiple FinGPT labels.",
        score=0.9,
        metadata={
            "doc_id": "doc-1",
            "fingpt_annotations": [
                {"task": "sentiment", "label": "positive", "confidence": "high"},
                {"task": "headline", "label": "price_up", "confidence": {"score": 0.82}},
            ],
        },
    )

    prompt, chunks = _build_ollama_prompt("MSFT", "Assess the thesis", [item], "general", "12m")

    assert chunks == 1
    assert "sentiment=positive confidence=unknown" in prompt
    assert "headline=price_up confidence=unknown" in prompt


def test_fingpt_annotation_prompt_compacts_and_truncates_task_and_label():
    raw_task = "sentiment\nwith\tvery    long " + ("x" * 80)
    raw_label = "price\nup\twith    large label " + ("y" * 160)
    expected_task = " ".join(raw_task.split())[:32]
    expected_label = " ".join(raw_label.split())[:96]
    item = RetrievalItem(
        source="news",
        title="MSFT annotation bloated fields",
        date="2026-05-01",
        chunk="Microsoft reported multiple FinGPT labels.",
        score=0.9,
        metadata={
            "doc_id": "doc-1",
            "fingpt_annotations": [
                {"task": raw_task, "label": raw_label, "confidence": 0.91},
            ],
        },
    )

    prompt, chunks = _build_ollama_prompt("MSFT", "Assess the thesis", [item], "general", "12m")
    annotation_line = _fingpt_annotation_line(prompt)

    assert chunks == 1
    assert f"{expected_task}={expected_label} confidence=0.91" in annotation_line
    assert "\n" not in annotation_line
    assert "\t" not in annotation_line
    assert raw_task not in annotation_line
    assert raw_label not in annotation_line
