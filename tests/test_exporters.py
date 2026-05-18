"""Smoke tests for the CSV / JSONL export adapters.

These exporters are *derived* artifacts, so the tests focus on:
- headers + row shape stability (downstream tooling pins to them),
- evidence-id linkage preservation between bull/bear points and exports,
- JSONL record-type coverage (retrieval + bull + bear + citations + header).
"""
from __future__ import annotations

import csv
import io
import json
import unittest

from pipelines.output.exporters import response_to_csv, response_to_jsonl


def _sample_response() -> dict:
    return {
        "ticker": "AAPL",
        "question": "What are the near-term risks?",
        "status": "success",
        "sentiment": "Neutral",
        "confidence": 0.72,
        "summary": "Apple faces mixed signals with strong services growth but hardware headwinds.",
        "conclusion": "Balanced setup.",
        "bull_points": ["Services segment margin expansion", "Buyback acceleration"],
        "bear_points": ["China demand softness"],
        "bull_evidence_ids": [["doc-svc-1"], ["doc-buyback-1", "doc-buyback-2"]],
        "bear_evidence_ids": [["doc-china-1"]],
        "citations": [
            {"source": "news", "title": "AAPL services margins", "date": "2026-04-10", "doc_id": "doc-svc-1"},
            {"source": "transcript", "title": "Q2 call", "date": "2026-04-15", "doc_id": "doc-buyback-1"},
        ],
        "raw_context": [
            {
                "document": "Services revenue accelerated...",
                "score": 0.91,
                "metadata": {"doc_id": "doc-svc-1", "title": "Services note", "source": "news", "published_at": "2026-04-10"},
            }
        ],
        "execution_meta": {"primary_model": "mistral:7b", "pipeline_latency_s": 42.1},
    }


class CsvExportTests(unittest.TestCase):
    def test_csv_contains_header_and_all_row_kinds(self) -> None:
        out = response_to_csv(_sample_response())
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        self.assertEqual(
            rows[0],
            [
                "ticker", "question", "status", "sentiment", "confidence",
                "kind", "index", "text", "evidence_doc_ids",
                "citation_source", "citation_title", "citation_date",
            ],
        )
        kinds = {r[5] for r in rows[1:]}
        self.assertIn("summary", kinds)
        self.assertIn("bull", kinds)
        self.assertIn("bear", kinds)
        self.assertIn("citation", kinds)
        self.assertIn("conclusion", kinds)

    def test_csv_preserves_bull_evidence_ids(self) -> None:
        out = response_to_csv(_sample_response())
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        bull_rows = [r for r in rows if r[5] == "bull"]
        self.assertEqual(len(bull_rows), 2)
        # Second bullet has two evidence ids joined with ", "
        self.assertIn("doc-buyback-1", bull_rows[1][8])
        self.assertIn("doc-buyback-2", bull_rows[1][8])


class JsonlExportTests(unittest.TestCase):
    def test_jsonl_emits_one_record_per_concept(self) -> None:
        out = response_to_jsonl(_sample_response(), include_raw_context=True)
        records = [json.loads(line) for line in out.strip().splitlines()]
        types = [r["record_type"] for r in records]
        self.assertEqual(types[0], "run_header")
        self.assertIn("retrieval", types)
        self.assertEqual(sum(1 for t in types if t == "bull_point"), 2)
        self.assertEqual(sum(1 for t in types if t == "bear_point"), 1)
        self.assertEqual(sum(1 for t in types if t == "citation"), 2)

    def test_jsonl_bull_point_carries_evidence_ids(self) -> None:
        out = response_to_jsonl(_sample_response())
        records = [json.loads(line) for line in out.strip().splitlines()]
        bulls = [r for r in records if r["record_type"] == "bull_point"]
        self.assertEqual(bulls[0]["evidence_doc_ids"], ["doc-svc-1"])
        self.assertEqual(bulls[1]["evidence_doc_ids"], ["doc-buyback-1", "doc-buyback-2"])

    def test_jsonl_lean_mode_skips_raw_context(self) -> None:
        out = response_to_jsonl(_sample_response(), include_raw_context=False)
        records = [json.loads(line) for line in out.strip().splitlines()]
        self.assertFalse(any(r["record_type"] == "retrieval" for r in records))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
