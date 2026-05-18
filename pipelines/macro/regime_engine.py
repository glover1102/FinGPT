from __future__ import annotations

from statistics import mean

from core.schemas.macro import MacroDataQuality, MacroRegime, MacroSeriesResponse, MacroSignal
from pipelines.macro.data_quality import aggregate_quality


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _latest(series: dict[str, MacroSeriesResponse], series_id: str) -> float | None:
    item = series.get(series_id)
    if not item or not item.latest or item.latest.value is None:
        return None
    return float(item.latest.value)


def _change(series: dict[str, MacroSeriesResponse], series_id: str, key: str = "change_3_period") -> float | None:
    item = series.get(series_id)
    if not item:
        return None
    value = item.changes.get(key)
    return float(value) if isinstance(value, int | float) else None


def _quality_for(series: dict[str, MacroSeriesResponse], ids: list[str]) -> MacroDataQuality:
    return aggregate_quality([series[item].data_quality for item in ids if item in series], provider="macro_signals")


def _signal(name: str, value: str, score: float, confidence: float, evidence: list[str], quality: MacroDataQuality, direction: str = "unknown") -> MacroSignal:
    return MacroSignal(
        name=name,
        value=value,
        score=round(_clamp(score), 2),
        direction=direction,
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        evidence=evidence,
        data_quality=quality,
    )


def build_macro_signals(series: dict[str, MacroSeriesResponse]) -> list[MacroSignal]:
    return [
        _growth_signal(series),
        _inflation_signal(series),
        _policy_signal(series),
        _labor_signal(series),
        _liquidity_signal(series),
        _credit_signal(series),
    ]


def _growth_signal(series: dict[str, MacroSeriesResponse]) -> MacroSignal:
    ids = ["GDPC1", "INDPRO", "RSAFS", "UMCSENT"]
    points: list[float] = []
    evidence: list[str] = []
    for sid in ["GDPC1", "INDPRO", "RSAFS"]:
        value = _latest(series, sid)
        if value is not None:
            points.append(_clamp(50 + value * 5))
            evidence.append(f"{sid} y/y {value:.2f}%")
    sentiment = _latest(series, "UMCSENT")
    if sentiment is not None:
        points.append(_clamp(50 + (sentiment - 80) * 0.7))
        evidence.append(f"UMCSENT {sentiment:.2f}")
    if not points:
        return _signal("growth_signal", "unknown", 50, 0.0, [], _quality_for(series, ids), "unknown")
    score = mean(points)
    if score >= 62:
        value = "expansion"
    elif score >= 50:
        value = "slowing_expansion"
    elif score >= 35:
        value = "contraction_risk"
    else:
        value = "recession"
    return _signal("growth_signal", value, score, len(points) / len(ids), evidence, _quality_for(series, ids), "improving" if score >= 55 else "weakening")


def _inflation_signal(series: dict[str, MacroSeriesResponse]) -> MacroSignal:
    ids = ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "T5YIE", "T10YIE", "PPIACO"]
    inflation_values = [_latest(series, sid) for sid in ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PPIACO"]]
    inflation_values = [value for value in inflation_values if value is not None]
    breakevens = [_latest(series, sid) for sid in ["T5YIE", "T10YIE"]]
    breakevens = [value for value in breakevens if value is not None]
    evidence: list[str] = []
    if inflation_values:
        avg_inflation = mean(inflation_values)
        evidence.append(f"inflation avg {avg_inflation:.2f}%")
    else:
        avg_inflation = None
    if breakevens:
        avg_breakeven = mean(breakevens)
        evidence.append(f"breakeven avg {avg_breakeven:.2f}%")
    momentum_values = [_change(series, sid) for sid in ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PPIACO"]]
    momentum_values = [value for value in momentum_values if value is not None]
    momentum = mean(momentum_values) if momentum_values else 0.0
    if avg_inflation is None and not breakevens:
        return _signal("inflation_signal", "unknown", 50, 0.0, [], _quality_for(series, ids), "unknown")
    pressure = avg_inflation if avg_inflation is not None else mean(breakevens)
    score = _clamp(35 + (pressure - 2.0) * 14 + max(momentum, 0) * 10)
    if pressure <= 2.8 and momentum <= 0:
        value = "cooling"
    elif pressure <= 4.0 and momentum <= 0.15:
        value = "sticky"
    elif momentum > 0.35:
        value = "reaccelerating"
    else:
        value = "rising"
    direction = "cooling" if momentum <= 0 else "rising"
    return _signal("inflation_signal", value, score, (len(inflation_values) + len(breakevens)) / len(ids), evidence, _quality_for(series, ids), direction)


def _policy_signal(series: dict[str, MacroSeriesResponse]) -> MacroSignal:
    ids = ["FEDFUNDS", "DGS2", "DFII10"]
    fed = _latest(series, "FEDFUNDS")
    two_year = _latest(series, "DGS2")
    real = _latest(series, "DFII10")
    points: list[float] = []
    evidence: list[str] = []
    if fed is not None:
        points.append(_clamp(35 + fed * 10))
        evidence.append(f"FEDFUNDS {fed:.2f}%")
    if two_year is not None:
        points.append(_clamp(35 + two_year * 9))
        evidence.append(f"DGS2 {two_year:.2f}%")
    if real is not None:
        points.append(_clamp(45 + real * 20))
        evidence.append(f"DFII10 {real:.2f}%")
    if not points:
        return _signal("policy_signal", "unknown", 50, 0.0, [], _quality_for(series, ids), "unknown")
    score = mean(points)
    if score >= 70:
        value = "restrictive"
    elif score <= 42:
        value = "easing"
    else:
        value = "neutral"
    return _signal("policy_signal", value, score, len(points) / len(ids), evidence, _quality_for(series, ids), value)


def _labor_signal(series: dict[str, MacroSeriesResponse]) -> MacroSignal:
    ids = ["UNRATE", "PAYEMS", "ICSA", "JTSJOL"]
    points: list[float] = []
    evidence: list[str] = []
    unrate = _latest(series, "UNRATE")
    if unrate is not None:
        points.append(_clamp(92 - unrate * 9))
        evidence.append(f"UNRATE {unrate:.2f}%")
    payroll = _latest(series, "PAYEMS")
    if payroll is not None:
        points.append(_clamp(50 + payroll * 7))
        evidence.append(f"PAYEMS y/y {payroll:.2f}%")
    claims = _latest(series, "ICSA")
    if claims is not None:
        points.append(_clamp(90 - max(0, claims - 180000) / 3500))
        evidence.append(f"ICSA {claims:.0f}")
    openings = _latest(series, "JTSJOL")
    if openings is not None:
        points.append(_clamp(30 + openings / 200000))
        evidence.append(f"JTSJOL {openings:.0f}")
    if not points:
        return _signal("labor_signal", "unknown", 50, 0.0, [], _quality_for(series, ids), "unknown")
    score = mean(points)
    if score >= 70:
        value = "strong"
    elif score >= 52:
        value = "cooling"
    elif score >= 38:
        value = "weakening"
    else:
        value = "stress"
    return _signal("labor_signal", value, score, len(points) / len(ids), evidence, _quality_for(series, ids), "weakening" if score < 52 else "stable")


def _liquidity_signal(series: dict[str, MacroSeriesResponse]) -> MacroSignal:
    ids = ["M2SL", "WALCL", "RRPONTSYD"]
    points: list[float] = []
    evidence: list[str] = []
    for sid in ["M2SL", "WALCL"]:
        value = _latest(series, sid)
        if value is not None:
            points.append(_clamp(50 + value * 4))
            evidence.append(f"{sid} y/y {value:.2f}%")
    rrp = _latest(series, "RRPONTSYD")
    if rrp is not None:
        points.append(_clamp(65 - rrp / 80))
        evidence.append(f"RRPONTSYD {rrp:.0f}")
    if not points:
        return _signal("liquidity_signal", "unknown", 50, 0.0, [], _quality_for(series, ids), "unknown")
    score = mean(points)
    if score >= 62:
        value = "easing"
    elif score <= 42:
        value = "tightening"
    else:
        value = "neutral"
    return _signal("liquidity_signal", value, score, len(points) / len(ids), evidence, _quality_for(series, ids), value)


def _credit_signal(series: dict[str, MacroSeriesResponse]) -> MacroSignal:
    ids = ["BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS"]
    hy = _latest(series, "BAMLH0A0HYM2")
    ig = _latest(series, "BAMLC0A0CM")
    vix = _latest(series, "VIXCLS")
    stress_points: list[float] = []
    evidence: list[str] = []
    if hy is not None:
        stress_points.append(_clamp((hy - 3.0) * 18, 0, 100))
        evidence.append(f"HY spread {hy:.2f}")
    if ig is not None:
        stress_points.append(_clamp((ig - 1.2) * 35, 0, 100))
        evidence.append(f"IG spread {ig:.2f}")
    if vix is not None:
        stress_points.append(_clamp((vix - 15.0) * 3.0, 0, 100))
        evidence.append(f"VIX {vix:.2f}")
    if not stress_points:
        return _signal("credit_signal", "unknown", 50, 0.0, [], _quality_for(series, ids), "unknown")
    stress = mean(stress_points)
    score = 100 - stress
    if stress >= 55:
        value = "stress"
    elif stress >= 28:
        value = "watch"
    else:
        value = "healthy"
    return _signal("credit_signal", value, score, len(stress_points) / len(ids), evidence, _quality_for(series, ids), "stress" if stress >= 28 else "healthy")


def classify_macro_regime(series: dict[str, MacroSeriesResponse], *, engine: str = "rules") -> tuple[MacroRegime, list[MacroSignal]]:
    signals = build_macro_signals(series)
    if str(engine or "rules").strip().lower() == "factor":
        return _classify_factor_regime(signals)
    signal_by_name = {signal.name: signal for signal in signals}
    available = [signal for signal in signals if signal.value != "unknown" and signal.confidence > 0]
    missing = [signal.name for signal in signals if signal.value == "unknown" or signal.confidence == 0]
    scores = {
        "growth_score": signal_by_name["growth_signal"].score,
        "inflation_score": signal_by_name["inflation_signal"].score,
        "labor_score": signal_by_name["labor_signal"].score,
        "policy_score": signal_by_name["policy_signal"].score,
        "liquidity_score": signal_by_name["liquidity_signal"].score,
        "credit_score": signal_by_name["credit_signal"].score,
    }
    if len(available) < 3:
        return (
            MacroRegime(
                name="unknown",
                display_name="Unknown",
                confidence=round(max(0.05, len(available) / 12), 3),
                risk_level="unknown",
                scores=scores,
                evidence=[item for signal in signals for item in signal.evidence[:2]],
                missing_inputs=missing,
                interpretation="Insufficient macro inputs; regime is not inferred.",
            ),
            signals,
        )

    growth = signal_by_name["growth_signal"].value
    inflation = signal_by_name["inflation_signal"].value
    labor = signal_by_name["labor_signal"].value
    policy = signal_by_name["policy_signal"].value
    credit = signal_by_name["credit_signal"].value

    name = "unknown"
    if growth in {"contraction_risk", "recession"} and labor in {"weakening", "stress"} and credit in {"watch", "stress"}:
        name = "recession_risk"
    elif growth in {"contraction_risk", "recession", "slowing_expansion"} and inflation in {"sticky", "rising", "reaccelerating"}:
        name = "stagflation"
    elif growth == "expansion" and inflation == "cooling":
        name = "goldilocks"
    elif growth in {"expansion", "slowing_expansion"} and inflation in {"rising", "reaccelerating"}:
        name = "overheating"
    elif growth in {"expansion", "slowing_expansion"} and inflation == "sticky":
        name = "reflation"
    elif growth in {"slowing_expansion", "contraction_risk"} and inflation == "cooling":
        name = "disinflation"
    elif growth in {"slowing_expansion", "expansion"} and policy == "easing":
        name = "recovery"

    risk_level = {
        "goldilocks": "low",
        "reflation": "moderate",
        "overheating": "elevated",
        "stagflation": "high",
        "disinflation": "moderate",
        "recession_risk": "high",
        "recovery": "moderate",
        "unknown": "unknown",
    }[name]
    confidence = mean([signal.confidence for signal in available])
    if name == "unknown":
        confidence = min(confidence, 0.35)
    interpretation = {
        "goldilocks": "Growth data are firm while inflation pressure is cooling.",
        "reflation": "Growth is constructive while inflation or inflation expectations are not fully subdued.",
        "overheating": "Growth is strong and inflation pressure is elevated or reaccelerating.",
        "stagflation": "Growth is weak while inflation pressure remains sticky or rising.",
        "disinflation": "Growth is slowing while inflation pressure is cooling.",
        "recession_risk": "Weak growth, softer labor, and credit stress point to elevated recession risk.",
        "recovery": "Growth is improving with easier policy conditions.",
        "unknown": "Available signals do not support a confident regime classification.",
    }[name]
    return (
        MacroRegime(
            name=name,
            display_name=name.replace("_", " ").title(),
            confidence=round(confidence, 3),
            risk_level=risk_level,
            scores=scores,
            evidence=[item for signal in signals for item in signal.evidence[:2]],
            missing_inputs=missing,
            interpretation=interpretation,
        ),
        signals,
    )


def _classify_factor_regime(signals: list[MacroSignal]) -> tuple[MacroRegime, list[MacroSignal]]:
    """Prototype-distance classifier.

    This is not a trained ML model. It is a factor-style classifier that keeps
    the regime-engine boundary pluggable while remaining auditable for MVP use.
    A future trained classifier can replace this function without changing the
    public service/API contract.
    """

    signal_by_name = {signal.name: signal for signal in signals}
    available = [signal for signal in signals if signal.value != "unknown" and signal.confidence > 0]
    missing = [signal.name for signal in signals if signal.value == "unknown" or signal.confidence == 0]
    scores = {
        "growth_score": signal_by_name["growth_signal"].score,
        "inflation_score": signal_by_name["inflation_signal"].score,
        "labor_score": signal_by_name["labor_signal"].score,
        "policy_score": signal_by_name["policy_signal"].score,
        "liquidity_score": signal_by_name["liquidity_signal"].score,
        "credit_score": signal_by_name["credit_signal"].score,
    }
    if len(available) < 3:
        return (
            MacroRegime(
                name="unknown",
                display_name="Unknown",
                confidence=round(max(0.05, len(available) / 12), 3),
                risk_level="unknown",
                scores={**scores, "classifier_engine": 1.0},
                evidence=[item for signal in signals for item in signal.evidence[:2]],
                missing_inputs=missing,
                interpretation="Insufficient macro inputs; factor regime is not inferred.",
            ),
            signals,
        )

    prototypes: dict[str, dict[str, float]] = {
        "goldilocks": {"growth_score": 72, "inflation_score": 38, "labor_score": 70, "policy_score": 52, "liquidity_score": 58, "credit_score": 78},
        "reflation": {"growth_score": 66, "inflation_score": 56, "labor_score": 62, "policy_score": 48, "liquidity_score": 64, "credit_score": 70},
        "overheating": {"growth_score": 78, "inflation_score": 74, "labor_score": 75, "policy_score": 68, "liquidity_score": 55, "credit_score": 66},
        "stagflation": {"growth_score": 34, "inflation_score": 76, "labor_score": 40, "policy_score": 68, "liquidity_score": 38, "credit_score": 42},
        "disinflation": {"growth_score": 48, "inflation_score": 36, "labor_score": 54, "policy_score": 58, "liquidity_score": 46, "credit_score": 62},
        "recession_risk": {"growth_score": 28, "inflation_score": 42, "labor_score": 32, "policy_score": 56, "liquidity_score": 34, "credit_score": 28},
        "recovery": {"growth_score": 58, "inflation_score": 44, "labor_score": 52, "policy_score": 36, "liquidity_score": 68, "credit_score": 58},
    }
    weights = {
        "growth_score": 1.25,
        "inflation_score": 1.2,
        "labor_score": 1.0,
        "policy_score": 0.8,
        "liquidity_score": 0.7,
        "credit_score": 1.1,
    }
    best_name = "unknown"
    best_distance = float("inf")
    for name, target in prototypes.items():
        weighted_distance = 0.0
        total_weight = 0.0
        for key, expected in target.items():
            weight = weights[key]
            weighted_distance += ((scores[key] - expected) ** 2) * weight
            total_weight += weight
        distance = weighted_distance / max(total_weight, 1.0)
        if distance < best_distance:
            best_name = name
            best_distance = distance

    avg_signal_confidence = mean([signal.confidence for signal in available])
    fit_confidence = max(0.0, min(1.0, 1.0 - best_distance / 1800.0))
    confidence = round(max(0.05, min(0.9, fit_confidence * avg_signal_confidence)), 3)
    if confidence < 0.25:
        best_name = "unknown"
        confidence = min(confidence, 0.24)

    risk_level = {
        "goldilocks": "low",
        "reflation": "moderate",
        "overheating": "elevated",
        "stagflation": "high",
        "disinflation": "moderate",
        "recession_risk": "high",
        "recovery": "moderate",
        "unknown": "unknown",
    }[best_name]
    interpretation = {
        "goldilocks": "Factor scores are closest to firm growth, cooling inflation, and healthy credit.",
        "reflation": "Factor scores are closest to constructive growth with moderately rising price pressure.",
        "overheating": "Factor scores are closest to strong growth and high inflation pressure.",
        "stagflation": "Factor scores are closest to weak growth with elevated inflation pressure.",
        "disinflation": "Factor scores are closest to slower growth and cooling inflation pressure.",
        "recession_risk": "Factor scores are closest to weak growth, weaker labor, and credit stress.",
        "recovery": "Factor scores are closest to improving growth with easier policy/liquidity factors.",
        "unknown": "Factor scores do not support a confident regime classification.",
    }[best_name]
    return (
        MacroRegime(
            name=best_name,
            display_name=best_name.replace("_", " ").title(),
            confidence=confidence,
            risk_level=risk_level,
            scores={**scores, "factor_distance": round(best_distance, 3)},
            evidence=[item for signal in signals for item in signal.evidence[:2]],
            missing_inputs=missing,
            interpretation=interpretation,
        ),
        signals,
    )
