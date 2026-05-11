from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from core.schemas.fingpt import FinGPTTask
from pipelines.fingpt.catalog import dataset_for_task


class FinGPTDatasetUnavailable(RuntimeError):
    """Raised when optional FinGPT dataset loading cannot be performed."""


def _coerce_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, Mapping):
        return dict(row.items())
    items = getattr(row, "items", None)
    if callable(items):
        return dict(items())
    raise FinGPTDatasetUnavailable(f"FinGPT dataset row is not mapping-like: {type(row).__name__}")


def _coerce_limit(max_rows: int) -> int:
    try:
        return max(0, int(max_rows))
    except (TypeError, ValueError) as exc:
        raise FinGPTDatasetUnavailable(f"invalid FinGPT dataset max_rows: {max_rows!r}") from exc


def _available_splits(dataset_bundle: Any) -> list[str]:
    keys = getattr(dataset_bundle, "keys", None)
    if callable(keys):
        return [str(key) for key in keys()]
    return []


def load_dataset_rows(
    task: str,
    *,
    enabled: bool,
    split: str | None = None,
    max_rows: int = 500,
    cache_dir: Path | str | None = None,
    revision: str = "main",
) -> list[dict[str, Any]]:
    if not enabled:
        raise FinGPTDatasetUnavailable("FinGPT dataset loading is disabled")

    try:
        spec = dataset_for_task(cast(FinGPTTask, task))
    except ValueError as exc:
        raise FinGPTDatasetUnavailable(f"unsupported FinGPT dataset task {task!r}") from exc

    limit = _coerce_limit(max_rows)
    if limit == 0:
        return []

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise FinGPTDatasetUnavailable(
            "FinGPT dataset loading requires the optional Hugging Face datasets package"
        ) from exc

    try:
        dataset_bundle = load_dataset(
            spec.hf_id,
            cache_dir=str(cache_dir) if cache_dir is not None else None,
            revision=revision or "main",
        )
    except Exception as exc:
        raise FinGPTDatasetUnavailable(
            f"failed to load FinGPT dataset for task {task!r} ({spec.hf_id}): {exc}"
        ) from exc

    split_name = split or spec.default_split

    try:
        dataset_split = dataset_bundle[split_name]
    except (KeyError, TypeError, AttributeError) as exc:
        available = _available_splits(dataset_bundle)
        available_text = ", ".join(available) if available else "none"
        raise FinGPTDatasetUnavailable(
            f"FinGPT dataset split {split_name!r} is unavailable; available splits: {available_text}"
        ) from exc

    rows: list[dict[str, Any]] = []
    for row in dataset_split:
        rows.append(_coerce_row(row))
        if len(rows) >= limit:
            break
    return rows
