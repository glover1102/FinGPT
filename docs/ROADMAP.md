# Roadmap

## Phase 1: Validation Hardening (Current)
1. **Schema Finalization**: Extend `AnalysisResponse` to handle timeout metadata and graceful failure states cleanly.
2. **Boundary Validation**: Ensure absolutely no dead code or cyclic dependency references exist between decoupled layers.

## Phase 2: Async API Development
1. **FastAPI Expansion**: Expose `/api/v1/research/analyze` and sub-module boundary endpoints (`/data`, `/signal`).
2. **Non-blocking Wrapper**: Ensure `asyncio.to_thread` guarantees Qdrant, OpenBB, and Huggingface synchronous bottlenecks do not lock event loops.

## Phase 3: Execution Services
1. **Execution Pre-checks**: Draft the Execution integration interface allowing portfolios checks prior to signals completing final evaluation.

## Phase 4: Risk Upgrades
1. **Pluggable Risk Module**: Formally replace naive keyword logic in `pipelines/analyze/risk_analysis.py` with an abstraction interface running standalone smaller models.

## Phase 5: Streaming Interfaces
1. **SSE Outputs (Finality)**: Post stability validation, upgrade API execution endpoints to stream out Ollama/Mistral tokens via Server-Sent Events for real-time reactivity in custom dashboards.
