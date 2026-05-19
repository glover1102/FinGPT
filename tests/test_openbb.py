from __future__ import annotations

import subprocess

from core.utils.openbb_compat import build_openbb_compat_report
from core.utils.openbb_compat import check_pip_consistency


def test_openbb_compat_report_treats_news_runtime_as_warning_only():
    report = build_openbb_compat_report(
        sec_user_agent="FinGPTLocalResearch/1.0 test@example.com",
        include_pip_check=False,
        include_network_smoke=False,
        include_openbb_news_runtime=True,
    )

    assert "versions" in report
    assert any(check["name"] == "openbb_package_versions" for check in report["checks"])
    news_check = next(check for check in report["checks"] if check["name"] == "openbb_news_company")
    assert news_check["critical"] is False
    assert report["critical_passed"] is True


def test_pip_check_external_conflict_is_not_critical(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="pykrx 1.2.4 has requirement numpy<2.0,>=1.24.0, but you have numpy 2.2.6.",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = check_pip_consistency(project_packages={"openbb", "yfinance"})

    assert result["ok"] is True
    assert result["critical"] is False
    assert result["status"] == "external_conflicts"
    assert result["broken_packages"] == ["pykrx"]


def test_pip_check_project_conflict_is_critical(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="openbb 4.6.0 has requirement openbb-core==1.5.9, but you have openbb-core 1.6.8.",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = check_pip_consistency(project_packages={"openbb", "openbb-core"})

    assert result["ok"] is False
    assert result["critical"] is True
    assert result["status"] == "failed"
    assert result["project_conflicts"] == ["openbb"]
