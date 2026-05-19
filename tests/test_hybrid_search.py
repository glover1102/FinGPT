import unittest
from unittest.mock import Mock, patch

from core.config.settings import Settings
from core.utils import qdrant_helpers


class HybridSearchTests(unittest.TestCase):
    def setUp(self):
        qdrant_helpers._SPARSE_COLLECTION_CACHE.clear()

    def test_get_client_sets_sparse_model_when_enabled(self):
        client = Mock()

        with patch.object(qdrant_helpers, "load_settings", return_value=Settings(hybrid_search_enabled=True, sparse_model="Qdrant/bm25")), \
             patch("qdrant_client.QdrantClient", return_value=client):
            qdrant_helpers.get_qdrant_client("http://localhost:6333", "", enable_embeddings=True)

        client.set_model.assert_called_once()
        client.set_sparse_model.assert_called_once_with("Qdrant/bm25")

    def test_get_client_can_disable_sparse_model_for_legacy_collection(self):
        client = Mock()

        with patch.object(qdrant_helpers, "load_settings", return_value=Settings(hybrid_search_enabled=True, sparse_model="Qdrant/bm25")), \
             patch("qdrant_client.QdrantClient", return_value=client):
            qdrant_helpers.get_qdrant_client(
                "http://localhost:6333",
                "",
                enable_embeddings=True,
                enable_sparse=False,
            )

        client.set_model.assert_called_once()
        client.set_sparse_model.assert_not_called()

    def test_ensure_collection_includes_sparse_vectors_when_enabled(self):
        client = Mock()
        client.collection_exists.return_value = False
        vector_params = {"dense": object()}
        sparse_params = {"bm25": object()}
        client.get_fastembed_vector_params.return_value = vector_params
        client.get_fastembed_sparse_vector_params.return_value = sparse_params

        with patch.object(qdrant_helpers, "load_settings", return_value=Settings(hybrid_search_enabled=True)):
            qdrant_helpers.ensure_collection(client, "market_docs")

        client.create_collection.assert_called_once_with(
            collection_name="market_docs",
            vectors_config=vector_params,
            sparse_vectors_config=sparse_params,
        )

    def test_search_documents_allows_topic_query_without_ticker_filter(self):
        client = Mock()
        hit = Mock()
        hit.metadata = {"doc_id": "d1"}
        hit.document = "oil backwardation context"
        hit.score = 0.9
        client.query.return_value = [hit]

        hits = qdrant_helpers.search_documents(
            client,
            "market_docs",
            symbol=None,
            query_text="oil backwardation",
            limit=5,
        )

        self.assertEqual(hits[0]["metadata"]["doc_id"], "d1")
        self.assertIsNone(client.query.call_args.kwargs["query_filter"])

    def test_search_documents_retries_dense_only_on_sparse_collection_mismatch(self):
        hybrid_client = Mock()
        hybrid_client.query.side_effect = RuntimeError("sparse vector fast-sparse-bm25 does not exist")

        dense_client = Mock()
        hit = Mock()
        hit.metadata = {"doc_id": "d1"}
        hit.document = "dense result"
        hit.score = 0.7
        dense_client.query.return_value = [hit]

        with patch.object(qdrant_helpers, "_dense_only_client", return_value=dense_client):
            hits = qdrant_helpers.search_documents(
                hybrid_client,
                "market_docs",
                symbol="QQQ",
                query_text="macro",
                limit=3,
            )

        self.assertEqual(hits[0]["document"], "dense result")
        hybrid_client.query.assert_called_once()
        dense_client.query.assert_called_once()

    def test_add_documents_retries_dense_only_on_legacy_dense_collection(self):
        hybrid_client = Mock()
        hybrid_client.add.side_effect = RuntimeError("argument of type 'NoneType' is not iterable")

        dense_client = Mock()
        dense_client.add.return_value = ["point-1"]

        with patch.object(qdrant_helpers, "_dense_only_client", return_value=dense_client):
            inserted = qdrant_helpers.add_documents_to_qdrant(
                hybrid_client,
                "market_docs",
                documents=["QQQ context"],
                metadata=[{"doc_id": "qqq-doc-1", "ticker": "QQQ"}],
            )

        self.assertEqual(inserted, ["point-1"])
        hybrid_client.add.assert_called_once()
        dense_client.add.assert_called_once()


if __name__ == "__main__":
    unittest.main()
