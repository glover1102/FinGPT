from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.data_mart.storage import repository  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a scheduler-level data update event.")
    parser.add_argument("--market", default="us")
    parser.add_argument("--status", choices=["success", "partial", "failed"], required=True)
    parser.add_argument("--message", default="")
    args = parser.parse_args(argv)

    run_id = repository.start_update_run(market=args.market, provider="scheduler")
    repository.record_provider_status(
        run_id,
        provider="scheduler",
        status=args.status,
        market=args.market,
        error_message=args.message or None,
        details={"message": args.message},
    )
    repository.finish_update_run(run_id, status=args.status, error_message=args.message or None)
    print(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
