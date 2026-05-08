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


def _clean_tickers(tickers: Iterable[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = str(raw or "").upper().strip()
        if ticker and ticker not in seen:
            clean.append(ticker)
            seen.add(ticker)
    return clean


def _frame_for_ticker(frame: Any, ticker: str, ticker_count: int) -> Any | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    columns = getattr(frame, "columns", None)
    nlevels = int(getattr(columns, "nlevels", 1) or 1)
    if nlevels <= 1:
        return frame if ticker_count == 1 else None
    try:
        level_zero = {str(value).upper() for value in columns.get_level_values(0)}
        if ticker.upper() in level_zero:
            return frame[ticker]
    except Exception:
        pass
    try:
        level_one = {str(value).upper() for value in columns.get_level_values(1)}
        if ticker.upper() in level_one:
            return frame.xs(ticker, axis=1, level=1)
    except Exception:
        pass
    return None


def _append_frame_records(
    *,
    ticker: str,
    frame: Any,
    provider: str,
    records: list[PriceBar],
    skipped_rows: dict[str, int],
) -> int:
    added = 0
    if frame is None or getattr(frame, "empty", True):
        return added
    for idx, row in frame.iterrows():
        open_value = _clean_float(row.get("Open"))
        high_value = _clean_float(row.get("High"))
        low_value = _clean_float(row.get("Low"))
        close = _clean_float(row.get("Close"))
        adjusted = _clean_float(row.get("Adj Close"))
        volume = _clean_float(row.get("Volume"))
        if close is None:
            skipped_rows[ticker] = skipped_rows.get(ticker, 0) + 1
            continue
        if adjusted is None:
            adjusted = close
        records.append(
            PriceBar(
                ticker=ticker,
                date=_as_date_text(idx),
                open=open_value,
                high=high_value,
                low=low_value,
                close=close,
                adjusted_close=adjusted,
                volume=volume,
                source=provider,
                collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            )
        )
        added += 1
    return added


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

    clean_tickers = _clean_tickers(tickers)
    records: list[PriceBar] = []
    failed: dict[str, str] = {}
    skipped_rows: dict[str, int] = {}

    if len(clean_tickers) > 1:
        try:
            downloaded = yf.download(
                tickers=" ".join(clean_tickers),
                group_by="ticker",
                threads=True,
                progress=False,
                **_history_kwargs(start_date, end_date),
            )
        except Exception as exc:  # noqa: BLE001
            failed = {ticker: str(exc) for ticker in clean_tickers}
        else:
            for ticker in clean_tickers:
                frame = _frame_for_ticker(downloaded, ticker, len(clean_tickers))
                if _append_frame_records(ticker=ticker, frame=frame, provider=provider, records=records, skipped_rows=skipped_rows) == 0:
                    failed[ticker] = "empty history"

    fallback_tickers = clean_tickers if len(clean_tickers) <= 1 else [ticker for ticker in clean_tickers if ticker in failed]
    if fallback_tickers:
        for ticker in fallback_tickers:
            try:
                frame = yf.Ticker(ticker).history(**_history_kwargs(start_date, end_date))
            except Exception as exc:  # noqa: BLE001
                failed[ticker] = str(exc)
                continue
            if _append_frame_records(ticker=ticker, frame=frame, provider=provider, records=records, skipped_rows=skipped_rows):
                failed.pop(ticker, None)
            else:
                failed[ticker] = "empty history"

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
        detail={
            "failed_tickers": failed,
            "skipped_empty_price_rows": skipped_rows,
            "requested_tickers": clean_tickers,
        },
        started_at=started,
        finished_at=utc_now_iso(),
    )
