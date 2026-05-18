from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config.settings import load_settings
from core.utils.openbb_compat import build_openbb_compat_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OpenBB/Yahoo/SEC runtime compatibility.")
    parser.add_argument("--output", default="reports/openbb_compat_latest.json", help="JSON report path.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when warning-only OpenBB runtime checks fail.")
    parser.add_argument("--skip-network", action="store_true", help="Skip Yahoo/SEC network smoke checks.")
    parser.add_argument(
        "--probe-openbb-news",
        action="store_true",
        help="Probe OpenBB news.company even when OPENBB_NEWS_ENABLED=false.",
    )
    args = parser.parse_args()

    settings = load_settings()
    report = build_openbb_compat_report(
        sec_user_agent=settings.sec_user_agent,
        include_pip_check=True,
        include_network_smoke=not args.skip_network,
        include_openbb_news_runtime=bool(settings.openbb_news_enabled or args.probe_openbb_news),
    )
    if not settings.openbb_news_enabled and not args.probe_openbb_news:
        report["checks"].append(
            {
                "name": "openbb_news_company",
                "ok": True,
                "critical": False,
                "status": "disabled",
                "detail": "OPENBB_NEWS_ENABLED=false; runtime probe skipped and direct providers are used.",
                "elapsed_s": 0.0,
            }
        )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["policy"] = {
        "primary_stack": ["Yahoo/yfinance", "FRED", "SEC EDGAR", "Google News RSS"],
        "openbb": "compatibility-gated; used only when OPENBB_NEWS_ENABLED=true",
        "fmp": "auxiliary; used only when FMP_ENABLED=true",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["critical_passed"]:
        return 1
    if args.strict and report["warning_count"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
