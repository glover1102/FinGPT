# Evaluation Plan

## Evaluation Criteria
- **Retrieval Relevance**: Ensure OpenBB pulled the proper transcripts and that Qdrant queries isolate the correct earnings texts.
- **Citation Coverage**: Validate that the LLM response accurately cites document IDs without injecting its own external context outside the prompt.
- **Answer Completeness**: Ensure the JSON answers adhere to the schema required by the pipeline.
- **Hallucination Risk**: Measure discrepancy rates between summary facts and context hits.
- **Latency**: Ensure context generation, load, and query takes < 15s, while local model generation operates at < 120s on standard hardware.

## Basic Grounding Tests
A small suite of pre-configured unit tests focusing solely on context mapping.

*Test Query 1 (General)*: "What was management's forward guidance on revenue growth?"
*Test Query 2 (Risk)*: "What specific macro-economic factors hurt margins in this quarter?"
