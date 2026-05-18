from __future__ import annotations

from typing import Any
from collections import defaultdict


def build_visualization_payload(
    *,
    experiment_id: str,
    model_id: str,
    ticker: str,
    price_rows: list[dict[str, Any]],
    training_result: dict[str, Any],
    backtest_result: dict[str, Any],
    feature_payload: dict[str, Any],
) -> dict[str, Any]:
    oos = training_result.get("oos_predictions") or []
    residuals = training_result.get("residuals") or []
    prices = [
        {"date": str(row.get("date") or ""), "price": row.get("price")}
        for row in price_rows
        if row.get("price") is not None
    ]
    forecast_series = [
        {
            "date": item.get("date"),
            "predicted_return": item.get("predicted_return"),
            "actual_forward_return": item.get("actual_forward_return"),
            "fold_id": item.get("fold_id"),
        }
        for item in oos
    ]
    expected = training_result.get("expected_return")
    intervals = []
    if expected is not None:
        intervals = [
            {
                "horizon_step": 1,
                "p10": training_result.get("p10"),
                "p50": training_result.get("p50"),
                "p90": training_result.get("p90"),
                "note": "Return interval, not guaranteed price path.",
            }
        ]
    return {
        "status": "success",
        "experiment_id": experiment_id,
        "model_id": model_id,
        "ticker": ticker,
        "price_series": prices,
        "forecast_series": forecast_series,
        "prediction_intervals": intervals,
        "signal_markers": backtest_result.get("signal_history") or [],
        "actual_vs_predicted": forecast_series,
        "residuals": [
            {"date": item.get("date"), "residual": round(float(residuals[idx]), 8)}
            for idx, item in enumerate(oos[: len(residuals)])
        ],
        "prediction_distribution": [item.get("predicted_return") for item in oos],
        "feature_importance": training_result.get("feature_importance") or [],
        "permutation_importance": training_result.get("permutation_importance") or [],
        "shap_importance": training_result.get("shap_importance") or [],
        "equity_curve": backtest_result.get("equity_curve") or [],
        "benchmark_curve": backtest_result.get("benchmark_curve") or [],
        "drawdown_series": backtest_result.get("drawdown_series") or [],
        "rolling_sharpe": backtest_result.get("rolling_metrics") or [],
        "signal_history": backtest_result.get("signal_history") or [],
        "position_exposure": backtest_result.get("position_history") or [],
        "turnover": [{"execution_date": item.get("execution_date"), "turnover": item.get("turnover")} for item in backtest_result.get("trades") or []],
        "monthly_return_heatmap": _monthly_returns(backtest_result.get("equity_curve") or []),
        "confusion_matrix": _confusion_matrix(oos),
        "fold_metrics": training_result.get("folds") or [],
        "regime_performance": _regime_performance(oos),
        "model_comparison": [
            {"model": training_result.get("model_name"), **(training_result.get("aggregate_metrics") or {})},
            {"model": "historical_mean_baseline", **(training_result.get("baseline_metrics") or {})},
        ],
        "data_quality_summary": feature_payload.get("summary") or {},
        "metadata": {
            "as_of": price_rows[-1].get("date") if price_rows else "unknown",
            "oos_only": True,
            "transaction_cost_reflected": bool((backtest_result.get("assumptions") or {}).get("transaction_cost_reflected")),
        },
    }


def _monthly_returns(equity_curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in equity_curve:
        date = str(row.get("date") or "")
        equity = row.get("equity")
        if len(date) >= 7 and equity is not None:
            by_month[date[:7]].append(row)
    out: list[dict[str, Any]] = []
    for month, rows in sorted(by_month.items()):
        rows = sorted(rows, key=lambda item: str(item.get("date") or ""))
        start = float(rows[0].get("equity") or 0.0)
        end = float(rows[-1].get("equity") or 0.0)
        value = (end / start - 1.0) if start else 0.0
        out.append({"month": month, "return": round(value, 8), "observations": len(rows)})
    return out


def _confusion_matrix(oos: list[dict[str, Any]]) -> dict[str, int]:
    matrix = {"true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0}
    for row in oos:
        pred = row.get("predicted_return")
        actual = row.get("actual_forward_return")
        if pred is None or actual is None:
            continue
        predicted_up = float(pred) > 0
        actual_up = float(actual) > 0
        if predicted_up and actual_up:
            matrix["true_positive"] += 1
        elif not predicted_up and not actual_up:
            matrix["true_negative"] += 1
        elif predicted_up and not actual_up:
            matrix["false_positive"] += 1
        else:
            matrix["false_negative"] += 1
    return matrix


def _regime_performance(oos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = {"up_market": [], "down_market": [], "flat_market": []}
    for row in oos:
        actual = row.get("actual_forward_return")
        pred = row.get("predicted_return")
        if actual is None or pred is None:
            continue
        actual_value = float(actual)
        regime = "flat_market"
        if actual_value > 0.005:
            regime = "up_market"
        elif actual_value < -0.005:
            regime = "down_market"
        buckets[regime].append(float(pred) if actual_value > 0 else -float(pred))
    out: list[dict[str, Any]] = []
    for regime, scores in buckets.items():
        if not scores:
            out.append({"regime": regime, "observations": 0, "directional_score": None, "source": "realized_forward_return_proxy"})
            continue
        out.append(
            {
                "regime": regime,
                "observations": len(scores),
                "directional_score": round(sum(1 for score in scores if score > 0) / len(scores), 6),
                "average_signed_prediction": round(sum(scores) / len(scores), 8),
                "source": "realized_forward_return_proxy",
            }
        )
    return out
