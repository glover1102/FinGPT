from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "reports" / "topic_latency_profile.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quality_review import run_quality_review


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile FinGPT topic latency on the local stack.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to save the latency profile JSON.",
    )
    parser.add_argument(
        "--suite",
        default="topic",
        choices=["topic", "all"],
        help="Which suite to profile. 'topic' is the default hot path benchmark.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = asyncio.run(
        run_quality_review(
            suite=args.suite,
            output_path=args.output,
            measure_latency=True,
        )
    )
    return 0 if report["summary"]["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
