import importlib.util
import sys
import unittest
from pathlib import Path


QUANT_STACK_DIR = Path(__file__).resolve().parents[2] / "archive" / "quant_stack"
if str(QUANT_STACK_DIR) not in sys.path:
    sys.path.insert(0, str(QUANT_STACK_DIR))

from core.utils.qdrant_helpers import (
    add_documents_to_qdrant,
    doc_id_to_point_id,
    get_qdrant_client,
    search_documents,
)


class QuantStackSmokeTests(unittest.TestCase):
    def test_doc_id_to_point_id_is_deterministic(self):
        first = doc_id_to_point_id("aapl_news_123")
        second = doc_id_to_point_id("aapl_news_123")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 36)

    @unittest.skipUnless(
        importlib.util.find_spec("qdrant_client") is not None,
        "qdrant-client is not installed in the active environment",
    )
    def test_in_memory_qdrant_roundtrip(self):
        client = get_qdrant_client(location=":memory:")
        documents = [
            "Apple launched a new chip and guided for stronger demand next quarter.",
            "Supply chain constraints may pressure margins in the short term.",
        ]
        metadata = [
            {
                "doc_id": "doc-1",
                "symbol": "AAPL",
                "doc_type": "news",
                "source": "unit-test",
                "published_at": "2026-04-10T00:00:00",
                "title": "Demand improving",
                "url": "https://example.com/1",
            },
            {
                "doc_id": "doc-2",
                "symbol": "AAPL",
                "doc_type": "news",
                "source": "unit-test",
                "published_at": "2026-04-11T00:00:00",
                "title": "Margin risk",
                "url": "https://example.com/2",
            },
        ]

        inserted_ids = add_documents_to_qdrant(
            client=client,
            collection_name="market_docs",
            documents=documents,
            metadata=metadata,
            batch_size=8,
        )

        hits = search_documents(
            client=client,
            collection_name="market_docs",
            symbol="AAPL",
            query_text="What are the short-term risks for Apple?",
            limit=5,
        )

        self.assertEqual(len(inserted_ids), 2)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["metadata"]["symbol"], "AAPL")
        self.assertTrue(hits[0]["document"])


if __name__ == "__main__":
    unittest.main()
