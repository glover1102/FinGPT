from core.utils.query_planner import plan_query


def test_tlt_maps_to_rates_bonds():
    plan = plan_query("TLT", "금리와 채권 가격 매력도 분석")
    assert plan.asset_type == "bond_etf"
    assert plan.lens == "rates_bonds"
    assert "duration" in plan.required_evidence_buckets
    assert "treasury_yields" in plan.required_evidence_buckets


def test_aapl_maps_to_equity_fundamental():
    plan = plan_query("AAPL", "제품 사이클과 밸류에이션 리스크")
    assert plan.asset_type == "equity"
    assert plan.lens == "equities_fundamental"
    assert "revenue" in plan.required_evidence_buckets
    assert "valuation" in plan.required_evidence_buckets


def test_btc_maps_to_crypto():
    plan = plan_query("BTC-USD", "ETF flow와 유동성 분석")
    assert plan.asset_type == "crypto"
    assert plan.lens == "crypto"
    assert "ETF_flows" in plan.required_evidence_buckets


def test_tickerless_macro_maps_to_macro():
    plan = plan_query("", "현재 시장이 무시하는 거시 리스크")
    assert plan.asset_type == "macro_topic"
    assert plan.lens == "macro"
    assert "liquidity" in plan.required_evidence_buckets
