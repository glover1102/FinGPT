# Run preflight diagnostics for the quant_stack runtime, data providers, Qdrant, and model stack.
from __future__ import annotations

import argparse
import json
import sys

from app.config import load_settings
from app.preflight import run_checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight diagnostics for quant_stack.")
    parser.add_argument(
        "--check",
        choices=["all", "openbb", "qdrant", "model"],
        default="all",
        help="Which diagnostic group to run.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    return parser.parse_args()


def render_result(result) -> None:
    tag = "OK" if result.ok else "FAIL"
    print(f"[{tag}] {result.name}")
    for key, value in result.details.items():
        print(f"  - {key}: {value}")
    for warning in result.warnings:
        print(f"  - warning: {warning}")
    for fix in result.fixes:
        print(f"  - fix: {fix}")


def main() -> int:
    args = parse_args()
    settings = load_settings()
    results = run_checks(settings, args.check)

    if args.json:
        print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))
    else:
        for result in results:
            render_result(result)

    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
