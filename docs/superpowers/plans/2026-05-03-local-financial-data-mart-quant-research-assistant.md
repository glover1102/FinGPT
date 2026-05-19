# Local Financial Data Mart + Quant Research Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing local FinGPT RAG research assistant into a local financial data mart + quant analytics engine + LLM research assistant.

**Architecture:** Qdrant remains dedicated to document evidence retrieval. Structured prices, macro observations, data quality, backtest inputs, and portfolio analytics live in a separate structured store. The existing `collect -> ingest -> retrieve -> infer -> analyze -> report` path is preserved, with scheduled data updates and structured context added.

**Tech Stack:** Python 3.11, FastAPI, SQLite default, optional DuckDB path, pandas/yfinance/FRED/SEC/Google RSS, Qdrant, Ollama `qwen2.5:7b`, pytest, PowerShell Task Scheduler scripts.

---

## Phase 0. Baseline And Safety

- [x] Confirm initial `git status --short`.
- [x] Record baseline behavior: `python -m pytest tests/test_watchlist.py tests/test_portfolio_quant.py tests/test_topic_quant.py -q`.
- [x] Inspect baseline docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`.
- [x] Keep existing `data/runs.db` as research execution history only.
- [x] Add data mart settings to `.env.example` without breaking local single-user defaults.

## Phase 1. Structured Data Mart Foundation

- [x] Create `pipelines/data_mart/storage/schema.py` with `assets`, `prices_daily`, `macro_series`, `macro_observations`, `news_articles`, `filings`, `data_update_runs`, `provider_status`, `data_quality_checks`.
- [x] Create `pipelines/data_mart/storage/db.py` with SQLite connection, WAL mode, migration table, and idempotent `init_db()`.
- [x] Create `pipelines/data_mart/storage/repository.py` with upsert/query APIs and fixed primary keys for price and macro observations.
- [x] Add `DATA_MART_DB_PATH`, `DATA_MART_BACKEND`, and `DATA_MART_DUCKDB_PATH` to `core/config/settings.py`.
- [x] Add `tests/test_data_mart_schema.py` and `tests/test_data_mart_repository.py`.
- [x] Verify schema/repository tests.

## Phase 2. Watchlist-Based Daily Update

- [x] Create `config/watchlists/core_us.yaml` and `config/watchlists/core_kr.yaml`.
- [x] Create `pipelines/data_mart/providers/yfinance_provider.py`.
- [x] Create `pipelines/data_mart/providers/fred_provider.py`.
- [x] Create `pipelines/data_mart/jobs/update_prices_daily.py`, `update_macro_daily.py`, `update_news_daily.py`, and `quality_checks.py`.
- [x] Create `scripts/daily_update.py` with `--market`, `--watchlist`, `--start-date`, `--end-date`, `--dry-run`, `--retry-failed`, `--skip-news`, `--skip-macro`, and `--json`.
- [x] Persist update runs into `data_update_runs` and provider outcomes into `provider_status`.
- [x] Add tests for idempotency, duplicate prevention, failed-provider status, and stale macro detection.
- [x] Verify daily update and quality check tests.
- [x] Execute actual US/KR data updates against `data/research_mart.db`: US prices/FRED/news succeeded; KR prices succeeded and KR news completed with empty provider statuses.

## Phase 3. Structured Context Builder

- [x] Create `pipelines/data_mart/context/structured_context.py`.
- [x] Add structured context to `research_pipeline.py` and `topic_pipeline.py` without weakening `current_run_only` document retrieval.
- [x] Update prompts with explicit numeric evidence policy.
- [x] Extend `execution_meta.extras` with `structured_context`, `data_mart_freshness`, and `data_quality_summary`.
- [x] Add structured context tests.
- [x] Verify structured context, topic prompt, and report builder tests.

## Phase 4. Backtest, Factors, Risk, Portfolio

- [x] Create `pipelines/factors/` for momentum, volatility, drawdown, correlation, and rate sensitivity.
- [x] Create `pipelines/backtest/` for engine, metrics, buy-and-hold, moving-average, momentum ranking, and volatility targeting.
- [x] Create `pipelines/portfolio/` for equal weight, inverse volatility, risk parity-style baseline, and max-Sharpe baseline optimizer.
- [x] Keep `pipelines/analyze/portfolio_quant.py` and `/api/v1/research/portfolio/risk` backward compatible.
- [x] Add tests for no-lookahead behavior, weights summing to one, cost/slippage assumptions, and metric calculations.
- [x] Verify factor/backtest/portfolio tests.

## Phase 5. API And UI Decision Surfaces

- [x] Add `/api/v1/data/health`, `/api/v1/data/prices/{ticker}`, `/api/v1/backtest/run`, and `/api/v1/portfolio/optimize`.
- [x] Extend `app/web/app.js`, `index.html`, and `styles.css` with Data Health, Asset Detail, Backtest, and Portfolio decision surfaces while preserving the existing dashboard/watchlist/research console.
- [x] Show loading, empty, partial, stale, and failed states explicitly.
- [x] Keep Research Console backed by structured context plus Qdrant evidence.
- [x] Verify syntax, UI contract, relevant API tests, and browser/API smoke.

## Phase 6. Automation And Notifications

- [x] Create `scripts/run_daily_update.ps1` with venv selection, update command, report generation, retry handling, and exit code propagation.
- [x] Add optional Telegram notifier gated by `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- [x] Document Windows Task Scheduler schedules in `docs/RUNBOOK.md`.
- [x] Implement retry/fallback policy and scheduler status recording.
- [x] Update `docs/RUNBOOK.md` with data-mart recovery, scheduler behavior, stale-data interpretation, and manual rerun commands.

## Final Verification Gate

- [x] `python -m pytest tests -q`
- [x] `node --check app/web/app.js`
- [x] `python -m core.preflight`
- [x] `python quality_review.py --suite all` completed after validation timeout/CLI-exit hardening; 19 cases, 0 gate failures, `gate_passed=True`.
- [x] `python scripts/profile_topic_latency.py`
- [x] `powershell -ExecutionPolicy Bypass -File scripts/verify_production_path.ps1`
- [x] Browser/API smoke: dashboard, data health, asset detail, backtest, research console.
- [x] Release statement must distinguish verified, likely-but-unverified, and environment-blocked items.
