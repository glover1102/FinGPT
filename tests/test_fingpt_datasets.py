from __future__ import annotations

import builtins
import importlib
import sys
from types import ModuleType
from typing import Any

import pytest

import pipelines.fingpt.datasets as fingpt_datasets_module


def test_disabled_raises() -> None:
    with pytest.raises(fingpt_datasets_module.FinGPTDatasetUnavailable, match="disabled"):
        fingpt_datasets_module.load_dataset_rows("sentiment", enabled=False)


def test_importing_module_does_not_import_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "datasets", raising=False)
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "datasets":
            raise AssertionError("datasets must not be imported at module import time")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    importlib.reload(fingpt_datasets_module)


def test_fake_datasets_module_returns_limited_normalized_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    module = ModuleType("datasets")

    class MappingLike:
        def __init__(self, value: str) -> None:
            self.value = value

        def items(self) -> list[tuple[str, str]]:
            return [("input", self.value), ("output", "positive")]

    def fake_load_dataset(hf_id: str, cache_dir: str | None = None) -> dict[str, list[Any]]:
        calls.append({"hf_id": hf_id, "cache_dir": cache_dir})
        return {"train": [MappingLike("a"), {"input": "b", "output": "negative"}, {"input": "c"}]}

    module.load_dataset = fake_load_dataset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datasets", module)

    rows = fingpt_datasets_module.load_dataset_rows("sentiment", enabled=True, max_rows=2, cache_dir="cache-path")

    assert calls == [{"hf_id": "FinGPT/fingpt-sentiment-train", "cache_dir": "cache-path"}]
    assert rows == [
        {"input": "a", "output": "positive"},
        {"input": "b", "output": "negative"},
    ]


def test_load_dataset_failure_is_wrapped_with_task_and_hf_id(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("datasets")

    def fake_load_dataset(hf_id: str, cache_dir: str | None = None) -> Any:
        raise RuntimeError("offline")

    module.load_dataset = fake_load_dataset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datasets", module)

    with pytest.raises(fingpt_datasets_module.FinGPTDatasetUnavailable) as exc_info:
        fingpt_datasets_module.load_dataset_rows("sentiment", enabled=True)

    message = str(exc_info.value)
    assert "sentiment" in message
    assert "FinGPT/fingpt-sentiment-train" in message
    assert "offline" in message


def test_missing_dependency_raises_message_containing_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "datasets", raising=False)
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "datasets":
            raise ImportError("missing optional dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(fingpt_datasets_module.FinGPTDatasetUnavailable, match="datasets"):
        fingpt_datasets_module.load_dataset_rows("sentiment", enabled=True)


def test_invalid_task_raises_dataset_unavailable() -> None:
    with pytest.raises(fingpt_datasets_module.FinGPTDatasetUnavailable, match="unsupported FinGPT dataset task"):
        fingpt_datasets_module.load_dataset_rows("not_a_task", enabled=True)


def test_missing_split_error_lists_available_split_names(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("datasets")

    def fake_load_dataset(hf_id: str, cache_dir: str | None = None) -> dict[str, list[dict[str, str]]]:
        return {
            "validation": [{"input": "a", "output": "positive"}],
            "test": [{"input": "b", "output": "negative"}],
        }

    module.load_dataset = fake_load_dataset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datasets", module)

    with pytest.raises(fingpt_datasets_module.FinGPTDatasetUnavailable) as exc_info:
        fingpt_datasets_module.load_dataset_rows("sentiment", enabled=True, split="train")

    message = str(exc_info.value)
    assert "validation" in message
    assert "test" in message


def test_max_rows_zero_returns_empty_without_importing_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "datasets", raising=False)

    rows = fingpt_datasets_module.load_dataset_rows("sentiment", enabled=True, max_rows=0)

    assert rows == []
