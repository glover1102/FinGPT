import re

from core.schemas.request import (
    AnalysisRequest,
    DISABLED_COLLECTION_SOURCES,
    KNOWN_COLLECTION_SOURCES,
)
from core.utils.asset_classifier import classify

# Allowed characters in a ticker. We added ``=`` so Yahoo-style futures/FX
# symbols (``GC=F``, ``EURUSD=X``) pass format validation; the length was
# bumped from 10 → 12 to accommodate ``EURUSD=X`` and friends without making
# the rule noisy enough to let raw sentences through.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-=]{1,12}$")


def run_execution_precheck(request: AnalysisRequest) -> str | None:
    """
    Validates the basic admissibility of the analysis request payload before execution.
    Returns an error message string if a check fails, otherwise None representing success.
    """
    # Rule 1: Ticker format validation
    # This only verifies format admissibility, NOT actual market existence.
    ticker = str(request.ticker or "").strip()
    if not ticker:
        return "Ticker is required for the single-ticker research pipeline."
    if not _TICKER_RE.match(ticker):
        return (
            f"Ticker format invalid: '{ticker}' must be 1-12 uppercase alphanumeric "
            "characters (., -, = allowed). "
            "(Note: this only verifies formatting, not market validity)."
        )

    # Rule 2: Minimum source validation
    if not request.sources:
        return "At least one data source must be specified."

    normalized_sources: list[str] = []
    seen: set[str] = set()
    for source in request.sources:
        cleaned = str(source).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized_sources.append(cleaned)

    unsupported = [source for source in normalized_sources if source not in KNOWN_COLLECTION_SOURCES]
    if unsupported:
        unsupported_text = ", ".join(unsupported)
        return f"Unsupported source(s): {unsupported_text}. Supported sources are: {', '.join(KNOWN_COLLECTION_SOURCES)}."

    active_sources = [source for source in normalized_sources if source not in DISABLED_COLLECTION_SOURCES]
    if not active_sources:
        disabled_text = ", ".join(sorted(DISABLED_COLLECTION_SOURCES))
        return (
            f"Requested sources are disabled in the production collector: {disabled_text}. "
            "At least one active source must be specified."
        )

    # Rule 3: Lookback days limit (e.g., prevent absurd context windows blowing up APIs)
    if not (1 <= request.lookback_days <= 3650):
        return f"Lookback days ({request.lookback_days}) must be between 1 and 3650 days."

    # Rule 4: Asset-class source compatibility.
    # Reject combinations that cannot possibly produce grounded context so the
    # user gets a clear error instead of a confusing ``partial`` result. We
    # only reject when *every* requested source is incompatible; mixed
    # requests still proceed so the pipeline can gather what it can.
    profile = classify(ticker)
    incompatible = [
        source for source in active_sources
        if not _source_compatible_with_profile(source, profile)
    ]
    if incompatible and len(incompatible) == len(active_sources):
        incompat_text = ", ".join(incompatible)
        return (
            f"Asset class '{profile.asset_class}' does not support the requested "
            f"source(s): {incompat_text}. "
            "Try: " + ", ".join(_suggested_sources(profile)) + "."
        )

    return None


def _source_compatible_with_profile(source: str, profile) -> bool:
    if source == "news":
        # Equity news stack handles most tickers; forex/futures/crypto use the
        # macro bundle for news instead of the equity providers.
        return profile.supports_equity_sources or profile.supports_macro
    if source == "transcript":
        return profile.supports_transcripts
    if source == "macro":
        # For equity-like symbols the collector maps the macro source to a
        # deterministic yfinance technical snapshot, so macro-only requests
        # should not fail before the data-mart fallback can run.
        return profile.supports_macro or profile.supports_equity_sources
    # Unknown source — let the upstream validator reject it.
    return True


def _suggested_sources(profile) -> list[str]:
    hints: list[str] = []
    if profile.supports_equity_sources:
        hints.append("news")
    if profile.supports_transcripts:
        hints.append("transcript")
    if profile.supports_macro:
        hints.append("macro")
    return hints or ["news"]
