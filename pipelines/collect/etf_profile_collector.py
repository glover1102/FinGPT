"""ETF issuer profile collector.

Purpose
-------
When the user asks detailed questions about an ETF ("What is the duration of
TLT?", "What sectors does XLK overweight?", "What is JEPI's strategy?"),
news and price data are not enough. The decision-grade context lives on the
issuer's product page (iShares / Vanguard / SPDR / Invesco / ARK / Schwab /
J.P. Morgan / Global X / USCF) — objective information: index/benchmark,
duration, expense ratio, top holdings summary, investment objective.

This module fetches one such page per ETF and turns it into a single RAG
document with ``doc_type="etf_profile"`` so the retriever treats it the same
way as news or macro documents.

Design
------
- **Curated map first, Yahoo fallback second.** The ``ETF_ISSUER_REGISTRY``
  in ``core.utils.asset_classifier`` holds the best primary URL per known
  ETF. Unknown ETFs (the ones we only recognize by heuristic) fall back to
  the Yahoo Finance profile page which at least contains a prose summary.
- **Reuses existing trafilatura-based extractor.** No new dependency. We
  borrow ``fetch_article_body`` from ``openbb_collector`` but do it via a
  local helper with a tighter timeout and larger minimum length because
  ETF product pages are typically content-rich.
- **Hard-capped in time and size.** Product pages can be JS-heavy; the
  collector fast-skips with ``timeout`` when the body is too thin rather
  than let the pipeline hang.
- **Bypass the strict purity check.** The document text (e.g.,
  "iShares 20+ Year Treasury Bond ETF seeks to track...") will not
  necessarily contain the ticker literal, so we use our own lightweight
  normalizer instead of ``normalize_news_records``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from core.utils.asset_classifier import AssetProfile
from core.utils.data_helpers import as_clean_text, build_doc_id
from core.utils.logger import get_logger
from pipelines.collect.models import SourceCollectionResult

logger = get_logger("pipelines.collect.etf_profile")

_HTTP_TIMEOUT_S = 6.0
_MIN_BODY_CHARS = 200
_MAX_BODY_CHARS = 6000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _yahoo_profile_url(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker}/profile"


def _yahoo_info_profile(ticker: str) -> tuple[str, str]:
    """Third-tier fallback: synthesize an ETF profile from ``yfinance.info``.

    Many issuer product pages (SSGA, Vanguard, Schwab) are JS-rendered SPAs
    that return empty when scraped statically. ``yfinance`` piggybacks on
    Yahoo's internal JSON APIs instead, which do expose the ETF summary
    metadata reliably. We convert the structured dict into a short prose
    paragraph so the RAG retriever can embed it just like any other doc.
    """
    try:
        import yfinance as yf
    except ImportError:
        return "", "provider_unavailable"

    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:  # noqa: BLE001
        return "", "provider_unavailable"

    if not isinstance(info, dict) or not info:
        return "", "empty"

    # Names of interest in yfinance's ETF info dict. We pick the fields that
    # matter for RAG grounding and skip pricing noise.
    long_name     = as_clean_text(info.get("longName") or info.get("shortName") or ticker)
    category      = as_clean_text(info.get("category") or info.get("fundFamily") or "")
    family        = as_clean_text(info.get("fundFamily") or "")
    summary       = as_clean_text(info.get("longBusinessSummary") or "")
    total_assets  = info.get("totalAssets")
    expense_ratio = info.get("annualReportExpenseRatio") or info.get("netExpenseRatio")
    yield_ttm     = info.get("yield")
    inception_ts  = info.get("fundInceptionDate")
    nav_price     = info.get("navPrice") or info.get("regularMarketPrice")

    lines: list[str] = [f"{long_name} ({ticker}) -- ETF profile summary."]
    if family and family.lower() not in long_name.lower():
        lines.append(f"Fund family: {family}.")
    if category:
        lines.append(f"Category: {category}.")
    if isinstance(total_assets, (int, float)) and total_assets > 0:
        lines.append(f"Total net assets (approx): {total_assets:,.0f} USD.")
    if isinstance(expense_ratio, (int, float)):
        lines.append(f"Expense ratio: {expense_ratio * 100:.3f}% per year.")
    if isinstance(yield_ttm, (int, float)):
        lines.append(f"Trailing 12-month yield: {yield_ttm * 100:.2f}%.")
    if isinstance(nav_price, (int, float)) and nav_price > 0:
        lines.append(f"Last NAV / market price: {nav_price:.2f} USD.")
    if isinstance(inception_ts, (int, float)) and inception_ts > 0:
        try:
            inception = datetime.utcfromtimestamp(int(inception_ts)).date().isoformat()
            lines.append(f"Fund inception: {inception}.")
        except (ValueError, OSError):
            pass
    if summary:
        lines.append("Objective: " + summary)

    body = as_clean_text(" ".join(lines))
    if len(body) < _MIN_BODY_CHARS:
        # yfinance sometimes returns only {symbol, quoteType}; reject thin payloads
        # so the pipeline doesn't index a near-empty document.
        return "", "empty"
    if len(body) > _MAX_BODY_CHARS:
        body = body[:_MAX_BODY_CHARS].rstrip() + " ..."
    return body, "ok"


def _fetch_body(url: str) -> tuple[str, str]:
    """Return (body_text, status) for a product-page URL.

    ``status`` is one of ``ok / empty / timeout / provider_unavailable``.
    Any transient failure is swallowed; downstream callers rely on the
    status code rather than on exceptions.
    """
    try:
        import trafilatura  # lazy to match the codebase's optional-extras pattern
    except ImportError:
        return "", "provider_unavailable"

    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_S, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
    except httpx.TimeoutException:
        return "", "timeout"
    except httpx.HTTPError as exc:
        logger.debug(f"[ETF_PROFILE] fetch error for {url}: {exc}")
        return "", "provider_unavailable"

    if resp.status_code == 429:
        return "", "rate_limited"
    if resp.status_code >= 400:
        return "", "provider_unavailable"

    try:
        extracted = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[ETF_PROFILE] trafilatura failure for {url}: {exc}")
        return "", "provider_unavailable"

    if not extracted:
        return "", "empty"
    cleaned = as_clean_text(extracted)
    if len(cleaned) < _MIN_BODY_CHARS:
        return "", "empty"
    if len(cleaned) > _MAX_BODY_CHARS:
        cleaned = cleaned[:_MAX_BODY_CHARS].rstrip() + " ..."
    return cleaned, "ok"


def _build_document(profile: AssetProfile, url: str, issuer: str, body: str) -> dict[str, Any]:
    issuer_label = issuer or "ETF Issuer"
    title = f"{profile.ticker} — {issuer_label} product profile"
    seed = "|".join([profile.ticker, url, body[:200]])
    doc_id = build_doc_id(profile.ticker, "etf_profile", seed)
    return {
        "doc_id": doc_id,
        "ticker": profile.ticker,
        "symbol": profile.ticker,
        "doc_type": "etf_profile",
        "source": f"issuer:{issuer_label}" if issuer else "issuer:yahoo",
        "published_at": datetime.now().isoformat(),
        "title": title,
        "text": body,
        "url": url,
        "admitted_by": "etf_profile",
    }


def collect_etf_profile(
    profile: AssetProfile,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    """Fetch the issuer product page for an ETF.

    Returns ``(skipped, [])`` silently when the ticker is not an ETF so the
    caller can append unconditionally without branching.
    """
    started = datetime.now()

    if not profile.is_etf:
        return (
            SourceCollectionResult(
                source="etf_profile",
                status="skipped",
                doc_count=0,
                elapsed_s=0.0,
                detail=f"ticker {profile.ticker} is not registered as an ETF.",
            ),
            [],
        )

    # Tier 1 — curated issuer URL via trafilatura.
    primary_url = profile.issuer_url
    issuer_label = profile.issuer

    body = ""
    status = "empty"
    if primary_url:
        body, status = _fetch_body(primary_url)

    # Tier 2 — Yahoo Finance profile page via trafilatura.
    if status != "ok":
        fallback_url = _yahoo_profile_url(profile.ticker)
        if fallback_url != primary_url:
            fb_body, fb_status = _fetch_body(fallback_url)
            if fb_status == "ok":
                body = fb_body
                status = "ok"
                primary_url = fallback_url
                issuer_label = issuer_label or "Yahoo Finance"

    # Tier 3 — yfinance.info JSON. Handles JS-rendered SPA issuer pages
    # (SSGA / Vanguard / Schwab) that produce empty trafilatura extracts.
    if status != "ok":
        yf_body, yf_status = _yahoo_info_profile(profile.ticker)
        if yf_status == "ok":
            body = yf_body
            status = "ok"
            primary_url = primary_url or _yahoo_profile_url(profile.ticker)
            issuer_label = issuer_label or "Yahoo Finance"

    elapsed = round((datetime.now() - started).total_seconds(), 2)

    if status != "ok" or not body:
        detail = f"etf_profile fetch status={status} for {profile.ticker}."
        return (
            SourceCollectionResult("etf_profile", status or "empty", 0, elapsed, detail),
            [],
        )

    document = _build_document(profile, primary_url, issuer_label, body)
    return (
        SourceCollectionResult(
            source="etf_profile",
            status="ok",
            doc_count=1,
            elapsed_s=elapsed,
            detail=f"ETF profile fetched for {profile.ticker} ({issuer_label or 'yahoo'}).",
        ),
        [document],
    )
