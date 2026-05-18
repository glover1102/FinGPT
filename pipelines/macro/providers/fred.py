from __future__ import annotations

import os

from core.config.settings import load_settings
from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesDefinition
from pipelines.data_mart.models import MacroObservation as StoredMacroObservation
from pipelines.data_mart.providers.fred_provider import fetch_macro_series
from pipelines.macro.providers.base import MacroDataProvider, MacroProviderResult


class FredProvider(MacroDataProvider):
    provider_name = "fred"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def _api_key(self) -> str:
        if self.api_key is not None:
            return self.api_key
        if "FRED_API_KEY" in os.environ:
            return str(os.environ.get("FRED_API_KEY") or "")
        return str(getattr(load_settings(), "fred_api_key", "") or "")

    def is_available(self) -> bool:
        key = self._api_key().strip().lower()
        return bool(key) and key not in {"0", "false", "disabled", "none", "null"}

    def supports(self, definition: MacroSeriesDefinition) -> bool:
        return definition.provider == "fred" and definition.enabled

    def fetch_series(
        self,
        definition: MacroSeriesDefinition,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> MacroProviderResult:
        if not self.supports(definition):
            return MacroProviderResult(
                provider=self.provider_name,
                observations=[],
                data_quality=MacroDataQuality(
                    status="unavailable",
                    provider=self.provider_name,
                    missing_series=[definition.series_id],
                    errors=[f"provider does not support {definition.series_id}"],
                ),
            )
        api_key = self._api_key()
        if not self.is_available():
            return MacroProviderResult(
                provider=self.provider_name,
                observations=[],
                data_quality=MacroDataQuality(
                    status="unavailable",
                    provider=self.provider_name,
                    missing_series=[definition.series_id],
                    errors=["FRED_API_KEY is missing."],
                ),
            )
        result = fetch_macro_series(
            [definition.provider_series_id],
            start_date=start_date,
            end_date=end_date,
            api_key=api_key,
        )
        observations = [
            MacroObservation(
                date=record.date,
                value=record.value,
                raw_value=record.value,
                source=record.source,
                metadata={"collected_at": record.collected_at},
            )
            for record in result.records
            if isinstance(record, StoredMacroObservation)
        ]
        if observations:
            status = "partial" if result.status not in {"ok", "partial"} or result.error else "ok"
        else:
            status = "unavailable"
        return MacroProviderResult(
            provider=self.provider_name,
            observations=observations,
            data_quality=MacroDataQuality(
                status=status,
                provider=self.provider_name,
                last_updated=result.finished_at,
                missing_series=[] if observations else [definition.series_id],
                errors=[result.error] if result.error else [],
                notes=[f"fred status: {result.status}"],
            ),
        )
