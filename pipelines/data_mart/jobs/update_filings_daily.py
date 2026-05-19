from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable

from core.config.settings import load_settings
from pipelines.collect.sec_filings import collect_sec_filings_as_news
from pipelines.data_mart.models import Filing, ProviderFetchResult, UpdateRunResult, utc_now_iso
from pipelines.data_mart.storage import repository

FilingsCollector = Callable[..., tuple[object, list[dict]]]
_FORM_RE = re.compile(r"\b(10-K|10-Q|8-K|6-K|20-F|40-F)\b", re.IGNORECASE)


def _form_type(doc: dict) -> str:
    haystack = " ".join(str(doc.get(field) or "") for field in ("title", "text", "summary"))
    match = _FORM_RE.search(haystack)
    return match.group(1).upper() if match else "UNKNOWN"


def _filings_from_docs(ticker: str, docs: list[dict]) -> list[Filing]:
    filings: list[Filing] = []
    for doc in docs:
        form_type = _form_type(doc)
        if form_type == "UNKNOWN":
            continue
        filings.append(
            Filing(
                ticker=ticker,
                form_type=form_type,
                filed_at=str(doc.get("published_at") or doc.get("date") or ""),
                url=str(doc.get("url") or ""),
                source="sec",
                filing_id=str(doc.get("url") or doc.get("title") or ""),
                collected_at=utc_now_iso(),
            )
        )
    return filings


def update_filings_daily(
    tickers: Iterable[str],
    *,
    market: str = "us",
    lookback_days: int = 120,
    dry_run: bool = False,
    db_path: str | Path | None = None,
    collector: FilingsCollector = collect_sec_filings_as_news,
) -> UpdateRunResult:
    tickers = [str(t).upper().strip() for t in tickers if str(t).strip()]
    if dry_run:
        return UpdateRunResult(run_id="dry-run", status="dry_run", market=market, provider="sec_filings")

    run_id = repository.start_update_run(market=market, provider="sec_filings", db_path=db_path)
    sec_user_agent = getattr(load_settings(), "sec_user_agent", "")
    all_filings: list[Filing] = []
    provider_results: list[ProviderFetchResult] = []

    if market.lower() != "us":
        repository.finish_update_run(run_id, status="success", db_path=db_path)
        return UpdateRunResult(run_id=run_id, status="success", market=market, provider="sec_filings")

    for ticker in tickers:
        try:
            source_result, docs = collector(ticker, lookback_days, sec_user_agent, limit=5)
            status = str(getattr(source_result, "status", "unknown"))
            error = str(getattr(source_result, "detail", "") or "") or None
            filings = _filings_from_docs(ticker, docs)
            all_filings.extend(filings)
            provider_results.append(
                ProviderFetchResult(
                    provider="sec_filings",
                    status=status,
                    rows=len(filings),
                    records=filings,
                    error=error if status not in {"ok", "empty"} else None,
                    detail={"ticker": ticker},
                )
            )
        except Exception as exc:  # noqa: BLE001
            provider_results.append(
                ProviderFetchResult(
                    provider="sec_filings",
                    status="failed",
                    rows=0,
                    error=str(exc),
                    detail={"ticker": ticker},
                )
            )

    counts = repository.upsert_filings(all_filings, db_path=db_path) if all_filings else {"inserted": 0, "updated": 0}
    for result in provider_results:
        repository.record_provider_status(
            run_id,
            provider=result.provider,
            status=result.status,
            market=market,
            ticker=str(result.detail.get("ticker") or ""),
            rows_inserted=len(result.records),
            error_message=result.error,
            details=result.detail,
            started_at=result.started_at,
            finished_at=result.finished_at,
            db_path=db_path,
        )

    failed = [result for result in provider_results if result.status == "failed"]
    final_status = "failed" if failed and not all_filings else "success"
    error = "; ".join(result.error or "" for result in failed) or None
    repository.finish_update_run(
        run_id,
        status=final_status,
        rows_inserted=counts["inserted"],
        rows_updated=counts["updated"],
        error_message=error,
        db_path=db_path,
    )
    return UpdateRunResult(
        run_id=run_id,
        status=final_status,
        market=market,
        provider="sec_filings",
        rows_inserted=counts["inserted"],
        rows_updated=counts["updated"],
        error_message=error,
        providers=provider_results,
    )
