from pathlib import Path
import re
import unittest


APP_JS = Path(__file__).resolve().parents[1] / "app" / "web" / "app.js"


class UiRoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_JS.read_text(encoding="utf-8")

    def test_non_compare_runs_use_universal_stream(self):
        match = re.search(r"async function runAnalysis\(e\) \{(?P<body>.*?)\n\}\n\n// ---------- Compare mode", self.source, re.S)
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("runStreamAnalysis(API.universalStream, payload, payload)", body)
        self.assertNotIn("API.stream", body)
        self.assertNotIn("useUniversal", body)

    def test_intent_normalizer_preserves_tickerless_topic_path(self):
        self.assertIn("function normalizeResearchIntent", self.source)
        self.assertIn("auto_topic", self.source)
        self.assertIn("extracted_ticker", self.source)
        self.assertIn("ticker 없이 질의 가능", self.source)

    def test_every_declared_progress_stage_exists_in_dom(self):
        html = (Path(__file__).resolve().parents[1] / "app" / "web" / "index.html").read_text(encoding="utf-8")
        stage_match = re.search(r"const STAGES = \[(?P<items>.*?)\];", self.source, re.S)
        self.assertIsNotNone(stage_match)
        stages = re.findall(r'"([^"]+)"', stage_match.group("items"))
        dom_stages = set(re.findall(r'data-stage="([^"]+)"', html))
        self.assertTrue(stages)
        self.assertEqual(set(stages), dom_stages)

    def test_progress_stage_helpers_are_null_safe(self):
        self.assertIn("function progressNode(stage)", self.source)
        self.assertIn("if (!node) return", self.source)

    def test_quant_backtest_workbench_uses_artifact_endpoint(self):
        match = re.search(r"async function runHomeBacktest\(\) \{(?P<body>.*?)\n\}\n\nasync function loadQuantRunHistory", self.source, re.S)
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("fetch(API.quantBacktest", body)
        self.assertIn("renderQuantBacktestResult(data, request)", body)
        self.assertIn("renderQuantDiagnosticsPanel(data)", self.source)
        self.assertIn("loadQuantRunHistory(true)", body)
        self.assertNotIn("fetch(API.backtestRun", body)

    def test_quant_run_history_can_reopen_artifacts(self):
        self.assertIn("API.quantBacktestBundle", self.source)
        self.assertIn("function loadQuantBacktestArtifact", self.source)
        self.assertIn("data-quant-run-id", self.source)


if __name__ == "__main__":
    unittest.main()
