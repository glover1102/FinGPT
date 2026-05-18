"""Asset-class classifier used by the collection router.

Why this exists
---------------
The original FinGPT collection stack was purpose-built for US single-name
equities (yfinance + FMP stock-news + FMP earnings-call transcripts + SEC
EDGAR). That stack is a bad fit for bonds, commodities, and FX: EDGAR has no
filings, FMP has no transcripts, and yfinance news is sparse.

Rather than guess at runtime, we classify the ticker string up front so the
collection orchestrator can pick the right providers AND the precheck layer
can keep rejecting clearly-invalid inputs.

Design constraints
------------------
- Pure-stdlib, zero new deps.
- Classification must be deterministic and offline (no network calls).
- Unknown tickers default to ``equity`` so existing user behavior stays intact.
- The classifier returns BOTH the class and a normalized form, because Yahoo's
  FX/futures symbols contain ``=`` which the old precheck regex rejected.
- ETF membership is tracked separately from asset class so the issuer-profile
  fetcher can run on any ETF (bond/commodity/broad-market) without altering
  the existing equity-or-macro routing decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

AssetClass = Literal[
    "equity",
    "forex",
    "futures",
    "bond_etf",
    "commodity_etf",
    "foreign_equity",
    "crypto",
]

# --- ETF issuer registry --------------------------------------------------
#
# The tuple value is ``(issuer, product_page_url)``. URLs point at the
# issuer's public product page; the ETF-profile collector reads these pages
# with trafilatura. Tickers absent from this table can still be fetched via
# the Yahoo Finance profile fallback inside the collector.
ETF_ISSUER_REGISTRY: dict[str, tuple[str, str]] = {
    # BlackRock / iShares -- bond
    "TLT":  ("iShares", "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf"),
    "IEF":  ("iShares", "https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf"),
    "SHY":  ("iShares", "https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf"),
    "AGG":  ("iShares", "https://www.ishares.com/us/products/239458/ishares-core-total-us-bond-market-etf"),
    "HYG":  ("iShares", "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf"),
    "LQD":  ("iShares", "https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf"),
    "TIP":  ("iShares", "https://www.ishares.com/us/products/239467/ishares-tips-bond-etf"),
    "EMB":  ("iShares", "https://www.ishares.com/us/products/239572/ishares-jp-morgan-usd-emerging-markets-bond-etf"),
    "GOVT": ("iShares", "https://www.ishares.com/us/products/239451/ishares-us-treasury-bond-etf"),
    "MBB":  ("iShares", "https://www.ishares.com/us/products/239465/ishares-mbs-etf"),
    "MUB":  ("iShares", "https://www.ishares.com/us/products/239766/ishares-national-muni-bond-etf"),
    # iShares -- commodity / broad
    "SLV":  ("iShares", "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"),
    "IAU":  ("iShares", "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund"),
    "IVV":  ("iShares", "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf"),
    "IWM":  ("iShares", "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf"),
    "EFA":  ("iShares", "https://www.ishares.com/us/products/239623/ishares-msci-eafe-etf"),
    "EEM":  ("iShares", "https://www.ishares.com/us/products/239637/ishares-msci-emerging-markets-etf"),
    # State Street / SPDR
    "SPY":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/spy"),
    "GLD":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/gld"),
    "DIA":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/dia"),
    "MDY":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/mdy"),
    "XLK":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlk"),
    "XLF":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlf"),
    "XLE":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xle"),
    "XLV":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlv"),
    "XLY":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xly"),
    "XLP":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlp"),
    "XLI":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xli"),
    "XLB":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlb"),
    "XLU":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlu"),
    "XLRE": ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlre"),
    "XLC":  ("SPDR",    "https://www.ssga.com/us/en/intermediary/etfs/xlc"),
    # Invesco
    "QQQ":  ("Invesco", "https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=QQQ"),
    "PDBC": ("Invesco", "https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=PDBC"),
    "DBC":  ("Invesco", "https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=DBC"),
    "DBA":  ("Invesco", "https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=DBA"),
    "DBB":  ("Invesco", "https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=DBB"),
    "CPER": ("Invesco", "https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=CPER"),
    "URA":  ("Global X","https://www.globalxetfs.com/funds/ura/"),
    # Vanguard
    "BND":  ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/bnd"),
    "VGIT": ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vgit"),
    "VGLT": ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vglt"),
    "VGSH": ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vgsh"),
    "VOO":  ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/voo"),
    "VTI":  ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vti"),
    "VEA":  ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vea"),
    "VWO":  ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vwo"),
    "VXUS": ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vxus"),
    "VIG":  ("Vanguard","https://investor.vanguard.com/investment-products/etfs/profile/vig"),
    # ARK
    "ARKK": ("ARK",     "https://www.ark-funds.com/funds/arkk/"),
    "ARKG": ("ARK",     "https://www.ark-funds.com/funds/arkg/"),
    "ARKW": ("ARK",     "https://www.ark-funds.com/funds/arkw/"),
    "ARKF": ("ARK",     "https://www.ark-funds.com/funds/arkf/"),
    "ARKQ": ("ARK",     "https://www.ark-funds.com/funds/arkq/"),
    # Schwab Asset Management
    "SCHD": ("Schwab",  "https://www.schwabassetmanagement.com/products/schd"),
    "SCHZ": ("Schwab",  "https://www.schwabassetmanagement.com/products/schz"),
    "SCHB": ("Schwab",  "https://www.schwabassetmanagement.com/products/schb"),
    # JPMorgan Asset Management
    "JEPI": ("J.P. Morgan", "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-equity-premium-income-etf-etf-shares-46641q332"),
    "JEPQ": ("J.P. Morgan", "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-nasdaq-equity-premium-income-etf-etf-shares-46641q845"),
    # Commodity trust specials
    "USO":  ("USCF",    "https://www.uscfinvestments.com/uso"),
    "UNG":  ("USCF",    "https://www.uscfinvestments.com/ung"),
}


# Bond ETF basket (used by the asset-class classifier + FRED series map).
_BOND_ETFS: frozenset[str] = frozenset({
    "TLT", "IEF", "SHY", "BND", "AGG", "HYG", "LQD", "TIP", "BIL",
    "GOVT", "MUB", "EMB", "MBB", "SCHZ", "VGIT", "VGLT", "VGSH",
})

_COMMODITY_ETFS: frozenset[str] = frozenset({
    "GLD", "SLV", "IAU", "USO", "UNG", "PDBC", "DBC", "DBA", "DBB",
    "CPER", "WEAT", "CORN", "SOYB", "URA", "COPX", "GDX", "GDXJ",
})

# Broad-market / sector ETFs that still classify as equity (so FMP stock news
# keeps working) but should also run through the ETF-profile fetcher.
_EQUITY_ETFS: frozenset[str] = frozenset({
    "SPY", "VOO", "IVV", "VTI", "QQQ", "DIA", "MDY", "IWM",
    "EFA", "EEM", "VEA", "VWO", "VXUS", "VIG",
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC",
    "SOXX", "SMH", "ARKK", "ARKG", "ARKW", "ARKF", "ARKQ",
    "SCHD", "SCHB", "JEPI", "JEPQ",
})

_ALL_ETFS: frozenset[str] = _BOND_ETFS | _COMMODITY_ETFS | _EQUITY_ETFS

# Forex pairs use the Yahoo convention: ``<BASE><QUOTE>=X`` — 6 letters + ``=X``.
_FOREX_RE = re.compile(r"^[A-Z]{6}=X$")

# Generic futures symbols: 1-3 letters + ``=F`` (GC=F, CL=F, NG=F, ZN=F...).
_FUTURES_RE = re.compile(r"^[A-Z]{1,3}=F$")

# Foreign-listed equities often carry an exchange suffix.
_FOREIGN_SUFFIX_RE = re.compile(
    r"\.(KS|KQ|HK|T|TO|L|PA|DE|SW|AX|NS|BO|SS|SZ|MC|MI|BR|ST|HE|CO|WA|IR|SA|MX)$",
    re.IGNORECASE,
)

# Crypto pairs on Yahoo use ``<SYMBOL>-USD`` (BTC-USD, ETH-USD, SOL-USD).
_CRYPTO_RE = re.compile(r"^[A-Z0-9]{2,8}-USD$")


@dataclass(frozen=True, slots=True)
class AssetProfile:
    """Container for everything the collector needs about the input ticker."""

    ticker: str
    asset_class: AssetClass
    display_name: str
    # Whether the classic equity sources apply (yfinance news + FMP + SEC).
    supports_equity_sources: bool
    # Whether FMP earnings-call transcripts apply.
    supports_transcripts: bool
    # Whether the macro bundle (FRED / yfinance macro / Google News) applies.
    supports_macro: bool
    # Whether this ticker is an ETF (so we should fetch the issuer profile).
    is_etf: bool = False
    # Human-readable issuer name for curated ETFs; empty for non-ETF tickers
    # or for ETFs that only have the Yahoo-profile fallback.
    issuer: str = ""
    # Direct URL to the issuer's product page, if curated.
    issuer_url: str = ""


def classify(raw_ticker: str) -> AssetProfile:
    """Classify a user-supplied ticker string into an ``AssetProfile``.

    The normalization pipeline is intentionally conservative: we uppercase and
    strip, but we do NOT rewrite the symbol. That keeps Yahoo-specific forms
    like ``GC=F`` intact — downstream collectors need the original shape.
    """
    ticker = (raw_ticker or "").strip().upper()
    if not ticker:
        return AssetProfile(
            ticker=ticker,
            asset_class="equity",
            display_name=ticker,
            supports_equity_sources=True,
            supports_transcripts=False,
            supports_macro=False,
        )

    is_etf = ticker in _ALL_ETFS
    issuer, issuer_url = ETF_ISSUER_REGISTRY.get(ticker, ("", ""))

    if _FOREX_RE.match(ticker):
        base, quote = ticker[:3], ticker[3:6]
        return AssetProfile(
            ticker=ticker,
            asset_class="forex",
            display_name=f"{base}/{quote}",
            supports_equity_sources=False,
            supports_transcripts=False,
            supports_macro=True,
        )

    if _FUTURES_RE.match(ticker):
        return AssetProfile(
            ticker=ticker,
            asset_class="futures",
            display_name=_futures_display(ticker),
            supports_equity_sources=False,
            supports_transcripts=False,
            supports_macro=True,
        )

    if _CRYPTO_RE.match(ticker):
        return AssetProfile(
            ticker=ticker,
            asset_class="crypto",
            display_name=ticker.replace("-USD", "/USD"),
            supports_equity_sources=False,
            supports_transcripts=False,
            supports_macro=True,
        )

    if ticker in _BOND_ETFS:
        return AssetProfile(
            ticker=ticker,
            asset_class="bond_etf",
            display_name=ticker,
            # Bond ETFs *do* have Yahoo news + FMP news coverage; transcripts
            # don't exist. Keeping equity sources on gives us headline context.
            supports_equity_sources=True,
            supports_transcripts=False,
            supports_macro=True,
            is_etf=True,
            issuer=issuer,
            issuer_url=issuer_url,
        )

    if ticker in _COMMODITY_ETFS:
        return AssetProfile(
            ticker=ticker,
            asset_class="commodity_etf",
            display_name=ticker,
            supports_equity_sources=True,
            supports_transcripts=False,
            supports_macro=True,
            is_etf=True,
            issuer=issuer,
            issuer_url=issuer_url,
        )

    if _FOREIGN_SUFFIX_RE.search(ticker):
        return AssetProfile(
            ticker=ticker,
            asset_class="foreign_equity",
            display_name=ticker,
            # Yahoo news works on many foreign listings; FMP/SEC do not.
            supports_equity_sources=True,
            supports_transcripts=False,
            supports_macro=False,
        )

    # Broad-market / sector ETF that still classifies as equity for news
    # purposes. Macro is enabled because ETF questions often ask about rates,
    # liquidity, factor rotation, or sector-wide conditions rather than a
    # single issuer's fundamentals.
    if is_etf:
        return AssetProfile(
            ticker=ticker,
            asset_class="equity",
            display_name=ticker,
            supports_equity_sources=True,
            supports_transcripts=False,
            supports_macro=True,
            is_etf=True,
            issuer=issuer,
            issuer_url=issuer_url,
        )

    # Default: US single-name equity.
    return AssetProfile(
        ticker=ticker,
        asset_class="equity",
        display_name=ticker,
        supports_equity_sources=True,
        supports_transcripts=True,
        supports_macro=False,
    )


# Human-readable names for the most common futures roots so downstream
# reports don't surface opaque two-letter codes to the user.
_FUTURES_NAMES: dict[str, str] = {
    "GC": "Gold Futures",
    "SI": "Silver Futures",
    "HG": "Copper Futures",
    "PL": "Platinum Futures",
    "PA": "Palladium Futures",
    "CL": "Crude Oil (WTI) Futures",
    "BZ": "Brent Crude Futures",
    "NG": "Natural Gas Futures",
    "HO": "Heating Oil Futures",
    "RB": "RBOB Gasoline Futures",
    "ZC": "Corn Futures",
    "ZS": "Soybean Futures",
    "ZW": "Wheat Futures",
    "KC": "Coffee Futures",
    "SB": "Sugar Futures",
    "CT": "Cotton Futures",
    "CC": "Cocoa Futures",
    "ZN": "10Y Treasury Note Futures",
    "ZB": "30Y Treasury Bond Futures",
    "ZF": "5Y Treasury Note Futures",
    "ES": "E-mini S&P 500 Futures",
    "NQ": "E-mini Nasdaq-100 Futures",
    "YM": "E-mini Dow Futures",
    "RTY": "E-mini Russell 2000 Futures",
    "DX": "US Dollar Index Futures",
    "6E": "Euro FX Futures",
    "6J": "Japanese Yen Futures",
}


def _futures_display(ticker: str) -> str:
    root = ticker.split("=", 1)[0]
    return _FUTURES_NAMES.get(root, f"{root} Futures")


__all__ = ["AssetClass", "AssetProfile", "ETF_ISSUER_REGISTRY", "classify"]
