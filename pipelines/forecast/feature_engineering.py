from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.schemas.forecast import FeatureConfig
from pipelines.data_mart.storage import repository


TARGET_RESERVED_PREFIXES = ("forward_return", "direction", "target", "label", "future_")


def build_features(
    price_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]] | None,
    config: FeatureConfig,
) -> dict[str, Any]:
    df = _price_frame(price_rows)
    benchmark = _price_frame(benchmark_rows or [])
    if df.empty:
        return {
            "status": "empty",
            "rows": [],
            "feature_names": [],
            "summary": {"feature_count": 0, "missing_ratio": 1.0},
            "warnings": ["price_frame_empty"],
        }
    groups = {item.lower() for item in config.feature_groups}
    out = pd.DataFrame(index=df.index)
    price = df["price"]
    returns = price.pct_change()
    log_returns = np.log(price / price.shift(1)).replace([np.inf, -np.inf], np.nan)

    if "returns" in groups:
        out["return_1d"] = returns
        out["return_5d"] = price.pct_change(5)
        out["return_20d"] = price.pct_change(20)
        out["log_return_1d"] = log_returns
        out["cumulative_return_20d"] = (1.0 + returns).rolling(20).apply(np.prod, raw=True) - 1.0

    if "momentum" in groups:
        out["momentum_5d"] = price / price.shift(5) - 1.0
        out["momentum_20d"] = price / price.shift(20) - 1.0
        out["momentum_60d"] = price / price.shift(60) - 1.0
        out["rate_of_change"] = price.pct_change(10)
        if not benchmark.empty:
            bench_price = benchmark["price"].reindex(df.index).ffill()
            out["relative_strength_vs_benchmark"] = price.pct_change(60) - bench_price.pct_change(60)

    if "volatility" in groups:
        out["realized_vol_5d"] = returns.rolling(5).std() * np.sqrt(252)
        out["realized_vol_20d"] = returns.rolling(20).std() * np.sqrt(252)
        out["realized_vol_60d"] = returns.rolling(60).std() * np.sqrt(252)
        out["downside_volatility"] = returns.where(returns < 0, 0.0).rolling(20).std() * np.sqrt(252)
        out["volatility_ratio_20d_60d"] = out["realized_vol_20d"] / out["realized_vol_60d"]

    if "trend" in groups:
        out["ma_20"] = price.rolling(20).mean()
        out["ma_60"] = price.rolling(60).mean()
        out["ma_200"] = price.rolling(200).mean()
        out["price_distance_from_ma20"] = price / out["ma_20"] - 1.0
        out["price_distance_from_ma60"] = price / out["ma_60"] - 1.0
        out["price_distance_from_ma200"] = price / out["ma_200"] - 1.0
        out["price_above_ma200"] = (price > out["ma_200"]).astype(float)

    if "mean_reversion" in groups:
        out["rsi_14"] = _rsi(price, 14)
        rolling_mean = price.rolling(20).mean()
        rolling_std = price.rolling(20).std()
        out["zscore_close_20d"] = (price - rolling_mean) / rolling_std
        lower = rolling_mean - 2.0 * rolling_std
        upper = rolling_mean + 2.0 * rolling_std
        out["bollinger_percent_b"] = (price - lower) / (upper - lower)
        out["short_term_reversal_5d"] = -price.pct_change(5)

    if "volume" in groups and "volume" in df:
        volume = df["volume"].replace(0, np.nan)
        out["volume_change_5d"] = volume.pct_change(5)
        out["volume_zscore_20d"] = (volume - volume.rolling(20).mean()) / volume.rolling(20).std()
        out["dollar_volume"] = volume * price
        out["obv"] = (np.sign(returns.fillna(0.0)) * volume.fillna(0.0)).cumsum()

    if "cross_asset" in groups and not benchmark.empty:
        bench_price = benchmark["price"].reindex(df.index).ffill()
        bench_returns = bench_price.pct_change()
        out["benchmark_return_20d"] = bench_price.pct_change(20)
        out["beta_to_benchmark_60d"] = returns.rolling(60).cov(bench_returns) / bench_returns.rolling(60).var()
        out["correlation_to_benchmark_60d"] = returns.rolling(60).corr(bench_returns)

    macro_warnings: list[str] = []
    if "macro" in groups:
        macro_features, macro_warnings = _macro_features(df.index)
        for name, series in macro_features.items():
            out[name] = series

    out = out.replace([np.inf, -np.inf], np.nan)
    if config.selected_features:
        selected = [name for name in config.selected_features if name in out.columns and not _is_reserved(name)]
        out = out[selected]
    else:
        out = out[[name for name in out.columns if not _is_reserved(name)]]
    if config.feature_shift:
        out = out.shift(int(config.feature_shift))

    rows = []
    for date, values in out.iterrows():
        features = {name: _json_float(values[name]) for name in out.columns}
        rows.append({"date": str(date.date()), "features": features})

    missing_by_feature = {name: round(float(out[name].isna().mean()), 6) for name in out.columns}
    missing_ratio = round(float(out.isna().mean().mean()), 6) if len(out.columns) else 1.0
    return {
        "status": "success" if rows else "empty",
        "rows": rows,
        "feature_names": list(out.columns),
        "summary": {
            "feature_count": len(out.columns),
            "row_count": len(rows),
            "missing_ratio": missing_ratio,
            "missing_by_feature": missing_by_feature,
            "feature_shift": config.feature_shift,
            "feature_groups": sorted(groups),
        },
        "warnings": (["high_feature_missing_ratio"] if missing_ratio > 0.5 else []) + macro_warnings,
    }


def _price_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if "date" not in frame or "price" not in frame:
        return pd.DataFrame()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    if "volume" in frame:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    return frame.set_index("date")


def _rsi(price: pd.Series, window: int) -> pd.Series:
    delta = price.diff()
    gain = delta.clip(lower=0.0).rolling(window).mean()
    loss = (-delta.clip(upper=0.0)).rolling(window).mean()
    rs = gain / loss
    return 100.0 - (100.0 / (1.0 + rs))


def _macro_features(index: pd.DatetimeIndex) -> tuple[dict[str, pd.Series], list[str]]:
    series_map = {
        "DGS10": "macro_10y_yield",
        "DGS2": "macro_2y_yield",
        "T10Y2Y": "macro_10y_2y_spread",
        "VIXCLS": "macro_vix",
        "CPIAUCSL": "macro_cpi",
    }
    features: dict[str, pd.Series] = {}
    warnings: list[str] = []
    if len(index) == 0:
        return features, ["macro_feature_index_empty"]
    start = str(index.min().date())
    end = str(index.max().date())
    for series_id, feature_name in series_map.items():
        rows = repository.get_macro_observations(series_id, start_date=start, end_date=end, limit=10000)
        if not rows:
            warnings.append(f"macro_series_unavailable:{series_id}")
            continue
        frame = pd.DataFrame(rows)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame = frame.dropna(subset=["date", "value"]).sort_values("date").drop_duplicates("date", keep="last")
        if frame.empty:
            warnings.append(f"macro_series_empty_after_cleaning:{series_id}")
            continue
        aligned = frame.set_index("date")["value"].reindex(index).ffill()
        features[feature_name] = aligned
        features[f"{feature_name}_change_20d"] = aligned.diff(20)
    if not features:
        warnings.append("macro_features_unavailable")
    return features, warnings


def _json_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _is_reserved(name: str) -> bool:
    clean = str(name).lower()
    return clean.startswith(TARGET_RESERVED_PREFIXES)
