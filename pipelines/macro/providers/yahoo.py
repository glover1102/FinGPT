from __future__ import annotations

from math import isfinite
from typing import Any

from core.config.settings import load_settings
from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesDefinition
from pipelines.macro.providers.base import MacroDataProvider, MacroProviderResult

try:  # pragma: no cover - availability is exercised through provider behavior.
    import yfinance as yf
except Exception:  # noqa: BLE001
    yf = None  # type: ignore[assignment]


class YahooFinanceProvider(MacroDataProvider):
    provider_name = "yahoo"

    def is_available(self) -> bool:
        return yf is not None

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
        if yf is None:
            return _unavailable(self.provider_name, definition, "yfinance is not installed.")
        symbol = str(definition.provider_series_id or "").strip()
        if not symbol:
            return _unavailable(self.provider_name, definition, f"missing Yahoo symbol for {definition.series_id}")
        try:
            settings = load_settings()
            kwargs: dict[str, Any] = {
                "tickers": symbol,
                "progress": False,
                "threads": False,
                "auto_adjust": False,
                "timeout": float(settings.macro_provider_timeout_s),
            }
            if start_date or end_date:
                if start_date:
                    kwargs["start"] = start_date
                if end_date:
                    kwargs["end"] = end_date
            else:
                kwargs["period"] = str(settings.macro_yahoo_default_period or "5y")
            frame = yf.download(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return _unavailable(self.provider_name, definition, f"yahoo_provider_error:{exc}")

        if frame is None or getattr(frame, "empty", True):
            return _unavailable(self.provider_name, definition, f"yahoo_empty_response:{symbol}")
        observations = _frame_to_observations(frame, symbol)
        if not observations:
            return _unavailable(self.provider_name, definition, f"yahoo_no_numeric_observations:{symbol}")
        return MacroProviderResult(
            provider=self.provider_name,
            observations=observations,
            data_quality=MacroDataQuality(
                status="ok",
                provider=self.provider_name,
                last_updated=observations[-1].date,
                notes=["Yahoo Finance price proxy via yfinance."],
            ),
        )


def _frame_to_observations(frame: Any, symbol: str) -> list[MacroObservation]:
    if hasattr(frame, "columns") and getattr(frame.columns, "nlevels", 1) > 1:
        try:
            if symbol in set(frame.columns.get_level_values(-1)):
                frame = frame.xs(symbol, axis=1, level=-1)
            elif symbol in set(frame.columns.get_level_values(0)):
                frame = frame.xs(symbol, axis=1, level=0)
        except Exception:  # noqa: BLE001
            return []
    price_col = "Adj Close" if "Adj Close" in frame.columns else "Close"
    if price_col not in frame.columns:
        return []
    out: list[MacroObservation] = []
    for index, row in frame.iterrows():
        try:
            value = float(row[price_col])
        except (TypeError, ValueError):
            continue
        if not isfinite(value):
            continue
        date_value = index.date().isoformat() if hasattr(index, "date") else str(index)[:10]
        metadata = {"symbol": symbol, "price_column": price_col}
        for col in ("Open", "High", "Low", "Close", "Adj Close", "Volume"):
            if col in frame.columns:
                raw = row[col]
                try:
                    metadata[col.lower().replace(" ", "_")] = float(raw)
                except (TypeError, ValueError):
                    pass
        out.append(
            MacroObservation(
                date=date_value,
                value=value,
                raw_value=value,
                source="yahoo_finance",
                metadata=metadata,
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
