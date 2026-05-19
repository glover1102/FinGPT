"""Tests for the optional FinGPT task adapter."""
from __future__ import annotations

import builtins
import sys
import types
import unittest
from unittest.mock import patch

from pipelines.fingpt.task_adapter import FinGPTTaskAdapter, FinGPTTaskUnavailable


class FinGPTTaskAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        FinGPTTaskAdapter._pipeline_cache.clear()
        self.addCleanup(FinGPTTaskAdapter._pipeline_cache.clear)

    def test_disabled_raises_without_importing_transformers(self) -> None:
        adapter = FinGPTTaskAdapter(enabled=False, model_name="model-a")

        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "transformers":
                raise AssertionError("transformers must not be imported when disabled")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", guarded_import):
            with self.assertRaises(FinGPTTaskUnavailable):
                adapter._load_pipeline()

    def test_positional_constructor_disabled_label_texts_raises(self) -> None:
        adapter = FinGPTTaskAdapter(False, "model-id")

        with self.assertRaises(FinGPTTaskUnavailable):
            adapter.label_texts("sentiment", ["risk flag"])

    def test_fake_transformers_pipeline_maps_outputs_to_annotations(self) -> None:
        calls: list[tuple[str, str, int]] = []

        def fake_pipeline(task, *, model, device):
            calls.append((task, model, device))

            def classifier(texts, **kwargs):
                self.assertEqual(kwargs, {"truncation": True, "max_length": 256})
                return [
                    [{"label": "Positive", "score": 0.91}, {"label": "negative", "score": 0.05}],
                    {"label": "NEGATIVE", "score": 0.82},
                ]

            return classifier

        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = fake_pipeline

        with patch.dict(sys.modules, {"transformers": fake_transformers}):
            adapter = FinGPTTaskAdapter(enabled=True, model_name="model-a", device=-1)
            annotations = adapter.label_texts("sentiment", ["  strong growth  ", "", "margin pressure"])

        self.assertEqual(calls, [("text-classification", "model-a", -1)])
        self.assertEqual([item.article_id for item in annotations], ["inline-0", "inline-1"])
        self.assertEqual([item.label for item in annotations], ["positive", "negative"])
        self.assertEqual([item.confidence for item in annotations], [0.91, 0.82])
        self.assertEqual([item.source for item in annotations], ["fingpt-task-adapter", "fingpt-task-adapter"])
        self.assertEqual([item.model_id for item in annotations], ["model-a", "model-a"])
        self.assertEqual(annotations[0].metadata["text_preview"], "strong growth")

    def test_missing_transformers_raises_unavailable(self) -> None:
        real_import = builtins.__import__

        def missing_transformers(name, *args, **kwargs):
            if name == "transformers":
                raise ModuleNotFoundError("No module named 'transformers'")
            return real_import(name, *args, **kwargs)

        adapter = FinGPTTaskAdapter(enabled=True, model_name="model-a")
        with patch.dict(sys.modules, {}, clear=False):
            sys.modules.pop("transformers", None)
            with patch("builtins.__import__", missing_transformers):
                with self.assertRaises(FinGPTTaskUnavailable):
                    adapter._load_pipeline()

    def test_cache_is_keyed_by_model_name_and_device(self) -> None:
        calls: list[tuple[str, int]] = []

        def fake_pipeline(task, *, model, device):
            calls.append((model, device))
            return lambda texts, **kwargs: [{"label": f"{model}:{device}", "score": 0.7} for _ in texts]

        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = fake_pipeline

        with patch.dict(sys.modules, {"transformers": fake_transformers}):
            first = FinGPTTaskAdapter(enabled=True, model_name="model-a", device=-1)
            second = FinGPTTaskAdapter(enabled=True, model_name="model-b", device=-1)
            third = FinGPTTaskAdapter(enabled=True, model_name="model-a", device=0)
            again = FinGPTTaskAdapter(enabled=True, model_name="model-a", device=-1)

            self.assertEqual(first.label_texts("sentiment", ["x"])[0].label, "model-a:-1")
            self.assertEqual(second.label_texts("sentiment", ["x"])[0].label, "model-b:-1")
            self.assertEqual(third.label_texts("sentiment", ["x"])[0].label, "model-a:0")
            self.assertEqual(again.label_texts("sentiment", ["x"])[0].label, "model-a:-1")

        self.assertEqual(calls, [("model-a", -1), ("model-b", -1), ("model-a", 0)])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
