# FinGPT 업데이트 제안서

> 프로젝트 목적(**로컬·프라이버시 유지**, **근거 기반 환각 방지**, **재현 가능한 아티팩트**)에
> 정렬된 개선 우선순위 정리. 코드 리뷰 기준일: 2026-04-22.

## 진행 현황 (2026-04-22)

- `[x]` **즉시 교정 위생 이슈**: CLI 오타, 모델 alias, CORS 기본값 로컬 한정, venv 없을 때 가이드.
- `[x]` **P0-#2 실행 히스토리 영속화** — `pipelines/output/run_history.py`, `data/outputs/runs/{TICKER}/{TS}/`, SQLite `data/runs.db`, `/api/v1/runs`·`/api/v1/runs/{id}`·`/api/v1/runs/summary/{ticker}`, UI 서버 기반 히스토리 + confidence 스파크라인.
- `[x]` **P0-#1 근거 ↔ Bull/Bear 링크** — 모델 스키마 `bull_points/bear_points: [{text, evidence_doc_ids}]`, `AnalysisResponse.bull_evidence_ids/bear_evidence_ids`, 리포트(.md/.html)에 per-bullet evidence 표기, UI 칩 클릭 → Evidence 아코디언 점프.
- `[x]` **P0-#3 Preflight API & UI 배지** — `/api/v1/preflight`(15s 캐시), `/api/v1/runbook/failure-modes`, 상단 배지/패널, 실패 시 경고/크리티컬 구분.
- `[x]` **P1-#8 실행 메타 노출** — `AnalysisResponse.execution_meta`(모델/폴백/레이턴시/프롬프트 크기/청크 수/렌즈/호라이즌/stage 실행기록), UI Diagnostics 탭에 Inference Trace + Stage Timeline 추가.
- `[x]` **P1-#5 수집 TTL 캐시** — `pipelines/collect/cache.py`(process-local LRU+TTL, 기본 300s/32 entries, 빈 결과는 네거티브 캐싱 금지), `CollectionOutcome.{cache_hit, cached_at, cache_age_s}`, `/api/v1/collection/cache`·`/api/v1/collection/cache/invalidate`, UI 결과 헤더 `cache · N` 배지 + Diagnostics cache_hit/cached_at.
- `[x]` **P1-#4 SSE 스트리밍** — `/api/v1/research/stream`(text/event-stream, 15s heartbeat, 클라이언트 disconnect 감지), `run_pipeline_async(..., event_sink=...)`로 stage 단위 이벤트(`pipeline_started`/`stage_started`/`stage_completed`/`pipeline_completed`/`pipeline_failed`/`result`) emit, UI는 fetch ReadableStream으로 실제 진행률·하위 상태 텍스트·warn 스테이지 표시.
- `[x]` **P1-#6 멀티 티커 비교 모드** — `CompareRequest`/`CompareResponse`, `POST /api/v1/research/compare`(최대 5 티커, `asyncio.Semaphore` 기반 concurrency 제한, 개별 실패는 배치를 중단시키지 않음), UI Compare 토글(쉼표 구분 입력, 칩은 append, 비교 테이블 + 티커별 요약 카드).
- `[x]` **P1-#7 Watchlist + 스케줄러** — `pipelines/watchlist/{store,scheduler}.py`(atomic JSON `data/watchlist.json`, thread-safe store, in-process asyncio 스케줄러, per-item `interval_hours`/`enabled`/run counters), CRUD/run-now 엔드포인트(`GET·POST·PUT·DELETE /api/v1/watchlist[/{id}]`, `POST /api/v1/watchlist/{id}/run`), UI Watchlist 섹션(추가/일시정지/즉시실행/폼으로 불러오기, 스케줄러 상태 배지, 30s 폴링).
- `[x]` **P2-#12 Qdrant 관리자 패널** — `core/utils/qdrant_admin.py`(collection info + ticker breakdown + age/ticker purge with payload 기반 filter, 전체 삭제 거부), `/api/v1/qdrant/collection`·`/api/v1/qdrant/purge`(dry-run 지원), UI 상단 `Qdrant` 버튼 → 통계/티커별 카운트/Dry run·Purge 컨트롤.
- `[x]` **P2-#11 내보내기 포맷 확장** — `pipelines/output/exporters.py`(CSV Bull/Bear + 증거 `doc_id` / JSONL 케이스별 레코드 + execution_meta 헤더), `/api/v1/outputs/export/csv`·`/api/v1/outputs/export/jsonl?include_raw_context=`, UI 결과 헤더 `Export ▾` 드롭다운(CSV / JSONL / JSONL lean).
- `[x]` **P2-#10 소스 커버리지 확장** — `pipelines/collect/google_news_rss.py`(무키, stdlib XML 파서, when:Xd 쿼리, freshness 필터 적용), YF → FMP → **Google News RSS** → SEC fallback 체인에 삽입, provider_results에 `news:google_news_rss` 표기.
- `[x]` **P2-#13 Evaluation 대시보드** — `core/utils/eval_dashboard.py`(report.md + quality_review_results.json 통합, category breakdown·purity/confidence 평균·status 카운트), `/api/v1/eval/dashboard`, UI 상단 `Quality` 버튼 → KPI + 카테고리 pass/partial/fail 바 + 최근 케이스 리스트 + 전체 eval markdown 토글.
- `[x]` **P2-#9 Pluggable Risk Engine** — `pipelines/analyze/risk_factory.py` + `finbert_risk_engine.py`(lazy transformers import, 모델 싱글톤, 체인 fallback), `settings.risk_engine`/`RISK_ENGINE` 환경변수, `/api/v1/config`에 `risk_engine` 노출, FinBERT 모듈 미설치 시 heuristic으로 자동 폴백(크래시 없음).

## 프로젝트 정체성 재확인

현재 저장소의 핵심 문서(`PROJECT_SCOPE`, `ARCHITECTURE`, `ROADMAP`, `RUNBOOK`)와 코드
(`orchestration`, `collect`, `analyze`, `output`, `app/web`)를 검토했을 때, 이 프로젝트의
정체성은 단순히 "로컬 LLM + 뉴스 요약"이 아니라 다음 3가지다:

> 1. **로컬·프라이버시 유지** — 모든 수집/임베딩/추론이 사용자 머신 내에서 완결
> 2. **근거 기반(current-run only) 환각 방지** — stale Qdrant 컨텍스트 차단, 신선한 증거만 사용
> 3. **재현 가능한 아티팩트** — `request.json`, `response.json`, `report.md`, `report.html` 4종 디스크 저장

6단계 파이프라인(Collect → Ingest → Retrieve → Infer → Analyze → Report)은 위 세 가지를
지키기 위해 존재한다. 따라서 **모든 업데이트 제안은 이 세 축을 강화**하는 것이어야 한다.

---

## P0. 프로젝트 목적에 직접 종속된 부족 요소 (지금 바로 메워야 함)

### 1. 근거 ↔ Bull/Bear 논점 트레이서빌리티

- **현재 문제**: `bull_points`, `bear_points`는 모델 출력 문자열 리스트일 뿐, 어느 `doc_id`·어느 chunk에서 나왔는지 추적 불가.
- **프로젝트 가치와의 충돌**: 핵심 가치(anti-hallucination, grounded RAG)와 **정면 배치**됨.
- **업데이트 방향**:
  - 모델 프롬프트에 `bull_points`/`bear_points` 각 항목에 `{text, evidence_doc_ids[]}` 구조 강제
  - `_OUTPUT_SCHEMA`(`ollama_adapter.py`) 스키마에 반영 + 검증
  - 응답 스키마 `Citation`에 `doc_id` 필드 추가, UI Bull/Bear 탭에 해당 근거로 점프하는 링크(Evidence 탭 아코디언 펼침)
- **기대 효과**: "이 문장의 근거가 뭐냐"에 1초 안에 답하는 리서치 도구가 됨.

### 2. 실행 히스토리 영속화 & 비교 뷰

- **현재 문제**: `data/outputs/latest_*` 파일만 존재. **매 실행마다 덮어쓰기**. 과거 AAPL 분석은 사라짐. 리서치 도구가 "시간에 따른 흐름"을 잃음.
- **업데이트 방향**:
  - `data/outputs/runs/{ticker}/{timestamp}/{request,response,collection,report}.{json,md,html}` 로 저장, `latest_*` 심링크/복사 유지
  - 경량 SQLite 인덱스 (`data/runs.db`) — ticker, question, status, sentiment, confidence, created_at
  - `/api/v1/runs?ticker=AAPL` / `/api/v1/runs/{id}` 엔드포인트
  - UI: 좌측 History를 localStorage가 아닌 서버 기반으로 승격, "AAPL 지난 5회 sentiment/confidence 변화" 미니 차트 탭 추가

### 3. Preflight을 UI가 소비 가능한 엔드포인트로 승격

- **현재 문제**: `python -m core.preflight`는 CLI 전용. 사용자는 폼 제출 후에야 `FMP entitlement_required`, `YFINANCE timeout`을 인지. 한 번의 실패 = 수 분 낭비.
- **업데이트 방향**:
  - `GET /api/v1/preflight` → Qdrant/Ollama/model pull 상태/YF/FMP/SEC 키 유효성 JSON 반환
  - UI 헤더에 조용한 상태 배지 6개 (Qdrant · Ollama · mistral:7b · YF · FMP · SEC) — 빨강이면 "Run Analysis" 비활성 + 해결 가이드 링크
  - `RUNBOOK.md`의 Failure Modes 표를 그대로 `/api/v1/runbook/failure-modes` 구조화해 UI에서 오류 배너 아래 "What to do next" 자동 제안

---

## P1. 안정성·사용성 격차 (ROADMAP이 이미 지목한 부분)

### 4. 파이프라인 실시간 스트리밍(SSE) — ROADMAP Phase 5

- **현재 문제**: UI의 6단계 진행바는 **시뮬레이션**일 뿐(고정 타이머). 실제 단계 전환을 알 수 없음. 로컬 추론이 2–3분 걸릴 때 사용자 불안 유발.
- **업데이트 방향**:
  - `POST /api/v1/research/analyze/stream` (SSE) — 각 단계 enter/exit 이벤트 + Ollama 토큰 스트림
  - `research_pipeline.py`에 이벤트 버스 추가 (`emit("stage.enter", "collect", ...)` 등, CLI 경로는 무시)
  - UI는 실제 이벤트로 진행바 칠하고, Summary 탭에 토큰 증가 렌더

### 5. 수집(Collection) TTL 캐시

- **현재 문제**: Yahoo는 이미 Rate Limited 현상(`latest_collection.json` 증거), FMP는 쿼터 있음. 동일 티커+룩백을 10분 안에 다시 돌려도 **그대로 네트워크 재히트**.
- **업데이트 방향**:
  - `data/cache/collect/{ticker}_{lookback}_{provider}.json` + `TTL=10min`(뉴스), `TTL=12h`(SEC), `TTL=6h`(transcript)
  - 캐시 적중을 `provider_results.detail`에 `source=cache, age=3m` 으로 표기 (관측성 유지)
  - UI 다이어그노스틱 테이블에 캐시 히트율 표시

### 6. 멀티 티커 / 비교 모드

- **현재 문제**: 1 티커 = 1 요청. 리서처의 실제 워크플로(동일 질문을 AAPL·MSFT·GOOGL에 적용)와 격차.
- **업데이트 방향**:
  - `POST /api/v1/research/batch` — 티커 배열 받아 병렬 실행(세마포어로 Ollama 동시성 제어)
  - UI 모드 토글 "Single / Compare". Compare는 각 KPI(Sentiment, Confidence, 증거 수)를 가로로 나란히 배치한 테이블 뷰

### 7. Watchlist + 스케줄러 (리서치 도구의 본질)

- **현재 문제**: 사용자는 매번 수동 실행. "매일 아침 내 관심 종목 10개 자동 분석" 니즈 충족 불가.
- **업데이트 방향**:
  - `data/watchlist.json` + 크론 유사 내부 스케줄러(`apscheduler`, 로컬 전용)
  - 직전 실행 대비 sentiment/confidence 변화가 임계 이상이면 `data/outputs/alerts/` 기록
  - UI: "Watchlist" 사이드 탭, 바뀐 항목에 ● 뱃지

### 8. 비용·지연 관측성 UI 노출

- **현재 문제**: `ollama_adapter.py`가 `_meta`(prompt_chars, chunks_used, retry_count, fallback_used, total_latency_s)를 **로그로만** 뱉음.
- **업데이트 방향**:
  - `AnalysisResponse`에 `execution_meta: Optional[ExecutionMeta]` 필드 추가
  - UI Diagnostics 탭에 "Inference Trace" 섹션: 모델, 프롬프트 크기, chunk 수, 재시도 횟수, 폴백 사용 여부, 각 단계 소요 시간
  - 이게 있으면 "왜 answer가 얇은가?"를 1화면에서 진단 가능

---

## P2. 플랫폼 확장 (Roadmap 이후 단계)

### 9. Pluggable Risk Engine 실장 — ROADMAP Phase 4

- 현재 `risk_analysis.py`는 키워드 `growth/catalyst/bull` 매칭에 의존. `BaseRiskEngine` 인터페이스는 이미 있음.
- **업데이트**:
  - 로컬 소형 분류기(FinBERT-tone 등) 어댑터 추가 (옵트인)
  - 환경변수 `RISK_ENGINE=heuristic|finbert` 로 전환

### 10. 소스 커버리지 확장

- 현재 뉴스 fallback 체인: YF → FMP → SEC. FMP가 entitlement_required면 SEC만 남아 `partial` 확률↑.
- **후보**: Finnhub free tier news, Alpha Vantage news/sentiment, Google News RSS (키 불필요), 기업 공식 IR RSS
- `openbb_collector.py`에 provider 플러그인 포맷 정착 (현 `PROVIDER_CHAIN` 구조를 다중 소스로)

### 11. 내보내기 포맷 다양화

- 현재 MD/HTML만. CSV(Bull/Bear+근거), PDF(보고용), JSONL(eval pipeline 연결) 확장
- UI 결과 헤더에 "Export ▾" 드롭다운

### 12. Qdrant 관리자 패널

- 현재 컬렉션 상태를 확인할 UI 없음. 장기 사용 시 오래된 임베딩 누적
- `GET /api/v1/qdrant/collection`(docs count, size), `POST /api/v1/qdrant/purge?older_than=30d`

### 13. Evaluation 대시보드

- `quality_review.py`, `evaluation_pass.py`가 이미 있는데 결과가 UI에 노출되지 않음
- `reports/latest_eval_report.md`를 새 "Quality" 탭에 실시간 렌더. 주간 트렌드 그래프

---

## 즉시 교정할 위생/작은 문제들

| 위치 | 문제 | 권장 수정 |
|---|---|---|
| `app/cli/main.py:18` | `--question` 도움말에 `pipieline` 오타 | `pipeline`으로 수정 |
| `app/cli/main.py:26`, `core/schemas/request.py:10` | `mistral/ollama/primary/fingpt/llama-2`가 **전부 같은 mistral**로 라우팅되는데 UI/CLI는 7종 선택지로 보여줌 | UI `<select>`는 `mistral(prod)`, `gemma(exp)` 2종만 노출하고, 나머지 alias는 `?experimental=true` 쿼리로 숨김. CLI는 alias 허용하되 deprecated 경고 로그 |
| `README.md` 4단계 `bootstrap_local.ps1` | 사용자 터미널에서 `py -3.11` 미발견(`No suitable Python runtime found`) 재현 | `winget install Python.Python.3.11` 또는 공식 링크 안내 추가. `scripts/run_web.ps1`에 venv 미존재 시 친절한 에러 |
| `data/outputs/latest_response.json` 한국어 conclusion 깨짐 인코딩 | PowerShell stdout만 문제지만 UI/MD는 정상. 문서에 "터미널 인코딩은 UTF-8 권장" 한 줄 |
| `legacy/`, `scratch/` 노출 | PROJECT_SCOPE에서 "엔진 경로 제외"라고 이미 명시했지만 최상위에 존재해 시각적 잡음 | `.gitignore`/문서로만 유지하거나 `archive/` 하위로 이동 |
| CORS `allow_origins=["*"]` | 로컬 프라이버시 포지셔닝과 약하게 상충 | 기본은 `http://127.0.0.1:*`로 좁히고, 명시적 옵트인만 허용 |

---

## 한 줄 우선순위 요약

1. **근거-논점 링크**, **히스토리 영속화**, **UI-연결 Preflight**
   → "로컬·근거·재현" 가치를 완성시키는 세 가지.
2. **SSE 스트리밍**, **수집 캐시**, **멀티티커**, **Watchlist**
   → 리서치 도구로서의 일상 효용.
3. **Pluggable 리스크 엔진**, **소스 확장**, **eval 대시보드**
   → ROADMAP 직접 실행.

---

## 제안 실행 순서 (참고)

다음 순서로 진행하면 상위 가치 축을 빠르게 완성하면서 UI 사용자 경험도 점진적으로 좋아진다:

1. **P0-#2 히스토리 영속화** — 백엔드 저장 구조 + `/api/v1/runs` + UI 서버 기반 history 전환
2. **P0-#1 근거 링크** — 스키마/프롬프트/UI 동시 확장 (가장 강한 가치 강화)
3. **P0-#3 Preflight 엔드포인트** — 실패 비용 즉시 감소
4. **P1-#8 실행 메타 노출** — 이미 로그로 있는 데이터만 스키마/UI로 승격
5. **P1-#5 수집 캐시** — 외부 API Rate Limit 고통 해결
6. **P1-#4 SSE 스트리밍** — 지각된 속도와 신뢰도 동시 상승
7. **P1-#6 멀티티커**, **P1-#7 Watchlist**
8. **P2** 순차 진행
