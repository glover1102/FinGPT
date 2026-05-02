# Project Map

This document outlines the main directories and their responsibilities.

- `app/`
  - `cli/`: Contains CLI implementations mapping arguments into request objects.
  - `api/`: Scaffold area strictly intended for exposing the identical pipeline over REST via FastAPI/Flask in the future.
- `core/`
  - `config/`: Configuration rules mapping `.env` and hardcoded project limits into typed configurations (`Settings`).
  - `schemas/`: Structured request and response boundaries (Pydantic). 
  - `prompts/`: Isolated text layouts to decouple string building from Python parsing.
  - `utils/`: Common cross-cutting helpers (e.g. data normalization).
- `pipelines/`
  - `collect/`: Source-aware collection logic for Yahoo Finance news and direct FMP transcripts.
  - `ingest/`: Embedding extraction and Qdrant ingestion rules.
  - `retrieve/`: Query embeddings and semantic cosine similarity search methods.
  - `infer/`: Logic for handling different LLMs (`FinGPTAdapter`, `RunnerFactory`).
  - `analyze/`: Deterministic data manipulation post-LLM extraction (e.g., sentiment parsing, mapping confidence).
  - `orchestration/`: Binds all the preceding modules into an end-to-end operational execution pipe (`research_pipeline.py`).
- `data/`: Outputs, storage, raw ingested chunks, and DB results.
- `reports/`: Evaluated reports and latest analysis summaries.
- `tests/`: Project test suite, including production and unit tests.
- `legacy/`: Consolidated area for research validation, archived stack versions, and experiments.
