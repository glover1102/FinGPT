# Runtime preflight checks and environment guards for quant_stack.
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import importlib.metadata as metadata
import os
import platform
import socket
import sys
from typing import Any
from urllib.parse import urlparse
import uuid

from .config import (
    EMBEDDING_MODEL,
    ENV_EXAMPLE_PATH,
    EXPECTED_ACCELERATE_VERSION,
    EXPECTED_BITSANDBYTES_VERSION,
    EXPECTED_OPENBB_VERSION,
    EXPECTED_PEFT_VERSION,
    EXPECTED_PLATFORM,
    EXPECTED_PYTHON_MINOR,
    EXPECTED_QDRANT_CLIENT_VERSION,
    EXPECTED_TORCH_VERSION,
    EXPECTED_TRANSFORMERS_VERSION,
    Settings,
)
from .pipeline import get_qdrant_client


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def runtime_snapshot() -> dict[str, Any]:
    return {
        "python_executable": sys.executable,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": platform.python_version(),
    }


def ensure_supported_runtime() -> None:
    if platform.system() != EXPECTED_PLATFORM:
        raise RuntimeError(
            "quant_stack must run inside WSL Ubuntu/Linux. "
            f"Current platform is {platform.system()}. Activate your WSL Python environment first."
        )
    if sys.version_info[:2] != (3, EXPECTED_PYTHON_MINOR):
        raise RuntimeError(
            f"quant_stack requires Python 3.{EXPECTED_PYTHON_MINOR}. "
            f"Current version is {platform.python_version()}."
        )


def ensure_expected_version(dist_name: str, expected: str) -> str:
    installed = metadata.version(dist_name)
    if installed != expected:
        raise RuntimeError(f"{dist_name} version mismatch: expected {expected}, found {installed}.")
    return installed


def configure_huggingface_env(settings: Settings) -> None:
    if settings.hf_token:
        os.environ["HF_TOKEN"] = settings.hf_token
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = settings.hf_token
        os.environ["HUGGING_FACE_HUB_TOKEN"] = settings.hf_token


def inject_openbb_credentials(obb: Any, settings: Settings) -> bool:
    if not settings.fmp_api_key:
        return False
    credentials = getattr(getattr(obb, "user", None), "credentials", None)
    if credentials is None or not hasattr(credentials, "fmp_api_key"):
        return False
    setattr(credentials, "fmp_api_key", settings.fmp_api_key)
    return True


def import_openbb_with_credentials(settings: Settings):
    version = ensure_expected_version("openbb", EXPECTED_OPENBB_VERSION)
    from openbb import obb

    injected = inject_openbb_credentials(obb, settings)
    return obb, version, injected


def has_openbb_fmp_key(obb: Any) -> bool:
    credentials = getattr(getattr(obb, "user", None), "credentials", None)
    return bool(getattr(credentials, "fmp_api_key", None)) if credentials is not None else False


def quarter_from_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def previous_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year, quarter - 1) if quarter > 1 else (year - 1, 4)


def candidate_transcript_periods(start_date_text: str, end_date_text: str) -> list[tuple[int, int]]:
    start = date.fromisoformat(start_date_text)
    end = date.fromisoformat(end_date_text)
    start_pair = (start.year, quarter_from_month(start.month))
    end_pair = (end.year, quarter_from_month(end.month))
    return sorted({start_pair, end_pair, previous_quarter(*start_pair)})


def classify_transcript_error(exc: Exception) -> str:
    text = str(exc).lower()
    if any(token in text for token in ("api key", "credential", "401", "403", "unauthorized", "forbidden")):
        return "credentials missing"
    if any(token in text for token in ("not found", "404", "no data", "empty")):
        return "no transcript in date range"
    return "provider/network failure"


def parse_qdrant_target(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError(f"QDRANT_URL must be a full http/https URL. Found: {url}")
    return parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def check_openbb(settings: Settings) -> CheckResult:
    result = CheckResult(name="openbb", ok=False, details=runtime_snapshot())
    try:
        ensure_supported_runtime()
        obb, version, injected = import_openbb_with_credentials(settings)
        result.details.update(
            {
                "openbb_version": version,
                "obb_import": True,
                "project_fmp_key_present": bool(settings.fmp_api_key),
                "openbb_fmp_key_present": has_openbb_fmp_key(obb),
                "fmp_key_injected_from_project_env": injected,
            }
        )
        if not settings.fmp_api_key:
            result.warnings.append(
                "FMP_API_KEY is empty. Transcript collection will soft-skip and only news documents will be collected."
            )
        result.ok = True
    except Exception as exc:
        result.details["error"] = str(exc)
        result.fixes.extend(
            [
                "Run quant_stack inside WSL Ubuntu with Python 3.12.",
                "Activate your Linux virtualenv before running: . venv/bin/activate",
                "Reinstall pinned dependencies: pip install -r quant_stack/requirements-quant-stack.txt -c quant_stack/constraints-quant-stack.txt",
                f"Copy {ENV_EXAMPLE_PATH.name} to .env and set FMP_API_KEY if you want transcripts.",
            ]
        )
    return result


def check_qdrant(settings: Settings) -> CheckResult:
    result = CheckResult(name="qdrant", ok=False, details={"qdrant_url": settings.qdrant_url})
    try:
        result.details["qdrant_client_version"] = ensure_expected_version("qdrant-client", EXPECTED_QDRANT_CLIENT_VERSION)
        host, port = parse_qdrant_target(settings.qdrant_url)
        result.details["parsed_host"] = host
        result.details["parsed_port"] = port
        with socket.create_connection((host, port), timeout=3):
            result.details["tcp_connect"] = True

        client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key, enable_embeddings=False)
        collections = client.get_collections()
        result.details["collection_count"] = len(getattr(collections, "collections", []) or [])
        result.details["auth_mode"] = "api_key" if settings.qdrant_api_key else "none"

        temp_collection = f"doctor_{uuid.uuid4().hex[:8]}"
        from qdrant_client import models

        client.create_collection(
            collection_name=temp_collection,
            vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE),
        )
        client.delete_collection(temp_collection)
        result.details["create_delete_permission"] = True

        fastembed_client = get_qdrant_client(location=":memory:")
        result.details["fastembed_model"] = EMBEDDING_MODEL
        result.details["fastembed_embedding_size"] = fastembed_client.get_embedding_size()
        result.ok = True
    except Exception as exc:
        result.details["error"] = str(exc)
        result.fixes.extend(
            [
                "Start Qdrant locally: docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:latest",
                "If you are using Qdrant Cloud, set QDRANT_URL and QDRANT_API_KEY in quant_stack/.env.",
                "Reinstall the pinned client: pip install -r quant_stack/requirements-quant-stack.txt -c quant_stack/constraints-quant-stack.txt",
            ]
        )
    return result


def check_model(settings: Settings) -> CheckResult:
    result = CheckResult(
        name="model",
        ok=False,
        details={
            "base_model_name": settings.base_model_name,
            "adapter_model_name": settings.adapter_model_name,
            "enable_4bit": settings.enable_4bit,
        },
    )
    try:
        ensure_supported_runtime()
        result.details["torch_version"] = ensure_expected_version("torch", EXPECTED_TORCH_VERSION)
        result.details["transformers_version"] = ensure_expected_version("transformers", EXPECTED_TRANSFORMERS_VERSION)
        result.details["peft_version"] = ensure_expected_version("peft", EXPECTED_PEFT_VERSION)
        result.details["accelerate_version"] = ensure_expected_version("accelerate", EXPECTED_ACCELERATE_VERSION)
        result.details["bitsandbytes_version"] = ensure_expected_version("bitsandbytes", EXPECTED_BITSANDBYTES_VERSION)

        if not settings.hf_token:
            raise RuntimeError("HF_TOKEN is empty. The base model is gated and cannot be checked anonymously.")

        configure_huggingface_env(settings)
        from huggingface_hub import HfApi
        import bitsandbytes  # noqa: F401
        import torch
        from transformers import BitsAndBytesConfig  # noqa: F401

        api = HfApi(token=settings.hf_token)
        api.model_info(settings.base_model_name, token=settings.hf_token)
        api.model_info(settings.adapter_model_name, token=settings.hf_token)

        result.details["hf_token_present"] = True
        result.details["base_model_access"] = True
        result.details["adapter_model_access"] = True
        result.details["cuda_available"] = torch.cuda.is_available()

        if settings.enable_4bit and not torch.cuda.is_available():
            result.warnings.append("CUDA is not available. 4bit loading will fall back to fp32 CPU and be slow.")
        elif settings.enable_4bit:
            result.details["bitsandbytes_4bit_ready"] = True

        result.ok = True
    except Exception as exc:
        result.details["error"] = str(exc)
        result.fixes.extend(
            [
                "Set HF_TOKEN in quant_stack/.env.",
                "Request Llama 2 access on Hugging Face for meta-llama/Llama-2-7b-hf.",
                "Reinstall the pinned stack: pip install -r quant_stack/requirements-quant-stack.txt -c quant_stack/constraints-quant-stack.txt",
                "If CUDA is unavailable, set ENABLE_4BIT=false to use fp32 CPU fallback.",
            ]
        )
    return result


def run_checks(settings: Settings, check_name: str) -> list[CheckResult]:
    if check_name == "openbb":
        return [check_openbb(settings)]
    if check_name == "qdrant":
        return [check_qdrant(settings)]
    if check_name == "model":
        return [check_model(settings)]
    return [check_openbb(settings), check_qdrant(settings), check_model(settings)]
