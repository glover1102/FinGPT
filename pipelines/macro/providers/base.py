from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesDefinition


@dataclass(frozen=True)
class MacroProviderResult:
    provider: str
    observations: list[MacroObservation]
    data_quality: MacroDataQuality


class MacroDataProvider(ABC):
    provider_name: str

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def supports(self, definition: MacroSeriesDefinition) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_series(
        self,
        definition: MacroSeriesDefinition,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> MacroProviderResult:
        raise NotImplementedError

    def fetch_latest(self, definition: MacroSeriesDefinition) -> MacroProviderResult:
        return self.fetch_series(definition)

    def health_check(self) -> dict[str, str | bool]:
        return {"provider": self.provider_name, "available": self.is_available()}
