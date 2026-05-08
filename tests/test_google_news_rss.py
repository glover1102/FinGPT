"""Tests for the Google News RSS provider.

Verifies:
- RSS parsing produces the same normalized document shape other providers use.
- Freshness filter is applied (stale items are dropped).
- Network failures and empty feeds return ``failed``/``empty`` rather than
  raising.
- The provider can be prioritized before SEC by provider policy when the
  earlier providers did not clear the freshness threshold.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


def _rss_sample(num_items: int = 3, pub: str | None = None) -> str:
    pub = pub or (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    items = []
    for i in range(num_items):
        items.append(
            f"""
            <item>
              <title>AAPL sample headline {i}</title>
              <link>https://example.com/aapl/{i}</link>
              <pubDate>{pub}</pubDate>
              <description>&lt;p&gt;Details about AAPL item {i}&lt;/p&gt;</description>
              <source url=\"https://www.example.com\">Example Wire</source>
            </item>
            """
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>{''.join(items)}</channel></rss>"""


def _broad_rss_sample(pub: str | None = None) -> str:
    pub = pub or (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Gold rises as real yields fall</title>
    <link>https://example.com/gold/1</link>
    <pubDate>{pub}</pubDate>
    <description>&lt;p&gt;Macro drivers lifted bullion prices across futures markets.&lt;/p&gt;</description>
    <source url=\"https://www.example.com\">Example Wire</source>
  </item>
</channel></rss>"""


class GoogleNewsRssProviderTests(unittest.TestCase):
    def test_etf_query_uses_fund_identity_terms(self) -> None:
        from pipelines.collect.google_news_rss import _build_query

        query = _build_query("QQQ", lookback_days=14)

        self.assertIn('"Invesco QQQ"', query)
        self.assertIn('"QQQ ETF"', query)
        self.assertNotIn("QQQ stock OR earnings", query)

    def test_parses_feed_into_normalized_documents(self) -> None:
        from pipelines.collect import google_news_rss

        mock_resp = MagicMock(status_code=200, text=_rss_sample(num_items=3))
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = mock_resp
        with patch.object(google_news_rss.httpx, "Client", return_value=client):
            result, docs = google_news_rss.collect_news_from_google_rss("AAPL", lookback_days=14)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.doc_count, 3)
        self.assertEqual(len(docs), 3)
        self.assertTrue(all(d.get("doc_id") for d in docs))
        self.assertTrue(all(d.get("text") or d.get("title") for d in docs))

    def test_filters_stale_items(self) -> None:
        from pipelines.collect import google_news_rss

        old = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        mock_resp = MagicMock(status_code=200, text=_rss_sample(num_items=2, pub=old))
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = mock_resp
        with patch.object(google_news_rss.httpx, "Client", return_value=client):
            result, docs = google_news_rss.collect_news_from_google_rss("AAPL", lookback_days=14)
        self.assertEqual(docs, [])
        self.assertIn(result.status, {"empty"})

    def test_query_override_can_relax_ticker_purity_for_dashboard_categories(self) -> None:
        from pipelines.collect import google_news_rss

        mock_resp = MagicMock(status_code=200, text=_broad_rss_sample())
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = mock_resp
        with patch.object(google_news_rss.httpx, "Client", return_value=client):
            result, docs = google_news_rss.collect_news_from_google_rss(
                "GLD",
                lookback_days=14,
                query_override='"gold price" OR "real yields gold"',
                strict_purity=False,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["symbol"], "GLD")
        self.assertEqual(docs[0]["admitted_by"], "dashboard_query_override")

    def test_network_error_returns_failed(self) -> None:
        from pipelines.collect import google_news_rss

        client = MagicMock()
        client.__enter__.return_value = client
        client.get.side_effect = RuntimeError("boom")
        with patch.object(google_news_rss.httpx, "Client", return_value=client):
            result, docs = google_news_rss.collect_news_from_google_rss("AAPL", lookback_days=7)
        self.assertEqual(result.status, "failed")
        self.assertEqual(docs, [])

    def test_http_non_200_returns_failed(self) -> None:
        from pipelines.collect import google_news_rss

        mock_resp = MagicMock(status_code=503, text="<html>Service Unavailable</html>")
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = mock_resp
        with patch.object(google_news_rss.httpx, "Client", return_value=client):
            result, docs = google_news_rss.collect_news_from_google_rss("AAPL", lookback_days=7)
        self.assertEqual(result.status, "failed")
        self.assertEqual(docs, [])


class NewsFallbackChainWiringTests(unittest.TestCase):
    """Light integration check: provider policy can prioritize Google before SEC."""

    def test_google_rss_runs_before_sec(self) -> None:
        from pipelines.collect import openbb_collector

        yf_result = MagicMock(status="empty", elapsed_s=0.1)
        google_result = MagicMock(status="ok", elapsed_s=0.2)
        sec_result = MagicMock(status="empty", elapsed_s=0.1)

        def _fake_google(ticker, lookback_days, limit=20):
            return google_result, [
                {"doc_id": "g1", "text": "body", "title": "t", "ticker": ticker, "symbol": ticker,
                 "source": "google_news", "published_at": datetime.now(timezone.utc).isoformat(),
                 "url": "https://example.com/g1", "doc_type": "news", "collected_at": datetime.now(timezone.utc).isoformat()},
                {"doc_id": "g2", "text": "body2", "title": "t2", "ticker": ticker, "symbol": ticker,
                 "source": "google_news", "published_at": datetime.now(timezone.utc).isoformat(),
                 "url": "https://example.com/g2", "doc_type": "news", "collected_at": datetime.now(timezone.utc).isoformat()},
                {"doc_id": "g3", "text": "body3", "title": "t3", "ticker": ticker, "symbol": ticker,
                 "source": "google_news", "published_at": datetime.now(timezone.utc).isoformat(),
                 "url": "https://example.com/g3", "doc_type": "news", "collected_at": datetime.now(timezone.utc).isoformat()},
            ]

        sec_called = {"count": 0}

        def _fake_sec(ticker, lookback_days, user_agent, limit=5):
            sec_called["count"] += 1
            return sec_result, []

        with patch.object(openbb_collector, "_collect_yfinance_news_source", return_value=(yf_result, [])), \
             patch.object(openbb_collector, "collect_news_from_google_rss", side_effect=_fake_google) as google_mock, \
             patch.object(openbb_collector, "collect_sec_filings_as_news", side_effect=_fake_sec):
            from core.config.settings import Settings

            result, docs, providers = openbb_collector._collect_news_source(
                "AAPL",
                14,
                settings=Settings(data_provider_priority="yfinance,google,sec,fmp"),
            )
        # Google RSS should have been invoked, and since it returned 3 docs
        # (above fallback threshold) SEC should *not* have been called.
        self.assertTrue(google_mock.called)
        self.assertEqual(sec_called["count"], 0)
        provider_names = [p.source for p in providers]
        self.assertIn("news:google_news_rss", provider_names)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
