"""Google News RSS provider — a key-less news fallback.

Why add this?
-------------
The current news fallback chain is YF → FMP → SEC. When Yahoo is rate-limited
and FMP lacks entitlement (or the user has no key), SEC filings are all that
remains — and those are regulatory, not news-shaped. Google News RSS is
public, requires no auth, and returns human-readable headlines with links
back to primary sources. Adding it as a tertiary provider lets the pipeline
stay informative even in degraded conditions.

Design
------
- Zero new dependencies — we parse the feed with stdlib ``xml.etree`` because
  a new library for one endpoint is overkill.
- Query is scoped with a conservative ``when:{lookback}d`` clause so Google
  returns results from the user's requested window. Falls back to the plain
  ticker query on parse failures.
- Published dates from RSS are in RFC 822; we convert to ISO 8601 so the
  downstream freshness filter treats them the same as other providers.
- The result still flows through ``filter_fresh_documents`` so stale items
  are dropped identically to YF/FMP.
- Defensive: any network/parse error returns an ``empty``/``failed``
  SourceCollectionResult rather than raising, mirroring the other providers.
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from core.utils.data_helpers import build_doc_id, deduplicate_documents, normalize_news_records, unique_text
from core.utils.asset_classifier import classify
from core.utils.logger import get_logger
from pipelines.collect.fmp_news import filter_fresh_documents
from pipelines.collect.models import SourceCollectionResult

logger = get_logger("pipelines.collect.google_news_rss")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HTTP_TIMEOUT_S = 8.0
_FEED_URL = "https://news.google.com/rss/search"
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _to_iso(published: str) -> str:
    """RFC 822 → ISO 8601 in UTC. Falls back to empty string on parse failure."""
    if not published:
        return ""
    try:
        dt = parsedate_to_datetime(published)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def _build_query(ticker: str, lookback_days: int) -> str:
    """Google News supports ``when:Xd`` to scope recency without extra params."""
    try:
        profile = classify(ticker)
    except Exception:
        profile = None
    if getattr(profile, "is_etf", False):
        issuer = str(getattr(profile, "issuer", "") or "").strip()
        terms = [f'"{ticker} ETF"', f'"{ticker} trust"', f'"{ticker} fund"']
        if issuer:
            terms.insert(0, f'"{issuer} {ticker}"')
        if ticker.upper() == "QQQ":
            terms.append('"Nasdaq-100 ETF"')
        base = " OR ".join(terms)
    else:
        base = f'{ticker} stock OR earnings OR company'
    # Cap lookback to 30d — Google News ignores unusually large windows.
    horizon = max(1, min(int(lookback_days), 30))
    return f"{base} when:{horizon}d"


def _normalize_query_override_records(records: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    """Normalize broad dashboard/news-query records without ticker purity gating.

    The regular single-name provider must keep strict identity checks to prevent
    cross-contamination. Dashboard category feeds are different: a valid gold,
    credit-spread, or Bitcoin headline often does not contain GLD/HYG/BTC-USD
    verbatim. This path is intentionally opt-in and used only by callers that
    pass broad query overrides.
    """
    documents: list[dict[str, Any]] = []
    for item in records:
        title = str(item.get("title") or "").strip()
        text = unique_text([
            title,
            str(item.get("text") or "").strip(),
            str(item.get("body") or "").strip(),
        ])
        if not text:
            continue
        published_at = str(item.get("published_at") or "").strip()
        source = str(item.get("source") or "Google News").strip() or "Google News"
        url = str(item.get("url") or "").strip()
        seed = "|".join([symbol, title, published_at, url, text[:200]])
        documents.append({
            "doc_id": build_doc_id(symbol, "news", seed),
            "ticker": symbol,
            "symbol": symbol,
            "doc_type": "news",
            "source": source,
            "published_at": published_at,
            "title": title or f"{symbol} market news",
            "text": text,
            "url": url,
            "admitted_by": "dashboard_query_override",
        })
    return deduplicate_documents(documents)


def collect_news_from_google_rss(
    ticker: str,
    lookback_days: int,
    *,
    limit: int = 20,
    query_override: str | None = None,
    strict_purity: bool = True,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    """Fetch and normalize Google News RSS results for a ticker."""
    started_at = datetime.now()
    query = query_override or _build_query(ticker, lookback_days)
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    url = f"{_FEED_URL}?{urllib.parse.urlencode(params)}"

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_S, headers={"User-Agent": _USER_AGENT}, follow_redirects=True) as client:
            resp = client.get(url)
    except Exception as exc:  # noqa: BLE001
        elapsed = round((datetime.now() - started_at).total_seconds(), 2)
        return (
            SourceCollectionResult("news", "failed", 0, elapsed, f"google_news request error: {exc}"),
            [],
        )

    elapsed = round((datetime.now() - started_at).total_seconds(), 2)
    if resp.status_code != 200:
        return (
            SourceCollectionResult("news", "failed", 0, elapsed, f"google_news HTTP {resp.status_code}"),
            [],
        )

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        return (
            SourceCollectionResult("news", "failed", 0, elapsed, f"google_news XML parse: {exc}"),
            [],
        )

    items = root.findall(".//item")
    if not items:
        return (
            SourceCollectionResult("news", "empty", 0, elapsed, "google_news returned zero items."),
            [],
        )

    records: list[dict[str, Any]] = []
    for item in items[:limit]:
        title = (item.findtext("title") or "").strip()
        raw_desc = item.findtext("description") or ""
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        source_el = item.find("source")
        source_name = (source_el.text.strip() if source_el is not None and source_el.text else "Google News")

        description = _strip_html(raw_desc)
        if not title and not description:
            continue

        records.append({
            "title": title,
            "text": description,
            "body": "",
            "published_at": _to_iso(pub) or pub,
            "source": source_name,
            "url": link,
            "symbol": ticker,
            "company_name": ticker,
        })

    if not records:
        return (
            SourceCollectionResult("news", "empty", 0, elapsed, "google_news items were unusable."),
            [],
        )

    if strict_purity:
        normalized = normalize_news_records(records, ticker, company_name=ticker, source_hint="google_news")
    else:
        normalized = _normalize_query_override_records(records, ticker)
    normalized, freshness_detail = filter_fresh_documents(
        normalized,
        lookback_days,
        now=started_at,
        collected_at=started_at.isoformat(),
    )

    if not normalized:
        detail = freshness_detail or "google_news articles did not survive freshness window."
        return SourceCollectionResult("news", "empty", 0, elapsed, detail), []

    return (
        SourceCollectionResult("news", "ok", len(normalized), elapsed, "Google News RSS collected."),
        normalized,
    )
