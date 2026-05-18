"""FRED (Federal Reserve Economic Data) macro collector.

Role in the stack
-----------------
FRED is our primary macro evidence channel for rate-sensitive assets such as
Treasury ETFs (TLT, IEF), broad bond baskets (BND, AGG), and yield-curve
questions. A FinGPT run that analyzes a bond ETF without rate data is
operating blind, so this provider is treated as a primary macro input when
available.

Why API-based (not scraping)
----------------------------
The public FRED API is free, well-documented, and stable. We only hit two
endpoints:

- ``series/observations`` — time series for a given FRED id.
- ``series`` — human-readable title/metadata for that id.

We synthesize one natural-language document per series so the RAG retriever
treats the data the same way it treats news (embed → retrieve → cite).

Graceful failure
----------------
Like every other provider in this stack, fetch failures degrade to a
``SourceCollectionResult`` with a structured status code. Missing API key →
``credentials_missing``. Rate-limit → ``rate_limited``. Empty response →
``empty``. Nothing raises.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

import httpx

from core.utils.asset_classifier import AssetProfile
from core.utils.data_helpers import build_doc_id
from core.utils.logger import get_logger
from pipelines.collect.models import SourceCollectionResult

logger = get_logger("pipelines.collect.fred")

_FRED_BASE = "https://api.stlouisfed.org/fred"
_HTTP_TIMEOUT_S = 8.0
_MAX_SERIES_PER_RUN = 6
_MAX_OBSERVATIONS_PER_SERIES = 40


# Series bundles mapped by asset-class / ticker. The lists are intentionally
# short — RAG quality drops when we flood the retriever with near-identical
# rate series, so we pick the most decision-relevant ones per asset.
_SERIES_BY_TICKER: dict[str, list[str]] = {
    # Long-duration Treasury ETF — sensitive to long-end yields + Fed path.
    "TLT": ["DGS10", "DGS30", "T10Y2Y", "DFF"],
    "IEF": ["DGS7", "DGS10", "T10Y2Y", "DFF"],
    "SHY": ["DGS2", "DGS1", "DFF", "DFEDTARU"],
    "BND": ["DGS10", "BAMLCC0A0CMTRIV", "DFF"],
    "AGG": ["DGS10", "BAMLCC0A0CMTRIV", "DFF"],
    "HYG": ["BAMLH0A0HYM2", "BAMLH0A0HYM2EY", "DFF"],
    "LQD": ["BAMLC0A0CM", "DGS10", "DFF"],
    "TIP": ["DFII10", "T10YIE", "CPIAUCSL"],
    "GOVT": ["DGS10", "DGS2", "DFF"],
    "MUB": ["MUNIA", "DGS10"],
    "EMB": ["BAMLEMCBPIEY", "DGS10"],
    # Gold / precious metals — real rates + CPI + USD index.
    "GLD": ["DFII10", "CPIAUCSL", "DTWEXBGS"],
    "IAU": ["DFII10", "CPIAUCSL", "DTWEXBGS"],
    "SLV": ["DFII10", "DTWEXBGS"],
    # Broad commodity / oil — WTI spot, USD index, industrial production.
    "USO": ["DCOILWTICO", "DTWEXBGS"],
    "UNG": ["DHHNGSP"],
    "DBC": ["DCOILWTICO", "DTWEXBGS"],
    "PDBC": ["DCOILWTICO", "DTWEXBGS"],
}

_SERIES_BY_CLASS: dict[str, list[str]] = {
    "bond_etf": ["DGS10", "DGS2", "T10Y2Y", "DFF"],
    "commodity_etf": ["DCOILWTICO", "DTWEXBGS", "CPIAUCSL"],
    "forex": ["DTWEXBGS", "DFF"],
    "futures": ["DCOILWTICO", "DTWEXBGS", "DGS10"],
    "crypto": ["DFF", "DTWEXBGS"],
}


def pick_series(profile: AssetProfile) -> list[str]:
    """Return the FRED series ids that are most relevant for ``profile``."""
    explicit = _SERIES_BY_TICKER.get(profile.ticker)
    if explicit:
        return explicit[:_MAX_SERIES_PER_RUN]
    fallback = _SERIES_BY_CLASS.get(profile.asset_class, [])
    return fallback[:_MAX_SERIES_PER_RUN]


def _fetch_json(client: httpx.Client, path: str, params: dict[str, Any]) -> tuple[str, Any]:
    try:
        resp = client.get(f"{_FRED_BASE}/{path}", params=params)
    except httpx.TimeoutException:
        return "timeout", None
    except httpx.HTTPError as exc:
        return "provider_unavailable", str(exc)

    if resp.status_code in (401, 403):
        return "credentials_missing", None
    if resp.status_code == 429:
        return "rate_limited", None
    if resp.status_code == 404:
        return "empty", None
    if resp.status_code >= 500:
        return "provider_unavailable", resp.text
    if resp.status_code != 200:
        return "provider_unavailable", resp.text
    try:
        return "ok", resp.json()
    except ValueError:
        return "provider_unavailable", resp.text


def _observations_within(payload: Any, cutoff: datetime) -> list[tuple[datetime, float]]:
    """Extract (date, value) observations within the lookback cutoff."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("observations") or []
    out: list[tuple[datetime, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_text = str(row.get("date") or "")
        value_text = str(row.get("value") or "")
        if not date_text or not value_text or value_text == ".":
            continue
        try:
            dt = datetime.fromisoformat(date_text)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        try:
            val = float(value_text)
        except ValueError:
            continue
        out.append((dt, val))
    return out[-_MAX_OBSERVATIONS_PER_SERIES:]


def _summarize(series_id: str, title: str, units: str, observations: list[tuple[datetime, float]]) -> tuple[str, str, str]:
    """Build the (title, body, published_at) for a FRED document.

    The body is a short natural-language summary so the LLM can quote it
    directly — we never feed raw time series into the prompt, because the
    retriever would index the numbers as disjoint tokens.
    """
    first_dt, first_val = observations[0]
    last_dt, last_val = observations[-1]
    peak_dt, peak_val = max(observations, key=lambda o: o[1])
    trough_dt, trough_val = min(observations, key=lambda o: o[1])
    change = last_val - first_val
    pct = (change / first_val * 100.0) if first_val else 0.0
    direction = "rose" if change > 0 else ("fell" if change < 0 else "was unchanged")

    doc_title = f"FRED {series_id}: {title}".strip()
    body = (
        f"{title} ({series_id}) {direction} from {first_val:.3f} {units} on "
        f"{first_dt.date().isoformat()} to {last_val:.3f} {units} on "
        f"{last_dt.date().isoformat()}, a change of {change:+.3f} ({pct:+.2f}%). "
        f"During this window the series peaked at {peak_val:.3f} on "
        f"{peak_dt.date().isoformat()} and bottomed at {trough_val:.3f} on "
        f"{trough_dt.date().isoformat()}. Source: Federal Reserve Bank of "
        f"St. Louis (FRED), series {series_id}."
    )
    return doc_title, body, last_dt.isoformat()


def _build_documents(series_docs: Iterable[tuple[str, str, str, str]], profile: AssetProfile) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for series_id, title, body, published_at in series_docs:
        url = f"https://fred.stlouisfed.org/series/{series_id}"
        seed = "|".join([profile.ticker, series_id, published_at, body[:200]])
        doc_id = build_doc_id(profile.ticker, "macro", seed)
        documents.append({
            "doc_id": doc_id,
            "ticker": profile.ticker,
            "symbol": profile.ticker,
            "doc_type": "macro",
            "source": f"FRED:{series_id}",
            "published_at": published_at,
            "title": title,
            "text": body,
            "url": url,
            "admitted_by": "macro_series",
        })
    return documents


def collect_fred_series(
    profile: AssetProfile,
    lookback_days: int,
    fred_api_key: str,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    """Fetch a short bundle of FRED series relevant to ``profile``."""
    started = datetime.now()

    if not fred_api_key:
        return (
            SourceCollectionResult(
                source="macro",
                status="credentials_missing",
                doc_count=0,
                elapsed_s=0.0,
                detail="FRED_API_KEY is missing; FRED macro collection is disabled.",
            ),
            [],
        )

    series_ids = pick_series(profile)
    if not series_ids:
        return (
            SourceCollectionResult(
                source="macro",
                status="empty",
                doc_count=0,
                elapsed_s=0.0,
                detail=f"No FRED series registered for {profile.ticker} "
                       f"(asset_class={profile.asset_class}).",
            ),
            [],
        )

    cutoff = datetime.now() - timedelta(days=max(lookback_days, 30))
    params_base = {"api_key": fred_api_key, "file_type": "json"}

    series_docs: list[tuple[str, str, str, str]] = []
    worst_status: str | None = None

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_S) as client:
            for series_id in series_ids:
                meta_status, meta_payload = _fetch_json(
                    client,
                    "series",
                    {**params_base, "series_id": series_id},
                )
                if meta_status != "ok" or not isinstance(meta_payload, dict):
                    worst_status = worst_status or meta_status
                    continue
                meta_list = meta_payload.get("seriess") or []
                meta = meta_list[0] if meta_list else {}
                title = str(meta.get("title") or series_id)
                units = str(meta.get("units_short") or meta.get("units") or "")

                obs_status, obs_payload = _fetch_json(
                    client,
                    "series/observations",
                    {
                        **params_base,
                        "series_id": series_id,
                        "sort_order": "asc",
                        "observation_start": cutoff.date().isoformat(),
                    },
                )
                if obs_status != "ok":
                    worst_status = worst_status or obs_status
                    continue

                observations = _observations_within(obs_payload, cutoff)
                if not observations:
                    continue
                doc_title, body, published_at = _summarize(series_id, title, units, observations)
                series_docs.append((series_id, doc_title, body, published_at))
    except Exception as exc:  # noqa: BLE001 - keep provider best-effort
        elapsed = round((datetime.now() - started).total_seconds(), 2)
        logger.warning(f"[FRED] unexpected fetch error: {exc}")
        return (
            SourceCollectionResult("macro", "provider_unavailable", 0, elapsed, f"FRED fetch error: {exc}"),
            [],
        )

    elapsed = round((datetime.now() - started).total_seconds(), 2)
    if not series_docs:
        detail = f"FRED returned zero usable series (worst_status={worst_status or 'none'})."
        status = worst_status or "empty"
        if status not in {"credentials_missing", "rate_limited", "timeout", "provider_unavailable"}:
            status = "empty"
        return SourceCollectionResult("macro", status, 0, elapsed, detail), []

    documents = _build_documents(series_docs, profile)
    return (
        SourceCollectionResult(
            "macro",
            "ok",
            len(documents),
            elapsed,
            f"FRED collected {len(documents)} macro series for {profile.ticker}.",
        ),
        documents,
    )
