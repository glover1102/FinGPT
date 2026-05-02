import time
import unittest

from pipelines.collect.cache import CollectionCache
from pipelines.collect.models import CollectionOutcome


def _outcome(docs=1) -> CollectionOutcome:
    return CollectionOutcome(
        documents=[{"doc_id": f"doc-{i}"} for i in range(docs)],
        current_doc_ids=[f"doc-{i}" for i in range(docs)],
        run_started_at="2026-04-22T00:00:00",
        freshness_cutoff="2026-04-21T00:00:00",
    )


class CollectionCacheTests(unittest.TestCase):
    def test_hit_returns_cached_outcome_with_metadata(self):
        cache = CollectionCache(ttl_s=60, max_entries=4)
        key = cache.make_key("AAPL", ["news"], 30)
        cache.put(key, _outcome())

        hit = cache.get(key)
        self.assertIsNotNone(hit)
        self.assertTrue(hit.cache_hit)
        self.assertGreaterEqual(hit.cache_age_s, 0.0)
        self.assertTrue(hit.cached_at.endswith("Z"))

    def test_miss_after_ttl_expiry(self):
        cache = CollectionCache(ttl_s=1, max_entries=4)
        key = cache.make_key("AAPL", ["news"], 30)
        cache.put(key, _outcome())
        time.sleep(1.2)
        self.assertIsNone(cache.get(key))

    def test_disabled_cache_never_stores(self):
        cache = CollectionCache(ttl_s=0, max_entries=4)
        key = cache.make_key("AAPL", ["news"], 30)
        cache.put(key, _outcome())
        self.assertIsNone(cache.get(key))
        self.assertFalse(cache.enabled)

    def test_does_not_cache_empty_outcomes(self):
        cache = CollectionCache(ttl_s=60, max_entries=4)
        key = cache.make_key("AAPL", ["news"], 30)
        cache.put(key, CollectionOutcome())
        self.assertIsNone(cache.get(key))

    def test_key_is_source_order_insensitive(self):
        cache = CollectionCache(ttl_s=60, max_entries=4)
        k1 = cache.make_key("aapl", ["news", "transcript"], 30)
        k2 = cache.make_key("AAPL", ["transcript", "news"], 30)
        self.assertEqual(k1, k2)

    def test_lru_eviction(self):
        cache = CollectionCache(ttl_s=60, max_entries=2)
        k1 = cache.make_key("AAPL", ["news"], 30)
        k2 = cache.make_key("MSFT", ["news"], 30)
        k3 = cache.make_key("NVDA", ["news"], 30)
        cache.put(k1, _outcome())
        cache.put(k2, _outcome())
        cache.put(k3, _outcome())
        self.assertIsNone(cache.get(k1))
        self.assertIsNotNone(cache.get(k2))
        self.assertIsNotNone(cache.get(k3))

    def test_invalidate_by_ticker(self):
        cache = CollectionCache(ttl_s=60, max_entries=4)
        cache.put(cache.make_key("AAPL", ["news"], 30), _outcome())
        cache.put(cache.make_key("AAPL", ["news"], 60), _outcome())
        cache.put(cache.make_key("MSFT", ["news"], 30), _outcome())
        dropped = cache.invalidate("aapl")
        self.assertEqual(dropped, 2)
        self.assertIsNone(cache.get(cache.make_key("AAPL", ["news"], 30)))
        self.assertIsNotNone(cache.get(cache.make_key("MSFT", ["news"], 30)))


if __name__ == "__main__":
    unittest.main()
