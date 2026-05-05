from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_run_id(template: str, config: dict[str, Any]) -> str:
    seed = json.dumps(config, sort_keys=True, ensure_ascii=True, default=str)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    clean_template = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(template or "quant"))
    return f"qlab_{stamp}_{clean_template}_{digest}"


def write_backtest_artifacts(
    *,
    run_id: str,
    root: Path,
    config: dict[str, Any],
    metrics: dict[str, Any],
    diagnostics: dict[str, Any],
    equity_curve: list[dict[str, Any]],
    drawdown_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    weights: list[dict[str, Any]] | dict[str, Any],
    data_snapshot: dict[str, Any] | None = None,
    schema_version: str = "quant_lab_artifact_v1",
) -> dict[str, str]:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, Any] = {
        "config": config,
        "metrics": metrics,
        "diagnostics": diagnostics,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "trades": trades,
        "signals": signals,
        "weights": weights,
    }
    paths: dict[str, str] = {"run_id": run_id, "root": str(run_dir)}
    for name, payload in payloads.items():
        path = run_dir / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
        paths[name] = str(path)
    manifest_path = run_dir / "manifest.json"
    config_hash = _stable_hash(config)
    manifest = {
        "run_id": run_id,
        "schema_version": schema_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": config_hash,
        "code_version": _code_version(root),
        "data_snapshot": data_snapshot or {},
        "files": paths,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    paths["manifest"] = str(manifest_path)
    return paths


def _stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()


def _code_version(root: Path) -> dict[str, Any]:
    project_root = root.resolve()
    for parent in [project_root, *project_root.parents]:
        if (parent / ".git").exists():
            project_root = parent
            break
    revision = _git_output(project_root, ["git", "rev-parse", "HEAD"]) or "unknown"
    dirty = bool(_git_output(project_root, ["git", "status", "--porcelain"]))
    return {
        "git_commit": revision,
        "git_dirty": dirty,
    }


def _git_output(cwd: Path, command: list[str]) -> str:
    try:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
