from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import server as api_server
from core.schemas.response import AnalysisResponse, ExecutionMeta
from core.schemas.topic import TopicResponse


def _parse_sse(raw: str) -> list[dict]:
    frames = []
    for block in raw.strip().split("\n\n"):
        if not block or block.startswith(":"):
            continue
        event = "message"
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            data = "\n".join(data_lines)
        frames.append({"event": event, "data": data})
    return frames


class StreamEndpointTests(unittest.TestCase):
    def test_stream_emits_stage_events_in_order(self):
        async def fake_pipeline(request, *, event_sink=None):
            for ev in ("pipeline_started", "stage_started", "stage_completed", "pipeline_completed"):
                if event_sink is not None:
                    event_sink({"event": ev, "stage": "collect"})
                await asyncio.sleep(0)
            return AnalysisResponse(
                ticker=request.ticker,
                question=request.question,
                status="success",
                summary="fake",
                sentiment="Neutral",
                conclusion="ok",
            )

        with patch.object(api_server, "run_pipeline_async", side_effect=fake_pipeline):
            client = TestClient(api_server.app)
            body = {
                "ticker": "AAPL",
                "question": "test",
                "sources": ["news"],
                "lookback_days": 7,
                "top_k": 5,
                "model": "qwen",
            }
            with client.stream("POST", "/api/v1/research/stream", json=body) as resp:
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/event-stream", resp.headers.get("content-type", ""))
                body_text = "".join(chunk for chunk in resp.iter_text())

        frames = _parse_sse(body_text)
        events = [f["event"] for f in frames]
        self.assertEqual(events[0], "stream_open")
        self.assertIn("pipeline_started", events)
        self.assertIn("stage_started", events)
        self.assertIn("stage_completed", events)
        self.assertIn("pipeline_completed", events)
        self.assertEqual(events[-1], "result")
        self.assertEqual(frames[-1]["data"]["ticker"], "AAPL")

    def test_universal_stream_emits_partial_result_before_final_result(self):
        async def fake_dispatch(request, *, event_sink=None):
            if event_sink is not None:
                event_sink({"event": "pipeline_started", "stage": "collect"})
                event_sink({"event": "stage_started", "stage": "collect"})
                event_sink({"event": "stage_completed", "stage": "collect"})
                event_sink(
                    {
                        "event": "partial_result",
                        "payload": {
                            "question": request.question,
                            "theme": "미국 장기채와 TLT",
                            "mode": "sector_macro",
                            "status": "partial",
                            "executive_summary": "초기 판단입니다.",
                            "core_thesis": "장기금리 안정 여부를 먼저 확인해야 합니다.",
                            "key_drivers": [{"text": "금리 피크아웃 기대"}],
                            "key_risks": [{"text": "인플레이션 재가속"}],
                            "execution_meta": {
                                "extras": {
                                    "phase": "fast",
                                }
                            },
                        },
                    }
                )
                event_sink({"event": "pipeline_completed", "status": "success", "elapsed_s": 12.3})
                await asyncio.sleep(0)
            return TopicResponse(
                question=request.question,
                theme="미국 장기채와 TLT",
                mode="sector_macro",
                status="success",
                executive_summary="최종 판단입니다.",
                core_thesis="중장기 기대값은 양호하지만 분할 접근이 적절합니다.",
                execution_meta=ExecutionMeta(extras={"phase": "final"}),
            )

        with patch.object(api_server, "dispatch_async", side_effect=fake_dispatch):
            client = TestClient(api_server.app)
            body = {
                "ticker": "TLT",
                "question": "지금 TLT가 매력적인지 분석해줘",
                "mode_hint": "topic",
                "sources": ["news", "transcript"],
                "lookback_days": 30,
                "top_k": 5,
                "model": "qwen",
            }
            with client.stream("POST", "/api/v1/research/universal/stream", json=body) as resp:
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/event-stream", resp.headers.get("content-type", ""))
                body_text = "".join(chunk for chunk in resp.iter_text())

        frames = _parse_sse(body_text)
        events = [f["event"] for f in frames]
        self.assertIn("partial_result", events)
        self.assertEqual(events[-1], "result")
        self.assertLess(events.index("partial_result"), events.index("result"))
        partial_frame = next(frame for frame in frames if frame["event"] == "partial_result")
        self.assertEqual(partial_frame["data"]["execution_meta"]["extras"]["phase"], "fast")
        result_frame = frames[-1]
        self.assertEqual(result_frame["data"]["mode"], "sector_macro")

    def test_stream_surfaces_pipeline_exceptions(self):
        async def failing_pipeline(request, *, event_sink=None):
            raise RuntimeError("boom")

        with patch.object(api_server, "run_pipeline_async", side_effect=failing_pipeline):
            client = TestClient(api_server.app)
            body = {
                "ticker": "AAPL",
                "question": "test",
                "sources": ["news"],
                "lookback_days": 7,
                "top_k": 5,
                "model": "qwen",
            }
            with client.stream("POST", "/api/v1/research/stream", json=body) as resp:
                self.assertEqual(resp.status_code, 200)
                body_text = "".join(chunk for chunk in resp.iter_text())

        frames = _parse_sse(body_text)
        failed_frame = next(f for f in frames if f["event"] == "pipeline_failed")
        self.assertEqual(failed_frame["data"].get("reason"), "boom")


if __name__ == "__main__":
    unittest.main()
