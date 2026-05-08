from __future__ import annotations

import json
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from core.config.settings import load_settings
from core.schemas.macro import MacroBriefResponse, MacroOverview
from pipelines.infer.runner_factory import resolve_model_name
from pipelines.macro.asset_impact import get_asset_impacts
from pipelines.macro.portfolio_hints import get_portfolio_policy_hint
from pipelines.macro.prompts import AI_MACRO_BRIEF_SYSTEM_PROMPT, AI_MACRO_BRIEF_TEMPLATE


def _indicator_line(item) -> str:
    latest = item.latest
    if not latest or latest.value is None:
        return f"- {item.display_name} ({item.series_id}): 사용 불가 ({item.data_quality.status})"
    return (
        f"- {item.display_name} ({item.series_id}): {latest.value:.3f} {item.unit} "
        f"기준일 {latest.date}; 품질={item.data_quality.status}; 공급자={item.provider}"
    )


def _compact_brief_payload(overview: MacroOverview) -> dict[str, Any]:
    impacts = get_asset_impacts(overview.regime, overview.signals)
    hint = get_portfolio_policy_hint(overview.regime, overview.data_quality)
    return {
        "macro_overview": {
            "as_of": overview.as_of,
            "key_indicators": [
                {
                    "series_id": item.series_id,
                    "display_name": item.display_name,
                    "category": item.category,
                    "unit": item.unit,
                    "frequency": item.frequency,
                    "provider": item.provider,
                    "latest": item.latest.model_dump(mode="json") if item.latest else None,
                    "changes": item.changes,
                    "data_quality": item.data_quality.model_dump(mode="json"),
                }
                for item in overview.key_indicators
            ],
            "data_quality": overview.data_quality.model_dump(mode="json"),
        },
        "macro_signals": [item.model_dump(mode="json") for item in overview.signals],
        "macro_regime": overview.regime.model_dump(mode="json"),
        "recent_changes": {
            item.series_id: item.changes
            for item in overview.key_indicators
            if item.changes
        },
        "asset_impact": [item.model_dump(mode="json") for item in impacts],
        "portfolio_policy_hints": hint.model_dump(mode="json"),
        "data_quality": overview.data_quality.model_dump(mode="json"),
    }


def _format_prompt(payload: dict[str, Any]) -> str:
    block = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return (
        AI_MACRO_BRIEF_TEMPLATE
        .replace("{{macro_overview}}", json.dumps(payload["macro_overview"], ensure_ascii=False, sort_keys=True, default=str))
        .replace("{{macro_signals}}", json.dumps(payload["macro_signals"], ensure_ascii=False, sort_keys=True, default=str))
        .replace("{{macro_regime}}", json.dumps(payload["macro_regime"], ensure_ascii=False, sort_keys=True, default=str))
        .replace("{{recent_changes}}", json.dumps(payload["recent_changes"], ensure_ascii=False, sort_keys=True, default=str))
        .replace("{{asset_impact}}", json.dumps(payload["asset_impact"], ensure_ascii=False, sort_keys=True, default=str))
        .replace("{{portfolio_policy_hints}}", json.dumps(payload["portfolio_policy_hints"], ensure_ascii=False, sort_keys=True, default=str))
        .replace("{{data_quality}}", json.dumps(payload["data_quality"], ensure_ascii=False, sort_keys=True, default=str))
        + "\n\nSTRICT INPUT PAYLOAD JSON:\n"
        + block
    )


_NUMERIC_TOKEN_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_CJK_IDEOGRAPH_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff]")
_MOJIBAKE_RE = re.compile(r"[�]|(?:[ìíîï][\x80-\xff]?)|(?:[êë][\x80-\xff]?)")
_DIRECT_TRADE_RE = re.compile(
    r"\b(buy|sell|short|go long|go short)\b|매수하|매도하|공매도하|롱\s*진입|숏\s*진입",
    re.IGNORECASE,
)


def _decimal_token(token: str) -> Decimal | None:
    value = str(token or "").strip().rstrip("%")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _allowed_numeric_values(text: str) -> list[Decimal]:
    values: list[Decimal] = []
    for token in _NUMERIC_TOKEN_RE.findall(text or ""):
        parsed = _decimal_token(token)
        if parsed is not None:
            values.append(parsed)
    # Section numbers and ordinary confidence bounds are allowed.
    values.extend(Decimal(item) for item in range(0, 13))
    return values


def _find_ungrounded_numeric_tokens(output: str, prompt: str) -> list[str]:
    allowed = _allowed_numeric_values(prompt)
    out: list[str] = []
    for token in _NUMERIC_TOKEN_RE.findall(output or ""):
        parsed = _decimal_token(token)
        if parsed is None:
            continue
        if any(abs(parsed - candidate) <= Decimal("0.01") for candidate in allowed):
            continue
        normalized = str(token)
        if normalized not in out:
            out.append(normalized)
        if len(out) >= 10:
            break
    return out


def _korean_language_issue(output: str) -> str:
    text = " ".join(str(output or "").split())
    if not text:
        return "Macro brief language guard rejected empty output."
    hangul = len(_HANGUL_RE.findall(text))
    cjk = len(_CJK_IDEOGRAPH_RE.findall(text))
    japanese = len(_JAPANESE_RE.findall(text))
    mojibake = len(_MOJIBAKE_RE.findall(text))
    latin_words = len(re.findall(r"\b[A-Za-z]{4,}\b", text))
    if japanese or mojibake:
        return "Macro brief language guard rejected Japanese or mojibake text."
    if cjk >= max(8, hangul):
        return "Macro brief language guard rejected Chinese/Hanja-style prose."
    if hangul < 10 and latin_words >= 8:
        return "Macro brief language guard rejected mostly non-Korean prose."
    return ""


def _call_ollama_macro_brief(*, prompt: str, model: str | None, timeout_s: float) -> tuple[str, str, float]:
    settings = load_settings()
    requested_model = str(model or "qwen").strip() or "qwen"
    try:
        resolved_model = resolve_model_name(requested_model, settings)
    except ValueError:
        if requested_model == str(settings.primary_model) or ":" in requested_model or "/" in requested_model:
            resolved_model = requested_model
        else:
            raise
    started = time.time()
    response = httpx.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        json={
            "model": resolved_model,
            "system": AI_MACRO_BRIEF_SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 1400,
                "num_ctx": 8192,
            },
            "keep_alive": "5m",
        },
        timeout=max(1.0, float(timeout_s)),
    )
    if response.status_code != 200:
        raise ConnectionError(f"Ollama macro brief returned HTTP {response.status_code}: {response.text[:200]}")
    body = response.json()
    text = str(body.get("response") or "").strip()
    if not text:
        raise ValueError("Ollama macro brief returned empty text.")
    return text, resolved_model, round(time.time() - started, 2)


def _fallback_brief(
    overview: MacroOverview,
    *,
    include_prompt: bool = False,
    extra_warnings: list[str] | None = None,
    llm_attempted: bool = False,
) -> MacroBriefResponse:
    impacts = get_asset_impacts(overview.regime, overview.signals)
    hint = get_portfolio_policy_hint(overview.regime, overview.data_quality)
    available = [item for item in overview.key_indicators if item.latest and item.latest.value is not None]
    missing = overview.data_quality.missing_series
    brief = f"""1. 현재 매크로 레짐
{overview.regime.display_name} (신뢰도 {overview.regime.confidence:.2f}, 위험 수준 {overview.regime.risk_level}). {overview.regime.interpretation}

2. 핵심 데이터 포인트
{chr(10).join(_indicator_line(item) for item in overview.key_indicators[:12]) if overview.key_indicators else "- 사용 가능한 핵심 지표가 없습니다."}

3. 최근 변화
최근 변화는 변환된 시계열 관측치에서만 계산합니다. 관측치가 없거나 부족하면 변화 값은 사용 불가로 남깁니다.

4. 인플레이션 평가
구조화된 인플레이션 지표만 기준으로 보면 현재 신호는 {next((signal.value for signal in overview.signals if signal.name == "inflation_signal"), "unknown")}입니다.

5. 성장과 고용 평가
성장 신호는 {next((signal.value for signal in overview.signals if signal.name == "growth_signal"), "unknown")}, 고용 신호는 {next((signal.value for signal in overview.signals if signal.name == "labor_signal"), "unknown")}입니다.

6. 금리 평가
정책 신호는 {next((signal.value for signal in overview.signals if signal.name == "policy_signal"), "unknown")}입니다. FRED 또는 데이터 마트 입력이 누락되면 금리 해석은 보류합니다.

7. 자산군별 시사점
{chr(10).join(f"- {item.asset_class}: {item.impact} ({item.reason})" for item in impacts[:6])}

8. 포트폴리오 리스크 메모
{hint.explanation} 이 내용은 자문용이며 AI Portfolio 정책을 변경하거나 주문을 생성하지 않습니다.

9. 추적해야 할 핵심 지표
먼저 확인해야 할 누락 또는 지연 시계열은 {", ".join([*missing, *overview.data_quality.stale_series]) or "현재 표시된 항목 없음"}입니다.

10. 결론
구조화된 매크로 데이터는 핵심 지표 {len(available)}/{len(overview.key_indicators)}개에서 사용 가능합니다. 누락되거나 오래된 데이터는 중립 신호가 아니라 증거 부족으로 처리해야 합니다.
"""
    warnings = []
    if overview.data_quality.status != "ok":
        warnings.append(f"매크로 데이터 품질={overview.data_quality.status} 상태에서 폴백 브리프를 생성했습니다.")
    warnings.append(
        "규칙 기반 폴백: 라이브 LLM을 시도했지만 수락하지 않았습니다."
        if llm_attempted
        else "규칙 기반 폴백: 라이브 LLM을 호출하지 않았습니다."
    )
    warnings.extend(extra_warnings or [])
    return MacroBriefResponse(
        status="success",
        provider="rule_based_fallback",
        is_fallback=True,
        content=brief,
        prompt_template=(AI_MACRO_BRIEF_SYSTEM_PROMPT + "\n\n" + AI_MACRO_BRIEF_TEMPLATE) if include_prompt else None,
        data_quality=overview.data_quality,
        warnings=warnings,
    )


def generate_brief(
    overview: MacroOverview,
    *,
    include_prompt: bool = False,
    use_llm: bool = False,
    model: str | None = None,
    timeout_s: float = 45.0,
) -> MacroBriefResponse:
    payload = _compact_brief_payload(overview)
    prompt = _format_prompt(payload)
    if not use_llm:
        return _fallback_brief(overview, include_prompt=include_prompt)
    try:
        content, resolved_model, latency_s = _call_ollama_macro_brief(
            prompt=prompt,
            model=model,
            timeout_s=timeout_s,
        )
        ungrounded = _find_ungrounded_numeric_tokens(content, prompt)
        if ungrounded:
            raise ValueError(
                "Macro brief grounding guard rejected ungrounded numeric token(s): "
                + ", ".join(ungrounded)
            )
        language_issue = _korean_language_issue(content)
        if language_issue:
            raise ValueError(language_issue)
        if _DIRECT_TRADE_RE.search(content):
            raise ValueError("Macro brief guard rejected direct trading language.")
        warnings = []
        if overview.data_quality.status != "ok":
            warnings.append(f"매크로 데이터 품질={overview.data_quality.status} 상태에서 LLM 브리프를 생성했습니다. 누락/지연 데이터는 여전히 불확실성입니다.")
        warnings.append("근거 검증 통과: 숫자 토큰을 구조화된 Macro payload와 대조했습니다.")
        warnings.append("자문 전용: 포트폴리오 정책을 변경하지 않았고 주문도 생성하지 않았습니다.")
        return MacroBriefResponse(
            status="success",
            provider=f"ollama:{resolved_model}",
            is_fallback=False,
            content=content,
            prompt_template=(AI_MACRO_BRIEF_SYSTEM_PROMPT + "\n\n" + prompt) if include_prompt else None,
            data_quality=overview.data_quality,
            warnings=[*warnings, f"llm_latency_s={latency_s}"],
        )
    except Exception as exc:  # noqa: BLE001
        return _fallback_brief(
            overview,
            include_prompt=include_prompt,
            extra_warnings=[f"라이브 LLM 매크로 브리프를 사용할 수 없거나 거부되어 폴백을 사용했습니다: {exc}"],
            llm_attempted=True,
        )
