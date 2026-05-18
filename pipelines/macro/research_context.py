from __future__ import annotations

import json
from core.schemas.macro import MacroOverview, MacroResearchContext
from core.schemas.retrieval import RetrievalItem
from pipelines.macro.asset_impact import get_asset_impacts
from pipelines.macro.portfolio_hints import get_portfolio_policy_hint


TICKER_RELEVANCE: dict[str, list[str]] = {
    "TLT": ["DGS10", "DFII10", "CPIAUCSL", "CPILFESL", "FEDFUNDS", "T10Y2Y", "T10Y3M"],
    "QQQ": ["DGS10", "DFII10", "M2SL", "WALCL", "VIXCLS"],
    "GLD": ["DFII10", "DTWEXBGS", "CPIAUCSL", "T10YIE", "VIXCLS"],
    "XLE": ["PPIACO", "INDPRO", "DTWEXBGS", "CPIAUCSL"],
    "JPM": ["T10Y2Y", "T10Y3M", "BAMLH0A0HYM2", "BAMLC0A0CM", "FEDFUNDS"],
    "SPY": ["GDPC1", "INDPRO", "CPIAUCSL", "DGS10", "VIXCLS"],
    "NVDA": ["DGS10", "DFII10", "M2SL", "WALCL", "VIXCLS", "INDPRO"],
}


def get_research_context(overview: MacroOverview, ticker: str | None = None) -> MacroResearchContext:
    requested = str(ticker or "").upper().strip()
    relevance = dict(TICKER_RELEVANCE)
    if requested and requested not in relevance:
        relevance[requested] = ["GDPC1", "CPIAUCSL", "DGS10", "VIXCLS"]
    warnings = [
        *overview.data_quality.errors,
        *[f"missing:{item}" for item in overview.data_quality.missing_series],
        *[f"stale:{item}" for item in overview.data_quality.stale_series],
    ]
    return MacroResearchContext(
        regime=overview.regime,
        risk_level=overview.regime.risk_level,
        key_indicators=overview.key_indicators,
        signals=overview.signals,
        asset_impacts=get_asset_impacts(overview.regime, overview.signals),
        portfolio_hints=get_portfolio_policy_hint(overview.regime, overview.data_quality),
        ticker_relevance=relevance,
        data_quality_warnings=warnings,
    )


def compact_research_context(context: MacroResearchContext) -> dict:
    """Return a prompt-safe Macro payload without full observation histories."""

    payload = context.model_dump(mode="json")
    payload["key_indicators"] = [
        {
            "series_id": item.get("series_id"),
            "display_name": item.get("display_name"),
            "category": item.get("category"),
            "unit": item.get("unit"),
            "frequency": item.get("frequency"),
            "provider": item.get("provider"),
            "latest": item.get("latest"),
            "changes": item.get("changes") or {},
            "data_quality": item.get("data_quality") or {},
        }
        for item in payload.get("key_indicators") or []
    ]
    payload["policy"] = {
        "numeric_authority": "macro_platform_structured_payload",
        "document_role": "macro context and interpretation support",
        "instruction": "Do not invent macro indicator values; missing/stale data remains an uncertainty.",
        "portfolio_policy": "advisory_only_no_trade_orders",
    }
    return payload


def macro_research_context_to_retrieval_item(
    context: MacroResearchContext,
    *,
    ticker: str | None = None,
) -> RetrievalItem:
    target = str(ticker or "").upper().strip() or "GLOBAL"
    compact = compact_research_context(context)
    latest_dates = [
        str(item.latest.date)
        for item in context.key_indicators
        if item.latest is not None and item.latest.date
    ]
    date_value = max(latest_dates) if latest_dates else "unknown"
    doc_id = f"macro_platform:{target}:{date_value}"
    text = (
        "STRUCTURED MACRO PLATFORM CONTEXT\n"
        "Numeric policy: this payload is the only authorized macro-data source for the research prompt. "
        "Do not invent economic indicator values. Treat unavailable, missing, and stale data as uncertainty. "
        "Portfolio policy hints are advisory only and cannot create trade orders.\n"
        f"{json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str)}"
    )
    return RetrievalItem(
        source="macro:platform",
        title=f"Macro platform context for {target}",
        date=date_value,
        chunk=text,
        score=1.0,
        metadata={
            "doc_id": doc_id,
            "parent_doc_id": doc_id,
            "doc_type": "macro_platform_context",
            "source_type": "macro_platform",
            "current_run_safe": True,
            "data_quality_status": context.portfolio_hints.data_quality.status,
            "regime": context.regime.name,
            "risk_level": context.risk_level,
            "advisory_only": True,
        },
    )


def macro_research_context_metrics(context: MacroResearchContext, *, ticker: str | None = None) -> list[dict]:
    target = str(ticker or "").upper().strip() or "GLOBAL"
    latest_dates = [
        str(item.latest.date)
        for item in context.key_indicators
        if item.latest is not None and item.latest.date
    ]
    date_value = max(latest_dates) if latest_dates else "unknown"
    doc_id = f"macro_platform:{target}:{date_value}"
    metrics: list[dict] = []
    for item in context.key_indicators:
        if item.latest is None or item.latest.value is None:
            continue
        metrics.append(
            {
                "name": f"{item.series_id} latest",
                "value": str(item.latest.value),
                "unit": item.unit,
                "as_of": item.latest.date or "unknown",
                "context": f"{item.display_name} from Macro platform registry.",
                "source": item.latest.source or item.provider or "macro_platform",
                "source_type": "structured_macro_platform",
                "calculation_method": item.latest.metadata.get("transform") if item.latest.metadata else item.changes.get("transform"),
                "is_deterministic": True,
                "grounding_status": "grounded",
                "freshness_status": item.data_quality.status,
                "evidence_doc_ids": [doc_id],
            }
        )
    return metrics
