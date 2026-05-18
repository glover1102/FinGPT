from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.api.routers.market_utils import clean_ticker_list, filter_price_rows
from pipelines.backtest.engine import (
    BacktestConfig,
    run_backtest,
    run_momentum_ranking_backtest,
    run_multi_asset_backtest,
)
from pipelines.data_mart.storage.repository import get_prices as data_mart_get_prices


router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


class BacktestRunRequest(BaseModel):
    ticker: str | None = Field(default=None)
    tickers: list[str] = Field(default_factory=list)
    strategy: str = Field(default="buy_and_hold")
    lookback_days: int = Field(default=252, ge=2, le=5000)
    start_date: str | None = Field(default=None)
    end_date: str | None = Field(default=None)
    short_window: int = Field(default=20, ge=1, le=252)
    long_window: int = Field(default=50, ge=2, le=756)
    top_n: int = Field(default=1, ge=1, le=50)
    rebalance_every: int = Field(default=21, ge=1, le=252)
    transaction_cost_bps: float = Field(default=5.0, ge=0, le=1000)
    slippage_bps: float = Field(default=2.0, ge=0, le=1000)
    initial_capital: float = Field(default=1.0, gt=0)
    price_rows: list[dict[str, Any]] | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def _clean_ticker(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip().upper()
        return cleaned or None

    @field_validator("tickers", mode="before")
    @classmethod
    def _clean_tickers(cls, value: Any) -> list[str]:
        return clean_ticker_list(value)

    @field_validator("strategy", mode="before")
    @classmethod
    def _clean_strategy(cls, value: Any) -> str:
        return str(value or "buy_and_hold").strip().lower()

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _clean_date(cls, value: Any) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None


@router.post("/run")
async def backtest_run(request: BacktestRunRequest) -> dict[str, Any]:
    """Run a deterministic backtest against data-mart prices or explicit request rows."""

    rows = list(request.price_rows or [])
    data_status = "request_rows" if rows else "data_mart"
    if not rows:
        tickers = request.tickers or ([request.ticker] if request.ticker else [])
        if not tickers:
            raise HTTPException(status_code=422, detail="ticker, tickers, or price_rows is required")
        rows_by_asset: dict[str, list[dict[str, Any]]] = {}
        missing: list[str] = []
        for ticker in tickers:
            asset_rows = await asyncio.to_thread(data_mart_get_prices, ticker, limit=request.lookback_days)
            asset_rows = filter_price_rows(asset_rows, start_date=request.start_date, end_date=request.end_date)
            rows_by_asset[ticker] = asset_rows
            if len(asset_rows) < 2:
                missing.append(ticker)
        config = BacktestConfig(
            strategy=request.strategy,
            short_window=request.short_window,
            long_window=request.long_window,
            transaction_cost_bps=request.transaction_cost_bps,
            slippage_bps=request.slippage_bps,
            initial_capital=request.initial_capital,
        )
        try:
            if request.strategy == "momentum_ranking" and len(tickers) > 1:
                result = await asyncio.to_thread(
                    run_momentum_ranking_backtest,
                    rows_by_asset,
                    lookback=request.short_window,
                    top_n=min(request.top_n, len(tickers)),
                    rebalance_every=request.rebalance_every,
                    config=config,
                )
                result["asset_results"] = {}
            else:
                asset_results = {
                    ticker: await asyncio.to_thread(run_backtest, asset_rows, config)
                    for ticker, asset_rows in rows_by_asset.items()
                }
                if len(asset_results) == 1:
                    only_ticker, only_result = next(iter(asset_results.items()))
                    result = dict(only_result)
                    result["asset_results"] = {only_ticker: dict(only_result)}
                else:
                    result = await asyncio.to_thread(run_multi_asset_backtest, rows_by_asset, config)
                    result["summary_policy"] = "reported metrics come from one aligned multi-asset portfolio equity curve"
                    result["asset_results"] = asset_results
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        result["ticker"] = request.ticker or (tickers[0] if len(tickers) == 1 else None)
        result["tickers"] = tickers
        result["missing_assets"] = missing
        result["price_counts"] = {ticker: len(asset_rows) for ticker, asset_rows in rows_by_asset.items()}
        result["data_status"] = "partial" if missing else data_status
        result["requested_range"] = {
            "start": request.start_date,
            "end": request.end_date,
            "lookback_days": request.lookback_days,
        }
        return result
    config = BacktestConfig(
        strategy=request.strategy,
        short_window=request.short_window,
        long_window=request.long_window,
        transaction_cost_bps=request.transaction_cost_bps,
        slippage_bps=request.slippage_bps,
        initial_capital=request.initial_capital,
    )
    try:
        result = await asyncio.to_thread(run_backtest, rows, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["ticker"] = request.ticker
    result["tickers"] = request.tickers or ([request.ticker] if request.ticker else [])
    result["price_count"] = len(rows)
    result["data_status"] = data_status if rows else "empty"
    result["requested_range"] = {"start": request.start_date, "end": request.end_date, "lookback_days": request.lookback_days}
    return result
