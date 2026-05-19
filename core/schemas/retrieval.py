from pydantic import BaseModel, Field
from typing import Dict, Any

class RetrievalItem(BaseModel):
    source: str = Field(..., description="The source type, e.g., 'news', 'transcript'.")
    title: str = Field(..., description="The title of the document or chunk.")
    date: str = Field(..., description="The publication date of the document.")
    chunk: str = Field(..., description="The raw context or chunk text retrieved.")
    score: float = Field(..., description="The semantic search relevancy score.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Any additional metadata associated with the chunk.")
