from __future__ import annotations

from typing import Any

from core.schemas.quant import ModelCapabilityProfile


def model_capability_profile(route: str, resolved_model: str | None = None) -> ModelCapabilityProfile:
    normalized_route = (route or "qwen").strip().lower()
    resolved = (resolved_model or "").strip() or ("qwen2.5:7b" if normalized_route in {"qwen", "primary", "ollama", "mistral", "llama-2", ""} else normalized_route)

    if normalized_route in {"qwen", "primary", "ollama", "mistral", "llama-2", ""}:
        return ModelCapabilityProfile(
            route=normalized_route or "qwen",
            resolved_model=resolved,
            json_reliability="medium",
            korean_reliability="medium",
            context_window=8192,
            structured_output_support=True,
            finance_reasoning="medium",
            latency_profile="medium",
            gpu_required=False,
            recommended_tasks=["single_name_research", "topic_macro", "final_report"],
            restricted_tasks=["deterministic_quant"],
        )

    if normalized_route == "fingpt":
        return ModelCapabilityProfile(
            route="fingpt",
            resolved_model=resolved or "FinGPT local adapter",
            json_reliability="low",
            korean_reliability="low",
            context_window=4096,
            structured_output_support=False,
            finance_reasoning="medium",
            latency_profile="slow",
            gpu_required=True,
            recommended_tasks=["event_extraction", "sentiment_tagging", "risk_tone_classification"],
            restricted_tasks=["final_report", "deterministic_quant", "topic_macro_json"],
        )

    if normalized_route == "gemma4":
        return ModelCapabilityProfile(
            route="gemma4",
            resolved_model=resolved or "gemma4:e4b",
            json_reliability="low",
            korean_reliability="medium",
            context_window=8192,
            structured_output_support=True,
            finance_reasoning="medium",
            latency_profile="unknown",
            gpu_required=False,
            recommended_tasks=["experimental_review", "single_name_research_comparison"],
            restricted_tasks=["deterministic_quant"],
        )

    if normalized_route in {"gemma", "gemma-experimental"}:
        return ModelCapabilityProfile(
            route=normalized_route,
            resolved_model=resolved,
            json_reliability="low",
            korean_reliability="medium",
            context_window=8192,
            structured_output_support=True,
            finance_reasoning="low",
            latency_profile="unknown",
            gpu_required=False,
            recommended_tasks=["experimental_review"],
            restricted_tasks=["production_final_report", "deterministic_quant"],
        )

    return ModelCapabilityProfile(
        route=normalized_route,
        resolved_model=resolved or normalized_route,
        json_reliability="low",
        korean_reliability="low",
        context_window=4096,
        structured_output_support=False,
        finance_reasoning="low",
        latency_profile="unknown",
        gpu_required=False,
        recommended_tasks=[],
        restricted_tasks=["production_final_report", "deterministic_quant"],
    )


def model_capability_dict(route: str, resolved_model: str | None = None) -> dict[str, Any]:
    return model_capability_profile(route, resolved_model).model_dump(mode="json")
