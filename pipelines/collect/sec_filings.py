from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from core.utils.data_helpers import normalize_news_records
from pipelines.collect.fmp_news import filter_fresh_documents
from pipelines.collect.models import SourceCollectionResult

_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_HTTP_TIMEOUT_S = 8.0
_RELEVANT_FORMS = {"8-K", "10-Q", "10-K", "6-K", "20-F", "40-F"}


def _now() -> datetime:
    return datetime.now()


def _headers(sec_user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def _classify_response(response: httpx.Response) -> str:
    if response.status_code == 429:
        return "rate_limited"
    if response.status_code in (403, 451):
        return "provider_unavailable"
    if response.status_code >= 500:
        return "provider_unavailable"
    if response.status_code == 404:
        return "empty"
    if response.status_code != 200:
        return "provider_unavailable"
    return "ok"


def _fetch_json(url: str, sec_user_agent: str) -> tuple[str, Any]:
    try:
        response = httpx.get(url, headers=_headers(sec_user_agent), timeout=_HTTP_TIMEOUT_S, follow_redirects=True)
    except httpx.TimeoutException:
        return "timeout", None
    except httpx.HTTPError as exc:
        return "provider_unavailable", str(exc)

    status = _classify_response(response)
    if status != "ok":
        return status, response.text

    try:
        return "ok", response.json()
    except ValueError:
        return "provider_unavailable", response.text


def _ticker_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    fields = payload.get("fields")
    rows = payload.get("data")
    if isinstance(fields, list) and isinstance(rows, list):
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            normalized.append({str(field): row[index] if index < len(row) else "" for index, field in enumerate(fields)})
        return normalized

    normalized = []
    for value in payload.values():
        if isinstance(value, dict):
            normalized.append(value)
    return normalized


def _lookup_cik(payload: Any, symbol: str) -> tuple[str, str] | None:
    symbol_upper = symbol.upper()
    for row in _ticker_rows(payload):
        ticker = str(row.get("ticker", "")).upper()
        if ticker != symbol_upper:
            continue
        cik_raw = row.get("cik") or row.get("cik_str") or row.get("CIK")
        try:
            cik = f"{int(cik_raw):010d}"
        except (TypeError, ValueError):
            return None
        company_name = str(row.get("name") or row.get("title") or symbol_upper)
        return cik, company_name
    return None


def _safe_recent_value(recent: dict[str, Any], field: str, index: int) -> str:
    values = recent.get(field)
    if not isinstance(values, list) or index >= len(values):
        return ""
    value = values[index]
    return "" if value is None else str(value)


def _filing_url(cik: str, accession_number: str, primary_document: str) -> str:
    accession_path = accession_number.replace("-", "")
    cik_path = str(int(cik))
    if not primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{accession_path}/"
    return f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{accession_path}/{primary_document}"


def _submission_records(payload: Any, symbol: str, cik: str, company_name: str, limit: int) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    recent = payload.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict):
        return []

    accession_numbers = recent.get("accessionNumber")
    if not isinstance(accession_numbers, list):
        return []

    records: list[dict[str, Any]] = []
    for index, accession in enumerate(accession_numbers):
        form = _safe_recent_value(recent, "form", index)
        if form not in _RELEVANT_FORMS:
            continue

        filing_date = _safe_recent_value(recent, "filingDate", index)
        report_date = _safe_recent_value(recent, "reportDate", index)
        primary_document = _safe_recent_value(recent, "primaryDocument", index)
        description = _safe_recent_value(recent, "primaryDocDescription", index)
        accession_text = str(accession)

        title = f"SEC {form} filing for {company_name} ({symbol})"
        detail = description or f"{form} filing"
        text = (
            f"{company_name} ({symbol}) filed SEC form {form} on {filing_date}. "
            f"Description: {detail}. Accession number: {accession_text}."
        )
        if report_date and report_date != filing_date:
            text += f" Report date: {report_date}."

        records.append(
            {
                "title": title,
                "text": text,
                "published_at": filing_date,
                "source": "SEC EDGAR",
                "url": _filing_url(cik, accession_text, primary_document),
                "symbol": symbol,
            }
        )
        if len(records) >= limit:
            break

    return records


def collect_sec_filings_as_news(
    symbol: str,
    lookback_days: int,
    sec_user_agent: str,
    limit: int = 5,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    started_at = _now()

    ticker_status, ticker_payload = _fetch_json(_TICKERS_URL, sec_user_agent)
    if ticker_status != "ok":
        elapsed_s = round((_now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("news", ticker_status, 0, elapsed_s, f"SEC ticker map returned status={ticker_status}."), []

    lookup = _lookup_cik(ticker_payload, symbol)
    if lookup is None:
        elapsed_s = round((_now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("news", "empty", 0, elapsed_s, f"SEC ticker map did not include {symbol}."), []

    cik, company_name = lookup
    submissions_status, submissions_payload = _fetch_json(_SUBMISSIONS_URL.format(cik=cik), sec_user_agent)
    if submissions_status != "ok":
        elapsed_s = round((_now() - started_at).total_seconds(), 2)
        return (
            SourceCollectionResult("news", submissions_status, 0, elapsed_s, f"SEC submissions returned status={submissions_status}."),
            [],
        )

    records = _submission_records(submissions_payload, symbol, cik, company_name, limit=limit)
    if not records:
        elapsed_s = round((_now() - started_at).total_seconds(), 2)
        return SourceCollectionResult("news", "empty", 0, elapsed_s, "SEC returned no relevant recent filings."), []

    normalized = normalize_news_records(records, symbol, company_name=company_name, source_hint="sec_filings")
    fresh_documents, freshness_detail = filter_fresh_documents(
        normalized,
        lookback_days,
        now=started_at,
        collected_at=started_at.isoformat(),
    )
    elapsed_s = round((_now() - started_at).total_seconds(), 2)

    if not fresh_documents:
        detail = freshness_detail or "SEC filings returned records, but none survived normalization."
        return SourceCollectionResult("news", "empty", 0, elapsed_s, detail), []

    return SourceCollectionResult("news", "ok", len(fresh_documents), elapsed_s, "SEC recent filings collected."), fresh_documents
