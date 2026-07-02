from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime, timedelta

import structlog

from .fingpt_loader import FinGPTModel
from .news_fetcher import NewsFetcher

log = structlog.get_logger()


class SentimentAnalyzer:
    def __init__(
        self,
        fingpt_model: FinGPTModel,
        news_fetcher: NewsFetcher,
        cache_ttl_seconds: int = 3600,
        max_cache_size: int = 1000,
    ):
        self.model = fingpt_model
        self.news_fetcher = news_fetcher
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_cache_size = max_cache_size
        self.cache: OrderedDict[str, tuple[datetime, dict]] = OrderedDict()

    def analyze_text(self, text: str, ticker: str | None = None) -> dict:
        log.info("analyzing_sentiment", ticker=ticker, text_length=len(text))
        raw_output = self.model.generate_sentiment(text)
        sentiment_label = self._parse_sentiment_label(raw_output)
        sentiment_score = self._label_to_score(sentiment_label)
        confidence = self._estimate_confidence(raw_output, sentiment_label)
        return {
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "confidence": confidence,
            "raw_output": raw_output,
            "analyzed_text": text[:200] + "..." if len(text) > 200 else text,
            "timestamp": datetime.now(UTC),
        }

    def analyze_ticker(self, ticker: str, days: int = 7, max_articles: int = 20) -> dict:
        cache_key = f"{ticker.upper()}:{days}:{max_articles}"
        cached_result = self._get_cached(cache_key)
        if cached_result is not None:
            log.info("sentiment_cache_hit", ticker=ticker)
            return cached_result

        log.info("analyzing_ticker_sentiment", ticker=ticker, days=days, max_articles=max_articles)
        articles = self.news_fetcher.fetch_news(ticker, days=days, limit=max_articles)
        if not articles:
            return {
                "ticker": ticker.upper(),
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "confidence": 0.0,
                "news_count": 0,
                "articles_analyzed": [],
                "timestamp": datetime.now(UTC),
            }

        sentiments = []
        confidences = []
        headlines = []
        for article in articles:
            headline = (article.get("headline") or "").strip()
            if not headline:
                continue
            result = self.analyze_text(headline, ticker=ticker.upper())
            sentiments.append(result["sentiment_score"])
            confidences.append(result["confidence"])
            headlines.append(headline)

        if not sentiments:
            return {
                "ticker": ticker.upper(),
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "confidence": 0.0,
                "news_count": len(articles),
                "articles_analyzed": [],
                "timestamp": datetime.now(UTC),
            }

        avg_sentiment = sum(sentiments) / len(sentiments)
        avg_confidence = sum(confidences) / len(confidences)
        result = {
            "ticker": ticker.upper(),
            "sentiment_score": round(avg_sentiment, 3),
            "sentiment_label": self._score_to_label(avg_sentiment),
            "confidence": round(avg_confidence, 3),
            "news_count": len(headlines),
            "articles_analyzed": headlines[:5],
            "timestamp": datetime.now(UTC),
        }
        self._set_cached(cache_key, result)
        return result

    def _get_cached(self, cache_key: str) -> dict | None:
        cached = self.cache.get(cache_key)
        if not cached:
            return None
        cached_at, cached_result = cached
        if datetime.now(UTC) - cached_at > timedelta(seconds=self.cache_ttl_seconds):
            self.cache.pop(cache_key, None)
            return None
        self.cache.move_to_end(cache_key)
        return cached_result

    def _set_cached(self, cache_key: str, value: dict) -> None:
        self.cache[cache_key] = (datetime.now(UTC), value)
        self.cache.move_to_end(cache_key)
        while len(self.cache) > self.max_cache_size:
            self.cache.popitem(last=False)

    def _parse_sentiment_label(self, raw_output: str) -> str:
        output_lower = raw_output.lower().strip()
        if "negative" in output_lower:
            return "negative"
        if "positive" in output_lower:
            return "positive"
        return "neutral"

    def _label_to_score(self, label: str) -> float:
        return {
            "positive": 0.75,
            "neutral": 0.0,
            "negative": -0.75,
        }.get(label, 0.0)

    def _score_to_label(self, score: float) -> str:
        if score > 0.3:
            return "positive"
        if score < -0.3:
            return "negative"
        return "neutral"

    def _estimate_confidence(self, raw_output: str, sentiment_label: str) -> float:
        normalized = raw_output.strip().lower()
        if normalized == sentiment_label:
            return 0.9
        if sentiment_label in normalized:
            return 0.8
        return 0.65

