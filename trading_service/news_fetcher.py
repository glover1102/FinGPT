from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

log = structlog.get_logger()


class NewsFetcher:
    def __init__(self, finnhub_api_key: str):
        self._finnhub_api_key = finnhub_api_key
        self.client = self._build_finnhub_client(finnhub_api_key)

    def fetch_news(self, ticker: str, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
        ticker = ticker.upper().strip()
        if not ticker:
            return []

        days = max(1, days)
        limit = max(1, limit)

        articles = self._fetch_finnhub_news(ticker, days=days, limit=limit)
        if articles:
            return articles
        return self._fetch_yfinance_news(ticker, limit=limit)

    def _build_finnhub_client(self, finnhub_api_key: str):
        if not finnhub_api_key:
            return None
        try:
            import finnhub
        except ImportError:
            log.warning("finnhub_dependency_missing")
            return None
        return finnhub.Client(api_key=finnhub_api_key)

    def _fetch_finnhub_news(self, ticker: str, days: int, limit: int) -> list[dict[str, Any]]:
        if not self.client:
            log.warning("finnhub_client_not_configured")
            return []

        try:
            now = datetime.now(UTC)
            from_date = (now - timedelta(days=days)).date().isoformat()
            to_date = now.date().isoformat()
            log.info("fetching_finnhub_news", ticker=ticker, from_date=from_date, to_date=to_date)
            news = self.client.company_news(ticker, _from=from_date, to=to_date)
            articles = [item for item in news if item.get("headline")][:limit]
            log.info("finnhub_news_fetched", ticker=ticker, count=len(articles))
            return articles
        except Exception as exc:
            log.error("finnhub_news_fetch_failed", ticker=ticker, error=str(exc))
            return []

    def _fetch_yfinance_news(self, ticker: str, limit: int) -> list[dict[str, Any]]:
        try:
            import yfinance as yf
        except ImportError:
            log.warning("yfinance_dependency_missing")
            return []

        try:
            log.info("fetching_yfinance_news", ticker=ticker)
            raw_items = getattr(yf.Ticker(ticker), "news", []) or []
            articles = []
            for item in raw_items[:limit]:
                content = item.get("content") or {}
                headline = (
                    item.get("title")
                    or content.get("title")
                    or content.get("summary")
                    or ""
                )
                if not headline:
                    continue
                articles.append(
                    {
                        "headline": headline,
                        "summary": content.get("summary") or item.get("summary", ""),
                        "url": item.get("link") or content.get("canonicalUrl", {}).get("url", ""),
                        "datetime": item.get("providerPublishTime") or content.get("pubDate"),
                    }
                )
            log.info("yfinance_news_fetched", ticker=ticker, count=len(articles))
            return articles
        except Exception as exc:
            log.error("yfinance_news_fetch_failed", ticker=ticker, error=str(exc))
            return []

