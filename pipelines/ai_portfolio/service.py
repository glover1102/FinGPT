from __future__ import annotations

import uuid
from typing import Any

from core.schemas.ai_portfolio import (
    AllocationRange,
    DataActivationRequest,
    GeneratePortfolioRequest,
    GeneratePortfolioResponse,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    PortfolioCoverageRow,
    PortfolioDashboardPolicySummary,
    PortfolioDashboardResponse,
    PortfolioHistoryEvent,
    PortfolioOperationSummary,
    PortfolioPolicy,
    PortfolioRecommendation,
    PortfolioSnapshot,
    PortfolioSnapshotTimelinePoint,
    RebalanceActionRequest,
    RebalanceSignal,
    ReportGenerateRequest,
    SecDataRefreshRequest,
    SnapshotJobRequest,
)
from core.utils.symbol_registry import symbol_identities
from pipelines.ai_portfolio.audit import constraint_policy_hash, data_quality_audit, policy_config_hash, request_id, stable_hash, ticker_universe_hash
from pipelines.ai_portfolio.engine import generate_recommendation, load_universe, new_id, now_iso, universe_presets
from pipelines.ai_portfolio.explainer import recommendation_explanation, report_text
from pipelines.ai_portfolio.rebalancing import calculate_rebalance_signal
from pipelines.ai_portfolio.store import append_item, filter_items, get_item, list_items, store_status, update_item, upsert_item
from pipelines.ai_portfolio.templates import investment_type_or_none, template_to_policy_defaults
from pipelines.collect.fundamentals_card import collect_fundamentals_card
from pipelines.data_mart.jobs.ensure_price_history import ensure_price_history
from pipelines.data_mart.jobs.update_sec_company_data import update_sec_company_data
from pipelines.data_mart.storage import repository as data_repository


def _event(
    policy_id: str,
    event_type: str,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    summary: str = "",
    actor: str = "system",
    audit: dict[str, Any] | None = None,
) -> PortfolioHistoryEvent:
    audit_payload = dict(audit or {})
    event = PortfolioHistoryEvent(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        policy_id=policy_id,
        event_type=event_type,
        event_time=now_iso(),
        before=before,
        after=after,
        summary=summary,
        actor=actor,
        request_id=audit_payload.get("request_id"),
        config_hash=audit_payload.get("config_hash"),
        universe_hash=audit_payload.get("universe_hash"),
        audit=audit_payload,
    )
    append_item("history", event.model_dump(mode="json"))
    return event


def _policy_audit(policy: PortfolioPolicy, *, prefix: str = "pol") -> dict[str, Any]:
    audit = dict(policy.audit or {})
    audit.update(
        {
            "request_id": request_id(prefix),
            "config_hash": policy_config_hash(policy),
            "constraint_policy_hash": constraint_policy_hash(policy),
            "universe_hash": stable_hash({"universe_id": policy.universe_id}),
            "data_snapshot_timestamp": now_iso(),
        }
    )
    return audit


def _save_operation(operation_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    operation = {
        "operation_id": new_id("op"),
        "operation_type": operation_type,
        "created_at": now_iso(),
        **payload,
    }
    append_item("operations", operation)
    return operation


def _clean_tickers(tickers: list[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = str(raw or "").upper().strip()
        if ticker and ticker not in seen:
            clean.append(ticker)
            seen.add(ticker)
    return clean


def _market_for_ticker(ticker: str) -> tuple[str, str, str]:
    if ticker.endswith((".KS", ".KQ")):
        return "KRX", "KR", "KRW"
    if ticker.endswith("-USD"):
        return "CRYPTO", "GLOBAL", "USD"
    return "US", "US", "USD"


def _asset_metadata_rows(assets: list[Any]) -> list[dict[str, Any]]:
    identities = symbol_identities()
    rows: list[dict[str, Any]] = []
    for asset in assets:
        ticker = str(getattr(asset, "ticker", "") or "").upper().strip()
        if not ticker:
            continue
        identity = identities.get(ticker)
        raw_asset_class = str(getattr(identity, "asset_class", "") or getattr(asset, "asset_class", "") or "").lower()
        market, country, currency = _market_for_ticker(ticker)
        if identity and getattr(identity, "market", ""):
            market = str(identity.market).upper()
            country = "KR" if market == "KRX" else "US"
            currency = "KRW" if country == "KR" else "USD"
        quote_type = "ETF" if raw_asset_class == "etf" else ("CRYPTOCURRENCY" if ticker.endswith("-USD") else "EQUITY")
        rows.append(
            {
                "ticker": ticker,
                "name": getattr(asset, "name", "") or ticker,
                "asset_class": getattr(asset, "asset_class", "") or raw_asset_class,
                "quote_type": quote_type,
                "market": market,
                "currency": currency,
                "exchange": market,
                "sector": getattr(asset, "sector", "") or "",
                "country": country,
                "source": getattr(asset, "source", "") or "ai_portfolio_universe",
            }
        )
    return rows


def _assets_for_activation(request: DataActivationRequest) -> tuple[list[Any], dict[str, Any]]:
    warnings: list[str] = []
    source = "default_universe"
    if request.tickers:
        assets, warnings = load_universe("custom:" + ",".join(request.tickers))
        source = "direct_tickers"
    elif request.policy_id:
        policy = get_policy(request.policy_id)
        if not policy:
            raise KeyError(request.policy_id)
        assets, warnings = load_universe(policy.universe_id)
        source = "policy"
    elif request.universe_id:
        assets, warnings = load_universe(request.universe_id)
        source = "universe"
    else:
        active = [policy for policy in list_policies() if policy.status == "active"]
        seen: set[str] = set()
        assets = []
        for policy in active:
            policy_assets, policy_warnings = load_universe(policy.universe_id)
            warnings.extend(policy_warnings)
            for asset in policy_assets:
                ticker = str(getattr(asset, "ticker", "") or "").upper().strip()
                if ticker and ticker not in seen:
                    seen.add(ticker)
                    assets.append(asset)
        if not assets:
            assets, warnings = load_universe("default_multi_asset")
        source = "active_policies"
    metadata = {
        "source": source,
        "warnings": warnings,
        "universe_hash": ticker_universe_hash([getattr(asset, "ticker", "") for asset in assets]),
    }
    return assets, metadata


def _coerce_ranges(value: Any) -> dict[str, AllocationRange]:
    out: dict[str, AllocationRange] = {}
    if not isinstance(value, dict):
        return out
    for key, raw in value.items():
        if isinstance(raw, AllocationRange):
            out[str(key)] = raw
        elif isinstance(raw, dict):
            out[str(key)] = AllocationRange(min=float(raw.get("min", raw.get("0", 0))), max=float(raw.get("max", raw.get("1", 0))))
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            out[str(key)] = AllocationRange(min=float(raw[0]), max=float(raw[1]))
    return out


def _apply_overrides(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key == "asset_allocation_ranges":
            ranges = _coerce_ranges(value)
            if ranges:
                merged[key] = ranges
            continue
        merged[key] = value
    return merged


def build_policy_from_request(request: PolicyCreateRequest, *, policy_id: str | None = None, status: str = "draft") -> PortfolioPolicy:
    template = investment_type_or_none(request.investment_type)
    if not template:
        raise ValueError(f"unknown investment type: {request.investment_type}")
    defaults = _apply_overrides(template_to_policy_defaults(template), request.policy_overrides)
    stamp = now_iso()
    policy = PortfolioPolicy(
        policy_id=policy_id or new_id("pol"),
        portfolio_name=request.portfolio_name,
        investment_type=template.id,
        universe_id=request.universe_id,
        initial_capital=request.initial_capital,
        monthly_contribution=request.monthly_contribution,
        target_return=request.target_return,
        automation_level=request.automation_level,
        benchmark=request.benchmark,
        status=status,  # type: ignore[arg-type]
        created_at=stamp,
        updated_at=stamp,
        **defaults,
    )
    policy.audit.update(
        {
            "request_id": request_id("pol"),
            "config_hash": policy_config_hash(policy),
            "constraint_policy_hash": constraint_policy_hash(policy),
            "universe_hash": stable_hash({"universe_id": policy.universe_id}),
            "created_by": "policy_template",
        }
    )
    return policy


def create_policy(request: PolicyCreateRequest) -> PortfolioPolicy:
    policy = build_policy_from_request(request)
    upsert_item("policies", "policy_id", policy.model_dump(mode="json"))
    _event(
        policy.policy_id,
        "policy_created",
        after=policy.model_dump(mode="json"),
        summary=f"정책 생성: {policy.portfolio_name}",
        audit=policy.audit,
    )
    return policy


def list_universes() -> list[dict[str, Any]]:
    return universe_presets()


def storage_status() -> dict[str, Any]:
    return store_status()


def list_policies() -> list[PortfolioPolicy]:
    return [PortfolioPolicy.model_validate(item) for item in list_items("policies")]


def get_policy(policy_id: str) -> PortfolioPolicy | None:
    item = get_item("policies", "policy_id", policy_id)
    return PortfolioPolicy.model_validate(item) if item else None


def update_policy(policy_id: str, request: PolicyUpdateRequest) -> PortfolioPolicy:
    existing = get_policy(policy_id)
    if not existing:
        raise KeyError(policy_id)
    before = existing.model_dump(mode="json")
    values = before.copy()
    if request.portfolio_name is not None:
        values["portfolio_name"] = request.portfolio_name
    if request.universe_id is not None:
        values["universe_id"] = request.universe_id
    if request.initial_capital is not None:
        values["initial_capital"] = request.initial_capital
    if request.monthly_contribution is not None:
        values["monthly_contribution"] = request.monthly_contribution
    if request.target_return is not None:
        values["target_return"] = request.target_return
    if request.automation_level is not None:
        values["automation_level"] = request.automation_level
    if request.benchmark is not None:
        values["benchmark"] = request.benchmark
    if request.status is not None:
        values["status"] = request.status
    for key, value in _apply_overrides({}, request.policy_overrides).items():
        values[key] = value
    values["updated_at"] = now_iso()
    updated = PortfolioPolicy.model_validate(values)
    updated.audit.update(_policy_audit(updated, prefix="polupd"))
    upsert_item("policies", "policy_id", updated.model_dump(mode="json"))
    _event(policy_id, "policy_updated", before=before, after=updated.model_dump(mode="json"), summary="정책 설정 업데이트")
    return updated


def set_policy_status(policy_id: str, status: str) -> PortfolioPolicy:
    existing = get_policy(policy_id)
    if not existing:
        raise KeyError(policy_id)
    before = existing.model_dump(mode="json")
    updated = existing.model_copy(update={"status": status, "updated_at": now_iso()})
    updated.audit.update(_policy_audit(updated, prefix="polstatus"))
    upsert_item("policies", "policy_id", updated.model_dump(mode="json"))
    event_type = "portfolio_activated" if status == "active" else "policy_updated"
    _event(policy_id, event_type, before=before, after=updated.model_dump(mode="json"), summary=f"정책 상태 변경: {status}", actor="user")
    return updated


def generate_portfolio(request: GeneratePortfolioRequest) -> GeneratePortfolioResponse:
    if request.policy_id:
        policy = get_policy(request.policy_id)
        if not policy:
            raise KeyError(request.policy_id)
        update_payload = PolicyUpdateRequest(
            portfolio_name=request.portfolio_name,
            universe_id=request.universe_id,
            initial_capital=request.initial_capital,
            monthly_contribution=request.monthly_contribution,
            target_return=request.target_return,
            policy_overrides=request.policy_overrides,
            automation_level=request.automation_level,
            benchmark=request.benchmark,
        )
        policy = update_policy(policy.policy_id, update_payload)
    else:
        policy = create_policy(request)
    recommendation, warnings = generate_recommendation(policy)
    recommendation.ai_explanation = recommendation_explanation(policy=policy, recommendation=recommendation, warnings=warnings)
    upsert_item("recommendations", "recommendation_id", recommendation.model_dump(mode="json"))
    _event(
        policy.policy_id,
        "recommendation_generated",
        after=recommendation.model_dump(mode="json"),
        audit=recommendation.audit,
        summary=f"추천 생성: {recommendation.status}",
    )
    return GeneratePortfolioResponse(
        policy=policy,
        recommendation=recommendation,
        warnings=warnings,
        data_quality=recommendation.data_quality,
    )


def list_recommendations(policy_id: str) -> list[PortfolioRecommendation]:
    items = filter_items("recommendations", policy_id=policy_id)
    return [PortfolioRecommendation.model_validate(item) for item in items]


def get_recommendation(recommendation_id: str) -> PortfolioRecommendation | None:
    item = get_item("recommendations", "recommendation_id", recommendation_id)
    return PortfolioRecommendation.model_validate(item) if item else None


def latest_recommendation(policy_id: str) -> PortfolioRecommendation | None:
    items = list_recommendations(policy_id)
    if not items:
        return None
    return sorted(items, key=lambda item: item.created_at, reverse=True)[0]


def create_snapshot(policy_id: str) -> PortfolioSnapshot:
    policy = get_policy(policy_id)
    if not policy:
        raise KeyError(policy_id)
    rec = latest_recommendation(policy_id)
    snapshot_audit = {
        "request_id": request_id("snap"),
        "config_hash": policy_config_hash(policy),
        "constraint_policy_hash": constraint_policy_hash(policy),
        "universe_hash": stable_hash({"universe_id": policy.universe_id}),
        "data_snapshot_timestamp": now_iso(),
    }
    if rec:
        snapshot_audit.update(
            {
                "recommendation_id": rec.recommendation_id,
                "recommendation_audit": rec.audit,
                **data_quality_audit(rec.data_quality),
            }
        )
    if not rec:
        snapshot = PortfolioSnapshot(
            snapshot_id=new_id("snap"),
            policy_id=policy_id,
            date=now_iso()[:10],
            current_weights={},
            created_at=now_iso(),
            audit=snapshot_audit,
        )
    else:
        metrics = rec.backtest_metrics if rec.backtest_metrics.get("status") == "available" else {}
        snapshot = PortfolioSnapshot(
            snapshot_id=new_id("snap"),
            policy_id=policy_id,
            date=now_iso()[:10],
            current_weights={item.ticker: item.weight for item in rec.weights},
            portfolio_value=policy.initial_capital,
            return_since_inception=metrics.get("total_return_pct"),
            period_return=metrics.get("total_return_pct"),
            benchmark_return=metrics.get("benchmark_return_pct"),
            volatility=metrics.get("annualized_volatility_pct"),
            max_drawdown=metrics.get("max_drawdown_pct"),
            sharpe=metrics.get("sharpe"),
            sortino=metrics.get("sortino"),
            risk_contribution=rec.risk_metrics.get("risk_contributions", {}) if isinstance(rec.risk_metrics, dict) else {},
            created_at=now_iso(),
            audit=snapshot_audit,
        )
    append_item("snapshots", snapshot.model_dump(mode="json"))
    _event(policy_id, "performance_snapshot_created", after=snapshot.model_dump(mode="json"), summary="성과 스냅샷 생성")
    return snapshot


def list_snapshots(policy_id: str) -> list[PortfolioSnapshot]:
    return [PortfolioSnapshot.model_validate(item) for item in filter_items("snapshots", policy_id=policy_id)]


def check_rebalance(policy_id: str, current_weights: dict[str, float]) -> RebalanceSignal:
    policy = get_policy(policy_id)
    if not policy:
        raise KeyError(policy_id)
    recommendation = latest_recommendation(policy_id)
    if not recommendation:
        raise LookupError("recommendation_not_found")
    signal = calculate_rebalance_signal(policy=policy, recommendation=recommendation, current_weights=current_weights)
    append_item("signals", signal.model_dump(mode="json"))
    _event(policy_id, "rebalance_checked", after=signal.model_dump(mode="json"), summary=f"리밸런싱 점검: {signal.rebalance_required}")
    if signal.rebalance_required:
        _event(policy_id, "rebalance_signal_created", after=signal.model_dump(mode="json"), summary="리밸런싱 신호 생성")
    return signal


def list_signals(policy_id: str) -> list[RebalanceSignal]:
    return [RebalanceSignal.model_validate(item) for item in filter_items("signals", policy_id=policy_id)]


def update_signal_status(signal_id: str, status: str, action_request: RebalanceActionRequest | None = None) -> RebalanceSignal:
    existing = get_item("signals", "signal_id", signal_id)
    if not existing:
        raise KeyError(signal_id)
    before = dict(existing)
    action_request = action_request or RebalanceActionRequest()
    actor = str(action_request.actor or "user").strip() or "user"
    reason = str(action_request.reason or "").strip()
    audit = dict(existing.get("audit") or {})
    audit.update(
        {
            "decision_request_id": request_id("act"),
            "decision_at": now_iso(),
            "decision_actor": actor,
            "decision_status": status,
            "decision_reason_hash": stable_hash(reason) if reason else None,
        }
    )
    update_payload: dict[str, Any] = {
        "status": status,
        "decision_reason": reason or None,
        "audit": audit,
    }
    if status == "approved":
        update_payload["approved_by"] = actor
    elif status == "rejected":
        update_payload["rejected_reason"] = reason or None
    elif status == "deferred":
        update_payload["deferred_until"] = action_request.deferred_until or existing.get("next_review_at")
    updated = update_item("signals", "signal_id", signal_id, update_payload)
    signal = RebalanceSignal.model_validate(updated)
    event_type = {
        "approved": "rebalance_approved",
        "rejected": "rebalance_rejected",
        "deferred": "rebalance_deferred",
    }.get(status, "rebalance_checked")
    _event(signal.policy_id, event_type, before=before, after=signal.model_dump(mode="json"), summary=f"리밸런싱 신호 상태 변경: {status}", actor="user")
    return signal


def list_history(policy_id: str) -> list[PortfolioHistoryEvent]:
    return [PortfolioHistoryEvent.model_validate(item) for item in filter_items("history", policy_id=policy_id)]


def generate_report(request: ReportGenerateRequest) -> dict[str, Any]:
    policy = get_policy(request.policy_id)
    if not policy:
        raise KeyError(request.policy_id)
    rec = latest_recommendation(request.policy_id)
    history = [item.model_dump(mode="json") for item in list_history(request.policy_id)]
    text = report_text(policy, rec, history, request.report_type)
    report_audit = {
        "request_id": request_id("rpt"),
        "config_hash": policy_config_hash(policy),
        "constraint_policy_hash": constraint_policy_hash(policy),
        "universe_hash": stable_hash({"universe_id": policy.universe_id}),
        "recommendation_id": rec.recommendation_id if rec else None,
        "history_event_count": len(history),
        "data_snapshot_timestamp": now_iso(),
    }
    report = {
        "report_id": new_id("rpt"),
        "policy_id": request.policy_id,
        "report_type": request.report_type,
        "created_at": now_iso(),
        "markdown": text,
        "audit": report_audit,
    }
    append_item("reports", report)
    _event(request.policy_id, "report_generated", after=report, summary=f"{request.report_type} 리포트 생성")
    return report


def list_reports(policy_id: str) -> list[dict[str, Any]]:
    return filter_items("reports", policy_id=policy_id)


def list_operations(limit: int = 25) -> list[dict[str, Any]]:
    bounded = max(1, min(200, int(limit or 25)))
    return list_items("operations")[:bounded]


def _pct(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if denominator in (None, 0):
        return None
    return round(float(numerator or 0) / float(denominator) * 100, 2)


def _coverage_status(pct_value: float | None, *, ok_at: float = 95.0) -> str:
    if pct_value is None:
        return "unavailable"
    if pct_value >= ok_at:
        return "ok"
    if pct_value > 0:
        return "partial"
    return "unavailable"


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _provider_status_counts(data_health: dict[str, Any]) -> dict[str, int]:
    rows = data_health.get("recent_provider_status") or []
    counts: dict[str, int] = {}
    for row in rows:
        status = str((row or {}).get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _compact_data_health(data_health: dict[str, Any]) -> dict[str, Any]:
    table_counts = data_health.get("table_counts") or {}
    count_keys = (
        "asset_identity",
        "asset_classification",
        "etf_exposure",
        "kr_equity_profile",
        "crypto_profile",
        "prices_daily",
        "fundamentals_snapshots",
        "valuation_metrics",
        "financial_statements",
        "filings",
        "sec_company_registry",
        "sec_financial_facts",
        "provider_status",
        "data_quality_checks",
    )
    return {
        "status": data_health.get("status", "unknown"),
        "database": data_health.get("database"),
        "table_counts": {key: int(table_counts.get(key) or 0) for key in count_keys},
        "latest_fundamental": data_health.get("latest_fundamental"),
        "latest_sec_filing": data_health.get("latest_sec_filing"),
        "latest_sec_fact": data_health.get("latest_sec_fact"),
        "latest_macro_observation": data_health.get("latest_macro_observation"),
        "latest_run": data_health.get("latest_run"),
        "provider_status_counts": _provider_status_counts(data_health),
    }


def _compact_operation(operation: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "operation_id": operation.get("operation_id"),
        "operation_type": operation.get("operation_type"),
        "status": operation.get("status"),
        "created_at": operation.get("created_at"),
        "request_id": operation.get("request_id"),
        "policy_count": operation.get("policy_count"),
        "created_count": operation.get("created_count"),
        "failure_count": operation.get("failure_count"),
        "asset_count": operation.get("asset_count"),
    }
    if isinstance(operation.get("sec_result"), dict):
        result = operation["sec_result"]
        compact["sec_result"] = {
            "run_id": result.get("run_id"),
            "status": result.get("status"),
            "rows_inserted": result.get("rows_inserted"),
            "rows_updated": result.get("rows_updated"),
            "provider_status_counts": result.get("provider_status_counts", {}),
        }
    if isinstance(operation.get("metadata_result"), dict):
        compact["metadata_result"] = operation["metadata_result"]
    return {key: value for key, value in compact.items() if value is not None}


def _selected_policy(policies: list[PortfolioPolicy], policy_id: str | None) -> PortfolioPolicy | None:
    if policy_id:
        return next((policy for policy in policies if policy.policy_id == policy_id), None)
    return (
        next((policy for policy in policies if policy.status == "active"), None)
        or (policies[0] if policies else None)
    )


def _snapshot_points(policy: PortfolioPolicy | None, policies: list[PortfolioPolicy], limit: int) -> list[PortfolioSnapshotTimelinePoint]:
    names = {item.policy_id: item.portfolio_name for item in policies}
    points: list[PortfolioSnapshotTimelinePoint] = []
    for item in list_items("snapshots"):
        if policy and str(item.get("policy_id")) != policy.policy_id:
            continue
        try:
            snapshot = PortfolioSnapshot.model_validate(item)
        except Exception:
            continue
        price_coverage = (snapshot.audit or {}).get("price_data_coverage") or {}
        price_pct = price_coverage.get("available_pct")
        points.append(
            PortfolioSnapshotTimelinePoint(
                snapshot_id=snapshot.snapshot_id,
                policy_id=snapshot.policy_id,
                policy_name=names.get(snapshot.policy_id),
                date=snapshot.date,
                created_at=snapshot.created_at,
                portfolio_value=snapshot.portfolio_value,
                period_return=snapshot.period_return,
                benchmark_return=snapshot.benchmark_return,
                volatility=snapshot.volatility,
                max_drawdown=snapshot.max_drawdown,
                sharpe=snapshot.sharpe,
                coverage_status=_coverage_status(float(price_pct)) if price_pct is not None else "unavailable",
                price_available_pct=float(price_pct) if price_pct is not None else None,
                audit=snapshot.audit,
            )
        )
    return sorted(points, key=lambda item: item.created_at, reverse=True)[: max(1, min(50, limit))]


def _coverage_rows(recommendation: PortfolioRecommendation | None, data_health: dict[str, Any]) -> list[PortfolioCoverageRow]:
    table_counts = (data_health.get("table_counts") or {})
    dq = recommendation.data_quality if recommendation else None
    coverage = dq.metadata_coverage if dq else {}
    price_pct = _pct(dq.available_asset_count if dq else None, dq.asset_count if dq else None)
    fundamentals_pct = coverage.get("fundamentals_pct") if isinstance(coverage, dict) else None
    sector_pct = coverage.get("sector_pct") if isinstance(coverage, dict) else None
    provider_counts = _provider_status_counts(data_health)
    provider_total = sum(provider_counts.values())
    provider_ok = provider_counts.get("ok", 0) + provider_counts.get("success", 0) + provider_counts.get("completed", 0)
    provider_pct = _pct(provider_ok, provider_total)
    metadata_total = int(table_counts.get("asset_identity") or 0)
    classification_total = int(table_counts.get("asset_classification") or 0)
    return [
        PortfolioCoverageRow(
            id="price_data",
            label="Price Data",
            status=_coverage_status(price_pct),
            available_count=dq.available_asset_count if dq else None,
            total_count=dq.asset_count if dq else None,
            pct=price_pct,
            latest_at=(data_health.get("latest_run") or {}).get("finished_at") if isinstance(data_health.get("latest_run"), dict) else None,
            detail="Selected policy universe price coverage",
            metadata={
                "missing_assets": list(dq.missing_assets if dq else [])[:20],
                "insufficient_assets": list(dq.insufficient_assets if dq else [])[:20],
            },
        ),
        PortfolioCoverageRow(
            id="fundamentals",
            label="Fundamentals",
            status=_coverage_status(float(fundamentals_pct)) if fundamentals_pct is not None else "unavailable",
            available_count=int(coverage.get("fundamentals_count") or 0) if isinstance(coverage, dict) else None,
            total_count=dq.asset_count if dq else None,
            pct=float(fundamentals_pct) if fundamentals_pct is not None else None,
            latest_at=(data_health.get("latest_fundamental") or {}).get("collected_at") if isinstance(data_health.get("latest_fundamental"), dict) else None,
            detail="Provider-backed fundamentals snapshots for selected universe",
        ),
        PortfolioCoverageRow(
            id="metadata",
            label="Asset Metadata",
            status=_coverage_status(float(sector_pct)) if sector_pct is not None else ("ok" if metadata_total else "unavailable"),
            available_count=classification_total or metadata_total or None,
            total_count=dq.asset_count if dq else None,
            pct=float(sector_pct) if sector_pct is not None else None,
            detail="Identity, classification, ETF, Korea, and crypto metadata",
            metadata={
                "asset_identity": metadata_total,
                "asset_classification": classification_total,
                "etf_exposure": int(table_counts.get("etf_exposure") or 0),
                "kr_equity_profile": int(table_counts.get("kr_equity_profile") or 0),
                "crypto_profile": int(table_counts.get("crypto_profile") or 0),
            },
        ),
        PortfolioCoverageRow(
            id="sec_financials",
            label="SEC Financials",
            status="ok" if int(table_counts.get("sec_financial_facts") or 0) else "unavailable",
            available_count=int(table_counts.get("sec_company_registry") or 0),
            total_count=int(table_counts.get("sec_financial_facts") or 0),
            pct=None,
            latest_at=(data_health.get("latest_sec_fact") or {}).get("collected_at") if isinstance(data_health.get("latest_sec_fact"), dict) else None,
            detail="SEC company registry, filings, and companyfacts rows",
            metadata={
                "filings": int(table_counts.get("filings") or 0),
                "sec_company_registry": int(table_counts.get("sec_company_registry") or 0),
                "sec_financial_facts": int(table_counts.get("sec_financial_facts") or 0),
            },
        ),
        PortfolioCoverageRow(
            id="provider_status",
            label="Provider Status",
            status=_coverage_status(provider_pct, ok_at=80.0) if provider_total else "unavailable",
            available_count=provider_ok if provider_total else None,
            total_count=provider_total or None,
            pct=provider_pct,
            latest_at=(data_health.get("latest_run") or {}).get("finished_at") if isinstance(data_health.get("latest_run"), dict) else None,
            detail="Recent provider run status mix",
            metadata={"status_counts": provider_counts},
        ),
    ]


def portfolio_dashboard(policy_id: str | None = None, *, limit: int = 12) -> PortfolioDashboardResponse:
    policies = list_policies()
    policy = _selected_policy(policies, policy_id)
    latest = latest_recommendation(policy.policy_id) if policy else None
    snapshots = _snapshot_points(policy if policy_id else None, policies, limit)
    data_health = data_repository.data_health()
    operations = list_operations(50)
    policy_counts = _count_by([policy.model_dump(mode="json") for policy in policies], "status")
    if policies:
        policy_counts["total"] = len(policies)
    selected_summary = None
    if policy:
        dq = latest.data_quality if latest else None
        price_pct = _pct(dq.available_asset_count if dq else None, dq.asset_count if dq else None)
        data_status = _coverage_status(price_pct) if latest else "unavailable"
        selected_snapshots = [item for item in snapshots if item.policy_id == policy.policy_id]
        selected_summary = PortfolioDashboardPolicySummary(
            policy_id=policy.policy_id,
            portfolio_name=policy.portfolio_name,
            status=policy.status,
            investment_type=policy.investment_type,
            universe_id=policy.universe_id,
            automation_level=policy.automation_level,
            latest_recommendation_id=latest.recommendation_id if latest else None,
            latest_recommendation_at=latest.created_at if latest else None,
            latest_snapshot_at=selected_snapshots[0].created_at if selected_snapshots else None,
            data_quality_status=data_status,
        )
    return PortfolioDashboardResponse(
        generated_at=now_iso(),
        selected_policy=selected_summary,
        policy_counts=policy_counts,
        store_status=storage_status(),
        data_health_summary=_compact_data_health(data_health),
        coverage_rows=_coverage_rows(latest, data_health),
        snapshot_timeline=snapshots,
        operation_summary=PortfolioOperationSummary(
            total_count=len(operations),
            by_type=_count_by(operations, "operation_type"),
            by_status=_count_by(operations, "status"),
            recent_operations=[_compact_operation(item) for item in operations[:10]],
        ),
    )


def recommendation_diff(policy_id: str) -> dict[str, Any]:
    recommendations = sorted(list_recommendations(policy_id), key=lambda item: item.created_at, reverse=True)
    if len(recommendations) < 2:
        return {
            "status": "insufficient_history",
            "policy_id": policy_id,
            "message": "비교할 이전 추천이 없습니다.",
            "changes": [],
        }
    latest, previous = recommendations[0], recommendations[1]
    latest_weights = {item.ticker: float(item.weight) for item in latest.weights}
    previous_weights = {item.ticker: float(item.weight) for item in previous.weights}
    changes = []
    for ticker in sorted(set(latest_weights) | set(previous_weights)):
        before = previous_weights.get(ticker, 0.0)
        after = latest_weights.get(ticker, 0.0)
        diff = round(after - before, 4)
        if abs(diff) < 0.0001:
            continue
        changes.append(
            {
                "ticker": ticker,
                "previous_weight": round(before, 4),
                "latest_weight": round(after, 4),
                "change": diff,
                "direction": "increase" if diff > 0 else "reduce",
            }
        )
    return {
        "status": "available",
        "policy_id": policy_id,
        "latest_recommendation_id": latest.recommendation_id,
        "previous_recommendation_id": previous.recommendation_id,
        "created_at": now_iso(),
        "audit": {
            "request_id": request_id("diff"),
            "latest_audit": latest.audit,
            "previous_audit": previous.audit,
            "diff_hash": stable_hash(changes),
        },
        "changes": sorted(changes, key=lambda item: abs(float(item["change"])), reverse=True),
    }


def run_data_activation(request: DataActivationRequest) -> dict[str, Any]:
    assets, source_meta = _assets_for_activation(request)
    target_assets = assets[: request.max_assets]
    tickers = _clean_tickers([getattr(asset, "ticker", "") for asset in target_assets if getattr(asset, "ticker", "") != "CASH"])
    operation_request_id = request_id("hydrate")
    metadata_rows = _asset_metadata_rows(target_assets)
    metadata_result = {"status": "dry_run", "rows": len(metadata_rows)}
    if not request.dry_run:
        metadata_result = {"status": "stored", **data_repository.upsert_universe_metadata(metadata_rows)}

    price_result: dict[str, Any] = {"status": "skipped", "reason": "hydrate_prices_disabled"}
    if request.hydrate_prices:
        if request.dry_run:
            availability = data_repository.price_availability(tickers, min_rows=request.min_price_rows)
            missing = [ticker for ticker, item in availability.items() if not item.get("available")]
            price_result = {
                "status": "dry_run",
                "candidate_count": len(missing),
                "missing_assets": missing[:100],
                "availability": availability,
            }
        else:
            price_result = ensure_price_history(
                tickers,
                min_rows=request.min_price_rows,
                hydrate_missing=True,
                max_hydrate_assets=request.max_assets,
            )
            price_result["status"] = "completed"

    fundamentals_result: dict[str, Any] = {"status": "skipped", "reason": "hydrate_fundamentals_disabled"}
    if request.hydrate_fundamentals:
        before = data_repository.fundamentals_availability(tickers)
        missing_before = [ticker for ticker, item in before.items() if not item.get("available")]
        if request.dry_run:
            fundamentals_result = {
                "status": "dry_run",
                "candidate_count": len(missing_before),
                "missing_assets": missing_before[:100],
            }
        else:
            attempted = missing_before[: request.max_assets] or tickers[: request.max_assets]
            hydrated: list[str] = []
            failed: list[str] = []
            for ticker in attempted:
                card = collect_fundamentals_card(ticker, timeout_s=5.0, persist=True)
                if card is None:
                    failed.append(ticker)
                else:
                    hydrated.append(ticker)
            after = data_repository.fundamentals_availability(tickers)
            fundamentals_result = {
                "status": "completed",
                "attempted_count": len(attempted),
                "hydrated_count": len(hydrated),
                "failed_count": len(failed),
                "hydrated": hydrated[:100],
                "failed": failed[:100],
                "still_missing": [ticker for ticker, item in after.items() if not item.get("available")][:100],
            }

    operation = _save_operation(
        "data_activation",
        {
            "status": "dry_run" if request.dry_run else "completed",
            "request_id": operation_request_id,
            "request": request.model_dump(mode="json"),
            "source": source_meta,
            "asset_count": len(assets),
            "processed_asset_count": len(target_assets),
            "ticker_count": len(tickers),
            "metadata_result": metadata_result,
            "price_result": price_result,
            "fundamentals_result": fundamentals_result,
            "data_health": data_repository.data_health(),
        },
    )
    if request.policy_id:
        _event(
            request.policy_id,
            "data_activation_run",
            after=operation,
            summary=f"데이터 활성화 작업: {operation['status']}",
            audit={
                "request_id": operation_request_id,
                "universe_hash": source_meta.get("universe_hash"),
                "operation_id": operation["operation_id"],
            },
        )
    return operation


def run_sec_data_refresh(request: SecDataRefreshRequest) -> dict[str, Any]:
    activation_request = DataActivationRequest(
        policy_id=request.policy_id,
        universe_id=request.universe_id,
        tickers=request.tickers,
        hydrate_prices=False,
        hydrate_fundamentals=False,
        dry_run=True,
        max_assets=request.max_assets,
    )
    assets, source_meta = _assets_for_activation(activation_request)
    target_assets = assets[: request.max_assets]
    tickers = _clean_tickers([getattr(asset, "ticker", "") for asset in target_assets if getattr(asset, "ticker", "") != "CASH"])
    operation_request_id = request_id("sec")
    before = data_repository.sec_data_availability(tickers)
    available_before = [ticker for ticker, item in before.items() if item.get("available")]

    if request.dry_run:
        sec_result: dict[str, Any] = {
            "status": "dry_run",
            "candidate_count": len(tickers),
            "available_before_count": len(available_before),
            "missing_before": [ticker for ticker, item in before.items() if not item.get("available")][:100],
        }
        after = before
    else:
        result = update_sec_company_data(
            tickers,
            forms=request.forms,
            lookback_days=request.lookback_days,
            max_assets=request.max_assets,
            hydrate_financials=request.hydrate_financials,
        )
        after = data_repository.sec_data_availability(tickers)
        provider_status_counts: dict[str, int] = {}
        for provider in result.providers:
            provider_status_counts[provider.status] = provider_status_counts.get(provider.status, 0) + 1
        sec_result = {
            "status": result.status,
            "run_id": result.run_id,
            "rows_inserted": result.rows_inserted,
            "rows_updated": result.rows_updated,
            "error_message": result.error_message,
            "provider_status_counts": provider_status_counts,
            "available_after_count": len([ticker for ticker, item in after.items() if item.get("available")]),
            "missing_after": [ticker for ticker, item in after.items() if not item.get("available")][:100],
        }

    operation = _save_operation(
        "sec_data_refresh",
        {
            "status": "dry_run" if request.dry_run else sec_result.get("status", "unknown"),
            "request_id": operation_request_id,
            "request": request.model_dump(mode="json"),
            "source": source_meta,
            "asset_count": len(assets),
            "processed_asset_count": len(target_assets),
            "ticker_count": len(tickers),
            "sec_result": sec_result,
            "sec_availability_before": before,
            "sec_availability_after": after,
            "data_health": data_repository.data_health(),
        },
    )
    if request.policy_id:
        _event(
            request.policy_id,
            "sec_data_refresh_run",
            after=operation,
            summary=f"SEC data refresh: {operation['status']}",
            audit={
                "request_id": operation_request_id,
                "universe_hash": source_meta.get("universe_hash"),
                "operation_id": operation["operation_id"],
            },
        )
    return operation


def run_snapshot_job(request: SnapshotJobRequest) -> dict[str, Any]:
    if request.policy_id:
        policies = [get_policy(request.policy_id)]
        if not policies[0]:
            raise KeyError(request.policy_id)
    else:
        policies = list_policies()
        if request.active_only:
            policies = [policy for policy in policies if policy.status == "active"]
    snapshots: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for policy in [item for item in policies if item]:
        try:
            snapshot = create_snapshot(policy.policy_id)
            snapshots.append(snapshot.model_dump(mode="json"))
        except Exception as exc:  # noqa: BLE001 - operation result must preserve per-policy failure.
            failures.append({"policy_id": policy.policy_id, "error": str(exc)})
    operation = _save_operation(
        "snapshot_job",
        {
            "status": "completed" if not failures else "partial",
            "request_id": request_id("snapjob"),
            "request": request.model_dump(mode="json"),
            "policy_count": len([item for item in policies if item]),
            "created_count": len(snapshots),
            "failure_count": len(failures),
            "snapshots": snapshots,
            "failures": failures,
        },
    )
    return operation
