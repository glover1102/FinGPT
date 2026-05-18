from __future__ import annotations

import re
from typing import Any


_TOPIC_MODES = {"sector_macro", "concept"}
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_IDEOGRAPH_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_MOJIBAKE_RE = re.compile(r"(?:\ufffd|\u00c3|\u00c2|\u5360|\uf9cd|\u5ae8|\u6e72|\u8af8|\?\uc392|\?\uc895|\?\ubfa4|\?\uba84)")
_PARENTHETICAL_RE = re.compile(r"\([^()]{8,280}\)")
_BRACKETED_CITATION_RE = re.compile(r"\[[^\[\]]{8,280}\]")
_NON_WORD_RE = re.compile(r"[^\w\uac00-\ud7a3]+")
_WARNING_HINTS = (
    "insufficient",
    "thin evidence",
    "low-context",
    "low context",
    "no topic context",
    "freshly collected documents",
    "warning",
    "partial",
    "uncertain",
    "uncertainty",
    "not enough context",
    "\uadfc\uac70",
    "\uc99d\uac70",
    "\ubd80\uc871",
    "\ubd88\ud655\uc2e4",
    "\ub204\ub77d",
    "\ubb38\uc11c",
    "\uc77c\ubd80",
)

DEFAULT_TOPIC_MINIMUMS = {
    "decision_sections": 3,
    "scenario_analysis": 2,
    "execution_strategy": 1,
    "key_drivers": 2,
    "key_risks": 2,
    "key_metrics": 1,
}

FAST_TOPIC_MINIMUMS = {
    "decision_sections": 3,
    "scenario_analysis": 2,
    "execution_strategy": 1,
    "key_drivers": 2,
    "key_risks": 2,
    "key_metrics": 2,
}

_ALL_EVIDENCE_BUCKETS = ("macro", "asset_specific", "market_structure", "latest_catalyst")
_REQUIRED_EVIDENCE_BUCKETS_BY_ASSET_CLASS = {
    "rates_bonds": {"macro", "market_structure"},
    "credit": {"macro", "market_structure"},
    "equity_index": {"macro", "asset_specific", "market_structure"},
    "fx": {"macro", "asset_specific", "market_structure"},
    "commodity": {"macro", "asset_specific", "market_structure", "latest_catalyst"},
    "crypto": {"macro", "asset_specific", "market_structure", "latest_catalyst"},
    "sector_theme": {"macro", "asset_specific", "market_structure", "latest_catalyst"},
}

def as_payload_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return payload
    raise TypeError(f"Unsupported payload type: {type(payload)!r}")


def detect_mode(payload: Any) -> str:
    data = as_payload_dict(payload)
    mode = str(data.get("mode") or "").strip()
    if mode in _TOPIC_MODES:
        return mode
    if isinstance(data.get("results"), dict):
        return "multi_ticker"
    topic_fields = (
        "asset_overview",
        "macro_regime",
        "rate_structure",
        "scenario_analysis",
        "investment_judgment",
        "execution_strategy",
    )
    if "core_thesis" in data and ("theme" in data or any(field in data for field in topic_fields)):
        return "concept"
    return "single_ticker"


def collect_descriptive_texts(payload: Any) -> list[str]:
    data = as_payload_dict(payload)
    mode = detect_mode(data)
    texts: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                texts.append(cleaned)

    def add_list(values: Any) -> None:
        if not isinstance(values, list):
            return
        for value in values:
            if isinstance(value, str):
                add(value)
            elif isinstance(value, dict):
                for field in (
                    "title",
                    "conclusion",
                    "text",
                    "scenario",
                    "probability",
                    "expected_outcome",
                    "asset_implication",
                    "decision_read",
                    "strategy",
                    "trigger",
                    "rationale",
                    "risk_control",
                    "context",
                    "name",
                    "value",
                ):
                    add(value.get(field))
                bullets = value.get("bullets")
                if isinstance(bullets, list):
                    for bullet in bullets:
                        add(bullet)

    if mode == "single_ticker":
        for field in ("summary", "conclusion", "uncertainty", "error_metadata"):
            add(data.get(field))
        for field in ("bull_points", "bear_points", "open_questions"):
            add_list(data.get(field))
        return texts

    if mode in _TOPIC_MODES:
        for field in ("executive_summary", "core_thesis", "uncertainty", "error_metadata"):
            add(data.get(field))
        for field in (
            "asset_overview",
            "macro_regime",
            "rate_structure",
            "investment_judgment",
            "scenario_analysis",
            "execution_strategy",
            "key_drivers",
            "key_risks",
            "open_questions",
        ):
            add_list(data.get(field))
        return texts

    if mode == "multi_ticker":
        results = data.get("results") or {}
        if isinstance(results, dict):
            for item in results.values():
                texts.extend(collect_descriptive_texts(item))
    return texts


def is_korean_dominant(text: str) -> bool:
    text = str(text or "")
    hangul = len(_HANGUL_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    cjk = len(_CJK_IDEOGRAPH_RE.findall(text))
    mojibake = len(_MOJIBAKE_RE.findall(text))
    if mojibake >= 3:
        return False
    if cjk >= max(8, hangul):
        return False
    if hangul == 0:
        return False
    if latin == 0:
        return True
    return hangul >= max(8, int(latin * 1.1))


def _strip_reference_parentheticals(text: str) -> str:
    """Remove English-heavy citation titles before language dominance checks.

    Research text often appends source titles such as "(FRED DGS30: Market
    Yield ...)" or "[JPMorgan Chase Stock ...]" after an otherwise Korean
    claim. Those titles are valid traceability metadata, not answer-language
    violations.
    """

    def replace(match: re.Match[str]) -> str:
        fragment = match.group(0)
        hangul = len(_HANGUL_RE.findall(fragment))
        latin = len(_LATIN_RE.findall(fragment))
        if latin >= 12 and hangul <= max(2, latin // 4):
            return " "
        return fragment

    cleaned = _PARENTHETICAL_RE.sub(replace, str(text or ""))
    return _BRACKETED_CITATION_RE.sub(replace, cleaned)


def language_ok(payload: Any, preferred_language: str = "ko") -> bool:
    if preferred_language != "ko":
        return True
    texts = collect_descriptive_texts(payload)
    if not texts:
        return False
    return is_korean_dominant(_strip_reference_parentheticals(" ".join(texts)))


def duplicate_paragraph_ratio(payload: Any, *, min_chars: int = 18) -> dict[str, Any]:
    """Measure repeated descriptive lines/paragraphs in a response.

    This deliberately ignores very short labels and citation fragments. The
    goal is to catch memo-level repetition such as the same summary sentence
    appearing in Summary, Conclusion, and Report.
    """

    data = as_payload_dict(payload)
    mode = detect_mode(data)
    texts: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                texts.append(cleaned)

    def add_list(values: Any) -> None:
        if not isinstance(values, list):
            return
        for value in values:
            if isinstance(value, str):
                add(value)
            elif isinstance(value, dict):
                for field in (
                    "title",
                    "conclusion",
                    "text",
                    "scenario",
                    "probability",
                    "expected_outcome",
                    "asset_implication",
                    "decision_read",
                    "strategy",
                    "trigger",
                    "rationale",
                    "risk_control",
                    "context",
                ):
                    add(value.get(field))
                bullets = value.get("bullets")
                if isinstance(bullets, list):
                    for bullet in bullets:
                        add(bullet)

    if mode == "single_ticker":
        for field in ("summary", "conclusion", "uncertainty", "error_metadata"):
            add(data.get(field))
        for field in ("bull_points", "bear_points", "open_questions"):
            add_list(data.get(field))
    elif mode in _TOPIC_MODES:
        for field in ("executive_summary", "core_thesis", "uncertainty", "error_metadata"):
            add(data.get(field))
        for field in (
            "asset_overview",
            "macro_regime",
            "rate_structure",
            "investment_judgment",
            "scenario_analysis",
            "execution_strategy",
            "key_drivers",
            "key_risks",
            "open_questions",
        ):
            add_list(data.get(field))
    else:
        texts = collect_descriptive_texts(data)

    fragments: list[str] = []
    for text in texts:
        for part in re.split(r"(?:\n\s*){2,}|[•\-]\s+", str(text or "")):
            cleaned = " ".join(str(part or "").split())
            if len(cleaned) >= min_chars:
                fragments.append(cleaned)

    normalized: list[str] = []
    for fragment in fragments:
        key = _NON_WORD_RE.sub(" ", fragment.lower()).strip()
        key = " ".join(key.split())
        if len(key) >= min_chars:
            normalized.append(key)

    total = len(normalized)
    if total == 0:
        return {"ok": True, "total": 0, "duplicates": 0, "ratio": 0.0, "examples": []}

    seen: set[str] = set()
    duplicates: list[str] = []
    examples: list[str] = []
    for key, original in zip(normalized, fragments):
        if key in seen:
            duplicates.append(key)
            if len(examples) < 5:
                examples.append(original[:180])
        else:
            seen.add(key)

    ratio = len(duplicates) / total
    return {
        "ok": ratio <= 0.25,
        "total": total,
        "duplicates": len(duplicates),
        "ratio": round(ratio, 4),
        "examples": examples,
    }


def citation_count(payload: Any) -> int:
    data = as_payload_dict(payload)
    citations = data.get("citations") or []
    if not isinstance(citations, list):
        return 0
    return len([item for item in citations if item])


def evidence_count(payload: Any) -> int:
    data = as_payload_dict(payload)
    context = data.get("raw_context") or []
    if not isinstance(context, list):
        return 0
    return len(context)


def evidence_bucket_policy(
    asset_class: str | None,
    bucket_counts: dict[str, Any] | None,
    *,
    reported_missing: list[str] | None = None,
    substituted_buckets: list[str] | None = None,
) -> dict[str, list[str]]:
    """Separate blocking evidence gaps from warning-only gaps.

    The topic pipeline uses the same four evidence buckets for every asset
    class, but not every bucket should block every asset. For rates/bonds and
    FX, a missing latest-news catalyst is often acceptable if macro, asset, and
    market-structure evidence exist.
    """

    normalized = str(asset_class or "sector_theme").strip() or "sector_theme"
    required = _REQUIRED_EVIDENCE_BUCKETS_BY_ASSET_CLASS.get(
        normalized,
        _REQUIRED_EVIDENCE_BUCKETS_BY_ASSET_CLASS["sector_theme"],
    )
    counts = bucket_counts or {}
    explicit_missing = {str(item) for item in (reported_missing or []) if str(item).strip()}
    substituted = {str(item) for item in (substituted_buckets or []) if str(item).strip()}
    def bucket_count(bucket: str) -> int:
        try:
            return int(counts.get(bucket, 0) or 0)
        except (TypeError, ValueError):
            return 0

    missing = {bucket for bucket in _ALL_EVIDENCE_BUCKETS if bucket_count(bucket) <= 0}
    missing.update(explicit_missing)
    missing.difference_update(substituted)
    blocking = sorted(bucket for bucket in missing if bucket in required)
    warning = sorted(bucket for bucket in missing if bucket not in required)
    return {"blocking_missing": blocking, "warning_missing": warning}


def _doc_date_lookup(data: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    context = data.get("raw_context") or []
    if not isinstance(context, list):
        return lookup
    for item in context:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        date = str(item.get("date") or item.get("published_at") or metadata.get("published_at") or "").strip()
        ids = [
            item.get("doc_id"),
            item.get("id"),
            metadata.get("doc_id"),
            metadata.get("parent_doc_id"),
        ]
        for doc_id in ids:
            key = str(doc_id or "").strip()
            if key and date and key not in lookup:
                lookup[key] = date
    citations = data.get("citations") or []
    if isinstance(citations, list):
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            doc_id = str(citation.get("doc_id") or "").strip()
            date = str(citation.get("date") or "").strip()
            if doc_id and date and doc_id not in lookup:
                lookup[doc_id] = date
    return lookup


def _valid_doc_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        values = [values]
    invalid = {"", "unknown", "none", "null", "n/a", "na"}
    return [
        str(doc_id).strip()
        for doc_id in values
        if str(doc_id or "").strip().lower() not in invalid
    ]


def metric_as_of_coverage(payload: Any) -> dict[str, Any]:
    data = as_payload_dict(payload)
    lookup = _doc_date_lookup(data)
    metrics = data.get("key_metrics") or []
    if not isinstance(metrics, list):
        metrics = []
    total = 0
    covered = 0
    missing: list[str] = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        total += 1
        as_of = str(metric.get("as_of") or "").strip()
        name = str(metric.get("name") or f"metric_{total}").strip()
        evidence_ids = _valid_doc_ids(metric.get("evidence_doc_ids") or [])
        if as_of or any(doc_id in lookup for doc_id in evidence_ids):
            covered += 1
        else:
            missing.append(name)
    coverage = 1.0 if total == 0 else covered / total
    return {"ok": coverage >= 1.0, "total": total, "covered": covered, "coverage": coverage, "missing": missing}


def _claim_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    if detect_mode(data) == "single_ticker":
        for field, evidence_field in (("bull_points", "bull_evidence_ids"), ("bear_points", "bear_evidence_ids")):
            points = data.get(field) or []
            evidence = data.get(evidence_field) or []
            if not isinstance(points, list):
                continue
            for idx, point in enumerate(points):
                ids = evidence[idx] if isinstance(evidence, list) and idx < len(evidence) else []
                valid_ids = _valid_doc_ids(ids)
                if valid_ids:
                    claims.append({"field": field, "text": point, "evidence_doc_ids": valid_ids})
        return claims

    for field in (
        "asset_overview",
        "macro_regime",
        "rate_structure",
        "investment_judgment",
        "scenario_analysis",
        "execution_strategy",
        "key_drivers",
        "key_risks",
    ):
        values = data.get(field) or []
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and item.get("evidence_doc_ids"):
                valid_ids = _valid_doc_ids(item.get("evidence_doc_ids"))
                if valid_ids:
                    claims.append({"field": field, "text": item.get("text") or item.get("title") or item.get("scenario") or item.get("strategy"), "evidence_doc_ids": valid_ids})
    return claims


def claim_evidence_date_coverage(payload: Any) -> dict[str, Any]:
    data = as_payload_dict(payload)
    lookup = _doc_date_lookup(data)
    claims = _claim_items(data)
    total = 0
    covered = 0
    missing: list[str] = []
    for claim in claims:
        ids = [str(doc_id) for doc_id in (claim.get("evidence_doc_ids") or []) if str(doc_id).strip()]
        if not ids:
            continue
        total += 1
        if any(doc_id in lookup for doc_id in ids):
            covered += 1
        else:
            missing.append(str(claim.get("field") or "claim"))
    coverage = 1.0 if total == 0 else covered / total
    return {"ok": coverage >= 1.0, "total": total, "covered": covered, "coverage": coverage, "missing": missing}


def quant_snapshot_present(payload: Any) -> bool:
    data = as_payload_dict(payload)
    extras = (data.get("execution_meta") or {}).get("extras") or {}
    if not isinstance(extras, dict):
        return False
    snapshot = extras.get("quant_snapshot") or {}
    if not isinstance(snapshot, dict):
        return False
    return bool(snapshot.get("metrics") or snapshot.get("duration_or_proxy") or snapshot.get("rate_shock_scenarios"))


def topic_bucket_coverage(payload: Any) -> dict[str, Any]:
    data = as_payload_dict(payload)
    extras = (data.get("execution_meta") or {}).get("extras") or {}
    if not isinstance(extras, dict):
        extras = {}
    counts = extras.get("evidence_bucket_counts") or {}
    substituted = [str(x) for x in (extras.get("substituted_buckets") or []) if str(x).strip()]
    blocking = [str(x) for x in (extras.get("blocking_missing_buckets") or extras.get("blocking_evidence_buckets") or extras.get("missing_evidence_buckets") or []) if str(x).strip()]
    warning = [str(x) for x in (extras.get("warning_missing_buckets") or extras.get("warning_evidence_buckets") or []) if str(x).strip()]
    present = []
    if isinstance(counts, dict):
        present = []
        for bucket in _ALL_EVIDENCE_BUCKETS:
            try:
                count = int(counts.get(bucket, 0) or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0 or bucket in substituted:
                present.append(bucket)
    return {"counts": counts, "present": present, "substituted": substituted, "blocking_missing": blocking, "warning_missing": warning}


def has_warning_only_partial(payload: Any) -> bool:
    data = as_payload_dict(payload)
    if str(data.get("status") or "").lower() != "partial":
        return False
    haystack = " ".join(
        str(data.get(field) or "")
        for field in ("error_metadata", "uncertainty", "summary", "executive_summary")
    ).lower()
    return any(marker in haystack for marker in _WARNING_HINTS)


def partial_reason_is_actionable(payload: Any) -> bool:
    data = as_payload_dict(payload)
    if str(data.get("status") or "").lower() != "partial":
        return True
    extras = (data.get("execution_meta") or {}).get("extras") or {}
    if not isinstance(extras, dict):
        extras = {}
    haystack = " ".join(
        [
            str(data.get("error_metadata") or ""),
            str(data.get("uncertainty") or ""),
            str(extras.get("missing_evidence_reasons") or ""),
            str(extras.get("blocking_evidence_buckets") or ""),
            str(extras.get("warning_evidence_buckets") or ""),
            str(extras.get("error_type") or ""),
        ]
    ).lower()
    hints = (
        "bucket",
        "source",
        "fred",
        "fmp",
        "entitlement",
        "missing",
        "evidence",
        "data",
        "provider",
        "근거",
        "증거",
        "버킷",
        "부족",
        "누락",
        "확인",
        "불확실",
    )
    return bool(haystack.strip()) and any(hint in haystack for hint in hints)


def decision_richness(payload: Any) -> dict[str, Any]:
    data = as_payload_dict(payload)
    mode = detect_mode(data)

    if mode == "single_ticker":
        summary_ok = bool(str(data.get("summary") or "").strip())
        conclusion_ok = bool(str(data.get("conclusion") or "").strip())
        bull_count = len([item for item in (data.get("bull_points") or []) if str(item).strip()])
        bear_count = len([item for item in (data.get("bear_points") or []) if str(item).strip()])
        return {
            "profile": "analysis",
            "ok": summary_ok and conclusion_ok and bull_count >= 2 and bear_count >= 2,
            "checks": {
                "summary": summary_ok,
                "conclusion": conclusion_ok,
                "bull_points": bull_count,
                "bear_points": bear_count,
            },
        }

    if mode in _TOPIC_MODES:
        section_count = sum(
            len(data.get(field) or [])
            for field in ("asset_overview", "macro_regime", "rate_structure", "investment_judgment")
        )
        scenario_count = len(data.get("scenario_analysis") or [])
        execution_count = len(data.get("execution_strategy") or [])
        driver_count = len(data.get("key_drivers") or [])
        risk_count = len(data.get("key_risks") or [])
        return {
            "profile": "topic",
            "ok": (
                section_count >= 3
                and scenario_count >= 2
                and execution_count >= 1
                and driver_count >= 2
                and risk_count >= 2
            ),
            "checks": {
                "decision_sections": section_count,
                "scenario_analysis": scenario_count,
                "execution_strategy": execution_count,
                "key_drivers": driver_count,
                "key_risks": risk_count,
            },
        }

    return {"profile": mode, "ok": False, "checks": {}}


def topic_completeness(
    payload: Any,
    minimums: dict[str, int] | None = None,
) -> dict[str, Any]:
    data = as_payload_dict(payload)
    counts = {
        "asset_overview": len(data.get("asset_overview") or []),
        "macro_regime": len(data.get("macro_regime") or []),
        "rate_structure": len(data.get("rate_structure") or []),
        "investment_judgment": len(data.get("investment_judgment") or []),
        "scenario_analysis": len(data.get("scenario_analysis") or []),
        "execution_strategy": len(data.get("execution_strategy") or []),
        "key_drivers": len(data.get("key_drivers") or []),
        "key_risks": len(data.get("key_risks") or []),
        "key_metrics": len(data.get("key_metrics") or []),
    }
    required = dict(DEFAULT_TOPIC_MINIMUMS)
    if minimums:
        required.update({key: int(value) for key, value in minimums.items()})
    derived = {
        "decision_sections": (
            counts["asset_overview"]
            + counts["macro_regime"]
            + counts["rate_structure"]
            + counts["investment_judgment"]
        ),
        "scenario_analysis": counts["scenario_analysis"],
        "execution_strategy": counts["execution_strategy"],
        "key_drivers": counts["key_drivers"],
        "key_risks": counts["key_risks"],
        "key_metrics": counts["key_metrics"],
    }
    missing = {key: max(0, required[key] - derived.get(key, 0)) for key in required}
    return {
        "ok": all(value == 0 for value in missing.values()),
        "counts": {**counts, **derived},
        "minimums": required,
        "missing": missing,
    }


def topic_gate(
    payload: Any,
    *,
    minimums: dict[str, int] | None = None,
    min_citations: int = 1,
    preferred_language: str = "ko",
    require_asset_overview: bool = True,
    min_macro_market_judgment: int = 2,
) -> dict[str, Any]:
    data = as_payload_dict(payload)
    completeness = topic_completeness(data, minimums)
    citations = citation_count(data)
    uncertainty = bool(str(data.get("uncertainty") or "").strip())
    asset_overview_ok = len(data.get("asset_overview") or []) >= (1 if require_asset_overview else 0)
    macro_market_judgment = (
        len(data.get("macro_regime") or [])
        + len(data.get("rate_structure") or [])
        + len(data.get("investment_judgment") or [])
    )
    language = language_ok(data, preferred_language=preferred_language)
    cited_doc_ids = data.get("cited_doc_ids") or []
    cited_doc_count = len(cited_doc_ids) if isinstance(cited_doc_ids, list) else 0
    evidence_ok = citations >= int(min_citations) or cited_doc_count >= int(min_citations) or uncertainty
    ok = bool(
        completeness["ok"]
        and language
        and evidence_ok
        and asset_overview_ok
        and macro_market_judgment >= int(min_macro_market_judgment)
    )
    return {
        "ok": ok,
        "language_ok": language,
        "citation_count": citations,
        "uncertainty_ok": uncertainty,
        "asset_overview_ok": asset_overview_ok,
        "macro_market_judgment": macro_market_judgment,
        "completeness": completeness,
    }


def topic_fast_gate(payload: Any, preferred_language: str = "ko") -> dict[str, Any]:
    return topic_gate(
        payload,
        minimums=FAST_TOPIC_MINIMUMS,
        min_citations=1,
        preferred_language=preferred_language,
        require_asset_overview=True,
        min_macro_market_judgment=2,
    )


def topic_final_gate(
    payload: Any,
    *,
    minimums: dict[str, int] | None = None,
    preferred_language: str = "ko",
) -> dict[str, Any]:
    return topic_gate(
        payload,
        minimums=minimums,
        min_citations=1,
        preferred_language=preferred_language,
        require_asset_overview=True,
        min_macro_market_judgment=2,
    )


def decision_quality_metrics(payload: Any) -> dict[str, Any]:
    """Return decision-grade quality metrics from a response or compute safe fallbacks."""
    data = as_payload_dict(payload)
    existing = data.get("quality_metrics")
    if isinstance(existing, dict) and existing:
        return {
            "claim_support_rate": float(existing.get("claim_support_rate") or 0.0),
            "numeric_grounding_rate": float(existing.get("numeric_grounding_rate") or 0.0),
            "evidence_quality_average": float(existing.get("evidence_quality_average") or 0.0),
            "freshness_coverage": float(existing.get("freshness_coverage") or 0.0),
            "stale_context_rate": float(existing.get("stale_context_rate") or 0.0),
            "source_diversity": int(existing.get("source_diversity") or 0),
            "required_bucket_coverage": float(existing.get("required_bucket_coverage") or 0.0),
        }

    metrics = data.get("key_metrics") if isinstance(data.get("key_metrics"), list) else []
    grounded_metrics = 0
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        if metric.get("grounding_status") == "grounded" or metric.get("evidence_doc_ids") or metric.get("source"):
            grounded_metrics += 1
    numeric_rate = grounded_metrics / len(metrics) if metrics else 0.0

    evidence_quality = data.get("evidence_quality") if isinstance(data.get("evidence_quality"), dict) else {}
    quality_values = []
    source_types = set()
    fresh = 0
    for item in evidence_quality.values():
        if not isinstance(item, dict):
            continue
        quality_values.append(float(item.get("overall_score") or 0.0))
        source_type = item.get("source_type")
        if source_type:
            source_types.add(str(source_type))
        if float(item.get("freshness_score") or 0.0) >= 0.60:
            fresh += 1
    quality_avg = sum(quality_values) / len(quality_values) if quality_values else 0.0
    freshness = fresh / len(quality_values) if quality_values else 0.0

    supported = 0
    total = 0
    for ids_field in ("bull_evidence_ids", "bear_evidence_ids"):
        values = data.get(ids_field)
        if isinstance(values, list):
            for ids in values:
                total += 1
                if isinstance(ids, list) and ids:
                    supported += 1
    for field in ("key_drivers", "key_risks", "scenario_analysis", "execution_strategy"):
        values = data.get(field)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    total += 1
                    if item.get("evidence_doc_ids"):
                        supported += 1
    claim_rate = supported / total if total else 0.0

    extras = ((data.get("execution_meta") or {}).get("extras") or {}) if isinstance(data.get("execution_meta"), dict) else {}
    plan = extras.get("retrieval_plan") if isinstance(extras.get("retrieval_plan"), dict) else {}
    required = plan.get("required_evidence_buckets") if isinstance(plan, dict) else []
    bucket_counts = extras.get("bucket_counts") if isinstance(extras.get("bucket_counts"), dict) else {}
    bucket_coverage = 0.0
    if required:
        matched = sum(1 for bucket in required if bucket_counts.get(bucket))
        bucket_coverage = matched / len(required)

    return {
        "claim_support_rate": round(claim_rate, 4),
        "numeric_grounding_rate": round(numeric_rate, 4),
        "evidence_quality_average": round(quality_avg, 4),
        "freshness_coverage": round(freshness, 4),
        "stale_context_rate": round(1.0 - freshness, 4) if freshness else 0.0,
        "source_diversity": len(source_types),
        "required_bucket_coverage": round(bucket_coverage, 4),
    }

