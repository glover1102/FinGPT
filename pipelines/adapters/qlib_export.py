from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config.settings import Settings
from pipelines.data_mart.storage.repository import get_prices


def build_qlib_csv_export(
    *,
    tickers: list[str],
    start_date: str | None,
    end_date: str | None,
    provider_uri: str | None,
    dry_run: bool,
    settings: Settings,
    runtime_status: dict[str, Any],
) -> dict[str, Any]:
    clean_tickers = _clean_tickers(tickers)
    rows_by_ticker = {
        ticker: _filter_rows(get_prices(ticker, limit=5000, db_path=settings.data_mart_db_path), start_date, end_date)
        for ticker in clean_tickers
    }
    counts = {ticker: len(rows) for ticker, rows in rows_by_ticker.items()}
    missing = [ticker for ticker, count in counts.items() if count == 0]
    dates = sorted({str(row.get("date") or "") for rows in rows_by_ticker.values() for row in rows if row.get("date")})
    output_root = _resolve_export_root(provider_uri, settings)
    payload: dict[str, Any] = {
        "status": "disabled" if not runtime_status.get("enabled") else ("dry_run_ready" if dry_run else "export_pending"),
        "enabled": bool(runtime_status.get("enabled")),
        "runtime_status": runtime_status.get("status", "unknown"),
        "dependency": runtime_status.get("dependency", "unknown"),
        "startup_required": False,
        "data_source_policy": "data_mart_export_only",
        "format": "qlib_csv_provider_seed",
        "provider_uri": str(output_root),
        "dry_run": dry_run,
        "export_ready": bool(clean_tickers and dates and not missing),
        "export_written": False,
        "requested": {
            "tickers": clean_tickers,
            "start_date": start_date,
            "end_date": end_date,
        },
        "row_counts": counts,
        "missing_assets": missing,
        "date_count": len(dates),
        "date_range": {"start": dates[0] if dates else "", "end": dates[-1] if dates else ""},
        "files": {},
        "message": runtime_status.get("message", ""),
    }
    if not runtime_status.get("enabled"):
        payload["export_ready"] = False
        return payload
    if not clean_tickers:
        payload.update({"status": "empty", "message": "No tickers were provided for Qlib export."})
        return payload
    if dry_run:
        return payload

    output_root.mkdir(parents=True, exist_ok=True)
    calendars_dir = output_root / "calendars"
    instruments_dir = output_root / "instruments"
    features_dir = output_root / "features"
    calendars_dir.mkdir(parents=True, exist_ok=True)
    instruments_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)

    calendar_path = calendars_dir / "day.txt"
    calendar_path.write_text("\n".join(dates) + ("\n" if dates else ""), encoding="utf-8")

    instrument_path = instruments_dir / "all.txt"
    with instrument_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        for ticker in clean_tickers:
            rows = rows_by_ticker.get(ticker, [])
            if not rows:
                continue
            writer.writerow([ticker, rows[0].get("date", ""), rows[-1].get("date", "")])

    feature_files: dict[str, str] = {}
    for ticker, rows in rows_by_ticker.items():
        if not rows:
            continue
        feature_path = features_dir / f"{_safe_symbol(ticker)}.csv"
        with feature_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["date", "$open", "$high", "$low", "$close", "$volume", "source", "collected_at"],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "date": row.get("date", ""),
                        "$open": row.get("open"),
                        "$high": row.get("high"),
                        "$low": row.get("low"),
                        "$close": row.get("adjusted_close") if row.get("adjusted_close") is not None else row.get("close"),
                        "$volume": row.get("volume"),
                        "source": row.get("source", ""),
                        "collected_at": row.get("collected_at", ""),
                    }
                )
        feature_files[ticker] = str(feature_path)

    manifest_path = output_root / "manifest.json"
    manifest = {
        "schema_version": "qlib_csv_provider_seed_v1",
        "generated_at": _utc_now(),
        "data_source": "data_mart:prices_daily",
        "runtime_status": runtime_status,
        "requested": payload["requested"],
        "row_counts": counts,
        "missing_assets": missing,
        "date_range": payload["date_range"],
        "files": {
            "calendar": str(calendar_path),
            "instruments": str(instrument_path),
            "features": feature_files,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    status = "exported" if runtime_status.get("status") == "available" else "exported_dependency_missing"
    payload.update(
        {
            "status": status,
            "export_written": True,
            "export_ready": bool(feature_files),
            "files": {
                "manifest": str(manifest_path),
                "calendar": str(calendar_path),
                "instruments": str(instrument_path),
                "features": feature_files,
            },
            "message": (
                "Data mart slice exported; Qlib runtime dependency is still missing."
                if status == "exported_dependency_missing"
                else "Data mart slice exported for explicit Qlib adapter workflows."
            ),
        }
    )
    return payload


def _clean_tickers(tickers: list[str]) -> list[str]:
    out: list[str] = []
    for raw in tickers:
        ticker = str(raw or "").strip().upper()
        if ticker and ticker not in out:
            out.append(ticker)
    return out


def _filter_rows(rows: list[dict[str, Any]], start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        row_date = str(row.get("date") or "")
        if start_date and row_date < start_date:
            continue
        if end_date and row_date > end_date:
            continue
        filtered.append(row)
    return filtered


def _resolve_export_root(provider_uri: str | None, settings: Settings) -> Path:
    raw = str(provider_uri if provider_uri is not None else settings.qlib_provider_uri or "").strip()
    if raw.startswith("file://"):
        raw = raw[7:]
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else settings.base_dir / path
    return settings.data_dir / "quant_lab" / "qlib_exports" / _utc_now().replace(":", "").replace("-", "")


def _safe_symbol(ticker: str) -> str:
    return "".join(ch for ch in ticker if ch.isalnum() or ch in {"_", "-", "."}) or "UNKNOWN"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
