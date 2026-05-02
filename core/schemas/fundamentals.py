from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class FundamentalsCard(BaseModel):
    ticker: str
    as_of: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    price: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    price_to_book: Optional[float] = None
    profit_margin: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    analyst_rating_mean: Optional[float] = None
    analyst_target_mean: Optional[float] = None
    num_analysts: Optional[int] = None
    source: str = "yfinance"
