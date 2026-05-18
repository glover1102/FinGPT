from __future__ import annotations

from typing import Any


def generate_explainability(training_result: dict[str, Any]) -> dict[str, Any]:
    top = list(training_result.get("feature_importance") or [])[:10]
    permutation = list(training_result.get("permutation_importance") or [])[:10]
    shap_items = list(training_result.get("shap_importance") or [])[:10]
    warnings = list(training_result.get("explainability_warnings") or [])
    unavailable = list(training_result.get("unavailable_explainers") or [])
    reason_codes = []
    for item in top[:5]:
        feature = str(item.get("feature") or "")
        if "momentum" in feature or "return" in feature:
            reason_codes.append(f"{feature} contributed through recent return or momentum behavior.")
        elif "vol" in feature:
            reason_codes.append(f"{feature} affected risk and confidence.")
        elif "ma_" in feature or "trend" in feature or "price_distance" in feature:
            reason_codes.append(f"{feature} contributed through trend state.")
        else:
            reason_codes.append(f"{feature} was among the highest ranked model drivers.")
    return {
        "status": "success",
        "top_features": [item.get("feature") for item in top],
        "feature_importance": top,
        "permutation_importance": permutation,
        "shap_importance": shap_items,
        "reason_codes": reason_codes,
        "unavailable_explainers": unavailable,
        "warnings": warnings,
    }
