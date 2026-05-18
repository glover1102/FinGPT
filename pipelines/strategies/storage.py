from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CURRENT_STRATEGY_SCHEMA_VERSION = "quant_strategy_v1"
SUPPORTED_STRATEGY_SCHEMA_VERSIONS = {"", "quant_strategy_v0", CURRENT_STRATEGY_SCHEMA_VERSION}


def save_strategy(strategy: dict[str, Any], root: Path) -> Path:
    normalized = validate_strategy(strategy)
    strategy_id = str(normalized.get("strategy_id") or "").strip()
    if not strategy_id:
        raise ValueError("strategy_id is required")
    safe_id = "".join(ch for ch in strategy_id if ch.isalnum() or ch in {"_", "-"})
    if safe_id != strategy_id:
        raise ValueError("strategy_id may only contain letters, numbers, underscore, and dash")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe_id}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(existing, dict) and existing.get("created_at"):
            normalized["created_at"] = existing["created_at"]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def migrate_strategy(
    strategy: dict[str, Any],
    *,
    source: str | None = None,
    touch: bool = False,
) -> dict[str, Any]:
    normalized = dict(strategy or {})
    schema_version = str(normalized.get("schema_version") or "").strip()
    if schema_version not in SUPPORTED_STRATEGY_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported strategy schema_version: {schema_version}")
    migrations = list(normalized.get("migration_history") or [])
    if schema_version != CURRENT_STRATEGY_SCHEMA_VERSION:
        migrations.append(
            {
                "from_schema_version": schema_version or "missing",
                "to_schema_version": CURRENT_STRATEGY_SCHEMA_VERSION,
                "migration": "default_strategy_metadata_v1",
            }
        )
        normalized["schema_version"] = CURRENT_STRATEGY_SCHEMA_VERSION
    normalized.setdefault("strategy_version", "1")
    normalized.setdefault("source", source or "user")
    now = datetime.now(timezone.utc).isoformat()
    normalized.setdefault("created_at", now)
    if touch or "updated_at" not in normalized:
        normalized["updated_at"] = now
    if migrations:
        normalized["migration_history"] = migrations
    return normalized


def validate_strategy(strategy: dict[str, Any]) -> dict[str, Any]:
    normalized = migrate_strategy(strategy, touch=True)
    strategy_id = str(normalized.get("strategy_id") or "").strip()
    if not strategy_id:
        raise ValueError("strategy_id is required")
    execution = normalized.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("execution is required")
    if str(execution.get("trade_at") or "").strip() != "next_bar_close":
        raise ValueError("execution.trade_at must be next_bar_close")
    return normalized


def load_strategy(strategy_id: str, root: Path) -> dict[str, Any] | None:
    safe_id = "".join(ch for ch in str(strategy_id or "") if ch.isalnum() or ch in {"_", "-"})
    if not safe_id:
        return None
    path = root / f"{safe_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return migrate_strategy(payload, touch=False)


def delete_strategy(strategy_id: str, root: Path) -> bool:
    safe_id = "".join(ch for ch in str(strategy_id or "") if ch.isalnum() or ch in {"_", "-"})
    if not safe_id:
        return False
    path = root / f"{safe_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True
