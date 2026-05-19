from __future__ import annotations

import importlib.metadata as metadata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VersionPolicy:
    package: str
    minimum: tuple[int, ...]
    maximum_exclusive: tuple[int, ...]
    critical: bool = True
    rationale: str = ""


PROVIDER_VERSION_POLICIES: tuple[VersionPolicy, ...] = (
    VersionPolicy("openbb", (4, 7, 0), (4, 8, 0), True, "OpenBB SDK major/minor used by provider adapters."),
    VersionPolicy("openbb-core", (1, 6, 0), (1, 7, 0), True, "OpenBB core ABI must align with extension packages."),
    VersionPolicy("openbb-news", (1, 6, 0), (1, 7, 0), True, "News connector interface used by compatibility checks."),
    VersionPolicy("openbb-yfinance", (1, 6, 0), (1, 7, 0), True, "Yahoo/OpenBB fallback connector."),
    VersionPolicy("openbb-fred", (1, 6, 0), (1, 7, 0), False, "Macro connector; direct FRED fallback remains available."),
    VersionPolicy("openbb-sec", (1, 6, 0), (1, 7, 0), False, "SEC connector; direct SEC fallback remains available."),
    VersionPolicy("openbb-fmp", (1, 6, 0), (1, 7, 0), False, "FMP is auxiliary after OpenBB/Yahoo/FRED/SEC."),
    VersionPolicy("openbb-ai", (1, 10, 0), (1, 11, 0), False, "Optional OpenBB Workspace SDK helper."),
    VersionPolicy("sse-starlette", (3, 0, 0), (4, 0, 0), False, "Optional SSE helper; FastAPI StreamingResponse fallback exists."),
    VersionPolicy("yfinance", (0, 2, 0), (2, 0, 0), True, "Primary keyless market data fallback."),
    VersionPolicy("fastapi", (0, 110, 0), (1, 0, 0), True, "API framework compatibility."),
    VersionPolicy("pydantic", (2, 7, 0), (3, 0, 0), True, "Schema validation compatibility."),
    VersionPolicy("qdrant-client", (1, 8, 0), (2, 0, 0), True, "Vector store client compatibility."),
)

OPENBB_AGENT_REQUIRED_WHEN_ENABLED = frozenset({"openbb-ai", "sse-starlette"})


def _parse_version(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    parts: list[int] = []
    token = ""
    for char in value:
        if char.isdigit():
            token += char
            continue
        if token:
            parts.append(int(token))
            token = ""
        if char not in {".", "-"}:
            break
    if token:
        parts.append(int(token))
    return tuple(parts[:4]) if parts else None


def _cmp_tuple(value: tuple[int, ...], size: int = 4) -> tuple[int, ...]:
    return value + (0,) * max(0, size - len(value))


def _in_range(version: tuple[int, ...], minimum: tuple[int, ...], maximum_exclusive: tuple[int, ...]) -> bool:
    size = max(len(version), len(minimum), len(maximum_exclusive), 4)
    normalized = _cmp_tuple(version, size)
    return _cmp_tuple(minimum, size) <= normalized < _cmp_tuple(maximum_exclusive, size)


def installed_provider_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for policy in PROVIDER_VERSION_POLICIES:
        try:
            versions[policy.package] = metadata.version(policy.package)
        except metadata.PackageNotFoundError:
            versions[policy.package] = None
    return versions


def build_provider_version_report(
    versions: dict[str, str | None] | None = None,
    *,
    require_openbb_agent: bool = False,
) -> dict[str, Any]:
    versions = dict(versions or installed_provider_versions())
    checks: list[dict[str, Any]] = []
    critical_failures: list[str] = []
    warnings: list[str] = []

    for policy in PROVIDER_VERSION_POLICIES:
        effective_critical = policy.critical or (
            require_openbb_agent and policy.package in OPENBB_AGENT_REQUIRED_WHEN_ENABLED
        )
        raw_version = versions.get(policy.package)
        parsed = _parse_version(raw_version)
        if not raw_version or parsed is None:
            ok = False
            status = "missing_optional" if not effective_critical else "missing"
            detail = "optional package not installed" if not effective_critical else "required package not installed"
        else:
            ok = _in_range(parsed, policy.minimum, policy.maximum_exclusive)
            status = "ok" if ok else "out_of_policy"
            detail = (
                f"{policy.package} {raw_version} within policy"
                if ok
                else f"{policy.package} {raw_version} outside >= {'.'.join(map(str, policy.minimum))}, < {'.'.join(map(str, policy.maximum_exclusive))}"
            )
        check = {
            "package": policy.package,
            "version": raw_version or "not_installed",
            "ok": ok,
            "critical": effective_critical,
            "base_critical": policy.critical,
            "status": status,
            "minimum": ".".join(map(str, policy.minimum)),
            "maximum_exclusive": ".".join(map(str, policy.maximum_exclusive)),
            "detail": detail,
            "rationale": policy.rationale,
        }
        checks.append(check)
        if not ok and effective_critical:
            critical_failures.append(f"{policy.package}: {detail}")
        elif not ok:
            warnings.append(f"{policy.package}: {detail}")

    return {
        "status": "failed" if critical_failures else "passed",
        "critical_passed": not critical_failures,
        "critical_failure_count": len(critical_failures),
        "warning_count": len(warnings),
        "critical_failures": critical_failures,
        "warnings": warnings,
        "require_openbb_agent": require_openbb_agent,
        "versions": versions,
        "checks": checks,
    }
