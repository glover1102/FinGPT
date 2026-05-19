from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_JS = PROJECT_ROOT / "app" / "web" / "app.js"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "universe_source_refresh_latest.json"

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

USER_AGENT = "FinGPT local universe refresh/1.0"

SECTOR_MAP = {
    "Communication Services": "COMMUNICATION SERVICES",
    "Consumer Discretionary": "CONSUMER CYCLICAL",
    "Consumer Staples": "CONSUMER DEFENSIVE",
    "Energy": "ENERGY",
    "Financials": "FINANCIAL",
    "Health Care": "HEALTHCARE",
    "Industrials": "INDUSTRIALS",
    "Information Technology": "TECHNOLOGY",
    "Materials": "BASIC MATERIALS",
    "Real Estate": "REAL ESTATE",
    "Utilities": "UTILITIES",
    "Basic Materials": "BASIC MATERIALS",
    "Consumer Defensive": "CONSUMER DEFENSIVE",
    "Technology": "TECHNOLOGY",
    "Telecommunications": "COMMUNICATION SERVICES",
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def read_tables(url: str) -> list[pd.DataFrame]:
    return pd.read_html(StringIO(fetch_html(url)))


def yfinance_symbol(value: Any) -> str:
    return str(value or "").strip().replace(".", "-").upper()


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def js_key(symbol: str) -> str:
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", symbol):
        return symbol
    return json.dumps(symbol, ensure_ascii=False)


def js_value(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def extract_symbol_list(source: str, const_name: str) -> list[str]:
    pattern = re.compile(
        rf"const\s+{re.escape(const_name)}\s*=\s*symbolList\(`(?P<body>.*?)`\);",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        return []
    return [yfinance_symbol(token) for token in match.group("body").split() if token.strip()]


def replace_symbol_list(source: str, const_name: str, symbols: list[str]) -> str:
    body = format_symbol_list(symbols)
    pattern = re.compile(
        rf"const\s+{re.escape(const_name)}\s*=\s*symbolList\(`.*?`\);",
        re.DOTALL,
    )
    replacement = f"const {const_name} = symbolList(`\n{body}\n`);"
    return pattern.sub(replacement, source, count=1)


def replace_name_block(source: str, const_name: str, names: dict[str, str]) -> str:
    body = "\n".join(f"{symbol}|{names[symbol]}" for symbol in names)
    pattern = re.compile(
        rf"const\s+{re.escape(const_name)}\s*=\s*Object\.fromEntries\(symbolNameList\(`.*?`\)\);",
        re.DOTALL,
    )
    replacement = f"const {const_name} = Object.fromEntries(symbolNameList(`\n{body}\n`));"
    return pattern.sub(replacement, source, count=1)


def replace_heatmap_classification(source: str, classification: dict[str, dict[str, str]]) -> str:
    lines = ["const HEATMAP_CLASSIFICATION = {"]
    for symbol, item in classification.items():
        lines.append(
            f"  {js_key(symbol)}: "
            f"{{ sector: {js_value(item['sector'])}, industry: {js_value(item['industry'])} }},"
        )
    lines.append("};")
    pattern = re.compile(r"const\s+HEATMAP_CLASSIFICATION\s*=\s*\{.*?\n\};", re.DOTALL)
    return pattern.sub("\n".join(lines), source, count=1)


def format_symbol_list(symbols: list[str], *, per_line: int = 18) -> str:
    lines = []
    for idx in range(0, len(symbols), per_line):
        lines.append("  " + " ".join(symbols[idx : idx + per_line]))
    return "\n".join(lines)


def find_nasdaq_components_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    for table in tables:
        columns = {str(column) for column in table.columns}
        if {"Ticker", "Company"}.issubset(columns):
            return table
    raise RuntimeError("Nasdaq-100 components table not found")


def build_universe(existing_order: list[str]) -> tuple[list[str], dict[str, str], dict[str, dict[str, str]], dict[str, Any]]:
    sp500 = read_tables(SP500_URL)[0]
    nasdaq100 = find_nasdaq_components_table(read_tables(NASDAQ100_URL))

    source_symbols: list[str] = []
    names: dict[str, str] = {}
    classification: dict[str, dict[str, str]] = {}
    sp500_symbols: set[str] = set()
    nasdaq_symbols: set[str] = set()

    for _, row in sp500.iterrows():
        symbol = yfinance_symbol(row.get("Symbol"))
        if not symbol:
            continue
        sp500_symbols.add(symbol)
        source_symbols.append(symbol)
        names[symbol] = clean_text(row.get("Security")) or symbol
        sector = SECTOR_MAP.get(clean_text(row.get("GICS Sector")), clean_text(row.get("GICS Sector")).upper())
        industry = clean_text(row.get("GICS Sub-Industry")).upper()
        classification[symbol] = {"sector": sector or "OTHER", "industry": industry or "UNKNOWN"}

    for _, row in nasdaq100.iterrows():
        symbol = yfinance_symbol(row.get("Ticker"))
        if not symbol:
            continue
        nasdaq_symbols.add(symbol)
        if symbol not in source_symbols:
            source_symbols.append(symbol)
        names.setdefault(symbol, clean_text(row.get("Company")) or symbol)
        industry = clean_text(row.get("ICB Industry[14]") or row.get("ICB Industry"))
        subsector = clean_text(row.get("ICB Subsector[14]") or row.get("ICB Subsector"))
        classification.setdefault(
            symbol,
            {
                "sector": SECTOR_MAP.get(industry, industry.upper() or "OTHER"),
                "industry": subsector.upper() or "UNKNOWN",
            },
        )

    valid = set(source_symbols)
    ordered: list[str] = []
    seen: set[str] = set()
    for symbol in existing_order:
        if symbol in valid and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    for symbol in source_symbols:
        if symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)

    ordered_names = {symbol: names[symbol] for symbol in ordered if symbol in names}
    ordered_classification = {symbol: classification[symbol] for symbol in ordered if symbol in classification}
    report = {
        "generated_at": now_iso(),
        "sources": {
            "sp500": SP500_URL,
            "nasdaq100": NASDAQ100_URL,
        },
        "sp500_count": len(sp500_symbols),
        "nasdaq100_count": len(nasdaq_symbols),
        "combined_us_equity_count": len(ordered),
        "removed_from_previous_static_list": [symbol for symbol in existing_order if symbol not in valid],
        "added_to_static_list": [symbol for symbol in ordered if symbol not in existing_order],
        "nasdaq100_only_count": len([symbol for symbol in nasdaq_symbols if symbol not in sp500_symbols]),
        "nasdaq100_only": sorted(symbol for symbol in nasdaq_symbols if symbol not in sp500_symbols),
    }
    return ordered, ordered_names, ordered_classification, report


def refresh_app_js(*, dry_run: bool, report_path: Path) -> dict[str, Any]:
    source = APP_JS.read_text(encoding="utf-8")
    existing = extract_symbol_list(source, "US_LARGE_CAP_SYMBOLS")
    symbols, names, classification, report = build_universe(existing)

    updated = replace_symbol_list(source, "US_LARGE_CAP_SYMBOLS", symbols)
    updated = replace_name_block(updated, "US_SYMBOL_NAMES", names)
    updated = replace_heatmap_classification(updated, classification)

    report["app_js_changed"] = updated != source
    report["app_js_path"] = str(APP_JS)
    if not dry_run:
        APP_JS.write_text(updated, encoding="utf-8", newline="\n")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh FinGPT static US equity universe from current public index tables.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report without modifying app/web/app.js.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="JSON report path.")
    args = parser.parse_args(argv)

    report = refresh_app_js(dry_run=args.dry_run, report_path=args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
