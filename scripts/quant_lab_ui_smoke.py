from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.browser_acceptance_matrix import run_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"


def run_quant_lab_smoke(
    *,
    base_url: str | None = None,
    timeout_s: int = 120,
    screenshot_dir: Path = REPORTS_DIR / "browser_ui",
    matrix_output: Path = REPORTS_DIR / "browser_acceptance_latest.json",
    browser_use_status: str = "not_run",
    browser_use_error: str = "",
) -> dict[str, Any]:
    proc: subprocess.Popen[str] | None = None
    started_server = False
    if not base_url:
        port = _find_free_port()
        proc = _start_server(port)
        base_url = f"http://127.0.0.1:{port}"
        started_server = True
        _wait_for_health(base_url, timeout_s=min(45, timeout_s))

    try:
        result = _run_playwright_flow(base_url, timeout_s=timeout_s, screenshot_dir=screenshot_dir)
        run_matrix(
            output=matrix_output,
            browser_use_status=browser_use_status,
            browser_use_error=browser_use_error,
            playwright_status=result["status"],
            fallback_screenshot=result.get("screenshot", ""),
        )
        result.update(
            {
                "base_url": base_url,
                "started_server": started_server,
                "acceptance_matrix": str(matrix_output),
            }
        )
        return result
    finally:
        if proc is not None:
            _stop_server(proc)


def _run_playwright_flow(base_url: str, *, timeout_s: int, screenshot_dir: Path) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    timeout_ms = int(timeout_s * 1000)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshot_dir / f"quant_lab_ui_smoke_{int(time.time())}.png"
    console_errors: list[str] = []
    checked: list[str] = []
    headless = os.environ.get("FINGPT_BROWSER_UI_HEADLESS", "1") != "0"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, args=["--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="ko-KR")
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        try:
            page.goto(f"{base_url.rstrip('/')}/ui/", wait_until="domcontentloaded", timeout=timeout_ms)
            page.locator("#quantLabTab").click()
            _mark(checked, "quant tab")

            for selector in [
                "#backtestFreshnessProfile",
                "#backtestRequireFresh",
                "#backtestUseResearchScore",
                "#portfolioBenchmark",
                "#portfolioCovarianceMethod",
                "#portfolioShrinkageAlpha",
                "#strategyDefinitionJson",
                "#quantStrategyDryRun",
            ]:
                page.locator(selector).wait_for(state="visible", timeout=timeout_ms)
                _mark(checked, selector)

            page.locator("#backtestFreshnessProfile").select_option("historical_lab")
            page.locator("#backtestTicker").fill("SPY,QQQ,TLT")
            page.locator("#backtestStrategy").select_option("momentum_ranking")
            page.locator("#backtestShortWindow").fill("21")
            page.locator("#backtestTopN").fill("2")
            page.locator("#portfolioCovarianceMethod").select_option("diagonal_shrinkage")
            page.locator("#portfolioShrinkageAlpha").fill("0.10")

            page.locator("#quantFeatureRun").click()
            page.locator("#quantFeatureSurface .decision-status-row").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "feature preview")

            page.locator("#quantSignalRun").click()
            page.locator("#quantSignalSurface .decision-status-row").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "signal matrix")

            page.locator("#quantStrategySurface .decision-status-row").wait_for(state="visible", timeout=timeout_ms)
            page.locator("#quantStrategyNewDraft").click()
            page.locator("#quantStrategyDryRun").click()
            page.locator("#quantStrategyResultSurface .decision-status-row").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "strategy governance dry-run")

            page.locator("#backtestRun").click()
            page.locator("#backtestSurface .decision-status-row").wait_for(state="visible", timeout=timeout_ms)
            page.locator('#backtestSurface [data-action="replay-backtest"]').wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "backtest")

            page.locator('#backtestSurface [data-action="replay-backtest"]').click()
            page.locator("text=Replay metric comparison").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "replay comparison")

            page.locator('#backtestSurface [data-action="replay-reports"]').first.click()
            page.locator("text=replay reports").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "replay report history")

            page.locator('#backtestSurface [data-action="export-backtest"][data-format="parquet"]').first.click()
            page.locator("text=PARQUET export").wait_for(state="visible", timeout=timeout_ms)
            page.locator("text=SHA-256").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "artifact parquet export")
            _mark(checked, "artifact export integrity")

            page.locator('#backtestSurface [data-action="verify-export"]').first.click()
            page.locator("text=export integrity verification").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "artifact export verify")

            page.locator('#backtestSurface [data-action="export-history"]').first.click()
            page.locator("text=export manifest").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "artifact export history")

            page.locator('#backtestSurface [data-action="export-cleanup-preview"]').first.click()
            page.locator("text=export cleanup preview").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "artifact export cleanup preview")

            page.locator("#portfolioOptimize").click()
            page.locator("#portfolioSurface .decision-status-row").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "portfolio optimize")

            page.locator("#quantRunHistoryRefresh").click()
            page.locator('#quantRunHistorySurface [data-quant-replay-id]').first.wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "run history replay button")

            page.locator("#quantExportStorageReport").click()
            page.locator("text=cross-run export storage report").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "cross-run export storage report")

            page.locator('#quantRunHistorySurface [data-action="cross-run-cleanup-preview"]').first.click()
            page.locator("text=cross-run export cleanup preview").wait_for(state="visible", timeout=timeout_ms)
            _mark(checked, "cross-run export cleanup preview")

            page.screenshot(path=str(screenshot_path), full_page=True)
            if console_errors:
                raise AssertionError("; ".join(console_errors[:5]))
            return {
                "status": "passed",
                "screenshot": str(screenshot_path),
                "checked": checked,
                "console_errors": console_errors,
            }
        except Exception as exc:  # noqa: BLE001
            failure_path = screenshot_dir / f"quant_lab_ui_smoke_failure_{int(time.time())}.png"
            try:
                page.screenshot(path=str(failure_path), full_page=True)
            except Exception:
                pass
            return {
                "status": "failed",
                "error": str(exc),
                "screenshot": str(failure_path),
                "checked": checked,
                "console_errors": console_errors,
            }
        finally:
            context.close()
            browser.close()


def _mark(checked: list[str], label: str) -> None:
    checked.append(label)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(port: int) -> subprocess.Popen[str]:
    env = dict(os.environ)
    env["FINGPT_WEB_PORT"] = str(port)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.api.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _wait_for_health(base_url: str, *, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url.rstrip('/')}/api/v1/health", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become healthy at {base_url}: {last_error}")


def _stop_server(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a committed Quant Lab browser smoke with Playwright.")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--timeout-s", type=int, default=120)
    parser.add_argument("--screenshot-dir", default=str(REPORTS_DIR / "browser_ui"))
    parser.add_argument("--matrix-output", default=str(REPORTS_DIR / "browser_acceptance_latest.json"))
    parser.add_argument("--browser-use-status", default="not_run", choices=["passed", "failed", "blocked", "not_run"])
    parser.add_argument("--browser-use-error", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_quant_lab_smoke(
        base_url=args.base_url or None,
        timeout_s=args.timeout_s,
        screenshot_dir=Path(args.screenshot_dir),
        matrix_output=Path(args.matrix_output),
        browser_use_status=args.browser_use_status,
        browser_use_error=args.browser_use_error,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
