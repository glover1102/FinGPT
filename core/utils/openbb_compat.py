from __future__ import annotations

import importlib
import importlib.metadata as metadata
import subprocess
import sys
import time
from typing import Any

import httpx


OPENBB_PACKAGES = (
    "openbb",
    "openbb-core",
    "openbb-news",
    "openbb-yfinance",
    "openbb-fred",
    "openbb-sec",
    "openbb-fmp",
)

PROJECT_PIP_PACKAGES = {
    "fastapi",
    "uvicorn",
    "httpx",
    "python-multipart",
    "pydantic",
    "pydantic-settings",
    "python-dotenv",
    "qdrant-client",
    "fastembed",
    "openbb",
    "openbb-core",
    "openbb-news",
    "openbb-yfinance",
    "openbb-fred",
    "openbb-sec",
    "openbb-fmp",
    "yfinance",
    "numpy",
    "pandas",
}


def _check_result(
    name: str,
    *,
    ok: bool,
    critical: bool,
    status: str,
    detail: str,
    elapsed_s: float = 0.0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "name": name,
        "ok": ok,
        "critical": critical,
        "status": status,
        "detail": detail,
        "elapsed_s": round(elapsed_s, 3),
    }
    if extra:
        result.update(extra)
    return result


def get_openbb_package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in OPENBB_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def check_imports() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for module_name, package_name in (
        ("openbb", "openbb"),
        ("openbb_core", "openbb-core"),
    ):
        started = time.perf_counter()
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - compatibility audit must be diagnostic.
            checks.append(
                _check_result(
                    f"{package_name}_import",
                    ok=False,
                    critical=True,
                    status="import_error",
                    detail=str(exc),
                    elapsed_s=time.perf_counter() - started,
                )
            )
        else:
            checks.append(
                _check_result(
                    f"{package_name}_import",
                    ok=True,
                    critical=True,
                    status="ok",
                    detail="import ok",
                    elapsed_s=time.perf_counter() - started,
                )
            )
    return checks


def _parse_pip_check_packages(output: str) -> set[str]:
    packages: set[str] = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("no broken requirements"):
            continue
        package = line.split(" ", 1)[0].strip().lower()
        if package:
            packages.add(package)
    return packages


def check_pip_consistency(
    timeout_s: float = 20.0,
    project_packages: set[str] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        process = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _check_result(
            "pip_check",
            ok=False,
            critical=True,
            status="timeout",
            detail=f"pip check timed out after {timeout_s}s",
            elapsed_s=time.perf_counter() - started,
        )
    except Exception as exc:  # noqa: BLE001
        return _check_result(
            "pip_check",
            ok=False,
            critical=True,
            status="failed",
            detail=str(exc),
            elapsed_s=time.perf_counter() - started,
        )

    output = (process.stdout or process.stderr or "").strip()
    if process.returncode != 0:
        project_package_set = project_packages or PROJECT_PIP_PACKAGES
        broken_packages = _parse_pip_check_packages(output)
        project_conflicts = sorted(broken_packages & {package.lower() for package in project_package_set})
        if not project_conflicts:
            return _check_result(
                "pip_check",
                ok=True,
                critical=False,
                status="external_conflicts",
                detail=output or "Only non-project package conflicts were reported by pip check.",
                elapsed_s=time.perf_counter() - started,
                extra={
                    "broken_packages": sorted(broken_packages),
                    "project_conflicts": [],
                },
            )

    return _check_result(
        "pip_check",
        ok=process.returncode == 0,
        critical=True,
        status="ok" if process.returncode == 0 else "failed",
        detail=output or "No broken requirements found.",
        elapsed_s=time.perf_counter() - started,
        extra=(
            {
                "broken_packages": sorted(_parse_pip_check_packages(output)),
                "project_conflicts": project_conflicts,
            }
            if process.returncode != 0
            else None
        ),
    )


def check_openbb_news_runtime(symbol: str = "MSFT", limit: int = 1) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from openbb import obb

        result = obb.news.company(symbol=symbol, limit=limit)
        records = getattr(result, "results", None) or getattr(result, "data", None) or result
        count = len(records) if isinstance(records, list) else 1
        return _check_result(
            "openbb_news_company",
            ok=True,
            critical=False,
            status="ok",
            detail=f"OpenBB news.company returned {count} record(s) for {symbol}",
            elapsed_s=time.perf_counter() - started,
        )
    except Exception as exc:  # noqa: BLE001 - OpenBB provider incompatibilities should not abort runtime.
        return _check_result(
            "openbb_news_company",
            ok=False,
            critical=False,
            status="runtime_error",
            detail=str(exc),
            elapsed_s=time.perf_counter() - started,
        )


def check_direct_yfinance_news(symbol: str = "MSFT") -> dict[str, Any]:
    started = time.perf_counter()
    try:
        import yfinance as yf

        news = yf.Ticker(symbol).news
        if isinstance(news, list) and news:
            return _check_result(
                "direct_yfinance_news",
                ok=True,
                critical=True,
                status="ok",
                detail=f"yfinance returned {len(news)} article(s) for {symbol}",
                elapsed_s=time.perf_counter() - started,
            )
        return _check_result(
            "direct_yfinance_news",
            ok=False,
            critical=True,
            status="empty",
            detail="yfinance returned no usable news records",
            elapsed_s=time.perf_counter() - started,
        )
    except Exception as exc:  # noqa: BLE001
        return _check_result(
            "direct_yfinance_news",
            ok=False,
            critical=True,
            status="failed",
            detail=str(exc),
            elapsed_s=time.perf_counter() - started,
        )


def check_sec_ticker_map(user_agent: str, timeout_s: float = 8.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = httpx.get(
            "https://www.sec.gov/files/company_tickers_exchange.json",
            timeout=timeout_s,
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
        )
        if response.status_code == 200:
            payload = response.json()
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            count = len(rows) if isinstance(rows, list) else 0
            return _check_result(
                "direct_sec_ticker_map",
                ok=True,
                critical=True,
                status="ok",
                detail=f"SEC ticker map returned {count} row(s)",
                elapsed_s=time.perf_counter() - started,
            )
        return _check_result(
            "direct_sec_ticker_map",
            ok=False,
            critical=True,
            status=f"http_{response.status_code}",
            detail=f"SEC ticker map returned HTTP {response.status_code}",
            elapsed_s=time.perf_counter() - started,
        )
    except Exception as exc:  # noqa: BLE001
        return _check_result(
            "direct_sec_ticker_map",
            ok=False,
            critical=True,
            status="failed",
            detail=str(exc),
            elapsed_s=time.perf_counter() - started,
        )


def build_openbb_compat_report(
    *,
    sec_user_agent: str,
    include_pip_check: bool = True,
    include_network_smoke: bool = True,
    include_openbb_news_runtime: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    versions = get_openbb_package_versions()
    missing = [package for package, version in versions.items() if version is None]
    checks.append(
        _check_result(
            "openbb_package_versions",
            ok=not missing,
            critical=True,
            status="ok" if not missing else "missing",
            detail="all OpenBB packages installed" if not missing else f"missing: {', '.join(missing)}",
            extra={"versions": versions},
        )
    )
    checks.extend(check_imports())
    if include_pip_check:
        checks.append(check_pip_consistency())
    if include_openbb_news_runtime:
        checks.append(check_openbb_news_runtime())
    if include_network_smoke:
        checks.append(check_direct_yfinance_news())
        checks.append(check_sec_ticker_map(sec_user_agent))

    critical_failures = [check for check in checks if check["critical"] and not check["ok"]]
    warnings = [check for check in checks if not check["critical"] and not check["ok"]]
    return {
        "critical_passed": not critical_failures,
        "warning_count": len(warnings),
        "critical_failure_count": len(critical_failures),
        "versions": versions,
        "checks": checks,
    }
