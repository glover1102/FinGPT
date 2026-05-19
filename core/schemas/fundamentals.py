from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class FundamentalsCard(BaseModel):
    ticker: str
    as_of: str
    asset_class: Optional[str] = None
    quote_type: Optional[str] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
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
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    return_on_equity: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    total_revenue: Optional[float] = None
    revenue_per_share: Optional[float] = None
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    book_value: Optional[float] = None
    enterprise_value: Optional[float] = None
    ebitda: Optional[float] = None
    free_cashflow: Optional[float] = None
    total_cash: Optional[float] = None
    total_debt: Optional[float] = None
    debt_to_equity: Optional[float] = None
    shares_outstanding: Optional[float] = None
    dividend_yield: Optional[float] = None
    yield_value: Optional[float] = None
    beta: Optional[float] = None
    analyst_rating_mean: Optional[float] = None
    analyst_target_mean: Optional[float] = None
    num_analysts: Optional[int] = None
    total_assets: Optional[float] = None
    net_assets: Optional[float] = None
    nav_price: Optional[float] = None
    expense_ratio: Optional[float] = None
    average_volume: Optional[float] = None
    source: str = "yfinance"
