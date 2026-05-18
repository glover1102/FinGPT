# Macro Platform Advancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `http://127.0.0.1:8002/ui/#macro` from a working Macro dashboard into a faster, more operable, scenario-aware macro decision workbench while preserving advisory-only boundaries.

**Architecture:** Keep the current FastAPI + static `app/web` shape. Add a cached Macro dashboard aggregate endpoint for fast initial render, keep detailed panels behind explicit drilldowns, add deterministic scenario analysis under `pipelines/macro`, and expose refresh/provider state as operational evidence rather than hidden background work.

**Tech Stack:** FastAPI, Pydantic, static HTML/CSS/JavaScript, SQLite data mart, existing `pipelines/macro/*`, existing `scripts/check_ui_contract.py`, pytest, Playwright/browser smoke.

---

## Current Baseline

- Live UI checked at `http://host.docker.internal:8002/ui/#macro` because MCP Docker cannot reach host `127.0.0.1` directly.
- Initial snapshot showed the Macro tab and layout immediately, while many panels stayed in "매크로 데이터를 불러오는 중입니다" until the backend calls completed.
- Console warnings/errors: none in the browser snapshot.
- API timing from the same workstation:
  - `GET /api/v1/macro/health`: `200`, about `0.023s`, `registry_series=74`, `data_mart_available=true`.
  - `GET /api/v1/macro/series`: `200`, about `0.009s`, `count=74`.
  - `GET /api/v1/macro/overview?compact=true&observation_limit=20`: `200`, about `1.42s`.
  - `GET /api/v1/macro/data-quality`: `200`, about `3.29s`, current quality `stale` because `DTWEXBGS` is 8 days old.
  - `GET /api/v1/macro/refresh/status`: `200`, about `2.00s`, scheduler running with `macro_platform_data=true`.
- Current UI load path in `app/web/app.js` calls `overview` first, then starts many category/data-quality/refresh requests. This makes the page appear stalled when one slower endpoint blocks final rendering.

## File Structure

- Modify `docs/MACRO_IMPLEMENTATION_CHECKLIST.md`: keep this as the source-of-truth status board for Macro work.
- Modify `core/schemas/macro.py`: add explicit dashboard, scenario, refresh, and provider-health schemas.
- Modify `app/api/routers/macro.py`: add new read endpoints without breaking the existing endpoint contract.
- Modify `pipelines/macro/macro_service.py`: expose cached aggregate helpers and avoid recomputing expensive views more than needed.
- Create `pipelines/macro/dashboard.py`: assemble the initial Macro dashboard payload from existing service functions.
- Create `pipelines/macro/scenario.py`: deterministic macro shock and ETF sleeve impact analysis.
- Create `pipelines/macro/provider_health.py`: normalize provider status, stale causes, refresh evidence, and last-run summaries.
- Modify `app/web/index.html`: add UI containers for status, filters, scenario lab, provider health, and research-context preview.
- Modify `app/web/app.js`: replace all-or-nothing Macro loading with panel-level rendering, timeout-aware fetches, scenario actions, and drilldowns.
- Modify `app/web/styles.css`: add dense dashboard controls, scenario grid, provider health table, and mobile-safe panel states.
- Modify `scripts/check_ui_contract.py`: add required markers for new Macro surfaces.
- Modify `tests/test_macro_platform.py`: add backend unit/API coverage for dashboard aggregate, scenario analysis, and provider health.
- Modify `tests/test_ui_routing_contract.py`: assert `#macro` routing and required Macro markers.
- Create `scripts/macro_ui_smoke.py`: repeatable browser smoke for `#macro`, scenario run, search, and refresh status.
- Modify `docs/PROJECT_MAP.md` and `docs/ARCHITECTURE.md`: document the new Macro workbench data flow.

## Phase 1: Stabilize Loading And Panel Isolation

### Task 1: Add A Fast Dashboard Aggregate Endpoint

**Files:**
- Create: `pipelines/macro/dashboard.py`
- Modify: `core/schemas/macro.py`
- Modify: `app/api/routers/macro.py`
- Test: `tests/test_macro_platform.py`

- [ ] **Step 1: Write failing schema/API test**

Add this test to `tests/test_macro_platform.py`:

```python
def test_macro_dashboard_summary_endpoint_is_compact_and_operable(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get("/api/v1/macro/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "partial", "stale", "unavailable"}
    assert "overview" in body
    assert "coverage" in body
    assert "data_quality" in body
    assert "refresh" in body
    assert "generated_at" in body
    assert body["coverage"]["registry_series"] >= 70
    for item in body["overview"].get("key_indicators", []):
        assert len(item.get("observations", [])) <= 20
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests\test_macro_platform.py::test_macro_dashboard_summary_endpoint_is_compact_and_operable -q
```

Expected before implementation: fail with `404` or missing `/api/v1/macro/dashboard`.

- [ ] **Step 3: Add dashboard response schemas**

Add to `core/schemas/macro.py`:

```python
class MacroDashboardCoverage(BaseModel):
    registry_series: int
    enabled_series: int
    categories: dict[str, int] = Field(default_factory=dict)
    providers: dict[str, int] = Field(default_factory=dict)
    countries: dict[str, int] = Field(default_factory=dict)


class MacroDashboardResponse(BaseModel):
    status: MacroQualityStatus
    generated_at: str
    overview: dict[str, Any]
    coverage: MacroDashboardCoverage
    data_quality: dict[str, Any]
    refresh: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Implement the aggregate builder**

Create `pipelines/macro/dashboard.py`:

```python
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from core.schemas.macro import MacroDashboardCoverage, MacroDashboardResponse
from pipelines.macro import macro_service


def _count(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(str(item.get(key) or "unknown") for item in items))


def build_macro_dashboard(*, observation_limit: int = 20, refresh_status: dict[str, Any] | None = None) -> MacroDashboardResponse:
    series = macro_service.list_macro_series(include_disabled=False)
    items = list(series.get("items") or [])
    overview = macro_service.compact_macro_payload(
        macro_service.get_macro_overview(),
        observation_limit=max(0, min(int(observation_limit), 120)),
    )
    quality = macro_service.get_data_quality()
    quality_payload = quality.get("data_quality") or {}
    warnings = []
    if quality_payload.get("status") not in {"ok", None}:
        stale_count = len(quality_payload.get("stale_series") or [])
        missing_count = len(quality_payload.get("missing_series") or [])
        warnings.append(f"Macro data quality needs review: stale={stale_count}, missing={missing_count}.")
    return MacroDashboardResponse(
        status=quality_payload.get("status") or overview.get("data_quality", {}).get("status") or "unavailable",
        generated_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        overview=overview,
        coverage=MacroDashboardCoverage(
            registry_series=int(series.get("count") or len(items)),
            enabled_series=len(items),
            categories=_count(items, "category"),
            providers=_count(items, "provider"),
            countries=_count(items, "country"),
        ),
        data_quality=quality,
        refresh=refresh_status or {},
        warnings=warnings,
    )
```

- [ ] **Step 5: Wire the route**

Add to `app/api/routers/macro.py`:

```python
from pipelines.macro.dashboard import build_macro_dashboard
```

Add route before `/health`:

```python
@router.get("/dashboard")
async def get_dashboard(observation_limit: int = Query(default=20, ge=0, le=120)) -> dict[str, Any]:
    scheduler = get_data_mart_scheduler()
    refresh_status = scheduler.status() if scheduler is not None else {"enabled": False}
    return build_macro_dashboard(observation_limit=observation_limit, refresh_status=refresh_status).model_dump(mode="json")
```

- [ ] **Step 6: Run test and smoke endpoint**

Run:

```powershell
python -m pytest tests\test_macro_platform.py::test_macro_dashboard_summary_endpoint_is_compact_and_operable -q
curl.exe -sS -w "dashboard status=%{http_code} time=%{time_total}\n" -o $env:TEMP\macro_dashboard.json --max-time 10 "http://127.0.0.1:8002/api/v1/macro/dashboard?observation_limit=20"
```

Expected: pytest passes; live endpoint returns `200` and should be faster than the current multi-request page load.

### Task 2: Make UI Loading Progressive

**Files:**
- Modify: `app/web/app.js`
- Modify: `app/web/index.html`
- Modify: `app/web/styles.css`
- Modify: `scripts/check_ui_contract.py`
- Test: `tests/test_ui_routing_contract.py`

- [ ] **Step 1: Add failing UI marker checks**

Add these entries to `REQUIRED_UI_MARKERS` in `scripts/check_ui_contract.py`:

```python
"macro load status": 'id="macroLoadStatus"',
"macro scenario surface": 'id="macroScenarioSurface"',
"macro provider health": 'id="macroProviderHealthSurface"',
"macro research preview": 'id="macroResearchPreviewSurface"',
```

Run:

```powershell
python scripts\check_ui_contract.py --output reports\macro_ui_contract.json
```

Expected before UI edit: fail with the four missing markers.

- [ ] **Step 2: Add containers in `app/web/index.html`**

Inside `#macroSurface`, directly below `.macro-quick-actions`, add:

```html
<div id="macroLoadStatus" class="decision-surface compact-surface">
  <div class="home-news-empty">매크로 초기 상태를 확인하는 중입니다.</div>
</div>
```

Below the Macro Explorer section, add:

```html
<section class="home-card macro-card macro-provider-card macro-surface">
  <div class="home-card-head"><h3>공급자·갱신 상태</h3><span>scheduler, providers, stale causes</span></div>
  <div id="macroProviderHealthSurface" class="decision-surface compact-surface">
    <div class="home-news-empty">공급자 상태를 불러오는 중입니다.</div>
  </div>
</section>
```

Below the Macro Regime section, add:

```html
<section class="home-card macro-card macro-scenario-card macro-surface">
  <div class="home-card-head"><h3>매크로 시나리오</h3><span>deterministic shocks, advisory only</span></div>
  <div id="macroScenarioSurface" class="decision-surface">
    <div class="home-news-empty">시나리오를 선택하면 자산군 영향과 ETF sleeve 변화를 계산합니다.</div>
  </div>
</section>
```

Below the Portfolio Policy Hints section, add:

```html
<section class="home-card macro-card macro-research-card macro-surface">
  <div class="home-card-head"><h3>리서치 맥락 미리보기</h3><span>ticker-aware, structured payload only</span></div>
  <div id="macroResearchPreviewSurface" class="decision-surface">
    <div class="home-news-empty">티커를 입력하면 리서치 프롬프트에 들어갈 매크로 맥락을 미리 확인합니다.</div>
  </div>
</section>
```

- [ ] **Step 3: Add API entry and elements**

In `app/web/app.js`, add to `API`:

```javascript
macroDashboard: "/api/v1/macro/dashboard?observation_limit=20",
```

Add to `els`:

```javascript
macroLoadStatus: document.getElementById("macroLoadStatus"),
macroScenarioSurface: document.getElementById("macroScenarioSurface"),
macroProviderHealthSurface: document.getElementById("macroProviderHealthSurface"),
macroResearchPreviewSurface: document.getElementById("macroResearchPreviewSurface"),
```

- [ ] **Step 4: Add timeout-aware fetch**

Below `macroFetchJson`, add:

```javascript
async function macroFetchJsonWithTimeout(url, options = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await macroFetchJson(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") throw new Error(`요청 시간 초과: ${url}`);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
```

- [ ] **Step 5: Replace all-or-nothing initial load**

In `loadMacro(force = false)`, first fetch `API.macroDashboard` and render the main surfaces immediately:

```javascript
const dashboard = await macroFetchJsonWithTimeout(API.macroDashboard, {}, 10000);
const overview = dashboard.overview || {};
const seriesList = {
  status: "success",
  count: dashboard.coverage?.enabled_series || dashboard.coverage?.registry_series || 0,
  items: state.macroSeriesList?.items || [],
};
state.macroOverview = overview;
renderMacroOverview(overview);
renderMacroIndicatorTable(overview.key_indicators || []);
renderMacroCharts(overview);
renderMacroRegime(overview.regime || {}, overview.signals || []);
renderMacroAssetImpact(overview.asset_impact_summary || []);
if (els.macroLoadStatus) {
  els.macroLoadStatus.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(dashboard.status))}">${escapeHtml(dashboard.status || "unknown")}</span>
      <span>초기 대시보드 ${escapeHtml(dashboard.generated_at || "-")} · 상세 패널은 순차 로드됩니다.</span>
    </div>
  `;
}
```

Then fetch category panels with `Promise.allSettled`, and render each failed panel independently:

```javascript
const categoryJobs = [
  [els.macroInterestRatesSurface, API.macroInterestRates],
  [els.macroInflationSurface, API.macroInflation],
  [els.macroGrowthLaborSurface, API.macroGrowthLabor],
  [els.macroHousingConsumerSurface, API.macroHousingConsumer],
  [els.macroYieldCurveSurface, API.macroYieldCurve],
  [els.macroLiquidityCreditSurface, API.macroLiquidityCredit],
  [els.macroFinancialConditionsSurface, API.macroFinancialConditions],
  [els.macroFxDollarSurface, API.macroFxDollar],
  [els.macroCommoditiesSurface, API.macroCommodities],
];
const categoryResults = await Promise.allSettled(
  categoryJobs.map(([, url]) => macroFetchJsonWithTimeout(url, {}, 12000))
);
categoryResults.forEach((result, index) => {
  const [surface] = categoryJobs[index];
  if (result.status === "fulfilled") renderMacroCategory(surface, result.value);
  else if (surface) surface.innerHTML = decisionEmpty(`패널 로드 실패: ${result.reason.message || result.reason}`);
});
```

- [ ] **Step 6: Run UI checks**

Run:

```powershell
node --check app\web\app.js
python scripts\check_ui_contract.py --output reports\macro_ui_contract.json
```

Expected: JS syntax passes and `missing_markers: []`.

## Phase 2: Provider Health And Refresh Operability

### Task 3: Add Provider Health Surface

**Files:**
- Create: `pipelines/macro/provider_health.py`
- Modify: `core/schemas/macro.py`
- Modify: `app/api/routers/macro.py`
- Modify: `app/web/app.js`
- Test: `tests/test_macro_platform.py`

- [ ] **Step 1: Write failing provider health test**

Add:

```python
def test_macro_provider_health_endpoint_reports_scheduler_and_stale_causes(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get("/api/v1/macro/provider-health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "partial", "stale", "unavailable"}
    assert "providers" in body
    assert "scheduler" in body
    assert isinstance(body["stale_series"], list)
```

- [ ] **Step 2: Add schema**

Add to `core/schemas/macro.py`:

```python
class MacroProviderHealthItem(BaseModel):
    provider: str
    enabled: bool
    configured: bool
    latest_status: str = "unknown"
    latest_rows: int = 0
    latest_error: str | None = None


class MacroProviderHealthResponse(BaseModel):
    status: MacroQualityStatus
    generated_at: str
    providers: list[MacroProviderHealthItem] = Field(default_factory=list)
    stale_series: list[dict[str, Any]] = Field(default_factory=list)
    scheduler: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 3: Implement provider health builder**

Create `pipelines/macro/provider_health.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.schemas.macro import MacroProviderHealthItem, MacroProviderHealthResponse
from pipelines.macro import macro_service


def build_provider_health(scheduler_status: dict[str, Any] | None = None) -> MacroProviderHealthResponse:
    health = macro_service.get_health()
    quality = macro_service.get_data_quality()
    data_quality = quality.get("data_quality") or {}
    last_result = ((scheduler_status or {}).get("last_result") or {}).get("jobs", {}).get("macro_platform_data") or {}
    provider_runs = last_result.get("providers") or []
    provider_by_name = {row.get("provider"): row for row in provider_runs if isinstance(row, dict)}
    providers = []
    for name, configured in (health.get("providers") or {}).items():
        latest = provider_by_name.get(name) or {}
        providers.append(MacroProviderHealthItem(
            provider=name,
            enabled=True,
            configured=bool(configured),
            latest_status=str(latest.get("status") or "unknown"),
            latest_rows=int(latest.get("rows") or 0),
            latest_error=latest.get("error"),
        ))
    rows = []
    for row in quality.get("series") or []:
        if row.get("status") in {"stale", "unavailable", "partial"}:
            rows.append(row)
    return MacroProviderHealthResponse(
        status=data_quality.get("status") or "unavailable",
        generated_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        providers=providers,
        stale_series=rows,
        scheduler=scheduler_status or {},
        warnings=list(data_quality.get("errors") or []) + list(data_quality.get("notes") or []),
    )
```

- [ ] **Step 4: Wire route and UI renderer**

Add route:

```python
@router.get("/provider-health")
async def get_provider_health() -> dict[str, Any]:
    from pipelines.macro.provider_health import build_provider_health

    scheduler = get_data_mart_scheduler()
    status = scheduler.status() if scheduler is not None else {"enabled": False}
    return build_provider_health(status).model_dump(mode="json")
```

Add to `API`:

```javascript
macroProviderHealth: "/api/v1/macro/provider-health",
```

Add renderer:

```javascript
function renderMacroProviderHealth(data = {}) {
  if (!els.macroProviderHealthSurface) return;
  const providers = Array.isArray(data.providers) ? data.providers : [];
  const stale = Array.isArray(data.stale_series) ? data.stale_series : [];
  els.macroProviderHealthSurface.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(data.status))}">${escapeHtml(data.status || "unknown")}</span>
      <span>공급자 ${escapeHtml(_fmtNumber(providers.length))}개 · stale/unavailable ${escapeHtml(_fmtNumber(stale.length))}개</span>
    </div>
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>공급자</th><th>설정</th><th>최근 상태</th><th>행</th><th>오류</th></tr></thead>
        <tbody>
          ${providers.map((row) => `
            <tr>
              <td>${escapeHtml(row.provider || "")}</td>
              <td>${row.configured ? "연결" : "미연결"}</td>
              <td><span class="table-status ${escapeHtml(decisionStatusClass(row.latest_status))}">${escapeHtml(row.latest_status || "unknown")}</span></td>
              <td>${escapeHtml(_fmtNumber(row.latest_rows || 0))}</td>
              <td>${escapeHtml(row.latest_error || "-")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
    ${stale.length ? `<div class="macro-warning">점검 대상: ${escapeHtml(stale.slice(0, 8).map((row) => row.series_id).join(", "))}</div>` : ""}
  `;
}
```

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest tests\test_macro_platform.py::test_macro_provider_health_endpoint_reports_scheduler_and_stale_causes -q
node --check app\web\app.js
curl.exe -sS -w "provider_health status=%{http_code} time=%{time_total}\n" -o $env:TEMP\macro_provider_health.json --max-time 10 http://127.0.0.1:8002/api/v1/macro/provider-health
```

Expected: test passes, syntax passes, endpoint returns `200`.

## Phase 3: Scenario And Stress Workbench

### Task 4: Add Deterministic Scenario Engine

**Files:**
- Create: `pipelines/macro/scenario.py`
- Modify: `core/schemas/macro.py`
- Modify: `app/api/routers/macro.py`
- Modify: `app/web/index.html`
- Modify: `app/web/app.js`
- Test: `tests/test_macro_platform.py`

- [ ] **Step 1: Write failing scenario test**

Add:

```python
def test_macro_scenario_endpoint_returns_advisory_asset_impacts(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/v1/macro/scenario",
        json={
            "name": "rates_up_credit_wider",
            "rate_shock_bp": 100,
            "inflation_shock_pct": 0.5,
            "credit_spread_shock_bp": 150,
            "oil_shock_pct": 20,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["advisory_only"] is True
    assert body["scenario"]["rate_shock_bp"] == 100
    assert body["risk_level"] in {"watch", "reduce", "neutral"}
    assert len(body["asset_impacts"]) >= 4
    assert "orders" not in body
```

- [ ] **Step 2: Add schemas**

Add:

```python
class MacroScenarioRequest(BaseModel):
    name: str = "custom"
    rate_shock_bp: float = Field(default=0.0, ge=-500.0, le=500.0)
    inflation_shock_pct: float = Field(default=0.0, ge=-5.0, le=5.0)
    growth_shock_pct: float = Field(default=0.0, ge=-10.0, le=10.0)
    credit_spread_shock_bp: float = Field(default=0.0, ge=-1000.0, le=1000.0)
    oil_shock_pct: float = Field(default=0.0, ge=-80.0, le=200.0)


class MacroScenarioResponse(BaseModel):
    status: str
    scenario: MacroScenarioRequest
    risk_level: str
    asset_impacts: list[AssetImpact] = Field(default_factory=list)
    sleeve_hints: list[PortfolioEtfCandidate] = Field(default_factory=list)
    explanation: str
    data_quality: MacroDataQuality
    advisory_only: bool = True
```

- [ ] **Step 3: Implement scenario logic**

Create `pipelines/macro/scenario.py`:

```python
from __future__ import annotations

from core.schemas.macro import (
    AssetImpact,
    MacroDataQuality,
    MacroScenarioRequest,
    MacroScenarioResponse,
    PortfolioEtfCandidate,
)
from pipelines.macro import macro_service


def run_macro_scenario(request: MacroScenarioRequest) -> MacroScenarioResponse:
    overview = macro_service.get_macro_overview()
    stress_score = 0.0
    stress_score += max(0.0, request.rate_shock_bp) / 100.0
    stress_score += max(0.0, request.credit_spread_shock_bp) / 150.0
    stress_score += max(0.0, request.inflation_shock_pct) / 0.5
    stress_score += max(0.0, request.oil_shock_pct) / 20.0
    stress_score += max(0.0, -request.growth_shock_pct) / 1.0
    if stress_score >= 3.0:
        risk_level = "reduce"
    elif stress_score >= 1.0:
        risk_level = "watch"
    else:
        risk_level = "neutral"
    confidence = max(0.0, min(1.0, overview.regime.confidence))
    asset_impacts = [
        AssetImpact(asset_class="US Equities", impact="negative" if risk_level == "reduce" else "mixed", confidence=confidence, reason="Scenario stress raises discount-rate or growth risk.", key_risks=["Valuation compression"], related_indicators=["DGS10", "BAMLH0A0HYM2"]),
        AssetImpact(asset_class="Long Bonds", impact="negative" if request.rate_shock_bp > 0 else "mixed", confidence=confidence, reason="Rate shock directly pressures duration.", key_risks=["Term premium shock"], related_indicators=["DGS10", "DFII10"]),
        AssetImpact(asset_class="Credit", impact="negative" if request.credit_spread_shock_bp > 0 else "neutral", confidence=confidence, reason="Spread widening lowers credit risk appetite.", key_risks=["Default cycle"], related_indicators=["BAMLH0A0HYM2"]),
        AssetImpact(asset_class="Gold", impact="mixed" if request.rate_shock_bp > 0 else "positive", confidence=confidence, reason="Inflation stress can help gold, real-rate stress can offset it.", key_risks=["Real-yield surge"], related_indicators=["DFII10", "T10YIE"]),
        AssetImpact(asset_class="Cash", impact="positive" if risk_level in {"watch", "reduce"} else "neutral", confidence=confidence, reason="Cash has option value in stressed scenarios.", key_risks=["Inflation erosion"], related_indicators=["FEDFUNDS"]),
    ]
    sleeve_hints = [
        PortfolioEtfCandidate(sleeve="equity", bias="lower_range" if risk_level == "reduce" else "neutral", tickers=["SPY", "USMV"], role="scenario_watch", rationale="Keep equity exposure broad and verify downside in Quant Lab."),
        PortfolioEtfCandidate(sleeve="bonds", bias="shorter_duration" if request.rate_shock_bp > 0 else "neutral_duration", tickers=["SGOV", "IEF", "TLT"], role="duration_control", rationale="Compare short and intermediate duration under the shock."),
        PortfolioEtfCandidate(sleeve="cash", bias="increase" if risk_level == "reduce" else "hold", tickers=["SGOV", "BIL"], role="liquidity_buffer", rationale="Use as advisory liquidity sleeve, not an order."),
    ]
    return MacroScenarioResponse(
        status="success",
        scenario=request,
        risk_level=risk_level,
        asset_impacts=asset_impacts,
        sleeve_hints=sleeve_hints,
        explanation=f"Scenario stress level is {risk_level}; this is deterministic advisory analysis only.",
        data_quality=overview.data_quality,
        advisory_only=True,
    )
```

- [ ] **Step 4: Add route**

In `app/api/routers/macro.py`, import `MacroScenarioRequest` and add:

```python
@router.post("/scenario")
async def post_scenario(request: MacroScenarioRequest) -> dict[str, Any]:
    from pipelines.macro.scenario import run_macro_scenario

    return run_macro_scenario(request).model_dump(mode="json")
```

- [ ] **Step 5: Add minimal UI controls**

In `#macroScenarioSurface`, render preset buttons and result table:

```javascript
function renderMacroScenarioStarter() {
  if (!els.macroScenarioSurface) return;
  els.macroScenarioSurface.innerHTML = `
    <div class="decision-chip-row">
      <button type="button" class="linkish decision-inline-action" data-action="macro-scenario" data-scenario="rates_up">금리 +100bp</button>
      <button type="button" class="linkish decision-inline-action" data-action="macro-scenario" data-scenario="stagflation">스태그플레이션</button>
      <button type="button" class="linkish decision-inline-action" data-action="macro-scenario" data-scenario="credit_stress">신용 스프레드 +150bp</button>
    </div>
    <div class="decision-summary ok">시나리오는 자문용 민감도 분석이며 주문, 정책 변경, 자동 리밸런싱을 실행하지 않습니다.</div>
  `;
}
```

Use this request mapping:

```javascript
function macroScenarioPayload(name) {
  if (name === "rates_up") return { name, rate_shock_bp: 100 };
  if (name === "stagflation") return { name, rate_shock_bp: 75, inflation_shock_pct: 1.0, growth_shock_pct: -1.0, oil_shock_pct: 20 };
  if (name === "credit_stress") return { name, credit_spread_shock_bp: 150, growth_shock_pct: -1.5 };
  return { name: "custom" };
}
```

- [ ] **Step 6: Verify**

Run:

```powershell
python -m pytest tests\test_macro_platform.py::test_macro_scenario_endpoint_returns_advisory_asset_impacts -q
node --check app\web\app.js
curl.exe -sS -X POST -H "Content-Type: application/json" -d "{\"name\":\"rates_up\",\"rate_shock_bp\":100}" http://127.0.0.1:8002/api/v1/macro/scenario
```

Expected: response has `advisory_only=true` and no order/trade fields.

## Phase 4: Research And Portfolio Integration Without Auto-Trading

### Task 5: Add Ticker-Aware Macro Research Preview

**Files:**
- Modify: `app/web/index.html`
- Modify: `app/web/app.js`
- Modify: `tests/test_macro_platform.py`
- Modify: `pipelines/macro/research_context.py` only if response shape needs additional metadata.

- [ ] **Step 1: Add backend contract test**

Add:

```python
def test_macro_research_context_is_ticker_aware_and_advisory(monkeypatch, tmp_path) -> None:
    _reset_macro_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get("/api/v1/macro/research-context", params={"ticker": "JPM"})
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_hints"]["advisory_only"] is True
    assert "risk_level" in body
    assert "data_quality_warnings" in body
```

- [ ] **Step 2: Add UI control**

Inside `#macroResearchPreviewSurface`, render:

```html
<div class="input-action-row">
  <input id="macroResearchTicker" type="search" value="JPM" aria-label="Macro research ticker" placeholder="JPM, TLT, SPY" />
  <button type="button" id="macroResearchPreviewRun" class="ghost-btn" data-testid="macro-research-preview-run">미리보기</button>
</div>
<div id="macroResearchPreviewResult" class="decision-surface compact-surface">
  <div class="home-news-empty">티커별 매크로 맥락을 불러올 수 있습니다.</div>
</div>
```

Add UI contract markers for `macroResearchTicker`, `macroResearchPreviewRun`, and `macroResearchPreviewResult`.

- [ ] **Step 3: Add renderer**

In `app/web/app.js`:

```javascript
macroResearchContext: (ticker) => `/api/v1/macro/research-context?ticker=${encodeURIComponent(ticker || "")}`,
macroResearchTicker: document.getElementById("macroResearchTicker"),
macroResearchPreviewRun: document.getElementById("macroResearchPreviewRun"),
macroResearchPreviewResult: document.getElementById("macroResearchPreviewResult"),
```

Add:

```javascript
function renderMacroResearchPreview(data = {}) {
  const target = els.macroResearchPreviewResult || els.macroResearchPreviewSurface;
  if (!target) return;
  const warnings = Array.isArray(data.data_quality_warnings) ? data.data_quality_warnings : [];
  target.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(data.risk_level === "high" ? "warn" : "ok")}">${escapeHtml(data.risk_level || "unknown")}</span>
      <span>레짐 ${escapeHtml(data.regime?.display_name || data.regime?.name || "unknown")} · advisory only</span>
    </div>
    <div class="decision-summary ${warnings.length ? "warn" : "ok"}">${escapeHtml((data.regime?.interpretation || "구조화된 매크로 맥락입니다."))}</div>
    ${warnings.length ? `<div class="macro-warning">${escapeHtml(warnings.join(" "))}</div>` : ""}
  `;
}
```

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests\test_macro_platform.py::test_macro_research_context_is_ticker_aware_and_advisory -q
node --check app\web\app.js
python scripts\check_ui_contract.py --output reports\macro_ui_contract.json
```

Expected: all pass; UI remains advisory-only.

## Phase 5: Explorer And Chart Usability

### Task 6: Add Filters, Multi-Series Compare, And Better Empty/Error States

**Files:**
- Modify: `app/web/index.html`
- Modify: `app/web/app.js`
- Modify: `app/web/styles.css`
- Modify: `scripts/check_ui_contract.py`

- [ ] **Step 1: Add UI markers**

Add markers:

```python
"macro provider filter": 'id="macroProviderFilter"',
"macro category filter": 'id="macroCategoryFilter"',
"macro compare surface": 'id="macroCompareSurface"',
```

- [ ] **Step 2: Add controls**

In the Macro Explorer form, add:

```html
<label>
  <span>범주</span>
  <select id="macroCategoryFilter" aria-label="Macro category filter">
    <option value="">전체</option>
    <option value="interest_rates">금리</option>
    <option value="inflation">인플레이션</option>
    <option value="growth">성장</option>
    <option value="labor">고용</option>
    <option value="liquidity_credit">유동성·신용</option>
    <option value="fx_dollar">FX·달러</option>
    <option value="commodities">원자재</option>
  </select>
</label>
<label>
  <span>공급자</span>
  <select id="macroProviderFilter" aria-label="Macro provider filter">
    <option value="">전체</option>
    <option value="fred">FRED</option>
    <option value="yahoo">Yahoo</option>
    <option value="ecos">ECOS</option>
    <option value="oecd">OECD</option>
    <option value="worldbank">WorldBank</option>
  </select>
</label>
```

Add below detail:

```html
<div id="macroCompareSurface" class="decision-surface">
  <div class="home-news-empty">비교할 시계열을 선택하면 정규화 차트를 표시합니다.</div>
</div>
```

- [ ] **Step 3: Filter results client-side first**

In `renderMacroSeriesSearchResults`, before rendering:

```javascript
const categoryFilter = els.macroCategoryFilter?.value || "";
const providerFilter = els.macroProviderFilter?.value || "";
const visibleItems = items.filter((item) => {
  if (categoryFilter && item.category !== categoryFilter) return false;
  if (providerFilter && item.provider !== providerFilter) return false;
  return true;
});
```

Render `visibleItems` instead of `items`, and show:

```javascript
if (!visibleItems.length) {
  els.macroSeriesSearchResults.innerHTML = decisionEmpty("필터 조건에 맞는 시계열이 없습니다. 범주 또는 공급자 필터를 완화하세요.");
  return;
}
```

- [ ] **Step 4: Verify mobile-safe layout**

Run:

```powershell
node --check app\web\app.js
python scripts\check_ui_contract.py --output reports\macro_ui_contract.json
```

Then browser-smoke desktop and mobile widths:

```powershell
python scripts\macro_ui_smoke.py --url http://127.0.0.1:8002/ui/#macro --width 1440 --height 1200
python scripts\macro_ui_smoke.py --url http://127.0.0.1:8002/ui/#macro --width 390 --height 844
```

Expected: no console errors, Macro tab selected, overview rendered, search/filter visible, no text overlap.

## Phase 6: Repeatable Browser Smoke

### Task 7: Add A Macro UI Smoke Script

**Files:**
- Create: `scripts/macro_ui_smoke.py`
- Test: local running server at `http://127.0.0.1:8002/ui/#macro`

- [ ] **Step 1: Create smoke script**

Create `scripts/macro_ui_smoke.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8002/ui/#macro")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1200)
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"BLOCKED: playwright unavailable: {exc}")
        return 2
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type in {"error", "warning"} else None)
        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#macroDashboardTab[aria-selected=\"true\"]", timeout=15000)
        page.wait_for_selector("#macroOverviewSurface .decision-status-row", timeout=20000)
        page.wait_for_selector("#macroDataQualitySurface", timeout=20000)
        title = page.locator("#macroSurface h3").first.text_content() or ""
        if "매크로" not in title and "Macro" not in title:
            print(f"FAIL: unexpected macro title: {title}")
            return 1
        if errors:
            print("FAIL: console warnings/errors")
            for item in errors:
                print(item)
            return 1
        out_dir = Path("reports")
        out_dir.mkdir(exist_ok=True)
        page.screenshot(path=str(out_dir / f"macro-ui-{args.width}x{args.height}.png"), full_page=False)
        browser.close()
    print("PASS: macro UI smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify script**

Run:

```powershell
python scripts\macro_ui_smoke.py --url http://127.0.0.1:8002/ui/#macro --width 1440 --height 1200
```

Expected: `PASS: macro UI smoke`. If Playwright is unavailable, report `BLOCKED` and use the MCP browser smoke evidence instead.

## Phase 7: Documentation And Release Gate

### Task 8: Reconcile Checklist And Docs

**Files:**
- Modify: `docs/MACRO_IMPLEMENTATION_CHECKLIST.md`
- Modify: `docs/PROJECT_MAP.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Update checklist**

Append a new section to `docs/MACRO_IMPLEMENTATION_CHECKLIST.md`:

```markdown
## 10. Macro Platform Advancement

- Phase A: Fast dashboard aggregate and progressive panel loading. Status: NOT_DONE.
- Phase B: Provider health and refresh operability. Status: NOT_DONE.
- Phase C: Deterministic scenario workbench. Status: NOT_DONE.
- Phase D: Ticker-aware research preview. Status: NOT_DONE.
- Phase E: Explorer filters, compare view, and mobile UI hardening. Status: NOT_DONE.
- Phase F: Repeatable browser smoke. Status: NOT_DONE.

Completion gate:
- `python -m pytest tests\test_macro_platform.py -q`
- `node --check app\web\app.js`
- `python scripts\check_ui_contract.py --output reports\macro_ui_contract.json`
- `python scripts\macro_ui_smoke.py --url http://127.0.0.1:8002/ui/#macro --width 1440 --height 1200`
- `python scripts\macro_ui_smoke.py --url http://127.0.0.1:8002/ui/#macro --width 390 --height 844`
```

- [ ] **Step 2: Update architecture docs**

In `docs/ARCHITECTURE.md`, add a Macro data flow note:

```markdown
Macro dashboard flow:
`app/web/app.js` loads `/api/v1/macro/dashboard` for the first render, then hydrates detailed category panels independently. Scenario analysis stays deterministic under `pipelines/macro/scenario.py`; it returns advisory-only impacts and never creates orders or mutates AI Portfolio policy.
```

In `docs/PROJECT_MAP.md`, add:

```markdown
- `pipelines/macro/dashboard.py`: cached aggregate payload for the Macro dashboard first render.
- `pipelines/macro/provider_health.py`: provider, scheduler, and stale-series operational status.
- `pipelines/macro/scenario.py`: deterministic advisory-only Macro shock analysis.
- `scripts/macro_ui_smoke.py`: browser smoke for the static Macro tab.
```

- [ ] **Step 3: Run full Macro validation ladder**

Run:

```powershell
python -m pytest tests\test_macro_platform.py tests\test_ui_routing_contract.py -q
node --check app\web\app.js
python scripts\check_ui_contract.py --output reports\macro_ui_contract.json
curl.exe -sS -w "dashboard status=%{http_code} time=%{time_total}\n" -o $env:TEMP\macro_dashboard.json --max-time 10 "http://127.0.0.1:8002/api/v1/macro/dashboard?observation_limit=20"
python scripts\macro_ui_smoke.py --url http://127.0.0.1:8002/ui/#macro --width 1440 --height 1200
python scripts\macro_ui_smoke.py --url http://127.0.0.1:8002/ui/#macro --width 390 --height 844
```

Expected: tests pass, JS syntax passes, UI contract has `missing_markers: []`, dashboard endpoint returns `200`, browser smoke passes or is explicitly marked `BLOCKED` with MCP fallback evidence.

## Execution Order

1. Stabilize loading first. Do not add scenario or research features until the first render is fast and panel failures are isolated.
2. Add provider health next because it explains stale/unavailable data and refresh behavior.
3. Add scenario analysis after data-quality visibility is clear, keeping it deterministic and advisory-only.
4. Add research preview and explorer filters after the core dashboard is reliable.
5. Finish with repeatable browser smoke and checklist reconciliation.

## Acceptance Criteria

- Macro tab first useful render does not wait for every category endpoint.
- A slow or failed Macro endpoint affects only its own panel.
- Provider/scheduler/stale-series state is visible in the UI.
- Scenario analysis is deterministic, auditable, and contains no trade/order side effects.
- Research preview uses structured Macro payload and remains advisory-only.
- UI contract, backend tests, JS syntax, and browser smoke all pass or report exact environment blockers.
