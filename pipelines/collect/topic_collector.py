from __future__ import annotations

import concurrent.futures
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from defusedxml import ElementTree as ET

import httpx

from core.config.settings import load_settings
from core.utils.asset_classifier import classify
from core.utils.data_helpers import build_doc_id, deduplicate_documents, write_documents
from core.utils.logger import get_logger
from core.utils.technical_indicators import compute_technical_metrics_from_history, technical_metrics_document_text
from pipelines.collect.cache import get_cache
from pipelines.collect.etf_profile_collector import collect_etf_profile
from pipelines.collect.macro_collector import collect_macro_bundle
from pipelines.collect.models import CollectionOutcome, SourceCollectionResult

logger = get_logger("pipelines.collect.topic")

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DEFAULT_FRED_SERIES = ["DGS10", "DGS2", "DGS30", "DFII10", "DFF", "CPIAUCSL", "UNRATE"]
_KOREA_INVERSE_RELATED_TICKERS = ["114800.KS", "252670.KS", "251340.KS", "EWY"]
_KOREA_MARKET_TERMS = [
    "kospi",
    "kosdaq",
    "krx",
    "\ucf54\uc2a4\ud53c",
    "\ucf54\uc2a4\ub2e5",
    "\ud55c\uad6d \uc99d\uc2dc",
    "\uad6d\ub0b4 \uc99d\uc2dc",
    "\ud55c\uad6d \uc2dc\uc7a5",
]
_KOREA_INVERSE_TERMS = [
    "inverse",
    "short kospi",
    "short korea",
    "\uc778\ubc84\uc2a4",
    "\uace1\ubc84\uc2a4",
    "\uc120\ubb3c\uc778\ubc84\uc2a4",
    "\ud558\ub77d \ubca0\ud305",
]
_SECTOR_ETF_MAP = {
    "semiconductor": ["SOXX", "SMH", "NVDA", "AMD", "AVGO", "TSM"],
    "반도체": ["SOXX", "SMH", "NVDA", "AMD", "AVGO", "TSM"],
    "growth": ["QQQ", "XLK", "SPY"],
    "성장주": ["QQQ", "XLK", "SPY"],
    "oil": ["USO", "XLE", "CL=F"],
    "crude": ["USO", "XLE", "CL=F"],
    "gold": ["GLD", "SLV"],
    "bond": ["TLT", "IEF", "SHY", "AGG"],
    "treasury": ["TLT", "IEF", "SHY"],
    "duration": ["TLT", "IEF", "SHY"],
    "rates": ["TLT", "IEF", "SHY"],
    "채권": ["TLT", "IEF", "SHY", "AGG"],
    "국채": ["TLT", "IEF", "SHY"],
    "금리": ["TLT", "IEF", "SHY"],
}


_SECTOR_ETF_MAP.update(
    {
        "반도체": ["SOXX", "SMH", "NVDA", "AMD", "AVGO", "TSM"],
        "AI": ["SOXX", "SMH", "NVDA", "AMD", "AVGO", "TSM"],
        "성장주": ["QQQ", "XLK", "SPY"],
        "원유": ["USO", "XLE", "CL=F"],
        "유가": ["USO", "XLE", "CL=F"],
        "금": ["GLD", "SLV"],
        "원자재": ["GLD", "USO", "SLV"],
        "채권": ["TLT", "IEF", "SHY", "AGG"],
        "국채": ["TLT", "IEF", "SHY"],
        "장기채": ["TLT", "IEF", "SHY"],
        "금리": ["TLT", "IEF", "SHY"],
        "신용": ["HYG", "LQD", "TLT"],
        "크레딧": ["HYG", "LQD", "TLT"],
        "달러": ["EURUSD=X", "DX-Y.NYB"],
        "환율": ["EURUSD=X", "DX-Y.NYB"],
        "비트코인": ["BTC-USD", "ETH-USD"],
        "암호화폐": ["BTC-USD", "ETH-USD"],
    }
)


def _contains_korea_inverse_topic(text: str) -> bool:
    lower = str(text or "").lower()
    return any(term in lower for term in _KOREA_MARKET_TERMS) and any(term in lower for term in _KOREA_INVERSE_TERMS)


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", text or "")).strip()


def _to_iso(published: str) -> str:
    try:
        dt = parsedate_to_datetime(published)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return published or ""


def _topic_doc(
    theme: str,
    source: str,
    title: str,
    text: str,
    published_at: str,
    url: str = "",
    *,
    asset_class: str = "sector_theme",
    bucket: str = "asset_specific",
) -> dict[str, Any]:
    seed = "|".join([theme, source, title, published_at, text[:200], url])
    doc_id = build_doc_id("topic", "macro", seed)
    return {
        "doc_id": doc_id,
        "ticker": "",
        "symbol": "",
        "doc_type": "topic",
        "source": source,
        "published_at": published_at,
        "title": title,
        "text": text,
        "url": url,
        "asset_class": asset_class,
        "bucket": bucket,
        "admitted_by": "topic_mode",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def _bucket_from_doc(doc: dict[str, Any]) -> str:
    source = str(doc.get("source") or "").lower()
    doc_type = str(doc.get("doc_type") or "").lower()
    text = f"{doc.get('title') or ''} {doc.get('text') or ''}".lower()
    if source.startswith("fred") or doc_type == "macro" or any(term in text for term in ("yield", "inflation", "cpi", "fed", "real yield")):
        return "macro"
    if "price" in source or "price" in text or "duration" in text or "curve" in text or doc_type in {"etf_profile", "fundamentals"}:
        return "market_structure"
    if "news" in source or "transcript" in source:
        return "latest_catalyst"
    return "asset_specific"


def _annotate_topic_documents(docs: list[dict[str, Any]], asset_class: str) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        copy = dict(doc)
        copy.setdefault("asset_class", asset_class)
        copy.setdefault("bucket", _bucket_from_doc(copy))
        copy.setdefault("collected_at", datetime.now(timezone.utc).isoformat())
        annotated.append(copy)
    return annotated


def _topic_asset_class_for_profile(profile: Any) -> str:
    asset_class = str(getattr(profile, "asset_class", "") or "")
    if asset_class == "bond_etf":
        return "rates_bonds"
    if asset_class in {"commodity_etf", "futures"}:
        return "commodity"
    if asset_class == "forex":
        return "fx"
    if asset_class == "crypto":
        return "crypto"
    return "sector_theme" if getattr(profile, "is_etf", False) else "sector_theme"


def _collect_google_topic_news(
    question: str,
    theme: str,
    lookback_days: int,
    limit: int = 20,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    started = datetime.now()
    horizon = max(1, min(int(lookback_days), 30))
    query = f"{theme or question} finance market stocks when:{horizon}d"
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    url = f"{_GOOGLE_NEWS_RSS}?{urllib.parse.urlencode(params)}"
    try:
        with httpx.Client(timeout=8.0, headers={"User-Agent": _USER_AGENT}, follow_redirects=True) as client:
            response = client.get(url)
        if response.status_code != 200:
            return SourceCollectionResult("topic_news", "failed", 0, 0.0, f"google_news HTTP {response.status_code}"), []
        root = ET.fromstring(response.text)
    except Exception as exc:  # noqa: BLE001
        elapsed = round((datetime.now() - started).total_seconds(), 2)
        return SourceCollectionResult("topic_news", "failed", 0, elapsed, f"google_news error: {exc}"), []

    docs: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        desc = _strip_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        pub = _to_iso(item.findtext("pubDate") or "")
        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
        except Exception:
            pass
        text = "\n\n".join(part for part in [title, desc] if part)
        if text:
            docs.append(_topic_doc(theme, "Google News", title or "Topic news", text, pub, link, bucket="latest_catalyst"))

    elapsed = round((datetime.now() - started).total_seconds(), 2)
    status = "ok" if docs else "empty"
    return SourceCollectionResult("topic_news", status, len(docs), elapsed, "Google News topic RSS collected."), docs


def _fetch_fred_series(series_id: str, api_key: str, lookback_days: int) -> dict[str, Any] | None:
    base = "https://api.stlouisfed.org/fred"
    cutoff = (datetime.now() - timedelta(days=max(lookback_days, 90))).date().isoformat()
    params = {"api_key": api_key, "file_type": "json", "series_id": series_id}
    with httpx.Client(timeout=8.0) as client:
        meta = client.get(f"{base}/series", params=params)
        obs = client.get(
            f"{base}/series/observations",
            params={**params, "sort_order": "asc", "observation_start": cutoff},
        )
    if meta.status_code != 200 or obs.status_code != 200:
        return None
    meta_rows = meta.json().get("seriess") or []
    title = (meta_rows[0] if meta_rows else {}).get("title") or series_id
    units = (meta_rows[0] if meta_rows else {}).get("units_short") or ""
    values = []
    for row in obs.json().get("observations") or []:
        try:
            if row.get("value") == ".":
                continue
            values.append((datetime.fromisoformat(row["date"]), float(row["value"])))
        except Exception:
            continue
    if len(values) < 2:
        return None
    first_dt, first_val = values[0]
    last_dt, last_val = values[-1]
    change = last_val - first_val
    text = (
        f"{title} ({series_id}) is {last_val:.3f} {units} as of {last_dt.date().isoformat()}, "
        f"changed {change:+.3f} from {first_val:.3f} on {first_dt.date().isoformat()}."
    )
    return {"series_id": series_id, "title": title, "text": text, "published_at": last_dt.isoformat()}


def _collect_macro_series(theme: str, lookback_days: int, api_key: str) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    started = datetime.now()
    if not api_key:
        return SourceCollectionResult("topic_macro", "credentials_missing", 0, 0.0, "FRED_API_KEY missing."), []
    docs: list[dict[str, Any]] = []
    for series_id in _DEFAULT_FRED_SERIES:
        try:
            row = _fetch_fred_series(series_id, api_key, lookback_days)
        except Exception:
            row = None
        if not row:
            continue
        docs.append(
            _topic_doc(
                theme,
                f"FRED:{series_id}",
                f"FRED {series_id}: {row['title']}",
                row["text"],
                row["published_at"],
                f"https://fred.stlouisfed.org/series/{series_id}",
                asset_class="rates_bonds",
                bucket="macro",
            )
        )
    elapsed = round((datetime.now() - started).total_seconds(), 2)
    return SourceCollectionResult("topic_macro", "ok" if docs else "empty", len(docs), elapsed, "FRED topic macro series collected."), docs


def _infer_theme_tickers(theme: str, related_tickers: list[str]) -> list[str]:
    tickers = [t.upper() for t in related_tickers if t]
    text = theme or ""
    lower = text.lower()
    if _contains_korea_inverse_topic(text):
        tickers.extend(_KOREA_INVERSE_RELATED_TICKERS)
    for key, mapped in _SECTOR_ETF_MAP.items():
        key_lower = key.lower()
        if key_lower == "ai":
            matched = re.search(r"(?<![a-z])ai(?![a-z])", lower) is not None
        elif key == "금":
            matched = re.search(r"(?<![가-힣])금(?!리|[가-힣])", text) is not None
        else:
            matched = key_lower in lower
        if matched:
            tickers.extend(mapped)
    seen: set[str] = set()
    out: list[str] = []
    for ticker in tickers:
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)
    return out[:8]


def _collect_ticker_price_docs(theme: str, tickers: list[str]) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    started = datetime.now()
    docs: list[dict[str, Any]] = []
    try:
        import yfinance as yf
    except Exception as exc:
        return SourceCollectionResult("topic_tickers", "failed", 0, 0.0, f"yfinance unavailable: {exc}"), []

    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="30d")
            if hist is None or hist.empty:
                continue
            first = float(hist["Close"].iloc[0])
            last = float(hist["Close"].iloc[-1])
            last_index = hist.index[-1]
            try:
                price_as_of = last_index.to_pydatetime().date().isoformat()
            except Exception:
                price_as_of = datetime.now(timezone.utc).date().isoformat()
            pct = ((last / first) - 1.0) * 100 if first else 0.0
            text = f"{ticker} closed at {last:.2f} as of {price_as_of}, a {pct:+.2f}% move over the last 30 trading days."
            docs.append(
                _topic_doc(
                    theme,
                    "yfinance:price",
                    f"{ticker} 30-day price snapshot",
                    text,
                    price_as_of,
                    bucket="market_structure",
                )
            )
            technical_metrics = compute_technical_metrics_from_history(hist, ticker)
            if technical_metrics:
                tech_as_of = str(technical_metrics[0].get("as_of") or price_as_of)
                seed = "|".join([theme, ticker, "technical", tech_as_of, ";".join(f"{m.get('name')}={m.get('value')}" for m in technical_metrics)])
                tech_doc_id = build_doc_id("topic", "technical", seed)
                technical_metrics = [{**metric, "evidence_doc_ids": [tech_doc_id]} for metric in technical_metrics]
                tech_doc = _topic_doc(
                    theme,
                    "yfinance:technical",
                    f"{ticker} technical indicator snapshot",
                    technical_metrics_document_text(ticker, technical_metrics),
                    tech_as_of,
                    bucket="market_structure",
                )
                tech_doc["doc_id"] = tech_doc_id
                tech_doc["ticker"] = ticker.upper()
                tech_doc["symbol"] = ticker.upper()
                tech_doc["doc_type"] = "technical_snapshot"
                docs.append(tech_doc)
        except Exception:
            continue

    elapsed = round((datetime.now() - started).total_seconds(), 2)
    return SourceCollectionResult("topic_tickers", "ok" if docs else "empty", len(docs), elapsed, "Related ticker price snapshots collected."), docs


def _collect_one_related_asset(
    ticker: str,
    lookback_days: int,
    settings,
) -> tuple[list[SourceCollectionResult], list[SourceCollectionResult], list[dict[str, Any]], bool]:
    source_results: list[SourceCollectionResult] = []
    provider_results: list[SourceCollectionResult] = []
    documents: list[dict[str, Any]] = []
    macro_supported = False

    profile = classify(ticker)
    topic_asset_class = _topic_asset_class_for_profile(profile)
    if profile.supports_macro:
        macro_supported = True
        macro_result, macro_docs, macro_provider_results = collect_macro_bundle(
            profile,
            lookback_days,
            settings.fred_api_key,
            macro_price_lookback_days=getattr(settings, "macro_price_lookback_days", 90),
        )
        source_results.append(
            SourceCollectionResult(
                source=f"topic_asset:{profile.ticker}",
                status=macro_result.status,
                doc_count=macro_result.doc_count,
                elapsed_s=macro_result.elapsed_s,
                detail=f"{profile.ticker} macro bundle: {macro_result.detail}",
            )
        )
        provider_results.extend(
            SourceCollectionResult(
                source=f"topic_asset:{profile.ticker}:{provider.source}",
                status=provider.status,
                doc_count=provider.doc_count,
                elapsed_s=provider.elapsed_s,
                detail=provider.detail,
            )
            for provider in macro_provider_results
        )
        documents.extend(_annotate_topic_documents(macro_docs, topic_asset_class))

    if profile.is_etf:
        etf_result, etf_docs = collect_etf_profile(profile)
        source_results.append(
            SourceCollectionResult(
                source=f"topic_etf_profile:{profile.ticker}",
                status=etf_result.status,
                doc_count=etf_result.doc_count,
                elapsed_s=etf_result.elapsed_s,
                detail=etf_result.detail,
            )
        )
        provider_results.append(
            SourceCollectionResult(
                source=f"topic_etf_profile:{profile.ticker}",
                status=etf_result.status,
                doc_count=etf_result.doc_count,
                elapsed_s=etf_result.elapsed_s,
                detail=etf_result.detail,
            )
        )
        documents.extend(_annotate_topic_documents(etf_docs, topic_asset_class))

    return source_results, provider_results, documents, macro_supported


def _collect_related_asset_docs(
    tickers: list[str],
    lookback_days: int,
    settings,
) -> tuple[list[SourceCollectionResult], list[SourceCollectionResult], list[dict[str, Any]], set[str]]:
    source_results: list[SourceCollectionResult] = []
    provider_results: list[SourceCollectionResult] = []
    documents: list[dict[str, Any]] = []
    macro_supported: set[str] = set()

    if not tickers:
        return source_results, provider_results, documents, macro_supported

    max_workers = max(1, min(4, len(tickers)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_collect_one_related_asset, ticker, lookback_days, settings): ticker
            for ticker in tickers
        }
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                src_results, prov_results, docs, supports_macro = future.result()
            except Exception as exc:  # noqa: BLE001
                source_results.append(
                    SourceCollectionResult(
                        source=f"topic_asset:{ticker}",
                        status="failed",
                        doc_count=0,
                        elapsed_s=0.0,
                        detail=str(exc),
                    )
                )
                continue
            source_results.extend(src_results)
            provider_results.extend(prov_results)
            documents.extend(docs)
            if supports_macro:
                macro_supported.add(ticker)

    return source_results, provider_results, documents, macro_supported


def _topic_cache_key(theme: str, related_tickers: list[str], lookback_days: int, settings) -> tuple[str, tuple[str, ...], int]:
    cache = get_cache(settings)
    return cache.make_key(f"TOPIC::{theme}".upper(), sorted({t.upper() for t in related_tickers if t}), lookback_days)


def collect_topic_bundle(
    question: str,
    theme: str | None,
    related_tickers: list[str] | None,
    lookback_days: int = 60,
) -> CollectionOutcome:
    settings = load_settings()
    started = datetime.now(timezone.utc)
    resolved_theme = (theme or question or "topic").strip()
    ticker_list = _infer_theme_tickers(resolved_theme, related_tickers or [])

    cache = get_cache(settings)
    cache_key = _topic_cache_key(resolved_theme, ticker_list, lookback_days, settings)
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info(
            "[TOPIC_COLLECT_CACHE_HIT] theme=%s lookback=%d age=%.1fs docs=%d",
            resolved_theme,
            lookback_days,
            cached.cache_age_s,
            len(cached.documents),
        )
        return cached

    source_results: list[SourceCollectionResult] = []
    provider_results: list[SourceCollectionResult] = []
    documents: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        macro_future = executor.submit(_collect_macro_series, resolved_theme, lookback_days, settings.fred_api_key)
        news_future = executor.submit(_collect_google_topic_news, question, resolved_theme, lookback_days)
        asset_future = executor.submit(_collect_related_asset_docs, ticker_list, lookback_days, settings)

        macro_result, macro_docs = macro_future.result()
        source_results.append(macro_result)
        provider_results.append(macro_result)
        documents.extend(macro_docs)

        news_result, news_docs = news_future.result()
        source_results.append(news_result)
        provider_results.append(news_result)
        documents.extend(news_docs)

        asset_results, asset_provider_results, asset_docs, macro_supported = asset_future.result()
        source_results.extend(asset_results)
        provider_results.extend(asset_provider_results)
        documents.extend(asset_docs)

    price_only_tickers = [ticker for ticker in ticker_list if ticker not in macro_supported]
    if price_only_tickers:
        ticker_result, ticker_docs = _collect_ticker_price_docs(resolved_theme, price_only_tickers)
        source_results.append(ticker_result)
        provider_results.append(ticker_result)
        documents.extend(ticker_docs)

    documents = deduplicate_documents(documents)
    current_doc_ids = [str(doc.get("doc_id")) for doc in documents if doc.get("doc_id")]
    safe_theme = re.sub(r"[^A-Za-z0-9._-]+", "_", resolved_theme)[:80] or "topic"
    write_documents(settings.raw_dir / f"TOPIC_{safe_theme}_docs.json", documents)

    degraded = not documents
    summary = "" if documents else "topic collection returned no usable documents"
    outcome = CollectionOutcome(
        documents=documents,
        source_results=source_results,
        provider_results=provider_results,
        degraded=degraded,
        summary_detail=summary,
        current_doc_ids=current_doc_ids,
        run_started_at=started.isoformat(),
        freshness_cutoff=(started - timedelta(days=lookback_days)).isoformat(),
        retrieval_policy="topic_current_run_fast_path",
    )
    cache.put(cache_key, outcome)
    logger.info("[TOPIC_COLLECT_SUMMARY] theme=%s docs=%d tickers=%s", resolved_theme, len(documents), ticker_list)
    return outcome
