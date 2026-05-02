from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from pipelines.data_mart.models import PriceBar, ProviderFetchResult, utc_now_iso


def _as_date_text(value: Any) -> str:
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except Exception:
            pass
    return str(value)[:10]


def _clean_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if str(value).lower() in {"nan", "nat"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _history_kwargs(start_date: str | date | None, end_date: str | date | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"interval": "1d", "auto_adjust": False}
    if start_date:
        kwargs["start"] = str(start_date)
    if end_date:
        kwargs["end"] = str(end_date)
    if not start_date and not end_date:
        kwargs["period"] = "1y"
    return kwargs


def fetch_daily_prices(
    tickers: Iterable[str],
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> ProviderFetchResult:
    provider = "yfinance"
    started = utc_now_iso()
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return ProviderFetchResult(
            provider=provider,
            status="failed",
            error=f"yfinance import failed: {exc}",
            started_at=started,
            finished_at=utc_now_iso(),
        )

    records: list[PriceBar] = []
    failed: dict[str, str] = {}
    for raw in tickers:
        ticker = str(raw or "").upper().strip()
        if not ticker:
            continue
        try:
            frame = yf.Ticker(ticker).history(**_history_kwargs(start_date, end_date))
        except Exception as exc:  # noqa: BLE001
            failed[ticker] = str(exc)
            continue
        if frame is None or getattr(frame, "empty", True):
            failed[ticker] = "empty history"
            continue
        for idx, row in frame.iterrows():
            close = _clean_float(row.get("Close"))
            adjusted = _clean_float(row.get("Adj Close"))
            if adjusted is None:
                adjusted = close
            records.append(
                PriceBar(
                    ticker=ticker,
                    date=_as_date_text(idx),
                    open=_clean_float(row.get("Open")),
                    high=_clean_float(row.get("High")),
                    low=_clean_float(row.get("Low")),
                    close=close,
                    adjusted_close=adjusted,
                    volume=_clean_float(row.get("Volume")),
                    source=provider,
                    collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                )
            )

    if records:
        status = "partial" if failed else "ok"
    else:
        status = "empty" if not failed else "failed"
    return ProviderFetchResult(
        provider=provider,
        status=status,
        rows=len(records),
        records=records,
        error="; ".join(f"{ticker}: {msg}" for ticker, msg in sorted(failed.items())) or None,
        detail={"failed_tickers": failed, "requested_tickers": [str(t).upper().strip() for t in tickers if str(t).strip()]},
        started_at=started,
        finished_at=utc_now_iso(),
    )
