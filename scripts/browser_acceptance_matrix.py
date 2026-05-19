from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_ui_contract import run_check as run_ui_contract_check


def build_acceptance_report(
    *,
    ui_contract: dict[str, Any],
    browser_use_status: str = "not_run",
    browser_use_error: str = "",
    playwright_status: str = "not_run",
    playwright_error: str = "",
    fallback_screenshot: str = "",
) -> dict[str, Any]:
    browser_use = {
        "status": _clean_status(browser_use_status),
        "error": browser_use_error,
        "satisfies_explicit_browser_use": _clean_status(browser_use_status) == "passed",
    }
    playwright = {
        "status": _clean_status(playwright_status),
        "error": playwright_error,
        "screenshot": fallback_screenshot,
        "satisfies_explicit_browser_use": False,
    }
    static_contract = {
        "status": "passed" if ui_contract.get("status") == "passed" else "failed",
        "report": ui_contract,
        "satisfies_explicit_browser_use": False,
    }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "browser_use_iab": browser_use,
        "playwright_fallback": playwright,
        "ui_contract": static_contract,
        "summary": {
            "explicit_browser_use_satisfied": browser_use["satisfies_explicit_browser_use"],
            "fallback_available": playwright["status"] == "passed" or static_contract["status"] == "passed",
            "release_evidence_level": _evidence_level(browser_use, playwright, static_contract),
        },
    }


def run_matrix(
    *,
    output: Path,
    browser_use_status: str = "not_run",
    browser_use_error: str = "",
    playwright_status: str = "not_run",
    playwright_error: str = "",
    fallback_screenshot: str = "",
) -> dict[str, Any]:
    ui_contract = run_ui_contract_check()
    report = build_acceptance_report(
        ui_contract=ui_contract,
        browser_use_status=browser_use_status,
        browser_use_error=browser_use_error,
        playwright_status=playwright_status,
        playwright_error=playwright_error,
        fallback_screenshot=fallback_screenshot,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _clean_status(value: str) -> str:
    status = str(value or "not_run").strip().lower()
    return status if status in {"passed", "failed", "blocked", "not_run"} else "not_run"


def _evidence_level(browser_use: dict[str, Any], playwright: dict[str, Any], ui_contract: dict[str, Any]) -> str:
    if browser_use["status"] == "passed":
        return "browser_use_iab"
    if playwright["status"] == "passed":
        return "playwright_fallback"
    if ui_contract["status"] == "passed":
        return "static_ui_contract"
    return "failed"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record browser acceptance evidence levels separately.")
    parser.add_argument("--output", default="reports/browser_acceptance_latest.json")
    parser.add_argument("--browser-use-status", default="not_run", choices=["passed", "failed", "blocked", "not_run"])
    parser.add_argument("--browser-use-error", default="")
    parser.add_argument("--playwright-status", default="not_run", choices=["passed", "failed", "blocked", "not_run"])
    parser.add_argument("--playwright-error", default="")
    parser.add_argument("--fallback-screenshot", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_matrix(
        output=Path(args.output),
        browser_use_status=args.browser_use_status,
        browser_use_error=args.browser_use_error,
        playwright_status=args.playwright_status,
        playwright_error=args.playwright_error,
        fallback_screenshot=args.fallback_screenshot,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ui_contract"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
