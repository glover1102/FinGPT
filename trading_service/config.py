from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    fingpt_model_name: str = "FinGPT/fingpt-sentiment_llama2-13b_lora"
    base_model_name: str = "meta-llama/Llama-2-7b-chat-hf"
    use_8bit: bool = True
    hf_token: str | None = None

    port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    finnhub_api_key: str = ""

    cache_ttl_seconds: int = 3600
    max_cache_size: int = 1000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

