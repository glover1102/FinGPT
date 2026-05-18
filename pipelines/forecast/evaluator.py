from __future__ import annotations

import math
from typing import Any

import numpy as np

from pipelines.forecast.common import safe_div, stdev


def regression_metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    pairs = _pairs(actual, predicted)
    if not pairs:
        return {"mae": 0.0, "rmse": 0.0, "r2": 0.0, "ic": 0.0, "rank_ic": 0.0, "directional_accuracy": 0.0}
    y = np.array([item[0] for item in pairs], dtype=float)
    p = np.array([item[1] for item in pairs], dtype=float)
    err = p - y
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    ic = _corr(y, p)
    return {
        "mae": round(float(np.mean(np.abs(err))), 6),
        "rmse": round(float(np.sqrt(np.mean(err ** 2))), 6),
        "r2": round(1.0 - safe_div(ss_res, ss_tot, 1.0), 6) if ss_tot else 0.0,
        "ic": round(ic, 6),
        "rank_ic": round(_corr(_rank(y), _rank(p)), 6),
        "directional_accuracy": round(float(np.mean((y > 0) == (p > 0))), 6),
    }


def classification_metrics(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    pairs = _pairs(actual, predicted)
    if not pairs:
        return {
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "confusion_matrix": [[0, 0], [0, 0]],
        }
    y = [1 if a > 0 else 0 for a, _ in pairs]
    p = [1 if pred >= 0.5 else 0 for _, pred in pairs]
    tp = sum(1 for a, b in zip(y, p) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y, p) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(y, p) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y, p) if a == 1 and b == 0)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {
        "accuracy": round(safe_div(tp + tn, len(y)), 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "confusion_matrix": [[tn, fp], [fn, tp]],
    }


def stability_metrics(fold_metrics: list[dict[str, Any]]) -> dict[str, float]:
    directional = [float(item.get("directional_accuracy") or item.get("accuracy") or 0.0) for item in fold_metrics]
    ic_values = [float(item.get("ic") or 0.0) for item in fold_metrics]
    return {
        "fold_count": float(len(fold_metrics)),
        "directional_accuracy_mean": round(sum(directional) / len(directional), 6) if directional else 0.0,
        "directional_accuracy_dispersion": round(stdev(directional), 6),
        "ic_mean": round(sum(ic_values) / len(ic_values), 6) if ic_values else 0.0,
        "ic_dispersion": round(stdev(ic_values), 6),
    }


def overfitting_check(train_scores: list[float], test_scores: list[float]) -> dict[str, Any]:
    train_mean = sum(train_scores) / len(train_scores) if train_scores else 0.0
    test_mean = sum(test_scores) / len(test_scores) if test_scores else 0.0
    gap = train_mean - test_mean
    warnings = []
    if gap > 0.15:
        warnings.append("train_test_metric_gap_high")
    return {
        "train_metric_mean": round(train_mean, 6),
        "test_metric_mean": round(test_mean, 6),
        "gap": round(gap, 6),
        "warnings": warnings,
    }


def _pairs(actual: list[float], predicted: list[float]) -> list[tuple[float, float]]:
    pairs = []
    for a, p in zip(actual, predicted):
        if math.isfinite(float(a)) and math.isfinite(float(p)):
            pairs.append((float(a), float(p)))
    return pairs


def _corr(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2:
        return 0.0
    if float(np.std(left)) == 0.0 or float(np.std(right)) == 0.0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _rank(values: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(values)).astype(float)
