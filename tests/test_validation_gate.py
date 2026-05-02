from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config.settings import Settings
from scripts import validation_gate
from scripts.validation_gate import (
    ValidationError,
    evaluate_preflight_gate,
    run_api_smoke_subprocess,
    run_browser_ui_gate,
    run_openbb_agent_contract_gate,
    run_command,
    run_runtime_compat_gate,
    validate_saved_outputs,
)


class ValidationGateTests(unittest.TestCase):
    def test_evaluate_preflight_gate_allows_entitlement_warnings_only(self) -> None:
        ok, failures, warnings = evaluate_preflight_gate(
            {
                "passed": True,
                "checks": [
                    {"name": "QDRANT_SERVICE", "ok": True, "detail": "ok"},
                    {"name": "OLLAMA_SERVICE", "ok": True, "detail": "ok"},
                    {"name": "FMP_STOCK_NEWS", "ok": False, "detail": "entitlement_required - plan issue"},
                    {"name": "TRANSCRIPT_PROVIDER", "ok": False, "detail": "entitlement_required - plan issue"},
                ],
            }
        )
        self.assertTrue(ok)
        self.assertEqual(failures, [])
        self.assertEqual(len(warnings), 2)

    def test_evaluate_preflight_gate_allows_known_rate_limit_warnings(self) -> None:
        ok, failures, warnings = evaluate_preflight_gate(
            {
                "passed": False,
                "checks": [
                    {"name": "QDRANT_SERVICE", "ok": True, "detail": "ok"},
                    {"name": "OLLAMA_SERVICE", "ok": True, "detail": "ok"},
                    {"name": "YFINANCE_FEED", "ok": True, "detail": "ok"},
                    {"name": "FMP_API_KEY", "ok": False, "detail": "FMP probe returned unexpected status 429"},
                    {"name": "FMP_STOCK_NEWS", "ok": False, "detail": "FMP stock news is rate-limiting requests."},
                    {"name": "TRANSCRIPT_PROVIDER", "ok": False, "detail": "Transcript provider is rate-limiting requests."},
                ],
            }
        )
        self.assertTrue(ok)
        self.assertEqual(failures, [])
        self.assertEqual(len(warnings), 3)

    def test_evaluate_preflight_gate_blocks_critical_or_unexpected_failures(self) -> None:
        ok, failures, warnings = evaluate_preflight_gate(
            {
                "passed": False,
                "checks": [
                    {"name": "OLLAMA_SERVICE", "ok": False, "detail": "unreachable"},
                    {"name": "FMP_API_KEY", "ok": False, "detail": "missing"},
                ],
            }
        )
        self.assertFalse(ok)
        self.assertTrue(failures)
        self.assertEqual(warnings, [])

    def test_validate_saved_outputs_checks_mode_language_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "latest_report.md").write_text("# report", encoding="utf-8")
            (root / "latest_report.html").write_text("<html></html>", encoding="utf-8")
            (root / "latest_collection.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
            (root / "latest_response.json").write_text(
                json.dumps(
                    {
                        "ticker": "MSFT",
                        "question": "q",
                        "status": "success",
                        "summary": "한국어 요약입니다. 매출과 마진 흐름을 근거로 판단합니다.",
                        "conclusion": "한국어 결론입니다. 리스크와 기회를 함께 봐야 합니다.",
                        "bull_points": ["상승 요인 1", "상승 요인 2"],
                        "bear_points": ["하락 리스크 1", "하락 리스크 2"],
                        "citations": [{"source": "news", "title": "기사", "date": "2026-04-24"}],
                        "raw_context": [{"chunk": "본문"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = validate_saved_outputs(
                root,
                expected_modes={"single_ticker"},
                require_evidence=True,
            )

        self.assertEqual(result["mode"], "single_ticker")
        self.assertEqual(result["citation_count"], 1)
        self.assertEqual(result["evidence_count"], 1)
        self.assertTrue(result["decision_richness"]["ok"])

    def test_validate_saved_outputs_rejects_topic_without_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "latest_report.md").write_text("# report", encoding="utf-8")
            (root / "latest_report.html").write_text("<html></html>", encoding="utf-8")
            (root / "latest_collection.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
            (root / "latest_response.json").write_text(
                json.dumps(
                    {
                        "mode": "sector_macro",
                        "theme": "credit risk",
                        "status": "success",
                        "summary": "한국어 요약입니다. 신용 리스크를 근거 중심으로 판단합니다.",
                        "executive_summary": "한국어 요약입니다.",
                        "conclusion": "한국어 결론입니다.",
                        "asset_overview": ["대상 시장 개요"],
                        "macro_regime": ["금리 환경"],
                        "rate_structure": ["시장 구조"],
                        "investment_judgment": ["투자 판단"],
                        "scenario_analysis": [],
                        "execution_strategy": [],
                        "key_drivers": ["상방 동인 1", "상방 동인 2"],
                        "key_risks": ["하방 리스크 1", "하방 리스크 2"],
                        "key_metrics": [
                            {
                                "name": "proxy",
                                "value": "1",
                                "unit": "index",
                                "as_of": "2026-04-24",
                                "source": "test",
                            }
                        ],
                        "citations": [{"source": "news", "title": "기사", "date": "2026-04-24"}],
                        "raw_context": [{"doc_id": "doc-1", "date": "2026-04-24", "chunk": "본문"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValidationError, "decision richness gate failed"):
                validate_saved_outputs(
                    root,
                    expected_modes={"sector_macro"},
                    require_evidence=True,
                )

    def test_runtime_compat_gate_reports_python_and_packages(self) -> None:
        report = run_runtime_compat_gate()
        self.assertEqual(report["status"], "passed")
        self.assertIn("python", report)
        self.assertIn("fastapi", report["packages"])

    def test_openbb_agent_contract_gate_passes_when_disabled(self) -> None:
        with patch.object(validation_gate, "load_settings", return_value=Settings(openbb_agent_enabled=False)):
            result = run_openbb_agent_contract_gate()
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["enabled"])

    def test_run_command_captures_utf8_output(self) -> None:
        result = run_command(
            "utf8-smoke",
            [sys.executable, "-c", "print('한국어 로그')"],
            timeout_s=20,
        )

        self.assertTrue(result["ok"])
        self.assertIn("한국어 로그", result["stdout"])


    def test_api_smoke_subprocess_reads_child_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observed_extra_env: dict[str, str] = {}

            def fake_run_command(label, command, *, timeout_s, cwd=validation_gate.PROJECT_ROOT, extra_env=None):
                observed_extra_env.update(extra_env or {})
                output_index = command.index("--api-smoke-output") + 1
                output_path = Path(command[output_index])
                output_path.write_text(
                    json.dumps({"status": "passed", "results": {"health": {"status": "ok"}}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return {
                    "label": label,
                    "command": command,
                    "ok": True,
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "elapsed_s": 0.1,
                }

            with patch.object(validation_gate, "OUTPUTS_DIR", root), \
                 patch.object(validation_gate, "run_command", side_effect=fake_run_command):
                result = run_api_smoke_subprocess(timeout_s=5)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["results"]["health"]["status"], "ok")
        self.assertEqual(observed_extra_env.get("FINGPT_VALIDATION_FAST_INFERENCE"), "1")

    def test_quality_gate_accepts_passed_artifact_after_command_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "quality_review_results.json"

            def fake_run_command(label, command, *, timeout_s, cwd=validation_gate.PROJECT_ROOT, extra_env=None):
                output_index = command.index("--output") + 1
                Path(command[output_index]).write_text(
                    json.dumps({"summary": {"gate_passed": True, "gate_failures": 0}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return {
                    "label": label,
                    "command": command,
                    "ok": False,
                    "returncode": -9,
                    "stdout": "",
                    "stderr": "timeout",
                    "elapsed_s": timeout_s,
                }

            with patch.object(validation_gate, "QUALITY_RESULTS_PATH", output_path), \
                 patch.object(validation_gate, "run_command", side_effect=fake_run_command):
                result = validation_gate.run_quality_gate()

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["summary"]["gate_failures"], 0)
        self.assertIn("warning", result)

    def test_latency_gate_accepts_passed_artifact_after_command_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "topic_latency_profile.json"

            def fake_run_command(label, command, *, timeout_s, cwd=validation_gate.PROJECT_ROOT, extra_env=None):
                output_index = command.index("--output") + 1
                Path(command[output_index]).write_text(
                    json.dumps(
                        {
                            "summary": {
                                "gate_passed": True,
                                "gate_failures": 0,
                                "latency": {"topic_cases": 1},
                            }
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return {
                    "label": label,
                    "command": command,
                    "ok": False,
                    "returncode": -9,
                    "stdout": "",
                    "stderr": "timeout",
                    "elapsed_s": timeout_s,
                }

            with patch.object(validation_gate, "LATENCY_RESULTS_PATH", output_path), \
                 patch.object(validation_gate, "run_command", side_effect=fake_run_command):
                result = validation_gate.run_latency_gate()

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["latency"]["topic_cases"], 1)
        self.assertIn("warning", result)

    def test_write_report_uses_browser_ui_gate_without_manual_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = {
                "generated_at": "2026-05-02T00:00:00Z",
                "automated_passed": True,
                "blocking_reason": None,
                "phases": {
                    "runtime_compat_gate": {"status": "passed"},
                    "browser_ui_gate": {
                        "status": "passed",
                        "url": "http://127.0.0.1:8000/ui/",
                        "browser": "chromium",
                        "checked_interactions": [{"label": "raw tab"}],
                        "screenshots": {"success": str(root / "success.png")},
                    },
                },
            }
            with patch.object(validation_gate, "OUTPUTS_DIR", root / "outputs"), \
                 patch.object(validation_gate, "REPORTS_DIR", root / "reports"):
                paths = validation_gate._write_report(report)

            payload = json.loads(Path(paths["latest_json"]).read_text(encoding="utf-8"))
            markdown = Path(paths["latest_md"]).read_text(encoding="utf-8")

        self.assertNotIn("manual_ui", payload["phases"])
        self.assertIn("browser_ui_gate", payload["phases"])
        self.assertIn("## Browser UI Gate", markdown)
        self.assertNotIn("Manual UI Checklist", markdown)
        self.assertNotIn("pending_manual", markdown)

    def test_browser_ui_dependency_missing_blocks_required_gate(self) -> None:
        with patch.object(validation_gate.importlib.util, "find_spec", return_value=None):
            with self.assertRaisesRegex(ValidationError, "Playwright is required"):
                validation_gate._ensure_browser_ui_dependencies(required=True)
            skipped = validation_gate._ensure_browser_ui_dependencies(required=False)

        self.assertEqual(skipped["status"], "skipped")
        self.assertFalse(skipped["available"])

    def test_browser_ui_skip_is_forbidden_for_release_candidate(self) -> None:
        with self.assertRaisesRegex(ValidationError, "not allowed"):
            run_browser_ui_gate(skip=True, release_candidate=True)

        skipped = run_browser_ui_gate(skip=True, release_candidate=False)
        self.assertEqual(skipped["status"], "skipped")

    def test_browser_ui_failure_payload_preserves_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            latest = Path(tmp) / "outputs"
            latest.mkdir()
            for name in ("latest_response.json", "latest_report.md", "latest_report.html", "latest_collection.json"):
                (latest / name).write_text("{}", encoding="utf-8")
            failure = validation_gate.BrowserUiGateFailure(
                "tab failed",
                {
                    "status": "failed",
                    "url": "http://127.0.0.1:1234/ui/",
                    "error": "tab failed",
                    "screenshots": {"failure": str(Path(tmp) / "failure.png")},
                    "checked_interactions": [{"label": "analysis form"}],
                },
            )
            with patch.object(validation_gate, "OUTPUTS_DIR", latest), \
                 patch.object(validation_gate, "_ensure_browser_ui_dependencies", return_value={"available": True}), \
                 patch.object(validation_gate, "_start_validation_server", return_value=(None, "http://127.0.0.1:1234")), \
                 patch.object(validation_gate, "_stop_validation_server"), \
                 patch.object(validation_gate, "_run_browser_ui_checks", side_effect=failure):
                result = run_browser_ui_gate(screenshot_dir=Path(tmp))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["screenshots"]["failure"], str(Path(tmp) / "failure.png"))
        self.assertIn("latest_output", result)


if __name__ == "__main__":
    unittest.main()
