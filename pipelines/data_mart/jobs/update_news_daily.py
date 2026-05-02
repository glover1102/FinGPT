from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from pipelines.collect.google_news_rss import collect_news_from_google_rss
from pipelines.data_mart.models import NewsArticle, ProviderFetchResult, UpdateRunResult, utc_now_iso
from pipelines.data_mart.storage import repository

NewsCollector = Callable[..., tuple[object, list[dict]]]


def _articles_from_docs(ticker: str, docs: list[dict]) -> list[NewsArticle]:
    articles: list[NewsArticle] = []
    for doc in docs:
        articles.append(
            NewsArticle(
                ticker=ticker,
                title=str(doc.get("title") or ""),
                url=str(doc.get("url") or ""),
                source=str(doc.get("source") or "google_news"),
                published_at=str(doc.get("published_at") or ""),
                summary=str(doc.get("text") or "")[:1000],
                collected_at=utc_now_iso(),
            )
        )
    return articles


def update_news_daily(
    tickers: Iterable[str],
    *,
    market: str = "us",
    lookback_days: int = 3,
    dry_run: bool = False,
    db_path: str | Path | None = None,
    collector: NewsCollector = collect_news_from_google_rss,
) -> UpdateRunResult:
    tickers = [str(t).upper().strip() for t in tickers if str(t).strip()]
    if dry_run:
        return UpdateRunResult(run_id="dry-run", status="dry_run", market=market, provider="google_news_rss")

    run_id = repository.start_update_run(market=market, provider="google_news_rss", db_path=db_path)
    all_articles: list[NewsArticle] = []
    provider_results: list[ProviderFetchResult] = []
    for ticker in tickers:
        try:
            source_result, docs = collector(ticker, lookback_days, limit=10)
            status = str(getattr(source_result, "status", "unknown"))
            error = str(getattr(source_result, "detail", "") or "") or None
            articles = _articles_from_docs(ticker, docs)
            all_articles.extend(articles)
            provider_results.append(
                ProviderFetchResult(
                    provider="google_news_rss",
                    status=status,
                    rows=len(articles),
                    records=articles,
                    error=error if status not in {"ok", "empty"} else None,
                    detail={"ticker": ticker},
                )
            )
        except Exception as exc:  # noqa: BLE001
            provider_results.append(
                ProviderFetchResult(
                    provider="google_news_rss",
                    status="failed",
                    rows=0,
                    error=str(exc),
                    detail={"ticker": ticker},
                )
            )
    counts = repository.upsert_news_articles(all_articles, db_path=db_path) if all_articles else {"inserted": 0, "updated": 0}
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
    final_status = "failed" if failed and not all_articles else "success"
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
        provider="google_news_rss",
        rows_inserted=counts["inserted"],
        rows_updated=counts["updated"],
        error_message=error,
        providers=provider_results,
    )
