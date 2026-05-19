from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.api import openbb_agent
from app.api import server as api_server
from core.config.settings import load_settings
from core.schemas.response import AnalysisResponse
from core.utils.openbb_agent_compat import (
    build_agents_json,
    check_openbb_agent_contract,
    validate_agents_json,
)

_MESSAGE_EVENTS = {"message_chunk", "copilotMessageChunk"}


def _parse_sse(raw: str) -> list[dict]:
    frames: list[dict] = []
    for block in raw.strip().split("\n\n"):
        if not block or block.startswith(":"):
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            data = "\n".join(data_lines)
        frames.append({"event": event, "data": data})
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the optional OpenBB Workspace agent adapter contract.")
    parser.add_argument("--output", default="reports/openbb_agent_compat_latest.json")
    parser.add_argument(
        "--probe-query",
        action="store_true",
        help="Run a mocked /query SSE dry-run when OPENBB_AGENT_ENABLED=true.",
    )
    args = parser.parse_args()

    settings = load_settings()
    name, ok, detail = check_openbb_agent_contract(settings)
    report: dict = {
        "status": "passed" if ok else "failed",
        "check": {"name": name, "ok": ok, "detail": detail},
        "enabled": bool(getattr(settings, "openbb_agent_enabled", False)),
        "agents_json": build_agents_json(settings, include_disabled=True),
        "errors": [],
    }
    report["errors"] = validate_agents_json(report["agents_json"], settings)

    if ok and args.probe_query and report["enabled"]:
        response = AnalysisResponse(
            ticker="MSFT",
            question="MSFT AI capex 리스크",
            status="success",
            summary="MSFT의 AI capex는 성장 옵션과 비용 부담을 동시에 만듭니다.",
            sentiment="Neutral",
            conclusion="수익화 속도와 마진 방어가 핵심 검증 지표입니다.",
        )
        payload = {
            "messages": [{"role": "user", "content": "MSFT AI capex 리스크"}],
            "selected_widget": {"symbol": "MSFT"},
        }
        with TestClient(api_server.app) as client, patch.object(openbb_agent, "load_settings", return_value=settings), patch.object(
            openbb_agent, "dispatch_async", new=AsyncMock(return_value=response)
        ):
            with client.stream("POST", "/query", json=payload) as resp:
                body = "".join(chunk for chunk in resp.iter_text())
                report["query_probe"] = {
                    "status_code": resp.status_code,
                    "events": [frame["event"] for frame in _parse_sse(body)],
                }
                if resp.status_code != 200 or not (_MESSAGE_EVENTS & set(report["query_probe"]["events"])):
                    report["status"] = "failed"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
