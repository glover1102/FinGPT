from __future__ import annotations

from pipelines.fingpt.catalog import FINGPT_DATASETS, dataset_for_task, model_for_task


def test_catalog_contains_all_core_tasks() -> None:
    tasks = {dataset.task for dataset in FINGPT_DATASETS}

    assert tasks == {"sentiment", "headline", "ner", "relation", "fiqa_qa", "forecaster"}


def test_sentiment_dataset_returns_stable_hf_id_and_task() -> None:
    dataset = dataset_for_task("sentiment")

    assert dataset.task == "sentiment"
    assert dataset.hf_id == "FinGPT/fingpt-sentiment-train"


def test_sentiment_model_is_task_specific_and_requires_gpu() -> None:
    model = model_for_task("sentiment")

    assert model.task == "sentiment"
    assert model.hf_id.startswith("FinGPT/")
    assert model.requires_gpu is True


def test_dataset_lookup_returns_mutation_isolated_copy() -> None:
    dataset = dataset_for_task("sentiment")
    dataset.expected_columns.append("mutated")

    fresh_dataset = dataset_for_task("sentiment")

    assert "mutated" not in fresh_dataset.expected_columns
    assert fresh_dataset.expected_columns == ["input", "output"]


def test_model_lookup_returns_mutation_isolated_copy() -> None:
    model = model_for_task("sentiment")
    model.recommended_for.append("mutated")

    fresh_model = model_for_task("sentiment")

    assert "mutated" not in fresh_model.recommended_for
    assert fresh_model.recommended_for == ["sentiment", "headline"]
