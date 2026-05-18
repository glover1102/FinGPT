# FinGPT Decision-Grade Research Upgrade Checklist

This file is the working checklist for the requested finance project upgrade. It records the user-provided operating instructions, constraints, implementation tasks, acceptance criteria, and live verification status.

Status legend: `pending`, `in_progress`, `reviewed`, `done`, `blocked`.

## 0. Source Instructions Captured

Status: `reviewed`

The implementation must transform FinGPT from a generic local financial RAG summary tool into a decision-grade local investment research assistant using the existing local stack:

- Local RAG pipeline
- Qdrant vector database
- Ollama local LLM route
- Financial data collectors
- Evidence-based analysis
- JSON / Markdown / HTML report generation
- API server
- Web UI
- Evaluation tools

The agent role is senior AI systems engineer, financial RAG architect, backend engineer, frontend engineer, evaluation engineer, frontend engineer, and investment research workflow designer.

The final system must better answer:

- What is the current investment view?
- Why is that view justified?
- What evidence supports each claim?
- How reliable is the evidence?
- Which numbers are grounded in actual data?
- What are the base, bull, and bear scenarios?
- What would change the investment view?
- What should be monitored next?
- What risks could invalidate the thesis?
- How confident should the user be, and why?

## 1. Hard Constraints

Status: `reviewed`

- Preserve existing core endpoints, especially existing research endpoints, report generation behavior, UI routes, and CLI commands.
- Do not weaken current-run-only retrieval. Stale Qdrant documents from previous runs must not be used unless historical comparison is explicitly requested.
- Do not allow the LLM to invent numbers. Numeric values must come from provider data, deterministic calculation, cited evidence, or explicitly user-provided input.
- Do not produce investment conclusions without evidence. Weak, incomplete, stale, or low-quality evidence must lower confidence and surface warnings.
- Do not rely on a single news article for high-confidence conclusions.
- Do not make UI-only improvements without backend validation.
- Do not mark work complete unless code is implemented, tests are added or updated, validation is attempted, and limitations are documented.
- Do not silently swallow failures. Surface failures in execution metadata, diagnostics, logs, or warnings.
- Do not introduce cloud dependencies unless already supported by project configuration.
- Do not change environment assumptions without documentation.
- Do not fake metrics, test results, or validation outcomes.
- Preserve backward compatibility for old saved runs and existing clients.

## 2. Execution Protocol

Status: `reviewed`

1. Repository inspection
   - Inspect directory structure.
   - Identify backend, frontend, pipeline, schema, report, test, evaluation, Qdrant, evidence, metrics, confidence, and UI consumption modules.
2. Architecture mapping
   - Map request schema, response schema, pipeline stages, document schema, retrieval metadata, report generation path, UI data flow, and evaluation suite.
3. Minimal safe implementation plan
   - Implement compatible additive schema fields and validation.
   - Prefer small modules and deterministic checks.
4. Implementation
   - Evidence quality scoring.
   - Numeric grounding validation.
   - Query planner.
   - Decision-oriented schema.
   - Confidence calibration.
   - Evaluation metrics.
   - Report updates.
   - UI updates.
   - Tests.
5. Validation
   - Run unit tests, targeted integration/API checks, frontend syntax/build checks where available, quality review where practical, and browser validation when UI changes.
6. Final report
   - Summarize implementation, files changed, schema fields, behavior, tests, commands, results, limitations, and next steps.

## 3. Repository Implementation Map

Status: `reviewed`

Current findings:

- Backend API entrypoints: `app/api/server.py`, `app/api/openbb_agent.py`
- CLI entrypoint: `app/cli/main.py`
- Frontend: `app/web/index.html`, `app/web/app.js`, `app/web/styles.css`
- Request schema: `core/schemas/request.py`
- Single-name response schema: `core/schemas/response.py`
- Topic response schema: `core/schemas/topic.py`
- Retrieval schema: `core/schemas/retrieval.py`
- Existing quant schema: `core/schemas/quant.py`
- Validation metrics: `core/utils/validation_metrics.py`
- Asset classification: `core/utils/asset_classifier.py`
- Single-name orchestration: `pipelines/orchestration/research_pipeline.py`
- Topic orchestration: `pipelines/orchestration/topic_pipeline.py`
- Universal dispatch: `pipelines/orchestration/dispatch.py`
- Collection: `pipelines/collect/*`
- Qdrant ingest: `pipelines/ingest/qdrant_ingestor.py`
- Qdrant retrieval: `pipelines/retrieve/qdrant_retriever.py`, `pipelines/retrieve/multi_query_retriever.py`, `pipelines/retrieve/topic_retriever.py`
- LLM inference: `pipelines/infer/*`
- Report generation: `pipelines/analyze/report_builder.py`, `pipelines/analyze/topic_report_builder.py`
- Output persistence: `pipelines/output/output_writer.py`, `pipelines/output/run_history.py`, `pipelines/output/exporters.py`
- Evaluation: `quality_review.py`, `scripts/validation_gate.py`, `scripts/profile_topic_latency.py`
- Tests: `tests/*`

Current-run-only retrieval observation:

- Single-name path collects `current_doc_ids`, retrieves from Qdrant, then filters retrieved chunks through `_filter_current_run_context()` in `pipelines/orchestration/research_pipeline.py`.
- If no current-run documents exist, the pipeline returns a no-context partial response and blocks stale Qdrant context.

## 4. Required Research Lenses and Query Planner

Status: `done`

The query planner must produce:

```json
{
  "intent": "...",
  "asset_type": "...",
  "lens": "...",
  "required_evidence_buckets": [],
  "sub_queries": [],
  "reasoning_summary": "...",
  "fallback_behavior": "..."
}
```

Required lenses:

- `equities_fundamental`
- `rates_bonds`
- `macro`
- `fx`
- `commodity`
- `crypto`
- `credit`
- `sector_theme`
- `etf`
- `general_financial_research`

Representative mappings:

- `TLT` -> `bond_etf`, `rates_bonds`, buckets: `price_action`, `duration`, `treasury_yields`, `inflation`, `fed_policy`, `recession_risk`, `real_yields`, `scenario_risks`
- `AAPL` -> `equity`, `equities_fundamental`, buckets: `revenue`, `margins`, `valuation`, `product_cycle`, `capital_return`, `guidance`, `risk_factors`, `analyst_estimates`
- `BTC` -> `crypto`, buckets: `liquidity`, `risk_appetite`, `ETF_flows`, `regulation`, `technical_trend`, `macro_correlation`

Deliverables:

- Query planner module.
- Query planner schema.
- Integration before retrieval.
- Tests for representative asset types.
- `retrieval_plan` in `execution_meta.extras`.

Implementation status:

- Added `core/utils/query_planner.py`.
- Integrated retrieval plans into single-name and topic execution metadata.
- Added `tests/test_query_planner.py`.

## 5. Evidence Integrity

Status: `done`

Evidence quality schema:

```json
{
  "source_type": "sec_filing | fred | official_ir | earnings_transcript | provider_data | reputable_news | rss_news | unknown",
  "reliability_score": 0.0,
  "freshness_score": 0.0,
  "specificity_score": 0.0,
  "overall_score": 0.0,
  "quality_rationale": "..."
}
```

Source reliability defaults:

- SEC filing: `0.95`
- FRED: `0.95`
- Exchange/provider market data: `0.90`
- Earnings transcript: `0.90`
- Official investor relations: `0.85`
- Reputable financial news: `0.75`
- Yahoo Finance summary/news: `0.65`
- Google RSS/news snippet: `0.55`
- Unknown scraped text: `0.30`

Freshness scoring:

- Same day to 7 days: high
- 8 to 30 days: medium-high
- 31 to 90 days: medium
- 91 to 365 days: low
- Older than 365 days: very low unless structural source

Major claims requiring evidence:

- Investment rating
- Bull thesis
- Bear thesis
- Scenario thesis
- Key risks
- Numeric metrics
- Monitoring triggers
- Confidence explanation

Deliverables:

- Evidence scoring module.
- Evidence quality fields in response schema.
- Evidence diagnostics.
- Tests for scoring logic.

Implementation status:

- Added `core/utils/evidence_quality.py`.
- Added additive `evidence_quality` response field.
- Added `tests/test_evidence_quality.py`.

## 6. Numeric Grounding

Status: `done`

Numeric metric schema:

```json
{
  "name": "...",
  "value": 0.0,
  "unit": "...",
  "as_of": "YYYY-MM-DD",
  "source": "...",
  "source_type": "...",
  "evidence_doc_ids": [],
  "calculation_method": "...",
  "is_deterministic": true,
  "grounding_status": "grounded | partially_grounded | ungrounded | unknown"
}
```

Validation rules:

- `name` exists.
- `value` exists and is parseable or explicitly marked unknown.
- `unit` exists.
- `as_of` exists.
- `source` exists.
- At least one grounding mechanism exists: evidence doc ids, provider source, deterministic calculation method, or user-provided source.

Invalid metrics must:

- Receive `grounding_status` of `ungrounded` or `partially_grounded`.
- Add warning to `execution_meta.extras.numeric_grounding_warnings`.
- Lower `numeric_grounding_rate`.
- Cap confidence when important metrics are weak.

Deliverables:

- Numeric validator module.
- Numeric grounding rate.
- Confidence cap integration.
- Tests.

Implementation status:

- Added `core/utils/numeric_grounding.py`.
- Extended `KeyMetric` with `source_type`, `calculation_method`, `is_deterministic`, and `grounding_status`.
- Added `tests/test_numeric_grounding.py`.

## 7. Decision-Oriented Schema

Status: `done`

Additive fields:

- `decision_view`
- `scenario_analysis`
- `monitoring_plan`
- `risk_management`
- `confidence_rationale`
- `quality_metrics`
- `evidence_quality`
- `warnings`

Backward compatibility fields to preserve:

- `summary`
- `sentiment`
- `bull_points`
- `bear_points`
- `key_metrics`
- `citations`
- `raw_context`
- `execution_meta`

Deliverables:

- Extended schemas.
- Prompt or deterministic fallback support.
- Report template updates.
- API compatibility tests.

Implementation status:

- Extended `AnalysisResponse` and `TopicResponse` additively.
- Added deterministic enrichment in `core/utils/decision_support.py`.
- Added `tests/test_decision_support_schema.py`.

## 8. Confidence Calibration

Status: `done`

Inputs:

- Evidence coverage
- Claim support rate
- Numeric grounding rate
- Evidence quality average
- Freshness coverage
- Source diversity
- Required bucket coverage
- Stale context rate
- Retrieval success
- Official source presence
- Deterministic metric presence

Confidence cap rules:

- No evidence: confidence <= `0.20`
- Only low-quality RSS/news snippets: confidence <= `0.55`
- Important numeric grounding failure: confidence <= `0.60`
- `claim_support_rate < 0.50`: confidence <= `0.50`
- `stale_context_rate > 0.30`: confidence <= `0.55`
- `required_bucket_coverage < 0.50`: confidence <= `0.60`
- Official filings/provider data/deterministic metrics can permit confidence above `0.75`.
- Fresh, diverse, specific, numerically grounded evidence can permit confidence above `0.85`.

Deliverables:

- Confidence calibration module.
- Integration into analysis response.
- Tests.

Implementation status:

- Added `core/utils/confidence_calibration.py`.
- Integrated confidence caps into `enrich_research_response()`.
- Added `tests/test_confidence_calibration.py`.

## 9. Evaluation Metrics

Status: `done`

Required metrics:

- `claim_support_rate`
- `numeric_grounding_rate`
- `evidence_quality_average`
- `freshness_coverage`
- `stale_context_rate`
- `source_diversity`
- `required_bucket_coverage`
- `retrieval_failure_rate`
- `schema_validity_rate`

Required test cases or fixtures:

- AAPL fundamental analysis
- NVDA AI capex / valuation risk
- TLT rates and duration analysis
- GLD inflation / real yield analysis
- BTC liquidity and risk appetite analysis
- JPM credit risk
- SPY macro risk
- `005930.KS` semiconductor cycle if international ticker support exists

Deliverables:

- Evaluation metrics.
- Tests or fixtures.
- Quality review integration.
- Documentation.

Implementation status:

- Added deterministic quality metric computation in `core/utils/validation_metrics.py`.
- Integrated decision-grade quality metrics into `quality_review.py`.
- Quality metrics now include claim support, numeric grounding, evidence quality, freshness, stale context, source diversity, and required bucket coverage where available.

## 10. Backend API Integration

Status: `done`

API response must include:

- `decision_view`
- `scenario_analysis`
- `monitoring_plan`
- `risk_management`
- `confidence_rationale`
- `evidence_quality`
- `quality_metrics`
- `numeric_grounding_warnings`
- `retrieval_plan` in `execution_meta.extras`
- confidence caps in `execution_meta.extras`

Failure behavior:

- Do not crash endpoints when new fields cannot be generated.
- Return partial response where supported.
- Expose missing fields and warnings in `execution_meta`.

Deliverables:

- API integration.
- Schema tests.
- Endpoint smoke tests.

Implementation status:

- Extended `AnalysisResponse` and `TopicResponse` additively.
- Integrated enrichment in single-ticker and topic orchestration paths.
- Preserved existing `/api/v1/research/analyze` and added backward-compatible `/api/v1/research` alias.
- Added API routing contract coverage for the legacy research endpoint.

## 11. Frontend UI

Status: `done`

UI sections:

- Top summary panel: ticker, asset type, as-of date, rating, confidence, evidence coverage, numeric grounding rate.
- Decision panel: rating, time horizon, decision summary, primary thesis, what would change the view.
- Scenario panel: base/bull/bear cases, probability, drivers, risks, evidence links.
- Metrics panel: key metrics, unit, as-of date, source, grounding status, warnings.
- Evidence panel: source type, reliability, freshness, specificity, overall score, linked claims.
- Risk panel: main risks, invalidating conditions, risk level, position sizing comment.
- Diagnostics panel: retrieval plan, bucket coverage, claim support, numeric grounding, evidence quality, confidence caps.

Deliverables:

- UI rendering updates.
- Defensive handling for missing fields and old runs.
- Syntax/build validation.
- Browser validation.

Implementation status:

- Updated `app/web/app.js` to render decision view, scenario bundles, risk management, confidence rationale, quality metrics, numeric grounding status, retrieval plan, and confidence caps defensively.
- Existing old-run rendering remains supported through fallback guards.
- JavaScript syntax validation passed. Browser validation is recorded in the live validation log.

## 12. Report Generation

Status: `done`

Report order:

1. Header
2. Decision View
3. What Would Change This View
4. Scenario Analysis
5. Key Metrics
6. Bullish Evidence
7. Bearish Evidence
8. Monitoring Plan
9. Risk Management
10. Evidence Quality
11. Confidence Rationale
12. Diagnostics
13. Raw Citations / Evidence IDs

Deliverables:

- Markdown report updates.
- HTML report updates.
- JSON includes new schema fields.
- Snapshot/report tests where available.

Implementation status:

- Updated single-name Markdown and HTML reports with Decision View, What Would Change This View, Scenario Analysis, Monitoring Plan, Risk Management, Confidence Rationale, warnings, and grounded metric metadata.
- Updated topic Markdown and HTML reports with decision and quality audit sections.
- JSON output includes additive schema fields through the response models.

## 13. Testing Requirements

Status: `done`

Required tests:

- Evidence quality tests.
- Numeric grounding tests.
- Query planner tests.
- Confidence calibration tests.
- Schema compatibility tests.
- Current-run-only retrieval regression tests.
- Report tests.
- API smoke tests where practical.
- Frontend syntax/build validation.

## 14. Acceptance Criteria

Status: `done`

The implementation is acceptable only if:

- Existing research endpoint still works.
- Existing response fields are preserved.
- `decision_view` is returned.
- `scenario_analysis` is returned.
- `monitoring_plan` is returned.
- `risk_management` is returned.
- Evidence quality scoring exists and is tested.
- Numeric grounding validation exists and is tested.
- Query planner exists and is tested.
- Confidence calibration exists and is tested.
- Quality metrics are computed.
- Reports include new sections.
- UI renders new sections or gracefully handles them.
- Current-run-only retrieval remains enforced.
- Tests are run or attempted.
- Failures are reported honestly.

## 15. Live Validation Log

Status: `done`

Commands and outcomes:

- `python -m py_compile core\schemas\response.py core\schemas\topic.py core\utils\query_planner.py core\utils\evidence_quality.py core\utils\numeric_grounding.py core\utils\confidence_calibration.py core\utils\decision_support.py pipelines\orchestration\research_pipeline.py pipelines\orchestration\topic_pipeline.py pipelines\analyze\report_builder.py pipelines\analyze\topic_report_builder.py quality_review.py` -> passed.
- `node --check app\web\app.js` -> passed.
- `python -m pytest tests\test_query_planner.py tests\test_evidence_quality.py tests\test_numeric_grounding.py tests\test_confidence_calibration.py tests\test_decision_support_schema.py -q` -> 18 passed.
- `python -m pytest tests\test_report_builder.py tests\test_topic_report_builder.py tests\test_validation_metrics.py tests\test_research_pipeline_fallback.py tests\test_api_routing_contract.py -q` -> 26 passed.
- `python scripts\check_ui_contract.py` -> passed.
- `python -m py_compile app\api\server.py` -> passed.
- `python -m pytest tests\test_api_routing_contract.py -q` -> 7 passed.
- `python -m pytest tests -q` -> 279 passed, 3 subtests passed.
- `python quality_review.py --help` -> passed; quality review CLI exposes `--suite` and `--measure-latency`.
- `python scripts\check_ui_contract.py` -> passed.
- `python -m core.preflight` -> passed; all critical dependencies operational, including Qdrant, FRED, SEC, yfinance, Ollama service, and `qwen2.5:7b`.
- `python scripts\validation_gate.py` -> first run blocked on stale UI DOM marker `tvHeatmapWidget`; fixed gate marker to `homeHeatmap` because current UI uses intraday yfinance heatmap to avoid TradingView EOD mislabeling.
- `python scripts\validation_gate.py` -> passed after gate/UI contract alignment.
- `python -m pytest tests\test_validation_gate.py tests\test_api_routing_contract.py -q` -> 17 passed.
- `python -m py_compile scripts\validation_gate.py` -> passed.
- Browser validation with Playwright MCP -> opened current `/ui/`, loaded latest successful NVDA run, verified Dashboard/Quant/Scenarios/Diagnostics tabs render without crashing old saved runs, and captured `decision-grade-ui-validation.png`.

## 16. Final Deep Verification

Status: `done`

Final hardening completed during release-candidate validation:

- Added citation fallback in `pipelines/analyze/thesis_builder.py` so evidence-backed context still produces citations when a model omits explicit citation IDs.
- Added current-run collected-document backfill in `pipelines/orchestration/research_pipeline.py` so a current run is not left with empty evidence when immediate vector retrieval misses freshly collected documents.
- Hardened `scripts/validation_gate.py` quality and latency gates to delete stale fixed-path artifacts before each run and to trust only a newly written `summary.gate_passed=true` artifact.
- Increased API smoke timeout to 1500 seconds because the local Ollama API smoke can legitimately exceed 720 seconds on this workstation.
- Added `FINGPT_VALIDATION_FAST_INFERENCE=1` for the API smoke child only. This keeps normal production inference at 300 seconds, but caps validation API inference at 60 seconds and falls back to deterministic grounded output instead of letting release gates stall on local Ollama.
- Added `extra_env` support to `scripts/validation_gate.py::run_command()` so validation-only runtime controls are explicit and testable.
- Added regression tests for citation fallback, current-run retrieval backfill, and artifact-backed gate handling.

Final verification results:

- `python -m py_compile pipelines\analyze\thesis_builder.py pipelines\orchestration\research_pipeline.py scripts\validation_gate.py` -> passed.
- `python -m pytest tests\test_validation_gate.py -q` -> 12 passed.
- `python -m py_compile pipelines\orchestration\research_pipeline.py scripts\validation_gate.py tests\test_validation_gate.py` -> passed.
- `python -m pytest tests\test_validation_gate.py tests\test_research_pipeline_fallback.py -q` -> 13 passed.
- `python -m pytest tests\test_collection_reliability.py tests\test_thesis_builder.py tests\test_research_pipeline_fallback.py -q` -> 23 passed.
- `python scripts\validation_gate.py --release-candidate` clean wrapper run -> exit code 0.
- Release-candidate artifact: `data\outputs\validation_20260501T225919Z.json`; restored to `data\outputs\validation_latest.json` after a duplicate weaker default gate overwrote latest.
- Automated release-candidate phases passed: runtime compatibility, code gate, model baseline, provider compatibility, OpenBB agent contract, UI contract, infrastructure, CLI smoke, API smoke, quality gate, and topic latency profile.
- Code gate inside release candidate: `283 passed, 3 subtests passed`; `node --check app\web\app.js` passed.
- API smoke artifact: `data\outputs\validation_api_smoke_20260501T221718Z.json`; health, preflight, analyze, universal, compare, stream, export, runs, and watchlist checks passed.
- Quality review artifact: `reports\quality_review_results.json`; 19 cases, 17 success, 2 partial, 0 gate failures, `gate_passed=true`.
- Topic latency artifact: `reports\topic_latency_profile.json`; 6 topic cases, 4 success, 2 partial, 0 gate failures, `gate_passed=true`, final result samples 7.15-13.17 seconds, deep-pass skip ratio 1.0.

Current automation verification on 2026-05-02 10:36 KST:

- `python -m py_compile core\schemas\response.py core\schemas\topic.py core\utils\query_planner.py core\utils\evidence_quality.py core\utils\numeric_grounding.py core\utils\confidence_calibration.py core\utils\decision_support.py core\utils\validation_metrics.py pipelines\orchestration\research_pipeline.py pipelines\orchestration\topic_pipeline.py pipelines\analyze\report_builder.py pipelines\analyze\topic_report_builder.py pipelines\analyze\thesis_builder.py scripts\validation_gate.py quality_review.py app\api\server.py` -> passed.
- `node --check app\web\app.js` -> passed.
- `python -m pytest tests\test_query_planner.py tests\test_evidence_quality.py tests\test_numeric_grounding.py tests\test_confidence_calibration.py tests\test_decision_support_schema.py tests\test_validation_metrics.py tests\test_report_builder.py tests\test_topic_report_builder.py tests\test_research_pipeline_fallback.py tests\test_api_routing_contract.py tests\test_validation_gate.py tests\test_thesis_builder.py -q` -> 62 passed.
- `python -m pytest tests -q` -> 283 passed, 3 subtests passed.
- `python -m core.preflight` -> passed; Qdrant, OpenBB packages, yfinance, SEC, FRED, Ollama service, and `qwen2.5:7b` were operational.
- `python scripts\validation_gate.py --release-candidate` -> exit code 0 after 2012 seconds; wrote a fresh passing release-candidate artifact.
- Release-candidate artifact: `data\outputs\validation_20260502T013627Z.json`; mirrored to `data\outputs\validation_latest.json`.
- Automated release-candidate phases passed: runtime compatibility, code gate, model baseline, provider compatibility, OpenBB agent contract, UI contract, infrastructure, CLI smoke, API smoke, quality gate, and topic latency profile.
- Code gate inside release candidate: `283 passed, 3 subtests passed`; `node --check app\web\app.js` passed.
- API smoke artifact: `data\outputs\validation_api_smoke_20260502T010738Z.json`; health, preflight, analyze, universal, compare, stream, export, runs, and watchlist checks passed.
- Quality review artifact: `reports\quality_review_results.json`; 19 cases, 17 success, 2 partial, 0 gate failures, `gate_passed=true`.
- Topic latency artifact: `reports\topic_latency_profile.json`; 6 topic cases, 4 success, 2 partial, 0 gate failures, `gate_passed=true`, final result samples 7.10-11.03 seconds, deep-pass skip ratio 1.0.
- Non-blocking provider note: OpenBB company-news compatibility still reports an optional runtime warning, but `OPENBB_NEWS_ENABLED=false` keeps the default path on direct Yahoo/SEC/Google providers and the provider gate passed.

Current automation verification on 2026-05-02 12:43 KST:

- Checklist scan for unfinished status markers, unchecked boxes, and placeholder task tokens -> no unfinished markers found.
- `python -m py_compile core\schemas\response.py core\schemas\topic.py core\utils\query_planner.py core\utils\evidence_quality.py core\utils\numeric_grounding.py core\utils\confidence_calibration.py core\utils\decision_support.py core\utils\validation_metrics.py pipelines\orchestration\research_pipeline.py pipelines\orchestration\topic_pipeline.py pipelines\analyze\report_builder.py pipelines\analyze\topic_report_builder.py pipelines\analyze\thesis_builder.py scripts\validation_gate.py quality_review.py app\api\server.py` -> passed.
- `node --check app\web\app.js` -> passed.
- `python scripts\check_ui_contract.py` -> passed; required UI markers were present.
- `python -m pytest tests -q` -> 283 passed, 3 subtests passed.
- `python -m core.preflight` -> passed; Qdrant hybrid collection, OpenBB packages, yfinance, SEC, FRED, Ollama service, and `qwen2.5:7b` were operational.
- `python scripts\validation_gate.py --release-candidate` -> completed with `automated_passed=true`, `blocking_reason=null`, 12 validation phases, and 0 failed phases.
- Release-candidate artifact: `data\outputs\validation_20260502T034353Z.json`; mirrored to `data\outputs\validation_latest.json`.
- Automated release-candidate phases passed: runtime compatibility, code gate, model baseline, provider compatibility, OpenBB agent contract, UI contract, infrastructure, CLI smoke, API smoke, quality gate, and topic latency profile.
- API smoke artifact: `data\outputs\validation_api_smoke_20260502T030818Z.json`; status `passed`, 10 checks, 0 failed.
- Quality review artifact: `reports\quality_review_results.json`; 19 cases, 17 success, 2 partial, 0 gate failures, `gate_passed=true`.
- Topic latency artifact: `reports\topic_latency_profile.json`; 6 topic cases, 4 success, 2 partial, 0 gate failures, `gate_passed=true`, final result samples 6.88-15.63 seconds, deep-pass skip ratio 1.0.
- Release-candidate stdout log: `scratch\automation_logs\validation_gate_release_candidate_20260502T120428.out.log`; stderr log was empty.

Current automation verification on 2026-05-02 13:47 KST:

- Checklist scan for unfinished status markers, unchecked boxes, and placeholder task tokens -> no unfinished markers found.
- `python -m py_compile core\schemas\response.py core\schemas\topic.py core\utils\query_planner.py core\utils\evidence_quality.py core\utils\numeric_grounding.py core\utils\confidence_calibration.py core\utils\decision_support.py core\utils\validation_metrics.py pipelines\orchestration\research_pipeline.py pipelines\orchestration\topic_pipeline.py pipelines\analyze\report_builder.py pipelines\analyze\topic_report_builder.py pipelines\analyze\thesis_builder.py scripts\validation_gate.py quality_review.py app\api\server.py` -> passed.
- `node --check app\web\app.js` -> passed.
- `python scripts\check_ui_contract.py` -> passed; required UI markers were present.
- `python -m pytest tests -q` -> 283 passed, 3 subtests passed.
- `python -m core.preflight` -> passed; Qdrant hybrid collection, OpenBB packages, yfinance, SEC, FRED, Ollama service, and `qwen2.5:7b` were operational.
- `python scripts\validation_gate.py --release-candidate` -> completed with `automated_passed=true`, `blocking_reason=null`, 12 validation phases, and 0 failed automated phases.
- Release-candidate artifact: `data\outputs\validation_20260502T044727Z.json`; mirrored to `data\outputs\validation_latest.json`.
- Automated release-candidate phases passed: runtime compatibility, code gate, model baseline, provider compatibility, OpenBB agent contract, UI contract, infrastructure, CLI smoke, API smoke, quality gate, and topic latency profile.
- API smoke artifact: `data\outputs\validation_api_smoke_20260502T041034Z.json`; status `passed`, 10 checks, 0 failed. Non-blocking provider note: the API-smoke child observed one transient FRED 502 warning during its internal preflight, while the standalone preflight before the release gate passed FRED and the final API smoke gate remained passed.
- Quality review artifact: `reports\quality_review_results.json`; 19 cases, 17 success, 2 partial, 0 gate failures, `gate_passed=true`.
- Topic latency artifact: `reports\topic_latency_profile.json`; 6 topic cases, 4 success, 2 partial, 0 gate failures, `gate_passed=true`, final result samples 6.93-12.63 seconds, deep-pass skip ratio 1.0.
- Release-candidate stdout log: `scratch\automation_logs\validation_gate_release_candidate_20260502T130611.out.log`; stderr log was empty.

Current automation verification on 2026-05-02 14:49 KST:

- Checklist scan for unfinished status markers, unchecked boxes, and placeholder task tokens -> no unfinished markers found.
- `python -m py_compile core\schemas\response.py core\schemas\topic.py core\utils\query_planner.py core\utils\evidence_quality.py core\utils\numeric_grounding.py core\utils\confidence_calibration.py core\utils\decision_support.py core\utils\validation_metrics.py pipelines\orchestration\research_pipeline.py pipelines\orchestration\topic_pipeline.py pipelines\analyze\report_builder.py pipelines\analyze\topic_report_builder.py pipelines\analyze\thesis_builder.py scripts\validation_gate.py quality_review.py app\api\server.py` -> passed.
- `node --check app\web\app.js` -> passed.
- `python scripts\check_ui_contract.py` -> passed; required UI markers were present.
- `python -m pytest tests -q` -> 283 passed, 3 subtests passed.
- `python -m core.preflight` -> passed; Qdrant hybrid collection, OpenBB packages, yfinance, SEC, FRED, Ollama service, and `qwen2.5:7b` were operational.
- `python scripts\validation_gate.py --release-candidate` -> completed with `automated_passed=true`, `blocking_reason=null`, 11 automated phases passed, and the former manual browser placeholder still present before the browser gate automation upgrade.
- Release-candidate artifact: `data\outputs\validation_20260502T054938Z.json`; mirrored to `data\outputs\validation_latest.json`.
- Automated release-candidate phases passed: runtime compatibility, code gate, model baseline, provider compatibility, OpenBB agent contract, UI contract, infrastructure, CLI smoke, API smoke, quality gate, and topic latency profile.
- Code gate inside release candidate: `283 passed, 3 subtests passed`; `node --check app\web\app.js` passed.
- API smoke artifact: `data\outputs\validation_api_smoke_20260502T051231Z.json`; status `passed`; health, preflight, analyze, universal, compare, stream, outputs, exports, runs, and watchlist checks passed.
- Quality review artifact: `reports\quality_review_results.json`; 19 cases, 17 success, 2 partial, 0 gate failures, `gate_passed=true`.
- Topic latency artifact: `reports\topic_latency_profile.json`; 6 topic cases, 4 success, 2 partial, 0 gate failures, `gate_passed=true`, final result samples 6.60-9.03 seconds, deep-pass skip ratio 1.0.
- Non-blocking provider note: standalone preflight passed FRED before the release gate; the topic-latency child later observed one FRED rate-limit warning, but fallback inputs were available and the final topic latency gate passed.

Current automation verification on 2026-05-02 15:46 KST:

- Replaced the release-candidate manual browser placeholder with automated `browser_ui_gate` validation in `scripts\validation_gate.py`.
- Added Playwright to `requirements-dev.txt`; installed Playwright and Chromium with `python -m pip install -r requirements-dev.txt` and `python -m playwright install chromium`.
- `python -m py_compile scripts\validation_gate.py tests\test_validation_gate.py` -> passed.
- `python -m pytest tests\test_validation_gate.py -q` -> 15 passed.
- Standalone `run_browser_ui_gate(timeout_s=180)` -> passed; headless Chromium opened `/ui/`, loaded the latest run, checked home/dashboard anchors, compare/watchlist controls, all eight result tabs, decision metrics, evidence, diagnostics, report, raw JSON, export menu, and sanitized partial/error banner behavior.
- Standalone browser screenshot: `reports\browser_ui\browser_ui_success_20260502T060943Z.png`.
- `python scripts\check_ui_contract.py` -> passed; required UI markers were present.
- `python -m pytest tests -q` -> 286 passed, 3 subtests passed.
- `python scripts\validation_gate.py --release-candidate` -> completed with `automated_passed=true`, `blocking_reason=null`, and 12 automated phases passed including `browser_ui_gate`.
- Release-candidate artifact: `data\outputs\validation_20260502T064643Z.json`; mirrored to `data\outputs\validation_latest.json`.
- Browser UI gate artifact evidence: `phases.browser_ui_gate.status=passed`, 33 checked interactions, screenshot `reports\browser_ui\browser_ui_success_20260502T061953Z.png`.
- Acceptance check: `data\outputs\validation_latest.json` contains no former manual browser placeholder fields; `reports\validation_latest.md` contains `Browser UI Gate` and no manual checklist section.
- Automated release-candidate phases passed: runtime compatibility, code gate, model baseline, provider compatibility, OpenBB agent contract, UI contract, infrastructure, CLI smoke, API smoke, browser UI gate, quality gate, and topic latency profile.
- No remaining manual browser-validation limitation remains in the release-candidate gate.
