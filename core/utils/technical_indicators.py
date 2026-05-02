from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable

_TECH_PREFIX = "TECH_METRICS_JSON:"


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


def _fmt_number(value: float | None, digits: int = 2) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def _date_from_index(index_value: Any) -> str:
    try:
        if hasattr(index_value, "to_pydatetime"):
            return index_value.to_pydatetime().date().isoformat()
        if hasattr(index_value, "date"):
            return index_value.date().isoformat()
    except Exception:
        pass
    text = str(index_value or "").strip()
    return text[:10] if len(text) >= 10 else datetime.now(timezone.utc).date().isoformat()


def freshness_status(as_of: str | None) -> str:
    text = str(as_of or "").strip()
    if not text or text == "unknown":
        return "unknown"
    try:
        parsed = datetime.fromisoformat(text[:10]).date()
    except Exception:
        return "unknown"
    age_days = (datetime.now(timezone.utc).date() - parsed).days
    if age_days <= 7:
        return "fresh"
    if age_days <= 45:
        return "recent"
    return "stale"


def _metric(
    name: str,
    value: str,
    *,
    unit: str,
    as_of: str,
    context: str,
    source: str = "yfinance:technical",
    evidence_doc_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "as_of": as_of or "unknown",
        "context": context,
        "source": source,
        "freshness_status": freshness_status(as_of),
        "evidence_doc_ids": [str(x) for x in (evidence_doc_ids or []) if str(x).strip()],
    }


def _localize_technical_metrics(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize deterministic technical metrics to Korean labels/context."""

    for metric in metrics:
        name = str(metric.get("name") or "")
        if " latest close" in name:
            metric["name"] = name.replace(" latest close", " 최신 종가")
            metric["context"] = "기술지표 계산의 기준 가격입니다."
        elif " 1M price momentum" in name:
            metric["name"] = name.replace(" 1M price momentum", " 1개월 가격 모멘텀")
            metric["context"] = "최근 20거래일 가격 모멘텀입니다."
        elif " 3M price momentum" in name:
            metric["name"] = name.replace(" 3M price momentum", " 3개월 가격 모멘텀")
            metric["context"] = "최근 60거래일 가격 모멘텀입니다."
        elif " price vs SMA" in name:
            metric["name"] = name.replace(" price vs SMA", " SMA") + " 대비 가격 괴리"
            window = re.search(r"SMA(\d+)", str(metric["name"]))
            metric["context"] = f"{window.group(0) if window else 'SMA'} 대비 가격 괴리율입니다."
        elif " RSI(14)" in name:
            metric["context"] = "70 이상은 과열, 30 이하는 침체권으로 해석하는 모멘텀 지표입니다."
        elif " MACD histogram" in name:
            metric["name"] = name.replace(" MACD histogram", " MACD 히스토그램")
            metric["context"] = "MACD와 시그널선의 차이를 보여주는 단기 모멘텀 지표입니다."
        elif " 20D realized volatility" in name:
            metric["name"] = name.replace(" 20D realized volatility", " 20일 실현 변동성")
            metric["context"] = "최근 20거래일 일간 수익률의 연율화 변동성입니다."
        elif " volume vs 20D average" in name:
            metric["name"] = name.replace(" volume vs 20D average", " 20일 평균 대비 거래량")
            metric["context"] = "최근 거래량이 20일 평균 대비 얼마나 강한지 보여줍니다."
    return metrics


def _close_series(history: Any):
    if history is None or getattr(history, "empty", True):
        return None
    if "Close" in history:
        close = history["Close"].dropna()
    elif "Adj Close" in history:
        close = history["Adj Close"].dropna()
    else:
        return None
    return close if len(close) else None


def _volume_series(history: Any):
    if history is None or getattr(history, "empty", True) or "Volume" not in history:
        return None
    volume = history["Volume"].dropna()
    return volume if len(volume) else None


def _rsi(close: Any, window: int = 14) -> float | None:
    if close is None or len(close) < window + 1:
        return None
    delta = close.diff().dropna()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.rolling(window=window).mean().iloc[-1]
    avg_loss = losses.rolling(window=window).mean().iloc[-1]
    avg_gain = _safe_float(avg_gain)
    avg_loss = _safe_float(avg_loss)
    if avg_gain is None or avg_loss is None:
        return None
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(close: Any) -> tuple[float | None, float | None, float | None]:
    if close is None or len(close) < 35:
        return None, None, None
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return _safe_float(macd.iloc[-1]), _safe_float(signal.iloc[-1]), _safe_float(hist.iloc[-1])


def _window_return(close: Any, window: int) -> float | None:
    if close is None or len(close) <= window:
        return None
    last = _safe_float(close.iloc[-1])
    prior = _safe_float(close.iloc[-window - 1])
    if last is None or prior in (None, 0):
        return None
    return (last / prior - 1.0) * 100.0


def _sma_distance(close: Any, window: int) -> tuple[float | None, float | None]:
    if close is None or len(close) < window:
        return None, None
    last = _safe_float(close.iloc[-1])
    sma = _safe_float(close.rolling(window=window).mean().iloc[-1])
    if last is None or sma in (None, 0):
        return sma, None
    return sma, (last / sma - 1.0) * 100.0


def compute_technical_metrics_from_history(
    history: Any,
    ticker: str,
    *,
    evidence_doc_ids: Iterable[str] | None = None,
    source: str = "yfinance:technical",
) -> list[dict[str, Any]]:
    """Compute reproducible technical indicators from OHLCV history.

    The function intentionally returns schema-compatible metric dictionaries
    rather than prose so downstream reports can show value, unit, 기준일,
    source, and evidence consistently.
    """

    close = _close_series(history)
    if close is None or len(close) < 20:
        return []
    volume = _volume_series(history)
    as_of = _date_from_index(close.index[-1])
    last = _safe_float(close.iloc[-1])
    if last is None:
        return []

    metrics = [
        _metric(
            f"{ticker.upper()} latest close",
            _fmt_number(last),
            unit="price",
            as_of=as_of,
            context="기술지표 계산의 기준 가격입니다.",
            source=source,
            evidence_doc_ids=evidence_doc_ids,
        )
    ]

    for window, label in ((20, "1M"), (60, "3M")):
        ret = _window_return(close, window)
        if ret is not None:
            metrics.append(
                _metric(
                    f"{ticker.upper()} {label} price momentum",
                    _fmt_pct(ret),
                    unit="%",
                    as_of=as_of,
                    context=f"최근 {window}거래일 가격 모멘텀입니다.",
                    source=source,
                    evidence_doc_ids=evidence_doc_ids,
                )
            )

    for window in (20, 50, 200):
        sma, distance = _sma_distance(close, window)
        if sma is None or distance is None:
            continue
        metrics.append(
            _metric(
                f"{ticker.upper()} price vs SMA{window}",
                _fmt_pct(distance),
                unit="%",
                as_of=as_of,
                context=f"SMA{window} {_fmt_number(sma)} 대비 가격 괴리율입니다.",
                source=source,
                evidence_doc_ids=evidence_doc_ids,
            )
        )

    rsi = _rsi(close, 14)
    if rsi is not None:
        metrics.append(
            _metric(
                f"{ticker.upper()} RSI(14)",
                _fmt_number(rsi, 1),
                unit="index",
                as_of=as_of,
                context="70 이상은 과열, 30 이하는 침체권으로 해석합니다.",
                source=source,
                evidence_doc_ids=evidence_doc_ids,
            )
        )

    macd, signal, hist = _macd(close)
    if hist is not None:
        context = f"MACD {_fmt_number(macd)} / Signal {_fmt_number(signal)} 기준 히스토그램입니다."
        metrics.append(
            _metric(
                f"{ticker.upper()} MACD histogram",
                _fmt_number(hist, 3),
                unit="price",
                as_of=as_of,
                context=context,
                source=source,
                evidence_doc_ids=evidence_doc_ids,
            )
        )

    returns = close.pct_change().dropna()
    if len(returns) >= 20:
        vol = _safe_float(returns.tail(20).std())
        if vol is not None:
            metrics.append(
                _metric(
                    f"{ticker.upper()} 20D realized volatility",
                    _fmt_pct(vol * math.sqrt(252.0) * 100.0),
                    unit="%",
                    as_of=as_of,
                    context="최근 20거래일 일간 수익률의 연율화 변동성입니다.",
                    source=source,
                    evidence_doc_ids=evidence_doc_ids,
                )
            )

    if volume is not None and len(volume) >= 20:
        latest_volume = _safe_float(volume.iloc[-1])
        avg_volume = _safe_float(volume.tail(20).mean())
        if latest_volume is not None and avg_volume not in (None, 0):
            metrics.append(
                _metric(
                    f"{ticker.upper()} volume vs 20D average",
                    f"{latest_volume / avg_volume:.2f}x",
                    unit="x",
                    as_of=as_of,
                    context="최근 거래량이 20일 평균 대비 얼마나 강한지 보여줍니다.",
                    source=source,
                    evidence_doc_ids=evidence_doc_ids,
                )
            )

    return _localize_technical_metrics(metrics)


def fetch_yfinance_history(ticker: str, lookback_days: int = 365) -> Any:
    import yfinance as yf

    days = max(int(lookback_days or 365), 260)
    period = "2y" if days > 370 else "1y"
    return yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)


def technical_metrics_document_text(ticker: str, metrics: list[dict[str, Any]]) -> str:
    as_of = next((str(item.get("as_of")) for item in metrics if item.get("as_of")), "unknown")
    compact = [
        {
            "name": item.get("name"),
            "value": item.get("value"),
            "unit": item.get("unit", ""),
            "as_of": item.get("as_of") or as_of,
            "context": item.get("context", ""),
            "source": item.get("source", "yfinance:technical"),
            "freshness_status": item.get("freshness_status", "unknown"),
            "evidence_doc_ids": item.get("evidence_doc_ids", []),
        }
        for item in metrics
        if item.get("name") and item.get("value")
    ]
    metric_line = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    human = "\n".join(
        f"- {item['name']}: {item['value']} {item.get('unit', '')} as of {item.get('as_of', as_of)}"
        for item in compact[:8]
    )
    return (
        f"Technical indicator snapshot for {ticker.upper()} as of {as_of} from yfinance daily prices.\n"
        f"{_TECH_PREFIX} {metric_line}\n\n"
        f"{human}\n\n"
        "Use these figures as deterministic technical anchors. Do not invent additional technical numbers."
    )


def parse_technical_metrics_from_text(text: str, *, doc_id: str | None = None) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for line in str(text or "").splitlines():
        if not line.strip().startswith(_TECH_PREFIX):
            continue
        payload = line.split(_TECH_PREFIX, 1)[1].strip()
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            value = str(item.get("value") or "").strip()
            if not name or not value:
                continue
            ids = [str(x) for x in (item.get("evidence_doc_ids") or []) if str(x).strip()]
            if doc_id and doc_id not in ids:
                ids.append(doc_id)
            as_of = str(item.get("as_of") or "unknown").strip() or "unknown"
            metrics.append(
                {
                    "name": name,
                    "value": value,
                    "unit": str(item.get("unit") or "").strip(),
                    "as_of": as_of,
                    "context": str(item.get("context") or "").strip(),
                    "source": str(item.get("source") or "yfinance:technical").strip(),
                    "freshness_status": str(item.get("freshness_status") or freshness_status(as_of)).strip(),
                    "evidence_doc_ids": ids,
                }
            )
    return _localize_technical_metrics(metrics)


def technical_metrics_from_retrieval_items(items: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        metadata = getattr(item, "metadata", None) or {}
        doc_id = str(metadata.get("parent_doc_id") or metadata.get("doc_id") or "").strip()
        for metric in parse_technical_metrics_from_text(getattr(item, "chunk", ""), doc_id=doc_id or None):
            key = f"{metric['name'].lower()}|{metric['as_of']}|{metric['value']}"
            if key in seen:
                continue
            seen.add(key)
            out.append(metric)
    return out
