from abc import ABC, abstractmethod
from typing import List, Dict, Any
from core.schemas.fundamentals import FundamentalsCard
from core.schemas.retrieval import RetrievalItem

class BaseModelRunner(ABC):
    @abstractmethod
    def run_inference(
        self,
        ticker: str,
        question: str,
        context: List[RetrievalItem],
        task_type: str = "general",
        horizon: str = "unspecified",
        fundamentals: FundamentalsCard | None = None,
    ) -> Dict[str, Any]:
        """
        Takes ticker, question, and context, and returns a structured dictionary containing
        the base analysis (sentiment, summary, risks).
        """
        pass
