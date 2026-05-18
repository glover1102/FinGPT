"""Tests for the pluggable risk engine factory.

Scope
-----
- Default / unknown settings resolve to HeuristicRiskEngine without side effects.
- FinBERT path falls back to heuristic when transformers is unavailable or the
  model can't load (no hard crash during evaluate stage).
- The pipeline consumes the factory, not a hardcoded HeuristicRiskEngine.

We patch the FinBERT classifier loader rather than importing real transformers
weights so CI stays fast + offline-friendly.
"""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipelines.analyze.risk_analysis import HeuristicRiskEngine
from pipelines.analyze.risk_factory import get_risk_engine


def _mk_settings(engine: str, *, fingpt_enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        risk_engine=engine,
        finbert_model_name="ProsusAI/finbert",
        fingpt_task_model_enabled=fingpt_enabled,
        fingpt_task_model_name="FinGPT/fingpt-mt_llama3-8b_lora",
    )


class RiskFactoryTests(unittest.TestCase):
    def test_default_resolves_to_heuristic(self) -> None:
        engine = get_risk_engine(settings=_mk_settings("heuristic"))
        self.assertIsInstance(engine, HeuristicRiskEngine)

    def test_unknown_engine_falls_back_to_heuristic(self) -> None:
        engine = get_risk_engine(settings=_mk_settings("chatgpt"))
        self.assertIsInstance(engine, HeuristicRiskEngine)

    def test_explicit_override_beats_settings(self) -> None:
        engine = get_risk_engine("heuristic", settings=_mk_settings("finbert"))
        self.assertIsInstance(engine, HeuristicRiskEngine)

    def test_finbert_falls_back_when_unavailable(self) -> None:
        """When transformers/weights aren't installed, we must not crash."""
        from pipelines.analyze import finbert_risk_engine

        # Simulate missing deps by forcing _load_classifier to raise the
        # FinBertUnavailable sentinel the factory knows to catch.
        def _boom(self):
            raise finbert_risk_engine.FinBertUnavailable("transformers not installed in test env")

        with patch.object(finbert_risk_engine.FinBertRiskEngine, "_load_classifier", _boom):
            engine = get_risk_engine(settings=_mk_settings("finbert"))
        self.assertIsInstance(engine, HeuristicRiskEngine)

    def test_finbert_falls_back_on_unexpected_loader_exception(self) -> None:
        from pipelines.analyze import finbert_risk_engine

        with patch.object(
            finbert_risk_engine.FinBertRiskEngine,
            "_load_classifier",
            lambda self: (_ for _ in ()).throw(RuntimeError("bad runtime")),
        ):
            engine = get_risk_engine(settings=_mk_settings("finbert"))
        self.assertIsInstance(engine, HeuristicRiskEngine)

    def test_fingpt_disabled_falls_back_to_heuristic(self) -> None:
        engine = get_risk_engine(settings=_mk_settings("fingpt", fingpt_enabled=False))
        self.assertIsInstance(engine, HeuristicRiskEngine)

    def test_fingpt_success_returns_fingpt_risk_engine_without_eager_load(self) -> None:
        from pipelines.fingpt.risk_engine import FinGPTRiskEngine
        from pipelines.fingpt.task_adapter import FinGPTTaskAdapter

        with patch.object(
            FinGPTTaskAdapter,
            "_load_pipeline",
            lambda self: (_ for _ in ()).throw(AssertionError("must not load synchronously")),
        ):
            engine = get_risk_engine(settings=_mk_settings("fingpt", fingpt_enabled=True))
        self.assertIsInstance(engine, FinGPTRiskEngine)

    def test_heuristic_risk_engine_reinforces_single_bull_from_summary(self) -> None:
        engine = HeuristicRiskEngine()
        raw = {
            "summary": "아마존은 AWS와 AI 수익화 기회가 커지고 있어 장기 성장과 경쟁력 개선 여지가 있습니다.",
            "bull_points": ["AWS 파트너십 확대는 클라우드 성장에 긍정적입니다."],
            "bear_points": ["리테일 마진 압박이 수익성에 부정적입니다.", "AI 경쟁이 가격 인하 압력으로 이어질 수 있습니다."],
        }

        result = asyncio.run(engine.evaluate_risk(raw))

        self.assertGreaterEqual(len(result.bull_points), 2)
        self.assertIn("보조 상방 논점", result.bull_points[1])

    def test_heuristic_risk_engine_reinforces_single_bear_from_summary(self) -> None:
        engine = HeuristicRiskEngine()
        raw = {
            "summary": "수요 둔화와 경쟁 심화는 단기 마진 압박 리스크를 키울 수 있습니다.",
            "bull_points": ["신제품 출시가 매출 회복을 이끌 수 있습니다.", "비용 통제는 수익성 방어에 기여합니다."],
            "bear_points": ["수요 둔화는 매출 추정치 하향으로 이어질 수 있습니다."],
        }

        result = asyncio.run(engine.evaluate_risk(raw))

        self.assertGreaterEqual(len(result.bear_points), 2)
        self.assertIn("보조 하방 리스크", result.bear_points[1])


class FinBertEngineTests(unittest.TestCase):
    def test_passthrough_when_llm_already_bucketed_points(self) -> None:
        """If bull/bear already exist, FinBERT path must not touch them."""
        from pipelines.analyze.finbert_risk_engine import FinBertRiskEngine

        engine = FinBertRiskEngine()
        raw = {
            "bull_points": ["margin expansion"],
            "bear_points": ["FX headwind"],
            "risk_flags": ["ignored"],
        }
        # Should not need to load the classifier at all in this path.
        with patch.object(FinBertRiskEngine, "_load_classifier", lambda self: (_ for _ in ()).throw(AssertionError("must not be called"))):
            result = asyncio.run(engine.evaluate_risk(raw))
        self.assertEqual(result.bull_points, ["margin expansion"])
        self.assertEqual(result.bear_points, ["FX headwind"])

    def test_classifies_risk_flags_when_points_missing(self) -> None:
        from pipelines.analyze.finbert_risk_engine import FinBertRiskEngine

        engine = FinBertRiskEngine()
        raw = {"risk_flags": ["strong revenue beat", "demand softness", "guidance in-line"]}

        # Stand-in classifier aligned with Hugging Face output shape
        # (list-of-list when top_k=None).
        def _fake_classifier(texts, **kwargs):
            mapping = {
                "strong revenue beat": "positive",
                "demand softness": "negative",
                "guidance in-line": "neutral",
            }
            return [[{"label": mapping.get(t, "neutral"), "score": 0.9}] for t in texts]

        with patch.object(FinBertRiskEngine, "_load_classifier", lambda self: _fake_classifier):
            result = asyncio.run(engine.evaluate_risk(raw))
        self.assertEqual(result.bull_points, ["strong revenue beat"])
        self.assertEqual(result.bear_points, ["demand softness"])
        # Neutrals are dropped intentionally.
        self.assertNotIn("guidance in-line", result.bull_points + result.bear_points)


class FinGPTRiskEngineTests(unittest.TestCase):
    def test_passthrough_when_llm_already_bucketed_points(self) -> None:
        from pipelines.fingpt.risk_engine import FinGPTRiskEngine

        adapter = SimpleNamespace(label_texts=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not classify")))
        engine = FinGPTRiskEngine(adapter)  # type: ignore[arg-type]
        raw = {
            "bull_points": ["margin expansion"],
            "bear_points": ["FX headwind"],
            "risk_flags": ["ignored"],
        }

        result = asyncio.run(engine.evaluate_risk(raw))

        self.assertEqual(result.bull_points, ["margin expansion"])
        self.assertEqual(result.bear_points, ["FX headwind"])

    def test_classifies_risk_flags_when_points_missing(self) -> None:
        from core.schemas.fingpt import FinGPTAnnotation
        from pipelines.fingpt.risk_engine import FinGPTRiskEngine

        class FakeAdapter:
            def label_texts(self, task, texts):
                self.task = task
                labels = {
                    "strong revenue beat": "positive",
                    "demand softness": "negative",
                    "guidance in-line": "neutral",
                }
                return [
                    FinGPTAnnotation(article_id=f"inline-{index}", task=task, label=labels[text])
                    for index, text in enumerate(texts)
                ]

        adapter = FakeAdapter()
        engine = FinGPTRiskEngine(adapter)  # type: ignore[arg-type]
        raw = {"risk_flags": ["strong revenue beat", "demand softness", "guidance in-line"]}

        result = asyncio.run(engine.evaluate_risk(raw))

        self.assertEqual(adapter.task, "sentiment")
        self.assertEqual(result.bull_points, ["strong revenue beat"])
        self.assertEqual(result.bear_points, ["demand softness"])
        self.assertNotIn("guidance in-line", result.bull_points + result.bear_points)

    def test_normalizes_fingpt_sentiment_aliases(self) -> None:
        from core.schemas.fingpt import FinGPTAnnotation
        from pipelines.fingpt.risk_engine import FinGPTRiskEngine

        labels = ["bullish", "bearish", "LABEL_2", "LABEL_0", "mixed", "unknown"]

        class FakeAdapter:
            def label_texts(self, task, texts):
                return [
                    FinGPTAnnotation(article_id=f"inline-{index}", task=task, label=label)
                    for index, label in enumerate(labels)
                ]

        engine = FinGPTRiskEngine(FakeAdapter())  # type: ignore[arg-type]
        raw = {"risk_flags": [f"flag-{index}" for index in range(len(labels))]}

        result = asyncio.run(engine.evaluate_risk(raw))

        self.assertEqual(result.bull_points, ["flag-0", "flag-2"])
        self.assertEqual(result.bear_points, ["flag-1", "flag-3"])
        self.assertNotIn("flag-4", result.bull_points + result.bear_points)
        self.assertNotIn("flag-5", result.bull_points + result.bear_points)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
