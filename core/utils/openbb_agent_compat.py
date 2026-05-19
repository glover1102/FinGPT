from __future__ import annotations

import importlib.util
from typing import Any


def openbb_ai_installed() -> bool:
    """Return whether the optional OpenBB AI SDK is importable."""

    return importlib.util.find_spec("openbb_ai") is not None


def sse_starlette_installed() -> bool:
    """Return whether the optional SSE helper dependency is importable."""

    return importlib.util.find_spec("sse_starlette") is not None


def _base_url(settings: Any) -> str:
    return str(getattr(settings, "openbb_agent_public_url", "http://127.0.0.1:8000") or "").rstrip("/")


def build_agents_json(settings: Any, *, include_disabled: bool = False) -> dict[str, Any]:
    """Build the OpenBB Workspace agents.json payload.

    The shape is intentionally conservative: it exposes stable metadata and
    endpoint URLs, while extra FinGPT-specific capability flags live under
    ``metadata`` so OpenBB can ignore them if its contract evolves.
    """

    enabled = bool(getattr(settings, "openbb_agent_enabled", False))
    if not enabled and not include_disabled:
        return {}

    agent_id = str(getattr(settings, "openbb_agent_id", "fingpt-local-research") or "fingpt-local-research").strip()
    agent_name = str(getattr(settings, "openbb_agent_name", "FinGPT Local Research") or "FinGPT Local Research").strip()
    base_url = _base_url(settings)
    query_url = f"{base_url}/query" if base_url else "/query"

    return {
        agent_id: {
            "name": agent_name,
            "description": (
                "Local FinGPT research agent for Korean decision-grade equity, macro, rates, "
                "credit, FX, commodity, and crypto analysis with citation/provenance artifacts."
            ),
            "endpoints": {
                "query": query_url,
            },
            "features": {
                "streaming": True,
                "widget_context": True,
                "provenance": True,
                "tables": True,
            },
            "metadata": {
                "enabled": enabled,
                "id": agent_id,
                "version": "1.0",
                "primary_language": "ko",
                "primary_model": getattr(settings, "primary_model", None),
                "openbb_ai_installed": openbb_ai_installed(),
                "sse_starlette_installed": sse_starlette_installed(),
                "backend": "FinGPT /api/v1/research/universal",
            },
        }
    }


def validate_agents_json(payload: dict[str, Any], settings: Any) -> list[str]:
    """Return contract validation errors for the generated agents.json payload."""

    if not isinstance(payload, dict):
        return ["agents.json payload must be an object"]
    if not payload:
        if bool(getattr(settings, "openbb_agent_enabled", False)):
            return ["OpenBB agent is enabled but agents.json returned no agents"]
        return []

    agent_id = str(getattr(settings, "openbb_agent_id", "fingpt-local-research") or "fingpt-local-research").strip()
    agent = payload.get(agent_id)
    if not isinstance(agent, dict):
        return [f"agents.json missing configured agent id '{agent_id}'"]

    errors: list[str] = []
    if not str(agent.get("name") or "").strip():
        errors.append("agent name is required")
    endpoints = agent.get("endpoints")
    if not isinstance(endpoints, dict) or not str(endpoints.get("query") or "").strip():
        errors.append("agent endpoints.query is required")
    features = agent.get("features")
    if not isinstance(features, dict) or features.get("streaming") is not True:
        errors.append("agent features.streaming must be true")
    return errors


def check_openbb_agent_contract(settings: Any) -> tuple[str, bool, str]:
    """Preflight-style check for the optional OpenBB Workspace agent adapter."""

    name = "OPENBB_AGENT_CONTRACT"
    if not bool(getattr(settings, "openbb_agent_enabled", False)):
        return name, True, "Disabled - OPENBB_AGENT_ENABLED=false; FinGPT core API/UI is unaffected."

    payload = build_agents_json(settings, include_disabled=True)
    errors = validate_agents_json(payload, settings)
    if errors:
        return name, False, "; ".join(errors)

    sdk_status = "openbb-ai installed" if openbb_ai_installed() else "openbb-ai not installed; manual SSE fallback active"
    sse_status = "sse-starlette installed" if sse_starlette_installed() else "sse-starlette not installed; FastAPI StreamingResponse fallback active"
    return name, True, f"Enabled - agents.json contract valid; {sdk_status}; {sse_status}."
