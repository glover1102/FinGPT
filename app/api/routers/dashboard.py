from __future__ import annotations

import asyncio
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.api.heatmap_universe import HEATMAP_UNIVERSE_VERSION, US_EQUITY_HEATMAP_UNIVERSE
from core.utils.logger import get_logger
from pipelines.collect.google_news_rss import collect_news_from_google_rss


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
logger = get_logger("api.dashboard")

_DASHBOARD_EQUITY_HEATMAP_CACHE_TTL_SEC = 60
_dashboard_equity_heatmap_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_EQUITY_HEATMAP_UNIVERSE = US_EQUITY_HEATMAP_UNIVERSE
_EQUITY_HEATMAP_BATCH_SIZE = 60


@router.get("/news")
async def dashboard_news(limit: int = 20) -> dict[str, Any]:
    """News cards for the UI home dashboard."""

    watchlist: list[dict[str, Any]] = [
        {
            "symbol": "MARKET",
            "query": '("Wall Street" OR "S&P 500" OR "stock market") (Reuters OR CNBC OR Bloomberg OR "Wall Street Journal" OR "Financial Times")',
            "category": "equity_index",
            "lookback": 7,
        },
        {"symbol": "SPY", "query": None, "category": "equity_index", "lookback": 7},
        {"symbol": "QQQ", "query": None, "category": "equity_index", "lookback": 7},
        {
            "symbol": "MACRO",
            "query": '("Federal Reserve" OR inflation OR CPI OR "Treasury yields" OR "rate cuts") (Reuters OR CNBC OR Bloomberg OR "New York Times" OR "Financial Times")',
            "category": "macro_policy",
            "lookback": 10,
        },
        {"symbol": "RATES", "query": 'site:cnbc.com "Treasury yields" when:10d', "category": "rates_credit", "lookback": 10},
        {
            "symbol": "BOND_MARKET",
            "query": 'site:bloomberg.com ("Treasury yields" OR "Bond Traders" OR "bond market") when:10d',
            "category": "rates_credit",
            "lookback": 10,
        },
        {"symbol": "TLT", "query": '"Treasury yields" OR "long bond ETF" OR TLT', "category": "rates_credit", "lookback": 10},
        {
            "symbol": "CREDIT",
            "query": 'site:bloomberg.com ("credit markets" OR "credit spreads" OR "high yield bonds") when:14d',
            "category": "rates_credit",
            "lookback": 14,
        },
        {
            "symbol": "CREDIT_REUTERS",
            "query": 'site:reuters.com ("credit spreads" OR "corporate debt" OR "high yield bonds") when:14d',
            "category": "rates_credit",
            "lookback": 14,
        },
        {"symbol": "HYG", "query": '"credit spreads" OR "high yield bonds" OR HYG', "category": "rates_credit", "lookback": 14},
        {
            "symbol": "AI_SEMIS",
            "query": '("AI chips" OR semiconductors OR Nvidia OR "AI capex") (Reuters OR CNBC OR Bloomberg OR "Financial Times")',
            "category": "ai_semis",
            "lookback": 10,
        },
        {
            "symbol": "EARNINGS",
            "query": '("earnings season" OR "earnings outlook" OR margins OR guidance) (Reuters OR CNBC OR Bloomberg OR "Wall Street Journal")',
            "category": "earnings",
            "lookback": 10,
        },
        {"symbol": "GLD", "query": '"gold price" OR "gold futures" OR "real yields gold" OR GLD', "category": "commodity", "lookback": 14},
        {"symbol": "OIL", "query": '"oil prices" OR "crude oil" OR OPEC OR "energy market"', "category": "commodity", "lookback": 14},
        {"symbol": "BTC-USD", "query": '"Bitcoin price" OR "Bitcoin ETF" OR cryptocurrency OR "crypto market"', "category": "crypto", "lookback": 14},
    ]
    max_items = max(6, min(int(limit or 20), 30))

    major_sources = (
        "reuters",
        "bloomberg",
        "cnbc",
        "wall street journal",
        "wsj",
        "financial times",
        "new york times",
        "nytimes",
        "associated press",
        "ap news",
        "barron's",
        "barrons",
    )
    market_sources = ("marketwatch", "yahoo finance", "axios", "fortune", "the economist", "seeking alpha")
    low_priority_sources = ("invesco", "etf database", "tipranks", "motley fool", "moomoo", "minichart", "investing.com")
    topic_keywords = {
        "equity_index": ("stock", "s&p", "nasdaq", "wall street", "equity", "market"),
        "macro_policy": ("inflation", "fed", "federal reserve", "consumer", "sentiment", "jobs", "cpi", "rates", "gdp"),
        "rates_credit": ("treasury", "yield", "bond", "credit", "spread", "debt", "fed", "rate", "default", "loan"),
        "ai_semis": ("ai", "chip", "semiconductor", "nvidia", "intel", "huawei", "capex"),
        "earnings": ("earnings", "profit", "margin", "guidance", "revenue", "quarter"),
        "commodity": ("oil", "crude", "gold", "opec", "commodity", "energy"),
        "crypto": ("bitcoin", "crypto", "cryptocurrency", "etf", "ethereum", "wallet"),
    }

    def _published_ts(value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def _repair_feed_text(value: Any) -> str:
        text = str(value or "")
        if not text or not any(marker in text for marker in ("창", "횄", "횂")):
            return text
        try:
            repaired = text.encode("latin1").decode("utf-8")
            return repaired if repaired else text
        except Exception:
            return text

    def _source_score(item: dict[str, Any]) -> int:
        haystack = " ".join([str(item.get("source") or ""), str(item.get("title") or ""), str(item.get("url") or "")]).lower()
        if any(token in haystack for token in major_sources):
            return 0
        if any(token in haystack for token in market_sources):
            return 1
        if any(token in haystack for token in low_priority_sources):
            return 3
        return 2

    def _topic_score(entry: dict[str, Any], item: dict[str, Any]) -> int:
        category = str(entry.get("category") or "market")
        title = str(item.get("title") or "").lower()
        return 0 if any(keyword in title for keyword in topic_keywords.get(category, ())) else 1

    def collect_one(entry: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            _, docs = collect_news_from_google_rss(
                str(entry["symbol"]),
                int(entry.get("lookback") or 10),
                limit=8,
                query_override=entry.get("query"),
                strict_purity=entry.get("query") is None,
            )
            return docs
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DASHBOARD_NEWS] %s failed: %s", entry.get("symbol"), exc)
            return []

    groups = await asyncio.gather(*(asyncio.to_thread(collect_one, entry) for entry in watchlist))
    seen: set[str] = set()

    def make_item(entry: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any] | None:
        symbol = str(entry["symbol"])
        title = _repair_feed_text(doc.get("title")).strip()
        url = str(doc.get("url") or "").strip()
        key = url or title.lower()
        if not title or key in seen:
            return None
        seen.add(key)
        published_at = doc.get("published_at") or doc.get("date") or ""
        item = {
            "symbol": symbol,
            "title": title,
            "source": _repair_feed_text(doc.get("source") or "Google News"),
            "url": url,
            "category": entry.get("category") or "market",
            "published_at": published_at,
            "collected_at": doc.get("collected_at") or datetime.now(timezone.utc).isoformat(),
            "summary": _repair_feed_text(doc.get("text") or doc.get("chunk") or ""),
        }
        item["source_tier"] = _source_score(item)
        item["topic_tier"] = _topic_score(entry, item)
        item["sort_ts"] = _published_ts(str(published_at))
        return item

    candidates_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for entry, docs in zip(watchlist, groups):
        symbol = str(entry["symbol"])
        candidates_by_symbol[symbol] = []
        for doc in docs:
            item = make_item(entry, doc)
            if item:
                candidates_by_symbol[symbol].append(item)
        candidates_by_symbol[symbol].sort(
            key=lambda row: (int(row.get("source_tier", 2)), int(row.get("topic_tier", 1)), -float(row.get("sort_ts", 0.0)))
        )

    items: list[dict[str, Any]] = []
    used_categories: set[str] = set()
    for entry in watchlist:
        symbol = str(entry["symbol"])
        category = str(entry.get("category") or "market")
        if category in used_categories:
            continue
        if candidates_by_symbol.get(symbol):
            items.append(candidates_by_symbol[symbol][0])
            used_categories.add(category)
            if len(items) >= max_items:
                break
    if len(items) < max_items:
        category_counts: dict[str, int] = {}
        for item in items:
            category = str(item.get("category") or "market")
            category_counts[category] = category_counts.get(category, 0) + 1
        leftovers = [item for rows in candidates_by_symbol.values() for item in rows if item not in items]
        leftovers.sort(
            key=lambda row: (int(row.get("source_tier", 2)), int(row.get("topic_tier", 1)), -float(row.get("sort_ts", 0.0)))
        )
        deferred: list[dict[str, Any]] = []
        for item in leftovers:
            if len(items) >= max_items:
                break
            category = str(item.get("category") or "market")
            if category_counts.get(category, 0) >= 4:
                deferred.append(item)
                continue
            items.append(item)
            category_counts[category] = category_counts.get(category, 0) + 1
        if len(items) < max_items:
            items.extend(deferred[: max_items - len(items)])

    for item in items:
        item.pop("sort_ts", None)
        item.pop("topic_tier", None)

    return {
        "items": items[:max_items],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "google_news_rss",
        "selection_policy": "major_source_priority_issue_coverage",
    }


@router.get("/market")
async def dashboard_market() -> dict[str, Any]:
    """Local market snapshot for the UI dashboard."""

    symbols = [
        {"symbol": "SPY", "label": "S&P 500", "asset_class": "equity_index"},
        {"symbol": "QQQ", "label": "Nasdaq 100", "asset_class": "equity_index"},
        {"symbol": "TLT", "label": "Long Treasury", "asset_class": "rates_bonds"},
        {"symbol": "HYG", "label": "High Yield Credit", "asset_class": "credit"},
        {"symbol": "LQD", "label": "IG Credit", "asset_class": "credit"},
        {"symbol": "GLD", "label": "Gold", "asset_class": "commodity"},
        {"symbol": "BTC-USD", "label": "Bitcoin", "asset_class": "crypto"},
        {"symbol": "DX-Y.NYB", "label": "DXY", "asset_class": "fx"},
        {"symbol": "^TNX", "label": "US 10Y Yield", "asset_class": "rates"},
    ]

    def pct_change(close_values: Any, periods: int) -> float | None:
        try:
            if len(close_values) <= periods:
                return None
            current = float(close_values.iloc[-1])
            previous = float(close_values.iloc[-1 - periods])
            if previous == 0:
                return None
            return round((current / previous - 1.0) * 100.0, 2)
        except Exception:
            return None

    def _as_iso(value: Any) -> str:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _close_series(frame: Any) -> Any:
        if frame is None or frame.empty or "Close" not in frame:
            raise RuntimeError("no close data")
        close = frame["Close"].dropna()
        if close.empty:
            raise RuntimeError("empty close series")
        return close

    def collect_one(item: dict[str, str]) -> dict[str, Any]:
        intraday_error = ""
        try:
            import yfinance as yf

            ticker = yf.Ticker(item["symbol"])
            intraday = ticker.history(period="5d", interval="5m", auto_adjust=False, prepost=False)
            close = _close_series(intraday)
            daily_last = close.groupby(close.index.date).last().dropna()
            if len(daily_last) < 2:
                raise RuntimeError("not enough intraday days for 1d return")
            last_idx = close.index[-1]
            as_of = _as_iso(last_idx)
            freshness = _us_market_freshness(as_of)
            usable = _dashboard_freshness_is_decision_usable(freshness.get("freshness_status"))
            daily_history = ticker.history(period="6mo", interval="1d", auto_adjust=False)
            daily_close = _close_series(daily_history)
            return {
                **item,
                "price": round(float(close.iloc[-1]), 4),
                "as_of": as_of,
                "source": "yfinance_intraday_5m",
                "status": "ok" if usable else "stale",
                "is_decision_usable": usable,
                "freshness_status": freshness.get("freshness_status", "unknown"),
                "age_minutes": freshness.get("age_minutes"),
                "market_clock": freshness.get("market_clock"),
                "returns": {
                    "1d": round((float(daily_last.iloc[-1]) / float(daily_last.iloc[-2]) - 1.0) * 100.0, 2),
                    "5d": pct_change(daily_close, 5),
                    "1m": pct_change(daily_close, 21),
                    "3m": pct_change(daily_close, 63),
                },
            }
        except Exception as exc:  # noqa: BLE001
            intraday_error = str(exc)
            try:
                import yfinance as yf

                history = yf.Ticker(item["symbol"]).history(period="6mo", interval="1d", auto_adjust=False)
                close = _close_series(history)
                last_idx = close.index[-1]
                as_of = last_idx.date().isoformat() if hasattr(last_idx, "date") else str(last_idx)
                freshness = _us_market_freshness(as_of)
                usable = _dashboard_freshness_is_decision_usable(freshness.get("freshness_status"))
                return {
                    **item,
                    "price": round(float(close.iloc[-1]), 4),
                    "as_of": as_of,
                    "source": "yfinance_daily_fallback",
                    "status": "ok" if usable else "stale",
                    "is_decision_usable": usable,
                    "freshness_status": freshness.get("freshness_status", "unknown"),
                    "age_minutes": freshness.get("age_minutes"),
                    "market_clock": freshness.get("market_clock"),
                    "intraday_error": intraday_error,
                    "returns": {
                        "1d": pct_change(close, 1),
                        "5d": pct_change(close, 5),
                        "1m": pct_change(close, 21),
                        "3m": pct_change(close, 63),
                    },
                }
            except Exception as fallback_exc:  # noqa: BLE001
                logger.warning("[DASHBOARD_MARKET] %s failed: %s", item["symbol"], fallback_exc)
                return {
                    **item,
                    "price": None,
                    "as_of": "",
                    "source": "yfinance",
                    "status": "unavailable",
                    "is_decision_usable": False,
                    "freshness_status": "unknown",
                    "age_minutes": None,
                    "error": str(fallback_exc),
                    "intraday_error": intraday_error,
                    "returns": {"1d": None, "5d": None, "1m": None, "3m": None},
                }

    items = await asyncio.gather(*(asyncio.to_thread(collect_one, item) for item in symbols))
    ok_count = sum(1 for item in items if item.get("status") == "ok")
    decision_usable_count = sum(1 for item in items if item.get("is_decision_usable"))
    freshness_counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("freshness_status") or "unknown")
        freshness_counts[key] = freshness_counts.get(key, 0) + 1
    return {
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "yfinance",
        "ok_count": ok_count,
        "decision_usable_count": decision_usable_count,
        "freshness_counts": freshness_counts,
        "freshness_policy": "US market hours require fresh or delayed intraday data; stale prior-close data is labelled and excluded from decision-usable counts.",
        "warning": "" if decision_usable_count else "No fresh or delayed intraday market snapshot could be loaded from yfinance.",
    }


def _previous_business_day(value: Any) -> Any:
    day = value
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _expected_latest_us_market_date(now_ny: datetime) -> Any:
    today = now_ny.date()
    if now_ny.weekday() >= 5:
        return _previous_business_day(today - timedelta(days=1))
    if now_ny.time() < dt_time(9, 30):
        return _previous_business_day(today - timedelta(days=1))
    return today


def _dashboard_freshness_is_decision_usable(status: Any) -> bool:
    return str(status or "").lower() in {"fresh", "delayed", "closed"}


def _us_market_freshness(as_of: str) -> dict[str, Any]:
    try:
        latest = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    except Exception:
        return {"freshness_status": "unknown", "age_minutes": None, "is_intraday": False}

    ny_tz = ZoneInfo("America/New_York")
    latest_ny = latest.astimezone(ny_tz) if latest.tzinfo else latest.replace(tzinfo=ny_tz)
    now_ny = datetime.now(ny_tz)
    age_minutes = max(0.0, round((now_ny - latest_ny).total_seconds() / 60.0, 1))
    expected_date = _expected_latest_us_market_date(now_ny)
    market_open = now_ny.weekday() < 5 and dt_time(9, 30) <= now_ny.time() <= dt_time(16, 15)
    is_intraday = latest_ny.date() == expected_date
    if latest_ny.date() < expected_date:
        status = "stale_prior_close"
    elif market_open and age_minutes <= 25:
        status = "fresh"
    elif market_open and age_minutes <= 90:
        status = "delayed"
    elif market_open:
        status = "stale"
    else:
        status = "closed"
    return {
        "freshness_status": status,
        "age_minutes": age_minutes,
        "is_intraday": is_intraday,
        "market_clock": now_ny.isoformat(),
        "expected_market_date": expected_date.isoformat(),
    }


def _tile_span(weight: float) -> dict[str, int]:
    if weight >= 8:
        return {"col": 4, "row": 4}
    if weight >= 4:
        return {"col": 3, "row": 3}
    if weight >= 2:
        return {"col": 2, "row": 2}
    return {"col": 1, "row": 1}


def _batched_symbols(symbols: list[str], batch_size: int) -> list[list[str]]:
    size = max(1, int(batch_size or 1))
    return [symbols[idx:idx + size] for idx in range(0, len(symbols), size)]


def _extract_yfinance_symbol_frame(raw: Any, pd: Any, symbol: str) -> Any:
    if raw is None or getattr(raw, "empty", False):
        raise RuntimeError("empty intraday download")
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = list(raw.columns.get_level_values(0))
        if symbol in level0:
            return raw[symbol]
        return raw.xs(symbol, axis=1, level=0)
    return raw


def _download_equity_heatmap_frames(yf: Any, pd: Any, symbols: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
    frames: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for batch in _batched_symbols(symbols, _EQUITY_HEATMAP_BATCH_SIZE):
        try:
            raw = yf.download(
                tickers=batch,
                period="5d",
                interval="5m",
                auto_adjust=False,
                prepost=False,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as exc:  # noqa: BLE001
            for symbol in batch:
                errors[symbol] = f"batch download failed: {exc}"
            continue
        for symbol in batch:
            try:
                frames[symbol] = _extract_yfinance_symbol_frame(raw, pd, symbol)
            except Exception as exc:  # noqa: BLE001
                errors[symbol] = str(exc)
    return frames, errors


def _collect_equity_heatmap_snapshot() -> dict[str, Any]:
    import pandas as pd
    import yfinance as yf

    symbols = [item["symbol"] for item in _EQUITY_HEATMAP_UNIVERSE]
    frames_by_symbol, download_errors = _download_equity_heatmap_frames(yf, pd, symbols)
    now_utc = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []

    for meta in _EQUITY_HEATMAP_UNIVERSE:
        symbol = str(meta["symbol"])
        try:
            if symbol in download_errors:
                raise RuntimeError(download_errors[symbol])
            frame = frames_by_symbol.get(symbol)
            if frame is None or frame.empty or "Close" not in frame:
                raise RuntimeError("no intraday close data")
            close = frame["Close"].dropna()
            if close.empty:
                raise RuntimeError("empty intraday close series")
            daily_last = close.groupby(close.index.date).last().dropna()
            if len(daily_last) < 2:
                raise RuntimeError("not enough intraday days for previous-close comparison")
            latest_idx = close.index[-1]
            latest_price = float(close.iloc[-1])
            previous_close = float(daily_last.iloc[-2])
            if previous_close == 0:
                raise RuntimeError("previous close is zero")
            change_pct = round((latest_price / previous_close - 1.0) * 100.0, 2)
            as_of = latest_idx.isoformat() if hasattr(latest_idx, "isoformat") else str(latest_idx)
            freshness = _us_market_freshness(as_of)
            usable = _dashboard_freshness_is_decision_usable(freshness["freshness_status"])
            items.append({
                **meta,
                "price": round(latest_price, 4),
                "previous_close": round(previous_close, 4),
                "change_pct": change_pct,
                "as_of": as_of,
                "source": "yfinance_intraday_5m",
                "status": "ok" if usable else "stale",
                "is_decision_usable": usable,
                "freshness_status": freshness["freshness_status"],
                "age_minutes": freshness["age_minutes"],
                "is_intraday": freshness["is_intraday"],
                "tile_span": _tile_span(float(meta["weight"])),
            })
        except Exception as exc:  # noqa: BLE001
            items.append({
                **meta,
                "price": None,
                "previous_close": None,
                "change_pct": None,
                "as_of": "",
                "source": "yfinance_intraday_5m",
                "status": "unavailable",
                "is_decision_usable": False,
                "freshness_status": "unknown",
                "age_minutes": None,
                "is_intraday": False,
                "tile_span": _tile_span(float(meta["weight"])),
                "error": str(exc),
            })

    usable_items = [item for item in items if item.get("status") == "ok" and item.get("is_decision_usable")]
    freshness_counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("freshness_status") or "unknown")
        freshness_counts[key] = freshness_counts.get(key, 0) + 1
    latest_as_of = max((str(item.get("as_of")) for item in usable_items if item.get("as_of")), default="")
    stale_count = sum(1 for item in items if not item.get("is_decision_usable"))
    return {
        "items": items,
        "generated_at": now_utc.isoformat(),
        "provider": "yfinance",
        "interval": "5m",
        "universe_version": HEATMAP_UNIVERSE_VERSION,
        "universe_size": len(_EQUITY_HEATMAP_UNIVERSE),
        "batch_size": _EQUITY_HEATMAP_BATCH_SIZE,
        "ok_count": len(usable_items),
        "decision_usable_count": len(usable_items),
        "stale_or_unavailable_count": stale_count,
        "latest_as_of": latest_as_of,
        "freshness_counts": freshness_counts,
        "freshness_policy": "US market hours require fresh or delayed 5-minute intraday data; prior-close/stale symbols are excluded from the rendered heatmap.",
        "warning": (
            f"{stale_count} symbols are excluded from the decision surface because fresh or delayed intraday data was unavailable."
            if stale_count else ""
        ),
    }


@router.get("/equity-heatmap")
async def dashboard_equity_heatmap(force: bool = False) -> dict[str, Any]:
    now = time.time()
    cached = _dashboard_equity_heatmap_cache.get("payload")
    if cached and not force and now - float(_dashboard_equity_heatmap_cache.get("ts") or 0) < _DASHBOARD_EQUITY_HEATMAP_CACHE_TTL_SEC:
        payload = dict(cached)
        payload["cache_hit"] = True
        return payload

    payload = await asyncio.to_thread(_collect_equity_heatmap_snapshot)
    payload["cache_hit"] = False
    _dashboard_equity_heatmap_cache["ts"] = now
    _dashboard_equity_heatmap_cache["payload"] = dict(payload)
    return payload
