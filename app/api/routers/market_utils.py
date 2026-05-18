from __future__ import annotations

from typing import Any


def clean_ticker_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.replace(",", " ").split()
    else:
        raw = list(value)
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        ticker = str(item or "").strip().upper()
        if ticker and ticker not in seen:
            out.append(ticker)
            seen.add(ticker)
    return out


def filter_price_rows(
    rows: list[dict[str, Any]],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    if not start_date and not end_date:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        row_date = str(row.get("date") or "")
        if start_date and row_date < start_date:
            continue
        if end_date and row_date > end_date:
            continue
        out.append(row)
    return out


def returns_from_price_rows(rows: list[dict[str, Any]]) -> list[float]:
    returns: list[float] = []
    prices: list[float] = []
    for row in sorted(rows, key=lambda item: str(item.get("date") or "")):
        value = row.get("adjusted_close")
        if value is None:
            value = row.get("close")
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price > 0:
            prices.append(price)
    for idx in range(1, len(prices)):
        previous = prices[idx - 1]
        current = prices[idx]
        if previous:
            returns.append(current / previous - 1.0)
    return returns
