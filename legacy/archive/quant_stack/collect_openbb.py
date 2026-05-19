# Collect company news and earnings transcripts with OpenBB and normalize them into one document format.
from __future__ import annotations

from datetime import date
import traceback

from app.config import load_settings
from app.preflight import (
    candidate_transcript_periods,
    classify_transcript_error,
    ensure_supported_runtime,
    has_openbb_fmp_key,
    import_openbb_with_credentials,
)
from app.pipeline import (
    deduplicate_documents,
    extract_records,
    iso_datetime,
    normalize_news_records,
    normalize_transcript_records,
    write_documents,
)

NEWS_PROVIDER = "yfinance"
TRANSCRIPT_PROVIDER = "fmp"
NEWS_LIMIT = 50


def fetch_company_news(obb: object, symbol: str, start_date: str, end_date: str) -> list[dict]:
    attempts = [
        {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "limit": NEWS_LIMIT,
            "provider": NEWS_PROVIDER,
        },
        {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "limit": NEWS_LIMIT,
        },
    ]

    for params in attempts:
        try:
            response = obb.news.company(**params)
            return normalize_news_records(extract_records(response), symbol, source_hint=params.get("provider", "openbb"))
        except Exception as exc:
            print(f"[news] attempt failed with params={params}: {exc}")

    return []


def fetch_transcripts(obb: object, symbol: str, start_date: str, end_date: str) -> list[dict]:
    if not has_openbb_fmp_key(obb):
        print("[transcript] skipped: credentials missing")
        return []

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    periods = candidate_transcript_periods(start_date, end_date)
    documents: list[dict] = []
    attempted = 0

    for year, quarter in periods:
        attempted += 1
        try:
            response = obb.equity.fundamental.transcript(
                symbol=symbol,
                year=year,
                quarter=quarter,
                provider=TRANSCRIPT_PROVIDER,
            )
        except Exception as exc:
            reason = classify_transcript_error(exc)
            print(f"[transcript] {symbol} Y{year} Q{quarter} skipped ({reason}): {exc}")
            continue

        rows = extract_records(response)
        if not rows:
            print(f"[transcript] {symbol} Y{year} Q{quarter} returned no rows")
            continue

        normalized = normalize_transcript_records(rows, symbol, source_hint=TRANSCRIPT_PROVIDER)
        for doc in normalized:
            published_at = doc.get("published_at", "")
            if not published_at:
                continue

            published_date = iso_datetime(published_at)[:10]
            if start_date <= published_date <= end_date:
                documents.append(doc)

    if attempted and not documents:
        print("[transcript] no transcript in date range")

    return deduplicate_documents(documents)


def main() -> None:
    ensure_supported_runtime()
    settings = load_settings()
    obb, _, _ = import_openbb_with_credentials(settings)
    print(f"Collecting OpenBB documents for {settings.symbol} from {settings.start_date} to {settings.end_date}")

    news_docs = fetch_company_news(obb, settings.symbol, settings.start_date, settings.end_date)
    transcript_docs = fetch_transcripts(obb, settings.symbol, settings.start_date, settings.end_date)

    documents = deduplicate_documents(news_docs + transcript_docs)
    write_documents(settings.raw_docs_path, documents)

    print(f"Saved {len(documents)} normalized documents to {settings.raw_docs_path}")
    print(f" - news: {len(news_docs)}")
    print(f" - transcript chunks: {len(transcript_docs)}")

    if not documents:
        print("No documents were collected. This can happen when the provider has no data or credentials are missing.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI behavior
        print(f"collect_openbb.py failed: {exc}")
        traceback.print_exc()
        raise SystemExit(1) from exc
