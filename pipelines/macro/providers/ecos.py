from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from core.config.settings import load_settings
from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesDefinition
from pipelines.macro.providers.base import MacroDataProvider, MacroProviderResult


def _disabled_key(value: str) -> bool:
    return str(value or "").strip().lower() in {"", "0", "false", "disabled", "none", "null"}


def _ecos_period(value: str | None, frequency: str, *, default_days: int) -> str:
    text = str(value or "").strip()
    if not text:
        dt = datetime.now(timezone.utc) - timedelta(days=default_days)
        text = dt.date().isoformat()
    clean = text.replace("-", "")
    freq = str(frequency or "").lower()
    if "daily" in freq:
        return clean[:8]
    if "quarter" in freq:
        if len(clean) >= 6:
            month = int(clean[4:6])
            quarter = max(1, min(4, (month - 1) // 3 + 1))
            return f"{clean[:4]}Q{quarter}"
        return clean[:4]
    if len(clean) >= 6:
        return clean[:6]
    return clean[:4]


def _normalise_time(value: str) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-01"
    if len(text) == 4 and text.isdigit():
        return f"{text}-01-01"
    if len(text) == 6 and "Q" in text.upper():
        return text.upper()
    return text


class EcosProvider(MacroDataProvider):
    provider_name = "ecos"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def _api_key(self) -> str:
        if self.api_key is not None:
            return self.api_key
        if "ECOS_API_KEY" in os.environ:
            return str(os.environ.get("ECOS_API_KEY") or "")
        return str(getattr(load_settings(), "ecos_api_key", "") or "")

    def is_available(self) -> bool:
        return not _disabled_key(self._api_key())

    def supports(self, definition: MacroSeriesDefinition) -> bool:
        return definition.provider == self.provider_name

    def fetch_series(
        self,
        definition: MacroSeriesDefinition,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> MacroProviderResult:
        if not self.supports(definition):
            return _unavailable(self.provider_name, definition, f"provider does not support {definition.series_id}")
        api_key = self._api_key()
        if _disabled_key(api_key):
            return _unavailable(self.provider_name, definition, "ECOS_API_KEY is missing.")
        try:
            url = self._url(definition, api_key=api_key, start_date=start_date, end_date=end_date)
            response = httpx.get(url, timeout=float(load_settings().macro_provider_timeout_s))
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            return _unavailable(self.provider_name, definition, f"ecos_provider_error:{exc}")

        rows = self._rows(payload)
        observations: list[MacroObservation] = []
        for row in rows:
            raw_value = row.get("DATA_VALUE")
            if raw_value is None:
                continue
            try:
                value = float(str(raw_value).replace(",", ""))
            except (TypeError, ValueError):
                continue
            period = _normalise_time(str(row.get("TIME") or ""))
            if not period:
                continue
            observations.append(
                MacroObservation(
                    date=period,
                    value=value,
                    raw_value=value,
                    source=self.provider_name,
                    metadata={
                        "stat_code": row.get("STAT_CODE"),
                        "item_code1": row.get("ITEM_CODE1"),
                        "unit": row.get("UNIT_NAME"),
                    },
                )
            )
        observations.sort(key=lambda item: item.date)
        if not observations:
            return _unavailable(self.provider_name, definition, f"ecos_empty_response:{definition.provider_series_id}")
        return MacroProviderResult(
            provider=self.provider_name,
            observations=observations,
            data_quality=MacroDataQuality(
                status="ok",
                provider=self.provider_name,
                last_updated=observations[-1].date,
                notes=["Bank of Korea ECOS StatisticSearch response."],
            ),
        )

    def _url(
        self,
        definition: MacroSeriesDefinition,
        *,
        api_key: str,
        start_date: str | None,
        end_date: str | None,
    ) -> str:
        parts = [part.strip() for part in str(definition.provider_series_id or "").split("/") if part.strip()]
        if len(parts) < 3:
            raise ValueError(f"invalid ECOS provider_series_id: {definition.provider_series_id}")
        stat_code, cycle, *item_codes = parts
        start = _ecos_period(start_date, definition.frequency, default_days=365 * 5)
        end = _ecos_period(end_date, definition.frequency, default_days=0)
        item_path = "/".join(item_codes)
        return f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/10000/{stat_code}/{cycle}/{start}/{end}/{item_path}"

    def _rows(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        root = payload.get("StatisticSearch")
        if not isinstance(root, dict):
            return []
        rows = root.get("row")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
        if isinstance(rows, dict):
            return [rows]
        return []


def _unavailable(provider: str, definition: MacroSeriesDefinition, error: str) -> MacroProviderResult:
    return MacroProviderResult(
        provider=provider,
        observations=[],
        data_quality=MacroDataQuality(
            status="unavailable",
            provider=provider,
            missing_series=[definition.series_id],
            errors=[error],
            notes=["No synthetic macro observations are generated."],
        ),
    )
