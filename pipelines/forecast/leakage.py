from __future__ import annotations

from core.schemas.forecast import (
    BacktestConfig,
    DataQualityResult,
    FeatureConfig,
    LeakageCheckResult,
    TargetConfig,
    ValidationConfig,
)
from pipelines.forecast.common import now_iso


def run_leakage_check(
    *,
    feature_config: FeatureConfig,
    target_config: TargetConfig,
    validation_config: ValidationConfig,
    backtest_config: BacktestConfig,
    data_quality: DataQualityResult | None = None,
    feature_names: list[str] | None = None,
) -> LeakageCheckResult:
    issues: list[str] = []
    recommendations: list[str] = []
    method = str(validation_config.validation_method or "").lower()
    if method in {"random", "random_split", "train_test_split", "kfold", "k-fold"}:
        issues.append(f"random_or_kfold_split_not_allowed:{method}")
        recommendations.append("Use walk_forward, expanding_window, or rolling_window validation.")
    if validation_config.shuffle:
        issues.append("shuffle_true_not_allowed")
        recommendations.append("Set shuffle=false for time-series validation.")
    if int(feature_config.feature_shift or 0) < 1:
        issues.append("feature_shift_below_safe_default")
        recommendations.append("Use feature_shift=1 so close-derived features are available only from the next bar.")
    purge = validation_config.purge_window
    purge_value = int(target_config.horizon) if str(purge).lower() == "auto" else _to_int(purge)
    if purge_value < int(target_config.horizon):
        issues.append("purge_window_shorter_than_target_horizon")
        recommendations.append("Use purge_window=auto or at least the target horizon.")
    if int(validation_config.embargo_window or 0) < 1:
        issues.append("embargo_window_missing")
        recommendations.append("Use a positive embargo window to reduce overlap after test folds.")
    if int(backtest_config.execution_delay_bars or 0) < 1:
        issues.append("same_bar_execution_risk")
        recommendations.append("Use execution_delay_bars=1 or greater.")
    for name in feature_names or []:
        lower = str(name).lower()
        if lower.startswith(("target", "forward_return", "future_", "direction_", "label")):
            issues.append(f"target_like_feature_detected:{name}")
            recommendations.append("Remove target or future-looking columns from feature inputs.")
            break
    if data_quality is not None and data_quality.status == "unavailable":
        issues.append("data_quality_unavailable")
        recommendations.append("Load verified price history before training.")
    status = "pass"
    hard_fail_prefixes = (
        "random_or_kfold_split_not_allowed",
        "shuffle_true_not_allowed",
        "target_like_feature_detected",
        "same_bar_execution_risk",
        "data_quality_unavailable",
    )
    if any(any(issue.startswith(prefix) for prefix in hard_fail_prefixes) for issue in issues):
        status = "fail"
    elif issues:
        status = "warning"
    return LeakageCheckResult(
        status=status,
        issues=issues,
        recommendations=recommendations,
        checked_at=now_iso(),
    )


def _to_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
