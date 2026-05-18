# OpenBB Workspace Agent Adapter

FinGPT can expose an optional OpenBB Workspace custom agent without changing
the existing FinGPT API/UI routes.

## Enable

```bash
pip install -r requirements-openbb-agent.txt
```

Set only when connecting OpenBB Workspace:

```bash
OPENBB_AGENT_ENABLED=true
OPENBB_AGENT_PUBLIC_URL=http://127.0.0.1:8000
```

## Contract

- `GET /agents.json`: Workspace discovery metadata.
- `POST /query`: OpenBB query stream routed into FinGPT universal analysis.

`/query` maps the latest human/user message to `UniversalRequest.question`.
Selected widget/dashboard ticker context becomes an optional ticker hint. If no
ticker is present, the request is routed as a topic question.

## Provenance

The adapter streams FinGPT memo text plus artifact tables for:

- key metrics with value, unit, as_of, source, freshness, and doc_id
- topic scenarios and execution strategies
- citations and raw evidence document metadata

The adapter does not replace FinGPT's data providers. OpenBB Workspace context
is read-only in v1; FinGPT remains responsible for collection, quant snapshots,
retrieval, and report generation.

## Validate

```bash
python scripts/check_openbb_agent_compat.py --probe-query
python -m core.preflight
python scripts/validation_gate.py
```

For a running local server, use the live HTTP/SSE probe. It sends a diagnostic
dry-run header, so it validates `/agents.json` and `/query` without consuming a
full LLM pipeline run:

```powershell
$env:OPENBB_AGENT_ENABLED = "true"
python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8000
python scripts/probe_openbb_agent_live.py --base-url http://127.0.0.1:8000
```

To run the actual FinGPT pipeline through the same OpenBB adapter, remove the
diagnostic shortcut:

```powershell
python scripts/probe_openbb_agent_live.py --base-url http://127.0.0.1:8000 --full-pipeline
```
