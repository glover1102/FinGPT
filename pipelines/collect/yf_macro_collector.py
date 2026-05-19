"""yfinance-backed macro snapshot for FX / futures / commodities / crypto.

Why this exists
---------------
For non-equity assets yfinance is the cheapest reliable source of both
headline news AND the price history itself. Rather than bolt yet another
news normalizer into the pipeline, we emit two document kinds per ticker:

1. A **price-history narrative**: a short natural-language paragraph that
   summarizes the latest window (open→close, range, percent change). RAG can
   cite this as ``FinGPT-derived macro snapshot``.
2. **Headlines**: we reuse ``_fetch_yfinance_feed`` via the equity collector
   — NOT imported here to avoid a circular dependency. Instead the macro
   orchestrator (``macro_collector.py``) fans out to Google News RSS for the
   news half, which is more reliable for FX/futures than Yahoo headlines.

Design note
-----------
Yahoo's "news" attribute is empty for many FX and futures tickers, so we do
not retry there. This keeps the macro bundle tight and avoids confusing the
downstream freshness filter with stale placeholder headlines.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.utils.asset_classifier import AssetProfile
from core.utils.data_helpers import build_doc_id
from core.utils.logger import get_logger
from pipelines.collect.models import SourceCollectionResult

logger = get_logger("pipelines.collect.yf_macro")

_HIST_MIN_DAYS = 30


def collect_price_snapshot(
    profile: AssetProfile,
    lookback_days: int,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    """Produce a single price-narrative document for the ticker.

    yfinance is imported lazily so the macro path only pulls the dependency
    when the user actually runs a non-equity ticker.
    """
    started = datetime.now()
    window = max(lookback_days, _HIST_MIN_DAYS)

    try:
        import yfinance as yf
    except ImportError as exc:
        elapsed = round((datetime.now() - started).total_seconds(), 2)
        return (
            SourceCollectionResult(
                "macro",
                "provider_unavailable",
                0,
                elapsed,
                f"yfinance not installed: {exc}",
            ),
            [],
        )

    try:
        ticker = yf.Ticker(profile.ticker)
        start = (datetime.now() - timedelta(days=window)).date().isoformat()
        hist = ticker.history(start=start, auto_adjust=False)
    except Exception as exc:  # noqa: BLE001
        elapsed = round((datetime.now() - started).total_seconds(), 2)
        return (
            SourceCollectionResult("macro", "provider_unavailable", 0, elapsed, f"yfinance fetch failed: {exc}"),
            [],
        )

    if hist is None or getattr(hist, "empty", True):
        elapsed = round((datetime.now() - started).total_seconds(), 2)
        return (
            SourceCollectionResult("macro", "empty", 0, elapsed, f"yfinance returned empty history for {profile.ticker}."),
            [],
        )

    # We intentionally do *not* depend on pandas types beyond basic iteration
    # so the collector stays compatible with minor yfinance refactors.
    try:
        closes = [float(v) for v in hist["Close"].dropna().tolist()]
        highs = [float(v) for v in hist["High"].dropna().tolist()]
        lows = [float(v) for v in hist["Low"].dropna().tolist()]
        dates = [d.to_pydatetime() if hasattr(d, "to_pydatetime") else d for d in hist.index.tolist()]
    except Exception as exc:  # noqa: BLE001
        elapsed = round((datetime.now() - started).total_seconds(), 2)
        return (
            SourceCollectionResult("macro", "provider_unavailable", 0, elapsed, f"yfinance parse failed: {exc}"),
            [],
        )

    if not closes or not dates:
        elapsed = round((datetime.now() - started).total_seconds(), 2)
        return (
            SourceCollectionResult("macro", "empty", 0, elapsed, "yfinance history had no usable rows."),
            [],
        )

    first_close = closes[0]
    last_close = closes[-1]
    peak = max(highs) if highs else last_close
    trough = min(lows) if lows else last_close
    change = last_close - first_close
    pct = (change / first_close * 100.0) if first_close else 0.0
    direction = "rose" if change > 0 else ("fell" if change < 0 else "was flat")
    first_dt = dates[0]
    last_dt = dates[-1]
    first_date = first_dt.date().isoformat() if hasattr(first_dt, "date") else str(first_dt)
    last_date = last_dt.date().isoformat() if hasattr(last_dt, "date") else str(last_dt)

    title = f"{profile.display_name} price snapshot ({first_date} → {last_date})"
    body = (
        f"{profile.display_name} (Yahoo symbol {profile.ticker}) {direction} "
        f"from {first_close:.4f} on {first_date} to {last_close:.4f} on {last_date}, "
        f"a change of {change:+.4f} ({pct:+.2f}%). Over the {len(closes)} trading "
        f"sessions in this window the instrument peaked at {peak:.4f} and bottomed "
        f"at {trough:.4f}. Source: Yahoo Finance price history."
    )

    published_at = last_dt.isoformat() if hasattr(last_dt, "isoformat") else str(last_dt)
    seed = "|".join([profile.ticker, first_date, last_date, f"{last_close:.4f}"])
    doc_id = build_doc_id(profile.ticker, "macro", seed)

    document = {
        "doc_id": doc_id,
        "ticker": profile.ticker,
        "symbol": profile.ticker,
        "doc_type": "macro",
        "source": "yahoo_finance_history",
        "published_at": published_at,
        "title": title,
        "text": body,
        "url": f"https://finance.yahoo.com/quote/{profile.ticker}",
        "admitted_by": "macro_price_snapshot",
    }

    elapsed = round((datetime.now() - started).total_seconds(), 2)
    return (
        SourceCollectionResult(
            "macro",
            "ok",
            1,
            elapsed,
            f"yfinance price snapshot captured for {profile.ticker}.",
        ),
        [document],
    )
