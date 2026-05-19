from __future__ import annotations

import json
import re
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, Field

from core.config.settings import load_settings
from core.utils.asset_classifier import classify
from core.utils.logger import get_logger
from core.utils.symbol_registry import known_symbol_tickers, resolve_symbol_aliases

logger = get_logger("pipelines.router")


class RoutedQuery(BaseModel):
    mode: Literal["single_ticker", "multi_ticker", "sector_macro", "concept"]
    tickers: list[str] = Field(default_factory=list)
    theme: Optional[str] = None
    horizon: Literal["short_term", "medium_term", "unspecified"] = "unspecified"
    reasoning: str


_CORE_KNOWN_TICKERS = {
    "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "GOOG", "AMZN", "META",
    "JPM", "GS", "SPY", "QQQ", "XLK", "SOXX", "SMH", "TLT", "IEF", "SHY", "AGG", "LQD", "HYG",
    "USO", "GLD", "SLV", "ASML", "AMAT", "KLAC", "INTC", "AMD",
    "BTC-USD", "ETH-USD", "EURUSD=X", "DXY", "CL=F",
    "114800.KS", "252670.KS", "251340.KS", "EWY",
}
_KNOWN_TICKERS = _CORE_KNOWN_TICKERS | known_symbol_tickers()
_NON_EQUITY_PROXY_TICKERS = {
    "TLT", "IEF", "SHY", "AGG", "LQD", "HYG",
    "GLD", "SLV", "USO", "CL=F",
    "EURUSD=X", "DXY",
    "BTC-USD", "ETH-USD",
}
_RATES_INTENT_TERMS = [
    "bond", "bonds", "treasury", "treasuries", "yield", "yield curve",
    "real yield", "term premium", "duration", "fed path", "long-end",
    "treasury supply",
    "금리", "채권", "국채", "장기채", "장기금리", "실질금리", "장단기", "듀레이션",
    "연준 경로", "정책금리", "기간 프리미엄", "국채 공급", "금리차",
]
_FX_INTENT_TERMS = [
    "eurusd", "eur/usd", "fx", "forex", "dollar", "euro", "usd",
    "rate differential", "policy divergence",
    "환율", "달러", "유로", "외환", "금리차", "정책 차별화",
]
_CRYPTO_INTENT_TERMS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "etf flow",
    "비트코인", "이더리움", "크립토", "암호화폐", "현물 etf",
]
_COMMODITY_INTENT_TERMS = [
    "gold", "oil", "crude", "wti", "commodity", "commodities", "inventory", "futures curve",
    "금값", "금 가격", "금 현물", "원유", "유가", "원자재", "재고", "선물곡선",
]
_CREDIT_INTENT_TERMS = [
    "credit risk", "credit risks", "credit spread", "credit spreads", "default risk",
    "corporate bond", "corporate bonds", "high yield", "investment grade", "spread widening",
    "신용 리스크", "신용위험", "신용 위험", "크레딧", "크레딧 리스크", "회사채",
    "하이일드", "투자등급", "스프레드", "부도 위험", "부실",
]
_RATES_INTENT_TERMS.extend(
    ["금리", "채권", "국채", "장기채", "장단기", "실질금리", "듀레이션", "연준", "기간 프리미엄", "국채 공급"]
)
_FX_INTENT_TERMS.extend(["환율", "달러", "유로", "금리차", "정책 차별화"])
_CRYPTO_INTENT_TERMS.extend(["비트코인", "이더리움", "암호화폐", "현물 ETF", "ETF flow"])
_COMMODITY_INTENT_TERMS.extend(["금 가격", "금값", "금 현물", "유가", "원유", "원자재", "재고", "선물곡선"])
_CREDIT_INTENT_TERMS.extend(["신용 리스크", "신용위험", "크레딧", "스프레드", "회사채", "하이일드", "투자등급", "부도 위험"])
_BROAD_MARKET_RISK_TERMS = [
    "market risk",
    "hidden risk",
    "ignored risk",
    "risk premium",
    "liquidity risk",
    "systemic risk",
    "broad market risk",
    "시장 리스크",
    "시장 위험",
    "시장이 무시",
    "무시하고 있는 리스크",
    "하방 리스크",
    "숨겨진 리스크",
    "위험 프리미엄",
    "유동성 리스크",
    "시스템 리스크",
]
_SECTOR_THEME_INTENT_TERMS = [
    "semiconductor",
    "semiconductors",
    "sector",
    "industry",
    "supply chain",
    "cloud",
    "\ubc18\ub3c4\uccb4",
    "\uc139\ud130",
    "\uc5c5\uc885",
    "\uacf5\uae09\ub9dd",
    "\ud074\ub77c\uc6b0\ub4dc",
]
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
_KOREA_INVERSE_RELATED_TICKERS = ["114800.KS", "252670.KS", "251340.KS", "EWY"]

_SIMPLE_TICKERS = {ticker for ticker in _CORE_KNOWN_TICKERS if re.fullmatch(r"[A-Z0-9]+", ticker)}
_TICKER_PATTERN = "|".join(sorted((re.escape(t) for t in _SIMPLE_TICKERS), key=len, reverse=True))
_TICKER_RE = re.compile(rf"(?<![A-Za-z0-9.$=-])({_TICKER_PATTERN})(?![A-Za-z0-9])", re.IGNORECASE)
_CATALOG_SIMPLE_TICKERS = {
    ticker for ticker in (known_symbol_tickers() - _CORE_KNOWN_TICKERS) if re.fullmatch(r"[A-Z0-9]+", ticker)
}
_CATALOG_TICKER_PATTERN = "|".join(
    sorted((re.escape(t) for t in _CATALOG_SIMPLE_TICKERS), key=len, reverse=True)
)
_CATALOG_TICKER_RE = re.compile(
    rf"(?<![A-Za-z0-9.$=-])({_CATALOG_TICKER_PATTERN})(?![A-Za-z0-9])"
) if _CATALOG_TICKER_PATTERN else None
_PUNCTUATED_TICKERS = {ticker for ticker in _KNOWN_TICKERS if not re.fullmatch(r"[A-Z0-9]+", ticker)}
_PUNCTUATED_TICKER_PATTERN = "|".join(
    sorted((re.escape(t) for t in _PUNCTUATED_TICKERS), key=len, reverse=True)
)
_PUNCTUATED_TICKER_RE = re.compile(
    rf"(?<![A-Za-z0-9])({_PUNCTUATED_TICKER_PATTERN})(?![A-Za-z0-9])",
    re.IGNORECASE,
) if _PUNCTUATED_TICKER_PATTERN else None
_SPECIAL_TICKER_PATTERNS = {
    "BTC-USD": re.compile(r"\b(?:btc(?:-usd)?|bitcoin)\b", re.IGNORECASE),
    "ETH-USD": re.compile(r"\b(?:eth(?:-usd)?|ethereum)\b", re.IGNORECASE),
    "EURUSD=X": re.compile(r"\b(?:eurusd(?:=x)?|eur/usd|euro\s*vs\s*dollar)\b", re.IGNORECASE),
    "CL=F": re.compile(r"\b(?:cl=f|wti|crude oil|oil futures)\b", re.IGNORECASE),
}
_EXPLICIT_TICKER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.$=-])(?P<marker>\$?)(?P<ticker>[A-Za-z][A-Za-z0-9]{0,9}(?:[.\-=][A-Za-z0-9]{1,8})?|\d{6}\.(?:KS|KQ))(?![A-Za-z0-9])"
)
_DIRECT_TICKER_ONLY_RE = re.compile(
    r"^\s*(?:\$?(?:[A-Za-z][A-Za-z0-9]{0,9}(?:[.\-=][A-Za-z0-9]{1,8})?|\d{6}\.(?:KS|KQ)))"
    r"(?:[\s,]+(?:outlook|analysis|analyze|view|전망|분석|주가|실적|리스크))*\s*$",
    re.IGNORECASE,
)
_CLASS_SHARE_DOT_RE = re.compile(r"^(?P<root>[A-Z]{1,5})\.(?P<class>[A-Z])$")
_SUPPORTED_EXPLICIT_TICKER_RE = re.compile(
    r"^(?:[A-Z]{3,5}(?:[.-][A-Z0-9]{1,4})?|[A-Z]{2,8}-USD|[A-Z]{6}=X|[A-Z]{1,3}=F|\d{6}\.(?:KS|KQ))$"
)
_SHORT_MARKED_TICKER_RE = re.compile(r"^[A-Z]{1,2}(?:[.-][A-Z0-9]{1,4})?$")
_UNREGISTERED_TICKER_STOPWORDS = {
    "AI", "API", "APP", "CEO", "CFO", "CPU", "CPI", "ETF", "EPS", "FED", "FOMC",
    "GDP", "GPU", "IPO", "KRX", "LLM", "MDD", "NAV", "NYSE", "PBR", "PER", "ROA",
    "ROE", "SEC", "USD",
}
_ALLOWED_MODES = {"single_ticker", "multi_ticker", "sector_macro", "concept"}
_HORIZON_ALIASES = {
    "short": "short_term",
    "short-term": "short_term",
    "short_term": "short_term",
    "near": "short_term",
    "near-term": "short_term",
    "near_term": "short_term",
    "medium": "medium_term",
    "medium-term": "medium_term",
    "medium_term": "medium_term",
    "mid": "medium_term",
    "mid-term": "medium_term",
    "long": "medium_term",
    "long-term": "medium_term",
    "long_term": "medium_term",
    "unspecified": "unspecified",
}


def _router_prompt(question: str, hint_ticker: str | None) -> str:
    hint = hint_ticker or ""
    return (
        "Classify the financial research request. Return only JSON with keys: "
        "mode, tickers, theme, horizon, reasoning.\n"
        "Allowed mode values: single_ticker, multi_ticker, sector_macro, concept.\n"
        "Allowed horizon values: short_term, medium_term, unspecified. "
        "Do not return long_term.\n"
        "Examples:\n"
        "Q: What are AAPL's near-term risks? -> {\"mode\":\"single_ticker\",\"tickers\":[\"AAPL\"],\"theme\":null,\"horizon\":\"short_term\",\"reasoning\":\"ticker-specific\"}\n"
        "Q: Compare AAPL and MSFT AI catalysts -> {\"mode\":\"multi_ticker\",\"tickers\":[\"AAPL\",\"MSFT\"],\"theme\":\"AI catalysts\",\"horizon\":\"unspecified\",\"reasoning\":\"comparison\"}\n"
        "Q: Fed path impact on growth stocks -> {\"mode\":\"sector_macro\",\"tickers\":[\"QQQ\",\"SPY\",\"XLK\"],\"theme\":\"Fed path and growth stocks\",\"horizon\":\"medium_term\",\"reasoning\":\"macro sector impact\"}\n"
        "Q: Why are semiconductor equipment stocks weak? -> {\"mode\":\"sector_macro\",\"tickers\":[\"AMAT\",\"ASML\",\"KLAC\"],\"theme\":\"semiconductor equipment weakness\",\"horizon\":\"unspecified\",\"reasoning\":\"sector theme\"}\n"
        "Q: What does oil backwardation mean? -> {\"mode\":\"concept\",\"tickers\":[\"USO\"],\"theme\":\"oil backwardation\",\"horizon\":\"unspecified\",\"reasoning\":\"market concept\"}\n"
        f"Ticker hint: {hint}\n"
        f"Question: {question}"
    )


def _call_router_model(question: str, hint_ticker: str | None) -> dict:
    settings = load_settings()
    model = getattr(settings, "router_model", None) or getattr(settings, "primary_model", "qwen2.5:7b")
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string"},
            "tickers": {"type": "array", "items": {"type": "string"}},
            "theme": {"type": ["string", "null"]},
            "horizon": {"type": "string"},
            "reasoning": {"type": "string"},
        },
        "required": ["mode", "tickers", "theme", "horizon", "reasoning"],
    }
    response = httpx.post(
        url,
        json={
            "model": model,
            "prompt": _router_prompt(question, hint_ticker),
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 256},
        },
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    return json.loads(payload.get("response") or "{}")


def _normalize_ticker_token(raw: object) -> str:
    ticker = str(raw or "").strip().upper().removeprefix("$")
    class_match = _CLASS_SHARE_DOT_RE.fullmatch(ticker)
    if class_match:
        if ticker in _KNOWN_TICKERS:
            return ticker
        return f"{class_match.group('root')}-{class_match.group('class')}"
    return ticker


def _is_supported_explicit_ticker(ticker: str, *, marked: bool = False) -> bool:
    ticker = _normalize_ticker_token(ticker)
    ticker = str(ticker or "").strip().upper()
    if not ticker or (ticker in _UNREGISTERED_TICKER_STOPWORDS and not marked):
        return False
    if ticker in _KNOWN_TICKERS:
        return True
    if _SUPPORTED_EXPLICIT_TICKER_RE.fullmatch(ticker):
        return True
    return marked and bool(_SHORT_MARKED_TICKER_RE.fullmatch(ticker))


def _clean_tickers(
    values: list[str],
    *,
    allow_unregistered: bool = False,
    explicit_unregistered: set[str] | None = None,
) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        ticker = _normalize_ticker_token(raw)
        if ticker in seen:
            continue
        if ticker not in _KNOWN_TICKERS:
            if explicit_unregistered and ticker in explicit_unregistered:
                pass
            elif not (allow_unregistered and _is_supported_explicit_ticker(ticker)):
                continue
        seen.add(ticker)
        cleaned.append(ticker)
    return cleaned


def _extract_explicit_unregistered_tickers(text: str) -> list[str]:
    haystack = str(text or "")
    found: list[str] = []
    for match in _EXPLICIT_TICKER_TOKEN_RE.finditer(haystack):
        raw = match.group("ticker") or ""
        ticker = _normalize_ticker_token(raw)
        if ticker in _KNOWN_TICKERS:
            continue
        marker = bool(match.group("marker"))
        next_char = haystack[match.end():match.end() + 1]
        colon_suffix = next_char in {":", "："}
        if not marker and not colon_suffix and raw != raw.upper():
            continue
        if _is_supported_explicit_ticker(ticker, marked=marker):
            found.append(ticker)
    return found


def _extract_literal_ticker_tokens(text: str) -> list[str]:
    haystack = str(text or "")
    found: list[str] = []
    for match in _EXPLICIT_TICKER_TOKEN_RE.finditer(haystack):
        raw = match.group("ticker") or ""
        ticker = _normalize_ticker_token(raw)
        marker = bool(match.group("marker"))
        next_char = haystack[match.end():match.end() + 1]
        colon_suffix = next_char in {":", "："}
        if not marker and not colon_suffix and raw != raw.upper():
            continue
        if ticker in _KNOWN_TICKERS or _is_supported_explicit_ticker(ticker, marked=marker):
            found.append(ticker)
    return found


def _leading_equity_literal_ticker(text: str) -> str:
    literal = _extract_literal_ticker_tokens(text)
    if not literal:
        return ""
    first = literal[0]
    try:
        profile = classify(first)
    except Exception:
        return ""
    if profile.asset_class in {"equity", "foreign_equity"} and not profile.is_etf:
        return first
    return ""


def _is_context_proxy_ticker(ticker: str) -> bool:
    try:
        profile = classify(ticker)
    except Exception:
        return False
    return profile.supports_macro and (not profile.supports_equity_sources or profile.asset_class != "equity" or profile.is_etf)


def _extract_known_tickers(text: str) -> list[str]:
    found = [match.group(1) for match in _TICKER_RE.finditer(str(text or ""))]
    haystack = str(text or "")
    if _CATALOG_TICKER_RE is not None:
        found.extend(match.group(1) for match in _CATALOG_TICKER_RE.finditer(haystack))
    if _PUNCTUATED_TICKER_RE is not None:
        found.extend(match.group(1) for match in _PUNCTUATED_TICKER_RE.finditer(haystack))
    for ticker, pattern in _SPECIAL_TICKER_PATTERNS.items():
        if pattern.search(haystack):
            found.append(ticker)
    literal_tokens = _extract_literal_ticker_tokens(haystack)
    found.extend(literal_tokens)
    if not (found and _DIRECT_TICKER_ONLY_RE.fullmatch(haystack)):
        found.extend(resolve_symbol_aliases(haystack))
    explicit_unregistered = [ticker for ticker in literal_tokens if ticker not in _KNOWN_TICKERS]
    leading_equity = _leading_equity_literal_ticker(haystack)
    if leading_equity:
        found = [
            ticker for ticker in found
            if ticker == leading_equity or not (_is_context_proxy_ticker(ticker) and ticker not in set(literal_tokens))
        ]
    return _clean_tickers(
        found,
        allow_unregistered=True,
        explicit_unregistered=set(explicit_unregistered),
    )


def extract_explicit_tickers(question: str) -> list[str]:
    return _extract_known_tickers(question)


def _normalise_horizon(value: object) -> Literal["short_term", "medium_term", "unspecified"]:
    raw = str(value or "unspecified").strip().lower()
    return _HORIZON_ALIASES.get(raw, "unspecified")  # type: ignore[return-value]


def _normalise_router_payload(raw: dict, question: str) -> dict:
    mode = str(raw.get("mode") or "").strip()
    if mode not in _ALLOWED_MODES:
        mode = "concept"

    tickers = raw.get("tickers") or []
    if not isinstance(tickers, list):
        tickers = []

    theme = raw.get("theme")
    if theme is not None:
        theme = str(theme).strip() or None

    return {
        "mode": mode,
        "tickers": _clean_tickers([str(t) for t in tickers]),
        "theme": theme or question[:120],
        "horizon": _normalise_horizon(raw.get("horizon")),
        "reasoning": str(raw.get("reasoning") or "router model"),
    }


def _merge_tickers(preferred: list[str], existing: list[str]) -> list[str]:
    return _clean_tickers([*preferred, *existing])


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _contains_korea_inverse_topic(original: str, lower: str) -> bool:
    return _contains_any(lower, _KOREA_MARKET_TERMS) and _contains_any(lower, _KOREA_INVERSE_TERMS)


def _contains_gold_intent(original: str, lower: str) -> bool:
    if any(term in lower for term in ("gold", "gld", "금값", "금 가격", "금 현물", "금 투자")):
        return True
    return re.search(r"(?<![가-힣])금(?!리|[가-힣])", original or "") is not None


def _contains_commodity_intent(original: str, lower: str) -> bool:
    if _contains_gold_intent(original, lower):
        return True
    return _contains_any(lower, [term for term in _COMMODITY_INTENT_TERMS if term not in {"금"}])


def _infer_horizon(question: str) -> Literal["short_term", "medium_term", "unspecified"]:
    q_lower = (question or "").lower()
    if _contains_any(q_lower, ["today", "next week", "short", "near-term", "\ub2e8\uae30"]):
        return "short_term"
    if _contains_any(q_lower, ["2026", "year", "12 month", "\uc911\uae30", "\uae08\ub9ac \uacbd\ub85c"]):
        return "medium_term"
    return "unspecified"


def _question_topic_intent_route(
    question: str,
    lower: str,
    horizon: Literal["short_term", "medium_term", "unspecified"],
) -> RoutedQuery | None:
    if _contains_any(lower, _CREDIT_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["HYG", "LQD", "TLT"],
            theme=question[:120] or "credit risk and corporate bond spreads",
            horizon=horizon,
            reasoning="question topic routed to credit-risk proxies before stale ticker hint",
        )
    if _contains_commodity_intent(question, lower):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["GLD", "USO"],
            theme=question[:120] or "commodity market regime",
            horizon=horizon,
            reasoning="question topic routed to commodity proxies before stale ticker hint",
        )
    if _contains_any(lower, _BROAD_MARKET_RISK_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["SPY", "QQQ", "HYG", "LQD", "TLT"],
            theme=question[:120] or "broad market risk regime",
            horizon=horizon,
            reasoning="broad market risk question topic routed to cross-asset proxies before stale ticker hint",
        )
    if _contains_any(lower, _RATES_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["TLT"],
            theme=question[:120] or "rates and bonds",
            horizon=horizon,
            reasoning="question topic routed to rates/bonds proxies before stale ticker hint",
        )
    if _contains_any(lower, _FX_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["EURUSD=X"],
            theme=question[:120] or "fx and dollar regime",
            horizon=horizon,
            reasoning="question topic routed to fx proxies before stale ticker hint",
        )
    if _contains_any(lower, _CRYPTO_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["BTC-USD"],
            theme=question[:120] or "crypto market regime",
            horizon=horizon,
            reasoning="question topic routed to crypto proxies before stale ticker hint",
        )
    if _contains_any(lower, _SECTOR_THEME_INTENT_TERMS):
        if _contains_any(lower, ["semiconductor", "semiconductors", "\ubc18\ub3c4\uccb4", "\uacf5\uae09\ub9dd"]):
            tickers = ["AMAT", "ASML", "KLAC"]
            reasoning = "question topic routed to semiconductor proxies before stale ticker hint"
        elif _contains_any(lower, ["cloud", "\ud074\ub77c\uc6b0\ub4dc"]):
            tickers = ["MSFT", "AMZN", "GOOGL"]
            reasoning = "question topic routed to cloud platform proxies before stale ticker hint"
        else:
            tickers = ["SPY", "QQQ", "XLK"]
            reasoning = "question topic routed to broad sector proxies before stale ticker hint"
        return RoutedQuery(
            mode="sector_macro",
            tickers=tickers,
            theme=question[:120] or "sector theme",
            horizon=horizon,
            reasoning=reasoning,
        )
    return None


def _korea_market_inverse_route(question: str, hint_ticker: str | None = None) -> RoutedQuery | None:
    q = question or ""
    q_lower = q.lower()
    if not _contains_korea_inverse_topic(q, q_lower):
        return None

    explicit = _extract_known_tickers(q)
    tickers = _merge_tickers(explicit, _KOREA_INVERSE_RELATED_TICKERS)
    return RoutedQuery(
        mode="sector_macro",
        tickers=tickers[:5],
        theme=q[:120] or "KOSPI inverse ETF timing",
        horizon=_infer_horizon(q),
        reasoning="korean market inverse topic routed before stale ticker hint",
    )


def _explicit_ticker_route(question: str, hint_ticker: str | None = None) -> RoutedQuery | None:
    found = _extract_known_tickers(question)
    hinted = _clean_tickers([hint_ticker]) if hint_ticker else []
    if hinted and not found:
        found = hinted

    horizon = _infer_horizon(question)
    if len(found) == 1:
        return RoutedQuery(
            mode="single_ticker",
            tickers=found,
            theme=None,
            horizon=horizon,
            reasoning="explicit ticker detected",
        )
    if len(found) > 1:
        return RoutedQuery(
            mode="multi_ticker",
            tickers=found[:5],
            theme=None,
            horizon=horizon,
            reasoning="explicit tickers detected",
        )
    return None


def _non_equity_intent_route(question: str, hint_ticker: str | None = None) -> RoutedQuery | None:
    """Route proxy assets to topic analysis before the single-ticker shortcut.

    TLT/GLD/BTC/EURUSD style tickers are not operating companies. Treating them
    as ordinary equity tickers produces shallow or brittle reports because the
    right playbook is macro, market structure, and scenario analysis.
    """

    q = question or ""
    q_lower = q.lower()
    found = _extract_known_tickers(q)
    if any(ticker not in _NON_EQUITY_PROXY_TICKERS for ticker in found):
        return None
    hinted = _clean_tickers([hint_ticker]) if hint_ticker else []
    related = _merge_tickers(found, hinted)
    non_equity = [ticker for ticker in related if ticker in _NON_EQUITY_PROXY_TICKERS]
    horizon = _infer_horizon(q)

    concept_like = _contains_any(q_lower, ["what does", "explain", "mean", "meaning", "뜻", "의미", "설명"])
    if not non_equity and concept_like:
        return None

    if not found:
        topic_route = _question_topic_intent_route(q, q_lower, horizon)
        if topic_route is not None:
            return topic_route

    if any(ticker in {"TLT", "IEF", "SHY", "AGG", "LQD", "HYG"} for ticker in non_equity):
        tickers = _merge_tickers(non_equity or ["TLT"], ["TLT"])
        return RoutedQuery(
            mode="sector_macro",
            tickers=tickers[:5],
            theme=q[:120] or "rates and bonds",
            horizon=horizon,
            reasoning="rates/bonds proxy routed to topic playbook",
        )
    if any(ticker in {"EURUSD=X", "DXY"} for ticker in non_equity):
        tickers = _merge_tickers(non_equity or ["EURUSD=X"], ["EURUSD=X"])
        return RoutedQuery(
            mode="sector_macro",
            tickers=tickers[:5],
            theme=q[:120] or "fx and dollar regime",
            horizon=horizon,
            reasoning="fx proxy routed to topic playbook",
        )
    if any(ticker in {"BTC-USD", "ETH-USD"} for ticker in non_equity):
        tickers = _merge_tickers(non_equity or ["BTC-USD"], ["BTC-USD"])
        return RoutedQuery(
            mode="sector_macro",
            tickers=tickers[:5],
            theme=q[:120] or "crypto market regime",
            horizon=horizon,
            reasoning="crypto proxy routed to topic playbook",
        )
    if any(ticker in {"GLD", "SLV", "USO", "CL=F"} for ticker in non_equity):
        tickers = _merge_tickers(non_equity or ["GLD", "USO"], ["GLD", "USO"])
        return RoutedQuery(
            mode="sector_macro",
            tickers=tickers[:5],
            theme=q[:120] or "commodity market regime",
            horizon=horizon,
            reasoning="commodity proxy routed to topic playbook",
        )
    if _contains_any(q_lower, _CREDIT_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["HYG", "LQD", "TLT"],
            theme=q[:120] or "credit risk and corporate bond spreads",
            horizon=horizon,
            reasoning="credit-risk topic routed to corporate bond and rates proxies",
        )
    if _contains_commodity_intent(q, q_lower):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["GLD", "USO"],
            theme=q[:120] or "commodity market regime",
            horizon=horizon,
            reasoning="commodity proxy routed to topic playbook",
        )
    if _contains_any(q_lower, _BROAD_MARKET_RISK_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["SPY", "QQQ", "HYG", "LQD", "TLT"],
            theme=q[:120] or "broad market risk regime",
            horizon=horizon,
            reasoning="broad market risk topic routed to equity-credit-rates proxies",
        )
    if _contains_any(q_lower, _RATES_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["TLT"],
            theme=q[:120] or "rates and bonds",
            horizon=horizon,
            reasoning="rates/bonds proxy routed to topic playbook",
        )
    if _contains_any(q_lower, _FX_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["EURUSD=X"],
            theme=q[:120] or "fx and dollar regime",
            horizon=horizon,
            reasoning="fx proxy routed to topic playbook",
        )
    if _contains_any(q_lower, _CRYPTO_INTENT_TERMS):
        return RoutedQuery(
            mode="sector_macro",
            tickers=["BTC-USD"],
            theme=q[:120] or "crypto market regime",
            horizon=horizon,
            reasoning="crypto proxy routed to topic playbook",
        )
    if _contains_any(q_lower, _SECTOR_THEME_INTENT_TERMS):
        if _contains_any(q_lower, ["semiconductor", "semiconductors", "\ubc18\ub3c4\uccb4", "\uacf5\uae09\ub9dd"]):
            tickers = ["AMAT", "ASML", "KLAC"]
            reasoning = "semiconductor sector topic routed to supply-chain proxies"
        elif _contains_any(q_lower, ["cloud", "\ud074\ub77c\uc6b0\ub4dc"]):
            tickers = ["MSFT", "AMZN", "GOOGL"]
            reasoning = "cloud sector topic routed to platform proxies"
        else:
            tickers = ["SPY", "QQQ", "XLK"]
            reasoning = "sector/theme topic routed to broad market proxies"
        return RoutedQuery(
            mode="sector_macro",
            tickers=tickers,
            theme=q[:120] or "sector theme",
            horizon=horizon,
            reasoning=reasoning,
        )
    return None


def should_route_hint_as_topic(question: str, hint_ticker: str | None = None) -> bool:
    return _korea_market_inverse_route(question) is not None or _non_equity_intent_route(question, hint_ticker) is not None


def _augment_theme_tickers(routed: RoutedQuery, question: str) -> RoutedQuery:
    text = f"{question} {routed.theme or ''}".lower()
    if routed.mode == "sector_macro":
        if _contains_korea_inverse_topic(f"{question} {routed.theme or ''}", text):
            routed.tickers = _merge_tickers(_KOREA_INVERSE_RELATED_TICKERS, routed.tickers)
        elif _contains_any(text, _CREDIT_INTENT_TERMS):
            routed.tickers = _merge_tickers(["HYG", "LQD", "TLT"], routed.tickers)
        elif _contains_any(text, ["semiconductor", "\ubc18\ub3c4\uccb4", "\ud6c4\uacf5\uc815"]):
            routed.tickers = _merge_tickers(["AMAT", "ASML", "KLAC"], routed.tickers)
        elif _contains_any(text, ["bond", "treasury", "yield curve", "real yield", "term premium", "duration", "\uad6d\ucc44", "\ucc44\uad8c", "\uae08\ub9ac"]):
            routed.tickers = _merge_tickers(["TLT"], routed.tickers)
        elif _contains_any(text, ["eurusd", "eur/usd", "dollar", "fx", "\ud658\uc728", "\ub2ec\ub7ec"]):
            routed.tickers = _merge_tickers(["EURUSD=X"], routed.tickers)
        elif _contains_any(text, ["bitcoin", "btc", "crypto", "\ube44\ud2b8\ucf54\uc778", "\uc554\ud638\ud654\ud3d0"]):
            routed.tickers = _merge_tickers(["BTC-USD"], routed.tickers)
        elif _contains_commodity_intent(f"{question} {routed.theme or ''}", text):
            routed.tickers = _merge_tickers(["GLD", "USO"], routed.tickers)
        elif _contains_any(text, ["fed", "growth", "\uae08\ub9ac", "\uc131\uc7a5\uc8fc"]):
            routed.tickers = _merge_tickers(["QQQ", "SPY", "XLK"], routed.tickers)
    elif routed.mode == "concept":
        if _contains_any(text, ["oil", "backwardation", "\uc6d0\uc720", "\ubc31\uc6cc\ub370\uc774\uc158"]):
            routed.tickers = _merge_tickers(["USO"], routed.tickers)
        elif _contains_any(text, ["yield curve", "real yield", "term premium", "duration", "\uc7a5\ub2e8\uae30", "\uc2e4\uc9c8\uae08\ub9ac"]):
            routed.tickers = _merge_tickers(["TLT"], routed.tickers)
        elif _contains_any(text, ["eurusd", "eur/usd", "dollar", "fx", "\ud658\uc728", "\ub2ec\ub7ec"]):
            routed.tickers = _merge_tickers(["EURUSD=X"], routed.tickers)
        elif _contains_any(text, ["bitcoin", "btc", "crypto", "\ube44\ud2b8\ucf54\uc778", "\uc554\ud638\ud654\ud3d0"]):
            routed.tickers = _merge_tickers(["BTC-USD"], routed.tickers)
    return routed


def _fallback_route(question: str, hint_ticker: str | None = None) -> RoutedQuery:
    q = question or ""
    korea_inverse = _korea_market_inverse_route(q)
    if korea_inverse is not None:
        korea_inverse.reasoning = f"{korea_inverse.reasoning} by fallback"
        return korea_inverse

    non_equity = _non_equity_intent_route(q, hint_ticker)
    if non_equity is not None:
        non_equity.reasoning = f"{non_equity.reasoning} by fallback"
        return non_equity

    explicit = _explicit_ticker_route(q, hint_ticker)
    if explicit is not None:
        explicit.reasoning = f"{explicit.reasoning} by fallback"
        return explicit

    q_lower = q.lower()
    horizon = _infer_horizon(q)

    macro_terms = [
        "sector", "industry", "fed", "growth stocks", "semiconductor", "ai", "cloud", "supply chain",
        "\uc139\ud130", "\uc5c5\uc885", "\uae08\ub9ac", "\uc131\uc7a5\uc8fc",
        "\ubc18\ub3c4\uccb4", "\ud6c4\uacf5\uc815", "\ud074\ub77c\uc6b0\ub4dc", "\uacf5\uae09\ub9dd",
    ]
    rates_terms = [
        "bond", "treasury", "yield curve", "real yield", "term premium", "duration",
        "\uad6d\ucc44", "\ucc44\uad8c", "\uc2e4\uc9c8\uae08\ub9ac", "\uc7a5\ub2e8\uae30",
    ]
    fx_terms = ["eurusd", "eur/usd", "fx", "dollar", "\ud658\uc728", "\ub2ec\ub7ec"]
    crypto_terms = ["bitcoin", "btc", "crypto", "\ube44\ud2b8\ucf54\uc778", "\uc554\ud638\ud654\ud3d0"]
    concept_terms = ["what does", "explain", "mean", "meaning", "\ub73b", "\uc758\ubbf8", "\uc124\uba85"]
    if _contains_any(q_lower, concept_terms):
        inferred: list[str] = []
        if _contains_any(q_lower, _CREDIT_INTENT_TERMS):
            inferred = ["HYG", "LQD", "TLT"]
        elif _contains_any(q_lower, rates_terms):
            inferred = ["TLT"]
        elif _contains_any(q_lower, fx_terms):
            inferred = ["EURUSD=X"]
        elif _contains_any(q_lower, crypto_terms):
            inferred = ["BTC-USD"]
        elif _contains_commodity_intent(q, q_lower) or _contains_any(q_lower, ["backwardation", "\uc6d0\uc720", "\ubc31\uc6cc\ub370\uc774\uc158"]):
            inferred = ["USO"]
        return RoutedQuery(mode="concept", tickers=inferred, theme=q[:120], horizon=horizon, reasoning="market concept fallback")
    if _contains_any(q_lower, macro_terms):
        inferred: list[str] = []
        if _contains_any(q_lower, _CREDIT_INTENT_TERMS):
            inferred = ["HYG", "LQD", "TLT"]
        elif _contains_any(q_lower, ["fed", "growth", "\uae08\ub9ac", "\uc131\uc7a5\uc8fc"]):
            inferred = ["QQQ", "SPY", "XLK"]
        elif _contains_any(q_lower, ["semiconductor", "ai", "supply chain", "\ubc18\ub3c4\uccb4", "\ud6c4\uacf5\uc815", "\uacf5\uae09\ub9dd"]):
            inferred = ["AMAT", "ASML", "KLAC"]
        return RoutedQuery(mode="sector_macro", tickers=inferred, theme=q[:120], horizon=horizon, reasoning="keyword sector/macro fallback")
    if _contains_any(q_lower, _BROAD_MARKET_RISK_TERMS):
        return RoutedQuery(mode="sector_macro", tickers=["SPY", "QQQ", "HYG", "LQD", "TLT"], theme=q[:120], horizon=horizon, reasoning="broad market risk fallback")
    if _contains_any(q_lower, rates_terms):
        return RoutedQuery(mode="sector_macro", tickers=["TLT"], theme=q[:120], horizon=horizon, reasoning="rates/bonds fallback")
    if _contains_any(q_lower, _CREDIT_INTENT_TERMS):
        return RoutedQuery(mode="sector_macro", tickers=["HYG", "LQD", "TLT"], theme=q[:120], horizon=horizon, reasoning="credit risk fallback")
    if _contains_any(q_lower, fx_terms):
        return RoutedQuery(mode="sector_macro", tickers=["EURUSD=X"], theme=q[:120], horizon=horizon, reasoning="fx fallback")
    if _contains_any(q_lower, crypto_terms):
        return RoutedQuery(mode="sector_macro", tickers=["BTC-USD"], theme=q[:120], horizon=horizon, reasoning="crypto fallback")
    if _contains_commodity_intent(q, q_lower):
        return RoutedQuery(mode="sector_macro", tickers=["GLD", "USO"], theme=q[:120], horizon=horizon, reasoning="commodity fallback")

    concept_terms = ["oil", "backwardation", "\uc6d0\uc720", "\ubc31\uc6cc\ub370\uc774\uc158"]
    inferred = ["USO"] if _contains_any(q_lower, concept_terms) else []
    return RoutedQuery(mode="concept", tickers=inferred, theme=q[:120], horizon=horizon, reasoning="concept fallback")


def route_query(question: str, hint_ticker: Optional[str] = None) -> RoutedQuery:
    if hint_ticker and not question.strip():
        ticker = _clean_tickers([hint_ticker])
        return RoutedQuery(mode="single_ticker", tickers=ticker, theme=None, reasoning="ticker hint only")

    korea_inverse = _korea_market_inverse_route(question)
    if korea_inverse is not None:
        return korea_inverse

    non_equity = _non_equity_intent_route(question, hint_ticker)
    if non_equity is not None:
        return non_equity

    explicit = _explicit_ticker_route(question, hint_ticker)
    if explicit is not None:
        return explicit

    try:
        raw = _call_router_model(question, hint_ticker)
        routed = RoutedQuery(**_normalise_router_payload(raw, question))
        routed = _augment_theme_tickers(routed, question)
        if hint_ticker and routed.mode in {"sector_macro", "concept"} and not routed.tickers:
            routed.tickers = _clean_tickers([hint_ticker])
        if routed.mode in {"single_ticker", "multi_ticker"} and not routed.tickers:
            raise ValueError("router selected ticker mode without valid tickers")
        return routed
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ROUTER] LLM route failed open to regex fallback: %s", exc)
        return _fallback_route(question, hint_ticker)
