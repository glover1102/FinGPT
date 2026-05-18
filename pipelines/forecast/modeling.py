from __future__ import annotations

import warnings
from typing import Any

import numpy as np

from core.schemas.forecast import ModelConfig, TargetConfig, ValidationConfig
from pipelines.forecast.common import finite_float, mean, percentile, stable_hash, stdev
from pipelines.forecast.evaluator import classification_metrics, overfitting_check, regression_metrics, stability_metrics
from pipelines.forecast.validation import create_purged_combinatorial_splits, create_walk_forward_splits

_DEEP_SEQUENCE_MODELS = {"lstm", "gru", "temporal_cnn", "transformer", "temporal_fusion_transformer"}


def available_models() -> dict[str, Any]:
    sklearn_available = _sklearn_available()
    torch_available = _module_available("torch")
    return {
        "status": "success",
        "models": [
            {"model_name": "historical_mean", "model_type": "baseline", "available": True},
            {"model_name": "zero_return", "model_type": "baseline", "available": True},
            {"model_name": "momentum_rule", "model_type": "baseline", "available": True},
            {"model_name": "ridge_regression", "model_type": "regression", "available": sklearn_available},
            {"model_name": "random_forest_regressor", "model_type": "regression", "available": sklearn_available},
            {"model_name": "gradient_boosting_regressor", "model_type": "regression", "available": sklearn_available},
            {"model_name": "logistic_regression", "model_type": "classification", "available": sklearn_available},
            {"model_name": "random_forest_classifier", "model_type": "classification", "available": sklearn_available},
            {"model_name": "gradient_boosting_classifier", "model_type": "classification", "available": sklearn_available},
            {"model_name": "xgboost", "model_type": "optional", "available": _module_available("xgboost")},
            {"model_name": "lightgbm", "model_type": "optional", "available": _module_available("lightgbm")},
            {"model_name": "lstm", "model_type": "deep_sequence", "available": torch_available, "optional_dependency": "torch"},
            {"model_name": "gru", "model_type": "deep_sequence", "available": torch_available, "optional_dependency": "torch"},
            {"model_name": "temporal_cnn", "model_type": "deep_sequence", "available": torch_available, "optional_dependency": "torch"},
            {"model_name": "transformer", "model_type": "deep_sequence", "available": torch_available, "optional_dependency": "torch"},
            {"model_name": "temporal_fusion_transformer", "model_type": "deep_sequence", "available": torch_available, "optional_dependency": "torch"},
        ],
    }


def train_and_forecast(
    aligned_rows: list[dict[str, Any]],
    latest_row: dict[str, Any] | None,
    feature_names: list[str],
    *,
    target_config: TargetConfig,
    validation_config: ValidationConfig,
    model_config: ModelConfig,
) -> dict[str, Any]:
    trainable = [row for row in aligned_rows if row.get("is_trainable")]
    if len(trainable) < 40:
        return {"status": "failed", "errors": ["insufficient_trainable_rows"], "warnings": []}
    dates = [row["date"] for row in trainable]
    folds, split_warnings = create_walk_forward_splits(dates, validation_config, target_config)
    if not folds:
        return {"status": "failed", "errors": ["walk_forward_split_unavailable"], "warnings": split_warnings}
    x = np.array([_feature_vector(row, feature_names) for row in trainable], dtype=float)
    y = np.array([float(row.get("target")) for row in trainable], dtype=float)
    forward = np.array([float(row.get("forward_return") or row.get("target") or 0.0) for row in trainable], dtype=float)
    if np.isnan(x).any() or np.isnan(y).any():
        mask = ~(np.isnan(x).any(axis=1) | np.isnan(y))
        x = x[mask]
        y = y[mask]
        forward = forward[mask]
        dates = [date for date, keep in zip(dates, mask.tolist()) if keep]
        trainable = [row for row, keep in zip(trainable, mask.tolist()) if keep]
    if len(y) < 40:
        return {"status": "failed", "errors": ["insufficient_complete_feature_target_rows"], "warnings": split_warnings}

    model_name = str(model_config.model_name or "ridge_regression").lower()
    target_type = _target_type(target_config)
    task = "classification" if _classification_target(target_type) or model_name.endswith("classifier") or model_name == "logistic_regression" else "regression"
    return_target = _return_target(target_type) and task != "classification"
    volatility_target = target_type == "volatility" and task != "classification"
    fold_payloads: list[dict[str, Any]] = []
    oos_predictions: list[dict[str, Any]] = []
    fold_metrics: list[dict[str, Any]] = []
    train_scores: list[float] = []
    test_scores: list[float] = []
    residuals: list[float] = []

    for fold in folds:
        if fold.test_end > len(y):
            continue
        model = _fit_model(x[fold.train_start:fold.train_end], y[fold.train_start:fold.train_end], model_name, task, model_config)
        if model.get("status") != "success":
            return model
        train_pred = _predict(model, x[fold.train_start:fold.train_end], task)
        test_pred = _predict(model, x[fold.test_start:fold.test_end], task)
        actual = y[fold.test_start:fold.test_end].tolist()
        target_actual = y[fold.test_start:fold.test_end].tolist()
        if task == "classification":
            metrics = classification_metrics(actual, test_pred)
            train_metric = classification_metrics(y[fold.train_start:fold.train_end].tolist(), train_pred)["accuracy"]
            test_metric = metrics["accuracy"]
        else:
            metrics = regression_metrics(target_actual, test_pred)
            train_metric = regression_metrics(y[fold.train_start:fold.train_end].tolist(), train_pred)["directional_accuracy"]
            test_metric = metrics["directional_accuracy"]
        fold_metrics.append(metrics)
        train_scores.append(float(train_metric))
        test_scores.append(float(test_metric))
        fold_payloads.append({**fold.as_dict(dates), "metrics": metrics})
        for idx, pred in enumerate(test_pred):
            absolute_idx = fold.test_start + idx
            actual_target_value = float(y[absolute_idx])
            actual_forward_value = float(forward[absolute_idx])
            pred_return = float(pred) if return_target else None
            if pred_return is not None:
                residuals.append(actual_target_value - pred_return)
            oos_predictions.append(
                {
                    "date": dates[absolute_idx],
                    "prediction": round(float(pred), 8),
                    "predicted_return": None if pred_return is None else round(float(pred_return), 8),
                    "actual": round(float(y[absolute_idx]), 8),
                    "actual_target": round(actual_target_value, 8),
                    "actual_forward_return": round(actual_forward_value, 8),
                    "fold_id": fold.fold_id,
                    "oos": True,
                }
            )

    return_calibration: dict[str, Any] = {}
    probability_calibration: dict[str, Any] = {}
    if task == "classification":
        probability_calibration = _classification_probability_calibration(oos_predictions)
        return_calibration = _classification_return_calibration(oos_predictions)
        residuals = []
        for item in oos_predictions:
            raw_probability = item.get("prediction")
            calibrated_probability = _apply_probability_calibration(raw_probability, probability_calibration)
            item["raw_probability_up"] = raw_probability
            item["calibrated_probability_up"] = None if calibrated_probability is None else round(calibrated_probability, 8)
            item["prediction"] = None if calibrated_probability is None else round(calibrated_probability, 8)
            item["probability_calibration"] = probability_calibration
            pred_return = _calibrated_return(calibrated_probability, return_calibration)
            item["predicted_return"] = None if pred_return is None else round(pred_return, 8)
            item["return_calibration"] = return_calibration
            actual_forward = item.get("actual_forward_return")
            if pred_return is not None and actual_forward is not None:
                residuals.append(float(actual_forward) - pred_return)

    final_model = _fit_model(x, y, model_name, task, model_config)
    if final_model.get("status") != "success":
        return final_model
    latest_features = _latest_vector(latest_row, feature_names)
    latest_prediction = None
    latest_prediction_raw = None
    if latest_features is not None:
        latest_prediction = _predict(final_model, np.array([latest_features], dtype=float), task)[0]
    if task == "classification":
        latest_prediction_raw = latest_prediction
        latest_prediction = _apply_probability_calibration(latest_prediction_raw, probability_calibration)
        expected_return = _calibrated_return(latest_prediction, return_calibration)
    elif volatility_target:
        latest_prediction_raw = latest_prediction
        expected_return = None
    else:
        latest_prediction_raw = latest_prediction
        expected_return = _prediction_to_return(latest_prediction, task) if latest_prediction is not None else None
    probability_up = _probability_up(latest_prediction, expected_return, residuals, task, target_type=target_type)
    aggregate = _aggregate_metrics(fold_metrics, task)
    purged_cv = _run_purged_cv_diagnostic(
        x=x,
        y=y,
        dates=dates,
        target_config=target_config,
        validation_config=validation_config,
        model_name=model_name,
        task=task,
        model_config=model_config,
    )
    stability = stability_metrics(fold_metrics)
    if purged_cv.get("status") == "success":
        stability["purged_cv_fold_count"] = float(purged_cv.get("fold_count") or 0)
        stability["purged_cv_directional_accuracy"] = finite_float((purged_cv.get("aggregate_metrics") or {}).get("directional_accuracy"), 0.0) or 0.0
    baseline = _baseline_metrics(y.tolist(), oos_predictions, task)
    importances = _feature_importance(final_model, feature_names, x, y)
    permutation_importances = _permutation_importance(final_model, feature_names, x, y, task, seed=int(model_config.seed or 42))
    shap_payload = _shap_importance(final_model, feature_names, x)
    unavailable_explainers = []
    if shap_payload.get("status") != "success":
        unavailable_explainers.append("shap")
    predicted_returns = [float(p["predicted_return"]) for p in oos_predictions if p.get("predicted_return") is not None]
    forecast_volatility = None
    if volatility_target and latest_prediction is not None:
        forecast_volatility = round(float(latest_prediction), 8)
    elif oos_predictions:
        forecast_volatility = round(stdev([p["actual_forward_return"] for p in oos_predictions]) * (252 ** 0.5), 8)
    interval = _conformal_interval(expected_return, residuals, volatility_target=volatility_target)
    return {
        "status": "success",
        "task": task,
        "target_type": target_type,
        "model_name": model_name,
        "model_id": f"mlf_{stable_hash({'model': model_name, 'features': feature_names, 'target': target_config.model_dump(mode='json')})}",
        "feature_set_hash": stable_hash(feature_names),
        "training_period": {"start": dates[0], "end": dates[-1]},
        "folds": fold_payloads,
        "fold_metrics": fold_metrics,
        "aggregate_metrics": aggregate,
        "baseline_metrics": baseline,
        "stability_metrics": stability,
        "purged_combinatorial_cv": purged_cv,
        "overfitting_check": overfitting_check(train_scores, test_scores),
        "oos_predictions": oos_predictions,
        "residuals": residuals,
        "latest_prediction": None if latest_prediction is None else round(float(latest_prediction), 8),
        "latest_prediction_raw": None if latest_prediction_raw is None else round(float(latest_prediction_raw), 8),
        "return_calibration": return_calibration,
        "probability_calibration": probability_calibration,
        "expected_return": None if expected_return is None else round(float(expected_return), 8),
        "median_return": None if not predicted_returns else round(float(percentile(predicted_returns, 0.5) or 0.0), 8),
        "probability_up": probability_up,
        "probability_down": None if probability_up is None else round(1.0 - probability_up, 6),
        "p10": interval.get("p10"),
        "p50": interval.get("p50"),
        "p90": interval.get("p90"),
        "forecast_volatility": forecast_volatility,
        "prediction_interval_method": interval.get("method"),
        "conformal_interval": interval,
        "feature_importance": importances,
        "permutation_importance": permutation_importances,
        "shap_importance": shap_payload.get("items") or [],
        "unavailable_explainers": unavailable_explainers,
        "explainability_warnings": shap_payload.get("warnings") or [],
        "warnings": split_warnings + list(purged_cv.get("warnings") or []) + (["selected_model_underperformed_baseline"] if _underperformed(aggregate, baseline) else []),
    }


def _run_purged_cv_diagnostic(
    *,
    x: np.ndarray,
    y: np.ndarray,
    dates: list[str],
    target_config: TargetConfig,
    validation_config: ValidationConfig,
    model_name: str,
    task: str,
    model_config: ModelConfig,
) -> dict[str, Any]:
    method = str(validation_config.validation_method or "").lower()
    if method not in {"purged_combinatorial_cv", "combinatorial_purged_cv", "walk_forward_plus_purged_cv"}:
        return {"status": "not_requested", "warnings": []}
    folds, warnings_ = create_purged_combinatorial_splits(dates, validation_config, target_config)
    if not folds:
        return {"status": "partial", "folds": [], "fold_count": 0, "warnings": warnings_}
    fold_payloads: list[dict[str, Any]] = []
    fold_metrics: list[dict[str, Any]] = []
    for fold in folds:
        train_idx = np.array(fold.train_indices, dtype=int)
        test_idx = np.array(fold.test_indices, dtype=int)
        model = _fit_model(x[train_idx], y[train_idx], model_name, task, model_config)
        if model.get("status") != "success":
            return {"status": "failed", "folds": fold_payloads, "fold_count": len(fold_payloads), "warnings": warnings_, "errors": model.get("errors") or ["purged_cv_model_failed"]}
        test_pred = _predict(model, x[test_idx], task)
        actual = y[test_idx].tolist()
        metrics = classification_metrics(actual, test_pred) if task == "classification" else regression_metrics(actual, test_pred)
        fold_metrics.append(metrics)
        fold_payloads.append({**fold.as_dict(dates), "metrics": metrics})
    return {
        "status": "success",
        "method": "purged_combinatorial_cv",
        "folds": fold_payloads,
        "fold_count": len(fold_payloads),
        "aggregate_metrics": _aggregate_metrics(fold_metrics, task),
        "warnings": warnings_,
    }


def _feature_vector(row: dict[str, Any], feature_names: list[str]) -> list[float]:
    features = row.get("features") or {}
    return [float(features.get(name)) for name in feature_names]


def _latest_vector(row: dict[str, Any] | None, feature_names: list[str]) -> list[float] | None:
    if not row:
        return None
    features = row.get("features") or {}
    values = []
    for name in feature_names:
        value = finite_float(features.get(name))
        if value is None:
            return None
        values.append(value)
    return values


def _fit_model(x: np.ndarray, y: np.ndarray, model_name: str, task: str, model_config: ModelConfig) -> dict[str, Any]:
    if model_name == "zero_return":
        return {"status": "success", "kind": "constant", "value": 0.0}
    if model_name == "historical_mean":
        return {"status": "success", "kind": "constant", "value": float(np.nanmean(y))}
    if model_name == "momentum_rule":
        return {"status": "success", "kind": "momentum_rule", "last_col": -1}
    if model_name in _DEEP_SEQUENCE_MODELS:
        return _fit_torch_sequence_model(x, y, model_name, task, model_config)
    if not _sklearn_available():
        return {"status": "failed", "errors": [f"model_unavailable:{model_name}:sklearn_missing"], "warnings": []}
    try:
        from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
        from sklearn.linear_model import LogisticRegression, Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "errors": [f"model_import_failed:{exc}"], "warnings": []}
    seed = int(model_config.seed or 42)
    params = dict(model_config.hyperparameters or {})
    if model_name == "ridge_regression":
        estimator = Ridge(alpha=float(params.get("alpha", 1.0)), random_state=seed)
    elif model_name == "random_forest_regressor":
        estimator = RandomForestRegressor(n_estimators=int(params.get("n_estimators", 80)), max_depth=params.get("max_depth", 5), random_state=seed)
    elif model_name == "gradient_boosting_regressor":
        estimator = GradientBoostingRegressor(random_state=seed)
    elif model_name == "logistic_regression":
        estimator = LogisticRegression(max_iter=1000, random_state=seed)
    elif model_name == "random_forest_classifier":
        estimator = RandomForestClassifier(n_estimators=int(params.get("n_estimators", 80)), max_depth=params.get("max_depth", 5), random_state=seed)
    elif model_name == "gradient_boosting_classifier":
        estimator = GradientBoostingClassifier(random_state=seed)
    elif model_name == "xgboost":
        estimator = _optional_xgboost_estimator(task, params, seed)
        if estimator.get("status") != "success":
            return estimator
        estimator = estimator["estimator"]
    elif model_name == "lightgbm":
        estimator = _optional_lightgbm_estimator(task, params, seed)
        if estimator.get("status") != "success":
            return estimator
        estimator = estimator["estimator"]
    else:
        return {"status": "failed", "errors": [f"model_unavailable:{model_name}"], "warnings": []}
    y_fit = (y > 0).astype(int) if task == "classification" else y
    estimator_to_fit = make_pipeline(StandardScaler(), estimator) if model_config.scaling and model_name in {"ridge_regression", "logistic_regression"} else estimator
    try:
        estimator_to_fit.fit(x, y_fit)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "errors": [f"model_training_failed:{exc}"], "warnings": []}
    return {"status": "success", "kind": "sklearn", "estimator": estimator_to_fit, "model_name": model_name}


def _optional_xgboost_estimator(task: str, params: dict[str, Any], seed: int) -> dict[str, Any]:
    try:
        from xgboost import XGBClassifier, XGBRegressor  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "errors": [f"model_unavailable:xgboost:{type(exc).__name__}"], "warnings": []}
    common = {
        "n_estimators": int(params.get("n_estimators", 120)),
        "max_depth": int(params.get("max_depth", 3)),
        "learning_rate": float(params.get("learning_rate", 0.05)),
        "subsample": float(params.get("subsample", 0.9)),
        "colsample_bytree": float(params.get("colsample_bytree", 0.9)),
        "random_state": seed,
        "n_jobs": int(params.get("n_jobs", 1)),
        "verbosity": 0,
    }
    if task == "classification":
        return {"status": "success", "estimator": XGBClassifier(**common, eval_metric="logloss")}
    return {"status": "success", "estimator": XGBRegressor(**common)}


def _optional_lightgbm_estimator(task: str, params: dict[str, Any], seed: int) -> dict[str, Any]:
    try:
        from lightgbm import LGBMClassifier, LGBMRegressor  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "errors": [f"model_unavailable:lightgbm:{type(exc).__name__}"], "warnings": []}
    common = {
        "n_estimators": int(params.get("n_estimators", 120)),
        "max_depth": int(params.get("max_depth", -1)),
        "learning_rate": float(params.get("learning_rate", 0.05)),
        "subsample": float(params.get("subsample", 0.9)),
        "colsample_bytree": float(params.get("colsample_bytree", 0.9)),
        "random_state": seed,
        "n_jobs": int(params.get("n_jobs", 1)),
        "verbose": -1,
    }
    if task == "classification":
        return {"status": "success", "estimator": LGBMClassifier(**common)}
    return {"status": "success", "estimator": LGBMRegressor(**common)}


def _fit_torch_sequence_model(x: np.ndarray, y: np.ndarray, model_name: str, task: str, model_config: ModelConfig) -> dict[str, Any]:
    try:
        import torch  # type: ignore
        from torch import nn  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "errors": [f"model_unavailable:{model_name}:torch_missing:{type(exc).__name__}"], "warnings": []}
    if len(x) < 40:
        return {"status": "failed", "errors": [f"model_training_failed:{model_name}:insufficient_sequence_rows"], "warnings": []}
    params = dict(model_config.hyperparameters or {})
    seed = int(model_config.seed or 42)
    torch.manual_seed(seed)
    try:
        torch.set_num_threads(int(params.get("torch_num_threads", 1)))
    except Exception:  # noqa: BLE001
        pass
    lookback = max(2, min(int(params.get("lookback", 10)), 63, len(x)))
    hidden_dim = max(4, min(int(params.get("hidden_dim", 16)), 128))
    epochs = max(1, min(int(params.get("epochs", 18)), 200))
    batch_size = max(8, min(int(params.get("batch_size", 64)), 512))
    learning_rate = max(1e-5, min(float(params.get("learning_rate", 0.01)), 0.5))
    x_train = np.asarray(x, dtype=np.float32)
    feature_mean = np.nanmean(x_train, axis=0).astype(np.float32)
    feature_std = np.nanstd(x_train, axis=0).astype(np.float32)
    feature_std[feature_std < 1e-8] = 1.0
    x_scaled = (x_train - feature_mean) / feature_std
    sequences = _sequence_windows(x_scaled, lookback)
    target_values = (y > 0).astype(np.float32) if task == "classification" else np.asarray(y, dtype=np.float32)
    y_tensor = torch.from_numpy(target_values.reshape(-1, 1))
    x_tensor = torch.from_numpy(sequences)
    network = _build_torch_sequence_network(
        model_name,
        input_dim=x.shape[1],
        hidden_dim=hidden_dim,
        nn_module=nn,
        params=params,
    )
    loss_fn = nn.BCEWithLogitsLoss() if task == "classification" else nn.MSELoss()
    optimizer = torch.optim.AdamW(network.parameters(), lr=learning_rate, weight_decay=float(params.get("weight_decay", 1e-4)))
    indices = np.arange(len(x_tensor))
    rng = np.random.default_rng(seed)
    try:
        network.train()
        for _ in range(epochs):
            rng.shuffle(indices)
            for start in range(0, len(indices), batch_size):
                batch_idx = indices[start:start + batch_size]
                batch_x = x_tensor[batch_idx]
                batch_y = y_tensor[batch_idx]
                optimizer.zero_grad(set_to_none=True)
                predictions = network(batch_x)
                loss = loss_fn(predictions, batch_y)
                if not bool(torch.isfinite(loss)):
                    return {"status": "failed", "errors": [f"model_training_failed:{model_name}:non_finite_loss"], "warnings": []}
                loss.backward()
                optimizer.step()
        network.eval()
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "errors": [f"model_training_failed:{model_name}:{type(exc).__name__}"], "warnings": []}
    return {
        "status": "success",
        "kind": "torch_sequence",
        "network": network,
        "model_name": model_name,
        "task": task,
        "lookback": lookback,
        "feature_mean": feature_mean,
        "feature_std": feature_std,
        "training_backend": "torch",
        "warnings": ["deep_sequence_model_trained_with_lightweight_torch_backend"],
    }


def _build_torch_sequence_network(
    model_name: str,
    *,
    input_dim: int,
    hidden_dim: int,
    nn_module: Any,
    params: dict[str, Any],
) -> Any:
    class RecurrentNet(nn_module.Module):
        def __init__(self, cell_type: str) -> None:
            super().__init__()
            cell = nn_module.LSTM if cell_type == "lstm" else nn_module.GRU
            self.encoder = cell(input_dim, hidden_dim, batch_first=True)
            self.head = nn_module.Linear(hidden_dim, 1)

        def forward(self, inputs: Any) -> Any:
            encoded, _ = self.encoder(inputs)
            return self.head(encoded[:, -1, :])

    class TemporalCNN(nn_module.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = nn_module.Sequential(
                nn_module.Conv1d(input_dim, hidden_dim, kernel_size=3, padding=1),
                nn_module.ReLU(),
                nn_module.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1),
                nn_module.ReLU(),
                nn_module.AdaptiveAvgPool1d(1),
            )
            self.head = nn_module.Linear(hidden_dim, 1)

        def forward(self, inputs: Any) -> Any:
            encoded = self.net(inputs.transpose(1, 2)).squeeze(-1)
            return self.head(encoded)

    class TransformerNet(nn_module.Module):
        def __init__(self) -> None:
            super().__init__()
            heads = max(1, min(int(params.get("nhead", 2)), hidden_dim))
            if hidden_dim % heads != 0:
                heads = 1
            self.input_projection = nn_module.Linear(input_dim, hidden_dim)
            layer = nn_module.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=heads,
                dim_feedforward=max(hidden_dim * 2, 16),
                dropout=float(params.get("dropout", 0.0)),
                batch_first=True,
            )
            self.encoder = nn_module.TransformerEncoder(layer, num_layers=max(1, min(int(params.get("layers", 1)), 3)))
            self.head = nn_module.Linear(hidden_dim, 1)

        def forward(self, inputs: Any) -> Any:
            encoded = self.encoder(self.input_projection(inputs))
            return self.head(encoded[:, -1, :])

    class GatedSequenceNet(nn_module.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn_module.LSTM(input_dim, hidden_dim, batch_first=True)
            self.gate = nn_module.Sequential(nn_module.Linear(hidden_dim, hidden_dim), nn_module.Sigmoid())
            self.head = nn_module.Linear(hidden_dim, 1)

        def forward(self, inputs: Any) -> Any:
            encoded, _ = self.encoder(inputs)
            last = encoded[:, -1, :]
            return self.head(last * self.gate(last))

    if model_name == "lstm":
        return RecurrentNet("lstm")
    if model_name == "gru":
        return RecurrentNet("gru")
    if model_name == "temporal_cnn":
        return TemporalCNN()
    if model_name == "transformer":
        return TransformerNet()
    return GatedSequenceNet()


def _sequence_windows(x: np.ndarray, lookback: int) -> np.ndarray:
    sequences = np.empty((len(x), lookback, x.shape[1]), dtype=np.float32)
    for idx in range(len(x)):
        start = max(0, idx - lookback + 1)
        window = x[start:idx + 1]
        if len(window) < lookback:
            pad = np.repeat(window[:1], lookback - len(window), axis=0)
            window = np.vstack([pad, window])
        sequences[idx] = window[-lookback:]
    return sequences


def _predict(model: dict[str, Any], x: np.ndarray, task: str) -> list[float]:
    if model["kind"] == "constant":
        return [float(model["value"]) for _ in range(len(x))]
    if model["kind"] == "momentum_rule":
        values = x[:, model.get("last_col", -1)]
        return [float(value) for value in values]
    if model["kind"] == "torch_sequence":
        return _predict_torch_sequence(model, x)
    estimator = model["estimator"]
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="X does not have valid feature names.*",
            category=UserWarning,
        )
        if task == "classification" and hasattr(estimator, "predict_proba"):
            return [float(value) for value in estimator.predict_proba(x)[:, 1].tolist()]
        predictions = estimator.predict(x)
    return [float(value) for value in predictions.tolist()]


def _predict_torch_sequence(model: dict[str, Any], x: np.ndarray) -> list[float]:
    try:
        import torch  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"torch_sequence_prediction_unavailable:{type(exc).__name__}") from exc
    feature_mean = np.asarray(model["feature_mean"], dtype=np.float32)
    feature_std = np.asarray(model["feature_std"], dtype=np.float32)
    x_scaled = (np.asarray(x, dtype=np.float32) - feature_mean) / feature_std
    sequences = _sequence_windows(x_scaled, int(model.get("lookback") or 10))
    network = model["network"]
    network.eval()
    with torch.no_grad():
        raw = network(torch.from_numpy(sequences)).detach().cpu().numpy().reshape(-1)
    if model.get("task") == "classification":
        raw = 1.0 / (1.0 + np.exp(-raw))
    return [float(value) for value in raw.tolist()]


def _prediction_to_return(prediction: float | None, task: str) -> float | None:
    if prediction is None:
        return None
    if task == "classification":
        return float(prediction) - 0.5
    return float(prediction)


def _probability_up(prediction: float | None, expected_return: float | None, residuals: list[float], task: str, *, target_type: str) -> float | None:
    if prediction is None:
        return None
    if task == "classification":
        return round(max(0.0, min(1.0, float(prediction))), 6)
    if target_type == "volatility":
        return None
    if expected_return is None:
        return None
    sigma = stdev(residuals) or 0.01
    z = expected_return / sigma
    probability = 1.0 / (1.0 + np.exp(-z))
    return round(float(max(0.0, min(1.0, probability))), 6)


def _aggregate_metrics(fold_metrics: list[dict[str, Any]], task: str) -> dict[str, float]:
    if not fold_metrics:
        return {}
    keys = ["accuracy", "precision", "recall", "f1"] if task == "classification" else ["mae", "rmse", "r2", "ic", "rank_ic", "directional_accuracy"]
    return {key: round(float(mean(item.get(key) for item in fold_metrics) or 0.0), 6) for key in keys}


def _baseline_metrics(targets: list[float], oos_predictions: list[dict[str, Any]], task: str) -> dict[str, float]:
    if not oos_predictions:
        return {}
    if task == "classification":
        positive_rate = float(np.mean([1.0 if value > 0 else 0.0 for value in targets])) if targets else 0.5
        actual = [item["actual"] for item in oos_predictions]
        predicted = [positive_rate for _ in actual]
        return classification_metrics(actual, predicted)
    historical_mean = float(np.mean(targets)) if targets else 0.0
    actual = [item.get("actual_target", item.get("actual_forward_return")) for item in oos_predictions]
    predicted = [historical_mean for _ in actual]
    return regression_metrics(actual, predicted)


def _feature_importance(model: dict[str, Any], feature_names: list[str], x: np.ndarray, y: np.ndarray) -> list[dict[str, Any]]:
    estimator = model.get("estimator")
    raw = None
    if estimator is not None:
        final = getattr(estimator, "steps", [[None, estimator]])[-1][1] if hasattr(estimator, "steps") else estimator
        if hasattr(final, "feature_importances_"):
            raw = final.feature_importances_
        elif hasattr(final, "coef_"):
            raw = np.ravel(final.coef_)
    if raw is None:
        raw = []
        for idx in range(x.shape[1]):
            try:
                column = x[:, idx]
                corr = 0.0 if float(np.std(column)) == 0.0 or float(np.std(y)) == 0.0 else float(np.corrcoef(column, y)[0, 1])
            except Exception:  # noqa: BLE001
                corr = 0.0
            raw.append(0.0 if not np.isfinite(corr) else abs(corr))
    total = float(np.sum(np.abs(raw))) or 1.0
    items = [
        {"feature": name, "importance": round(float(abs(value) / total), 6)}
        for name, value in zip(feature_names, raw)
    ]
    return sorted(items, key=lambda item: item["importance"], reverse=True)[:15]


def _permutation_importance(
    model: dict[str, Any],
    feature_names: list[str],
    x: np.ndarray,
    y: np.ndarray,
    task: str,
    *,
    seed: int,
) -> list[dict[str, Any]]:
    if not feature_names or len(x) < 20:
        return []
    rng = np.random.default_rng(seed)
    baseline = _model_score(y.tolist(), _predict(model, x, task), task)
    rows: list[dict[str, Any]] = []
    max_rows = min(len(x), 600)
    sample_idx = np.arange(len(x))[-max_rows:]
    sample_x = x[sample_idx].copy()
    sample_y = y[sample_idx].copy()
    sample_baseline = _model_score(sample_y.tolist(), _predict(model, sample_x, task), task)
    if sample_baseline > 0:
        baseline = sample_baseline
    for idx, name in enumerate(feature_names):
        permuted = sample_x.copy()
        shuffled = permuted[:, idx].copy()
        rng.shuffle(shuffled)
        permuted[:, idx] = shuffled
        score = _model_score(sample_y.tolist(), _predict(model, permuted, task), task)
        rows.append(
            {
                "feature": name,
                "importance": round(max(0.0, float(baseline - score)), 6),
                "baseline_score": round(float(baseline), 6),
                "permuted_score": round(float(score), 6),
                "method": "permutation_score_drop",
            }
        )
    total = float(sum(item["importance"] for item in rows)) or 1.0
    for item in rows:
        item["normalized_importance"] = round(float(item["importance"]) / total, 6)
    return sorted(rows, key=lambda item: item["importance"], reverse=True)[:15]


def _model_score(actual: list[float], predicted: list[float], task: str) -> float:
    if task == "classification":
        return float(classification_metrics(actual, predicted).get("accuracy") or 0.0)
    return float(regression_metrics(actual, predicted).get("directional_accuracy") or 0.0)


def _shap_importance(model: dict[str, Any], feature_names: list[str], x: np.ndarray) -> dict[str, Any]:
    if model.get("kind") == "torch_sequence":
        return _approximate_shapley_importance(
            model,
            feature_names,
            x,
            warnings=["torch_sequence_model_using_model_agnostic_shapley_approximation"],
        )
    try:
        import shap  # type: ignore
    except Exception:  # noqa: BLE001
        return _approximate_shapley_importance(
            model,
            feature_names,
            x,
            warnings=["shap_optional_dependency_missing_using_model_agnostic_shapley_approximation"],
        )
    estimator = model.get("estimator")
    if estimator is None or not feature_names or len(x) < 5:
        return {"status": "unavailable", "items": [], "warnings": ["shap_estimator_unavailable"]}
    final = getattr(estimator, "steps", [[None, estimator]])[-1][1] if hasattr(estimator, "steps") else estimator
    if not (hasattr(final, "feature_importances_") or hasattr(final, "coef_")):
        return {"status": "unavailable", "items": [], "warnings": ["shap_model_type_not_supported_for_lightweight_path"]}
    try:
        sample = x[-min(len(x), 100) :]
        explainer = shap.Explainer(estimator.predict, sample)
        values = explainer(sample)
        raw = np.abs(np.asarray(values.values)).mean(axis=0)
        if raw.ndim > 1:
            raw = raw.mean(axis=0)
        total = float(np.sum(np.abs(raw))) or 1.0
        items = [
            {"feature": name, "importance": round(float(abs(value) / total), 6), "method": "shap_mean_abs"}
            for name, value in zip(feature_names, raw)
        ]
        return {"status": "success", "items": sorted(items, key=lambda item: item["importance"], reverse=True)[:15], "warnings": []}
    except Exception as exc:  # noqa: BLE001
        return _approximate_shapley_importance(
            model,
            feature_names,
            x,
            warnings=[f"shap_failed:{type(exc).__name__}", "using_model_agnostic_shapley_approximation"],
        )


def _approximate_shapley_importance(
    model: dict[str, Any],
    feature_names: list[str],
    x: np.ndarray,
    *,
    warnings: list[str],
) -> dict[str, Any]:
    if not feature_names or len(x) < 5:
        return {"status": "unavailable", "items": [], "warnings": warnings + ["shapley_approximation_insufficient_rows"]}
    try:
        sample = x[-min(len(x), 120) :].copy()
        baseline = np.nanmedian(sample, axis=0)
        original = np.asarray(_predict(model, sample, "regression"), dtype=float)
        rows: list[dict[str, Any]] = []
        for idx, name in enumerate(feature_names):
            occluded = sample.copy()
            occluded[:, idx] = baseline[idx]
            shifted = np.asarray(_predict(model, occluded, "regression"), dtype=float)
            rows.append(
                {
                    "feature": name,
                    "importance": round(float(np.mean(np.abs(original - shifted))), 8),
                    "method": "model_agnostic_shapley_occlusion_approx",
                }
            )
        total = float(sum(item["importance"] for item in rows)) or 1.0
        items = [
            {
                **item,
                "importance": round(float(item["importance"]) / total, 6),
            }
            for item in rows
        ]
        return {"status": "success", "items": sorted(items, key=lambda item: item["importance"], reverse=True)[:15], "warnings": warnings}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "items": [], "warnings": warnings + [f"shapley_approximation_failed:{type(exc).__name__}"]}


def _underperformed(aggregate: dict[str, float], baseline: dict[str, float]) -> bool:
    if not aggregate or not baseline:
        return False
    if "accuracy" in aggregate and "accuracy" in baseline:
        return float(aggregate.get("accuracy") or 0.0) < float(baseline.get("accuracy") or 0.0)
    return float(aggregate.get("directional_accuracy") or 0.0) < float(baseline.get("directional_accuracy") or 0.0)


def _target_type(config: TargetConfig) -> str:
    raw = str(config.target_type or "forward_return").lower()
    return "triple_barrier_label" if raw == "triple_barrier" else raw


def _classification_target(target_type: str) -> bool:
    return target_type in {"direction", "triple_barrier_label", "quantile_return"}


def _return_target(target_type: str) -> bool:
    return target_type in {"forward_return", "excess_return"}


def _classification_return_calibration(oos_predictions: list[dict[str, Any]]) -> dict[str, Any]:
    positive = [float(item["actual_forward_return"]) for item in oos_predictions if item.get("actual_forward_return") is not None and float(item["actual_forward_return"]) > 0]
    non_positive = [float(item["actual_forward_return"]) for item in oos_predictions if item.get("actual_forward_return") is not None and float(item["actual_forward_return"]) <= 0]
    all_returns = [float(item["actual_forward_return"]) for item in oos_predictions if item.get("actual_forward_return") is not None]
    if not all_returns:
        return {"positive_mean": 0.0, "non_positive_mean": 0.0, "method": 0.0}
    positive_mean = float(np.mean(positive)) if positive else max(float(np.mean(all_returns)), 0.0)
    non_positive_mean = float(np.mean(non_positive)) if non_positive else min(float(np.mean(all_returns)), 0.0)
    return {
        "positive_mean": round(positive_mean, 8),
        "non_positive_mean": round(non_positive_mean, 8),
        "method": "oos_conditional_forward_return_by_direction",
    }


def _classification_probability_calibration(oos_predictions: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (float(item["prediction"]), 1.0 if float(item.get("actual") or 0.0) > 0.0 else 0.0)
        for item in oos_predictions
        if item.get("prediction") is not None
    ]
    if len(pairs) < 5:
        return {"method": "insufficient_oos_probability_calibration", "bins": [], "brier_score": None}
    bin_count = 5
    bins: list[dict[str, Any]] = []
    brier_terms: list[float] = []
    for idx in range(bin_count):
        lower = idx / bin_count
        upper = (idx + 1) / bin_count
        bucket = [(prob, actual) for prob, actual in pairs if lower <= prob < upper or (idx == bin_count - 1 and prob <= upper)]
        if not bucket:
            continue
        mean_pred = float(np.mean([prob for prob, _ in bucket]))
        observed_rate = float(np.mean([actual for _, actual in bucket]))
        bins.append(
            {
                "lower": round(lower, 4),
                "upper": round(upper, 4),
                "count": len(bucket),
                "mean_prediction": round(mean_pred, 6),
                "observed_rate": round(observed_rate, 6),
            }
        )
        brier_terms.extend((prob - actual) ** 2 for prob, actual in bucket)
    return {
        "method": "oos_reliability_bin_calibration",
        "bins": bins,
        "brier_score": round(float(np.mean(brier_terms)), 6) if brier_terms else None,
        "sample_count": len(pairs),
    }


def _apply_probability_calibration(prediction: float | None, calibration: dict[str, Any]) -> float | None:
    if prediction is None:
        return None
    probability = max(0.0, min(1.0, float(prediction)))
    bins = calibration.get("bins") or []
    if not bins:
        return probability
    selected = None
    for item in bins:
        lower = float(item.get("lower") or 0.0)
        upper = float(item.get("upper") or 1.0)
        if lower <= probability < upper or (upper >= 1.0 and probability <= upper):
            selected = item
            break
    if selected is None:
        selected = min(bins, key=lambda item: abs(float(item.get("mean_prediction") or probability) - probability))
    observed = float(selected.get("observed_rate") if selected.get("observed_rate") is not None else probability)
    count = float(selected.get("count") or 0.0)
    shrinkage = min(0.80, count / (count + 20.0))
    calibrated = probability * (1.0 - shrinkage) + observed * shrinkage
    return max(0.0, min(1.0, calibrated))


def _calibrated_return(prediction: float | None, calibration: dict[str, Any]) -> float | None:
    if prediction is None:
        return None
    try:
        probability = max(0.0, min(1.0, float(prediction)))
    except (TypeError, ValueError):
        return None
    positive_mean = float(calibration.get("positive_mean") or 0.0)
    non_positive_mean = float(calibration.get("non_positive_mean") or 0.0)
    return probability * positive_mean + (1.0 - probability) * non_positive_mean


def _conformal_interval(expected_return: float | None, residuals: list[float], *, volatility_target: bool) -> dict[str, Any]:
    if volatility_target or expected_return is None:
        return {"method": "unavailable_for_volatility_target", "p10": None, "p50": None, "p90": None, "alpha": 0.20, "sample_count": len(residuals)}
    if len(residuals) < 5:
        return {
            "method": "insufficient_oos_residuals_for_conformal_interval",
            "p10": round(float(expected_return), 8),
            "p50": round(float(expected_return), 8),
            "p90": round(float(expected_return), 8),
            "alpha": 0.20,
            "sample_count": len(residuals),
        }
    absolute_residuals = [abs(float(value)) for value in residuals if np.isfinite(value)]
    if not absolute_residuals:
        return {"method": "conformal_interval_unavailable_non_finite_residuals", "p10": None, "p50": round(float(expected_return), 8), "p90": None, "alpha": 0.20, "sample_count": len(residuals)}
    alpha = 0.20
    quantile = float(percentile(absolute_residuals, 1.0 - alpha) or 0.0)
    return {
        "method": "oos_residual_conformal_interval",
        "p10": round(float(expected_return - quantile), 8),
        "p50": round(float(expected_return), 8),
        "p90": round(float(expected_return + quantile), 8),
        "alpha": alpha,
        "residual_quantile": round(quantile, 8),
        "sample_count": len(absolute_residuals),
    }


def _sklearn_available() -> bool:
    return _module_available("sklearn")


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except Exception:  # noqa: BLE001
        return False
    return True
