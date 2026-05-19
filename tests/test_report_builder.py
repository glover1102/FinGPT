import unittest

from core.schemas.request import AnalysisRequest
from core.schemas.response import AnalysisResponse, Citation
from core.schemas.retrieval import RetrievalItem
from pipelines.analyze.report_builder import build_report


class ReportBuilderTests(unittest.TestCase):
    def test_partial_report_surfaces_status_and_evidence(self):
        request = AnalysisRequest(ticker="MSFT", question="What matters next?", model="mistral")
        response = AnalysisResponse(
            ticker="MSFT",
            question=request.question,
            status="partial",
            error_metadata="Empty retrieval result. Potential LLM hallucination.",
            summary="Summary text.",
            bull_points=["Azure demand remains resilient."],
            bear_points=["Capex intensity remains elevated."],
            sentiment="Mixed",
            confidence=0.72,
            conclusion="Near-term setup is mixed.",
            citations=[
                Citation(
                    source="Reuters",
                    title="Microsoft update",
                    date="2026-04-19",
                )
            ],
            raw_context=[
                RetrievalItem(
                    source="Reuters",
                    title="Microsoft update",
                    date="2026-04-19",
                    chunk="Context",
                    score=0.93,
                    metadata={"doc_id": "msft_doc_1"},
                )
            ],
        )

        markdown, html = build_report(request, response, language="en")

        self.assertIn("**Status**: `partial`", markdown)
        self.assertIn("Operator Note", markdown)
        self.assertIn("Core Analysis", markdown)
        self.assertIn("Market Pricing vs Reality", markdown)
        self.assertIn("Synthesis", markdown)
        self.assertIn("Decision Edge", markdown)
        self.assertIn("Investment Decision Checklist", markdown)
        self.assertIn("Key Thesis Evidence", markdown)
        self.assertIn("Evidence Base", markdown)
        self.assertIn("`msft_doc_1`", markdown)
        self.assertIn("Run Status", html)
        self.assertIn("Core Analysis", html)
        self.assertIn("Market Pricing vs Reality", html)
        self.assertIn("Synthesis", html)
        self.assertIn("Decision Edge", html)
        self.assertIn("Investment Decision Checklist", html)
        self.assertIn("Key Thesis Evidence", html)
        self.assertIn("msft_doc_1", html)


if __name__ == "__main__":
    unittest.main()
