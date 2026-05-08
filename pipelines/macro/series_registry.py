from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

from core.schemas.macro import MacroSeriesDefinition


def _definition(
    series_id: str,
    display_name: str,
    category: str,
    *,
    subcategory: str = "",
    provider: str = "fred",
    provider_series_id: str | None = None,
    country: str = "US",
    region: str = "US",
    frequency: str = "daily",
    unit: str = "level",
    transform: str = "level",
    stale_after_days: int = 30,
    importance: str = "medium",
    description: str = "",
    interpretation_hint: str = "",
    enabled: bool = True,
    tags: Iterable[str] = (),
) -> MacroSeriesDefinition:
    return MacroSeriesDefinition(
        series_id=series_id.upper(),
        display_name=display_name,
        category=normalize_category(category),
        subcategory=subcategory,
        provider=provider,
        provider_series_id=(provider_series_id or series_id).upper(),
        country=country,
        region=region,
        frequency=frequency,
        unit=unit,
        transform=transform,
        stale_after_days=stale_after_days,
        importance=importance,
        description=description,
        interpretation_hint=interpretation_hint,
        enabled=enabled,
        tags=list(tags),
    )


def normalize_category(category: str) -> str:
    return str(category or "").strip().lower().replace("&", "and").replace("-", "_").replace(" ", "_")


_SERIES: "OrderedDict[str, MacroSeriesDefinition]" = OrderedDict()


def _add(definition: MacroSeriesDefinition) -> None:
    _SERIES[definition.series_id] = definition


# Interest rates and yield curve
for item in [
    ("FEDFUNDS", "Effective Federal Funds Rate", "policy", "monthly", "percent", 65, "Policy rate level."),
    ("DGS3MO", "3-Month Treasury Yield", "treasury", "daily", "percent", 7, "Front-end Treasury yield."),
    ("DGS2", "2-Year Treasury Yield", "treasury", "daily", "percent", 7, "Policy-sensitive Treasury yield."),
    ("DGS10", "10-Year Treasury Yield", "treasury", "daily", "percent", 7, "Long-duration discount-rate anchor."),
    ("DGS30", "30-Year Treasury Yield", "treasury", "daily", "percent", 7, "Long-end Treasury yield."),
    ("T10Y2Y", "10Y-2Y Treasury Spread", "yield_curve", "daily", "percentage points", 7, "Curve inversion and recession-risk proxy."),
    ("T10Y3M", "10Y-3M Treasury Spread", "yield_curve", "daily", "percentage points", 7, "Curve inversion and policy-restriction proxy."),
    ("DFII10", "10-Year Real Yield", "real_rates", "daily", "percent", 7, "Real-rate pressure on growth assets and gold."),
]:
    _add(_definition(item[0], item[1], "interest_rates", subcategory=item[2], frequency=item[3], unit=item[4], stale_after_days=item[5], interpretation_hint=item[6], importance="high"))


# Inflation
for item in [
    ("CPIAUCSL", "CPI", "consumer_prices", "monthly", "y/y percent", "yoy_percent", 65, "Headline inflation pressure."),
    ("CPILFESL", "Core CPI", "consumer_prices", "monthly", "y/y percent", "yoy_percent", 65, "Core inflation persistence."),
    ("PCEPI", "PCE Price Index", "consumer_prices", "monthly", "y/y percent", "yoy_percent", 65, "Fed-preferred inflation proxy."),
    ("PCEPILFE", "Core PCE", "consumer_prices", "monthly", "y/y percent", "yoy_percent", 65, "Fed-preferred core inflation proxy."),
    ("T5YIE", "5-Year Breakeven Inflation", "inflation_expectations", "daily", "percent", "level", 7, "Market-implied medium-term inflation expectation."),
    ("T10YIE", "10-Year Breakeven Inflation", "inflation_expectations", "daily", "percent", "level", 7, "Market-implied long-term inflation expectation."),
    ("PPIACO", "Producer Price Index", "producer_prices", "monthly", "y/y percent", "yoy_percent", 65, "Input-price pressure."),
]:
    _add(_definition(item[0], item[1], "inflation", subcategory=item[2], frequency=item[3], unit=item[4], transform=item[5], stale_after_days=item[6], interpretation_hint=item[7], importance="high"))


# Growth
for item in [
    ("GDPC1", "Real GDP", "growth", "quarterly", "y/y percent", "yoy_percent", 140, "Real growth trend."),
    ("INDPRO", "Industrial Production", "growth", "monthly", "y/y percent", "yoy_percent", 65, "Industrial cycle momentum."),
    ("RSAFS", "Retail Sales", "growth", "monthly", "y/y percent", "yoy_percent", 65, "Consumer demand momentum."),
    ("UMCSENT", "University of Michigan Sentiment", "growth", "monthly", "index", "level", 65, "Consumer confidence and demand risk."),
]:
    _add(_definition(item[0], item[1], "growth", subcategory=item[2], frequency=item[3], unit=item[4], transform=item[5], stale_after_days=item[6], interpretation_hint=item[7], importance="high"))


# Labor
for item in [
    ("UNRATE", "Unemployment Rate", "labor", "monthly", "percent", "level", 65, "Labor-market slack."),
    ("PAYEMS", "Nonfarm Payrolls", "labor", "monthly", "y/y percent", "yoy_percent", 65, "Payroll growth trend."),
    ("ICSA", "Initial Jobless Claims", "labor", "weekly", "level", "level", 21, "High-frequency labor stress."),
    ("JTSJOL", "Job Openings", "labor", "monthly", "level", "level", 65, "Labor demand."),
]:
    _add(_definition(item[0], item[1], "labor", subcategory=item[2], frequency=item[3], unit=item[4], transform=item[5], stale_after_days=item[6], interpretation_hint=item[7], importance="high"))


# Liquidity, credit, and market stress
for item in [
    ("M2SL", "M2 Money Stock", "liquidity", "monthly", "y/y percent", "yoy_percent", 65, "Broad money growth."),
    ("WALCL", "Fed Balance Sheet", "liquidity", "weekly", "y/y percent", "yoy_percent", 21, "Central-bank liquidity impulse."),
    ("RRPONTSYD", "Overnight Reverse Repo", "liquidity", "daily", "USD billions", "level", 7, "Reserve-drain and liquidity proxy."),
    ("BAMLH0A0HYM2", "High Yield Credit Spread", "credit", "daily", "percentage points", "level", 7, "Credit stress proxy."),
    ("BAMLC0A0CM", "Investment Grade Credit Spread", "credit", "daily", "percentage points", "level", 7, "Investment-grade credit stress proxy."),
]:
    _add(_definition(item[0], item[1], "liquidity_credit", subcategory=item[2], frequency=item[3], unit=item[4], transform=item[5], stale_after_days=item[6], interpretation_hint=item[7], importance="high"))

_add(_definition("VIXCLS", "CBOE VIX", "market", subcategory="risk", frequency="daily", unit="index", stale_after_days=7, interpretation_hint="Equity volatility and risk appetite.", importance="medium"))


# Cross-provider extension entries. ECOS/OECD/World Bank remain disabled in
# default dashboards to avoid surprise key/network dependencies, but direct
# series fetches can use their adapters. Yahoo market proxies are enabled
# category surfaces because yfinance is already part of the local stack.
for item in [
    (
        "ECOS_KR_POLICY_RATE",
        "Korea Policy Rate",
        "interest_rates",
        "ecos",
        "722Y001/M/0101000",
        "KR",
        "monthly",
        "percent",
        65,
        "Bank of Korea policy-rate extension; requires ECOS_API_KEY.",
    ),
    (
        "ECOS_KR_CPI",
        "Korea CPI",
        "inflation",
        "ecos",
        "901Y009/M/0",
        "KR",
        "monthly",
        "index",
        65,
        "Korea CPI extension; requires ECOS_API_KEY and verified ECOS item code.",
    ),
    (
        "ECOS_USDKRW",
        "USD/KRW",
        "fx_dollar",
        "ecos",
        "731Y001/D/0000001",
        "KR",
        "daily",
        "KRW per USD",
        7,
        "USD/KRW extension; requires ECOS_API_KEY and verified ECOS item code.",
    ),
    (
        "OECD_CLI",
        "OECD US Composite Leading Indicator",
        "growth",
        "oecd",
        "DP_LIVE/USA.CLI.AMPLITUD.LTRENDIDX.M",
        "US",
        "monthly",
        "index",
        65,
        "OECD leading-indicator extension via SDMX.",
    ),
    (
        "WORLD_BANK_GDP",
        "World Bank US GDP Growth",
        "growth",
        "worldbank",
        "NY.GDP.MKTP.KD.ZG",
        "US",
        "annual",
        "annual percent",
        500,
        "World Bank annual real GDP growth extension.",
    ),
]:
    _add(
        _definition(
            item[0],
            item[1],
            item[2],
            provider=item[3],
            provider_series_id=item[4],
            country=item[5],
            region=item[5],
            frequency=item[6],
            unit=item[7],
            stale_after_days=item[8],
            description="Cross-provider macro extension entry.",
            interpretation_hint=item[9],
            enabled=False,
            tags=["extension"],
        )
    )

for item in [
    ("YAHOO_DXY_PROXY", "Dollar Index Proxy", "fx_dollar", "DX-Y.NYB", "index", "Dollar strength proxy."),
    ("YAHOO_GLD", "GLD Gold Proxy", "commodities", "GLD", "price", "Gold price proxy."),
    ("YAHOO_USO", "USO Oil Proxy", "commodities", "USO", "price", "Oil price proxy."),
    ("YAHOO_TLT", "TLT Duration Proxy", "market", "TLT", "price", "Long-duration Treasury ETF proxy."),
    ("YAHOO_SPY", "SPY Equity Proxy", "market", "SPY", "price", "US equity beta proxy."),
]:
    _add(
        _definition(
            item[0],
            item[1],
            item[2],
            provider="yahoo",
            provider_series_id=item[3],
            country="US",
            region="US",
            frequency="daily",
            unit=item[4],
            stale_after_days=7,
            importance="medium",
            description="Yahoo Finance market proxy; values are price/index levels, not economic releases.",
            interpretation_hint=item[5],
            enabled=True,
            tags=["market_proxy", "extension"],
        )
    )


def list_macro_series(*, include_disabled: bool = False) -> list[MacroSeriesDefinition]:
    return [definition for definition in _SERIES.values() if include_disabled or definition.enabled]


def get_series_definition(series_id: str) -> MacroSeriesDefinition:
    key = str(series_id or "").upper().strip()
    if key not in _SERIES:
        raise KeyError(key)
    return _SERIES[key]


def series_by_category(category: str, *, include_disabled: bool = False) -> list[MacroSeriesDefinition]:
    slug = normalize_category(category)
    return [item for item in list_macro_series(include_disabled=include_disabled) if item.category == slug]


def category_names() -> list[str]:
    return sorted({item.category for item in list_macro_series(include_disabled=False)})


def provider_names(*, include_disabled: bool = True) -> list[str]:
    return sorted({item.provider for item in list_macro_series(include_disabled=include_disabled)})


def country_names(*, include_disabled: bool = True) -> list[str]:
    return sorted({item.country for item in list_macro_series(include_disabled=include_disabled)})
