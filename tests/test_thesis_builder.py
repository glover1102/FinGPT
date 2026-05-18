import unittest

from pipelines.analyze.thesis_builder import build_thesis
from core.schemas.retrieval import RetrievalItem


def _item(doc_id: str, title: str, source: str = "Reuters", date: str = "2026-04-19") -> RetrievalItem:
    return RetrievalItem(
        source=source,
        title=title,
        date=date,
        chunk=f"Context for {title}",
        score=0.9,
        metadata={"doc_id": doc_id},
    )


class ThesisBuilderTests(unittest.TestCase):
    def test_positive_thesis_prefers_direct_cited_doc_ids(self):
        result = build_thesis(
            ticker="MSFT",
            question="What are the key positive catalysts for Microsoft in the next 30 days related to Azure and AI?",
            status="success",
            error_metadata=None,
            task_type="catalyst",
            horizon="short_term",
            summary="Azure and AI execution remain the main positives.",
            bull_points=[
                "Azure growth is holding up ahead of earnings, supporting near-term confidence (Document 1)",
                "Copilot adoption is broadening inside enterprise accounts, improving monetization visibility (Document 2)",
            ],
            bear_points=["Heavy AI-related spending could still pressure margins (Document 3)"],
            sentiment="Positive",
            confidence=0.9,
            uncertainty="",
            cited_doc_ids=["doc-2", "doc-1"],
            raw_context=[
                _item("doc-1", "Azure growth holds"),
                _item("doc-2", "Copilot adoption expands"),
                _item("doc-3", "AI spending rises"),
            ],
            language="en",
        )

        self.assertIn("constructive", result.conclusion)
        self.assertEqual([citation.title for citation in result.citations], ["Copilot adoption expands", "Azure growth holds", "AI spending rises"])

    def test_mixed_thesis_uses_document_refs_when_direct_ids_are_missing(self):
        result = build_thesis(
            ticker="MSFT",
            question="Is Microsoft a good investment?",
            status="success",
            error_metadata=None,
            task_type="general",
            horizon="unspecified",
            summary="Microsoft has strong growth, but AI spending and competition complicate the case.",
            bull_points=["Revenue rose 17% year over year and operating income climbed 21% (Document 1)"],
            bear_points=[
                "Azure growth is not clearly outpacing Google Cloud and AWS (Document 2)",
                "Higher AI infrastructure depreciation could weigh on profitability over time (Document 3)",
            ],
            sentiment="Mixed",
            confidence=0.88,
            uncertainty="",
            cited_doc_ids=[],
            raw_context=[
                _item("doc-1", "Revenue growth remains solid"),
                _item("doc-2", "Cloud competition tightens"),
                _item("doc-3", "AI depreciation risk"),
            ],
            language="en",
        )

        self.assertIn("balanced rather than one-sided", result.conclusion)
        self.assertEqual([citation.title for citation in result.citations], ["Revenue growth remains solid", "AI depreciation risk", "Cloud competition tightens"])

    def test_partial_thesis_marks_limited_evidence(self):
        result = build_thesis(
            ticker="UONE",
            question="What is the current financial condition and near-term outlook for Urban One?",
            status="partial",
            error_metadata="Empty retrieval result. Potential LLM hallucination.",
            task_type="general",
            horizon="short_term",
            summary="Urban One has some cost savings, but evidence coverage is thin.",
            bull_points=["Annualized expense savings improved cost control (Document 1)"],
            bear_points=[],
            sentiment="Mixed",
            confidence=0.62,
            uncertainty="Thin recent coverage",
            cited_doc_ids=[],
            raw_context=[_item("doc-1", "Urban One saves costs")],
            language="en",
        )

        self.assertIn("limited-evidence thesis", result.conclusion)
        self.assertIn("Operationally, the thesis is capped", result.conclusion)

    def test_negative_thesis_does_not_invent_bullish_offset(self):
        result = build_thesis(
            ticker="TSLA",
            question="What operational or demand risks could pressure Tesla in the next 60 days?",
            status="success",
            error_metadata=None,
            task_type="risk",
            horizon="short_term",
            summary="Execution and demand risks remain elevated.",
            bull_points=[],
            bear_points=["The success of Tesla's AI5 chip design is not yet confirmed in manufacturing, which could delay self-driving rollout (Document 1)"],
            sentiment="Negative",
            confidence=0.83,
            uncertainty="",
            cited_doc_ids=[],
            raw_context=[_item("doc-1", "AI5 chip risk")],
            language="en",
        )

        self.assertIn("tentatively cautious", result.conclusion)
        self.assertIn("does not surface a comparably strong documented bullish offset", result.conclusion)

    def test_citations_fall_back_to_context_when_model_omits_ids(self):
        result = build_thesis(
            ticker="MSFT",
            question="Summarize current risks and opportunities.",
            status="success",
            error_metadata=None,
            task_type="general",
            horizon="unspecified",
            summary="Cloud demand is supportive, but competition remains a risk.",
            bull_points=["Azure demand supports growth"],
            bear_points=["Competition can pressure margins"],
            sentiment="Mixed",
            confidence=0.72,
            uncertainty="",
            cited_doc_ids=[],
            raw_context=[_item("doc-1", "Azure growth context")],
            language="en",
        )

        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.citations[0].doc_id, "doc-1")
        self.assertEqual(result.citations[0].title, "Azure growth context")


if __name__ == "__main__":
    unittest.main()
