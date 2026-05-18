import unittest
from unittest.mock import patch

from pipelines.retrieve import reranker


class FakeReranker:
    def predict(self, pairs):
        scores = []
        for _, text in pairs:
            lower = text.lower()
            score = 0.0
            if "iphone" in lower:
                score += 3.0
            if "revenue" in lower:
                score += 2.0
            if "weather" in lower:
                score -= 2.0
            scores.append(score)
        return scores


class RerankerTests(unittest.TestCase):
    def test_rerank_moves_irrelevant_chunk_back(self):
        candidates = [
            {"document": "Regional weather remains mild.", "metadata": {"doc_id": "d1"}},
            {"document": "Apple iPhone revenue accelerated in services.", "metadata": {"doc_id": "d2"}},
            {"document": "AAPL supply-chain demand improved.", "metadata": {"doc_id": "d3"}},
            {"document": "iPhone replacement cycle supports revenue.", "metadata": {"doc_id": "d4"}},
        ]

        with patch.object(reranker, "get_reranker", return_value=FakeReranker()):
            ranked = reranker.rerank("Apple iPhone revenue outlook", candidates, top_k=3)

        self.assertEqual(ranked[0]["metadata"]["doc_id"], "d2")
        self.assertEqual(ranked[1]["metadata"]["doc_id"], "d4")
        self.assertNotIn("d1", [item["metadata"]["doc_id"] for item in ranked[:2]])

    def test_small_candidate_pool_keeps_original_order(self):
        candidates = [
            {"document": "first", "metadata": {"doc_id": "d1"}},
            {"document": "second", "metadata": {"doc_id": "d2"}},
            {"document": "third", "metadata": {"doc_id": "d3"}},
        ]

        with patch.object(reranker, "get_reranker", side_effect=AssertionError("should not load model")):
            ranked = reranker.rerank("query", candidates, top_k=3)

        self.assertEqual(ranked, candidates)

    def test_model_load_failure_fails_open(self):
        candidates = [
            {"document": "first", "metadata": {"doc_id": "d1"}},
            {"document": "second", "metadata": {"doc_id": "d2"}},
            {"document": "third", "metadata": {"doc_id": "d3"}},
            {"document": "fourth", "metadata": {"doc_id": "d4"}},
        ]

        with patch.object(reranker, "get_reranker", side_effect=RuntimeError("boom")):
            ranked = reranker.rerank("query", candidates, top_k=2)

        self.assertEqual(ranked, candidates[:2])


if __name__ == "__main__":
    unittest.main()
