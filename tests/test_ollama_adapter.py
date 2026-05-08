import unittest
from unittest.mock import Mock, patch

from core.config.settings import Settings
from core.schemas.retrieval import RetrievalItem
from pipelines.infer import ollama_adapter


def _response_payload(payload: str, done_reason: str = "stop") -> dict:
    return {
        "response": payload,
        "done_reason": done_reason,
    }


class OllamaAdapterTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            primary_model="mistral:7b",
            enable_experimental_fallback=False,
            ollama_base_url="http://localhost:11434",
            output_language="en",
        )
        self.context = [
            RetrievalItem(
                source="news",
                title="NVIDIA news",
                date="2026-04-20",
                chunk="NVIDIA announced updates to its AI roadmap and hyperscaler demand remained strong.",
                score=0.91,
                metadata={"doc_id": "doc-1", "ticker": "NVDA"},
            )
        ]

    def test_call_ollama_uses_structured_output_schema(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = _response_payload("{}")

        with patch.object(ollama_adapter.httpx, "post", return_value=response) as post:
            result = ollama_adapter._call_ollama(
                self.settings.ollama_base_url,
                "mistral:7b",
                "system",
                "prompt",
            )

        payload = post.call_args.kwargs["json"]
        self.assertIn("format", payload)
        self.assertEqual(payload["options"]["temperature"], 0)
        # Pinned to the adapter's default so the test tracks the production
        # generation budget instead of a hardcoded number.
        self.assertEqual(payload["options"]["num_predict"], ollama_adapter.DEFAULT_NUM_PREDICT)
        self.assertEqual(payload["format"]["type"], "object")
        self.assertIn("summary", payload["format"]["properties"])
        # New deep-analysis fields must be part of the schema contract.
        self.assertIn("key_metrics", payload["format"]["properties"])
        metric_schema = payload["format"]["properties"]["key_metrics"]["items"]
        self.assertIn("as_of", metric_schema["properties"])
        self.assertIn("as_of", metric_schema["required"])
        self.assertIn("catalyst_timeline", payload["format"]["properties"])
        self.assertIn("open_questions", payload["format"]["properties"])
        self.assertEqual(result["response"], "{}")

    def test_prompt_includes_domain_specific_decision_playbook(self):
        prompt, chunks = ollama_adapter._build_ollama_prompt(
            "USO",
            "Is crude oil attractive now?",
            self.context,
            task_type="valuation",
            horizon="medium_term",
            language="en",
        )

        self.assertEqual(chunks, 1)
        self.assertIn("DOMAIN PLAYBOOK", prompt)
        self.assertIn("domain-specific decision variables", prompt)
        self.assertIn("Commodities / energy / metals", ollama_adapter._SYSTEM_PROMPT)
        self.assertIn("Credit / banks / financials", ollama_adapter._SYSTEM_PROMPT)
        self.assertIn("Crypto / digital assets", ollama_adapter._SYSTEM_PROMPT)

    def test_run_inference_retries_truncated_primary_output_once(self):
        adapter = ollama_adapter.OllamaAdapter(self.settings)
        valid_json = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.72,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.",'
            '"bull_points":["AI demand is holding up -> revenue visibility stays firm."],'
            '"bear_points":["Export controls remain a risk -> estimate revisions can compress multiples."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":[],'
            '"cited_doc_ids":["doc-1"]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(
                 ollama_adapter,
                 "_call_ollama",
                 side_effect=[
                     _response_payload('{"symbol":"NVDA"', done_reason="length"),
                     _response_payload(valid_json),
                 ],
             ):
            result = adapter.run_inference("NVDA", "What are the main upside and downside drivers?", self.context)

        self.assertEqual(result["_meta"]["retry_count"], 1)
        self.assertFalse(result["_meta"]["fallback_used"])
        self.assertEqual(result["_meta"]["producing_model"], "mistral:7b")
        self.assertEqual(result["summary"], "Demand remains strong despite supply debates.")

    def test_run_inference_retries_malformed_primary_output_once(self):
        adapter = ollama_adapter.OllamaAdapter(self.settings)
        malformed_json = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high"'
            '"confidence":0.72,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.",'
            '"bull_points":["AI demand is holding up -> revenue visibility stays firm."],'
            '"bear_points":["Export controls remain a risk -> estimate revisions can compress multiples."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":[],'
            '"cited_doc_ids":["doc-1"]}'
        )
        valid_json = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.72,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.",'
            '"bull_points":["AI demand is holding up -> revenue visibility stays firm."],'
            '"bear_points":["Export controls remain a risk -> estimate revisions can compress multiples."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":[],'
            '"cited_doc_ids":["doc-1"]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(
                 ollama_adapter,
                 "_call_ollama",
                 side_effect=[
                     _response_payload(malformed_json),
                     _response_payload(valid_json),
                 ],
             ):
            result = adapter.run_inference("NVDA", "What are the main upside and downside drivers?", self.context)

        self.assertEqual(result["_meta"]["retry_count"], 1)
        self.assertEqual(result["bear_points"], ["Export controls remain a risk -> estimate revisions can compress multiples."])

    def test_run_inference_retries_schema_invalid_primary_output_once(self):
        adapter = ollama_adapter.OllamaAdapter(self.settings)
        invalid_json = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.72,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.","bull_points":"not-a-list",'
            '"bear_points":[],"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":[],"cited_doc_ids":["doc-1"]}'
        )
        valid_json = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.72,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.",'
            '"bull_points":["AI demand is holding up -> revenue visibility stays firm."],'
            '"bear_points":["Export controls remain a risk -> estimate revisions can compress multiples."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":[],'
            '"cited_doc_ids":["doc-1"]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(
                 ollama_adapter,
                 "_call_ollama",
                 side_effect=[
                     _response_payload(invalid_json),
                     _response_payload(valid_json),
                 ],
             ):
            result = adapter.run_inference("NVDA", "What are the main upside and downside drivers?", self.context)

        self.assertEqual(result["_meta"]["retry_count"], 1)
        self.assertEqual(result["bull_points"], ["AI demand is holding up -> revenue visibility stays firm."])

    def test_run_inference_retries_when_korean_output_requested_but_english_returned(self):
        settings = Settings(
            primary_model="mistral:7b",
            enable_experimental_fallback=False,
            ollama_base_url="http://localhost:11434",
            output_language="ko",
        )
        adapter = ollama_adapter.OllamaAdapter(settings)
        english_payload = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.7,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.",'
            '"bull_points":["AI demand is holding up and revenue visibility remains firm."],'
            '"bear_points":["Export controls remain a risk to estimate revisions."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":["What is the next demand signal?"],'
            '"cited_doc_ids":["doc-1"]}'
        )
        korean_payload = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.7,"horizon":"short_term","uncertainty":"수출 규제 영향은 계속 확인해야 합니다.",'
            '"summary":"AI 수요가 견조해 매출 가시성이 유지되고 있습니다.",'
            '"bull_points":["AI 수요가 견조해 단기 매출 가시성을 뒷받침합니다."],'
            '"bear_points":["수출 규제는 추정치 하향 위험으로 남아 있습니다."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":["다음 실적에서 수요 지속성이 확인되는지 점검해야 합니다."],'
            '"cited_doc_ids":["doc-1"]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(
                 ollama_adapter,
                 "_call_ollama",
                 side_effect=[
                     _response_payload(english_payload),
                     _response_payload(korean_payload),
                 ],
             ):
            result = adapter.run_inference("NVDA", "핵심 투자 포인트는?", self.context)

        self.assertEqual(result["_meta"]["retry_count"], 1)
        self.assertIn("AI 수요", result["summary"])

    def test_run_inference_rejects_final_non_korean_attempt(self):
        settings = Settings(
            primary_model="mistral:7b",
            enable_experimental_fallback=False,
            ollama_base_url="http://localhost:11434",
            output_language="ko",
        )
        adapter = ollama_adapter.OllamaAdapter(settings)
        english_payload = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.7,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.",'
            '"bull_points":["AI demand is holding up and revenue visibility remains firm."],'
            '"bear_points":["Export controls remain a risk to estimate revisions."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":["What is the next demand signal?"],'
            '"cited_doc_ids":["doc-1"]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(
                 ollama_adapter,
                 "_call_ollama",
                 side_effect=[
                     _response_payload(english_payload),
                     _response_payload(english_payload),
                     _response_payload(english_payload),
                 ],
             ):
            with self.assertRaisesRegex(ValueError, "Language violation"):
                adapter.run_inference("NVDA", "investment view?", self.context)

    def test_language_warning_accepts_normal_korean_output(self):
        payload = {
            "summary": "수요는 견조하지만 밸류에이션 부담 때문에 분할 접근이 필요합니다.",
            "uncertainty": "다음 실적에서 AI 매출 전환율과 마진 훼손 여부를 확인해야 합니다.",
            "bull_points": [{"text": "클라우드 성장률이 유지되면 매출 가시성이 높아집니다.", "evidence_doc_ids": []}],
            "bear_points": [{"text": "CAPEX 증가가 잉여현금흐름을 압박하면 멀티플이 낮아질 수 있습니다.", "evidence_doc_ids": []}],
            "key_metrics": [{"name": "매출 성장률", "context": "성장 지속성 판단 지표", "value": "10%", "as_of": "2026-04-24", "evidence_doc_ids": []}],
            "catalyst_timeline": {"near_term": ["실적 발표"], "mid_term": [], "long_term": []},
            "open_questions": ["마진 방어력이 확인되는가?"],
        }

        self.assertIsNone(ollama_adapter._language_warning(payload, "ko"))

    def test_language_warning_rejects_chinese_or_mojibake_output(self):
        payload = {
            "summary": "需求仍然强劲，但估值压力需要谨慎。",
            "uncertainty": "需要观察下一季度的利润率。",
            "bull_points": [{"text": "需求改善可能推动收入。", "evidence_doc_ids": []}],
            "bear_points": [{"text": "监管风险仍然存在。", "evidence_doc_ids": []}],
            "key_metrics": [],
            "catalyst_timeline": {"near_term": ["财报发布"], "mid_term": [], "long_term": []},
            "open_questions": ["利润率是否改善？"],
        }

        self.assertIn("Language violation", ollama_adapter._language_warning(payload, "ko"))

    def test_run_inference_repairs_language_after_final_english_attempt(self):
        settings = Settings(
            primary_model="mistral:7b",
            enable_experimental_fallback=False,
            ollama_base_url="http://localhost:11434",
            output_language="ko",
        )
        adapter = ollama_adapter.OllamaAdapter(settings)
        english_payload = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.7,"horizon":"short_term","uncertainty":"Execution risk remains.",'
            '"summary":"Demand remains strong despite supply debates.",'
            '"bull_points":["AI demand is holding up and revenue visibility remains firm."],'
            '"bear_points":["Export controls remain a risk to estimate revisions."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":["What is the next demand signal?"],'
            '"cited_doc_ids":["doc-1"]}'
        )
        repaired_payload = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.7,"horizon":"short_term","uncertainty":"실행 리스크는 계속 확인해야 합니다.",'
            '"summary":"수요는 공급 논쟁에도 견조하게 유지되고 있습니다.",'
            '"bull_points":["AI 수요가 유지되어 매출 가시성이 높습니다."],'
            '"bear_points":["수출 규제는 실적 추정치 하향 위험으로 남아 있습니다."],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":["다음 수요 신호는 무엇입니까?"],'
            '"cited_doc_ids":["doc-1"]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(
                 ollama_adapter,
                 "_call_ollama",
                 side_effect=[
                     _response_payload(english_payload),
                     _response_payload(english_payload),
                     _response_payload(repaired_payload),
                 ],
             ):
            result = adapter.run_inference("NVDA", "investment view?", self.context)

        self.assertEqual(result["_meta"]["retry_count"], 2)
        self.assertEqual(result["_meta"]["language_warning"], None)
        self.assertIn("수요", result["summary"])

    def test_run_inference_extracts_evidence_from_object_thesis_points(self):
        adapter = ollama_adapter.OllamaAdapter(self.settings)
        payload = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.7,"horizon":"short_term","uncertainty":"",'
            '"summary":"Demand holds firm.",'
            '"bull_points":[{"text":"AI demand holds up -> revenue visibility stays firm.",'
            '"evidence_doc_ids":["doc-1","doc-2"]}],'
            '"bear_points":[{"text":"Export controls risk -> estimate revisions compress multiples.",'
            '"evidence_doc_ids":["doc-3"]}],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":[],'
            '"cited_doc_ids":["doc-1","doc-2","doc-3"]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(ollama_adapter, "_call_ollama", return_value=_response_payload(payload)):
            result = adapter.run_inference("NVDA", "drivers?", self.context)

        self.assertEqual(result["bull_points"], ["AI demand holds up -> revenue visibility stays firm."])
        self.assertEqual(result["bear_points"], ["Export controls risk -> estimate revisions compress multiples."])
        self.assertEqual(result["bull_evidence_ids"], [["doc-1", "doc-2"]])
        self.assertEqual(result["bear_evidence_ids"], [["doc-3"]])
        self.assertEqual(result["cited_doc_ids"], ["doc-1", "doc-2", "doc-3"])

    def test_run_inference_derives_cited_ids_when_only_evidence_supplied(self):
        adapter = ollama_adapter.OllamaAdapter(self.settings)
        payload = (
            '{"symbol":"NVDA","event_type":"general","sentiment":"positive","importance":"high",'
            '"confidence":0.7,"horizon":"short_term","uncertainty":"","summary":"Demand holds firm.",'
            '"bull_points":[{"text":"A","evidence_doc_ids":["doc-1","doc-2"]}],'
            '"bear_points":[{"text":"B","evidence_doc_ids":["doc-2","doc-3"]}],'
            '"key_metrics":[],"catalyst_timeline":{"near_term":[],"mid_term":[],"long_term":[]},'
            '"open_questions":[],'
            '"cited_doc_ids":[]}'
        )

        with patch.object(ollama_adapter, "_get_installed_models", return_value=["mistral:7b"]), \
             patch.object(ollama_adapter, "_call_ollama", return_value=_response_payload(payload)):
            result = adapter.run_inference("NVDA", "drivers?", self.context)

        self.assertEqual(result["cited_doc_ids"], ["doc-1", "doc-2", "doc-3"])


if __name__ == "__main__":
    unittest.main()
