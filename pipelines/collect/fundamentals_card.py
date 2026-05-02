from __future__ import annotations

import concurrent.futures
from datetime import date
from typing import Any, Optional

from core.schemas.fundamentals import FundamentalsCard
from core.utils.asset_classifier import classify
from core.utils.logger import get_logger

logger = get_logger("pipelines.collect.fundamentals")


def _run_with_timeout(func, *args, timeout_s: float):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, *args)
    try:
        return future.result(timeout=timeout_s)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _float_or_none(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _fetch_info(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info or {}
    if not isinstance(info, dict):
        return {}
    return info


def _build_card(ticker: str, info: dict[str, Any]) -> FundamentalsCard:
    price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("previousClose")
    )
    return FundamentalsCard(
        ticker=ticker.upper(),
        as_of=date.today().isoformat(),
        name=_str_or_none(info.get("longName") or info.get("shortName")),
        sector=_str_or_none(info.get("sector")),
        industry=_str_or_none(info.get("industry")),
        market_cap=_float_or_none(info.get("marketCap")),
        price=_float_or_none(price),
        week52_high=_float_or_none(info.get("fiftyTwoWeekHigh")),
        week52_low=_float_or_none(info.get("fiftyTwoWeekLow")),
        trailing_pe=_float_or_none(info.get("trailingPE")),
        forward_pe=_float_or_none(info.get("forwardPE")),
        price_to_book=_float_or_none(info.get("priceToBook")),
        profit_margin=_float_or_none(info.get("profitMargins")),
        revenue_growth=_float_or_none(info.get("revenueGrowth")),
        earnings_growth=_float_or_none(info.get("earningsGrowth")),
        dividend_yield=_float_or_none(info.get("dividendYield")),
        beta=_float_or_none(info.get("beta")),
        analyst_rating_mean=_float_or_none(info.get("recommendationMean")),
        analyst_target_mean=_float_or_none(info.get("targetMeanPrice")),
        num_analysts=_int_or_none(info.get("numberOfAnalystOpinions")),
    )


def collect_fundamentals_card(ticker: str, timeout_s: float = 5.0) -> Optional[FundamentalsCard]:
    """Collect a fixed yfinance fundamentals snapshot for single-name equities."""
    profile = classify(ticker)
    if profile.is_etf or profile.asset_class not in {"equity", "foreign_equity"}:
        logger.info(
            "[FUNDAMENTALS] skipped ticker=%s asset_class=%s is_etf=%s",
            profile.ticker,
            profile.asset_class,
            profile.is_etf,
        )
        return None

    try:
        info = _run_with_timeout(_fetch_info, profile.ticker, timeout_s=timeout_s)
        if not info:
            return None
        return _build_card(profile.ticker, info)
    except concurrent.futures.TimeoutError:
        logger.warning("[FUNDAMENTALS] skip for %s: timeout after %.1fs", profile.ticker, timeout_s)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FUNDAMENTALS] skip for %s: %s", profile.ticker, exc)
        return None
