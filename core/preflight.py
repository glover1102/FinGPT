"""
Preflight / Startup Environment Verification
============================================
Checks all required runtime dependencies at operator startup.
Not user-facing. Designed for operator clarity and fast failure diagnosis.

Rules:
- CRITICAL failures (missing keys, unreachable services) are logged as ERROR
  and returned as a structured report.
- WARNINGS (missing optional credentials) are non-blocking.
- This module must not import pipeline stages; it is a pure diagnostic probe.
"""

from __future__ import annotations

import csv
import io
import subprocess
from urllib.parse import urlparse

import httpx

from core.config.settings import load_settings
from core.utils.openbb_agent_compat import check_openbb_agent_contract
from core.utils.logger import get_logger
from core.utils.openbb_compat import build_openbb_compat_report
from core.utils.provider_versions import build_provider_version_report

logger = get_logger("core.preflight")

_LOCAL_QDRANT_HOSTS = {"127.0.0.1", "::1", "localhost"}
_QDRANT_CONTAINER_NAME = "fingpt-qdrant"
_QDRANT_SMOKE_COLLECTION = "__preflight_smoke__"


def _http_get(url: str, timeout: float, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.get(url, timeout=timeout, headers=headers)


def _http_get_with_retry(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    attempts: int = 2,
    retry_statuses: set[int] | None = None,
) -> tuple[httpx.Response | None, str | None]:
    retry_statuses = retry_statuses or {429, 500, 502, 503, 504}
    last_error: str | None = None
    last_response: httpx.Response | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            response = _http_get(url, timeout=timeout, headers=headers)
            last_response = response
            if response.status_code not in retry_statuses:
                return response, None
            last_error = f"status {response.status_code}"
        except httpx.TimeoutException:
            last_error = "timeout"
        except Exception as exc:
            last_error = str(exc)
            break
    return last_response, last_error


def _run_command(command: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


def _parse_qdrant_target(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"QDRANT_URL must be a full http/https URL. Found: {url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _is_local_qdrant_url(url: str) -> bool:
    host, _ = _parse_qdrant_target(url)
    return host in _LOCAL_QDRANT_HOSTS


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _docker_command_available() -> bool:
    try:
        result = _run_command(["docker", "--version"])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _docker_daemon_available() -> bool:
    try:
        result = _run_command(["docker", "info"])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _get_qdrant_container_status() -> str | None:
    try:
        result = _run_command(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^/{_QDRANT_CONTAINER_NAME}$",
                "--format",
                "{{.Names}}|{{.Status}}",
            ]
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        cleaned = _clean_text(line)
        if not cleaned:
            continue
        parts = cleaned.split("|", 1)
        if len(parts) == 2 and parts[0] == _QDRANT_CONTAINER_NAME:
            return parts[1]
    return None


def _parse_windows_tasklist_name(output: str) -> str:
    cleaned = _clean_text(output)
    if not cleaned or cleaned.startswith("INFO:"):
        return ""
    try:
        row = next(csv.reader(io.StringIO(output)))
        return row[0].strip() if row else ""
    except Exception:
        return cleaned.split(",", 1)[0].strip("\" ")


def _get_local_port_process(port: int) -> dict[str, int | str] | None:
    try:
        result = _run_command(["netstat", "-ano", "-p", "tcp"])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    pid: int | None = None
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, local_address, _, state, owning_pid = parts[:5]
        if proto.upper() != "TCP" or state.upper() != "LISTENING":
            continue
        if local_address.endswith(f":{port}") or local_address == f"[::]:{port}":
            try:
                pid = int(owning_pid)
                break
            except ValueError:
                continue

    if pid is None:
        return None

    process_name = ""
    try:
        task_result = _run_command(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"])
        if task_result.returncode == 0:
            process_name = _parse_windows_tasklist_name(task_result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        process_name = ""

    return {"pid": pid, "name": process_name or "unknown"}


def _diagnose_local_qdrant_failure(settings, *, timeout: bool) -> str:
    _, port = _parse_qdrant_target(settings.qdrant_url)

    if not _docker_command_available():
        return (
            "Docker CLI is not installed or not on PATH. "
            "Install Docker Desktop and reopen PowerShell before starting local Qdrant."
        )

    if not _docker_daemon_available():
        return (
            "Docker Desktop is installed, but the Docker daemon is not reachable. "
            "Start Docker Desktop before running the local Qdrant baseline."
        )

    container_status = _get_qdrant_container_status()
    port_process = _get_local_port_process(port)

    if port_process and (not container_status or not container_status.lower().startswith("up")):
        return (
            f"Port {port} is already occupied by process '{port_process['name']}' "
            f"(PID {port_process['pid']}). Stop that process or free the port before starting local Qdrant."
        )

    if container_status and not container_status.lower().startswith("up"):
        return (
            f"Qdrant container '{_QDRANT_CONTAINER_NAME}' is not running ({container_status}). "
            "Run `docker compose up -d qdrant` from the repo root."
        )

    if timeout:
        return (
            f"Qdrant did not respond at {settings.qdrant_url} before the timeout. "
            f"If the container just started, wait and retry or inspect `docker logs {_QDRANT_CONTAINER_NAME}`."
        )

    return (
        f"Local Qdrant is unavailable at {settings.qdrant_url}. "
        "Run `docker compose up -d qdrant` from the repo root."
    )


def _check_fmp_key(settings) -> tuple[str, bool, str]:
    """Verify FMP API key is present and the stable API endpoint responds."""
    name = "FMP_API_KEY"
    if not getattr(settings, "fmp_enabled", False):
        return name, True, "Disabled - FMP is auxiliary and FMP_ENABLED=false."
    if not settings.fmp_api_key:
        return name, False, "Missing - set FMP_API_KEY in .env"
    try:
        url = f"https://financialmodelingprep.com/stable/profile?symbol=MSFT&apikey={settings.fmp_api_key}"
        resp = _http_get(url, timeout=8.0)
        if resp.status_code == 200:
            return name, True, "Valid - stable/profile probe: 200 OK"
        if resp.status_code == 403:
            return name, False, "Key rejected by FMP (403). Key may be expired or revoked."
        return name, False, f"FMP probe returned unexpected status {resp.status_code}"
    except httpx.TimeoutException:
        return name, False, "FMP API unreachable - connection timed out"
    except Exception as e:
        return name, False, f"FMP probe error: {e}"


def _check_transcript_provider(settings) -> tuple[str, bool, str]:
    """Verify the direct FMP transcript-dates endpoint used by the runtime transcript adapter."""
    name = "TRANSCRIPT_PROVIDER"
    transcript_policy = str(getattr(settings, "transcript_provider", "fmp_optional") or "").strip().lower()
    if not getattr(settings, "fmp_enabled", False) or transcript_policy in {"disabled", "none", "off"}:
        return name, True, "Disabled - transcript collection is auxiliary and not in the default hot path."
    if not settings.fmp_api_key:
        return name, False, "Skipped - FMP_API_KEY is missing, so transcript collection will be disabled."

    try:
        response = _http_get(
            (
                "https://financialmodelingprep.com/stable/"
                f"earning-call-transcript-dates?symbol=MSFT&apikey={settings.fmp_api_key}"
            ),
            timeout=8.0,
        )
        if response.status_code == 200:
            rows = response.json()
            count = len(rows) if isinstance(rows, list) else 0
            return name, True, f"Operational - transcript-dates probe returned {count} row(s) for MSFT"
        if response.status_code in (401, 403):
            return name, False, "Transcript provider rejected FMP_API_KEY."
        if response.status_code == 402:
            return name, False, "entitlement_required - FMP transcript endpoint requires account plan/API entitlement."
        if response.status_code == 429:
            return name, False, "Transcript provider is rate-limiting requests."
        return name, False, f"Transcript provider returned unexpected status {response.status_code}"
    except httpx.TimeoutException:
        return name, False, "Transcript provider timed out."
    except Exception as e:
        return name, False, f"Transcript provider probe error: {e}"


def _check_fmp_stock_news(settings) -> tuple[str, bool, str]:
    """Verify the direct FMP stock-news endpoint used as the secondary primary news provider."""
    name = "FMP_STOCK_NEWS"
    if not getattr(settings, "fmp_enabled", False):
        return name, True, "Disabled - FMP stock news is auxiliary and FMP_ENABLED=false."
    if not settings.fmp_api_key:
        return name, False, "Skipped - FMP_API_KEY is missing, so FMP stock news fallback will be disabled."

    try:
        response = _http_get(
            (
                "https://financialmodelingprep.com/stable/"
                f"news/stock?symbols=MSFT&limit=1&apikey={settings.fmp_api_key}"
            ),
            timeout=8.0,
        )
        if response.status_code == 200:
            rows = response.json()
            count = len(rows) if isinstance(rows, list) else 0
            return name, True, f"Operational - stock-news probe returned {count} row(s) for MSFT"
        if response.status_code in (401, 403):
            return name, False, "FMP stock news rejected FMP_API_KEY."
        if response.status_code == 402:
            return name, False, "entitlement_required - FMP stock news endpoint requires account plan/API entitlement."
        if response.status_code == 429:
            return name, False, "FMP stock news is rate-limiting requests."
        return name, False, f"FMP stock news returned unexpected status {response.status_code}"
    except httpx.TimeoutException:
        return name, False, "FMP stock news timed out."
    except Exception as e:
        return name, False, f"FMP stock news probe error: {e}"


def _check_sec_filings(settings) -> tuple[str, bool, str]:
    """Verify the no-key SEC EDGAR fallback used for sparse-ticker news coverage."""
    name = "SEC_FILINGS"
    headers = {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }
    try:
        response = _http_get(
            "https://www.sec.gov/files/company_tickers_exchange.json",
            timeout=8.0,
            headers=headers,
        )
        if response.status_code == 200:
            payload = response.json()
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            count = len(rows) if isinstance(rows, list) else 0
            return name, True, f"Operational - SEC ticker map returned {count} row(s)"
        if response.status_code == 429:
            return name, False, "SEC EDGAR is rate-limiting requests; check request cadence and SEC_USER_AGENT."
        if response.status_code in (403, 451):
            return name, False, "SEC EDGAR rejected the request; set a valid SEC_USER_AGENT with operator contact."
        return name, False, f"SEC EDGAR returned unexpected status {response.status_code}"
    except httpx.TimeoutException:
        return name, False, "SEC EDGAR timed out."
    except Exception as e:
        return name, False, f"SEC EDGAR probe error: {e}"


def _check_fred_macro(settings) -> tuple[str, bool, str]:
    """Verify FRED macro API access for rates/bonds and macro-sensitive topics."""
    name = "FRED_MACRO"
    if not settings.fred_api_key:
        return name, False, "FRED_API_KEY is missing; macro runs will fall back to price/news proxies."
    try:
        response, retry_error = _http_get_with_retry(
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=DGS10&api_key={settings.fred_api_key}&file_type=json&limit=1",
            timeout=8.0,
            attempts=2,
        )
        if response is None:
            return name, False, f"FRED probe failed after retry: {retry_error or 'no response'}"
        if response.status_code == 200:
            rows = response.json().get("observations", [])
            count = len(rows) if isinstance(rows, list) else 0
            return name, True, f"Operational - DGS10 observations endpoint returned {count} row(s)"
        if response.status_code in (401, 403):
            return name, False, "FRED rejected FRED_API_KEY."
        if response.status_code == 429:
            return name, False, "FRED is rate-limiting requests after retry; Yahoo price/rate proxies remain fallback inputs."
        if response.status_code >= 500:
            return name, False, f"FRED upstream returned {response.status_code} after retry; macro runs should use fallback proxies."
        return name, False, f"FRED returned unexpected status {response.status_code}"
    except httpx.TimeoutException:
        return name, False, "FRED timed out."
    except Exception as e:
        return name, False, f"FRED probe error: {e}"


def _check_alpha_vantage_news(settings) -> tuple[str, bool, str]:
    """Verify optional Alpha Vantage news access without making it a hard dependency."""
    name = "ALPHA_VANTAGE_NEWS"
    if not getattr(settings, "alpha_vantage_enabled", False):
        return name, True, "Disabled - Alpha Vantage news is optional and ALPHA_VANTAGE_ENABLED=false."
    if not settings.alpha_vantage_api_key:
        return name, False, "ALPHA_VANTAGE_API_KEY is missing."
    try:
        response = _http_get(
            "https://www.alphavantage.co/query"
            f"?function=NEWS_SENTIMENT&tickers=MSFT&limit=1&apikey={settings.alpha_vantage_api_key}",
            timeout=10.0,
        )
        if response.status_code != 200:
            return name, False, f"Alpha Vantage returned unexpected status {response.status_code}"
        payload = response.json()
        if isinstance(payload, dict) and payload.get("feed"):
            return name, True, f"Operational - news endpoint returned {len(payload.get('feed') or [])} item(s)"
        if isinstance(payload, dict) and (payload.get("Information") or payload.get("Note")):
            return (
                name,
                True,
                "Optional provider degraded - Alpha Vantage returned a rate-limit or plan message; Yahoo/SEC/Google/OpenBB remain primary.",
            )
        if isinstance(payload, dict) and payload.get("Error Message"):
            return name, False, "Alpha Vantage rejected the request."
        return name, True, "Optional provider returned no feed records; primary providers remain available."
    except httpx.TimeoutException:
        return name, False, "Alpha Vantage timed out."
    except Exception as e:
        return name, False, f"Alpha Vantage probe error: {e}"


def _check_openbb_package(settings) -> tuple[str, bool, str]:
    """Verify OpenBB package compatibility without putting it on the hot path."""
    name = "OPENBB_PACKAGE"
    if not getattr(settings, "openbb_enabled", True):
        return name, True, "Disabled - OpenBB adapter disabled by OPENBB_ENABLED=false."
    report = build_provider_version_report(require_openbb_agent=bool(getattr(settings, "openbb_agent_enabled", False)))
    version_text = ", ".join(f"{package}={version}" for package, version in report["versions"].items())
    if not report["critical_passed"]:
        return name, False, "; ".join(report["critical_failures"])
    warning_text = f"; warnings={len(report['warnings'])}" if report["warnings"] else ""
    return name, True, f"Installed within policy - {version_text}{warning_text}"


def _check_openbb_news_runtime(settings) -> tuple[str, bool, str]:
    """OpenBB news is optional until its provider stack passes the compatibility gate."""
    name = "OPENBB_NEWS_RUNTIME"
    if not getattr(settings, "openbb_enabled", True):
        return name, True, "Disabled - OpenBB adapter disabled by OPENBB_ENABLED=false."
    if not getattr(settings, "openbb_news_enabled", False):
        return name, True, "Disabled - OPENBB_NEWS_ENABLED=false; direct Yahoo/SEC/Google providers are used."
    report = build_openbb_compat_report(
        sec_user_agent=settings.sec_user_agent,
        include_pip_check=False,
        include_network_smoke=False,
        include_openbb_news_runtime=True,
    )
    check = next((item for item in report["checks"] if item["name"] == "openbb_news_company"), None)
    if not check:
        return name, False, "OpenBB news runtime check did not return a result."
    return name, bool(check["ok"]), str(check["detail"])


def _check_hf_token(settings) -> tuple[str, bool, str]:
    """Verify HuggingFace token presence. Ollama is the production inference backend."""
    name = "HF_TOKEN"
    if not settings.hf_token:
        return name, True, "Not required - inference backend is Ollama (local). HF_TOKEN only needed for HuggingFace model downloads."
    return name, True, "Present (not used by current Ollama backend)"


def _check_qdrant_service(settings) -> tuple[str, bool, str]:
    """Verify the configured Qdrant endpoint is reachable and classify local failures."""
    name = "QDRANT_SERVICE"
    headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else None
    try:
        resp = _http_get(f"{settings.qdrant_url}/collections", timeout=5.0, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            n = len(data.get("result", {}).get("collections", []))
            return name, True, f"Reachable at {settings.qdrant_url} - {n} collection(s)"
        return name, False, f"Qdrant responded with unexpected status {resp.status_code}"
    except httpx.TimeoutException:
        if _is_local_qdrant_url(settings.qdrant_url):
            return name, False, _diagnose_local_qdrant_failure(settings, timeout=True)
        return name, False, f"Qdrant timed out at {settings.qdrant_url}"
    except httpx.ConnectError:
        if _is_local_qdrant_url(settings.qdrant_url):
            return name, False, _diagnose_local_qdrant_failure(settings, timeout=False)
        return name, False, f"Qdrant is unreachable at {settings.qdrant_url}"
    except Exception as e:
        return name, False, f"Qdrant probe error: {e}"


def _check_qdrant_query_stack(settings) -> tuple[str, bool, str]:
    """Verify the in-memory add/query path used by runtime retrieval helpers is ready."""
    name = "QDRANT_QUERY_STACK"
    try:
        from core.utils.qdrant_helpers import (
            add_documents_to_qdrant,
            ensure_collection,
            get_qdrant_client,
            search_documents,
        )

        client = get_qdrant_client(location=":memory:", enable_embeddings=True)
        ensure_collection(client, _QDRANT_SMOKE_COLLECTION)
        add_documents_to_qdrant(
            client=client,
            collection_name=_QDRANT_SMOKE_COLLECTION,
            documents=["Microsoft Azure demand remains resilient in enterprise workloads."],
            metadata=[{"doc_id": "preflight-doc-1", "ticker": "MSFT", "symbol": "MSFT"}],
            batch_size=1,
        )
        hits = search_documents(
            client=client,
            collection_name=_QDRANT_SMOKE_COLLECTION,
            symbol="MSFT",
            query_text="Azure demand",
            limit=1,
        )
        if not hits:
            return name, False, "Qdrant is up but retrieval stack is not ready: smoke query returned no hits."
        return name, True, "Ready - in-memory embeddings, add(), and query() passed a smoke test"
    except Exception as e:
        return name, False, f"Qdrant is up but retrieval stack is not ready: {e}"


def _check_qdrant_collection_schema(settings) -> tuple[str, bool, str]:
    """Inspect the configured persistent collection for hybrid sparse support."""
    name = "QDRANT_COLLECTION_SCHEMA"
    if not getattr(settings, "hybrid_search_enabled", True):
        return name, True, "Hybrid search disabled; dense collection schema is acceptable."
    try:
        from core.utils.qdrant_helpers import (
            collection_has_sparse_vectors,
            ensure_collection,
            ensure_sparse_vectors,
            get_qdrant_client,
        )

        client = get_qdrant_client(
            settings.qdrant_url,
            settings.qdrant_api_key,
            enable_embeddings=True,
        )
        ensure_collection(client, settings.collection_name)
        if collection_has_sparse_vectors(client, settings.collection_name) is True:
            return name, True, f"Hybrid-ready - collection '{settings.collection_name}' has sparse vectors."
        if ensure_sparse_vectors(client, settings.collection_name, settings=settings):
            return name, True, f"Auto-migrated - collection '{settings.collection_name}' now has sparse vectors."
        return (
            name,
            False,
            f"warning-only dense fallback active - collection '{settings.collection_name}' has no sparse vectors.",
        )
    except Exception as e:
        return name, False, f"warning-only schema probe unavailable: {e}"


def _check_yfinance_feed() -> tuple[str, bool, str]:
    """Verify yfinance can fetch news (no auth required - tests network and library)."""
    name = "YFINANCE_FEED"
    try:
        import yfinance as yf

        news = yf.Ticker("MSFT").news
        if isinstance(news, list) and len(news) > 0:
            return name, True, f"Operational - {len(news)} articles available for MSFT"
        if isinstance(news, list):
            return name, False, "yfinance returned an empty news list - possible rate-limit or API change"
        return name, False, f"Unexpected yfinance news type: {type(news)}"
    except Exception as e:
        return name, False, f"yfinance probe error: {e}"


def _check_ollama(settings) -> tuple[str, bool, str]:
    """Verify Ollama service is reachable on local port."""
    name = "OLLAMA_SERVICE"
    try:
        _http_get(settings.ollama_base_url, timeout=5.0)
        return name, True, f"Running at {settings.ollama_base_url}"
    except httpx.ConnectError:
        return name, False, f"Unreachable at {settings.ollama_base_url} - ensure Ollama desktop app is running."
    except httpx.TimeoutException:
        return name, False, f"Ollama timed out at {settings.ollama_base_url}"
    except Exception as e:
        return name, False, f"Ollama probe error: {e}"


def _check_ollama_model(settings) -> tuple[str, bool, str]:
    """Verify the target production model is installed in Ollama."""
    name = f"OLLAMA_MODEL ({settings.primary_model})"
    expected_model = "qwen2.5:7b"
    if str(settings.primary_model).strip() != expected_model:
        return name, False, f"PRIMARY_MODEL mismatch - expected {expected_model}, configured {settings.primary_model}"
    try:
        resp = _http_get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
        if resp.status_code != 200:
            return name, False, f"Cannot check models - Ollama returned {resp.status_code}"
        installed = [m.get("name", "") for m in resp.json().get("models", [])]
        if any(settings.primary_model in n for n in installed):
            return name, True, f"Installed - inference backend=ollama model={settings.primary_model}"
        return name, False, (
            f"Model '{settings.primary_model}' not found. "
            f"Run: `ollama pull {settings.primary_model}`\n"
            f"  Installed: {installed}"
        )
    except Exception as e:
        return name, False, f"Model check error: {e}"


def run_preflight() -> dict:
    """
    Run all preflight checks and return a structured report.
    Logs each result at the appropriate level.
    Returns: {"passed": bool, "checks": [{"name", "ok", "detail"}, ...]}
    """
    settings = load_settings()
    logger.info("=" * 60)
    logger.info("PREFLIGHT ENVIRONMENT VERIFICATION")
    logger.info("=" * 60)

    probes = [
        _check_hf_token(settings),
        _check_qdrant_service(settings),
        _check_qdrant_query_stack(settings),
        _check_qdrant_collection_schema(settings),
        _check_openbb_package(settings),
        _check_openbb_news_runtime(settings),
        check_openbb_agent_contract(settings),
        _check_yfinance_feed(),
        _check_sec_filings(settings),
        _check_fred_macro(settings),
        _check_alpha_vantage_news(settings),
        _check_fmp_key(settings),
        _check_fmp_stock_news(settings),
        _check_transcript_provider(settings),
        _check_ollama(settings),
        _check_ollama_model(settings),
    ]

    checks = []
    has_critical_failure = False
    warning_only = {
        "HF_TOKEN",
        "FMP_API_KEY",
        "FMP_STOCK_NEWS",
        "SEC_FILINGS",
        "FRED_MACRO",
        "ALPHA_VANTAGE_NEWS",
        "QDRANT_COLLECTION_SCHEMA",
        "TRANSCRIPT_PROVIDER",
        "OPENBB_NEWS_RUNTIME",
        "OPENBB_AGENT_CONTRACT",
    }

    for name, ok, detail in probes:
        check = {"name": name, "ok": ok, "detail": detail}
        checks.append(check)
        symbol = "OK" if ok else "FAIL"
        is_warning_only = any(w in name for w in warning_only)
        if not ok and not is_warning_only:
            has_critical_failure = True
            logger.error(f"  [{symbol}] {name}: {detail}")
        else:
            level = logger.info if ok else logger.warning
            level(f"  [{symbol}] {name}: {detail}")

    logger.info("=" * 60)
    if has_critical_failure:
        logger.error("PREFLIGHT: One or more CRITICAL dependencies are unavailable. Pipeline will fail.")
    else:
        logger.info("PREFLIGHT: All critical dependencies are operational.")

    return {"passed": not has_critical_failure, "checks": checks}


if __name__ == "__main__":
    import sys

    report = run_preflight()
    if not report["passed"]:
        sys.exit(1)
    sys.exit(0)
