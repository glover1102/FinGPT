"""Reusable Macro platform layer for FinGPT."""

from pipelines.macro.macro_service import (
    generate_macro_brief,
    get_asset_impact,
    get_macro_category,
    get_macro_overview,
    get_macro_research_context,
    get_macro_series,
    get_portfolio_policy_hints,
    list_macro_series,
)

__all__ = [
    "generate_macro_brief",
    "get_asset_impact",
    "get_macro_category",
    "get_macro_overview",
    "get_macro_research_context",
    "get_macro_series",
    "get_portfolio_policy_hints",
    "list_macro_series",
]
