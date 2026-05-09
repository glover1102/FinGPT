from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta
from typing import Any

import httpx

from core.config.settings import load_settings
from core.schemas.request import DISABLED_COLLECTION_SOURCES
from core.utils.asset_classifier import classify
from core.utils.data_helpers import build_doc_id, deduplicate_documents, extract_records, normalize_news_records, write_documents
from core.utils.logger import get_logger
from core.utils.technical_indicators import (
    compute_technical_metrics_from_history,
    fetch_yfinance_history,
    technical_metrics_document_text,
)
from pipelines.collect.cache import get_cache
from pipelines.collect.alpha_vantage_news import collect_news_from_alpha_vantage
from pipelines.collect.etf_profile_collector import collect_etf_profile
from pipelines.collect.fmp_news import collect_stock_news_from_fmp, filter_fresh_documents
from pipelines.collect.google_news_rss import collect_news_from_google_rss
from pipelines.collect.fundamentals_card import collect_fundamentals_card, fundamentals_card_to_retrieval_item
from pipelines.collect.macro_collector import collect_macro_bundle
from pipelines.collect.sec_filings import collect_sec_filings_as_news
from pipelines.collect.fmp_transcripts import collect_transcripts_from_fmp
from pipelines.collect.models import CollectionOutcome, SourceCollectionResult

logger = get_logger("pipelines.collect")

_NEWS_FEED_TIMEOUT_S = 10.0
_NEWS_ENRICH_TIMEOUT_S = 3.0
_NEWS_ENRICH_BUDGET_S = 12.0
_NEWS_ENRICH_MAX_ARTICLES = 5
_NEWS_ENRICH_WORKERS = 3
_NEWS_MIN_DOC_THRESHOLD = 3
_NEWS_PROVIDER_ALIASES = {
    "yf": "yfinance",
    "yahoo": "yfinance",
    "yfinance": "yfinance",
    "sec": "sec_filings",
    "edgar": "sec_filings",
    "sec_filings": "sec_filings",
    "google": "google_news_rss",
    "google_news": "google_news_rss",
    "google_news_rss": "google_news_rss",
    "alpha": "alpha_vantage_news",
    "alpha_vantage": "alpha_vantage_news",
    "alpha_vantage_news": "alpha_vantage_news",
    "openbb": "openbb_news",
    "openbb_news": "openbb_news",
    "fmp": "fmp_stock_news",
    "fmp_stock_news": "fmp_stock_news",
}
_DEFAULT_NEWS_PROVIDER_ORDER = [
    "yfinance",
    "sec_filings",
    "google_news_rss",
    "openbb_news",
    "alpha_vantage_news",
    "fmp_stock_news",
]
_NON_DEGRADED_STATUSES = {"ok", "disabled", "no_data_in_window", "skipped"}


def fetch_article_body(url: str, timeout: float = _NEWS_ENRICH_TIMEOUT_S) -> str:
    """Fetch and extract the main body text of an article, stripping boilerplate."""
    if not url:
        return ""
    try:
        import trafilatura

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                extract = trafilatura.extract(resp.text)
                if extract and len(extract) > 250:
                    return str(extract)
    except Exception:
        return ""
    return ""


def _run_with_timeout(func, *args, timeout_s: float):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, *args)
    try:
        return future.result(timeout=timeout_s)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _fetch_yfinance_feed(symbol: str) -> list[dict[str, Any]]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(f"[YF News] yfinance not installed: {exc}") from exc

    try:
        ticker_obj = yf.Ticker(symbol)
        raw = ticker_obj.news
        company_name = ticker_obj.info.get("longName", symbol)
    except Exception as exc:
        raise ConnectionError(f"[YF News] yfinance fetch failed for {symbol}: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError(f"[YF News] Unexpected payload type from yfinance: {type(raw)}")

    records: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, dict):
            continue
        title = content.get("title", "")
        summary = content.get("summary", content.get("description", ""))
        if not title and not summary:
            continue

        canonical = content.get("canonicalUrl") or content.get("clickThroughUrl")
        url = canonical.get("url", "") if isinstance(canonical, dict) else ""
        provider_info = content.get("provider", {})
        source = provider_info.get("displayName", "Yahoo Finance") if isinstance(provider_info, dict) else "Yahoo Finance"

        records.append(
            {
                "title": title,
                "text": summary,
                "body": "",
                "published_at": content.get("pubDate", content.get("displayTime", "")),
                "source": source,
                "url": url,
                "symbol": symbol,
                "company_name": company_name,
            }
        )
    return records


def _enrich_news_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return records

    candidates = [(index, record["url"]) for index, record in enumerate(records[:_NEWS_ENRICH_MAX_ARTICLES]) if record.get("url")]
    if not candidates:
        return records

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=_NEWS_ENRICH_WORKERS)
    future_map = {executor.submit(fetch_article_body, url, _NEWS_ENRICH_TIMEOUT_S): index for index, url in candidates}
    try:
        done, _ = concurrent.futures.wait(future_map.keys(), timeout=_NEWS_ENRICH_BUDGET_S)
        for future in done:
            index = future_map[future]
            try:
                body = future.result()
            except Exception:
                body = ""
            if body:
                records[index]["body"] = body
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return records


def _provider_result(provider: str, result: SourceCollectionResult, doc_count: int) -> SourceCollectionResult:
    return SourceCollectionResult(
        source=f"news:{provider}",
        status=result.status,
        doc_count=doc_count,
        elapsed_s=result.elapsed_s,
        detail=result.detail,
    )


def _disabled_news_result(detail: str) -> SourceCollectionResult:
    return SourceCollectionResult("news", "disabled", 0, 0.0, detail)


def _parse_news_provider_order(raw: str | None) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        alias = _NEWS_PROVIDER_ALIASES.get(part.strip().lower())
        if alias and alias not in seen:
            seen.add(alias)
            order.append(alias)
    if order:
        return order
    for provider in _DEFAULT_NEWS_PROVIDER_ORDER:
        if provider not in seen:
            order.append(provider)
    return order


def _settings_flag(settings: Any, name: str, default: bool = False) -> bool:
    return bool(getattr(settings, name, default))


def _collect_openbb_news_source(
    ticker: str,
    lookback_days: int,
    *,
    enabled: bool,
    limit: int = 20,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    started_at = datetime.now()
    if not enabled:
        return (
            _disabled_news_result(
                "OpenBB news runtime is disabled by OPENBB_NEWS_ENABLED=false; "
                "run scripts/check_openbb_compat.py before enabling it."
            ),
            [],
        )

    try:
        from openbb import obb

        raw = _run_with_timeout(
            lambda: obb.news.company(symbol=ticker, limit=limit),
            timeout_s=_NEWS_FEED_TIMEOUT_S,
        )
        records = extract_records(raw)
    except concurrent.futures.TimeoutError:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return (
            SourceCollectionResult("news", "timeout", 0, elapsed_s, "OpenBB news.company timed out."),
            [],
        )
    except Exception as exc:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return (
            SourceCollectionResult("news", "provider_unavailable", 0, elapsed_s, f"OpenBB news.company unavailable: {exc}"),
            [],
        )

    normalized = normalize_news_records(records, ticker, company_name=ticker, source_hint="openbb_news")
    normalized, freshness_detail = filter_fresh_documents(
        normalized,
        lookback_days,
        now=started_at,
        collected_at=started_at.isoformat(),
    )
    elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)

    if not normalized:
        detail = freshness_detail or "OpenBB news.company returned zero usable records."
        return SourceCollectionResult("news", "empty", 0, elapsed_s, detail), []

    return SourceCollectionResult("news", "ok", len(normalized), elapsed_s, "OpenBB news collected."), normalized


def _collect_yfinance_news_source(ticker: str, lookback_days: int) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    started_at = datetime.now()

    try:
        records = _run_with_timeout(_fetch_yfinance_feed, ticker, timeout_s=_NEWS_FEED_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return (
            SourceCollectionResult("news", "timeout", 0, elapsed_s, "Yahoo Finance feed metadata timed out."),
            [],
        )
    except Exception as exc:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return (
            SourceCollectionResult("news", "failed", 0, elapsed_s, str(exc)),
            [],
        )

    if not records:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return (
            SourceCollectionResult("news", "empty", 0, elapsed_s, "Yahoo Finance returned zero articles."),
            [],
        )

    records = _enrich_news_records(records)
    from core.utils.data_helpers import normalize_news_records

    company_name = records[0].get("company_name", ticker) if records else ticker
    normalized = normalize_news_records(records, ticker, company_name=company_name, source_hint="yahoo_finance")
    normalized, freshness_detail = filter_fresh_documents(
        normalized,
        lookback_days,
        now=started_at,
        collected_at=started_at.isoformat(),
    )
    elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)

    if not normalized:
        detail = freshness_detail or "Yahoo Finance returned articles, but none survived normalization."
        return (
            SourceCollectionResult("news", "empty", 0, elapsed_s, detail),
            [],
        )

    return (
        SourceCollectionResult("news", "ok", len(normalized), elapsed_s, "Yahoo Finance news collected."),
        normalized,
    )


def _collect_news_source(
    ticker: str,
    lookback_days: int,
    settings: Any | None = None,
    *,
    fmp_api_key: str | None = None,
    sec_user_agent: str | None = None,
) -> tuple[SourceCollectionResult, list[dict[str, Any]], list[SourceCollectionResult]]:
    settings = settings or load_settings()
    fmp_key = settings.fmp_api_key if fmp_api_key is None else fmp_api_key
    sec_agent = settings.sec_user_agent if sec_user_agent is None else sec_user_agent
    provider_order = _parse_news_provider_order(getattr(settings, "data_provider_priority", ""))
    alpha_vantage_enabled = _settings_flag(settings, "alpha_vantage_enabled", False)
    alpha_vantage_key = str(getattr(settings, "alpha_vantage_api_key", "") or "")
    fmp_enabled = _settings_flag(settings, "fmp_enabled", False)
    openbb_news_enabled = _settings_flag(settings, "openbb_enabled", True) and _settings_flag(settings, "openbb_news_enabled", False)

    documents: list[dict[str, Any]] = []
    provider_results: list[SourceCollectionResult] = []
    detail_parts: list[str] = []

    for provider in provider_order:
        if len(deduplicate_documents(documents)) >= _NEWS_MIN_DOC_THRESHOLD:
            break

        if provider == "yfinance":
            provider_result, provider_documents = _collect_yfinance_news_source(ticker, lookback_days)
        elif provider == "sec_filings":
            provider_result, provider_documents = collect_sec_filings_as_news(
                ticker,
                lookback_days,
                sec_agent,
                limit=5,
            )
        elif provider == "google_news_rss":
            provider_result, provider_documents = collect_news_from_google_rss(
                ticker,
                lookback_days,
                limit=20,
            )
        elif provider == "alpha_vantage_news":
            if not alpha_vantage_enabled:
                provider_result, provider_documents = (
                    _disabled_news_result("Alpha Vantage news disabled by ALPHA_VANTAGE_ENABLED=false."),
                    [],
                )
            elif not alpha_vantage_key:
                provider_result, provider_documents = (
                    _disabled_news_result("ALPHA_VANTAGE_API_KEY is missing; Alpha Vantage news skipped."),
                    [],
                )
            else:
                provider_result, provider_documents = collect_news_from_alpha_vantage(
                    ticker,
                    lookback_days,
                    alpha_vantage_key,
                    limit=20,
                )
        elif provider == "openbb_news":
            provider_result, provider_documents = _collect_openbb_news_source(
                ticker,
                lookback_days,
                enabled=openbb_news_enabled,
                limit=20,
            )
        elif provider == "fmp_stock_news":
            if not fmp_enabled:
                provider_result, provider_documents = (
                    _disabled_news_result("FMP stock news disabled by FMP_ENABLED=false; provider is auxiliary."),
                    [],
                )
            elif not fmp_key:
                provider_result, provider_documents = (
                    _disabled_news_result("FMP_API_KEY is missing; auxiliary FMP stock news skipped."),
                    [],
                )
            else:
                provider_result, provider_documents = collect_stock_news_from_fmp(
                    ticker,
                    lookback_days,
                    fmp_key,
                    limit=20,
                )
        else:
            continue

        documents.extend(provider_documents)
        provider_results.append(_provider_result(provider, provider_result, len(provider_documents)))
        detail_parts.append(f"{provider}={provider_result.status}")

    if documents:
        documents = deduplicate_documents(documents)
        result = SourceCollectionResult(
            source="news",
            status="ok",
            doc_count=len(documents),
            elapsed_s=round(sum(provider.elapsed_s for provider in provider_results), 2),
            detail="; ".join(detail_parts),
        )
        return result, documents, provider_results

    status = next(
        (
            provider.status
            for provider in provider_results
            if provider.status not in {"disabled", "skipped"}
        ),
        "empty",
    )
    result = SourceCollectionResult(
        source="news",
        status=status,
        doc_count=0,
        elapsed_s=round(sum(provider.elapsed_s for provider in provider_results), 2),
        detail="; ".join(detail_parts),
    )
    return result, [], provider_results


def _collect_technical_snapshot_source(ticker: str, lookback_days: int) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    started_at = datetime.now()
    try:
        history = _run_with_timeout(fetch_yfinance_history, ticker, max(lookback_days, 260), timeout_s=8.0)
        metrics = compute_technical_metrics_from_history(history, ticker)
    except concurrent.futures.TimeoutError:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("macro", "timeout", 0, elapsed_s, "yfinance technical snapshot timed out."), []
    except Exception as exc:  # noqa: BLE001
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("macro", "failed", 0, elapsed_s, f"yfinance technical snapshot failed: {exc}"), []

    if not metrics:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("macro", "empty", 0, elapsed_s, "No usable price history for technical indicators."), []

    as_of = str(metrics[0].get("as_of") or datetime.now().date().isoformat())
    seed = "|".join([ticker.upper(), "technical", as_of, ";".join(f"{m.get('name')}={m.get('value')}" for m in metrics)])
    doc_id = build_doc_id(ticker.upper(), "technical", seed)
    metrics = [{**metric, "evidence_doc_ids": [doc_id]} for metric in metrics]
    document = {
        "doc_id": doc_id,
        "ticker": ticker.upper(),
        "symbol": ticker.upper(),
        "doc_type": "technical_snapshot",
        "source": "yfinance:technical",
        "published_at": as_of,
        "title": f"{ticker.upper()} technical indicator snapshot",
        "text": technical_metrics_document_text(ticker, metrics),
        "url": "",
        "asset_class": "technical",
        "bucket": "market_structure",
        "collected_at": datetime.now().isoformat(),
    }
    elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
    return SourceCollectionResult("macro", "ok", 1, elapsed_s, "yfinance technical indicators collected."), [document]


def _collect_fundamentals_source(ticker: str, settings: Any | None = None) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    settings = settings or load_settings()
    started_at = datetime.now()
    try:
        card = collect_fundamentals_card(
            ticker,
            timeout_s=float(getattr(settings, "fundamentals_card_timeout_s", 5.0) or 5.0),
        )
    except concurrent.futures.TimeoutError:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("fundamentals", "timeout", 0, elapsed_s, "fundamentals snapshot timed out."), []
    except Exception as exc:  # noqa: BLE001
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("fundamentals", "failed", 0, elapsed_s, f"fundamentals snapshot failed: {exc}"), []

    item = fundamentals_card_to_retrieval_item(card)
    if item is None:
        elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("fundamentals", "empty", 0, elapsed_s, "No fundamentals snapshot was available."), []

    metadata = dict(item.metadata or {})
    doc_id = str(metadata.get("doc_id") or build_doc_id(ticker.upper(), "fundamentals", str(item.date or "")))
    document = {
        "doc_id": doc_id,
        "ticker": ticker.upper(),
        "symbol": ticker.upper(),
        "doc_type": "fundamentals_snapshot",
        "source": "yfinance:fundamentals",
        "published_at": item.date or datetime.now().date().isoformat(),
        "title": item.title or f"{ticker.upper()} fundamentals snapshot",
        "text": item.chunk,
        "url": "",
        "asset_class": "fundamentals",
        "bucket": "market_structure",
        "collected_at": datetime.now().isoformat(),
        "retrieval_mode": metadata.get("retrieval_mode", "deterministic_provider_snapshot"),
    }
    elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
    return SourceCollectionResult("fundamentals", "ok", 1, elapsed_s, "yfinance fundamentals snapshot collected."), [document]


def _collect_filings_source(ticker: str, lookback_days: int, settings: Any | None = None) -> tuple[SourceCollectionResult, list[dict[str, Any]], SourceCollectionResult]:
    settings = settings or load_settings()
    result, documents = collect_sec_filings_as_news(
        ticker,
        lookback_days,
        getattr(settings, "sec_user_agent", None),
        limit=10,
    )
    filing_result = SourceCollectionResult(
        source="filings",
        status=result.status,
        doc_count=len(documents),
        elapsed_s=result.elapsed_s,
        detail=result.detail,
    )
    provider_result = SourceCollectionResult(
        source="filings:sec_filings",
        status=result.status,
        doc_count=len(documents),
        elapsed_s=result.elapsed_s,
        detail=result.detail,
    )
    return filing_result, documents, provider_result


def _build_summary_detail(source_results: list[SourceCollectionResult]) -> str:
    failing = [result for result in source_results if result.status not in _NON_DEGRADED_STATUSES]
    if not failing:
        return ""
    details = "; ".join(f"{result.source}={result.status}" for result in failing)
    return f"collection degraded: {details}"


def _normalize_requested_sources(sources: list[str] | None) -> list[str]:
    if sources is None:
        sources = ["news", "transcript"]
    normalized: list[str] = []
    seen: set[str] = set()
    for source in sources:
        cleaned = str(source).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized or ["news", "transcript"]


def collect_data(ticker: str, sources: list[str] | None, lookback_days: int) -> CollectionOutcome:
    logger.info(f"Collecting data for {ticker} from {sources} over {lookback_days} days.")
    settings = load_settings()
    profile = classify(ticker)
    normalized_sources = _normalize_requested_sources(sources)
    logger.info(
        "[COLLECT_PROFILE] ticker=%s asset_class=%s equity=%s transcripts=%s macro=%s",
        profile.ticker,
        profile.asset_class,
        profile.supports_equity_sources,
        profile.supports_transcripts,
        profile.supports_macro,
    )

    # Cache lookup — avoids re-hitting rate-limited external APIs when the same
    # (ticker, sources, lookback) is re-run within the TTL window.
    cache = get_cache(settings)
    cache_key = cache.make_key(ticker, normalized_sources, lookback_days)
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info(
            "[COLLECT_CACHE_HIT] ticker=%s sources=%s lookback=%d age=%.1fs docs=%d",
            ticker, normalized_sources, lookback_days, cached.cache_age_s, len(cached.documents),
        )
        return cached

    run_started_at = datetime.now()
    freshness_cutoff = (run_started_at - timedelta(days=lookback_days)).isoformat()

    documents: list[dict[str, Any]] = []
    source_results: list[SourceCollectionResult] = []
    provider_results: list[SourceCollectionResult] = []

    for source in normalized_sources:
        provider_results_before = len(provider_results)
        if source == "news":
            if not profile.supports_equity_sources and not profile.supports_macro:
                result = SourceCollectionResult(
                    source="news",
                    status="skipped",
                    doc_count=0,
                    elapsed_s=0.0,
                    detail=f"news source not applicable to asset_class={profile.asset_class}.",
                )
                source_documents = []
            elif not profile.supports_equity_sources and profile.supports_macro:
                # For FX/futures/crypto we intentionally steer 'news' to the
                # macro bundle so the user doesn't have to know to request
                # the 'macro' source explicitly. This keeps the existing CLI
                # defaults (news + transcript) functional for non-equity.
                macro_result, source_documents, macro_provider_results = collect_macro_bundle(
                    profile,
                    lookback_days,
                    settings.fred_api_key,
                    macro_price_lookback_days=settings.macro_price_lookback_days,
                )
                result = SourceCollectionResult(
                    source="news",
                    status=macro_result.status,
                    doc_count=macro_result.doc_count,
                    elapsed_s=macro_result.elapsed_s,
                    detail=f"redirected_to_macro: {macro_result.detail}",
                )
                provider_results.extend(macro_provider_results)
            else:
                result, source_documents, source_provider_results = _collect_news_source(
                    ticker,
                    lookback_days,
                    settings=settings,
                )
                provider_results.extend(source_provider_results)
        elif source == "transcript":
            if not profile.supports_transcripts:
                result = SourceCollectionResult(
                    source="transcript",
                    status="skipped",
                    doc_count=0,
                    elapsed_s=0.0,
                    detail=f"transcript source not applicable to asset_class={profile.asset_class}.",
                )
                source_documents = []
            else:
                transcript_policy = str(getattr(settings, "transcript_provider", "fmp_optional") or "").strip().lower()
                fmp_transcripts_enabled = (
                    transcript_policy in {"fmp", "fmp_optional"}
                    and bool(getattr(settings, "fmp_enabled", False))
                    and bool(settings.fmp_api_key)
                )
                if fmp_transcripts_enabled:
                    result, source_documents = collect_transcripts_from_fmp(ticker, lookback_days, settings.fmp_api_key)
                else:
                    result = SourceCollectionResult(
                        source="transcript",
                        status="disabled",
                        doc_count=0,
                        elapsed_s=0.0,
                        detail=(
                            "FMP transcript collection disabled. Set FMP_ENABLED=true, "
                            "TRANSCRIPT_PROVIDER=fmp_optional, and FMP_API_KEY to enable the auxiliary provider."
                        ),
                    )
                    source_documents = []
                provider_results.append(
                    SourceCollectionResult(
                        source="transcript:fmp",
                        status=result.status,
                        doc_count=len(source_documents),
                        elapsed_s=result.elapsed_s,
                        detail=result.detail,
                    )
                )
        elif source == "fundamentals":
            if not profile.supports_equity_sources:
                result = SourceCollectionResult(
                    source="fundamentals",
                    status="skipped",
                    doc_count=0,
                    elapsed_s=0.0,
                    detail=f"fundamentals source not applicable to asset_class={profile.asset_class}.",
                )
                source_documents = []
            else:
                result, source_documents = _collect_fundamentals_source(ticker, settings=settings)
                provider_results.append(
                    SourceCollectionResult(
                        source="fundamentals:yfinance",
                        status=result.status,
                        doc_count=len(source_documents),
                        elapsed_s=result.elapsed_s,
                        detail=result.detail,
                    )
                )
        elif source == "filings":
            if not profile.supports_equity_sources:
                result = SourceCollectionResult(
                    source="filings",
                    status="skipped",
                    doc_count=0,
                    elapsed_s=0.0,
                    detail=f"filings source not applicable to asset_class={profile.asset_class}.",
                )
                source_documents = []
            else:
                result, source_documents, provider_result = _collect_filings_source(ticker, lookback_days, settings=settings)
                provider_results.append(provider_result)
        elif source == "macro":
            if not profile.supports_macro:
                if profile.supports_equity_sources:
                    result, source_documents = _collect_technical_snapshot_source(ticker, lookback_days)
                    provider_results.append(
                        SourceCollectionResult(
                            source="macro:yfinance_technical",
                            status=result.status,
                            doc_count=result.doc_count,
                            elapsed_s=result.elapsed_s,
                            detail=result.detail,
                        )
                    )
                else:
                    result = SourceCollectionResult(
                        source="macro",
                        status="skipped",
                        doc_count=0,
                        elapsed_s=0.0,
                        detail=f"macro source not applicable to asset_class={profile.asset_class}.",
                    )
                    source_documents = []
            else:
                macro_result, source_documents, macro_provider_results = collect_macro_bundle(
                    profile,
                    lookback_days,
                    settings.fred_api_key,
                    macro_price_lookback_days=settings.macro_price_lookback_days,
                )
                provider_results.extend(macro_provider_results)
                tech_result, tech_documents = _collect_technical_snapshot_source(ticker, lookback_days)
                if tech_result.status == "ok":
                    source_documents.extend(tech_documents)
                provider_results.append(
                    SourceCollectionResult(
                        source="macro:yfinance_technical",
                        status=tech_result.status,
                        doc_count=tech_result.doc_count,
                        elapsed_s=tech_result.elapsed_s,
                        detail=tech_result.detail,
                    )
                )
                combined_docs = macro_result.doc_count + (tech_result.doc_count if tech_result.status == "ok" else 0)
                combined_status = macro_result.status
                if macro_result.status in {"empty", "failed", "timeout", "credentials_missing"} and tech_result.status == "ok":
                    combined_status = "ok"
                result = SourceCollectionResult(
                    source="macro",
                    status=combined_status,
                    doc_count=combined_docs,
                    elapsed_s=round(float(macro_result.elapsed_s or 0.0) + float(tech_result.elapsed_s or 0.0), 2),
                    detail=f"{macro_result.detail}; technical={tech_result.status}",
                )
        elif source in DISABLED_COLLECTION_SOURCES:
            result = SourceCollectionResult(
                source=source,
                status="disabled",
                doc_count=0,
                elapsed_s=0.0,
                detail=f"{source} source is currently disabled in the production collector.",
            )
            source_documents = []
            source_provider_results = []
        else:
            result = SourceCollectionResult(
                source=source,
                status="failed",
                doc_count=0,
                elapsed_s=0.0,
                detail=f"Unsupported source '{source}'.",
            )
            source_documents = []
            source_provider_results = []

        source_results.append(result)
        documents.extend(source_documents)
        for provider_result in provider_results[provider_results_before:]:
            logger.info(
                "[COLLECT_PROVIDER] source=%s provider=%s status=%s docs=%s elapsed=%.2fs",
                provider_result.source.split(":", 1)[0],
                provider_result.source.split(":", 1)[1] if ":" in provider_result.source else provider_result.source,
                provider_result.status,
                provider_result.doc_count,
                provider_result.elapsed_s,
            )
        logger.info(
            "[COLLECT_SOURCE] source=%s status=%s docs=%s elapsed=%.2fs",
            result.source,
            result.status,
            result.doc_count,
            result.elapsed_s,
        )

    # --- ETF issuer-profile augmentation -------------------------------
    # For ETFs we always attempt to fetch the issuer's product page (iShares,
    # Vanguard, SPDR, Invesco, ARK, etc.) regardless of which source set the
    # user requested. It's a single best-effort HTTP call with a tight
    # timeout, so it never materially slows equity runs and never blocks a
    # pipeline that is otherwise healthy. Failures degrade silently into a
    # provider_result entry.
    if profile.is_etf:
        etf_result, etf_documents = collect_etf_profile(profile)
        issuer_label = profile.issuer or "yahoo"
        provider_results.append(
            SourceCollectionResult(
                source=f"etf_profile:{issuer_label}",
                status=etf_result.status,
                doc_count=etf_result.doc_count,
                elapsed_s=etf_result.elapsed_s,
                detail=etf_result.detail,
            )
        )
        logger.info(
            "[COLLECT_PROVIDER] source=etf_profile provider=%s status=%s docs=%s elapsed=%.2fs",
            issuer_label,
            etf_result.status,
            etf_result.doc_count,
            etf_result.elapsed_s,
        )
        if etf_documents:
            documents.extend(etf_documents)

    documents = deduplicate_documents(documents)
    current_doc_ids = [str(document.get("doc_id")) for document in documents if document.get("doc_id")]
    raw_path = settings.raw_dir / f"{ticker}_docs.json"
    write_documents(raw_path, documents)

    degraded_sources = [result.source for result in source_results if result.status not in _NON_DEGRADED_STATUSES]
    logger.info("[COLLECT_SUMMARY] usable_docs=%s degraded_sources=%s", len(documents), degraded_sources)

    outcome = CollectionOutcome(
        documents=documents,
        source_results=source_results,
        provider_results=provider_results,
        degraded=bool(degraded_sources),
        summary_detail=_build_summary_detail(source_results),
        current_doc_ids=current_doc_ids,
        run_started_at=run_started_at.isoformat(),
        freshness_cutoff=freshness_cutoff,
        retrieval_policy="current_run_only",
    )

    cache.put(cache_key, outcome)
    return outcome
