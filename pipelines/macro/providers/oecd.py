from __future__ import annotations

from typing import Any

import httpx

from core.config.settings import load_settings
from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesDefinition
from pipelines.macro.providers.base import MacroDataProvider, MacroProviderResult


def _year(value: str | None) -> str | None:
    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return None


def _normalise_period(value: str) -> str:
    text = str(value or "").strip()
    if len(text) == 4 and text.isdigit():
        return f"{text}-01-01"
    if len(text) == 7 and text[4] == "-":
        return f"{text}-01"
    return text


class OecdProvider(MacroDataProvider):
    provider_name = "oecd"

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
        try:
            url, params = self._request(definition, start_date=start_date, end_date=end_date)
            response = httpx.get(url, params=params, timeout=float(load_settings().macro_provider_timeout_s))
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            return _unavailable(self.provider_name, definition, f"oecd_provider_error:{exc}")

        observations = self._parse_sdmx_json(payload, definition)
        if not observations:
            return _unavailable(self.provider_name, definition, f"oecd_empty_response:{definition.provider_series_id}")
        return MacroProviderResult(
            provider=self.provider_name,
            observations=observations,
            data_quality=MacroDataQuality(
                status="ok",
                provider=self.provider_name,
                last_updated=observations[-1].date,
                notes=["OECD SDMX JSON response."],
            ),
        )

    def _request(
        self,
        definition: MacroSeriesDefinition,
        *,
        start_date: str | None,
        end_date: str | None,
    ) -> tuple[str, dict[str, str]]:
        provider_id = str(definition.provider_series_id or "").strip()
        if provider_id.lower().startswith("http"):
            url = provider_id
        else:
            dataset, _, key = provider_id.partition("/")
            if not dataset or not key:
                raise ValueError(f"invalid OECD provider_series_id: {provider_id}")
            url = f"https://stats.oecd.org/sdmx-json/data/{dataset}/{key}/all"
        params = {"dimension_at_observation": "allDimensions"}
        start_year = _year(start_date)
        end_year = _year(end_date)
        if start_year:
            params["startTime"] = start_year
        if end_year:
            params["endTime"] = end_year
        return url, params

    def _parse_sdmx_json(self, payload: Any, definition: MacroSeriesDefinition) -> list[MacroObservation]:
        if not isinstance(payload, dict):
            return []
        data_sets = payload.get("dataSets")
        structure = payload.get("structure") or {}
        if not isinstance(data_sets, list) or not data_sets:
            return []
        observations = data_sets[0].get("observations") if isinstance(data_sets[0], dict) else None
        dimensions = (structure.get("dimensions") or {}).get("observation") if isinstance(structure, dict) else None
        if not isinstance(observations, dict) or not isinstance(dimensions, list):
            return []
        time_index = None
        time_values: list[Any] = []
        for idx, dim in enumerate(dimensions):
            if not isinstance(dim, dict):
                continue
            dim_id = str(dim.get("id") or "").upper()
            if dim_id in {"TIME_PERIOD", "TIME"}:
                time_index = idx
                time_values = list(dim.get("values") or [])
                break
        if time_index is None:
            return []

        out: list[MacroObservation] = []
        for key, raw in observations.items():
            indexes = [part for part in str(key).split(":") if part != ""]
            if len(indexes) <= time_index:
                continue
            try:
                period = str(time_values[int(indexes[time_index])].get("id") or "")
                value = float(raw[0] if isinstance(raw, list) else raw)
            except (IndexError, TypeError, ValueError, AttributeError):
                continue
            if not period:
                continue
            out.append(
                MacroObservation(
                    date=_normalise_period(period),
                    value=value,
                    raw_value=value,
                    source=self.provider_name,
                    metadata={"dataset": definition.provider_series_id},
                )
            )
        return sorted(out, key=lambda item: item.date)


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
