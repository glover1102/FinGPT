from __future__ import annotations

import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.api.routers.market_utils import clean_ticker_list, returns_from_price_rows
from core.schemas.ai_portfolio import (
    DataQuality,
    PortfolioPolicy,
    PortfolioRecommendation,
    PortfolioWeight,
)
from core.utils.symbol_registry import symbol_display_name, symbol_identities
from pipelines.ai_portfolio.audit import recommendation_audit, ticker_universe_hash
from pipelines.ai_portfolio.rules import apply_constraint_status, check_constraints, normalize_asset_class
from pipelines.data_mart.jobs.ensure_price_history import ensure_price_history
from pipelines.data_mart.storage.repository import fundamentals_availability
from pipelines.data_mart.storage.repository import get_prices as data_mart_get_prices
from pipelines.portfolio.optimizer import optimize_portfolio


BOND_ETFS = {
    "AGG",
    "BND",
    "BNDX",
    "GOVT",
    "IEF",
    "TLT",
    "SHY",
    "LQD",
    "HYG",
    "MUB",
    "TIP",
    "VCIT",
    "VCSH",
}
CASH_ETFS = {"SGOV", "BIL", "SHV", "MINT", "JPST", "CASH"}
ALTERNATIVE_ETFS = {"GLD", "IAU", "SLV", "USO", "DBC", "VNQ", "REET", "BTC-USD", "ETH-USD"}
DEFAULT_MULTI_ASSET = ["SPY", "QQQ", "TLT", "BND", "GLD", "SGOV"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

UNIVERSE_PRESET_LABELS: dict[str, str] = {
    "default_multi_asset": "기본 멀티에셋",
    "quant_lab_default": "Quant Lab 기본",
    "sp500_top_200": "미국 대형주 200",
    "etf_core_100": "주요 ETF 100",
    "kr_300": "한국 300",
    "crypto_core": "암호화폐 2",
    "all_supported": "전체 지원 유니버스",
}

UNIVERSE_PRESET_DESCRIPTIONS: dict[str, str] = {
    "default_multi_asset": "미국 주식, 장기채, 종합채권, 금, 현금성 ETF를 함께 사용하는 기본 정책 유니버스입니다.",
    "quant_lab_default": "기존 Quant Lab 기본값과 같은 SPY, TLT, GLD 조합입니다.",
    "sp500_top_200": "앱 심볼 카탈로그의 S&P 500 대형주 상위 200개 범위입니다.",
    "etf_core_100": "주요 지수, 섹터, 채권, 원자재, 글로벌 ETF 100개 범위입니다.",
    "kr_300": "KOSPI 200과 KOSDAQ 100을 합친 한국 주식 300개 범위입니다.",
    "crypto_core": "BTC-USD와 ETH-USD만 포함하는 암호화폐 핵심 범위입니다.",
    "all_supported": "미국 대형주 200, ETF 100, 한국 300, 암호화폐 2를 모두 포함합니다.",
}

UNIVERSE_PRESET_LABELS.update(
    {
        "default_multi_asset": "기본 멀티에셋",
        "quant_lab_default": "Quant Lab 기본",
        "sp500_top_200": "미국 대형주 200",
        "etf_core_100": "주요 ETF 100",
        "kr_300": "한국 300",
        "crypto_core": "암호화폐 2",
        "all_supported": "전체 지원 유니버스",
    }
)

UNIVERSE_PRESET_DESCRIPTIONS.update(
    {
        "default_multi_asset": "미국 주식, 장기채, 금, 현금성 ETF를 함께 쓰는 기본 정책 유니버스입니다.",
        "quant_lab_default": "기존 Quant Lab 기본값과 같은 SPY, TLT, GLD 조합입니다.",
        "sp500_top_200": "심볼 레지스트리의 S&P 500 대형주 상위 200개 범위입니다.",
        "etf_core_100": "주요 지수, 섹터, 채권, 원자재, 글로벌 ETF 100개 범위입니다.",
        "kr_300": "KOSPI 200과 KOSDAQ 100을 합친 한국 주식 300개 범위입니다.",
        "crypto_core": "BTC-USD와 ETH-USD만 포함하는 암호화폐 핵심 범위입니다.",
        "all_supported": "미국 대형주 200, ETF 100, 한국 300, 암호화폐 2를 모두 포함합니다.",
    }
)

ETF_SECTOR_MAP: dict[str, str] = {
    "XLK": "TECHNOLOGY",
    "VGT": "TECHNOLOGY",
    "SMH": "TECHNOLOGY",
    "SOXX": "TECHNOLOGY",
    "XLF": "FINANCIAL",
    "VFH": "FINANCIAL",
    "KRE": "FINANCIAL",
    "XLV": "HEALTHCARE",
    "VHT": "HEALTHCARE",
    "XBI": "HEALTHCARE",
    "IBB": "HEALTHCARE",
    "XLY": "CONSUMER CYCLICAL",
    "VCR": "CONSUMER CYCLICAL",
    "XRT": "CONSUMER CYCLICAL",
    "ITB": "CONSUMER CYCLICAL",
    "XLP": "CONSUMER DEFENSIVE",
    "VDC": "CONSUMER DEFENSIVE",
    "XLE": "ENERGY",
    "VDE": "ENERGY",
    "XOP": "ENERGY",
    "XLI": "INDUSTRIALS",
    "VIS": "INDUSTRIALS",
    "XLU": "UTILITIES",
    "VPU": "UTILITIES",
    "XLB": "BASIC MATERIALS",
    "VAW": "BASIC MATERIALS",
    "XLRE": "REAL ESTATE",
    "VNQ": "REAL ESTATE",
    "IYR": "REAL ESTATE",
    "REET": "REAL ESTATE",
    "XLC": "COMMUNICATION SERVICES",
    "GLD": "COMMODITY",
    "IAU": "COMMODITY",
    "SLV": "COMMODITY",
    "USO": "COMMODITY",
    "DBC": "COMMODITY",
}


@dataclass(frozen=True)
class UniverseAsset:
    ticker: str
    name: str
    asset_class: str
    sector: str = ""
    source: str = "symbol_registry"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:10]}"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _canonical_universe_id(universe_id: str | None) -> str:
    raw = str(universe_id or "default_multi_asset").strip()
    if not raw:
        return "default_multi_asset"
    if "," in raw or raw.lower().startswith("custom:"):
        return "custom"
    clean = raw.lower()
    aliases = {
        "default": "default_multi_asset",
        "existing_universe_id": "default_multi_asset",
        "core_balanced": "quant_lab_default",
        "us_large_cap_200": "sp500_top_200",
        "major_etf_100": "etf_core_100",
        "korea_300": "kr_300",
        "crypto": "crypto_core",
        "expanded_universe": "all_supported",
    }
    return aliases.get(clean, clean)


def universe_source(universe_id: str | None) -> str:
    return "direct_input" if _canonical_universe_id(universe_id) == "custom" else "preset"


@lru_cache(maxsize=1)
def _static_heatmap_sectors() -> dict[str, str]:
    source_path = PROJECT_ROOT / "app" / "web" / "app.js"
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    match = re.search(r"const\s+HEATMAP_CLASSIFICATION\s*=\s*\{(?P<body>.*?)\n\};", source, re.DOTALL)
    if not match:
        return {}
    sectors: dict[str, str] = {}
    line_re = re.compile(r'\s*(?:"(?P<quoted>[^"]+)"|(?P<bare>[A-Z0-9.\-]+))\s*:\s*\{\s*sector:\s*"(?P<sector>[^"]+)"')
    for raw_line in match.group("body").splitlines():
        found = line_re.match(raw_line)
        if not found:
            continue
        ticker = (found.group("quoted") or found.group("bare") or "").upper().strip()
        sector = (found.group("sector") or "").upper().strip()
        if ticker and sector:
            sectors[ticker] = sector
    return sectors


def sector_for_ticker(ticker: str, raw_class: str | None = None) -> str:
    ticker = str(ticker or "").upper().strip()
    if not ticker:
        return ""
    if ticker in ETF_SECTOR_MAP:
        return ETF_SECTOR_MAP[ticker]
    if ticker in BOND_ETFS:
        return "FIXED INCOME"
    if ticker in CASH_ETFS:
        return "CASH"
    if ticker in ALTERNATIVE_ETFS:
        return "ALTERNATIVE"
    if ticker.endswith(".KS"):
        return "KOSPI EQUITY"
    if ticker.endswith(".KQ"):
        return "KOSDAQ EQUITY"
    if str(raw_class or "").strip().lower() == "crypto":
        return "CRYPTO"
    return _static_heatmap_sectors().get(ticker, "")


def normalize_ai_asset_class(ticker: str, raw_class: str | None = None) -> str:
    ticker = ticker.upper().strip()
    if ticker in CASH_ETFS:
        return "cash"
    if ticker in BOND_ETFS:
        return "bond"
    if ticker in ALTERNATIVE_ETFS:
        return "alternative"
    clean = str(raw_class or "").strip().lower()
    if clean == "crypto":
        return "alternative"
    return normalize_asset_class(clean if clean not in {"stock", "etf"} else "equity")


def universe_label(universe_id: str | None) -> str:
    clean = _canonical_universe_id(universe_id)
    if clean == "custom":
        return "직접 입력 심볼 목록"
    return UNIVERSE_PRESET_LABELS.get(clean, str(universe_id or "default_multi_asset"))


def asset_role(asset_class: str) -> str:
    if asset_class == "bond":
        return "변동성 완충 / 금리 민감 자산"
    if asset_class == "cash":
        return "현금성 완충 / 리밸런싱 대기 자금"
    if asset_class == "alternative":
        return "분산 / 원자재·대체 노출"
    return "성장 / 주식 위험 프리미엄"


def asset_key_risk(asset_class: str) -> str:
    if asset_class == "bond":
        return "금리 상승, 신용 스프레드 확대"
    if asset_class == "cash":
        return "낮은 기대수익, 재투자 위험"
    if asset_class == "alternative":
        return "원자재·대체자산 변동성, 유동성"
    return "주식시장 하락, 실적/밸류에이션 재평가"


def _asset_from_ticker(ticker: str) -> UniverseAsset:
    identities = symbol_identities()
    identity = identities.get(ticker.upper())
    raw_class = identity.asset_class if identity else ""
    return UniverseAsset(
        ticker=ticker.upper().strip(),
        name=symbol_display_name(ticker) or ticker.upper().strip(),
        asset_class=normalize_ai_asset_class(ticker, raw_class),
        sector=sector_for_ticker(ticker, raw_class),
        source="symbol_registry" if identity else "custom",
    )


def load_universe(universe_id: str | None) -> tuple[list[UniverseAsset], list[str]]:
    raw = str(universe_id or "default_multi_asset").strip()
    clean = _canonical_universe_id(raw)
    warnings: list[str] = []
    identities = symbol_identities()
    if "," in raw or raw.lower().startswith("custom:"):
        tickers = clean_ticker_list(raw.split(":", 1)[1] if raw.lower().startswith("custom:") else raw)
    elif clean == "default_multi_asset":
        tickers = list(DEFAULT_MULTI_ASSET)
        if raw.lower() == "existing_universe_id":
            warnings.append("universe_alias_used:existing_universe_id->default_multi_asset")
    elif clean == "quant_lab_default":
        tickers = ["SPY", "TLT", "GLD"]
    elif clean == "sp500_top_200":
        tickers = [ticker for ticker, item in identities.items() if item.market == "US" and item.asset_class == "stock"][:200]
    elif clean == "etf_core_100":
        tickers = [ticker for ticker, item in identities.items() if item.asset_class == "etf"][:100]
    elif clean == "kr_300":
        tickers = [ticker for ticker, item in identities.items() if item.market == "KRX"][:300]
    elif clean == "crypto_core":
        tickers = ["BTC-USD", "ETH-USD"]
    elif clean == "all_supported":
        tickers = list(identities)[:602]
    else:
        warnings.append(f"universe_not_found:{raw}")
        return [], warnings
    assets = [_asset_from_ticker(ticker) for ticker in tickers]
    seen: set[str] = set()
    unique: list[UniverseAsset] = []
    for asset in assets:
        if not asset.ticker or asset.ticker in seen:
            continue
        seen.add(asset.ticker)
        unique.append(asset)
    return unique, warnings


def universe_presets() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for preset_id in [
        "default_multi_asset",
        "quant_lab_default",
        "sp500_top_200",
        "etf_core_100",
        "kr_300",
        "crypto_core",
        "all_supported",
    ]:
        assets, warnings = load_universe(preset_id)
        mix: dict[str, int] = {}
        for asset in assets:
            mix[asset.asset_class] = mix.get(asset.asset_class, 0) + 1
        out.append(
            {
                "id": preset_id,
                "display_name": universe_label(preset_id),
                "source_type": "preset",
                "description": UNIVERSE_PRESET_DESCRIPTIONS.get(preset_id, ""),
                "asset_count": len(assets),
                "asset_class_mix": mix,
                "sample_assets": [asset.ticker for asset in assets[:8]],
                "request_hint": preset_id,
                "warnings": warnings,
            }
        )
    out.append(
        {
            "id": "custom",
            "display_name": "직접 입력 심볼 목록",
            "source_type": "direct_input",
            "description": "사용자가 쉼표로 입력한 심볼만 사용합니다. 프리셋과 분리되며 요청 값은 custom:SPY,TLT 형식으로 전달됩니다.",
            "asset_count": 0,
            "asset_class_mix": {},
            "sample_assets": [],
            "request_hint": "custom:SPY,TLT,GLD",
        }
    )
    return out


def _price_hydration_result(assets: list[UniverseAsset], lookback_days: int) -> dict[str, Any]:
    tickers = [asset.ticker for asset in assets if asset.ticker != "CASH"]
    enabled = _env_bool("AI_PORTFOLIO_HYDRATE_MISSING", True)
    min_rows = max(2, min(252, int(max(2, lookback_days) // 4)))
    try:
        result = ensure_price_history(
            tickers,
            min_rows=min_rows,
            hydrate_missing=enabled,
            max_hydrate_assets=_env_int("AI_PORTFOLIO_MAX_HYDRATE_ASSETS", 750),
            batch_size=_env_int("AI_PORTFOLIO_HYDRATE_BATCH_SIZE", 40),
        )
        hydration = dict(result.get("hydration") or {})
        hydration["status"] = "completed"
        return hydration
    except Exception as exc:  # noqa: BLE001 - provider/network failure must stay visible in data quality.
        return {
            "enabled": enabled,
            "attempted": enabled,
            "status": "failed",
            "error": str(exc),
            "requested_count": len(tickers),
            "min_rows": min_rows,
        }


def load_price_data(assets: list[UniverseAsset], lookback_days: int) -> tuple[dict[str, list[dict[str, Any]]], list[str], list[str], dict[str, Any]]:
    hydration = _price_hydration_result(assets, lookback_days)
    price_data: dict[str, list[dict[str, Any]]] = {}
    missing: list[str] = []
    insufficient: list[str] = []
    for asset in assets:
        if asset.ticker == "CASH":
            continue
        rows = data_mart_get_prices(asset.ticker, limit=max(2, int(lookback_days)))
        if len(rows) < 2:
            missing.append(asset.ticker)
        elif len(rows) < min(21, max(2, int(lookback_days // 4))):
            insufficient.append(asset.ticker)
            price_data[asset.ticker] = rows
        else:
            price_data[asset.ticker] = rows
    return price_data, missing, insufficient, hydration


def calculate_returns(price_data: dict[str, list[dict[str, Any]]]) -> dict[str, list[float]]:
    returns: dict[str, list[float]] = {}
    for ticker, rows in price_data.items():
        values = returns_from_price_rows(rows)
        if len(values) >= 2:
            returns[ticker] = values
    return returns


def _method_candidates(method: str) -> list[str]:
    clean = str(method or "equal_weight").strip().lower()
    aliases = {
        "minimum_volatility_risk_parity_blend": ["minimum_volatility", "risk_parity"],
        "risk_parity_max_sharpe_blend": ["risk_parity", "max_sharpe"],
        "momentum_tilted_max_sharpe": ["momentum_tilt", "max_sharpe"],
        "income_stability": ["inverse_volatility", "minimum_volatility"],
        "defensive_min_volatility": ["minimum_volatility", "inverse_volatility"],
        "risk_parity_min_vol_blend": ["risk_parity", "minimum_volatility"],
    }
    return aliases.get(clean, [clean])


def _blend_weights(weight_sets: list[dict[str, float]]) -> dict[str, float]:
    if not weight_sets:
        return {}
    assets = sorted({asset for weights in weight_sets for asset in weights})
    blended = {asset: sum(weights.get(asset, 0.0) for weights in weight_sets) / len(weight_sets) for asset in assets}
    total = sum(blended.values())
    if total <= 0:
        return {asset: round(1 / len(assets), 8) for asset in assets} if assets else {}
    return {asset: round(value / total, 8) for asset, value in blended.items()}


def _optimize_core(
    returns_by_asset: dict[str, list[float]],
    *,
    method: str,
    max_weight: float,
    risk_model: str,
    benchmark: str,
) -> tuple[dict[str, float], dict[str, Any], list[str]]:
    warnings: list[str] = []
    results: list[dict[str, Any]] = []
    for candidate in _method_candidates(method):
        try:
            result = optimize_portfolio(
                returns_by_asset,
                method=candidate,
                max_weight=max_weight,
                covariance_method="diagonal_shrinkage" if risk_model in {"ledoit_wolf", "diagonal_shrinkage"} else "sample",
                shrinkage_alpha=0.1,
                benchmark=benchmark,
            )
            if result.get("status") == "success" and result.get("weights"):
                results.append(result)
            warnings.extend(str(item) for item in result.get("warnings", []))
        except ValueError as exc:
            warnings.append(f"{candidate}_unavailable:{exc}")
    if not results:
        return {}, {"status": "failed", "warnings": warnings}, warnings
    if len(results) == 1:
        result = results[0]
        return dict(result.get("weights") or {}), result, warnings
    blended_weights = _blend_weights([dict(item.get("weights") or {}) for item in results])
    base = dict(results[0])
    base["weights"] = blended_weights
    base["sum_weights"] = round(sum(blended_weights.values()), 8)
    base["method"] = method
    base["warnings"] = warnings
    base["diagnostics"] = {**dict(base.get("diagnostics") or {}), "optimizer": "hybrid_blend", "blended_methods": _method_candidates(method)}
    return blended_weights, base, warnings


def _template_fallback_weights(assets: list[UniverseAsset], policy: PortfolioPolicy) -> tuple[dict[str, float], list[str]]:
    warnings = ["price_data_unavailable:template_policy_midpoint_allocation_used"]
    if not assets:
        warnings.append("universe_empty:no_template_allocation_generated")
        return {}, warnings
    by_class: dict[str, list[UniverseAsset]] = {}
    for asset in assets:
        by_class.setdefault(asset.asset_class, []).append(asset)
    if policy.min_cash_weight > 0 and not by_class.get("cash"):
        by_class.setdefault("cash", []).append(UniverseAsset("CASH", "Cash", "cash", source="policy_cash_proxy"))
        warnings.append("cash_proxy_used:no_price_return_assumed_zero")
    weights: dict[str, float] = {}
    for asset_class, allowed in policy.asset_allocation_ranges.items():
        members = by_class.get(asset_class) or []
        if not members:
            continue
        midpoint = (allowed.min + allowed.max) / 2.0
        if asset_class == "cash":
            midpoint = max(midpoint, policy.min_cash_weight)
        per_asset = min(policy.max_single_asset_weight, midpoint / len(members))
        for member in members:
            weights[member.ticker] = weights.get(member.ticker, 0.0) + per_asset / 100.0
    total = sum(weights.values())
    if total <= 0 and assets:
        weights = {asset.ticker: 1.0 / len(assets) for asset in assets[: min(10, len(assets))]}
        total = sum(weights.values())
    if total > 0:
        weights = {ticker: value / total for ticker, value in weights.items()}
    return weights, warnings


def _reserve_cash_weight(
    weights: dict[str, float],
    assets: list[UniverseAsset],
    policy: PortfolioPolicy,
) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    target_cash = max(0.0, policy.min_cash_weight / 100.0)
    if target_cash <= 0:
        return weights, warnings
    cash_candidates = [asset.ticker for asset in assets if asset.asset_class == "cash"]
    cash_ticker = next((ticker for ticker in cash_candidates if ticker in weights), None)
    if not cash_ticker:
        cash_ticker = cash_candidates[0] if cash_candidates else "CASH"
        warnings.append("cash_proxy_used:no_price_return_assumed_zero" if cash_ticker == "CASH" else f"cash_reserve_added:{cash_ticker}")
    non_cash_total = sum(value for ticker, value in weights.items() if ticker != cash_ticker)
    if non_cash_total <= 0:
        return {cash_ticker: 1.0}, warnings
    scaled = {ticker: value / non_cash_total * max(0.0, 1.0 - target_cash) for ticker, value in weights.items() if ticker != cash_ticker}
    scaled[cash_ticker] = target_cash
    total = sum(scaled.values())
    return {ticker: value / total for ticker, value in scaled.items()} if total else scaled, warnings


def _enforce_asset_class_ranges(
    weights: dict[str, float],
    assets: list[UniverseAsset],
    policy: PortfolioPolicy,
) -> tuple[dict[str, float], list[str]]:
    if not weights:
        return weights, []
    warnings: list[str] = []
    total = sum(max(float(value), 0.0) for value in weights.values())
    if total <= 0:
        return weights, []
    current = {ticker: max(float(value), 0.0) / total for ticker, value in weights.items()}
    meta = {asset.ticker: asset for asset in assets}
    if "CASH" in current and "CASH" not in meta:
        meta["CASH"] = UniverseAsset("CASH", "Cash", "cash", source="policy_cash_proxy")

    members_by_class: dict[str, list[str]] = {}
    for ticker, asset in meta.items():
        members_by_class.setdefault(asset.asset_class, []).append(ticker)

    cap = max(0.0, min(policy.max_single_asset_weight / 100.0, 1.0))
    lowers: dict[str, float] = {}
    uppers: dict[str, float] = {}
    targets: dict[str, float] = {}
    for asset_class, allowed in policy.asset_allocation_ranges.items():
        members = members_by_class.get(asset_class, [])
        lower = max(0.0, allowed.min / 100.0)
        upper = min(1.0, allowed.max / 100.0)
        if asset_class == "cash":
            lower = max(lower, policy.min_cash_weight / 100.0)
        if not members:
            if lower > 0:
                warnings.append(f"asset_class_{asset_class}_unavailable:minimum_not_enforced")
            lower = 0.0
            upper = 0.0
        if cap > 0 and members:
            feasible_upper = min(upper, cap * len(members))
            if feasible_upper + 1e-10 < lower:
                warnings.append(f"asset_class_{asset_class}_minimum_infeasible:max_single_asset_cap")
                lower = feasible_upper
            upper = feasible_upper
        group_current = sum(current.get(ticker, 0.0) for ticker in members)
        lowers[asset_class] = lower
        uppers[asset_class] = max(lower, upper)
        targets[asset_class] = min(max(group_current, lower), max(lower, upper))

    for asset_class, members in members_by_class.items():
        if asset_class not in targets:
            group_current = sum(current.get(ticker, 0.0) for ticker in members)
            lowers[asset_class] = 0.0
            uppers[asset_class] = 1.0
            targets[asset_class] = group_current

    for _ in range(20):
        target_total = sum(targets.values())
        delta = 1.0 - target_total
        if abs(delta) <= 1e-8:
            break
        if delta > 0:
            capacity = {key: max(uppers.get(key, 1.0) - targets[key], 0.0) for key in targets}
            total_capacity = sum(capacity.values())
            if total_capacity <= 1e-10:
                warnings.append("asset_class_ranges_infeasible:surplus_unallocated")
                break
            for key, value in capacity.items():
                targets[key] += delta * value / total_capacity
        else:
            reducible = {key: max(targets[key] - lowers.get(key, 0.0), 0.0) for key in targets}
            total_reducible = sum(reducible.values())
            if total_reducible <= 1e-10:
                warnings.append("asset_class_ranges_infeasible:excess_not_reduced")
                break
            excess = abs(delta)
            for key, value in reducible.items():
                targets[key] -= excess * value / total_reducible

    out: dict[str, float] = {}
    for asset_class, members in members_by_class.items():
        target = max(targets.get(asset_class, 0.0), 0.0)
        if target <= 0:
            continue
        scores = {ticker: current.get(ticker, 0.0) for ticker in members}
        if any(value > 0 for value in scores.values()):
            scores = {ticker: (value if value > 0 else 1.0) for ticker, value in scores.items()}
        else:
            scores = {ticker: 1.0 for ticker in members}
        score_total = sum(scores.values()) or float(len(members))
        relative = {ticker: value / score_total for ticker, value in scores.items()}
        if cap > 0:
            relative, cap_warnings = _enforce_max_weight(relative, min(1.0, cap / max(target, 1e-10)))
            warnings.extend(f"{asset_class}_{warning}" for warning in cap_warnings)
        for ticker in members:
            out[ticker] = target * relative.get(ticker, 0.0)
    out_total = sum(out.values())
    if out_total <= 0:
        return current, warnings
    normalized = {ticker: value / out_total for ticker, value in out.items()}
    changed = any(abs(normalized.get(ticker, 0.0) - current.get(ticker, 0.0)) > 1e-5 for ticker in set(normalized) | set(current))
    if changed:
        warnings.append("asset_class_ranges_adjusted_to_policy")
    return normalized, warnings


def _enforce_max_weight(weights: dict[str, float], cap: float) -> tuple[dict[str, float], list[str]]:
    cap = max(0.0, min(float(cap or 1.0), 1.0))
    if not weights or cap <= 0:
        return weights, []
    feasible_floor = 1.0 / max(len(weights), 1)
    warnings: list[str] = []
    if cap < feasible_floor:
        warnings.append(f"max_single_asset_weight_infeasible:raised_to_{feasible_floor:.4f}")
        cap = feasible_floor
    out = {ticker: max(float(weight), 0.0) for ticker, weight in weights.items()}
    total = sum(out.values()) or 1.0
    out = {ticker: weight / total for ticker, weight in out.items()}
    for _ in range(20):
        over = {ticker: weight for ticker, weight in out.items() if weight > cap + 1e-10}
        if not over:
            break
        excess = sum(weight - cap for weight in over.values())
        for ticker in over:
            out[ticker] = cap
        under = [ticker for ticker, weight in out.items() if weight < cap - 1e-10]
        if not under or excess <= 0:
            break
        capacity = {ticker: cap - out[ticker] for ticker in under}
        total_capacity = sum(capacity.values())
        if total_capacity <= 0:
            break
        for ticker in under:
            out[ticker] += min(capacity[ticker], excess * capacity[ticker] / total_capacity)
    total = sum(out.values()) or 1.0
    return {ticker: weight / total for ticker, weight in out.items()}, warnings


def _price_value(row: dict[str, Any]) -> float | None:
    value = row.get("adjusted_close")
    if value is None:
        value = row.get("close")
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out > 0 else None


def _aligned_weighted_returns(weights: dict[str, float], price_data: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[str]]:
    price_by_date: dict[str, dict[str, float]] = {}
    for ticker, rows in price_data.items():
        previous: float | None = None
        for row in sorted(rows, key=lambda item: str(item.get("date") or "")):
            price = _price_value(row)
            date = str(row.get("date") or "")
            if not price or not date:
                continue
            if previous is not None and previous > 0:
                price_by_date.setdefault(date, {})[ticker] = price / previous - 1.0
            previous = price
    active = [ticker for ticker, weight in weights.items() if weight > 0 and ticker != "CASH"]
    if not active:
        return [], []
    common_dates = sorted(date for date, values in price_by_date.items() if all(ticker in values for ticker in active))
    rows: list[dict[str, Any]] = []
    nav = 1.0
    peak = 1.0
    for date in common_dates:
        daily = sum(weights.get(ticker, 0.0) * price_by_date[date][ticker] for ticker in active)
        nav *= 1.0 + daily
        peak = max(peak, nav)
        rows.append({"date": date, "return": daily, "equity": nav, "drawdown": nav / peak - 1.0})
    return rows, active


def _annualized_vol(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(variance, 0.0)) * math.sqrt(252)


def _max_drawdown(equity: list[float]) -> float | None:
    if not equity:
        return None
    peak = equity[0]
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            drawdown = min(drawdown, value / peak - 1.0)
    return drawdown


def run_backtest(weights: dict[str, float], price_data: dict[str, list[dict[str, Any]]], benchmark: str) -> dict[str, Any]:
    curve, active = _aligned_weighted_returns(weights, price_data)
    if len(curve) < 2:
        return {"status": "unavailable", "reason": "insufficient_common_price_history", "equity_curve": []}
    returns = [float(row["return"]) for row in curve]
    equity = [float(row["equity"]) for row in curve]
    total_return = equity[-1] / equity[0] - 1 if equity[0] else None
    vol = _annualized_vol(returns)
    downside = [min(value, 0.0) for value in returns]
    downside_vol = _annualized_vol(downside)
    avg = sum(returns) / len(returns)
    mdd = _max_drawdown(equity)
    benchmark_total_return = None
    if benchmark in price_data and len(price_data[benchmark]) >= 2:
        first = _price_value(price_data[benchmark][0])
        last = _price_value(price_data[benchmark][-1])
        if first and last:
            benchmark_total_return = last / first - 1.0
    return {
        "status": "available",
        "sample_count": len(curve),
        "used_assets": active,
        "total_return_pct": round((total_return or 0.0) * 100, 4),
        "annualized_return_pct": round(avg * 252 * 100, 4),
        "annualized_volatility_pct": round((vol or 0.0) * 100, 4),
        "max_drawdown_pct": round((mdd or 0.0) * 100, 4),
        "sharpe": round((avg * 252) / vol, 4) if vol else None,
        "sortino": round((avg * 252) / downside_vol, 4) if downside_vol else None,
        "benchmark_return_pct": round(benchmark_total_return * 100, 4) if benchmark_total_return is not None else None,
        "equity_curve": [
            {
                "date": row["date"],
                "equity": round(row["equity"], 6),
                "return_pct": round(row["return"] * 100, 4),
                "drawdown_pct": round(row["drawdown"] * 100, 4),
            }
            for row in curve[-400:]
        ],
    }


def _metadata_coverage(assets: list[UniverseAsset], used_assets: list[str]) -> dict[str, Any]:
    asset_map = {asset.ticker: asset for asset in assets}
    selected = [asset_map[ticker] for ticker in used_assets if ticker in asset_map]
    denominator = len(selected) or len(assets)
    target = selected if selected else assets
    with_sector = sum(1 for asset in target if asset.sector)
    with_name = sum(1 for asset in target if asset.name and asset.name != asset.ticker)
    fundamental_status = fundamentals_availability([asset.ticker for asset in target if asset.ticker != "CASH"])
    with_fundamentals = sum(1 for item in fundamental_status.values() if item.get("available"))
    return {
        "asset_count": len(assets),
        "evaluated_count": len(target),
        "sector_count": with_sector,
        "sector_pct": round(with_sector / denominator * 100, 2) if denominator else 0.0,
        "name_count": with_name,
        "name_pct": round(with_name / denominator * 100, 2) if denominator else 0.0,
        "fundamentals_count": with_fundamentals,
        "fundamentals_pct": round(with_fundamentals / denominator * 100, 2) if denominator else 0.0,
        "fundamentals_missing": [ticker for ticker, item in fundamental_status.items() if not item.get("available")][:50],
    }


def _weights_to_lines(weights: dict[str, float], assets: list[UniverseAsset]) -> list[PortfolioWeight]:
    meta = {asset.ticker: asset for asset in assets}
    if "CASH" in weights and "CASH" not in meta:
        meta["CASH"] = UniverseAsset("CASH", "Cash", "cash", source="policy_cash_proxy")
    out: list[PortfolioWeight] = []
    for ticker, decimal_weight in sorted(weights.items(), key=lambda item: item[1], reverse=True):
        asset = meta.get(ticker) or _asset_from_ticker(ticker)
        pct = round(float(decimal_weight) * 100, 4)
        out.append(
            PortfolioWeight(
                ticker=ticker,
                name=asset.name,
                asset_class=asset.asset_class,
                sector=asset.sector or None,
                weight=pct,
                weight_decimal=round(float(decimal_weight), 8),
                role=asset_role(asset.asset_class),
                key_risk=asset_key_risk(asset.asset_class),
                constraint_status="unchecked",
            )
        )
    return out


def generate_recommendation(policy: PortfolioPolicy) -> tuple[PortfolioRecommendation, list[str]]:
    warnings: list[str] = []
    assets, universe_warnings = load_universe(policy.universe_id)
    warnings.extend(universe_warnings)
    lookback_days = max(42, int(policy.lookback_window_months) * 21)
    price_data, missing_assets, insufficient_assets, hydration = load_price_data(assets, lookback_days)
    returns_by_asset = calculate_returns(price_data)
    used_assets = sorted(returns_by_asset)
    data_quality = DataQuality(
        universe_id=policy.universe_id,
        universe_source=universe_source(policy.universe_id),  # type: ignore[arg-type]
        universe_label=universe_label(policy.universe_id),
        asset_count=len(assets),
        available_asset_count=len(used_assets),
        universe_available=bool(assets),
        price_data_available=bool(returns_by_asset),
        backtest_available=False,
        missing_assets=missing_assets,
        insufficient_assets=insufficient_assets,
        used_assets=used_assets,
        metadata_coverage=_metadata_coverage(assets, used_assets),
        hydration=hydration,
        warnings=list(warnings),
    )
    if hydration.get("attempted"):
        warnings.append(
            "price_hydration_attempted:"
            f"requested={hydration.get('requested_count', 0)},"
            f"candidates={hydration.get('candidate_count', 0)},"
            f"hydrated={hydration.get('hydrated_count', 0)},"
            f"still_unavailable={hydration.get('still_unavailable_count', 0)}"
        )
    if hydration.get("status") == "failed":
        warnings.append(f"price_hydration_failed:{hydration.get('error', 'unknown')}")

    if returns_by_asset:
        max_weight = max(0.01, min(policy.max_single_asset_weight / 100.0, 1.0))
        core_weights, optimizer_result, optimizer_warnings = _optimize_core(
            returns_by_asset,
            method=policy.optimization_method,
            max_weight=max_weight,
            risk_model=policy.risk_model,
            benchmark=policy.benchmark,
        )
        warnings.extend(optimizer_warnings)
        if core_weights:
            weights, cash_warnings = _reserve_cash_weight(core_weights, assets, policy)
            warnings.extend(cash_warnings)
            weights, allocation_warnings = _enforce_asset_class_ranges(weights, assets, policy)
            warnings.extend(allocation_warnings)
            weights, cap_warnings = _enforce_max_weight(weights, policy.max_single_asset_weight / 100.0)
            warnings.extend(cap_warnings)
            expected_metrics = optimizer_result.get("portfolio_metrics", {}) if optimizer_result else {}
            risk_metrics = {
                "annualized_volatility_pct": round(float(expected_metrics.get("annualized_volatility", 0.0)) * 100, 4),
                "expected_annual_return_pct": round(float(expected_metrics.get("expected_annual_return", 0.0)) * 100, 4),
                "sharpe": expected_metrics.get("sharpe"),
                "risk_contributions": optimizer_result.get("risk_contributions", {}) if optimizer_result else {},
            }
        else:
            weights, fallback_warnings = _template_fallback_weights(assets, policy)
            warnings.extend(fallback_warnings)
            weights, allocation_warnings = _enforce_asset_class_ranges(weights, assets, policy)
            warnings.extend(allocation_warnings)
            weights, cap_warnings = _enforce_max_weight(weights, policy.max_single_asset_weight / 100.0)
            warnings.extend(cap_warnings)
            expected_metrics = {"status": "unavailable", "reason": "optimization_failed"}
            risk_metrics = {"status": "unavailable", "reason": "optimization_failed"}
    else:
        weights, fallback_warnings = _template_fallback_weights(assets, policy)
        warnings.extend(fallback_warnings)
        weights, allocation_warnings = _enforce_asset_class_ranges(weights, assets, policy)
        warnings.extend(allocation_warnings)
        weights, cap_warnings = _enforce_max_weight(weights, policy.max_single_asset_weight / 100.0)
        warnings.extend(cap_warnings)
        expected_metrics = {"status": "unavailable", "reason": "price_data_unavailable"}
        risk_metrics = {"status": "unavailable", "reason": "price_data_unavailable"}
        data_quality.price_data_available = False
        data_quality.unavailable_reason = "price_data_unavailable"

    weights_list = _weights_to_lines(weights, assets)
    check = check_constraints(
        weights_list,
        policy,
        universe_metadata={asset.ticker: asset.__dict__ for asset in assets},
        missing_assets=missing_assets,
    )
    weights_list = apply_constraint_status(weights_list, check)
    backtest = run_backtest(weights, price_data, policy.benchmark) if returns_by_asset else {"status": "unavailable", "reason": "price_data_unavailable", "equity_curve": []}
    data_quality.backtest_available = backtest.get("status") == "available"
    data_quality.warnings = list(dict.fromkeys(warnings))
    status = "generated"
    if check.status == "fail" or missing_assets:
        status = "partial"
    if not weights_list:
        status = "failed"
    recommendation = PortfolioRecommendation(
        recommendation_id=new_id("rec"),
        policy_id=policy.policy_id,
        created_at=now_iso(),
        method=policy.optimization_method,
        universe_id=policy.universe_id,
        weights=weights_list,
        expected_metrics=expected_metrics,
        backtest_metrics=backtest,
        risk_metrics=risk_metrics,
        constraint_check=check,
        ai_explanation="",
        status=status,
        data_quality=data_quality,
        audit={
            **recommendation_audit(policy, data_quality),
            "full_universe_hash": ticker_universe_hash([asset.ticker for asset in assets]),
            "price_data_latest_dates": {
                ticker: rows[-1].get("date") for ticker, rows in price_data.items() if rows
            },
        },
    )
    return recommendation, list(dict.fromkeys(warnings))
