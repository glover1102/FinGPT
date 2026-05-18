# FinGPT Quant Research Upgrade Execution Plan

## 목적

FinGPT를 단순 로컬 RAG 리서치 도구가 아니라, 기준일과 출처가 명확하고 종목, ETF, 금리, 신용, FX, 원자재, 크립토, 섹터/테마 질의를 안정적으로 처리하는 quant-aware research platform으로 고도화한다.

## 운영 원칙

- 기존 REST top-level schema는 유지한다.
- 신규 진단, 정량, 검증 정보는 `execution_meta.extras`, `key_metrics`, report/UI rendering layer에 additive로만 추가한다.
- LLM은 숫자를 새로 만들지 않고 deterministic quant layer가 만든 수치를 해석한다.
- 모든 수치 출력은 `value`, `unit`, `as_of`, `source`, `freshness_status`, `evidence_doc_ids`를 우선 갖는다.
- parser/model 오류는 UI에 raw exception으로 노출하지 않고 structured partial/fallback으로 정리한다.
- 기능 변경은 기존 동작을 깨지 않거나 상향하는 방향으로만 진행한다.

## 현재 진행 상태

- [x] 실행 계획 문서 생성 및 체크리스트 정리
- [x] single ticker `execution_meta.extras.quant_snapshot` 추가
- [x] topic/rates/credit/FX/commodity/crypto quant snapshot top-level 필드 정리
- [x] single ticker scenario/execution UI fallback 보강
- [x] saved output validation에 decision richness/topic final gate 추가
- [x] saved output validation에 duplicate paragraph ratio gate 추가
- [x] validation gate에 topic latency profile 연결
- [x] Quant tab decision read와 Scenario tab evidence badge 렌더링 보강
- [x] Risk tab factor/downside/stress/data-gap 카드 보강
- [x] topic deterministic fast path 확대
- [x] tickerless macro/rates 질의의 느린 LLM fallback 제거
- [x] single ticker LLM JSON 실패 시 deterministic inference fallback 추가
- [x] Python compile 검증
- [x] JS syntax 검증
- [x] targeted unit/integration tests
- [x] full pytest suite
- [x] live topic latency profile
- [x] quality review suite
- [x] full validation gate 최종 재실행
- [x] live browser smoke 최종 재확인

## 1단계: Quant Signal Layer 강화

### 목표

LLM 전에 투자 판단에 필요한 정량 지표를 먼저 계산하고, 이를 report, prompt, UI의 공통 입력으로 사용한다.

### 구현 체크리스트

- [x] single ticker 응답에 formal `quant_snapshot` 추가
- [x] single ticker snapshot에 `asset_class`, `target`, `as_of`, `freshness_status`, `source`, `metrics`, `regime`, `source_status` 제공
- [x] `key_metrics` 기반 regime 판단 생성
- [x] source/evidence/as_of를 metric record에 유지
- [x] TLT/rates, credit, FX, commodity, crypto quant snapshot에 동일 top-level 필드 제공
- [x] technical indicator 기반 fallback summary/bull/bear 생성
- [x] portfolio-level risk contribution/stress P&L internal schema 및 API 추가

### 주요 파일

- `pipelines/orchestration/research_pipeline.py`
- `pipelines/analyze/topic_quant.py`
- `tests/test_single_ticker_quant_snapshot.py`
- `tests/test_topic_quant.py`

## 2단계: Topic Fast Path 및 Latency 개선

### 목표

TLT, GLD, FX, BTC, AI semiconductors, tickerless macro 질의를 기본적으로 current-doc + quant snapshot 기반 fast path로 처리한다. LLM JSON 실패가 전체 실패나 2~6분 지연으로 이어지지 않게 한다.

### 구현 체크리스트

- [x] `rates_bonds`, `commodity`, `fx`, `crypto`, `sector_theme`, `equity_index` deterministic fast path 지원
- [x] credit topic deterministic fast path 유지
- [x] rates/bonds는 FRED가 없더라도 가격+duration proxy가 충분하면 fast path 허용
- [x] sparse rates 케이스는 metric coverage guard로 느슨하게 성공 처리하지 않음
- [x] tickerless macro routing이 topic fast path로 처리됨
- [x] topic latency profile을 validation artifact로 저장

### 검증 결과

- TLT: `local-deterministic-fast-path`, 약 11초
- GLD: `local-deterministic-fast-path`, 약 12초
- EURUSD: `local-deterministic-fast-path`, 약 9초
- BTC-USD: `local-deterministic-fast-path`, 약 8초
- AI semiconductors: `local-deterministic-fast-path`, 약 7초
- tickerless macro: `local-deterministic-fast-path`, 약 10초

## 3단계: Report Template 및 UI 품질

### 목표

종목과 비종목 질의가 같은 얕은 문장으로 출력되지 않도록 asset class별 decision memo 구조를 유지한다.

### 구현 체크리스트

- [x] single ticker에서 scenario/execution이 비어 있으면 UI가 quant 기반 fallback을 표시
- [x] UI가 top-level, `execution_meta.extras`, `quant_snapshot` alias를 순차 확인
- [x] 문자열/객체 형태 scenario/strategy 정규화
- [x] topic pipeline final invariant에서 scenario/execution/key risk 누락 보정
- [x] Quant tab에 regime/decision read 표시
- [x] Risk tab에 factor risk, downside, stress, data gap 표시
- [ ] backend report builder의 single equity/rates/credit/FX/commodity/crypto template 추가 정리

## 4단계: Quality Gate 강화

### 목표

한국어, 근거/기준일, 시나리오/전략, parser 오류, partial 사유, 문단 반복을 자동 검증한다.

### 구현 체크리스트

- [x] `duplicate_paragraph_ratio` metric 추가
- [x] `language_ok` 판정에서 non-descriptive metric fields 제외
- [x] topic final gate에 scenario/execution/driver/risk 기준 유지
- [x] latency gate를 `validation_gate.py`와 `verify_production_path.ps1`에 연결
- [x] single ticker fallback 테스트 추가
- [x] quality review suite 통과
- [x] full validation gate 최종 artifact 갱신

## 5단계: Compatibility 및 운영 안정성

### 목표

OpenBB/Yahoo/FRED/SEC 중심 운영과 기존 UI/API 호환성을 유지하면서, FMP/Alpha Vantage/Transcript는 optional source로 격리한다.

### 구현 체크리스트

- [x] OpenBB package compatibility check 유지
- [x] OpenBB Workspace agent endpoint는 optional adapter로 유지
- [x] `OPENBB_AGENT_ENABLED=false` 기본값에서 core API/UI 영향 없음
- [x] `OPENBB_AGENT_ENABLED=true`일 때 `openbb-ai` / `sse-starlette`를 blocking dependency로 승격
- [x] `bootstrap_local.ps1 -WithOpenBBAgent` 선택 설치 경로 추가
- [x] `/ui/` static contract smoke를 validation gate에 추가
- [x] release-candidate gate alias 추가 (`--release-candidate`, `-ReleaseCandidate`)
- [x] FRED preflight transient failure retry 및 fallback 메시지 정리
- [x] preflight에서 Yahoo, SEC, FRED, Ollama, Qdrant critical check 수행
- [x] FMP/Alpha/transcript disabled 상태를 warning이 아닌 운영 정책으로 명확화
- [x] local qwen2.5:7b baseline 유지
- [x] external provider version drift에 대한 lock/update policy 추가 문서화

## 검증 로그

최근 확인한 명령:

```powershell
python -m py_compile .\pipelines\orchestration\topic_pipeline.py .\pipelines\orchestration\research_pipeline.py
python -m pytest .\tests\test_topic_pipeline.py .\tests\test_topic_quant.py .\tests\test_research_pipeline_fallback.py -q
python -m pytest .\tests -q
node --check .\app\web\app.js
python .\scripts\validation_gate.py
powershell -ExecutionPolicy Bypass -File .\scripts\verify_production_path.ps1
python .\scripts\profile_topic_latency.py --suite topic --output .\reports\topic_latency_profile.json
python quality_review.py --suite all --output .\reports\quality_review_results.json
python .\scripts\validation_gate.py --release-candidate
python .\scripts\check_provider_versions.py
python .\scripts\check_provider_versions.py --require-openbb-agent
python .\scripts\check_ui_contract.py
$env:OPENBB_AGENT_ENABLED='true'; python .\scripts\check_openbb_agent_compat.py --probe-query
python .\scripts\probe_openbb_agent_live.py --base-url http://127.0.0.1:8030
```

최근 결과:

- OpenBB adapter targeted tests: `9 passed`
- provider/OpenBB/portfolio targeted tests: `16 passed`
- full pytest: `257 passed, 3 subtests passed`
- default validation gate: `automated_passed=true`, 약 49초, live smoke skipped
- PowerShell verification entrypoint: `automated validation passed`, 약 73초, live smoke skipped
- topic latency profile: gate failures `0`
- quality review suite: gate failures `0`
- full validation gate: `automated_passed=true` (2026-04-29T15:29:09Z)
- OpenBB live HTTP/SSE dry-run probe: `passed` (`/agents.json`, `/query`, message/table/citation/done events)
- preflight: all critical dependencies operational (2026-04-30T00:53 KST)
- browser smoke: home dashboard widgets visible, latest result tabs `Quant/Risk/Scenarios` non-empty, console errors `0`

## 남은 작업

1. OpenBB Workspace 계정/앱 내부에 custom agent URL을 등록하는 수동 UI 검증은 외부 Workspace 접근 권한이 필요하다. 로컬 HTTP/SSE 계약은 `probe_openbb_agent_live.py`와 `OPENBB_AGENT_ENABLED=true` contract gate로 검증한다.
2. live CLI/API smoke는 로컬 LLM 속도에 따라 길어질 수 있으므로 기본 게이트에서 분리했다. 릴리스 후보는 `python scripts/validation_gate.py --release-candidate` 또는 `scripts/verify_production_path.ps1 -ReleaseCandidate`로 명시 실행한다.
