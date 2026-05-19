# FinGPT Topic / Non-Equity Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TLT, rates/bonds, sector/theme, FX, commodity, crypto, and tickerless macro queries should return decision-grade Korean output without surfacing recovered LLM JSON failures as user-facing errors.

**Architecture:** Treat topic/non-equity analysis as a first-class path, not a weaker variant of single-stock analysis. Split the fix into routing, evidence bucket policy, structured generation, deterministic synthesis, status/error taxonomy, UI presentation, and regression gates. Preserve public REST response schemas; put new diagnostics in `execution_meta.extras`.

**Tech Stack:** Python 3.11 runtime via `venv311`, FastAPI, Pydantic models in `core/schemas`, local Ollama `qwen2.5:7b`, topic pipeline in `pipelines/orchestration/topic_pipeline.py`, UI in `app/web/app.js`, tests via `pytest`, JS syntax check via `node --check`.

---

## Current Findings

The latest TLT run did not fail as a pipeline crash. It returned `status=partial` with a usable deterministic fallback memo, but the UI still exposed this as an error-like banner:

- `status`: `partial`
- `error_metadata`: `LLM 구조화 출력 실패: [Topic] JSON truncated or unclosed. | Missing evidence buckets: latest catalyst`
- `producing_model`: `local-deterministic-fallback`
- `fast_gate.ok`: `true`
- `final_gate.ok`: `true`
- `evidence_bucket_counts`: `macro=9`, `asset_specific=6`, `market_structure=2`, `latest_catalyst=0`
- `deep_pass_reason`: `missing_evidence_buckets`
- `deep_pass_skipped`: `true`

Root cause is not a single bug. It is a path-quality mismatch:

1. `pipelines/router/query_router.py` classifies explicit tickers first, so TLT can become `single_ticker` before rates/bonds intent is checked.
2. `pipelines/infer/topic_prompt.py` still asks a small local model to produce large structured JSON. When it truncates, fallback output is often good, but the original truncation remains in `error_metadata`.
3. `pipelines/orchestration/topic_pipeline.py` treats missing `latest_catalyst` as partial even when rates/bonds evidence is otherwise sufficient.
4. `app/web/app.js` shows any final `error_metadata` as a prominent banner, even when `final_gate.ok=true` and the issue is a recovered warning.
5. Current tests cover structural fields but not the exact user-facing contract: "TLT/rates topic must not look failed when fallback produced a complete memo."

---

## File Structure

- Modify: `F:\LLM\FinGPT\pipelines\router\query_router.py`
  - Responsibility: classify asset intent before explicit ticker mode when tickers are non-equity proxies such as `TLT`, `GLD`, `USO`, `EURUSD=X`, `BTC-USD`, `QQQ`, `SOXX`.

- Modify: `F:\LLM\FinGPT\pipelines\infer\topic_prompt.py`
  - Responsibility: make topic JSON generation smaller, repairable, and asset-class aware; keep local deterministic fields authoritative for citations, metrics, related tickers, and uncertainty.

- Modify: `F:\LLM\FinGPT\pipelines\orchestration\topic_pipeline.py`
  - Responsibility: separate blocking failures from recovered warnings; downgrade non-blocking missing buckets by asset class; never set user-visible `error_metadata` for recovered truncation when final output passes quality gate.

- Modify: `F:\LLM\FinGPT\core\utils\validation_metrics.py`
  - Responsibility: expose topic gate details that distinguish `blocking_failure`, `warning_only`, and `ok`.

- Modify: `F:\LLM\FinGPT\pipelines\collect\topic_collector.py`
  - Responsibility: record collection coverage reasons per bucket and normalize mojibake in collected titles/snippets where possible.

- Modify: `F:\LLM\FinGPT\app\web\app.js`
  - Responsibility: show `partial` with `final_gate.ok=true` as a warning/coverage note, not a pipeline error.

- Modify: `F:\LLM\FinGPT\quality_review.py`
  - Responsibility: add topic/non-equity regression cases and record recovered warnings separately from failures.

- Create: `F:\LLM\FinGPT\tests\test_topic_non_equity_stability.py`
  - Responsibility: focused contract tests for TLT, sector/theme, FX, commodity, crypto, and tickerless macro.

- Modify: `F:\LLM\FinGPT\tests\test_query_router.py`
  - Responsibility: ensure non-equity proxy tickers route to topic/sector_macro when the question intent is macro/asset-class analysis.

- Modify: `F:\LLM\FinGPT\tests\test_topic_pipeline.py`
  - Responsibility: ensure recovered JSON truncation does not become a user-facing failed state.

- Modify: `F:\LLM\FinGPT\tests\test_validation_metrics.py`
  - Responsibility: enforce asset-class-specific evidence bucket policy.

---

## Task 1: Reproduce And Freeze The Current Failure Contract

**Files:**
- Create: `F:\LLM\FinGPT\tests\test_topic_non_equity_stability.py`
- Modify: `F:\LLM\FinGPT\tests\test_topic_pipeline.py`

- [ ] **Step 1: Add a regression fixture for the latest TLT failure shape**

Create `tests/test_topic_non_equity_stability.py` with a payload that mirrors the observed run:

```python
from core.utils.validation_metrics import topic_final_gate


def test_tlt_recovered_fallback_is_quality_ok_even_with_missing_latest_catalyst():
    payload = {
        "mode": "concept",
        "theme": "TLT 금리와 채권 가격 매력도",
        "executive_summary": "TLT는 장기금리 하락에는 큰 가격 탄력성을 갖지만 인플레이션 재가속에는 취약합니다.",
        "core_thesis": "성장 둔화와 Fed 완화 전환 가능성이 커질수록 장기채 기대수익은 개선됩니다.",
        "asset_overview": [{"title": "TLT", "bullets": ["장기 미국 국채 ETF"], "conclusion": "금리 방향성이 핵심입니다."}],
        "macro_regime": [{"title": "성장/물가/Fed", "bullets": ["성장 둔화", "물가 둔화"], "conclusion": "완화 전환 기대가 있습니다."}],
        "rate_structure": [{"title": "장기금리", "bullets": ["실질금리가 높습니다."], "conclusion": "캐리와 듀레이션을 함께 봐야 합니다."}],
        "investment_judgment": [{"title": "판단", "bullets": ["분할 접근"], "conclusion": "중장기 조건부 매력입니다."}],
        "scenario_analysis": [
            {"scenario": "금리 하락", "probability": "중간", "expected_outcome": "장기금리 하락", "asset_implication": "TLT 상승", "decision_read": "분할 매수"},
            {"scenario": "연착륙", "probability": "중간", "expected_outcome": "금리 횡보", "asset_implication": "제한적 상승", "decision_read": "관망"},
            {"scenario": "인플레 재가속", "probability": "낮음", "expected_outcome": "금리 상승", "asset_implication": "TLT 하락", "decision_read": "비중 축소"},
        ],
        "execution_strategy": [
            {"strategy": "분할 매수", "trigger": "장기금리 안정", "rationale": "타이밍 위험 분산", "risk_control": "금리 재상승 시 중단"},
            {"strategy": "확인 후 진입", "trigger": "Fed 완화 확인", "rationale": "듀레이션 손실 제한", "risk_control": "손절 기준 설정"},
        ],
        "key_drivers": [{"text": "장기금리 하락 가능성", "direction": "supporting"} for _ in range(2)],
        "key_risks": [{"text": "인플레이션 재가속", "direction": "opposing"} for _ in range(2)],
        "key_metrics": [{"name": "10Y", "value": "4.30%", "context": "장기금리 앵커"} for _ in range(3)],
        "uncertainty": "latest catalyst 근거는 부족하지만 macro/asset/market structure 근거는 충분합니다.",
    }
    gate = topic_final_gate(payload, preferred_language="ko")
    assert gate["ok"] is True
```

- [ ] **Step 2: Run the new test and confirm baseline**

Run:

```powershell
python -m pytest tests\test_topic_non_equity_stability.py -q
```

Expected: PASS initially for quality gate. Later tasks will add status/error taxonomy tests that currently fail.

- [ ] **Step 3: Add a topic pipeline status test for recovered truncation**

In `tests/test_topic_pipeline.py`, add a test that constructs the final response metadata path or calls the helper introduced in Task 3:

```python
def test_recovered_topic_truncation_is_warning_not_user_error():
    from pipelines.orchestration.topic_pipeline import _final_topic_status

    status, error_metadata, warnings = _final_topic_status(
        current_status="success",
        final_gate={"ok": True},
        missing_buckets=["latest_catalyst"],
        asset_class="rates_bonds",
        recovered_errors=["[Topic] JSON truncated or unclosed."],
    )

    assert status == "success"
    assert error_metadata is None
    assert warnings == ["Recovered LLM structured-output error: [Topic] JSON truncated or unclosed.", "Missing optional evidence bucket: latest_catalyst"]
```

- [ ] **Step 4: Run the status test and confirm it fails before implementation**

Run:

```powershell
python -m pytest tests\test_topic_pipeline.py::test_recovered_topic_truncation_is_warning_not_user_error -q
```

Expected: FAIL because `_final_topic_status` does not exist yet.

---

## Task 2: Fix Routing For Non-Equity Proxy Tickers

**Files:**
- Modify: `F:\LLM\FinGPT\pipelines\router\query_router.py`
- Modify: `F:\LLM\FinGPT\tests\test_query_router.py`

- [ ] **Step 1: Add route tests for TLT and non-equity proxies**

Add tests:

```python
from pipelines.router.query_router import route_query


def test_tlt_with_rates_question_routes_to_sector_macro():
    routed = route_query("TLT 기준으로 금리 수준과 장기채 가격이 매력적인지 분석", hint_ticker="TLT")
    assert routed.mode == "sector_macro"
    assert "TLT" in routed.tickers


def test_non_equity_proxy_questions_route_to_topic_modes():
    cases = [
        ("GLD와 실질금리 관점에서 금 가격 매력도 분석", "GLD"),
        ("EURUSD=X 환율을 금리차와 달러 유동성으로 분석", "EURUSD=X"),
        ("BTC-USD를 유동성과 ETF flow 관점에서 분석", "BTC-USD"),
    ]
    for question, ticker in cases:
        routed = route_query(question, hint_ticker=ticker)
        assert routed.mode == "sector_macro"
        assert ticker in routed.tickers
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest tests\test_query_router.py::test_tlt_with_rates_question_routes_to_sector_macro tests\test_query_router.py::test_non_equity_proxy_questions_route_to_topic_modes -q
```

Expected: FAIL for TLT because explicit ticker currently wins before rates intent.

- [ ] **Step 3: Implement intent-first override for non-equity proxies**

In `query_router.py`, add helper near `_explicit_ticker_route`:

```python
_NON_EQUITY_PROXY_TICKERS = {"TLT", "IEF", "SHY", "AGG", "LQD", "HYG", "GLD", "USO", "EURUSD=X", "BTC-USD"}
_RATES_INTENT_TERMS = ["bond", "treasury", "yield curve", "real yield", "term premium", "duration", "국채", "채권", "금리", "실질금리", "장단기"]
_FX_INTENT_TERMS = ["eurusd", "eur/usd", "fx", "dollar", "환율", "달러", "금리차"]
_CRYPTO_INTENT_TERMS = ["bitcoin", "btc", "crypto", "비트코인", "암호화폐", "etf flow", "유동성"]
_COMMODITY_INTENT_TERMS = ["gold", "oil", "commodity", "원자재", "유가", "금", "실질금리"]


def _non_equity_intent_route(question: str, hint_ticker: str | None = None) -> RoutedQuery | None:
    q = question or ""
    q_lower = q.lower()
    found = _merge_tickers(_extract_known_tickers(q), _clean_tickers([hint_ticker]) if hint_ticker else [])
    if not any(t in _NON_EQUITY_PROXY_TICKERS for t in found):
        return None
    horizon = _infer_horizon(q)
    if "TLT" in found or _contains_any(q_lower, _RATES_INTENT_TERMS):
        return RoutedQuery(mode="sector_macro", tickers=_merge_tickers(["TLT"], found), theme=q[:120], horizon=horizon, reasoning="non-equity rates/bonds intent")
    if any(t in found for t in ["EURUSD=X"]) or _contains_any(q_lower, _FX_INTENT_TERMS):
        return RoutedQuery(mode="sector_macro", tickers=_merge_tickers(["EURUSD=X"], found), theme=q[:120], horizon=horizon, reasoning="non-equity fx intent")
    if any(t in found for t in ["BTC-USD"]) or _contains_any(q_lower, _CRYPTO_INTENT_TERMS):
        return RoutedQuery(mode="sector_macro", tickers=_merge_tickers(["BTC-USD"], found), theme=q[:120], horizon=horizon, reasoning="non-equity crypto intent")
    if any(t in found for t in ["GLD", "USO"]) or _contains_any(q_lower, _COMMODITY_INTENT_TERMS):
        return RoutedQuery(mode="sector_macro", tickers=_merge_tickers(["GLD", "USO"], found), theme=q[:120], horizon=horizon, reasoning="non-equity commodity intent")
    return None
```

Then call it before `_explicit_ticker_route` in `route_query()`:

```python
    non_equity = _non_equity_intent_route(question, hint_ticker)
    if non_equity is not None:
        return non_equity
```

- [ ] **Step 4: Re-run route tests**

Run:

```powershell
python -m pytest tests\test_query_router.py -q
```

Expected: PASS.

---

## Task 3: Separate Blocking Failures From Recovered Warnings

**Files:**
- Modify: `F:\LLM\FinGPT\pipelines\orchestration\topic_pipeline.py`
- Modify: `F:\LLM\FinGPT\tests\test_topic_pipeline.py`

- [ ] **Step 1: Add status taxonomy helper**

Add near existing fallback helpers:

```python
_OPTIONAL_BUCKETS_BY_ASSET_CLASS = {
    "rates_bonds": {"latest_catalyst"},
    "fx": {"latest_catalyst"},
    "commodity": set(),
    "crypto": set(),
    "sector_theme": set(),
    "equity_index": {"latest_catalyst"},
}


def _final_topic_status(
    *,
    current_status: str,
    final_gate: dict,
    missing_buckets: list[str],
    asset_class: str,
    recovered_errors: list[str],
) -> tuple[str, str | None, list[str]]:
    warnings: list[str] = []
    optional = _OPTIONAL_BUCKETS_BY_ASSET_CLASS.get(asset_class, set())
    blocking_missing = [b for b in missing_buckets if b not in optional]
    for err in recovered_errors:
        if err:
            warnings.append(f"Recovered LLM structured-output error: {err}")
    for bucket in missing_buckets:
        level = "optional" if bucket in optional else "required"
        warnings.append(f"Missing {level} evidence bucket: {bucket}")
    if current_status == "failed":
        return "failed", "Topic pipeline failed before recoverable synthesis.", warnings
    if not final_gate.get("ok"):
        return "partial", "최종 topic 품질 기준을 충족하지 못했습니다.", warnings
    if blocking_missing:
        return "partial", "Missing required evidence buckets: " + ", ".join(blocking_missing), warnings
    return "success", None, warnings
```

- [ ] **Step 2: Wire helper into final response creation**

Replace the current final status block around `missing_buckets` with:

```python
recovered_errors = []
if fast_meta.get("fallback_reason"):
    recovered_errors.append(str(fast_meta["fallback_reason"]))
if final_meta.get("fallback_reason") and final_meta.get("fallback_reason") not in recovered_errors:
    recovered_errors.append(str(final_meta["fallback_reason"]))

final_status, final_error_metadata, final_warnings = _final_topic_status(
    current_status=status,
    final_gate=final_gate,
    missing_buckets=missing_buckets,
    asset_class=str(final_meta.get("asset_class") or fast_meta.get("asset_class") or "sector_theme"),
    recovered_errors=recovered_errors,
)
```

Then pass `status=final_status` and `error_metadata=final_error_metadata` into `_response_from_payload()`.

Add warnings to `ExecutionMeta.extras`:

```python
"warnings": final_warnings,
"recovered_errors": recovered_errors,
```

- [ ] **Step 3: Re-run status test**

Run:

```powershell
python -m pytest tests\test_topic_pipeline.py::test_recovered_topic_truncation_is_warning_not_user_error -q
```

Expected: PASS.

---

## Task 4: Make Evidence Bucket Policy Asset-Class Aware

**Files:**
- Modify: `F:\LLM\FinGPT\pipelines\infer\topic_prompt.py`
- Modify: `F:\LLM\FinGPT\core\utils\validation_metrics.py`
- Modify: `F:\LLM\FinGPT\tests\test_validation_metrics.py`

- [ ] **Step 1: Add bucket-policy tests**

Add to `tests/test_validation_metrics.py`:

```python
from core.utils.validation_metrics import evidence_bucket_policy


def test_rates_bonds_latest_catalyst_is_optional_when_core_buckets_exist():
    result = evidence_bucket_policy(
        asset_class="rates_bonds",
        bucket_counts={"macro": 9, "asset_specific": 6, "market_structure": 2, "latest_catalyst": 0},
    )
    assert result["blocking_missing"] == []
    assert result["warning_missing"] == ["latest_catalyst"]


def test_sector_theme_latest_catalyst_is_required():
    result = evidence_bucket_policy(
        asset_class="sector_theme",
        bucket_counts={"macro": 1, "asset_specific": 1, "market_structure": 1, "latest_catalyst": 0},
    )
    assert result["blocking_missing"] == ["latest_catalyst"]
```

- [ ] **Step 2: Implement policy helper**

In `validation_metrics.py`, add:

```python
_REQUIRED_BUCKETS_BY_ASSET_CLASS = {
    "rates_bonds": {"macro", "asset_specific", "market_structure"},
    "equity_index": {"macro", "asset_specific", "market_structure"},
    "commodity": {"macro", "asset_specific", "market_structure", "latest_catalyst"},
    "fx": {"macro", "asset_specific", "market_structure"},
    "crypto": {"macro", "asset_specific", "market_structure", "latest_catalyst"},
    "sector_theme": {"macro", "asset_specific", "market_structure", "latest_catalyst"},
}


def evidence_bucket_policy(asset_class: str, bucket_counts: dict[str, int]) -> dict[str, list[str]]:
    required = _REQUIRED_BUCKETS_BY_ASSET_CLASS.get(asset_class, _REQUIRED_BUCKETS_BY_ASSET_CLASS["sector_theme"])
    all_buckets = {"macro", "asset_specific", "market_structure", "latest_catalyst"}
    missing = [bucket for bucket in sorted(all_buckets) if int(bucket_counts.get(bucket, 0) or 0) <= 0]
    blocking = [bucket for bucket in missing if bucket in required]
    warning = [bucket for bucket in missing if bucket not in required]
    return {"blocking_missing": blocking, "warning_missing": warning}
```

- [ ] **Step 3: Use bucket policy in topic pipeline**

In `topic_pipeline.py`, where `missing_buckets` is built, replace raw missing-bucket handling with `evidence_bucket_policy(asset_class, evidence_bucket_counts)` and store:

```python
"missing_evidence_buckets": bucket_policy["blocking_missing"],
"warning_evidence_buckets": bucket_policy["warning_missing"],
```

- [ ] **Step 4: Re-run validation tests**

Run:

```powershell
python -m pytest tests\test_validation_metrics.py tests\test_topic_pipeline.py -q
```

Expected: PASS.

---

## Task 5: Reduce Topic JSON Truncation At The Source

**Files:**
- Modify: `F:\LLM\FinGPT\pipelines\infer\topic_prompt.py`
- Modify: `F:\LLM\FinGPT\tests\test_topic_prompt.py`

- [ ] **Step 1: Add prompt-budget test**

Add to `tests/test_topic_prompt.py`:

```python
def test_topic_fast_prompt_budget_keeps_schema_out_of_prompt():
    from pipelines.infer.topic_prompt import _build_topic_prompt

    prompt = _build_topic_prompt(
        question="TLT 금리 매력도 분석",
        theme="TLT",
        context=[],
        fields=["executive_summary", "core_thesis", "scenario_analysis"],
        phase="fast",
        expected_language="ko",
    )

    assert "JSON Schema" not in prompt
    assert len(prompt) <= 6000
```

If `_build_topic_prompt` requires more arguments, add a small factory fixture rather than weakening the assertion.

- [ ] **Step 2: Make fast prompt deterministic and smaller**

In `_build_topic_prompt()`:

1. Do not include full schema text in prompt when Ollama `format` already receives schema.
2. Limit fast evidence to one compact item per bucket.
3. Limit each evidence snippet to 500 characters.
4. For fast phase, request only the fields needed for the public schema, but instruct local code to fill deterministic fields.

Required prompt rules:

```text
Return exactly one JSON object.
Do not include markdown fences.
Use concise Korean.
Do not repeat evidence text.
Keep each bullet under 120 Korean characters.
If a field is uncertain, write a short uncertainty item instead of expanding prose.
```

- [ ] **Step 3: Make JSON repair bounded**

In `_build_json_repair_prompt()`, cap broken output:

```python
broken = _shorten(_clean_json_candidate(raw_text), 2500)
```

and make repair fields explicit:

```python
"Repair only syntax and missing closing brackets. Do not expand the memo."
```

- [ ] **Step 4: Re-run prompt tests**

Run:

```powershell
python -m pytest tests\test_topic_prompt.py -q
```

Expected: PASS.

---

## Task 6: Promote Deterministic Synthesis From Emergency Fallback To Normal Safety Net

**Files:**
- Modify: `F:\LLM\FinGPT\pipelines\orchestration\topic_pipeline.py`
- Modify: `F:\LLM\FinGPT\pipelines\infer\topic_prompt.py`
- Modify: `F:\LLM\FinGPT\tests\test_topic_pipeline.py`

- [ ] **Step 1: Add deterministic synthesis contract test**

Add:

```python
def test_topic_deterministic_fallback_has_citations_and_no_failed_status():
    from pipelines.orchestration.topic_pipeline import _build_deterministic_topic_payload
    from pipelines.infer.topic_prompt import build_topic_plan, build_evidence_pack

    context = make_tlt_context_items()  # use existing test helper or create 4 RetrievalItem objects
    plan = build_topic_plan("TLT 금리 매력도", "TLT", ["TLT"], context)
    pack = build_evidence_pack("TLT 금리 매력도", "TLT", context, ["TLT"], plan)
    payload, meta = _build_deterministic_topic_payload(
        question="TLT 금리 매력도",
        theme="TLT",
        related_tickers=["TLT"],
        context=context,
        topic_plan=plan,
        evidence_pack=pack,
        error_metadata="[Topic] JSON truncated or unclosed.",
        language="ko",
    )

    assert payload["executive_summary"]
    assert len(payload["scenario_analysis"]) >= 3
    assert len(payload["execution_strategy"]) >= 2
    assert payload["cited_doc_ids"]
    assert meta["producing_model"] == "local-deterministic-fallback"
```

- [ ] **Step 2: Ensure fallback citations are populated**

In `_build_deterministic_topic_payload()`, guarantee:

```python
payload["cited_doc_ids"] = evidence_pack.cited_doc_ids[:6]
payload["citations"] = _citations_from_context(context, payload["cited_doc_ids"])
```

If citations are built later, ensure the final `TopicResponse.citations` receives them from `cited_doc_ids`.

- [ ] **Step 3: Change terminology in metadata**

Do not call deterministic output an error if it passed final gate. Store:

```python
"_meta": {
    "producing_model": "local-deterministic-synthesis",
    "recovered_from": "llm_structured_output",
}
```

Keep backward compatibility by accepting old value in tests if needed.

- [ ] **Step 4: Re-run pipeline tests**

Run:

```powershell
python -m pytest tests\test_topic_pipeline.py -q
```

Expected: PASS.

---

## Task 7: Fix UI Error Presentation For Partial / Warning-Only Topic Results

**Files:**
- Modify: `F:\LLM\FinGPT\app\web\app.js`
- Modify or create browser test if available: `F:\LLM\FinGPT\tests\test_sse_stream.py`

- [ ] **Step 1: Add display helper**

In `app/web/app.js`, add:

```javascript
function responseIssueLevel(data) {
  if (!data) return "none";
  if (data.status === "failed") return "error";
  const extras = data.execution_meta?.extras || {};
  if (extras.final_gate?.ok === true && Array.isArray(extras.warnings) && extras.warnings.length) return "warning";
  if (data.status === "partial" && data.error_metadata) return "warning";
  return "none";
}
```

- [ ] **Step 2: Replace error banner logic**

Replace the final-phase `error_metadata` block with:

```javascript
const issueLevel = responseIssueLevel(data);
if (isFastPhase) {
  els.errorBanner.textContent = data.error_metadata || "초기 판단입니다. 심화 분석을 계속 진행합니다.";
  els.errorBanner.classList.remove("hidden", "failed");
} else if (issueLevel === "error") {
  els.errorBanner.textContent = data.error_metadata || "파이프라인 오류입니다.";
  els.errorBanner.classList.remove("hidden");
  els.errorBanner.classList.add("failed");
} else if (issueLevel === "warning") {
  const warnings = data.execution_meta?.extras?.warnings || [];
  els.errorBanner.textContent = warnings.length ? warnings.join(" | ") : data.error_metadata;
  els.errorBanner.classList.remove("hidden", "failed");
} else {
  els.errorBanner.classList.add("hidden");
}
```

- [ ] **Step 3: Allow export for warning-only results**

Keep:

```javascript
setExportAvailability(!isFastPhase && !!state.lastResponse && data.status !== "failed");
```

Do not disable export for `partial` if final output exists.

- [ ] **Step 4: Run JS check**

Run:

```powershell
node --check app\web\app.js
```

Expected: no output, exit code 0.

---

## Task 8: Add Non-Equity Quality Review Cases

**Files:**
- Modify: `F:\LLM\FinGPT\quality_review.py`
- Modify: `F:\LLM\FinGPT\tests\test_quality_review.py`

- [ ] **Step 1: Add topic matrix**

Add cases:

```python
TOPIC_STABILITY_CASES = [
    {"theme": "TLT rates attractiveness", "question": "TLT 기준으로 지금 금리 수준과 장기채 가격 매력도를 분석", "expected_asset_class": "rates_bonds"},
    {"theme": "Gold real rates", "question": "GLD와 실질금리 관점에서 금 가격 매력도 분석", "expected_asset_class": "commodity"},
    {"theme": "EURUSD policy divergence", "question": "EURUSD를 금리차와 달러 유동성으로 분석", "expected_asset_class": "fx"},
    {"theme": "Bitcoin liquidity cycle", "question": "BTC-USD를 ETF flow와 달러 유동성으로 분석", "expected_asset_class": "crypto"},
    {"theme": "AI semiconductors", "question": "AI semiconductors 섹터 투자 매력도와 리스크 분석", "expected_asset_class": "sector_theme"},
    {"theme": "US rates macro", "question": "미국 금리와 인플레이션 환경이 위험자산에 미치는 영향 분석", "expected_asset_class": "rates_bonds"},
]
```

- [ ] **Step 2: Record warning-only separately from failures**

Quality JSON must include:

```python
"status_level": "ok" | "warning_only" | "failed",
"warning_count": len(extras.get("warnings") or []),
"blocking_error": response.error_metadata if response.status == "failed" else None,
```

- [ ] **Step 3: Add assertions**

For topic suite:

```python
assert item["status_level"] in {"ok", "warning_only"}
assert item["language_ok"] is True
assert item["decision_richness"]["ok"] is True
assert item["asset_class"] == expected_asset_class
```

- [ ] **Step 4: Run focused quality tests**

Run:

```powershell
python -m pytest tests\test_quality_review.py -q
```

Expected: PASS.

---

## Task 9: Add A Local Topic Stability Gate Script

**Files:**
- Create: `F:\LLM\FinGPT\scripts\validate_topic_stability.py`
- Modify: `F:\LLM\FinGPT\scripts\verify_production_path.ps1`

- [ ] **Step 1: Create validation script**

The script should run API or pipeline calls for the six topic cases and write:

```json
{
  "case": "TLT rates attractiveness",
  "status": "success",
  "status_level": "ok",
  "asset_class": "rates_bonds",
  "language_ok": true,
  "final_gate_ok": true,
  "warning_count": 1,
  "blocking_error": null,
  "latency_s": 58.1
}
```

- [ ] **Step 2: Hard-fail only on blocking issues**

Exit code 1 only when:

- `status == "failed"`
- `final_gate.ok != true`
- Korean dominance fails
- decision richness fails
- required evidence bucket missing for that asset class

Do not fail for optional missing `latest_catalyst` on rates/bonds.

- [ ] **Step 3: Wire into production verifier**

In `scripts/verify_production_path.ps1`, add optional switch:

```powershell
[switch]$RunTopicStability
```

and when set:

```powershell
python scripts/validate_topic_stability.py --output data/outputs/validation_topic_stability.json
if ($LASTEXITCODE -ne 0) { throw "Topic stability gate failed" }
```

- [ ] **Step 4: Run gate**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1 -RunTopicStability
```

Expected: topic stability cases are `ok` or `warning_only`, no `failed`.

---

## Task 10: Final Verification Matrix

**Files:**
- No new files unless failures require fixes.

- [ ] **Step 1: Python 3.11 import/runtime check**

Run:

```powershell
venv311\Scripts\python.exe -m py_compile pipelines\router\query_router.py pipelines\infer\topic_prompt.py pipelines\orchestration\topic_pipeline.py core\utils\validation_metrics.py app\api\server.py
```

Expected: no output, exit code 0.

- [ ] **Step 2: Unit tests**

Run:

```powershell
python -m pytest tests\test_query_router.py tests\test_topic_prompt.py tests\test_topic_pipeline.py tests\test_validation_metrics.py tests\test_topic_non_equity_stability.py -q
```

Expected: all pass.

- [ ] **Step 3: Full tests**

Run:

```powershell
python -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 4: JS syntax**

Run:

```powershell
node --check app\web\app.js
```

Expected: no output, exit code 0.

- [ ] **Step 5: Server health**

Run:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8000/api/v1/health -TimeoutSec 10
```

Expected: `{"status":"ok","version":"1.1.0"}`.

- [ ] **Step 6: Manual UI smoke**

In `http://127.0.0.1:8000/ui/`, run:

1. `TLT` + "거시경제를 다방면으로 분석했을 때 지금 금리 수준과 채권 가격이 매력적인지 분석"
2. `AI semiconductors` topic
3. `EURUSD=X` FX macro
4. `BTC-USD` liquidity/ETF flow

Expected:

- No `FAILED` badge unless actual pipeline failure.
- Recovered JSON truncation appears, at most, as warning diagnostics, not blocking error copy.
- Summary and Report tabs contain decision-grade Korean memo.
- Evidence/Diagnostics shows bucket coverage and optional/required distinction.
- Export buttons enabled for `success` and warning-only `partial`, disabled only for `failed`.

---

## Acceptance Criteria

- TLT rates/bonds query returns `success` when final gate passes and only optional `latest_catalyst` is missing.
- If the LLM JSON truncates but deterministic synthesis passes final gate, UI does not display it as a red/pipeline error.
- Non-equity proxy tickers with macro/asset-class intent route to topic path, not single-equity path.
- Sector/theme/macro queries have asset-class-specific evidence bucket rules.
- `error_metadata` is reserved for blocking errors; recovered issues move to `execution_meta.extras.warnings`.
- Full test suite remains green.
- Server runtime is validated with Python 3.11 because that is what the UI server uses.

---

## Rollback Plan

If topic routing changes create regressions:

1. Revert only `query_router.py` and its tests.
2. Keep status/error taxonomy and UI warning handling because they are independently beneficial.
3. Run `python -m pytest tests\test_query_router.py tests\test_topic_pipeline.py -q`.

If deterministic synthesis produces poor quality:

1. Keep LLM generation changes.
2. Mark deterministic synthesis status as `partial` but still move recovered truncation to warnings.
3. Tighten `topic_final_gate()` minimums rather than exposing raw parser failures to users.

---

## Implementation Order

1. Task 1: freeze the failure contract.
2. Task 2: fix routing.
3. Task 4: asset-class evidence policy.
4. Task 3: status/error taxonomy.
5. Task 6: deterministic synthesis as safety net.
6. Task 5: reduce JSON truncation.
7. Task 7: UI warning presentation.
8. Task 8: quality review cases.
9. Task 9: local stability gate.
10. Task 10: final verification.

