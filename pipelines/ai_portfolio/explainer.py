from __future__ import annotations

from core.schemas.ai_portfolio import ConstraintCheck, PortfolioPolicy, PortfolioRecommendation, RebalanceSignal
from pipelines.ai_portfolio.templates import investment_type_or_none


def investment_type_explanation(investment_type_id: str) -> str:
    template = investment_type_or_none(investment_type_id)
    if not template:
        return "선택한 투자 유형 템플릿을 찾을 수 없습니다."
    ranges = template.asset_allocation_ranges
    typical = ", ".join(f"{key} {value.min:.0f}-{value.max:.0f}%" for key, value in ranges.items())
    return (
        f"요약: {template.display_name}은 {template.description}\n"
        f"적합 투자자: 권장 투자 기간은 {template.suitable_horizon}이고 위험 수준은 {template.risk_level}입니다.\n"
        f"일반 배분: {typical}.\n"
        f"주요 리스크: 목표 변동성 {template.risk_limits.target_volatility:.1f}%, "
        f"최대낙폭 경고 {template.risk_limits.max_drawdown_alert:.1f}%를 넘으면 정책 재검토가 필요합니다.\n"
        "부적합한 경우: 짧은 투자 기간, 보장 수익 기대, 정책 범위를 자주 벗어나는 재량 매매가 필요한 경우에는 맞지 않을 수 있습니다."
    )


def recommendation_explanation(
    *,
    policy: PortfolioPolicy,
    recommendation: PortfolioRecommendation,
    warnings: list[str] | None = None,
) -> str:
    warnings = list(warnings or [])
    weights = recommendation.weights
    check = recommendation.constraint_check
    top_weights = sorted(weights, key=lambda item: item.weight, reverse=True)[:5]
    allocation_text = ", ".join(f"{item.ticker} {item.weight:.2f}%" for item in top_weights) or "계산된 비중 없음"
    violations = "; ".join(item.message for item in check.violations[:5]) or "정책 위반 없음"
    metrics = recommendation.risk_metrics or {}
    backtest = recommendation.backtest_metrics or {}
    data_quality = recommendation.data_quality
    backtest_line = (
        f"백테스트 해석: 총수익률 {backtest.get('total_return_pct'):.2f}%, MDD {backtest.get('max_drawdown_pct'):.2f}%입니다."
        if isinstance(backtest.get("total_return_pct"), (int, float)) and isinstance(backtest.get("max_drawdown_pct"), (int, float))
        else "백테스트 해석: 충분한 공통 가격 이력이 없어 성과 지표는 unavailable 상태입니다."
    )
    risk_line = (
        f"리스크 평가: 예상 변동성 {metrics.get('annualized_volatility_pct'):.2f}%, Sharpe {metrics.get('sharpe'):.2f}입니다."
        if isinstance(metrics.get("annualized_volatility_pct"), (int, float))
        else "리스크 평가: 가격 데이터가 부족한 자산은 리스크 계산에서 제외되었습니다."
    )
    missing_line = (
        f"데이터 품질: 누락 자산 {', '.join(data_quality.missing_assets)}."
        if data_quality.missing_assets
        else "데이터 품질: 계산에 사용된 자산 기준으로 누락 자산은 없습니다."
    )
    fundamentals = data_quality.metadata_coverage.get("fundamentals_pct") if data_quality.metadata_coverage else None
    fundamentals_line = (
        f"재무 데이터: 정규화된 fundamentals coverage {fundamentals:.2f}%입니다."
        if isinstance(fundamentals, (int, float))
        else "재무 데이터: 정규화된 fundamentals coverage는 아직 집계되지 않았습니다."
    )
    warning_line = f"주의: {'; '.join(warnings)}" if warnings else ""
    return "\n".join(
        line
        for line in [
            f"포트폴리오 요약: {policy.portfolio_name}은 {policy.investment_type} 정책과 {policy.optimization_method} 방식으로 계산되었습니다.",
            f"배분 근거: 정량 엔진은 사용 가능한 가격 데이터와 정책 제약조건을 기준으로 비중을 산출했습니다. 상위 비중은 {allocation_text}입니다.",
            "자산별 설명: 각 자산의 역할은 자산군, 데이터 가용성, 정책상 최대 비중 한도를 기준으로 분리했습니다.",
            risk_line,
            backtest_line,
            f"제약조건: {check.status}. {violations}",
            missing_line,
            fundamentals_line,
            "최종 판단: 이 결과는 투자 조언이 아니라 사용자가 정한 정책을 검증하기 위한 의사결정 보조 정보입니다.",
            warning_line,
        ]
        if line
    )


def constraint_explanation(check: ConstraintCheck) -> str:
    if not check.violations:
        return "정책 준수 상태: pass. 현재 추천 비중은 설정된 제약조건을 충족합니다."
    lines = [f"정책 준수 상태: {check.status}."]
    for item in check.violations:
        lines.append(f"- {item.rule}: {item.message}")
    lines.append("필요 조치: fail 항목이 있으면 정책 한도 또는 추천 비중을 수정하고 다시 검증해야 합니다.")
    return "\n".join(lines)


def rebalance_explanation(signal: RebalanceSignal) -> str:
    if not signal.rebalance_required:
        return "리밸런싱 상태: 현재 비중 이탈이 정책 기준보다 작아 사용자 조치가 필요하지 않습니다."
    changes = ", ".join(
        f"{item.ticker} {item.current_weight:.2f}% -> {item.target_weight:.2f}% ({item.action})"
        for item in signal.recommended_changes[:8]
    )
    triggers = ", ".join(signal.trigger_type) or "policy_check"
    return (
        "리밸런싱 상태: 사용자 승인 대기입니다.\n"
        f"트리거: {triggers}. 이 신호는 룰 엔진이 현재 비중과 목표 비중의 차이를 계산해 생성했습니다.\n"
        f"제안 변경: {changes or '실제 변경 없음'}.\n"
        "예상 효과: 정책 목표 비중과의 이탈을 줄이는 것이 목적이며, 시장 전망만으로 새 거래를 만들지 않습니다.\n"
        "사용자 조치: 승인, 거절, 보류 중 하나를 선택해야 하며 실제 브로커 주문은 실행하지 않습니다."
    )


def report_text(policy: PortfolioPolicy, recommendation: PortfolioRecommendation | None, history: list[dict], report_type: str) -> str:
    header = f"# AI Portfolio {report_type.title()} Report\n\n"
    if not recommendation:
        return header + "아직 생성된 추천이 없어 성과 리포트를 만들 수 없습니다."
    metrics = recommendation.backtest_metrics or {}
    metric_line = (
        f"- 총수익률: {metrics.get('total_return_pct'):.2f}%\n- MDD: {metrics.get('max_drawdown_pct'):.2f}%\n"
        if isinstance(metrics.get("total_return_pct"), (int, float)) and isinstance(metrics.get("max_drawdown_pct"), (int, float))
        else "- 성과 지표: insufficient data\n"
    )
    return (
        header
        + f"정책: {policy.portfolio_name} / {policy.investment_type}\n\n"
        + metric_line
        + f"- 제약조건 상태: {recommendation.constraint_check.status}\n"
        + f"- 최근 이력 수: {len(history)}\n\n"
        + recommendation.ai_explanation
    )
