from __future__ import annotations

from pipelines.data_mart.jobs import update_sec_company_data as sec_job
from pipelines.data_mart.models import Filing, ProviderFetchResult
from pipelines.data_mart.storage import repository


def test_update_sec_company_data_persists_filings_facts_and_snapshot(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "research_mart.db"
    monkeypatch.setattr(sec_job, "fetch_ticker_map", lambda _ua: ("ok", {"data": []}))

    def fake_collector(ticker, **kwargs):
        assert kwargs["forms"] == ["10-K", "10-Q", "8-K"]
        company = {
            "ticker": ticker,
            "cik": "0000320193",
            "company_name": "Apple Inc.",
            "exchange": "Nasdaq",
            "source": "sec_company_tickers",
        }
        facts = [
            {
                "ticker": ticker,
                "cik": "0000320193",
                "taxonomy": "us-gaap",
                "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                "label": "Revenue",
                "unit": "USD",
                "form_type": "10-K",
                "fiscal_year": 2025,
                "fiscal_period": "FY",
                "end_date": "2025-12-31",
                "filed_at": "2026-01-31",
                "accession_number": "0000320193-26-000001",
                "value": 390000000000,
            },
            {
                "ticker": ticker,
                "cik": "0000320193",
                "taxonomy": "us-gaap",
                "concept": "Assets",
                "label": "Assets",
                "unit": "USD",
                "form_type": "10-K",
                "fiscal_year": 2025,
                "fiscal_period": "FY",
                "end_date": "2025-12-31",
                "filed_at": "2026-01-31",
                "accession_number": "0000320193-26-000001",
                "value": 500000000000,
            },
        ]
        return ProviderFetchResult(
            provider="sec_edgar",
            status="ok",
            rows=3,
            records=[
                Filing(
                    ticker=ticker,
                    cik="0000320193",
                    accession_number="0000320193-26-000001",
                    form_type="10-K",
                    filed_at="2026-01-31",
                    report_date="2025-12-31",
                    fiscal_year=2025,
                    fiscal_period="FY",
                    primary_document="aapl-20251231.htm",
                    url="https://sec.example/aapl-10k",
                    filing_id=f"{ticker}:0000320193-26-000001",
                )
            ],
            detail={"ticker": ticker, "company": company, "facts": facts, "filing_count": 1, "fact_count": 2},
        )

    result = sec_job.update_sec_company_data(
        ["AAPL", "SPY", "005930.KS", "BTC-USD"],
        forms=["10-K", "10-Q", "8-K"],
        max_assets=10,
        db_path=db_path,
        collector=fake_collector,
    )

    health = repository.data_health(db_path=db_path)
    fundamentals = repository.latest_fundamentals("AAPL", db_path=db_path)
    provider_status = health["recent_provider_status"]

    assert result.status == "success"
    assert health["table_counts"]["sec_company_registry"] == 1
    assert health["table_counts"]["filings"] == 1
    assert health["table_counts"]["sec_financial_facts"] == 2
    assert fundamentals is not None
    assert fundamentals["source"] == "sec_companyfacts"
    assert fundamentals["financials"]["total_revenue"] == 390000000000
    assert fundamentals["financials"]["total_assets"] == 500000000000
    assert any(row["status"] == "skipped" and row["ticker"] == "SPY" for row in provider_status)
    assert any(row["status"] == "skipped" and row["ticker"] == "005930.KS" for row in provider_status)
