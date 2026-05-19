import unittest
from unittest.mock import Mock, patch

from core.config.settings import Settings
from pipelines.ingest import qdrant_ingestor


def _doc():
    return {
        "doc_id": "aapl_news_1",
        "ticker": "AAPL",
        "symbol": "AAPL",
        "doc_type": "news",
        "source": "Reuters",
        "published_at": "2026-04-20",
        "title": "Apple update",
        "text": " ".join(f"Apple revenue growth sentence {i}." for i in range(220)),
        "url": "https://example.com",
        "admitted_by": "ticker_match",
    }


class QdrantIngestorChunkedTests(unittest.TestCase):
    def test_ingest_expands_one_doc_to_indexed_chunks_with_parent_payload(self):
        settings = Settings(ingest_chunking_enabled=True, ingest_chunk_tokens=80, ingest_chunk_overlap=8)
        client = Mock()

        captured = {}

        def fake_add(client, collection_name, documents, metadata, batch_size=16):
            captured["documents"] = documents
            captured["metadata"] = metadata
            return [item["doc_id"] for item in metadata]

        with patch.object(qdrant_ingestor, "load_settings", return_value=settings), \
             patch("core.utils.qdrant_helpers.get_qdrant_client", return_value=client), \
             patch("core.utils.qdrant_helpers.ensure_collection"), \
             patch("core.utils.qdrant_helpers.add_documents_to_qdrant", side_effect=fake_add):
            inserted = qdrant_ingestor.ingest_documents([_doc()])

        metadata = captured["metadata"]
        self.assertGreater(len(metadata), 1)
        self.assertEqual(inserted, [item["doc_id"] for item in metadata])
        self.assertEqual([item["chunk_index"] for item in metadata], list(range(len(metadata))))
        self.assertTrue(all(item["parent_doc_id"] == "aapl_news_1" for item in metadata))
        self.assertTrue(all(item["total_chunks"] == len(metadata) for item in metadata))
        self.assertTrue(all(str(item["doc_id"]).startswith("aapl_news_1__c") for item in metadata))

    def test_chunking_disabled_keeps_parent_doc_id_as_doc_id(self):
        settings = Settings(ingest_chunking_enabled=False)
        client = Mock()
        captured = {}

        def fake_add(client, collection_name, documents, metadata, batch_size=16):
            captured["metadata"] = metadata
            return [item["doc_id"] for item in metadata]

        with patch.object(qdrant_ingestor, "load_settings", return_value=settings), \
             patch("core.utils.qdrant_helpers.get_qdrant_client", return_value=client), \
             patch("core.utils.qdrant_helpers.ensure_collection"), \
             patch("core.utils.qdrant_helpers.add_documents_to_qdrant", side_effect=fake_add):
            qdrant_ingestor.ingest_documents([_doc()], chunking_enabled=False)

        self.assertEqual(captured["metadata"][0]["doc_id"], "aapl_news_1")
        self.assertEqual(captured["metadata"][0]["parent_doc_id"], "aapl_news_1")

    def test_legacy_dense_collection_uses_dense_only_add_client(self):
        settings = Settings(ingest_chunking_enabled=False, hybrid_search_enabled=True)
        hybrid_client = Mock(name="hybrid_client")
        dense_client = Mock(name="dense_client")
        captured = {}

        def fake_add(client, collection_name, documents, metadata, batch_size=16):
            captured["client"] = client
            return [item["doc_id"] for item in metadata]

        with patch.object(qdrant_ingestor, "load_settings", return_value=settings), \
             patch("core.utils.qdrant_helpers.get_qdrant_client", side_effect=[hybrid_client, dense_client]), \
             patch("core.utils.qdrant_helpers.ensure_collection"), \
             patch("core.utils.qdrant_helpers.collection_has_sparse_vectors", return_value=False), \
             patch("core.utils.qdrant_helpers.add_documents_to_qdrant", side_effect=fake_add):
            qdrant_ingestor.ingest_documents([_doc()], chunking_enabled=False)

        self.assertIs(captured["client"], dense_client)

    def test_incremental_ingest_skips_existing_parent_docs(self):
        settings = Settings(ingest_chunking_enabled=False)
        client = Mock()

        with patch.object(qdrant_ingestor, "load_settings", return_value=settings), \
             patch("core.utils.qdrant_helpers.get_qdrant_client", return_value=client), \
             patch("core.utils.qdrant_helpers.ensure_collection"), \
             patch("core.utils.qdrant_helpers.existing_parent_doc_ids", return_value={"aapl_news_1"}), \
             patch("core.utils.qdrant_helpers.add_documents_to_qdrant") as add_docs:
            stats = qdrant_ingestor.ingest_documents(
                [_doc()],
                chunking_enabled=False,
                skip_existing_parent_docs=True,
                return_stats=True,
            )

        add_docs.assert_not_called()
        self.assertEqual(stats["inserted_docs"], 0)
        self.assertEqual(stats["skipped_docs"], 1)
        self.assertEqual(stats["skipped_parent_doc_ids"], ["aapl_news_1"])


if __name__ == "__main__":
    unittest.main()
