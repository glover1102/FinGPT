from __future__ import annotations

import logging
from functools import lru_cache

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .fingpt_loader import FinGPTModel
from .models import SentimentRequest, SentimentResponse, TickerSentimentResponse
from .news_fetcher import NewsFetcher
from .sentiment_analyzer import SentimentAnalyzer


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper(), logging.INFO)),
    )


settings = get_settings()
_configure_logging(settings.log_level)
log = structlog.get_logger()

app = FastAPI(
    title="FinGPT Sentiment API",
    description="Financial sentiment analysis powered by FinGPT",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_sentiment_analyzer() -> SentimentAnalyzer:
    runtime_settings = get_settings()
    model = FinGPTModel(
        base_model_name=runtime_settings.base_model_name,
        lora_model_name=runtime_settings.fingpt_model_name,
        use_8bit=runtime_settings.use_8bit,
        hf_token=runtime_settings.hf_token,
    )
    news_fetcher = NewsFetcher(runtime_settings.finnhub_api_key)
    return SentimentAnalyzer(
        fingpt_model=model,
        news_fetcher=news_fetcher,
        cache_ttl_seconds=runtime_settings.cache_ttl_seconds,
        max_cache_size=runtime_settings.max_cache_size,
    )


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    analyzer = get_sentiment_analyzer()
    return {
        "status": "healthy",
        "model_loaded": analyzer.model.is_loaded(),
        "finnhub_configured": bool(settings.finnhub_api_key),
    }


@app.post("/analyze-sentiment", response_model=SentimentResponse)
def analyze_sentiment(
    request: SentimentRequest,
    analyzer: SentimentAnalyzer = Depends(get_sentiment_analyzer),
) -> dict:
    try:
        return analyzer.analyze_text(request.text, ticker=request.ticker)
    except RuntimeError as exc:
        log.error("sentiment_analysis_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("sentiment_analysis_failed")
        raise HTTPException(status_code=500, detail="Sentiment analysis failed") from exc


@app.get("/sentiment/{ticker}", response_model=TickerSentimentResponse)
def sentiment_for_ticker(
    ticker: str,
    days_lookback: int = Query(7, ge=1, le=30),
    max_articles: int = Query(20, ge=1, le=100),
    analyzer: SentimentAnalyzer = Depends(get_sentiment_analyzer),
) -> dict:
    try:
        return analyzer.analyze_ticker(ticker, days=days_lookback, max_articles=max_articles)
    except RuntimeError as exc:
        log.error("ticker_sentiment_unavailable", ticker=ticker, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("ticker_sentiment_failed", ticker=ticker)
        raise HTTPException(status_code=500, detail="Ticker sentiment analysis failed") from exc


@app.get("/batch-sentiment", response_model=list[TickerSentimentResponse])
def batch_sentiment(
    tickers: str = Query(..., description="Comma-separated ticker symbols"),
    days_lookback: int = Query(7, ge=1, le=30),
    max_articles: int = Query(20, ge=1, le=100),
    analyzer: SentimentAnalyzer = Depends(get_sentiment_analyzer),
) -> list[dict]:
    parsed_tickers = [ticker.strip().upper() for ticker in tickers.split(",") if ticker.strip()]
    if not parsed_tickers:
        raise HTTPException(status_code=400, detail="At least one ticker is required")

    results = []
    for ticker in parsed_tickers:
        results.append(analyzer.analyze_ticker(ticker, days=days_lookback, max_articles=max_articles))
    return results

