from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx


_MESSAGE_EVENTS = {"message_chunk", "copilotMessageChunk"}
_TABLE_EVENTS = {"table", "copilotMessageArtifact"}
_CITATION_EVENTS = {"citations", "copilotCitationCollection"}


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
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
        data_text = "\n".join(data_lines)
        try:
            data: Any = json.loads(data_text)
        except json.JSONDecodeError:
            data = data_text
        frames.append({"event": event, "data": data})
    return frames


def _agent_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key, value in payload.items():
        if key == "agents" and isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict) and ("query" in value or "query_url" in value or "endpoints" in value):
            entry = {"id": key}
            entry.update(value)
            entries.append(entry)
    return entries


def _has_agent(payload: Any, agent_id: str) -> bool:
    if not isinstance(payload, dict):
        return False
    if agent_id in payload:
        return True
    return any(str(item.get("id") or item.get("name") or "") == agent_id for item in _agent_entries(payload))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe a running FinGPT OpenBB Workspace agent adapter over real HTTP/SSE."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--agent-id", default="fingpt-local-research")
    parser.add_argument("--question", default="현재 시장이 무시하는 신용 리스크")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--output", default="reports/openbb_agent_live_probe_latest.json")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--full-pipeline",
        action="store_true",
        help="Run the actual FinGPT pipeline instead of the diagnostic dry-run header.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    report: dict[str, Any] = {
        "status": "failed",
        "base_url": base_url,
        "agent_id": args.agent_id,
        "dry_run": not args.full_pipeline,
        "errors": [],
    }

    try:
        with httpx.Client(timeout=args.timeout) as client:
            agents_resp = client.get(f"{base_url}/agents.json")
            report["agents_json_status_code"] = agents_resp.status_code
            agents_payload = agents_resp.json()
            report["agent_present"] = _has_agent(agents_payload, args.agent_id)
            if agents_resp.status_code != 200:
                report["errors"].append(f"/agents.json returned HTTP {agents_resp.status_code}")
            if not report["agent_present"]:
                report["errors"].append(f"agent id {args.agent_id!r} was not found in /agents.json")

            headers = {"Accept": "text/event-stream"}
            if not args.full_pipeline:
                headers["X-FinGPT-OpenBB-Dry-Run"] = "true"
            payload = {
                "messages": [{"role": "user", "content": args.question}],
                "selected_widget": {"symbol": args.ticker} if args.ticker else {},
            }

            with client.stream("POST", f"{base_url}/query", headers=headers, json=payload) as query_resp:
                body = "".join(query_resp.iter_text())
            frames = _parse_sse(body)
            event_names = [frame["event"] for frame in frames]
            report["query_status_code"] = query_resp.status_code
            report["events"] = event_names
            report["event_count"] = len(frames)
            report["has_message"] = bool(_MESSAGE_EVENTS & set(event_names))
            report["has_table"] = bool(_TABLE_EVENTS & set(event_names))
            report["has_citations"] = bool(_CITATION_EVENTS & set(event_names))
            report["has_done"] = "done" in event_names

            if query_resp.status_code != 200:
                report["errors"].append(f"/query returned HTTP {query_resp.status_code}")
            if not report["has_message"]:
                report["errors"].append("/query did not stream a message event")
            if not report["has_done"]:
                report["errors"].append("/query did not terminate with a done event")
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(str(exc))

    report["status"] = "passed" if not report["errors"] else "failed"
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
