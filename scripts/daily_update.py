from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.data_mart.jobs.quality_checks import run_data_quality_checks
from pipelines.data_mart.jobs.update_filings_daily import update_filings_daily
from pipelines.data_mart.jobs.update_macro_daily import update_macro_platform_data
from pipelines.data_mart.jobs.update_news_daily import update_news_daily
from pipelines.data_mart.jobs.update_prices_daily import update_prices_daily
from pipelines.data_mart.storage.repository import data_health


def parse_watchlist(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"watchlist not found: {path}")
    tickers: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.endswith(":"):
            continue
        if line.startswith("- "):
            value = line[2:].strip().strip("'\"")
            if value:
                tickers.append(value.upper())
    return tickers


def default_watchlist_path(market: str) -> Path:
    name = "core_kr.yaml" if market.lower() == "kr" else "core_us.yaml"
    return PROJECT_ROOT / "config" / "watchlists" / name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update the local structured financial data mart.")
    parser.add_argument("--market", default="us", choices=["us", "kr"], help="Market watchlist preset.")
    parser.add_argument("--watchlist", default="", help="Path to a simple YAML watchlist file.")
    parser.add_argument("--start-date", default=None, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Exclusive/provider-specific end date, YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without writing to the data mart.")
    parser.add_argument("--retry-failed", action="store_true", help="Reserved for scheduler retry flows; current run still updates the full watchlist.")
    parser.add_argument("--skip-news", action="store_true", help="Skip Google News RSS article capture.")
    parser.add_argument("--skip-macro", action="store_true", help="Skip FRED macro capture.")
    parser.add_argument("--skip-filings", action="store_true", help="Skip SEC filings capture for US watchlists.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    watchlist_path = Path(args.watchlist) if args.watchlist else default_watchlist_path(args.market)
    tickers = parse_watchlist(watchlist_path)
    if not tickers:
        raise SystemExit(f"watchlist is empty: {watchlist_path}")

    results = {
        "market": args.market,
        "watchlist": str(watchlist_path),
        "tickers": tickers,
        "dry_run": bool(args.dry_run),
        "retry_failed": bool(args.retry_failed),
        "jobs": [],
    }

    price_result = update_prices_daily(
        tickers,
        market=args.market,
        start_date=args.start_date,
        end_date=args.end_date,
        dry_run=args.dry_run,
    )
    results["jobs"].append(price_result.__dict__)

    if not args.skip_macro:
        macro_result = update_macro_platform_data(
            market=args.market,
            start_date=args.start_date,
            end_date=args.end_date,
            dry_run=args.dry_run,
        )
        results["jobs"].append(macro_result.__dict__)

    if not args.skip_news:
        news_result = update_news_daily(
            tickers,
            market=args.market,
            dry_run=args.dry_run,
        )
        results["jobs"].append(news_result.__dict__)

    if not args.skip_filings and args.market == "us":
        filings_result = update_filings_daily(
            tickers,
            market=args.market,
            dry_run=args.dry_run,
        )
        results["jobs"].append(filings_result.__dict__)

    if not args.dry_run:
        checks = run_data_quality_checks()
        results["quality_checks"] = checks
        results["data_health"] = data_health()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"Updated data mart for market={args.market} tickers={len(tickers)} dry_run={args.dry_run}")
        for job in results["jobs"]:
            print(
                f"- {job['provider']}: {job['status']} "
                f"inserted={job.get('rows_inserted', 0)} updated={job.get('rows_updated', 0)}"
            )
    failed = [job for job in results["jobs"] if job["status"] == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
