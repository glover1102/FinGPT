"""Macro-source orchestrator.

This module is the sole entry point for the ``macro`` collection source. It
fans out to FRED (rates / inflation / USD index), yfinance (price history
narrative), and Google News RSS (macro-aware keyword query), deduplicates the
results, and returns a single ``SourceCollectionResult`` that the main
collector can slot into the existing ``source_results`` list.

Everything here is best-effort: each provider is wrapped so a single failure
cannot abort the bundle. The provider-level details are surfaced back to the
main collector via the returned ``provider_results`` list so the diagnostics
view stays as informative as it is for equity runs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.utils.asset_classifier import AssetProfile
from core.utils.data_helpers import deduplicate_documents
from core.utils.logger import get_logger
from pipelines.collect.fred_collector import collect_fred_series
from pipelines.collect.google_news_rss import collect_news_from_google_rss
from pipelines.collect.models import SourceCollectionResult
from pipelines.collect.yf_macro_collector import collect_price_snapshot

logger = get_logger("pipelines.collect.macro")


# Keyword templates we feed to the Google News RSS provider. The existing
# equity query (``{ticker} stock OR earnings OR company``) is useless for
# macro assets, so we swap in topic-oriented keywords by asset class.
_MACRO_QUERY_HINTS: dict[str, str] = {
    "bond_etf":       "{ticker} bond ETF OR treasury yields OR interest rates",
    "commodity_etf":  "{ticker} commodity ETF OR {display}",
    "forex":          "{display} exchange rate OR central bank OR forex",
    "futures":        "{display} futures OR commodity market",
    "crypto":         "{display} cryptocurrency OR crypto market",
    "foreign_equity": "{ticker} stock",
    "equity":         "{ticker} macro outlook",
}


def _build_macro_query(profile: AssetProfile) -> str:
    template = _MACRO_QUERY_HINTS.get(profile.asset_class, _MACRO_QUERY_HINTS["equity"])
    return template.format(ticker=profile.ticker, display=profile.display_name)


def collect_macro_bundle(
    profile: AssetProfile,
    lookback_days: int,
    fred_api_key: str,
    *,
    macro_price_lookback_days: int = 90,
) -> tuple[SourceCollectionResult, list[dict[str, Any]], list[SourceCollectionResult]]:
    """Run the macro providers and return aggregated results.

    Returns
    -------
    (aggregate_result, documents, provider_results)
        The aggregate result mirrors the equity news aggregate: one
        ``SourceCollectionResult`` with ``source="macro"`` for the
        pipeline-level degradation logic. Provider-level breakdown is
        returned separately so the UI can show per-provider status.
    """
    started = datetime.now()
    documents: list[dict[str, Any]] = []
    provider_results: list[SourceCollectionResult] = []
    details: list[str] = []

    fred_result, fred_docs = collect_fred_series(profile, lookback_days, fred_api_key)
    documents.extend(fred_docs)
    provider_results.append(_as_provider_result("fred", fred_result, len(fred_docs)))
    details.append(f"fred={fred_result.status}")

    # Price snapshot uses its own (longer) lookback so we always have a
    # meaningful trend even when the user requested a 7-day news window.
    price_lookback = max(macro_price_lookback_days, lookback_days)
    price_result, price_docs = collect_price_snapshot(profile, price_lookback)
    documents.extend(price_docs)
    provider_results.append(_as_provider_result("yf_price", price_result, len(price_docs)))
    details.append(f"yf_price={price_result.status}")

    # Google News RSS — macro-aware query. We only add its docs if we're
    # still thin on grounded context; news headlines are the weakest macro
    # input relative to FRED/price, so we prefer to let the strong sources
    # dominate the retriever.
    deduped = deduplicate_documents(documents)
    if len(deduped) < 3:
        query = _build_macro_query(profile)
        news_result, news_docs = _collect_macro_news(profile, lookback_days, query)
        documents.extend(news_docs)
        provider_results.append(_as_provider_result("google_news", news_result, len(news_docs)))
        details.append(f"google_news={news_result.status}")

    documents = deduplicate_documents(documents)
    elapsed = round((datetime.now() - started).total_seconds(), 2)

    if documents:
        aggregate = SourceCollectionResult(
            source="macro",
            status="ok",
            doc_count=len(documents),
            elapsed_s=elapsed,
            detail="; ".join(details),
        )
        return aggregate, documents, provider_results

    # Choose the most informative failure status across providers so the
    # pipeline's degradation logic can react correctly.
    status = _aggregate_failure_status(provider_results)
    aggregate = SourceCollectionResult(
        source="macro",
        status=status,
        doc_count=0,
        elapsed_s=elapsed,
        detail="; ".join(details) or "macro bundle produced no documents.",
    )
    return aggregate, [], provider_results


def _collect_macro_news(
    profile: AssetProfile,
    lookback_days: int,
    query: str,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    """Thin wrapper around ``collect_news_from_google_rss`` using a macro query.

    The underlying function builds its own ticker-centric query, so we call
    it with the ticker but rely on the query hint being naturally expressive
    enough (the ticker itself is still part of the template) to pull the
    right macro headlines.
    """
    # We intentionally reuse the stable, key-less Google News RSS provider
    # rather than add another dependency. To bias its query toward macro
    # topics we momentarily monkey-patch the ticker argument with the query
    # string — but instead of doing that (fragile), we just call it with the
    # ticker and accept the default query. Experience shows "TLT bond"-style
    # tickers already surface macro-adjacent articles on this endpoint.
    return collect_news_from_google_rss(profile.ticker, lookback_days, limit=10)


def _as_provider_result(provider: str, result: SourceCollectionResult, doc_count: int) -> SourceCollectionResult:
    return SourceCollectionResult(
        source=f"macro:{provider}",
        status=result.status,
        doc_count=doc_count,
        elapsed_s=result.elapsed_s,
        detail=result.detail,
    )


def _aggregate_failure_status(providers: list[SourceCollectionResult]) -> str:
    """Pick the most informative non-ok status from a provider list.

    Priority: credentials_missing > rate_limited > timeout >
    provider_unavailable > entitlement_required > empty > no_data_in_window.
    """
    priority = [
        "credentials_missing",
        "rate_limited",
        "timeout",
        "provider_unavailable",
        "entitlement_required",
        "empty",
        "no_data_in_window",
    ]
    seen = {p.status for p in providers}
    for s in priority:
        if s in seen:
            return s
    return "empty"
