from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.data_mart.storage.repository import data_health  # noqa: E402


def build_report(market: str) -> str:
    health = data_health()
    counts = health.get("table_counts") or {}
    latest = health.get("latest_run") or {}
    providers = health.get("recent_provider_status") or []
    quality = health.get("recent_quality_checks") or []
    failed = [row for row in providers if str(row.get("status") or "").lower() in {"failed", "error"}]
    stale = [row for row in quality if str(row.get("status") or "").lower() in {"warn", "fail"}]
    decision_status = "failed" if failed else ("partial" if stale else "ok")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    lines = [
        f"# Daily Data Mart Report ({market.upper()})",
        "",
        f"- generated_at: `{now}`",
        f"- database: `{health.get('database', 'default')}`",
        f"- status: `{health.get('status', 'unknown')}`",
        f"- decision_status: `{decision_status}`",
        "",
        "## Table Counts",
        "",
    ]
    for name in sorted(counts):
        lines.append(f"- `{name}`: {counts[name]}")
    lines.extend(
        [
            "",
            "## Latest Update Run",
            "",
            f"- run_id: `{latest.get('run_id', '-')}`",
            f"- status: `{latest.get('status', '-')}`",
            f"- started_at: `{latest.get('started_at', '-')}`",
            f"- finished_at: `{latest.get('finished_at', '-')}`",
            f"- rows_inserted: {latest.get('rows_inserted', 0)}",
            f"- rows_updated: {latest.get('rows_updated', 0)}",
            "",
            "## Recent Provider Status",
            "",
        ]
    )
    if providers:
        for row in providers[:20]:
            ticker = f" ticker={row.get('ticker')}" if row.get("ticker") else ""
            lines.append(f"- `{row.get('provider')}` status=`{row.get('status')}` market=`{row.get('market')}`{ticker}")
    else:
        lines.append("- No provider status rows recorded.")
    lines.extend(["", "## Recent Quality Checks", ""])
    if quality:
        for row in quality[:20]:
            entity = f" {row.get('entity_type') or ''}:{row.get('entity_id') or ''}".strip()
            lines.append(f"- `{row.get('check_name')}` status=`{row.get('status')}` {entity} - {row.get('message')}")
    else:
        lines.append("- No quality checks recorded.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a markdown data-mart health report.")
    parser.add_argument("--market", default="us")
    parser.add_argument("--output-dir", default="data/outputs")
    args = parser.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(args.market)
    dated = output_dir / f"daily_data_health_{args.market}_{stamp}.md"
    latest = output_dir / "daily_data_health_latest.md"
    dated.write_text(report, encoding="utf-8")
    latest.write_text(report, encoding="utf-8")
    print(str(dated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
