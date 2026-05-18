from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class RetrievalPlan(BaseModel):
    intent: str = "investment_research"
    asset_type: str = "unknown"
    lens: str = "general_financial_research"
    required_evidence_buckets: list[str] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""
    fallback_behavior: str = "Return partial output with actionable uncertainty when evidence is sparse."


_EQUITY_BUCKETS = [
    "revenue",
    "margins",
    "valuation",
    "product_cycle",
    "capital_return",
    "guidance",
    "risk_factors",
    "analyst_estimates",
]

_RATES_BUCKETS = [
    "price_action",
    "duration",
    "treasury_yields",
    "inflation",
    "fed_policy",
    "recession_risk",
    "real_yields",
    "scenario_risks",
]

_CRYPTO_BUCKETS = [
    "liquidity",
    "risk_appetite",
    "ETF_flows",
    "regulation",
    "technical_trend",
    "macro_correlation",
]

_COMMODITY_BUCKETS = [
    "spot_price",
    "dollar",
    "real_yields",
    "supply",
    "demand",
    "inventory",
    "curve_structure",
    "event_risk",
]

_FX_BUCKETS = [
    "rate_differential",
    "growth_differential",
    "inflation_differential",
    "central_bank_policy",
    "dollar_liquidity",
    "positioning",
    "technical_trend",
]

_CREDIT_BUCKETS = [
    "spread_proxy",
    "default_cycle",
    "liquidity",
    "equity_credit_divergence",
    "funding_conditions",
    "recession_risk",
    "scenario_risks",
]

_MACRO_BUCKETS = [
    "growth",
    "inflation",
    "rates",
    "liquidity",
    "credit_conditions",
    "earnings_cycle",
    "policy_risk",
]

_SECTOR_BUCKETS = [
    "demand_cycle",
    "capex",
    "pricing_power",
    "valuation",
    "competition",
    "beneficiaries",
    "at_risk_names",
]

_ETF_BUCKETS = [
    "price_action",
    "holdings_exposure",
    "factor_exposure",
    "flows",
    "valuation_proxy",
    "macro_sensitivity",
]

_KNOWN_EQUITIES = {
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "GOOG",
    "META",
    "TSLA",
    "JPM",
    "SPY",
    "QQQ",
    "BRK.B",
    "LLY",
    "AVGO",
}

_RATES_PROXIES = {"TLT", "IEF", "SHY", "BIL", "AGG", "BND", "^TNX", "^TYX", "^IRX"}
_CREDIT_PROXIES = {"HYG", "LQD", "JNK", "EMB"}
_COMMODITY_PROXIES = {"GLD", "SLV", "USO", "UNG", "DBC", "CL=F", "GC=F", "SI=F"}
_CRYPTO_PROXIES = {"BTC", "BTC-USD", "ETH", "ETH-USD"}
_FX_PROXIES = {"EURUSD=X", "JPY=X", "DX-Y.NYB", "DXY", "GBPUSD=X", "KRW=X"}


def _normalize_ticker(ticker: str | None) -> str:
    return str(ticker or "").strip().upper()


def _contains(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _sub_queries(question: str, ticker: str, buckets: list[str]) -> list[str]:
    target = ticker or "target"
    base = str(question or "").strip()
    return [f"{target} {bucket} evidence for: {base}" for bucket in buckets[:8]]


def plan_query(ticker: str | None = None, question: str | None = None, mode_hint: str | None = None) -> RetrievalPlan:
    """Create an additive retrieval plan for diagnostics and evidence coverage.

    The plan is intentionally heuristic and deterministic. It does not replace
    existing routing; it makes the research lens and missing-bucket policy
    visible without weakening current-run-only retrieval.
    """

    symbol = _normalize_ticker(ticker)
    text = f"{symbol} {question or ''}".strip()
    mode = str(mode_hint or "").strip().lower()

    if mode == "topic" and not symbol:
        asset_type = "macro_topic"
        lens = "macro"
        buckets = _MACRO_BUCKETS
        reason = "tickerless topic request routed to macro/general research lens"
    elif symbol in _RATES_PROXIES or _contains(text, ["tlt", "yield", "duration", "treasury", "term premium", "fed", "금리", "채권", "국채", "듀레이션", "실질금리", "기간 프리미엄"]):
        asset_type = "bond_etf" if symbol else "rates_topic"
        lens = "rates_bonds"
        buckets = _RATES_BUCKETS
        reason = "rates/bonds keywords or proxy ticker detected"
    elif symbol in _CREDIT_PROXIES or _contains(text, ["credit", "spread", "default", "hyg", "lqd", "신용", "스프레드", "부도", "회사채"]):
        asset_type = "credit_proxy" if symbol else "credit_topic"
        lens = "credit"
        buckets = _CREDIT_BUCKETS
        reason = "credit-risk ticker or question terms detected"
    elif symbol in _CRYPTO_PROXIES or _contains(text, ["btc", "bitcoin", "crypto", "ethereum", "비트코인", "암호화폐", "이더리움", "etf flow"]):
        asset_type = "crypto"
        lens = "crypto"
        buckets = _CRYPTO_BUCKETS
        reason = "crypto ticker or liquidity/regulation terms detected"
    elif symbol in _FX_PROXIES or re.search(r"[A-Z]{3}USD=X", symbol) or _contains(text, ["fx", "currency", "dollar", "eurusd", "환율", "달러", "유로", "금리차"]):
        asset_type = "fx"
        lens = "fx"
        buckets = _FX_BUCKETS
        reason = "FX ticker or currency terms detected"
    elif symbol in _COMMODITY_PROXIES or _contains(text, ["gold", "oil", "commodity", "inventory", "원자재", "금 ", "유가", "원유", "재고", "선물곡선"]):
        asset_type = "commodity"
        lens = "commodity"
        buckets = _COMMODITY_BUCKETS
        reason = "commodity proxy or supply/demand terms detected"
    elif _contains(text, ["sector", "theme", "ai", "semiconductor", "cloud", "섹터", "테마", "반도체", "클라우드"]):
        asset_type = "sector_theme" if not symbol else "equity_or_theme"
        lens = "sector_theme" if not symbol else "equities_fundamental"
        buckets = _SECTOR_BUCKETS if not symbol else _EQUITY_BUCKETS
        reason = "sector/theme terms detected"
    elif symbol in {"SPY", "QQQ", "DIA", "IWM"}:
        asset_type = "equity_index_etf"
        lens = "etf"
        buckets = _ETF_BUCKETS
        reason = "broad ETF proxy detected"
    elif symbol:
        asset_type = "equity"
        lens = "equities_fundamental"
        buckets = _EQUITY_BUCKETS
        reason = "explicit ticker treated as operating-company equity unless classified otherwise"
    elif _contains(text, ["macro", "market", "risk", "rates", "inflation", "liquidity", "거시", "시장", "리스크", "인플레이션", "유동성"]):
        asset_type = "macro_topic"
        lens = "macro"
        buckets = _MACRO_BUCKETS
        reason = "tickerless macro/risk question detected"
    else:
        asset_type = "general_topic"
        lens = "general_financial_research"
        buckets = ["market_context", "evidence", "risk_factors", "scenario_risks", "monitoring_indicators"]
        reason = "fallback general financial research lens"

    return RetrievalPlan(
        intent="investment_research",
        asset_type=asset_type,
        lens=lens,
        required_evidence_buckets=list(buckets),
        sub_queries=_sub_queries(question or "", symbol, list(buckets)),
        reasoning_summary=reason,
        fallback_behavior="Return status=partial with explicit missing evidence buckets when coverage is weak.",
    )


def plan_to_dict(plan: RetrievalPlan | dict[str, Any] | None) -> dict[str, Any]:
    if plan is None:
        return {}
    if isinstance(plan, RetrievalPlan):
        return plan.model_dump(mode="json")
    return dict(plan)
