import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.config.settings import Settings
from core.utils import qdrant_helpers
from core.utils.qdrant_helpers import ensure_collection


class QdrantHelperTests(unittest.TestCase):
    def setUp(self):
        qdrant_helpers._SPARSE_COLLECTION_CACHE.clear()

    def test_ensure_collection_uses_fastembed_vector_params_when_available(self):
        client = Mock()
        client.collection_exists.return_value = False
        vector_params = {"fast-bge-small-en-v1.5": object()}
        client.get_fastembed_vector_params.return_value = vector_params

        with patch("core.utils.qdrant_helpers.load_settings", return_value=Settings(hybrid_search_enabled=False)):
            ensure_collection(client, "market_docs")

        client.create_collection.assert_called_once_with(
            collection_name="market_docs",
            vectors_config=vector_params,
        )

    def test_ensure_collection_auto_migrates_existing_dense_collection(self):
        client = Mock()
        client.collection_exists.return_value = True
        client.get_collection.return_value = SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(sparse_vectors=None))
        )
        sparse_params = {"fast-sparse-bm25": object()}
        client.get_fastembed_sparse_vector_params.return_value = sparse_params
        client.update_collection.return_value = True

        with patch("core.utils.qdrant_helpers.load_settings", return_value=Settings(hybrid_search_enabled=True)):
            ensure_collection(client, "market_docs")

        client.update_collection.assert_called_once_with(
            collection_name="market_docs",
            sparse_vectors_config=sparse_params,
        )
        self.assertTrue(qdrant_helpers.collection_has_sparse_vectors(client, "market_docs"))

    def test_ensure_sparse_vectors_respects_auto_migrate_flag(self):
        client = Mock()
        client.get_collection.return_value = SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(sparse_vectors=None))
        )

        migrated = qdrant_helpers.ensure_sparse_vectors(
            client,
            "market_docs",
            settings=Settings(hybrid_search_enabled=True, hybrid_search_auto_migrate_sparse=False),
        )

        self.assertFalse(migrated)
        client.update_collection.assert_not_called()

    def test_loopback_qdrant_api_key_warning_is_suppressed(self):
        import warnings

        def _warn_and_return(**_kwargs):
            warnings.warn("Api key is used with unsecure connection.", UserWarning)
            return SimpleNamespace()

        with patch("qdrant_client.QdrantClient", side_effect=_warn_and_return):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                qdrant_helpers._new_qdrant_client(
                    qdrant_url="http://127.0.0.1:6333",
                    api_key="local-dev-key",
                )

        self.assertEqual([], caught)


if __name__ == "__main__":
    unittest.main()
