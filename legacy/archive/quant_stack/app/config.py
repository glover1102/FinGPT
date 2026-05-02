# Shared environment and filesystem configuration for the quant_stack pipeline.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
REPO_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"

DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_QDRANT_API_KEY = ""
DEFAULT_SYMBOL = "AAPL"
DEFAULT_START_DATE = "2026-04-01"
DEFAULT_END_DATE = "2026-04-13"
DEFAULT_FMP_API_KEY = ""
DEFAULT_HF_TOKEN = ""
DEFAULT_BASE_MODEL_NAME = "meta-llama/Llama-2-7b-hf"
DEFAULT_ADAPTER_MODEL_NAME = "FinGPT/fingpt-mt_llama2-7b_lora"
DEFAULT_ENABLE_4BIT = True
DEFAULT_MAX_NEW_TOKENS = 384

COLLECTION_NAME = "market_docs"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_SEARCH_QUERY = "What are the most important short-term risks and catalysts for AAPL?"

EXPECTED_OPENBB_VERSION = "4.7.1"
EXPECTED_QDRANT_CLIENT_VERSION = "1.17.1"
EXPECTED_TORCH_VERSION = "2.11.0"
EXPECTED_TRANSFORMERS_VERSION = "4.57.6"
EXPECTED_PEFT_VERSION = "0.18.1"
EXPECTED_ACCELERATE_VERSION = "1.13.0"
EXPECTED_BITSANDBYTES_VERSION = "0.49.2"
EXPECTED_PYTHON_MINOR = 12
EXPECTED_PLATFORM = "Linux"

load_dotenv(ENV_PATH, override=False)


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    qdrant_url: str
    qdrant_api_key: str
    symbol: str
    start_date: str
    end_date: str
    fmp_api_key: str
    hf_token: str
    base_model_name: str
    adapter_model_name: str
    enable_4bit: bool
    max_new_tokens: int
    collection_name: str = COLLECTION_NAME

    @property
    def raw_docs_path(self) -> Path:
        return RAW_DIR / f"{self.symbol}_docs.json"


def ensure_directories() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    ensure_directories()
    return Settings(
        qdrant_url=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL).strip() or DEFAULT_QDRANT_URL,
        qdrant_api_key=os.getenv("QDRANT_API_KEY", DEFAULT_QDRANT_API_KEY).strip(),
        symbol=(os.getenv("SYMBOL", DEFAULT_SYMBOL).strip() or DEFAULT_SYMBOL).upper(),
        start_date=os.getenv("START_DATE", DEFAULT_START_DATE).strip() or DEFAULT_START_DATE,
        end_date=os.getenv("END_DATE", DEFAULT_END_DATE).strip() or DEFAULT_END_DATE,
        fmp_api_key=os.getenv("FMP_API_KEY", DEFAULT_FMP_API_KEY).strip(),
        hf_token=os.getenv("HF_TOKEN", DEFAULT_HF_TOKEN).strip(),
        base_model_name=os.getenv("BASE_MODEL_NAME", DEFAULT_BASE_MODEL_NAME).strip() or DEFAULT_BASE_MODEL_NAME,
        adapter_model_name=os.getenv("ADAPTER_MODEL_NAME", DEFAULT_ADAPTER_MODEL_NAME).strip()
        or DEFAULT_ADAPTER_MODEL_NAME,
        enable_4bit=_to_bool(os.getenv("ENABLE_4BIT"), DEFAULT_ENABLE_4BIT),
        max_new_tokens=int(os.getenv("MAX_NEW_TOKENS", str(DEFAULT_MAX_NEW_TOKENS)).strip() or DEFAULT_MAX_NEW_TOKENS),
    )
