from __future__ import annotations

import json
import os
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from core.config.settings import load_settings


FORECAST_INTERPRETATION_PROMPT = """System:
당신은 금융 머신러닝 예측 결과를 해석하는 정량 리서치 보조자입니다.

당신의 작업은 시스템이 제공한 구조화된 ML Forecast 결과만 사용하여 예측 결과, 신호 품질, 모델 성능, 주요 근거, 리스크, 한계를 설명하는 것입니다.

규칙:
- 가격, 수익률, 확률, 변동성, 신호 품질, 백테스트 지표를 임의로 만들지 마십시오.
- 제공된 ML output에 없는 수치를 추가하지 마십시오.
- 미래 가격을 단정하지 마십시오.
- 예측은 투자 조언이 아니라 의사결정 보조 신호임을 명확히 하십시오.
- 데이터 누수, 검증 방식, out-of-sample 성능, 모델 신뢰도, 신호 품질을 반드시 언급하십시오.
- Macro context가 제공되면 예측과 Macro 환경이 일치하는지 설명하십시오.
- 차트 요약이 제공되면 차트가 의미하는 바를 설명하십시오.
- 직접적인 매수/매도 주문을 제공하지 마십시오.
- 모델의 한계와 실패 가능성을 명확히 설명하십시오.
"""

DEFAULT_PROVIDER_MAX_LATENCY_S = 45.0

_NUMERIC_TOKEN_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?")
_DIRECT_ORDER_RE = re.compile(
    r"\b(buy|sell|short|go long|go short)\b|매수하세요|매도하세요|공매도하세요|진입하세요|청산하세요|비중을 늘리세요|비중을 줄이세요",
    re.IGNORECASE,
)


def ai_provider_health(*, timeout_s: float = 3.0) -> dict[str, Any]:
    settings = load_settings()
    model = str(settings.primary_model or "qwen2.5:7b")
    latency_policy = provider_latency_policy()
    try:
        response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=max(1.0, min(timeout_s, 10.0)))
        response.raise_for_status()
        body = response.json()
        names = {str(item.get("name") or item.get("model") or "") for item in body.get("models") or []}
        return {
            "status": "ok" if model in names else "partial",
            "provider": "ollama",
            "base_url": settings.ollama_base_url,
            "model": model,
            "model_available": model in names,
            "available_models": sorted(name for name in names if name),
            "guard_policy": "numeric_grounding_and_advisory_only",
            "latency_policy": latency_policy,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "provider": "ollama",
            "base_url": settings.ollama_base_url,
            "model": model,
            "model_available": False,
            "available_models": [],
            "error": f"{type(exc).__name__}:{exc}",
            "guard_policy": "deterministic_fallback_required",
            "latency_policy": latency_policy,
        }


def generate_ai_interpretation(payload: dict[str, Any], *, use_llm: bool = False) -> dict[str, Any]:
    # Defaulting to deterministic interpretation avoids numeric hallucination in
    # the train path. Optional provider output is accepted only after the
    # numeric-grounding and advisory-only guards pass.
    forecast = payload.get("forecast_result") or {}
    signal = payload.get("signal_result") or {}
    quality = payload.get("signal_quality") or {}
    backtest = payload.get("backtest_result") or {}
    evaluation = payload.get("model_evaluation") or {}
    leakage = payload.get("leakage_check") or {}
    explainability = payload.get("explainability") or {}
    macro = payload.get("macro_context") or {}
    visualization = payload.get("visualization_summary") or {}
    fallback = _fallback_interpretation(
        forecast=forecast,
        signal=signal,
        quality=quality,
        backtest=backtest,
        evaluation=evaluation,
        leakage=leakage,
        explainability=explainability,
        macro=macro,
        visualization=visualization,
    )
    if not use_llm:
        fallback["warnings"] = ["llm_provider_not_used_numeric_hallucination_guard_active"]
        return fallback
    try:
        content, provider, latency_s = _call_local_llm(payload)
        latency_policy = provider_latency_policy(payload)
        if latency_s > latency_policy["max_latency_s"]:
            raise TimeoutError(f"llm_latency_sla_exceeded:{latency_s}>{latency_policy['max_latency_s']}")
        ungrounded = _find_ungrounded_numeric_tokens(content, payload)
        if ungrounded:
            raise ValueError(f"ungrounded_numeric_tokens:{','.join(ungrounded)}")
        if _DIRECT_ORDER_RE.search(content):
            raise ValueError("direct_order_language_detected")
        return {
            "status": "success",
            "provider": provider,
            "prompt_template": FORECAST_INTERPRETATION_PROMPT,
            "content": content,
            "warnings": [
                f"llm_latency_s={latency_s}",
                f"llm_latency_sla_s={latency_policy['max_latency_s']}",
                "numeric_grounding_guard_passed",
                "advisory_only_guard_passed",
            ],
        }
    except Exception as exc:  # noqa: BLE001
        fallback["warnings"] = [
            "llm_provider_failed_or_rejected_output",
            f"fallback_reason:{type(exc).__name__}:{exc}",
            "numeric_hallucination_guard_fallback_active",
        ]
        return fallback


def provider_latency_policy(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = os.environ.get("FORECAST_AI_MAX_LATENCY_S")
    if payload and payload.get("max_provider_latency_s") is not None:
        raw = str(payload.get("max_provider_latency_s"))
    try:
        max_latency_s = float(raw) if raw is not None else DEFAULT_PROVIDER_MAX_LATENCY_S
    except (TypeError, ValueError):
        max_latency_s = DEFAULT_PROVIDER_MAX_LATENCY_S
    max_latency_s = max(1.0, min(max_latency_s, 180.0))
    return {
        "policy_version": "forecast_ai_provider_latency_policy_v1",
        "max_latency_s": max_latency_s,
        "fail_closed": True,
        "fallback": "deterministic_interpretation",
    }


def _fallback_interpretation(
    *,
    forecast: dict[str, Any],
    signal: dict[str, Any],
    quality: dict[str, Any],
    backtest: dict[str, Any],
    evaluation: dict[str, Any],
    leakage: dict[str, Any],
    explainability: dict[str, Any],
    macro: dict[str, Any],
    visualization: dict[str, Any],
) -> dict[str, Any]:
    confidence = forecast.get("model_confidence") or {}
    lines = [
        "1. Forecast Summary",
        f"- 대상: {forecast.get('ticker', 'unknown')} / 기준일: {forecast.get('as_of', 'unknown')} / horizon: {forecast.get('horizon', 'unknown')}",
        f"- prediction_type={forecast.get('prediction_type')}, expected_return={forecast.get('expected_return')}, probability_up={forecast.get('probability_up')}, interval=({forecast.get('p10')}, {forecast.get('p50')}, {forecast.get('p90')})",
        "2. Signal Interpretation",
        f"- signal={signal.get('signal')}, score={signal.get('signal_score')}, position_target={signal.get('position_target')}, advisory_only={signal.get('advisory_only', True)}",
        "3. Model Confidence",
        f"- confidence={confidence.get('score')} / level={confidence.get('level')}",
        "4. Signal Quality",
        f"- hit_rate={quality.get('hit_rate')}, turnover={quality.get('turnover')}, signal_count={quality.get('signal_count')}",
        "5. Key Drivers",
        f"- top_features={', '.join(str(x) for x in (explainability.get('top_features') or [])[:5]) or 'unavailable'}",
        "6. Validation Quality",
        f"- leakage_status={leakage.get('status')}, validation_folds={evaluation.get('stability_metrics', {}).get('fold_count', 'unknown')}; 실전 판단에는 out-of-sample 지표만 사용해야 합니다.",
        "7. Backtest Interpretation",
        f"- total_return={backtest.get('metrics', {}).get('total_return')}, sharpe={backtest.get('metrics', {}).get('sharpe')}, max_drawdown={backtest.get('metrics', {}).get('max_drawdown')}, cost_reflected={backtest.get('assumptions', {}).get('transaction_cost_reflected')}",
        "8. Visualization Takeaways",
        f"- chart_metadata={visualization}; 차트는 예측 경로 보장이 아니라 OOS 예측, 잔차, 신호, 비용 반영 성과를 점검하기 위한 진단 자료입니다.",
        "9. Macro Context",
        f"- macro_status={macro.get('status', 'unavailable')}; macro가 없거나 일부만 있으면 신호를 뒤집지 않고 불확실성으로 취급합니다.",
        "10. Main Risks",
        "- 데이터 부족, 최근 regime 변화, 높은 turnover, fold 성능 분산, leakage warning, 낮은 confidence가 주요 리스크입니다.",
        "11. When The Forecast May Fail",
        "- 과거 검증 구간과 다른 변동성/유동성 환경, 급격한 이벤트, stale 데이터에서는 실패할 수 있습니다.",
        "12. Portfolio / Research Usage",
        "- AI Portfolio에는 자동 리밸런싱 트리거가 아니라 advisory signal로만 전달해야 합니다.",
        "13. Bottom Line",
        "- 이 결과는 구조화된 ML output의 해석이며 직접 주문 지시가 아닙니다.",
    ]
    return {
        "status": "partial",
        "provider": "deterministic_fallback",
        "prompt_template": FORECAST_INTERPRETATION_PROMPT,
        "content": "\n".join(lines),
        "warnings": [],
    }


def _call_local_llm(payload: dict[str, Any]) -> tuple[str, str, float]:
    settings = load_settings()
    model = str(payload.get("model") or settings.primary_model or "qwen2.5:7b")
    timeout_s = max(1.0, min(float(payload.get("timeout_s") or 30.0), 90.0))
    compact = _compact_payload(payload)
    prompt = (
        FORECAST_INTERPRETATION_PROMPT
        + "\n\nSTRUCTURED_ML_OUTPUT_JSON:\n"
        + json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str)
        + "\n\n위 JSON에 있는 값만 사용해 Output 1~13 형식으로 한국어 해석을 작성하십시오. "
        + "decimal 수익률과 확률을 다른 단위의 숫자로 바꾸지 마십시오. 숫자를 언급할 때는 JSON 숫자를 그대로 복사하거나 "
        + "0.51 -> 51%, -0.03 -> -3%처럼 수학적으로 같은 percent 표현만 사용하십시오. "
        + "JSON 값이 0.01이면 0.01%라고 쓰지 마십시오. 직접 매수/매도 주문 지시는 금지합니다."
    )
    started = time.time()
    response = httpx.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "system": FORECAST_INTERPRETATION_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1200},
            "keep_alive": "5m",
        },
        timeout=timeout_s,
    )
    response.raise_for_status()
    body = response.json()
    text = str(body.get("response") or "").strip()
    if not text:
        raise ValueError("empty_llm_response")
    return text, f"ollama:{model}", round(time.time() - started, 2)


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = [
        "dataset_summary",
        "feature_summary",
        "target_config",
        "validation_result",
        "forecast_result",
        "signal_result",
        "signal_quality",
        "backtest_result",
        "model_evaluation",
        "explainability",
        "visualization_summary",
        "macro_context",
        "leakage_check",
    ]
    compact = {key: payload.get(key) for key in allowed_keys if key in payload}
    backtest = compact.get("backtest_result")
    if isinstance(backtest, dict):
        compact["backtest_result"] = {
            "status": backtest.get("status"),
            "assumptions": backtest.get("assumptions"),
            "metrics": backtest.get("metrics"),
            "cost_impact": backtest.get("cost_impact"),
        }
    validation = compact.get("validation_result")
    if isinstance(validation, dict):
        compact["validation_result"] = {
            "aggregate_metrics": validation.get("aggregate_metrics"),
            "fold_count": len(validation.get("folds") or []),
        }
    return compact


def _decimal_token(token: str) -> Decimal | None:
    value = str(token or "").strip().rstrip("%")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _numeric_token_candidates(token: str) -> set[Decimal]:
    parsed = _decimal_token(token)
    if parsed is None:
        return set()
    if str(token or "").strip().endswith("%"):
        return {parsed / Decimal("100")}
    return {parsed}


def _find_ungrounded_numeric_tokens(output: str, payload: dict[str, Any]) -> list[str]:
    prompt_numbers = set(_NUMERIC_TOKEN_RE.findall(json.dumps(_compact_payload(payload), ensure_ascii=False, default=str)))
    allowed: set[Decimal] = set()
    for token in prompt_numbers:
        allowed.update(_numeric_token_candidates(token))
    allowed = {item for item in allowed if item is not None}
    allowed.update(Decimal(item) for item in range(0, 14))
    out: list[str] = []
    for token in _NUMERIC_TOKEN_RE.findall(output or ""):
        candidates = _numeric_token_candidates(token)
        if not candidates:
            continue
        if any(abs(parsed - candidate) <= Decimal("0.0001") for parsed in candidates for candidate in allowed):
            continue
        if token not in out:
            out.append(token)
        if len(out) >= 10:
            break
    return out
