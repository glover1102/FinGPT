from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api import openbb_agent
from app.api import server as api_server
from core.config.settings import Settings
from core.schemas.response import AnalysisResponse, Citation, KeyMetric
from core.schemas.retrieval import RetrievalItem
from core.schemas.topic import ScenarioAnalysis, TopicResponse
from core.utils.openbb_agent_compat import build_agents_json, check_openbb_agent_contract, validate_agents_json


def _parse_sse(raw: str) -> list[dict]:
    frames = []
    for block in raw.strip().split("\n\n"):
        if not block or block.startswith(":"):
            continue
        event = "message"
        data_lines = []
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


_MESSAGE_EVENTS = {"message_chunk", "copilotMessageChunk"}
_TABLE_EVENTS = {"table", "copilotMessageArtifact"}
_CITATION_EVENTS = {"citations", "copilotCitationCollection"}
_REASONING_EVENTS = {"reasoning_step", "copilotStatusUpdate"}


def _event_data(event: dict) -> dict:
    data = event.get("data") or {}
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _table_rows(event: dict) -> list[dict]:
    data = _event_data(event)
    rows = data.get("rows")
    if isinstance(rows, list):
        return rows
    content = data.get("content")
    if isinstance(content, list):
        return content
    return []


class OpenBBAgentAdapterTests(unittest.TestCase):
    def test_extracts_latest_human_question_and_widget_ticker(self):
        payload = {
            "messages": [
                {"role": "assistant", "content": "old"},
                {"role": "user", "content": [{"type": "text", "text": "MSFT AI capex 리스크"}]},
            ],
            "widgets": {"selected": {"symbol": "MSFT"}},
        }

        self.assertEqual(openbb_agent.extract_latest_human_question(payload), "MSFT AI capex 리스크")
        self.assertEqual(openbb_agent.extract_ticker_hint(payload), "MSFT")

    def test_openbb_payload_maps_to_universal_request(self):
        request = openbb_agent.build_universal_request_from_openbb(
            {
                "messages": [{"role": "human", "content": "TLT 금리 매력도"}],
                "selected_widget": {"ticker": "TLT"},
                "lookback_days": 30,
                "top_k": 8,
            }
        )

        self.assertEqual(request.question, "TLT 금리 매력도")
        self.assertEqual(request.ticker, "TLT")
        self.assertEqual(request.mode_hint, "auto")
        self.assertEqual(request.lookback_days, 30)
        self.assertEqual(request.top_k, 8)

    def test_tickerless_payload_maps_to_topic_mode(self):
        request = openbb_agent.build_universal_request_from_openbb(
            {"messages": [{"role": "user", "content": "현재 시장이 무시하는 신용 리스크"}]}
        )

        self.assertIsNone(request.ticker)
        self.assertEqual(request.mode_hint, "topic")

    def test_response_mapping_includes_metrics_and_citations(self):
        response = AnalysisResponse(
            ticker="MSFT",
            question="q",
            status="success",
            summary="요약",
            sentiment="Neutral",
            conclusion="결론",
            key_metrics=[
                KeyMetric(
                    name="MSFT 종가",
                    value="424.62",
                    unit="USD",
                    as_of="2026-04-24",
                    source="yfinance",
                    evidence_doc_ids=["doc-1"],
                )
            ],
            citations=[Citation(source="news", title="기사", date="2026-04-24", doc_id="doc-1")],
            raw_context=[
                RetrievalItem(
                    source="news",
                    title="기사",
                    date="2026-04-24",
                    chunk="본문",
                    score=0.9,
                    metadata={"doc_id": "doc-1", "url": "https://example.com/a"},
                )
            ],
        )

        events = openbb_agent.response_to_openbb_events(response)
        event_names = [event.get("event") for event in events]

        self.assertTrue(_MESSAGE_EVENTS & set(event_names))
        self.assertTrue(_TABLE_EVENTS & set(event_names))
        self.assertTrue(_CITATION_EVENTS & set(event_names))
        metric_table = next(event for event in events if event.get("event") in _TABLE_EVENTS)
        self.assertEqual(_table_rows(metric_table)[0]["기준일"], "2026-04-24")

    def test_topic_response_mapping_includes_scenario_table(self):
        response = TopicResponse(
            question="TLT 금리 매력도",
            theme="TLT",
            mode="sector_macro",
            status="partial",
            executive_summary="요약",
            core_thesis="논지",
            scenario_analysis=[
                ScenarioAnalysis(
                    scenario="금리 하락",
                    probability="중간",
                    expected_outcome="장기금리 하락",
                    asset_implication="TLT 상승",
                    decision_read="분할 진입 유리",
                    evidence_doc_ids=["doc-1"],
                )
            ],
            uncertainty="FRED 일부 축이 비었습니다.",
        )

        events = openbb_agent.response_to_openbb_events(response)
        tables = [event for event in events if event.get("event") in _TABLE_EVENTS]

        self.assertTrue(tables)
        self.assertTrue(any(event.get("event") in _REASONING_EVENTS for event in events))

    def test_agents_json_contract_disabled_and_enabled(self):
        disabled = Settings(openbb_agent_enabled=False)
        self.assertEqual(build_agents_json(disabled), {})
        name, ok, detail = check_openbb_agent_contract(disabled)
        self.assertEqual(name, "OPENBB_AGENT_CONTRACT")
        self.assertTrue(ok)
        self.assertIn("Disabled", detail)

        enabled = Settings(openbb_agent_enabled=True, openbb_agent_public_url="http://127.0.0.1:8000")
        payload = build_agents_json(enabled)
        self.assertEqual(validate_agents_json(payload, enabled), [])
        self.assertIn("fingpt-local-research", payload)

    def test_agents_json_endpoint_and_query_stream_when_enabled(self):
        settings = Settings(openbb_agent_enabled=True, openbb_agent_public_url="http://127.0.0.1:8000")
        response = AnalysisResponse(
            ticker="MSFT",
            question="MSFT AI capex 리스크",
            status="success",
            summary="요약",
            sentiment="Neutral",
            conclusion="결론",
        )

        client = TestClient(api_server.app)
        with patch.object(openbb_agent, "load_settings", return_value=settings), patch.object(
            openbb_agent, "dispatch_async", new=AsyncMock(return_value=response)
        ) as dispatch:
            agents_resp = client.get("/agents.json")
            self.assertEqual(agents_resp.status_code, 200)
            self.assertIn("fingpt-local-research", agents_resp.json())

            with client.stream(
                "POST",
                "/query",
                json={
                    "messages": [{"role": "user", "content": "MSFT AI capex 리스크"}],
                    "selected_widget": {"symbol": "MSFT"},
                },
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                raw = "".join(chunk for chunk in resp.iter_text())

        dispatch.assert_awaited_once()
        sent_request = dispatch.await_args.args[0]
        self.assertEqual(sent_request.ticker, "MSFT")
        self.assertEqual(sent_request.mode_hint, "auto")
        events = [frame["event"] for frame in _parse_sse(raw)]
        self.assertTrue(_MESSAGE_EVENTS & set(events))
        self.assertEqual(events[-1], "done")

    def test_query_stream_dry_run_does_not_call_pipeline(self):
        settings = Settings(openbb_agent_enabled=True, openbb_agent_public_url="http://127.0.0.1:8000")
        client = TestClient(api_server.app)

        with patch.object(openbb_agent, "load_settings", return_value=settings), patch.object(
            openbb_agent, "dispatch_async", new=AsyncMock()
        ) as dispatch:
            with client.stream(
                "POST",
                "/query",
                headers={"X-FinGPT-OpenBB-Dry-Run": "true"},
                json={
                    "messages": [{"role": "user", "content": "현재 시장이 무시하는 신용 리스크"}],
                    "selected_widget": {"symbol": "SPY"},
                },
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                raw = "".join(chunk for chunk in resp.iter_text())

        dispatch.assert_not_awaited()
        events = _parse_sse(raw)
        event_names = [frame["event"] for frame in events]
        self.assertTrue(_MESSAGE_EVENTS & set(event_names))
        self.assertTrue(_TABLE_EVENTS & set(event_names))
        self.assertTrue(_CITATION_EVENTS & set(event_names))
        self.assertEqual(event_names[-1], "done")
        messages = [
            _event_data(frame).get("content", "") or _event_data(frame).get("delta", "") or _event_data(frame).get("message", "")
            for frame in events
            if frame["event"] in _MESSAGE_EVENTS
        ]
        self.assertTrue(any("Dry-run" in text or "OpenBB Workspace 연결" in text for text in messages))

    def test_query_stream_returns_structured_error_when_disabled(self):
        settings = Settings(openbb_agent_enabled=False)
        client = TestClient(api_server.app)

        with patch.object(openbb_agent, "load_settings", return_value=settings):
            with client.stream("POST", "/query", json={"messages": [{"role": "user", "content": "test"}]}) as resp:
                self.assertEqual(resp.status_code, 200)
                raw = "".join(chunk for chunk in resp.iter_text())

        frames = _parse_sse(raw)
        self.assertEqual(frames[0]["event"], "error")
        self.assertEqual(frames[0]["data"]["error_type"], "openbb_contract_error")


if __name__ == "__main__":
    unittest.main()
