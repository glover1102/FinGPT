from datetime import datetime

from pydantic import BaseModel, Field


class SentimentRequest(BaseModel):
    text: str = Field(..., description="News text or headline to analyze", min_length=1)
    ticker: str | None = Field(None, description="Optional ticker symbol for context")


class SentimentResponse(BaseModel):
    sentiment_score: float = Field(..., description="Score from -1 (bearish) to +1 (bullish)")
    sentiment_label: str = Field(..., description="negative | neutral | positive")
    confidence: float = Field(..., description="Model confidence 0-1")
    analyzed_text: str
    timestamp: datetime


class TickerSentimentRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol (e.g., AAPL)", min_length=1)
    days_lookback: int = Field(7, description="Number of days to fetch news", ge=1, le=30)
    max_articles: int = Field(20, description="Max number of articles to analyze", ge=1, le=100)


class TickerSentimentResponse(BaseModel):
    ticker: str
    sentiment_score: float
    sentiment_label: str
    confidence: float
    news_count: int
    articles_analyzed: list[str]
    timestamp: datetime

