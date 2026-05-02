from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from core.schemas.retrieval import RetrievalItem
from core.utils.technical_indicators import technical_metrics_from_retrieval_items


_FRED_VALUE_RE = re.compile(
    r"\bis\s+(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>%|percent|pct|bp|bps|pp)?\s+as of\s+(?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_TOPIC_PRICE_RE = re.compile(
    r"\b(?P<ticker>[A-Z0-9=.^-]{1,16})\s+closed at\s+(?P<price>[-+]?\d+(?:\.\d+)?)"
    r"(?:\s+as of\s+(?P<asof>\d{4}-\d{2}-\d{2}))?,\s+a\s+"
    r"(?P<change>[-+]?\d+(?:\.\d+)?)%\s+move over the last\s+(?P<window>\d+)\s+trading days",
    re.IGNORECASE,
)
_MACRO_PRICE_RE = re.compile(
    r"Yahoo symbol (?P<ticker>[A-Z0-9=.^-]{1,16})\)\s+(?:rose|fell|was unchanged)\s+"
    r"from\s+(?P<first>[-+]?\d+(?:\.\d+)?)\s+on\s+(?P<first_date>\d{4}-\d{2}-\d{2})\s+to\s+"
    r"(?P<last>[-+]?\d+(?:\.\d+)?)\s+on\s+(?P<last_date>\d{4}-\d{2}-\d{2}),\s+"
    r"a change of\s+(?P<change>[-+]?\d+(?:\.\d+)?)\s+\((?P<pct>[-+]?\d+(?:\.\d+)?)%\)",
    re.IGNORECASE,
)


_ASSET_PROXIES = {
    "rates_bonds": ("TLT", "IEF", "SHY", "AGG"),
    "credit": ("HYG", "LQD", "IEF", "TLT", "SPY"),
    "commodity": ("GLD", "USO", "CL=F", "GC=F", "DXY"),
    "fx": ("EURUSD=X", "DX=F", "UUP"),
    "crypto": ("BTC-USD", "ETH-USD", "QQQ"),
    "sector_theme": ("SOXX", "QQQ", "SPY"),
    "equity_index": ("SPY", "QQQ", "IWM"),
}


def _parent_doc_id(item: RetrievalItem) -> str:
    metadata = item.metadata or {}
    return str(metadata.get("parent_doc_id") or metadata.get("doc_id") or "").strip()


def _source_series_id(item: RetrievalItem) -> str:
    source = str(item.source or "")
    if source.upper().startswith("FRED:"):
        return source.split(":", 1)[1].strip().upper()
    metadata = item.metadata or {}
    series = str(metadata.get("series_id") or metadata.get("fred_series_id") or "").strip().upper()
    if series:
        return series
    match = re.search(r"\b(DGS10|DGS2|DGS30|DFII10|DFF|CPIAUCSL|UNRATE|T10Y2Y)\b", f"{item.title} {item.chunk}", re.I)
    return match.group(1).upper() if match else ""


def _freshness_status(as_of: str) -> str:
    if not as_of or as_of == "unknown":
        return "unknown"
    try:
        date_part = as_of[:10]
        dt = datetime.fromisoformat(date_part)
        age_days = (datetime.now(timezone.utc).date() - dt.date()).days
        return "stale" if age_days > 10 else "fresh"
    except Exception:
        return "unknown"


def _metric(
    name: str,
    value: str,
    *,
    as_of: str,
    context: str,
    evidence_doc_ids: list[str],
    source: str = "deterministic_quant",
    unit: str = "",
) -> dict[str, Any]:
    basis_date = as_of or "unknown"
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "as_of": basis_date,
        "context": context,
        "source": source,
        "freshness_status": _freshness_status(basis_date),
        "evidence_doc_ids": [doc_id for doc_id in evidence_doc_ids if doc_id],
    }


def _dedupe_metric_dicts(existing: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {
        str(item.get("name") or "").strip().lower()
        for item in existing
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    out: list[dict[str, Any]] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _latest_date(items: list[dict[str, Any]]) -> str:
    dates = [str(item.get("as_of") or "").strip() for item in items if str(item.get("as_of") or "").strip()]
    return sorted(dates)[-1] if dates else "unknown"


def _latest_context_date(context: list[RetrievalItem]) -> str:
    dates = [str(item.date or "").strip() for item in context if str(item.date or "").strip()]
    return sorted(dates)[-1] if dates else "unknown"


def _snapshot_as_of(metrics: list[dict[str, Any]], context: list[RetrievalItem]) -> str:
    as_of = _latest_date(metrics)
    if as_of == "unknown":
        as_of = _latest_context_date(context)
    return as_of or "unknown"


def _snapshot_source_status(metrics: list[dict[str, Any]], missing_axes: list[str]) -> dict[str, Any]:
    sources = sorted({str(item.get("source") or "").strip() for item in metrics if str(item.get("source") or "").strip()})
    evidence_doc_ids = sorted(
        {
            str(doc_id)
            for item in metrics
            for doc_id in (item.get("evidence_doc_ids") or [])
            if str(doc_id).strip()
        }
    )
    return {
        "metric_count": len(metrics),
        "sources": sources,
        "evidence_doc_count": len(evidence_doc_ids),
        "has_price_metrics": any(source.startswith("yfinance:price") for source in sources),
        "has_fred_metrics": any(source.startswith("FRED:") for source in sources),
        "has_technical_metrics": any("technical" in source for source in sources),
        "missing_axes": list(missing_axes),
    }


def _extract_fred_values(context: list[RetrievalItem]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for item in context:
        series_id = _source_series_id(item)
        if not series_id:
            continue
        match = _FRED_VALUE_RE.search(item.chunk or "")
        if not match:
            if " as of " not in str(item.chunk or "").lower():
                continue
            numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", item.chunk or "")
            if not numbers:
                continue
            value = float(numbers[0])
            as_of = str(item.date or "").strip() or "unknown"
        else:
            value = float(match.group("value"))
            as_of = match.group("date") or str(item.date or "").strip() or "unknown"
        values[series_id] = {
            "value": value,
            "as_of": as_of,
            "doc_id": _parent_doc_id(item),
            "source": item.source,
            "title": item.title,
        }
    return values


def _extract_price_snapshots(context: list[RetrievalItem]) -> dict[str, dict[str, Any]]:
    prices: dict[str, dict[str, Any]] = {}
    for item in context:
        text = item.chunk or ""
        match = _TOPIC_PRICE_RE.search(text)
        if match:
            ticker = match.group("ticker").upper()
            prices[ticker] = {
                "price": float(match.group("price")),
                "change_pct": float(match.group("change")),
                "window": int(match.group("window")),
                "as_of": str(match.group("asof") or item.date or "").strip() or "unknown",
                "doc_id": _parent_doc_id(item),
                "source": item.source,
                "title": item.title,
            }
            continue
        match = _MACRO_PRICE_RE.search(text)
        if match:
            ticker = match.group("ticker").upper()
            prices[ticker] = {
                "price": float(match.group("last")),
                "change_pct": float(match.group("pct")),
                "window": _infer_window_days(match.group("first_date"), match.group("last_date")),
                "as_of": str(match.group("last_date") or item.date or "").strip() or "unknown",
                "doc_id": _parent_doc_id(item),
                "source": item.source,
                "title": item.title,
            }
    return prices


def _infer_window_days(first_date: str, last_date: str) -> int:
    try:
        first = datetime.fromisoformat(first_date).date()
        last = datetime.fromisoformat(last_date).date()
        return max(1, (last - first).days)
    except Exception:
        return 30


def _first_target(theme: str, related_tickers: list[str], asset_class: str) -> str:
    for ticker in related_tickers:
        value = str(ticker or "").upper().strip()
        if value:
            return value
    upper_theme = str(theme or "").upper()
    for symbol in ("TLT", "HYG", "LQD", "GLD", "CL=F", "GC=F", "EURUSD=X", "BTC-USD", "SOXX", "QQQ", "SPY"):
        if symbol in upper_theme:
            return symbol
    return _ASSET_PROXIES.get(asset_class, ("SPY",))[0]


def _duration_proxy(target: str, asset_class: str) -> dict[str, Any] | None:
    symbol = target.upper()
    proxies = {
        "TLT": 16.8,
        "EDV": 24.0,
        "IEF": 7.4,
        "SHY": 1.9,
        "AGG": 6.2,
        "LQD": 8.2,
        "HYG": 3.7,
        "BND": 6.1,
    }
    if symbol not in proxies and asset_class not in {"rates_bonds", "credit"}:
        return None
    duration = proxies.get(symbol, 16.0 if asset_class == "rates_bonds" else 5.5)
    return {
        "value": duration,
        "unit": "years",
        "source": "duration proxy",
        "description": "Issuer real-time duration is unavailable in the current evidence; deterministic ETF duration proxy used.",
    }


def _shock_table(duration: float, as_of: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for shock_bp in (-100, -50, 50, 100):
        impact_pct = -duration * (shock_bp / 10000.0) * 100.0
        rows.append(
            {
                "shock_bp": shock_bp,
                "estimated_price_impact_pct": f"{impact_pct:+.1f}%",
                "as_of": as_of,
                "method": "modified-duration approximation",
            }
        )
    return rows


def _price_metrics(prices: dict[str, dict[str, Any]], tickers: list[str], limit: int = 5) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    ordered = []
    for ticker in tickers:
        if ticker in prices and ticker not in ordered:
            ordered.append(ticker)
    for ticker in prices:
        if ticker not in ordered:
            ordered.append(ticker)
    for ticker in ordered[:limit]:
        row = prices[ticker]
        metrics.append(
            _metric(
                f"{ticker} price return ({row['window']} trading days)",
                f"{row['change_pct']:+.2f}%",
                unit="%",
                as_of=row["as_of"],
                context="Recent price trend used as a market-implied expectation proxy.",
                evidence_doc_ids=[row["doc_id"]],
                source="yfinance:price",
            )
        )
        metrics.append(
            _metric(
                f"{ticker} latest close",
                f"{row['price']:.2f}",
                as_of=row["as_of"],
                context="Latest close anchors valuation and scenario sensitivity.",
                evidence_doc_ids=[row["doc_id"]],
                source="yfinance:price",
            )
        )
    return metrics


def _rates_bonds_snapshot(theme: str, related_tickers: list[str], context: list[RetrievalItem]) -> dict[str, Any]:
    target = _first_target(theme, related_tickers, "rates_bonds")
    fred = _extract_fred_values(context)
    prices = _extract_price_snapshots(context)
    metrics: list[dict[str, Any]] = []
    substituted_buckets: list[str] = []

    series_labels = {
        "DGS10": ("US 10Y Treasury yield", "Long-end Treasury yield is the main discount-rate driver for duration assets."),
        "DGS30": ("US 30Y Treasury yield", "The 30Y yield is a direct long-duration bond valuation anchor."),
        "DFII10": ("US 10Y real yield proxy", "Real yields capture the inflation-adjusted tightening burden."),
        "DFF": ("Fed effective rate", "Fed policy rate indicates current front-end monetary stance."),
    }
    for series_id, (label, context_text) in series_labels.items():
        row = fred.get(series_id)
        if not row:
            continue
        metrics.append(
            _metric(
                label,
                f"{row['value']:.3f}%",
                unit="%",
                as_of=row["as_of"],
                context=context_text,
                evidence_doc_ids=[row["doc_id"]],
                source=f"FRED:{series_id}",
            )
        )

    if fred.get("DGS10") and fred.get("DGS2"):
        d10 = fred["DGS10"]
        d2 = fred["DGS2"]
        spread = d10["value"] - d2["value"]
        as_of = max(str(d10["as_of"]), str(d2["as_of"]))
        metrics.append(
            _metric(
                "10Y-2Y Treasury curve",
                f"{spread:+.3f} pp ({spread * 100:+.0f} bp)",
                unit="pp",
                as_of=as_of,
                context="Curve slope helps distinguish recession risk from soft-landing pricing.",
                evidence_doc_ids=[d10["doc_id"], d2["doc_id"]],
                source="FRED:DGS10-DGS2",
            )
        )

    price_metrics = _price_metrics(prices, [target.upper(), *[t.upper() for t in related_tickers]], limit=2)
    if price_metrics:
        metrics.extend(price_metrics)
        substituted_buckets.extend(["asset_specific", "market_structure"])

    technical_metrics = technical_metrics_from_retrieval_items(context)
    if technical_metrics:
        metrics.extend(_dedupe_metric_dicts(metrics, technical_metrics))
        substituted_buckets.append("market_structure")

    duration = _duration_proxy(target, "rates_bonds")
    shock_as_of = _latest_date(metrics)
    if shock_as_of == "unknown":
        shock_as_of = _latest_context_date(context)
    if duration:
        metrics.append(
            _metric(
                f"{target.upper()} duration proxy",
                f"{duration['value']:.1f}",
                unit="years",
                as_of=shock_as_of,
                context="Duration estimates price sensitivity to interest-rate shocks.",
                evidence_doc_ids=[],
                source="deterministic_duration_proxy",
            )
        )
        metrics.append(
            _metric(
                "Rate shock sensitivity (+/-100bp)",
                f"-100bp: +{duration['value']:.1f}%, +100bp: -{duration['value']:.1f}%",
                unit="estimated price impact",
                as_of=shock_as_of,
                context="Linear duration approximation for upside/downside asymmetry.",
                evidence_doc_ids=[],
                source="deterministic_duration_proxy",
            )
        )
        substituted_buckets.append("market_structure")

    missing_axes = _rates_missing_axes(fred, prices, target)
    snapshot_as_of = _snapshot_as_of(metrics, context)
    return {
        "asset_class": "rates_bonds",
        "target": target.upper(),
        "as_of": snapshot_as_of,
        "freshness_status": _freshness_status(snapshot_as_of),
        "source": "deterministic_quant",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "duration_or_proxy": duration,
        "rate_shock_scenarios": _shock_table(float(duration["value"]), shock_as_of) if duration else [],
        "factor_exposures": {"primary": "duration", "secondary": ["real_yield", "yield_curve", "term_premium"]},
        "stress_table": _shock_table(float(duration["value"]), shock_as_of) if duration else [],
        "substituted_buckets": sorted(set(substituted_buckets)),
        "missing_axes": missing_axes,
        "source_status": _snapshot_source_status(metrics, missing_axes),
        "notes": [
            "LLM must interpret the deterministic numbers and must not invent additional numeric values.",
            "Duration is a proxy when issuer real-time duration is unavailable.",
        ],
    }


def _rates_missing_axes(fred: dict[str, dict[str, Any]], prices: dict[str, dict[str, Any]], target: str) -> list[str]:
    missing: list[str] = []
    if not fred.get("DGS10"):
        missing.append("10Y Treasury yield")
    if not fred.get("DGS30"):
        missing.append("30Y Treasury yield")
    if not (fred.get("DGS10") and fred.get("DGS2")):
        missing.append("10Y-2Y curve")
    if not fred.get("DFII10"):
        missing.append("real yield proxy")
    if not prices.get(target.upper()):
        missing.append(f"{target.upper()} price trend")
    return missing


def _credit_snapshot(theme: str, related_tickers: list[str], context: list[RetrievalItem]) -> dict[str, Any]:
    prices = _extract_price_snapshots(context)
    target = _first_target(theme, related_tickers or ["HYG", "LQD"], "credit")
    tickers = [target.upper(), "HYG", "LQD", "IEF", "TLT", "SPY"]
    metrics = _price_metrics(prices, tickers, limit=6)
    technical_metrics = technical_metrics_from_retrieval_items(context)
    if technical_metrics:
        metrics.extend(_dedupe_metric_dicts(metrics, technical_metrics))
    missing = [ticker for ticker in ("HYG", "LQD") if ticker not in prices]
    as_of = _snapshot_as_of(metrics, context)
    duration = _duration_proxy(target, "credit")
    if duration:
        metrics.append(
            _metric(
                "Credit duration proxy",
                f"{duration['value']:.1f}",
                unit="years",
                as_of=as_of,
                context="Credit ETFs still carry duration risk alongside spread risk.",
                evidence_doc_ids=[],
                source="deterministic_duration_proxy",
            )
        )
    return _snapshot(
        "credit",
        target,
        metrics,
        substituted=["market_structure", "asset_specific"] if metrics else [],
        missing_axes=missing or (["credit proxy prices"] if not metrics else []),
        factor_exposures={"primary": "credit_spread_proxy", "secondary": ["duration", "liquidity", "equity_beta"]},
        context=context,
    )


def _generic_snapshot(asset_class: str, theme: str, related_tickers: list[str], context: list[RetrievalItem]) -> dict[str, Any]:
    normalized = asset_class or "sector_theme"
    prices = _extract_price_snapshots(context)
    target = _first_target(theme, related_tickers, normalized)
    proxy_tickers = [target.upper(), *[t.upper() for t in related_tickers], *_ASSET_PROXIES.get(normalized, ())]
    metrics = _price_metrics(prices, proxy_tickers, limit=6)
    technical_metrics = technical_metrics_from_retrieval_items(context)
    if technical_metrics:
        metrics.extend(_dedupe_metric_dicts(metrics, technical_metrics))
    missing = [] if metrics else ["price trend"]
    factor_map = {
        "commodity": {"primary": "real_rate_usd", "secondary": ["supply_demand", "inventory", "curve"]},
        "fx": {"primary": "rate_differential", "secondary": ["growth_divergence", "usd_liquidity", "positioning"]},
        "crypto": {"primary": "global_liquidity", "secondary": ["risk_appetite", "ETF_flow", "regulation"]},
        "sector_theme": {"primary": "sector_beta", "secondary": ["earnings_cycle", "capex", "pricing_power"]},
        "equity_index": {"primary": "equity_beta", "secondary": ["rates", "earnings", "liquidity"]},
    }
    return _snapshot(
        normalized,
        target,
        metrics,
        substituted=["market_structure", "asset_specific"] if metrics else [],
        missing_axes=missing,
        factor_exposures=factor_map.get(normalized, {"primary": "market_beta", "secondary": []}),
        context=context,
    )


def _snapshot(
    asset_class: str,
    target: str,
    metrics: list[dict[str, Any]],
    *,
    substituted: list[str],
    missing_axes: list[str],
    factor_exposures: dict[str, Any],
    context: list[RetrievalItem],
) -> dict[str, Any]:
    snapshot_as_of = _snapshot_as_of(metrics, context)
    return {
        "asset_class": asset_class,
        "target": target.upper(),
        "as_of": snapshot_as_of,
        "freshness_status": _freshness_status(snapshot_as_of),
        "source": "deterministic_quant",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "duration_or_proxy": None,
        "rate_shock_scenarios": [],
        "factor_exposures": factor_exposures,
        "stress_table": [],
        "substituted_buckets": sorted(set(substituted)),
        "missing_axes": missing_axes,
        "source_status": _snapshot_source_status(metrics, missing_axes),
        "notes": [
            "Topic quant snapshot uses currently collected public evidence and deterministic proxy calculations.",
            "Missing axes are surfaced as uncertainty instead of being hidden.",
        ],
    }




def _normalize_asset_class(asset_class: str | None, theme: str, related: list[str]) -> str:
    """Classify topic quant snapshots with explicit asset hints taking precedence."""

    normalized = str(asset_class or "sector_theme").strip() or "sector_theme"
    if normalized in {"rates_bonds", "credit", "commodity", "fx", "crypto", "equity_index"}:
        return normalized

    primary = related[0].upper() if related else ""
    if primary in {"HYG", "LQD"}:
        return "credit"
    if primary in {"TLT", "IEF", "SHY", "AGG"}:
        return "rates_bonds"
    if primary in {"GLD", "USO", "CL=F", "GC=F"}:
        return "commodity"
    if primary.endswith("=X") or primary in {"DX=F", "DX-Y.NYB", "UUP"}:
        return "fx"
    if primary.endswith("-USD"):
        return "crypto"

    text = f"{theme} {' '.join(related)}".upper()
    lower = f"{theme} {' '.join(related)}".lower()
    if any(ticker in text for ticker in ("HYG", "LQD")) or any(term in lower for term in ("credit", "spread", "default", "신용", "스프레드", "부도")):
        return "credit"
    if "TLT" in text or any(term in lower for term in ("treasury", "duration", "yield curve", "금리", "채권", "국채", "장기채", "듀레이션")):
        return "rates_bonds"
    if any(ticker in text for ticker in ("GLD", "USO", "CL=F", "GC=F")):
        return "commodity"
    if "=X" in text or any(term in lower for term in ("fx", "currency", "환율", "달러", "유로")):
        return "fx"
    if "-USD" in text or any(term in lower for term in ("crypto", "bitcoin", "비트코인", "암호화폐")):
        return "crypto"
    return normalized


def build_topic_quant_snapshot(
    asset_class: str | None,
    theme: str,
    related_tickers: list[str] | None,
    context: list[RetrievalItem],
) -> dict[str, Any]:
    related = [str(ticker).upper().strip() for ticker in (related_tickers or []) if str(ticker).strip()]
    normalized = _normalize_asset_class(asset_class, theme, related)
    if normalized == "rates_bonds":
        return _rates_bonds_snapshot(theme, related, context)
    if normalized == "credit":
        return _credit_snapshot(theme, related, context)
    return _generic_snapshot(normalized, theme, related, context)


def key_metrics_from_quant_snapshot(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return []
    metrics = snapshot.get("metrics")
    if not isinstance(metrics, list):
        return []
    out: list[dict[str, Any]] = []
    for item in metrics:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or not value:
            continue
        out.append(
            {
                "name": name,
                "value": value,
                "unit": str(item.get("unit") or "").strip(),
                "as_of": str(item.get("as_of") or "unknown").strip() or "unknown",
                "context": str(item.get("context") or "").strip(),
                "source": str(item.get("source") or "deterministic_quant").strip(),
                "freshness_status": str(item.get("freshness_status") or "unknown").strip(),
                "evidence_doc_ids": [str(x) for x in (item.get("evidence_doc_ids") or []) if str(x).strip()],
            }
        )
    return out
