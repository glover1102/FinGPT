"""Tests for the Quality / Evaluation dashboard aggregator.

Uses tempdir fixtures rather than the real project to isolate against
changes in the committed reports.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.utils.eval_dashboard import load_eval_dashboard


class EvalDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_results(self, cases: list[dict]) -> None:
        (self.root / "quality_review_results.json").write_text(
            json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_report(self, md: str) -> None:
        (self.root / "reports" / "latest_eval_report.md").write_text(md, encoding="utf-8")

    def test_reports_absence_is_tolerated(self) -> None:
        data = load_eval_dashboard(self.root)
        self.assertFalse(data["has_report"])
        self.assertFalse(data["has_results"])
        self.assertEqual(data["summary"]["total"], 0)
        self.assertEqual(data["cases"], [])

    def test_summary_aggregates_status_and_averages(self) -> None:
        self._write_results([
            {"category": "A", "ticker": "AAPL", "status": "success", "confidence": 0.9,
             "purity_ratio": 1.0, "elapsed_s": 10.0},
            {"category": "A", "ticker": "AAPL", "status": "partial", "confidence": 0.4,
             "purity_ratio": 0.8, "elapsed_s": 12.0},
            {"category": "B", "ticker": "MSFT", "status": "failed", "confidence": 0.0,
             "purity_ratio": 0.0, "elapsed_s": 8.0, "error": "boom"},
        ])
        data = load_eval_dashboard(self.root)
        self.assertTrue(data["has_results"])
        summary = data["summary"]
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["status_counts"], {"success": 1, "partial": 1, "failed": 1})
        self.assertAlmostEqual(summary["avg_confidence"], 0.433, places=2)
        categories = {c["category"]: c for c in summary["categories"]}
        self.assertEqual(categories["A"]["count"], 2)
        self.assertEqual(categories["A"]["pass"], 1)
        self.assertEqual(categories["A"]["partial"], 1)
        self.assertEqual(categories["B"]["failed"], 1)

    def test_report_markdown_is_exposed(self) -> None:
        self._write_report("# eval\nthe markdown body")
        data = load_eval_dashboard(self.root)
        self.assertTrue(data["has_report"])
        self.assertIn("eval", data["report_markdown"])

    def test_trimmed_cases_preserve_key_fields(self) -> None:
        self._write_results([
            {
                "suite": "analysis",
                "category": "A",
                "ticker": "AAPL",
                "mode": "single_ticker",
                "status": "success",
                "desc": "desc",
                "question": "q",
                "summary": "s",
                "confidence": 0.5,
                "context_chunks": 3,
                "purity_ratio": 1.0,
                "citation_count": 2,
                "evidence_count": 3,
                "language_ok": True,
                "decision_richness": {"ok": True},
                "gate_pass": True,
                "raw_context": [{"huge": "payload"}],
            }
        ])
        data = load_eval_dashboard(self.root)
        case = data["cases"][0]
        self.assertEqual(case["suite"], "analysis")
        self.assertEqual(case["ticker"], "AAPL")
        self.assertNotIn("raw_context", case)
        self.assertEqual(case["context_chunks"], 3)
        self.assertEqual(case["citation_count"], 2)
        self.assertTrue(case["language_ok"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
