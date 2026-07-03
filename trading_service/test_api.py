from datetime import UTC, datetime

from fastapi.testclient import TestClient

from trading_service.main import app, get_sentiment_analyzer


class StubSentimentAnalyzer:
    def analyze_text(self, text: str, ticker: str | None = None) -> dict:
        return {
            "sentiment_score": 0.75,
            "sentiment_label": "positive",
            "confidence": 0.91,
            "analyzed_text": text,
            "timestamp": datetime.now(UTC),
        }

    def analyze_ticker(self, ticker: str, days: int = 7, max_articles: int = 20) -> dict:
        return {
            "ticker": ticker.upper(),
            "sentiment_score": 0.3,
            "sentiment_label": "positive",
            "confidence": 0.82,
            "news_count": min(max_articles, 2),
            "articles_analyzed": [
                f"{ticker.upper()} beats earnings expectations",
                f"{ticker.upper()} expands margins",
            ],
            "timestamp": datetime.now(UTC),
        }


def _override_analyzer():
    return StubSentimentAnalyzer()


client = TestClient(app)


def setup_function():
    app.dependency_overrides[get_sentiment_analyzer] = _override_analyzer


def teardown_function():
    app.dependency_overrides.clear()


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "model_loaded" in body


def test_analyze_sentiment():
    response = client.post(
        "/analyze-sentiment",
        json={
            "text": "Apple stock surges on strong iPhone sales",
            "ticker": "AAPL",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "sentiment_score" in data
    assert "sentiment_label" in data
    assert -1 <= data["sentiment_score"] <= 1


def test_ticker_sentiment():
    response = client.get("/sentiment/AAPL?days_lookback=7&max_articles=10")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["news_count"] == 2


def test_batch_sentiment():
    response = client.get("/batch-sentiment?tickers=AAPL,MSFT&days_lookback=7&max_articles=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {item["ticker"] for item in data} == {"AAPL", "MSFT"}

