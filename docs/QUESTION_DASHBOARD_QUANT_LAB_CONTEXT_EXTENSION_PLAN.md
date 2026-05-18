# 질의 답변을 대시보드와 Quant Lab으로 확장하는 실행 계획

## 범위

이번 단계에서는 `textarea#question` UI 자체는 변경하지 않는다. 입력창은 그대로 두고, 질의 실행 시점에 현재 대시보드와 Quant Lab 상태를 백엔드에 함께 전달하는 구조를 설계한다. 목표는 사용자가 "현재 시장이 무시하는 리스크는 무엇인가요?" 같은 질문을 했을 때 가격, 히트맵, 데이터 마트, 팩터, 신호, 백테스트, 포트폴리오 결과를 근거로 답변 품질을 높이는 것이다.

## 현재 연결 지점

- 프론트엔드 입력: `app/web/index.html`의 `textarea#question`
- 질의 실행 로직: `app/web/app.js`의 `runAnalysis`, `runStreamAnalysis`
- 리서치 API: `POST /api/v1/research/universal`, `POST /api/v1/research/universal/stream`
- 시장 대시보드 데이터: `GET /api/v1/dashboard/market`, `GET /api/v1/dashboard/equity-heatmap`, `GET /api/v1/data/health`
- Quant Lab 데이터: `POST /api/v1/quant/features/preview`, `POST /api/v1/quant/signals/generate`, `POST /api/v1/quant/backtest`, `GET /api/v1/quant/backtests`
- 저장 가격: `GET /api/v1/data/prices/{ticker}`

## 제안 계약

리서치 요청에 선택 필드 `context_snapshot`을 추가한다.

```json
{
  "ticker": "SPY",
  "question": "현재 시장이 무시하는 리스크는 무엇인가요?",
  "context_snapshot": {
    "source": "ui_dashboard_quant_lab_v1",
    "captured_at": "2026-05-06T00:00:00Z",
    "dashboard": {
      "market_items": [],
      "heatmap": {
        "latest_as_of": "2026-05-05T15:15:00Z",
        "top_up": [],
        "top_down": [],
        "sector_breadth": []
      },
      "data_health": {
        "decision_status": "ok",
        "table_counts": {},
        "covered_empty_provider_rows": 0
      }
    },
    "quant_lab": {
      "asset_detail": {},
      "features_preview": {},
      "signals": {},
      "latest_backtest": {},
      "portfolio": {}
    },
    "limits": {
      "max_items_per_section": 8,
      "max_serialized_bytes": 12000
    }
  }
}
```

## 프론트엔드 구현 단계

1. `app/web/app.js`에 `buildDashboardContextSnapshot()`을 추가한다.
2. 이 함수는 화면에 이미 로드된 상태를 우선 사용하고, 비어 있으면 가벼운 API만 호출한다.
3. 수집 대상은 `state.lastAssetDetail`, `state.lastQuantFeaturePreview`, `state.lastQuantSignalResult`, `state.lastQuantBacktestResult`, `state.lastPortfolioResult`처럼 명시적인 상태 슬롯으로 분리한다.
4. 히트맵은 전체 200개 이상을 보내지 않고 상승 상위 8개, 하락 상위 8개, 섹터별 가중 평균과 breadth만 보낸다.
5. 데이터 마트 상태는 `decision_status`, `table_counts`, 최근 실패/보강 provider만 보낸다.
6. `runAnalysis`에서 `payload.context_snapshot = await buildDashboardContextSnapshot(payload)`를 붙인다.
7. 스트리밍 요청도 동일한 payload를 사용해 일반 실행과 결과 차이를 없앤다.

## 백엔드 구현 단계

1. `core/schemas` 또는 현재 리서치 요청 모델에 `ContextSnapshot`, `DashboardSnapshot`, `QuantLabSnapshot` 타입을 추가한다.
2. `app/api/routers/research.py`에서 기존 요청을 깨지 않도록 `context_snapshot: dict[str, Any] | None = None` 형태로 받는다.
3. `pipelines/orchestration` 아래에 `dashboard_context_adapter.py`를 추가한다.
4. adapter는 원본 JSON을 그대로 프롬프트에 붙이지 않고 다음 섹션으로 압축한다.
   - 시장 요약: 지수, 히트맵 breadth, 상하위 종목
   - 데이터 신선도: 정상/부분/실패, stale 또는 보강 empty
   - Quant 근거: 팩터, 신호, 백테스트 성과, MDD, 벤치마크 대비
   - 포트폴리오: 비중, 위험기여도, 집중도, 제약 위반
5. 리서치 프롬프트에는 "화면 컨텍스트는 보조 근거이며, 날짜와 신선도를 명시하고 stale 데이터는 결론 강도를 낮춰라"는 규칙을 넣는다.
6. 답변에는 "대시보드 근거", "Quant Lab 근거", "주의할 데이터 한계" 섹션을 생성한다.

## 답변 품질 규칙

- 가격/수익률/백테스트 수치는 날짜와 기준 소스를 함께 언급한다.
- 히트맵은 장중 5분봉이므로 장 마감 후에는 "장중 스냅샷"으로만 표현한다.
- 백테스트 결과는 미래 성과 보장이 아니라 전략 조건 검증으로 설명한다.
- `data_health.decision_status !== "ok"`이면 답변 첫 부분에 데이터 한계를 먼저 표시한다.
- `covered_empty_provider_rows > 0`이면 "일부 provider empty는 적용 대상 아님으로 정상 처리됨"을 짧게 표시한다.
- 질의 대상 티커와 Quant Lab universe가 다르면 그 차이를 명시한다.

## 검증 계획

1. 단위 테스트: context snapshot 압축 함수가 최대 항목 수와 최대 바이트를 지키는지 확인한다.
2. API 테스트: `context_snapshot`이 없을 때 기존 리서치 요청이 그대로 통과하는지 확인한다.
3. API 테스트: `context_snapshot`이 있을 때 프롬프트/trace에 `dashboard_context`가 포함되는지 확인한다.
4. UI 계약 테스트: `textarea#question` 마크업이 바뀌지 않았고, payload에만 context가 추가되는지 확인한다.
5. 브라우저 테스트: Quant Lab에서 백테스트 실행 후 질문을 실행했을 때 답변에 백테스트/MDD/벤치마크 근거가 표시되는지 확인한다.
6. 회귀 테스트: `python scripts/check_ui_contract.py`, `python -m pytest tests/test_data_mart_api.py tests/test_ui_routing_contract.py -q`, `python scripts/quant_lab_ui_smoke.py --base-url http://127.0.0.1:8002 --timeout-s 240 --browser-use-status passed`.

## 단계별 릴리스

1. 1단계: 타입과 payload만 추가하고, 백엔드는 trace에만 저장한다.
2. 2단계: 프롬프트 압축 adapter를 붙이고 답변 섹션을 생성한다.
3. 3단계: 브라우저 UI에서 "화면 컨텍스트 사용됨" 진단 chip을 결과 패널에 추가한다.
4. 4단계: 사용자가 원할 때만 특정 Quant Lab run을 고정해 질문에 연결하는 run pin 기능을 추가한다.
5. 5단계: context snapshot을 `runs.db`에 저장해 동일 질문 재현과 감사 추적을 지원한다.

## 완료 기준

- 입력창 마크업 변경 없이 기존 질문 실행이 동작한다.
- context가 없는 요청은 완전한 하위 호환성을 유지한다.
- context가 있는 요청은 날짜, 신선도, 수치 출처를 답변에 반영한다.
- 장중 히트맵, 데이터 마트, Quant Lab 결과가 서로 충돌할 때 답변이 충돌을 숨기지 않고 표시한다.
- 브라우저에서 실제 질문 실행 결과가 한국어 중심으로 표시된다.
