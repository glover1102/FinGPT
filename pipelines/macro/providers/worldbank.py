from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from core.config.settings import load_settings
from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesDefinition
from pipelines.macro.providers.base import MacroDataProvider, MacroProviderResult


_COUNTRY_ALIASES = {
    "GLOBAL": "all",
    "US": "USA",
    "KR": "KOR",
}


def _year(value: str | None) -> str | None:
    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return None


class WorldBankProvider(MacroDataProvider):
    provider_name = "worldbank"

    def is_available(self) -> bool:
        return True

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

        country = _COUNTRY_ALIASES.get(str(definition.country or "").upper(), str(definition.country or "all"))
        url = f"https://api.worldbank.org/v2/country/{country}/indicator/{definition.provider_series_id}"
        params: dict[str, Any] = {"format": "json", "per_page": 20000}
        start_year = _year(start_date)
        end_year = _year(end_date)
        if start_year or end_year:
            params["date"] = f"{start_year or '1960'}:{end_year or datetime.now(timezone.utc).year}"

        try:
            response = httpx.get(url, params=params, timeout=float(load_settings().macro_provider_timeout_s))
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            return _unavailable(self.provider_name, definition, f"worldbank_provider_error:{exc}")

        rows: list[dict[str, Any]] = []
        if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
            rows = [item for item in payload[1] if isinstance(item, dict)]
        if not rows:
            return _unavailable(self.provider_name, definition, f"worldbank_empty_response:{definition.provider_series_id}")

        observations: list[MacroObservation] = []
        for row in rows:
            raw_value = row.get("value")
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            year_text = str(row.get("date") or "").strip()
            if not year_text:
                continue
            observations.append(
                MacroObservation(
                    date=f"{year_text[:4]}-01-01" if year_text[:4].isdigit() else year_text,
                    value=value,
                    raw_value=value,
                    source=self.provider_name,
                    metadata={
                        "indicator": definition.provider_series_id,
                        "country": country,
                        "unit_hint": definition.unit,
                    },
                )
            )

        observations.sort(key=lambda item: item.date)
        if not observations:
            return _unavailable(self.provider_name, definition, f"worldbank_no_numeric_observations:{definition.provider_series_id}")
        return MacroProviderResult(
            provider=self.provider_name,
            observations=observations,
            data_quality=MacroDataQuality(
                status="ok",
                provider=self.provider_name,
                last_updated=observations[-1].date,
                notes=["World Bank Indicators API v2 response."],
            ),
        )


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
