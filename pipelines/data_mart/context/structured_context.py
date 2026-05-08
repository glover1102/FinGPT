from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from core.schemas.retrieval import RetrievalItem
from core.utils.logger import get_logger
from core.utils.symbol_registry import symbol_display_name
from pipelines.data_mart.jobs.update_macro_daily import DEFAULT_US_MACRO_SERIES
from pipelines.data_mart.storage import db as storage_db
from pipelines.data_mart.storage import repository

logger = get_logger("pipelines.data_mart.context.structured")


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _freshness(as_of: str | None, *, stale_after_days: int) -> str:
    parsed = _parse_date(as_of or "")
    if parsed is None:
        return "unknown"
    age = (datetime.now(timezone.utc).date() - parsed).days
    if age <= stale_after_days:
        return "fresh"
    return "stale"


def _pct_return(rows: list[dict[str, Any]], lookback: int) -> float | None:
    if len(rows) <= lookback:
        return None
    latest = _price_value(rows[-1])
    previous = _price_value(rows[-1 - lookback])
    if latest is None or previous in (None, 0):
        return None
    return (latest / previous - 1.0) * 100.0


def _realized_vol(rows: list[dict[str, Any]], lookback: int = 20) -> float | None:
    values = [_price_value(row) for row in rows[-(lookback + 1):]]
    values = [value for value in values if value is not None and value > 0]
    if len(values) < 3:
        return None
    returns = [math.log(values[idx] / values[idx - 1]) for idx in range(1, len(values))]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((ret - mean) ** 2 for ret in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252) * 100.0


def _price_value(row: dict[str, Any]) -> float | None:
    value = row.get("adjusted_close")
    if value is None:
        value = row.get("close")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _compact_metadata_text(value: Any, max_chars: int = 256) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            text = str(value)
    return " ".join(text.split())[:max_chars]


def _bounded_annotation_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    bounded: dict[str, Any] = {}
    for key, value in list(metadata.items())[:10]:
        clean_key = " ".join(str(key or "").split())[:64]
        if not clean_key:
            continue
        if value is None or isinstance(value, (bool, int, float)):
            bounded[clean_key] = value
        else:
            bounded[clean_key] = _compact_metadata_text(value)
    return bounded


def _serialize_fingpt_annotation(annotation: Any) -> dict[str, Any]:
    if hasattr(annotation, "model_dump"):
        raw = annotation.model_dump(mode="json")
    elif isinstance(annotation, dict):
        raw = annotation
    else:
        raw = {
            "article_id": getattr(annotation, "article_id", ""),
            "ticker": getattr(annotation, "ticker", ""),
            "task": getattr(annotation, "task", ""),
            "label": getattr(annotation, "label", ""),
            "confidence": getattr(annotation, "confidence", 0.0),
            "source": getattr(annotation, "source", "fingpt"),
            "model_id": getattr(annotation, "model_id", ""),
            "metadata": getattr(annotation, "metadata", {}),
        }
    return {
        "article_id": str(raw.get("article_id") or ""),
        "ticker": str(raw.get("ticker") or "").upper().strip(),
        "task": str(raw.get("task") or ""),
        "label": str(raw.get("label") or ""),
        "confidence": raw.get("confidence"),
        "source": str(raw.get("source") or "fingpt"),
        "model_id": str(raw.get("model_id") or ""),
        "metadata": _bounded_annotation_metadata(raw.get("metadata")),
    }


def _recent_fingpt_annotations(ticker: str, db_path: str | Path | None) -> list[dict[str, Any]]:
    clean_ticker = str(ticker or "").upper().strip()
    if not clean_ticker:
        return []
    try:
        with storage_db.connect(db_path) as conn:
            annotations = repository.get_fingpt_annotations(conn, ticker=clean_ticker, limit=20)
    except (sqlite3.Error, OSError, ValueError) as exc:
        logger.warning(
            "Failed to load FinGPT annotations for ticker=%s db_path=%s: %s",
            clean_ticker,
            db_path,
            exc,
        )
        return []
    try:
        return [_serialize_fingpt_annotation(annotation) for annotation in annotations[:20]]
    except Exception as exc:
        logger.warning(
            "Failed to serialize FinGPT annotations for ticker=%s db_path=%s; omitting annotations.",
            clean_ticker,
            db_path,
            exc_info=True,
        )
        return []


def build_structured_context(
    ticker: str | None,
    *,
    related_tickers: Iterable[str] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    tickers = []
    if ticker:
        tickers.append(str(ticker).upper().strip())
    for raw in related_tickers or []:
        cleaned = str(raw or "").upper().strip()
        if cleaned and cleaned not in tickers:
            tickers.append(cleaned)

    price_snapshots: list[dict[str, Any]] = []
    for symbol in tickers[:8]:
        rows = repository.get_prices(symbol, limit=252, db_path=db_path)
        latest = rows[-1] if rows else None
        if not latest:
            price_snapshots.append(
                {
                    "ticker": symbol,
                    "display_name": symbol_display_name(symbol),
                    "status": "missing",
                    "freshness_status": "unknown",
                }
            )
            continue
        price_snapshots.append(
            {
                "ticker": symbol,
                "display_name": symbol_display_name(symbol),
                "status": "ok",
                "as_of": latest.get("date"),
                "freshness_status": _freshness(latest.get("date"), stale_after_days=5),
                "close": latest.get("close"),
                "adjusted_close": latest.get("adjusted_close"),
                "volume": latest.get("volume"),
                "source": latest.get("source"),
                "returns": {
                    "1d_pct": _round_or_none(_pct_return(rows, 1)),
                    "21d_pct": _round_or_none(_pct_return(rows, 21)),
                    "63d_pct": _round_or_none(_pct_return(rows, 63)),
                },
                "risk": {
                    "realized_vol_20d_pct": _round_or_none(_realized_vol(rows, 20)),
                },
            }
        )

    fundamental_snapshots: list[dict[str, Any]] = []
    for symbol in tickers[:8]:
        latest_fundamental = repository.latest_fundamentals(symbol, db_path=db_path)
        if not latest_fundamental:
            fundamental_snapshots.append(
                {
                    "ticker": symbol,
                    "display_name": symbol_display_name(symbol),
                    "status": "missing",
                    "freshness_status": "unknown",
                }
            )
            continue
        snapshot = latest_fundamental.get("snapshot") or {}
        valuation = latest_fundamental.get("valuation") or {}
        financials = latest_fundamental.get("financials") or {}
        fundamental_snapshots.append(
            {
                "ticker": symbol,
                "display_name": snapshot.get("name") or symbol_display_name(symbol),
                "status": "ok",
                "as_of": latest_fundamental.get("as_of"),
                "source": latest_fundamental.get("source") or "data_mart:fundamentals",
                "freshness_status": _freshness(latest_fundamental.get("as_of"), stale_after_days=30),
                "profile": {
                    "quote_type": snapshot.get("quote_type"),
                    "currency": snapshot.get("currency"),
                    "exchange": snapshot.get("exchange_name"),
                    "sector": snapshot.get("sector"),
                    "industry": snapshot.get("industry"),
                },
                "valuation": {
                    "price": valuation.get("price"),
                    "market_cap": valuation.get("market_cap"),
                    "trailing_pe": valuation.get("trailing_pe"),
                    "forward_pe": valuation.get("forward_pe"),
                    "price_to_book": valuation.get("price_to_book"),
                    "dividend_yield": valuation.get("dividend_yield"),
                    "beta": valuation.get("beta"),
                    "analyst_target_mean": valuation.get("analyst_target_mean"),
                },
                "financials": {
                    "total_revenue": financials.get("total_revenue"),
                    "profit_margin": financials.get("profit_margin"),
                    "gross_margin": financials.get("gross_margin"),
                    "operating_margin": financials.get("operating_margin"),
                    "return_on_equity": financials.get("return_on_equity"),
                    "revenue_growth": financials.get("revenue_growth"),
                    "earnings_growth": financials.get("earnings_growth"),
                    "free_cashflow": financials.get("free_cashflow"),
                    "total_cash": financials.get("total_cash"),
                    "total_debt": financials.get("total_debt"),
                    "debt_to_equity": financials.get("debt_to_equity"),
                    "total_assets": financials.get("total_assets"),
                    "net_assets": financials.get("net_assets"),
                    "expense_ratio": financials.get("expense_ratio"),
                },
            }
        )

    fingpt_annotations = _recent_fingpt_annotations(tickers[0], db_path) if tickers else []

    macro_snapshots: list[dict[str, Any]] = []
    for series_id in DEFAULT_US_MACRO_SERIES:
        latest = repository.latest_macro(series_id, db_path=db_path)
        if not latest:
            continue
        macro_snapshots.append(
            {
                "series_id": series_id,
                "title": latest.get("title") or series_id,
                "value": latest.get("value"),
                "unit": latest.get("units") or "",
                "as_of": latest.get("date"),
                "source": latest.get("source"),
                "freshness_status": _freshness(latest.get("date"), stale_after_days=7),
            }
        )

    health = repository.data_health(db_path=db_path)
    stale_count = sum(1 for item in [*price_snapshots, *macro_snapshots, *fundamental_snapshots] if item.get("freshness_status") == "stale")
    missing_count = sum(1 for item in price_snapshots if item.get("status") == "missing")
    missing_fundamentals_count = sum(1 for item in fundamental_snapshots if item.get("status") == "missing")
    has_numeric_data = (
        any(item.get("status") == "ok" for item in price_snapshots)
        or any(item.get("status") == "ok" for item in fundamental_snapshots)
        or bool(macro_snapshots)
    )
    has_context_data = has_numeric_data or bool(fingpt_annotations)
    status = "ok" if has_numeric_data and stale_count == 0 and missing_count == 0 else "partial"
    if not has_context_data:
        status = "no_data"
    return {
        "version": 1,
        "status": status,
        "target": tickers[0] if tickers else "",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "price_snapshot": price_snapshots,
        "fundamental_snapshot": fundamental_snapshots,
        "fingpt_annotations": fingpt_annotations,
        "macro_snapshot": macro_snapshots,
        "freshness": {
            "stale_count": stale_count,
            "missing_price_count": missing_count,
            "missing_fundamentals_count": missing_fundamentals_count,
            "price_count": len(price_snapshots),
            "fundamentals_count": len(fundamental_snapshots),
            "macro_count": len(macro_snapshots),
        },
        "data_quality_summary": {
            "latest_run": health.get("latest_run"),
            "recent_quality_checks": health.get("recent_quality_checks", [])[:5],
            "recent_provider_status": health.get("recent_provider_status", [])[:5],
        },
        "policy": {
            "numeric_authority": "structured_data_mart",
            "document_role": "qualitative_interpretation_and_citations",
            "instruction": "Do not invent numbers; use structured context as authoritative numeric evidence.",
        },
    }


def structured_context_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    doc_id = _context_doc_id(context)
    for snapshot in context.get("price_snapshot") or []:
        if snapshot.get("status") != "ok":
            continue
        ticker = snapshot.get("ticker") or ""
        as_of = snapshot.get("as_of") or "unknown"
        source = snapshot.get("source") or "data_mart"
        if snapshot.get("adjusted_close") is not None:
            metrics.append(
                _metric(
                    f"{ticker} data-mart adjusted close",
                    snapshot["adjusted_close"],
                    "price",
                    as_of,
                    "Stored adjusted close from local data mart.",
                    source,
                    snapshot.get("freshness_status"),
                    doc_id,
                )
            )
        for key, value in (snapshot.get("returns") or {}).items():
            if value is not None:
                metrics.append(
                    _metric(
                        f"{ticker} {key}",
                        value,
                        "%",
                        as_of,
                        "Stored price series return calculation.",
                        "data_mart:prices_daily",
                        snapshot.get("freshness_status"),
                        doc_id,
                    )
                )
        vol = (snapshot.get("risk") or {}).get("realized_vol_20d_pct")
        if vol is not None:
            metrics.append(
                _metric(
                    f"{ticker} realized_vol_20d_pct",
                    vol,
                    "%",
                    as_of,
                    "Annualized volatility from stored daily prices.",
                    "data_mart:prices_daily",
                    snapshot.get("freshness_status"),
                    doc_id,
            )
        )
    for snapshot in context.get("fundamental_snapshot") or []:
        if snapshot.get("status") != "ok":
            continue
        ticker = snapshot.get("ticker") or ""
        as_of = snapshot.get("as_of") or "unknown"
        source = snapshot.get("source") or "data_mart:fundamentals"
        for group_name in ("valuation", "financials"):
            for key, value in (snapshot.get(group_name) or {}).items():
                if value is None:
                    continue
                metrics.append(
                    _metric(
                        f"{ticker} {key}",
                        value,
                        "provider_snapshot",
                        as_of,
                        f"Stored {group_name} field from normalized fundamentals data mart.",
                        source,
                        snapshot.get("freshness_status"),
                        doc_id,
                    )
                )
    for snapshot in context.get("macro_snapshot") or []:
        if snapshot.get("value") is None:
            continue
        metrics.append(
            _metric(
                f"{snapshot.get('series_id')} latest",
                snapshot.get("value"),
                snapshot.get("unit") or "",
                snapshot.get("as_of") or "unknown",
                str(snapshot.get("title") or "Stored macro observation."),
                snapshot.get("source") or "data_mart:macro_observations",
                snapshot.get("freshness_status"),
                doc_id,
            )
        )
    return metrics


def structured_context_to_retrieval_item(context: dict[str, Any]) -> RetrievalItem | None:
    if not context or context.get("status") == "no_data":
        return None
    doc_id = _context_doc_id(context)
    as_of = _context_as_of(context)
    text = (
        "STRUCTURED DATA MART CONTEXT\n"
        "Numeric policy: use this structured context as authoritative numeric evidence. "
        "Do not invent numbers. Use RAG documents only for qualitative interpretation and citations.\n"
        f"{json.dumps(context, ensure_ascii=False, sort_keys=True)}"
    )
    metadata = {
        "doc_id": doc_id,
        "parent_doc_id": doc_id,
        "doc_type": "structured_context",
        "source_type": "data_mart",
        "current_run_safe": True,
    }
    annotations = context.get("fingpt_annotations")
    if isinstance(annotations, list) and annotations:
        metadata["fingpt_annotations"] = annotations
    return RetrievalItem(
        source="data_mart:structured",
        title=f"Structured data mart context for {context.get('target') or 'request'}",
        date=as_of,
        chunk=text,
        score=1.0,
        metadata=metadata,
    )


def _metric(
    name: str,
    value: Any,
    unit: str,
    as_of: str,
    context: str,
    source: str,
    freshness_status: str | None,
    doc_id: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": str(value),
        "unit": unit,
        "as_of": as_of,
        "context": context,
        "source": source,
        "source_type": "structured_data",
        "calculation_method": "data_mart_snapshot",
        "is_deterministic": True,
        "grounding_status": "grounded",
        "freshness_status": freshness_status or "unknown",
        "evidence_doc_ids": [doc_id],
    }


def _context_doc_id(context: dict[str, Any]) -> str:
    target = str(context.get("target") or "GLOBAL").upper().strip()
    generated = str(context.get("generated_at") or "")[:10]
    return f"data_mart:{target}:{generated}"


def _context_as_of(context: dict[str, Any]) -> str:
    dates: list[str] = []
    for item in context.get("price_snapshot") or []:
        if item.get("as_of"):
            dates.append(str(item["as_of"]))
    for item in context.get("fundamental_snapshot") or []:
        if item.get("as_of"):
            dates.append(str(item["as_of"]))
    for item in context.get("macro_snapshot") or []:
        if item.get("as_of"):
            dates.append(str(item["as_of"]))
    return max(dates) if dates else str(context.get("generated_at") or "unknown")
