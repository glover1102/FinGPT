from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.utils.provider_versions import build_provider_version_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate provider package versions against FinGPT policy.")
    parser.add_argument("--output", default="reports/provider_versions_latest.json")
    parser.add_argument(
        "--require-openbb-agent",
        action="store_true",
        help="Treat OpenBB Workspace agent packages as required instead of optional.",
    )
    args = parser.parse_args()

    report = build_provider_version_report(require_openbb_agent=args.require_openbb_agent)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["critical_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
