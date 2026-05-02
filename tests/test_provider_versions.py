from __future__ import annotations

from core.utils.provider_versions import build_provider_version_report


def _valid_versions() -> dict[str, str]:
    return {
        "openbb": "4.7.1",
        "openbb-core": "1.6.8",
        "openbb-news": "1.6.1",
        "openbb-yfinance": "1.6.2",
        "openbb-fred": "1.6.0",
        "openbb-sec": "1.6.0",
        "openbb-fmp": "1.6.0",
        "openbb-ai": "1.10.0",
        "sse-starlette": "3.2.0",
        "yfinance": "1.3.0",
        "fastapi": "0.128.0",
        "pydantic": "2.12.5",
        "qdrant-client": "1.8.2",
    }


def test_provider_version_report_passes_current_policy() -> None:
    report = build_provider_version_report(_valid_versions())

    assert report["critical_passed"] is True
    assert report["status"] == "passed"
    assert report["critical_failure_count"] == 0


def test_provider_version_report_blocks_critical_drift() -> None:
    versions = _valid_versions()
    versions["openbb"] = "5.0.0"

    report = build_provider_version_report(versions)

    assert report["critical_passed"] is False
    assert any("openbb" in item for item in report["critical_failures"])


def test_provider_version_report_treats_optional_missing_as_warning() -> None:
    versions = _valid_versions()
    versions["openbb-ai"] = None

    report = build_provider_version_report(versions)

    assert report["critical_passed"] is True
    assert report["warning_count"] >= 1
    assert any("openbb-ai" in item for item in report["warnings"])


def test_provider_version_report_requires_openbb_agent_dependencies_when_enabled() -> None:
    versions = _valid_versions()
    versions["openbb-ai"] = None

    report = build_provider_version_report(versions, require_openbb_agent=True)

    assert report["critical_passed"] is False
    assert any("openbb-ai" in item for item in report["critical_failures"])
    check = next(item for item in report["checks"] if item["package"] == "openbb-ai")
    assert check["critical"] is True
    assert check["base_critical"] is False
