# Project Scope

## What this Project Is
This repository contains a local financial research assistant. It is designed to run end-to-end quant research execution locally without relying on expensive remote cloud LLMs. The primary flow involves collecting market documents (Yahoo Finance news plus direct FMP transcripts), indexing them via vector databases (Qdrant), retrieving semantics, and executing an Ollama-backed local LLM (`qwen2.5:7b` production primary; `gemma4:e4b` experimental only).

## Included Scope
- Data collection from Yahoo Finance news and direct FMP transcripts.
- Local embeddings and vector ingestion.
- RAG pipeline construction specifically tuned for unstructured financial contexts.
- Local LLM inference (PyTorch, BitsandBytes 4-bit load, Transformers).
- Extensible structured output generation and report generation.

## Excluded Scope
- B2B payment pipelines, Steablecoin rails, and API gateways. (See `archive/finogrid` for past prototypes).
- Deep learning training scripts and Jupyter Notebooks (Migrated to `experiments/notebooks`).
- Blockchain integration.
- Production multi-tenant database serving.

## Success Criteria
The CLI successfully executes:
`python app/cli/main.py --ticker MSFT --question ...`
and produces four distinct artifacts (`request.json`, `response.json`, `report.md`, `report.html`).
