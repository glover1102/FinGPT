from __future__ import annotations

from core.schemas.macro import MacroDataQuality, MacroSeriesDefinition
from pipelines.macro.providers.base import MacroDataProvider, MacroProviderResult


class UnavailableProvider(MacroDataProvider):
    provider_name = "unavailable"

    def __init__(self, reason: str = "provider unavailable") -> None:
        self.reason = reason

    def is_available(self) -> bool:
        return False

    def supports(self, definition: MacroSeriesDefinition) -> bool:
        return True

    def fetch_series(
        self,
        definition: MacroSeriesDefinition,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> MacroProviderResult:
        return MacroProviderResult(
            provider=self.provider_name,
            observations=[],
            data_quality=MacroDataQuality(
                status="unavailable",
                provider=self.provider_name,
                missing_series=[definition.series_id],
                errors=[self.reason],
                notes=["No synthetic macro observations are generated."],
            ),
        )
