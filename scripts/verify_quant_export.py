from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.backtest.artifact_exports import verify_export_package


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a Quant Lab export package without requiring FastAPI or the source run tree."
    )
    parser.add_argument(
        "package_path",
        help="Export directory, package_manifest.json, or legacy export_manifest.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full verification report as JSON.")
    parser.add_argument("--output", default="", help="Optional path to write the JSON verification report.")
    return parser.parse_args()


def _print_human_report(report: dict) -> None:
    print(f"status: {report.get('status')}")
    print(f"package_root: {report.get('package_root')}")
    print(f"manifest_kind: {report.get('manifest_kind')}")
    print(f"source_run_id: {report.get('source_run_id')}")
    print(
        "files: "
        f"{report.get('files_passed', 0)} passed / "
        f"{report.get('files_checked', 0)} checked / "
        f"{report.get('files_failed', 0)} failed"
    )
    warnings = report.get("warnings") or []
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    failures = report.get("failures") or []
    if failures:
        print("failures:")
        for failure in failures:
            reason = failure.get("reason") or "unknown"
            file_key = failure.get("file") or "unknown"
            print(f"  - {file_key}: {reason}")


def main() -> int:
    args = _parse_args()
    try:
        report = verify_export_package(args.package_path)
    except (FileNotFoundError, ValueError) as exc:
        report = {
            "status": "failed",
            "schema_version": "quant_lab_export_package_verification_v1",
            "package_root": str(Path(args.package_path)),
            "files_checked": 0,
            "files_passed": 0,
            "files_failed": 0,
            "failures": [{"file": "package_path", "reason": str(exc)}],
            "files": {},
            "warnings": [],
        }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human_report(report)

    return 0 if report.get("status") == "success" and int(report.get("files_failed") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
