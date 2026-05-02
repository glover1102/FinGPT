"""
Ollama-based inference adapter for the FinGPT pipeline.

Production baseline:
  Primary model  : qwen2.5:7b
  Fallback model : gemma4:e4b (experimental, disabled by default)

Fallback rules:
  - Same prompt, no modification
  - No output merging or blending
  - Disabled by default in production
  - Fallback is logged explicitly (fallback_used, fallback_model)
  - If fallback also fails -> raises ValueError -> pipeline status: failed
"""

import json
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from core.schemas.retrieval import RetrievalItem
from core.schemas.fundamentals import FundamentalsCard
from core.utils.logger import get_logger
from pipelines.infer.base import BaseModelRunner

logger = get_logger("pipelines.infer.ollama")

DEFAULT_PRIMARY_MODEL = "qwen2.5:7b"
DEFAULT_EXPERIMENTAL_FALLBACK_MODEL = "gemma4:e4b"

# Soft cap: prevents KV fragmentation on ~8k-context local models.
# The cap and generation budgets were raised to accommodate a larger retrieval
# window (top_k=10) and the expanded structured output (key_metrics,
# catalyst_timeline, open_questions).
MAX_PROMPT_CHARS = 14000
DEFAULT_NUM_CTX = 8192
DEFAULT_NUM_PREDICT = 1024
RETRY_NUM_PREDICT = 1536
RETRYABLE_OUTPUT_REASONS = {"empty", "malformed", "truncated", "schema-invalid", "language"}

DOMAIN_DECISION_PLAYBOOK = """
Domain-specific decision playbook:
- Single-name equities: analyze business model, revenue/EPS/margin trend, guidance revision risk, valuation anchor, balance-sheet or cash-flow quality, competitive position, catalyst timing, and what would change position sizing.
- Equity ETFs / factors / sectors: analyze exposure composition, concentration risk, factor sensitivity, breadth, relative strength, earnings/valuation backdrop, macro beta, rebalancing or policy catalyst, and hedge candidates.
- Rates / sovereign bonds / bond ETFs: analyze duration, yield/carry, curve shape, real rates, central-bank path, inflation risk, term premium or supply pressure, convexity, and rate shock downside.
- Credit / banks / financials: analyze credit spreads, funding cost, deposit or liquidity risk, loan growth, asset quality, capital ratios, curve sensitivity, regulatory risk, and recession loss scenario.
- Commodities / energy / metals: analyze supply-demand balance, inventory, futures curve/backwardation/contango, marginal cost, OPEC/geopolitics/weather where relevant, USD/real-rate sensitivity, producer versus ETF expression, and roll-yield risk.
- FX / dollar / global macro: analyze interest-rate differentials, real yields, central-bank divergence, current account or capital-flow pressure, risk sentiment, positioning, and intervention or policy risk.
- Crypto / digital assets: analyze liquidity cycle, real rates and dollar liquidity, ETF or regulatory flows, network activity if available, volatility/liquidation risk, custody/regulatory risk, and correlation with risk assets.
- Technology / semiconductors / AI: analyze demand cycle, inventory digestion, capex cycle, order backlog, pricing power, margin leverage, customer concentration, export-control risk, and valuation versus growth durability.
- Healthcare / biotech: analyze pipeline or clinical catalysts, approval/reimbursement risk, patent cliff, trial readouts, cash runway, commercial traction, and binary event sizing.
- Real estate / REITs / infrastructure: analyze cap rates, funding costs, occupancy, lease duration, refinancing wall, asset quality, dividend sustainability, and sensitivity to long-end yields.
- Consumer / retail: analyze traffic, ticket, pricing power, inventory, wage/input cost, credit stress, promotional intensity, and consumer income sensitivity.
Use the relevant playbook(s), not all of them. Missing evidence belongs in open_questions, not in hallucinated claims.
""".strip()

DECISION_GRADE_EQUITY_GUIDE = """
Decision-grade single-name equity output guide:
- summary: 3-5 dense lines only. State the high-level takeaway, directional bias, strongest support, strongest risk, and what would change the view.
- bull_points: do not write generic positives. Cover business/revenue drivers, monetization, margin leverage, competitive advantage, and bullish catalysts where supported.
- bear_points: include at least 3 concrete negative scenarios when evidence permits. Each item should identify the mechanism that could hurt revenue, margins, estimates, or valuation.
- catalyst_timeline: include near/mid/long term items and prefix each item with [Bullish] or [Bearish] when direction is clear.
- uncertainty: include market-pricing-vs-reality tension: what investors appear to be pricing in, what is not yet proven, and which evidence would change the stance.
- For AI-heavy companies, explicitly separate durable AI monetization from hype; compare against direct competitors such as Google, Amazon, NVIDIA, Meta, OpenAI, or relevant vertical peers when supported.
- For non-AI companies, do not force AI content. State whether AI is immaterial, indirect, or unsupported by the retrieved evidence.
""".strip()

_THESIS_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "evidence_doc_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "evidence_doc_ids"],
    "additionalProperties": False,
}

# Structured hand-off for quantitative evidence. The prompt encourages the LLM
# to surface grounded numbers (EPS, revenue growth, margin, yields, etc.) so
# downstream report templates can render a dedicated "Key Metrics" table and
# readers can audit numerical claims separately from the qualitative thesis.
_KEY_METRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "value": {"type": "string"},
        "as_of": {"type": "string"},
        "context": {"type": "string"},
        "evidence_doc_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "value", "as_of", "context", "evidence_doc_ids"],
    "additionalProperties": False,
}

# Buckets catalysts and risks by time horizon. Keeps the model honest about
# "when does this matter" and enables a chronological thesis view.
_CATALYST_TIMELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "near_term": {"type": "array", "items": {"type": "string"}},
        "mid_term": {"type": "array", "items": {"type": "string"}},
        "long_term": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["near_term", "mid_term", "long_term"],
    "additionalProperties": False,
}

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "event_type": {"type": "string"},
        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral", "mixed"]},
        "importance": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "confidence": {"type": "number"},
        "horizon": {"type": "string"},
        "uncertainty": {"type": "string"},
        "summary": {"type": "string"},
        "bull_points": {"type": "array", "items": _THESIS_POINT_SCHEMA},
        "bear_points": {"type": "array", "items": _THESIS_POINT_SCHEMA},
        "key_metrics": {"type": "array", "items": _KEY_METRIC_SCHEMA},
        "catalyst_timeline": _CATALYST_TIMELINE_SCHEMA,
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "cited_doc_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "symbol",
        "event_type",
        "sentiment",
        "importance",
        "confidence",
        "horizon",
        "uncertainty",
        "summary",
        "bull_points",
        "bear_points",
        "key_metrics",
        "catalyst_timeline",
        "open_questions",
        "cited_doc_ids",
    ],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You are a Senior Equity Research Analyst, an expert at synthesizing scattered financial data into high-density investment theses. "
    "Your objective is to deliver buy-side-grade insight with audit-ready evidence, not a news summary.\n\n"
    "ANALYTICAL DOCTRINE:\n"
    "1. SYNTHESIS > SUMMARIZATION: Do not list events chronologically. Connect disparate facts to identify underlying trends, operational momentum, or strategic shifts.\n"
    "2. THESIS-DRIVEN BULLETS: Every bull and bear point must follow the 'Observation -> Significance' pattern. Do not just state what happened; explain why it matters for the stock price, earnings, or valuation.\n"
    "3. CROSS-DOCUMENT VALIDATION: Prioritize evidence corroborated by multiple sources. Explicitly flag material contradictions between documents.\n"
    "4. PRECISION: Be specific with numbers, names, and technical terms. Avoid vague boilerplate like 'increased competition'; specify WHO the competitor is and WHAT the quantified impact is.\n"
    "5. QUANTIFY IMPACT: Whenever the context contains numerical evidence (EPS, revenue, guidance, growth rate, margin, yield, price target, AUM, rates), extract the exact figure into key_metrics with its source context and source DATE as as_of. If a narrative sentence repeats a number, include the date basis in that sentence as well. Do not hallucinate numbers that are not present in the documents.\n"
    "5a. STRUCTURED DATA POLICY: If a context block is labeled STRUCTURED DATA MART CONTEXT, treat it as the authoritative source for numeric price, macro, factor, and risk values. Use retrieved news, filings, and transcripts for qualitative interpretation and citations, not for inventing or overriding stored numeric values.\n"
    "6. SOURCE HIERARCHY: When weighing evidence, treat official filings and earnings-call transcripts as higher-tier than secondary news; treat primary issuer sources as higher-tier than syndicated wire copies. Contradictions between tiers must be called out.\n"
    "7. EXPLICIT UNCERTAINTY: If evidence is thin, stale, or contradictory, state this candidly in the uncertainty field and list concrete data the reader would need next in open_questions. Do not paper over gaps with boilerplate optimism.\n"
    "8. CHAIN-OF-THOUGHT DISCIPLINE: Before writing bull_points / bear_points, mentally enumerate every distinct material event in the retrieved context, then keep only the ones that are directly investable. Drop filler and duplicates.\n"
    "9. DECISION USEFULNESS: Prefer factors an investor can actually monitor: valuation anchor, price trend, margin or growth signal, macro sensitivity, catalyst timing, downside trigger, and missing data needed before sizing a position.\n\n"
    f"{DOMAIN_DECISION_PLAYBOOK}\n\n"
    f"{DECISION_GRADE_EQUITY_GUIDE}\n\n"
    "CRITICAL GENERATION RULES:\n"
    "1. Return ONLY a single valid JSON object conforming to the provided schema.\n"
    "2. No markdown fences, no commentary, no padding.\n"
    "3. bull_points and bear_points: each item MUST be an object of the form {\"text\": \"...\", \"evidence_doc_ids\": [\"doc-id-1\", \"doc-id-2\"]}.\n"
    "   - 'text' follows the 'Observation -> Significance' pattern (explain the 'So What?').\n"
    "   - 'evidence_doc_ids' lists the DOCUMENT IDs from the retrieved context (see each block's 'ID: ...') that directly support the point. Do not fabricate ids.\n"
    "   - If a point is not directly supported by any retrieved document, use an empty array [] and mark the point as speculative in 'text'.\n"
    "4. key_metrics: array of {name, value, as_of, context, evidence_doc_ids}. Each value must be copied or derived ONLY from the retrieved context. 'as_of' must be the source block DATE for that value, or 'unknown' only if unavailable. 'context' must be a short phrase (<= 20 words) describing why the metric matters. Return [] if the context contains no credible numerical evidence.\n"
    "5. catalyst_timeline: bucket concrete upcoming events or watch-items into near_term (0-3 months), mid_term (3-12 months), long_term (12+ months). Use the empty list [] for any bucket with no grounded items.\n"
    "6. open_questions: concrete, investable questions that remain unanswered given the evidence window. Keep each item to one sentence. Return [] only if the evidence is clearly sufficient.\n"
    "7. cited_doc_ids: union of all evidence_doc_ids used across bull_points, bear_points, and key_metrics.\n"
    "8. Use the requested Lens and Horizon to filter and weight the significance of evidence.\n"
    "9. If the prompt requests Korean, every natural-language value must be Korean: summary, bull_points.text, bear_points.text, key_metrics.name, key_metrics.context, catalyst_timeline items, open_questions, and uncertainty. Keep tickers, company names, product names, and source titles in their original language when appropriate."
)


def _format_compact_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(float(value))
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.2f}"


def _format_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _fundamentals_prompt_block(card: FundamentalsCard | None) -> str:
    if card is None:
        return ""
    sector = card.sector or "N/A"
    industry = card.industry or "N/A"
    name = card.name or card.ticker
    analysts = f"{card.num_analysts} analysts" if card.num_analysts is not None else "analyst count N/A"
    return (
        "FUNDAMENTALS SNAPSHOT (verified from yfinance, not RAG):\n"
        f"- Name: {name} ({card.ticker}) - Sector: {sector} / Industry: {industry}\n"
        f"- Market cap: {_format_compact_money(card.market_cap)} | Price: {_format_compact_money(card.price)} | "
        f"52w: {_format_compact_money(card.week52_low)} - {_format_compact_money(card.week52_high)}\n"
        f"- Valuation: P/E(TTM) {_format_float(card.trailing_pe, 1)} | P/E(Fwd) {_format_float(card.forward_pe, 1)} | "
        f"P/B {_format_float(card.price_to_book, 1)} | Beta {_format_float(card.beta, 2)}\n"
        f"- Growth / Margins: Revenue growth {_format_percent(card.revenue_growth)} | EPS growth {_format_percent(card.earnings_growth)} | "
        f"Profit margin {_format_percent(card.profit_margin)}\n"
        f"- Yield / Analyst: Div yield {_format_percent(card.dividend_yield)} | Consensus target "
        f"{_format_compact_money(card.analyst_target_mean)} ({analysts}, mean rating {_format_float(card.analyst_rating_mean, 1)})\n"
        "RULE: You MAY cite these values directly without an evidence_doc_id.\n"
        "      You MUST NOT contradict them. If RAG text contradicts these, flag it.\n\n"
    )


class StructuredOutputError(ValueError):
    """Typed validation failure for retryable structured-output issues."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def _build_ollama_prompt(
    symbol: str,
    question: str,
    context_items: List[RetrievalItem],
    task_type: str = "general",
    horizon: str = "unspecified",
    language: str = "ko",
    fundamentals: FundamentalsCard | None = None,
) -> tuple[str, int]:
    """
    Build the generation prompt from ranked context items.
    Enforces MAX_PROMPT_CHARS soft cap by dropping lowest-ranked chunks.
    Injects internal task_type and horizon for analytical lensing.
    Supports localization via language parameter.
    """
    if not context_items:
        raise ValueError(f"[Ollama] No context for {symbol}.")

    lang_instr = ""
    if language == "ko":
        lang_instr = (
            "LANGUAGE: KOREAN\n"
            "INSTRUCTION: Provide every natural-language output field in professional Korean: "
            "summary, bull_points.text, bear_points.text, key_metrics.name, key_metrics.context, "
            "catalyst_timeline items, open_questions, and uncertainty. "
            "English is allowed only for tickers, product names, company names, source titles, and standard market abbreviations.\n"
        )
    else:
        lang_instr = "LANGUAGE: ENGLISH\nINSTRUCTION: Provide all descriptive fields in professional English.\n"

    lens_instr = (
        f"ANALYTICAL LENS: {task_type.upper()}\n"
        f"TIME HORIZON: {horizon.upper()}\n"
        f"{lang_instr}"
        "PRIORITY: Prioritize evidence and reasoning that aligns with this lens and horizon.\n"
        "DOMAIN PLAYBOOK: Apply the relevant domain-specific decision variables from the system prompt. "
        "For example, do not analyze a commodity ETF like a software company, or a bank like a growth-stock ETF.\n"
        "REPORT SHAPE: Internally answer as a buy-side decision memo: Summary, Core Analysis, Synthesis, Decision Edge, Conclusion. "
        "The JSON fields must contain the raw material for that memo: compact summary, distinct bull/bear points, concrete risk scenarios, catalysts, pricing tension, and view-change triggers. "
        "If STRUCTURED DATA MART CONTEXT is present, use it as authoritative numeric evidence and do not invent numbers."
    )

    fundamentals_block = _fundamentals_prompt_block(fundamentals)
    output_contract = (
        "OUTPUT CONTRACT: Return exactly one JSON object. Ollama receives the full JSON schema via the structured "
        "format parameter, so do not repeat schema text or add fields. Required top-level fields are: symbol, "
        "event_type, sentiment, importance, confidence, horizon, uncertainty, summary, bull_points, bear_points, "
        "key_metrics, catalyst_timeline, open_questions, cited_doc_ids. bull_points and bear_points must be "
        "objects with text and evidence_doc_ids. key_metrics must include name, value, as_of, context, and "
        "evidence_doc_ids when evidence exists.\n\n"
    )

    base_overhead = (
        f"{lens_instr}\n\n"
        f"Target symbol: {symbol}\nUser question: {question}\n\n"
        f"{fundamentals_block}"
        f"{output_contract}"
        "Retrieved context documents:\n"
    )
    tail_overhead = "\n\nNow return the JSON object:"

    budget = MAX_PROMPT_CHARS - len(base_overhead) - len(tail_overhead)
    context_blocks: List[str] = []
    used_chunks = 0
    current_length = 0

    for i, item in enumerate(context_items, start=1):
        meta = getattr(item, "metadata", {}) or {}
        doc_id = meta.get("parent_doc_id") or meta.get("doc_id") or i
        source = getattr(item, "source", "Unknown")
        date = getattr(item, "date", "Unknown")
        title = getattr(item, "title", "Financial News")
        chunk = getattr(item, "chunk", "")
        chunk_hint = ""
        if meta.get("chunk_index") not in (None, "") and meta.get("total_chunks") not in (None, ""):
            chunk_hint = f" | CHUNK: {meta.get('chunk_index')}/{meta.get('total_chunks')}"

        snippet = " ".join(chunk.split())
        block = (
            f"--- DOCUMENT {i} [ID: {doc_id}] ---\n"
            f"SOURCE: {source} | DATE: {date}{chunk_hint}\n"
            f"TITLE: {title}\n"
            f"CONTENT: {snippet}\n"
        )

        if current_length + len(block) > budget and used_chunks > 0:
            break

        context_blocks.append(block)
        current_length += len(block)
        used_chunks += 1

    joined_context = "\n".join(context_blocks)
    final_prompt = base_overhead + joined_context + tail_overhead
    return final_prompt, used_chunks


def _get_installed_models(base_url: str) -> List[str]:
    """Return list of installed model name strings from Ollama."""
    tags_url = f"{base_url}/api/tags"
    try:
        resp = httpx.get(tags_url, timeout=5.0)
    except httpx.ConnectError:
        raise ConnectionError(f"[Ollama] Unreachable at {base_url}.")
    except httpx.TimeoutException:
        raise ConnectionError("[Ollama] Connection timed out.")
    if resp.status_code != 200:
        raise ConnectionError(f"[Ollama] Tags endpoint returned {resp.status_code}.")
    data = resp.json()
    return [m.get("name", "") for m in data.get("models", [])]


def _check_model_available(model_name: str, installed: Optional[List[str]] = None) -> None:
    """Raise RuntimeError if model_name is not in the installed list."""
    if installed is None:
        raise RuntimeError("Installed-model list must be provided.")
    if not any(model_name in name for name in installed):
        raise RuntimeError(f"[Ollama] '{model_name}' not installed. Run: ollama pull {model_name}")


def _call_ollama(
    base_url: str,
    model_name: str,
    system: str,
    prompt: str,
    timeout: float = 280.0,
    num_predict: int = DEFAULT_NUM_PREDICT,
) -> Dict[str, Any]:
    """POST to Ollama /api/generate (non-streaming)."""
    generate_url = f"{base_url}/api/generate"
    payload = {
        "model": model_name,
        "system": system,
        "prompt": prompt,
        "format": _OUTPUT_SCHEMA,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": num_predict,
            "num_ctx": DEFAULT_NUM_CTX,
        },
        "keep_alive": "5m",
    }
    try:
        resp = httpx.post(generate_url, json=payload, timeout=timeout)
    except Exception as e:
        raise ConnectionError(f"[Ollama] Request failed: {e}")
    if resp.status_code != 200:
        raise ConnectionError(f"[Ollama] API Error {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    return {
        "response": body.get("response", ""),
        "done_reason": body.get("done_reason"),
        "done": body.get("done"),
    }


def _clean_json_candidate(raw_text: str) -> str:
    text = str(raw_text or "").lstrip("\ufeff").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    return text


def _extract_json(raw_text: str) -> Dict[str, Any]:
    """Extract and parse the first complete JSON object from model output."""
    cleaned = _clean_json_candidate(raw_text)
    if not cleaned:
        raise StructuredOutputError("empty", "[Ollama] Empty output.")

    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise StructuredOutputError("schema-invalid", "[Ollama] JSON root must be an object.")
        return parsed
    except StructuredOutputError:
        raise
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    if start < 0:
        raise StructuredOutputError("malformed", "[Ollama] No JSON payload found.")

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(cleaned)):
        ch = cleaned[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "\"":
                in_string = False
            continue
        if ch == "\"":
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_str = cleaned[start : idx + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    raise StructuredOutputError("malformed", f"[Ollama] JSON malformed: {e}")
    raise StructuredOutputError("truncated", "[Ollama] JSON truncated or unclosed.")


def _natural_language_fragments(parsed: Dict[str, Any]) -> list[str]:
    fragments: list[str] = []

    for key in ("summary", "uncertainty"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            fragments.append(value)

    for field in ("bull_points", "bear_points"):
        for item in parsed.get(field, []) or []:
            if isinstance(item, dict):
                text = item.get("text")
            else:
                text = item
            if isinstance(text, str) and text.strip():
                fragments.append(text)

    for metric in parsed.get("key_metrics", []) or []:
        if not isinstance(metric, dict):
            continue
        for key in ("name", "context"):
            value = metric.get(key)
            if isinstance(value, str) and value.strip():
                fragments.append(value)

    timeline = parsed.get("catalyst_timeline") or {}
    if isinstance(timeline, dict):
        for bucket in ("near_term", "mid_term", "long_term"):
            for item in timeline.get(bucket, []) or []:
                if isinstance(item, str) and item.strip():
                    fragments.append(item)

    for question in parsed.get("open_questions", []) or []:
        if isinstance(question, str) and question.strip():
            fragments.append(question)

    return fragments


def _language_warning(parsed: Dict[str, Any], expected_language: str) -> Optional[str]:
    if str(expected_language or "").strip().lower() != "ko":
        return None

    joined = " ".join(_natural_language_fragments(parsed))
    if not joined.strip():
        return None

    hangul_count = len(re.findall(r"[\uac00-\ud7a3]", joined))
    cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", joined))
    mojibake_count = joined.count("\ufffd") + joined.count("\u5360") + len(re.findall(r"[\u00c0-\u00ff]{2,}", joined))
    latin_words = len(re.findall(r"\b[A-Za-z][A-Za-z\-]{2,}\b", joined))
    # A Korean report can still contain English tickers/product names. Reject
    # only when the descriptive payload is effectively non-Korean.
    if mojibake_count >= 3 or cjk_count >= max(8, hangul_count):
        return "[Ollama] Language violation: Korean output requested, but descriptive fields are not Korean."
    if hangul_count < 10 and latin_words >= 8:
        return "[Ollama] Language violation: Korean output requested, but descriptive fields are mostly English."
    return None


def _validate_language(parsed: Dict[str, Any], expected_language: str) -> None:
    warning = _language_warning(parsed, expected_language)
    if warning:
        raise StructuredOutputError("language", warning)


def _validate_response(
    parsed: Dict[str, Any],
    expected_language: str = "ko",
    enforce_language: bool = True,
) -> None:
    """Strictly validates that the parsed JSON matches the required schema and depth.

    The new ``key_metrics`` / ``catalyst_timeline`` / ``open_questions`` fields
    are *soft-required*: we accept empty values but raise when the top-level key
    is missing, since their absence usually signals that the model ignored the
    schema and reverted to a legacy shape.
    """
    required = [
        "symbol",
        "event_type",
        "sentiment",
        "importance",
        "confidence",
        "horizon",
        "uncertainty",
        "summary",
        "bull_points",
        "bear_points",
        "key_metrics",
        "catalyst_timeline",
        "open_questions",
        "cited_doc_ids",
    ]
    for key in required:
        if key not in parsed:
            raise StructuredOutputError("schema-invalid", f"[Ollama] Schema violation: missing required field '{key}'")

    if not str(parsed.get("summary", "")).strip():
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'summary' is empty.")

    if not isinstance(parsed.get("bull_points"), list):
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'bull_points' must be an array.")

    if not isinstance(parsed.get("bear_points"), list):
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'bear_points' must be an array.")

    # Accept both legacy string items and the new {text, evidence_doc_ids} objects.
    for field in ("bull_points", "bear_points"):
        for idx, item in enumerate(parsed.get(field, [])):
            if isinstance(item, str):
                continue
            if not isinstance(item, dict) or "text" not in item:
                raise StructuredOutputError(
                    "schema-invalid",
                    f"[Ollama] Schema violation: {field}[{idx}] must be a string or an object with 'text'.",
                )

    if not isinstance(parsed.get("cited_doc_ids"), list):
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'cited_doc_ids' must be an array.")

    if not isinstance(parsed.get("confidence"), (int, float)):
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'confidence' must be numeric.")

    if not isinstance(parsed.get("key_metrics"), list):
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'key_metrics' must be an array.")

    timeline = parsed.get("catalyst_timeline")
    if not isinstance(timeline, dict):
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'catalyst_timeline' must be an object.")
    for bucket in ("near_term", "mid_term", "long_term"):
        if bucket not in timeline or not isinstance(timeline.get(bucket), list):
            raise StructuredOutputError("schema-invalid", f"[Ollama] Schema violation: 'catalyst_timeline.{bucket}' must be an array.")

    if not isinstance(parsed.get("open_questions"), list):
        raise StructuredOutputError("schema-invalid", "[Ollama] Schema violation: 'open_questions' must be an array.")

    if enforce_language:
        _validate_language(parsed, expected_language)


def _coerce_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_thesis_points(value: Any) -> tuple[List[str], List[List[str]]]:
    """
    Accepts either a list of plain strings (legacy) or a list of
    ``{text, evidence_doc_ids}`` objects (current schema). Returns parallel
    arrays so the rest of the pipeline can keep the simple ``List[str]`` view.
    """
    texts: List[str] = []
    evidence: List[List[str]] = []
    if not isinstance(value, list):
        return texts, evidence
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            ev = item.get("evidence_doc_ids") or []
            ev_clean = [str(x).strip() for x in ev if str(x).strip()] if isinstance(ev, list) else []
            texts.append(text)
            evidence.append(ev_clean)
        else:
            text = str(item).strip()
            if not text:
                continue
            texts.append(text)
            evidence.append([])
    return texts, evidence


def _coerce_key_metrics(value: Any) -> List[Dict[str, Any]]:
    """Coerce the model's key_metrics array into the downstream shape.

    We tolerate minor deviations (missing evidence array, integer values) so
    partial outputs still render a useful metrics table. Items without a
    usable name+value pair are dropped silently.
    """
    if not isinstance(value, list):
        return []
    metrics: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        raw_val = item.get("value")
        if raw_val is None:
            continue
        val = str(raw_val).strip()
        if not name or not val:
            continue
        context = str(item.get("context") or "").strip()
        ev_raw = item.get("evidence_doc_ids") or []
        ev = [str(x).strip() for x in ev_raw if str(x).strip()] if isinstance(ev_raw, list) else []
        metrics.append({
            "name": name,
            "value": val,
            "as_of": str(item.get("as_of") or "").strip(),
            "context": context,
            "evidence_doc_ids": ev,
        })
    return metrics


def _coerce_timeline(value: Any) -> Dict[str, List[str]]:
    """Normalize catalyst_timeline into three string arrays.

    Unknown bucket keys are dropped. Missing buckets default to [].
    """
    buckets = {"near_term": [], "mid_term": [], "long_term": []}
    if not isinstance(value, dict):
        return buckets
    for key in buckets:
        raw = value.get(key)
        if isinstance(raw, list):
            buckets[key] = [str(x).strip() for x in raw if str(x).strip()]
    return buckets


def _normalize_response(parsed: Dict[str, Any], ticker: str, horizon: str) -> Dict[str, Any]:
    confidence = parsed.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5

    bull_texts, bull_evidence = _coerce_thesis_points(parsed.get("bull_points"))
    bear_texts, bear_evidence = _coerce_thesis_points(parsed.get("bear_points"))
    cited = _coerce_string_list(parsed.get("cited_doc_ids"))

    key_metrics = _coerce_key_metrics(parsed.get("key_metrics"))
    catalyst_timeline = _coerce_timeline(parsed.get("catalyst_timeline"))
    open_questions = _coerce_string_list(parsed.get("open_questions"))

    # If the model forgot cited_doc_ids but populated per-point evidence,
    # derive the union so downstream citation builders still work.
    if not cited:
        merged: List[str] = []
        seen: set[str] = set()
        for bucket in (bull_evidence, bear_evidence):
            for ids in bucket:
                for doc_id in ids:
                    if doc_id and doc_id not in seen:
                        seen.add(doc_id)
                        merged.append(doc_id)
        for metric in key_metrics:
            for doc_id in metric.get("evidence_doc_ids", []):
                if doc_id and doc_id not in seen:
                    seen.add(doc_id)
                    merged.append(doc_id)
        cited = merged

    return {
        "symbol": str(parsed.get("symbol") or ticker).strip() or ticker,
        "event_type": str(parsed.get("event_type") or "general").strip() or "general",
        "sentiment": str(parsed.get("sentiment") or "neutral").strip() or "neutral",
        "importance": str(parsed.get("importance") or "medium").strip() or "medium",
        "confidence": confidence,
        "horizon": str(parsed.get("horizon") or horizon).strip() or horizon,
        "uncertainty": str(parsed.get("uncertainty") or "").strip(),
        "summary": str(parsed.get("summary") or "").strip(),
        "bull_points": bull_texts,
        "bear_points": bear_texts,
        "bull_evidence_ids": bull_evidence,
        "bear_evidence_ids": bear_evidence,
        "key_metrics": key_metrics,
        "catalyst_timeline": catalyst_timeline,
        "open_questions": open_questions,
        "cited_doc_ids": cited,
    }


def _parse_generation_result(
    result: Dict[str, Any],
    expected_language: str = "ko",
    enforce_language: bool = True,
) -> Dict[str, Any]:
    raw_text = result.get("response", "")
    done_reason = result.get("done_reason")

    if not str(raw_text or "").strip():
        raise StructuredOutputError("empty", "[Ollama] Empty output.")

    if done_reason == "length":
        raise StructuredOutputError("truncated", "[Ollama] JSON truncated or unclosed.")

    parsed = _extract_json(raw_text)
    _validate_response(parsed, expected_language=expected_language, enforce_language=enforce_language)
    if not enforce_language:
        warning = _language_warning(parsed, expected_language)
        if warning:
            parsed["_language_warning"] = warning
    return parsed


def _build_language_repair_prompt(parsed: Dict[str, Any], expected_language: str) -> str:
    language_name = "Korean" if str(expected_language or "").lower() == "ko" else "English"
    return (
        f"Rewrite the following JSON object so every natural-language descriptive field is in {language_name}. "
        "Do not change tickers, company names, product names, source titles, numeric values, evidence_doc_ids, "
        "cited_doc_ids, sentiment, importance, confidence, symbol, event_type, or horizon. "
        "Return only one valid JSON object with the same keys and nested structure.\n\n"
        f"JSON to repair:\n{json.dumps(parsed, ensure_ascii=False)}"
    )


def _run_model_attempts(
    base_url: str,
    model_name: str,
    system: str,
    prompt: str,
    *,
    allow_retry: bool,
    expected_language: str = "ko",
) -> tuple[Dict[str, Any], float, int]:
    latencies = 0.0
    retries_used = 0
    num_predict_values = [DEFAULT_NUM_PREDICT]
    if allow_retry:
        num_predict_values.append(RETRY_NUM_PREDICT)

    current_prompt = prompt
    for attempt, num_predict in enumerate(num_predict_values):
        started_at = time.time()
        result = _call_ollama(
            base_url,
            model_name,
            system,
            current_prompt,
            num_predict=num_predict,
        )
        latencies += time.time() - started_at

        try:
            enforce_language = attempt < len(num_predict_values) - 1
            parsed = _parse_generation_result(
                result,
                expected_language=expected_language,
                enforce_language=enforce_language,
            )
            if parsed.get("_language_warning"):
                if allow_retry and str(expected_language or "").lower() == "ko":
                    retries_used += 1
                    logger.warning(
                        "[INFERENCE] %s missed requested language after retry. Attempting language repair pass...",
                        model_name,
                    )
                    repair_started = time.time()
                    repair_result = _call_ollama(
                        base_url,
                        model_name,
                        system,
                        _build_language_repair_prompt(parsed, expected_language),
                        num_predict=RETRY_NUM_PREDICT,
                    )
                    latencies += time.time() - repair_started
                    try:
                        repaired = _parse_generation_result(
                            repair_result,
                            expected_language=expected_language,
                            enforce_language=True,
                        )
                        return repaired, latencies, retries_used
                    except StructuredOutputError as repair_err:
                        logger.warning(
                            "[INFERENCE] %s language repair failed (%s). Returning final valid JSON with warning.",
                            model_name,
                            repair_err.reason,
                        )
                else:
                    logger.warning(
                        "[INFERENCE] %s returned valid JSON but missed requested language on final attempt: %s",
                        model_name,
                        parsed["_language_warning"],
                    )
            return parsed, latencies, retries_used
        except StructuredOutputError as err:
            can_retry = allow_retry and attempt == 0 and err.reason in RETRYABLE_OUTPUT_REASONS
            if can_retry:
                retries_used += 1
                if err.reason == "language" and str(expected_language or "").lower() == "ko":
                    current_prompt = (
                        prompt
                        + "\n\nRETRY CORRECTION: The previous response was rejected because it was not Korean. "
                        "Return the same JSON schema again, but write every descriptive field in Korean. "
                        "Only tickers, company names, product names, source titles, and standard market abbreviations may remain in English."
                    )
                logger.warning(
                    "[INFERENCE] %s returned %s output. Attempting retry 1/1 with larger generation budget...",
                    model_name,
                    err.reason,
                )
                continue
            raise

    raise StructuredOutputError("malformed", "[Ollama] Structured generation failed unexpectedly.")


class OllamaAdapter(BaseModelRunner):
    """Inference adapter backed by local Ollama with a production-first Qwen baseline."""

    def __init__(self, settings, model_name: Optional[str] = None):
        self.settings = settings
        self.ollama_base_url = settings.ollama_base_url.rstrip("/")
        self.model_name = model_name or settings.primary_model or DEFAULT_PRIMARY_MODEL
        self.fallback_model = settings.experimental_fallback_model or DEFAULT_EXPERIMENTAL_FALLBACK_MODEL
        self.enable_experimental_fallback = bool(settings.enable_experimental_fallback)

    def run_inference(
        self,
        ticker: str,
        question: str,
        context: List[RetrievalItem],
        task_type: str = "general",
        horizon: str = "unspecified",
        fundamentals: FundamentalsCard | None = None,
    ) -> Dict[str, Any]:
        installed = _get_installed_models(self.ollama_base_url)
        _check_model_available(self.model_name, installed)
        fallback_available = (
            self.enable_experimental_fallback
            and bool(self.fallback_model)
            and self.fallback_model != self.model_name
            and any(self.fallback_model in name for name in installed)
        )
        language = getattr(self.settings, "output_language", "ko")
        prompt, chunks_used = _build_ollama_prompt(
            ticker,
            question,
            context,
            task_type,
            horizon,
            language=language,
            fundamentals=fundamentals,
        )
        start_t = time.time()
        fallback_used = False
        producing_model = self.model_name
        primary_latency = 0.0
        fallback_latency = 0.0
        retries_used = 0

        try:
            parsed, primary_latency, retries_used = _run_model_attempts(
                self.ollama_base_url,
                self.model_name,
                _SYSTEM_PROMPT,
                prompt,
                allow_retry=True,
                expected_language=language,
            )
            logger.info("[INFERENCE] Primary generation succeeded.")

        except Exception as primary_err:
            if not fallback_available:
                if self.enable_experimental_fallback and self.fallback_model != self.model_name:
                    fallback_reason = f"experimental fallback model '{self.fallback_model}' is unavailable"
                else:
                    fallback_reason = "experimental fallback is disabled"
                raise ValueError(
                    f"[Ollama] Primary failed and no production fallback is configured ({fallback_reason}). Last error: {primary_err}"
                )

            logger.warning(f"[INFERENCE] Primary failed ({primary_err}). Activating fallback={self.fallback_model}...")

            try:
                parsed, fallback_latency, _ = _run_model_attempts(
                    self.ollama_base_url,
                    self.fallback_model,
                    _SYSTEM_PROMPT,
                    prompt,
                    allow_retry=False,
                    expected_language=language,
                )

                fallback_used = True
                producing_model = self.fallback_model
                logger.info("[INFERENCE] Fallback generation succeeded.")

            except Exception as second_err:
                logger.error(f"[INFERENCE] Critical failure in both models. Last error: {second_err}")
                raise ValueError(f"Inference pipeline failed: Both models produced invalid output. (Last: {second_err})")

        total_latency = time.time() - start_t
        language_warning = parsed.pop("_language_warning", None)
        normalized = _normalize_response(parsed, ticker, horizon)

        result = {
            "symbol": normalized["symbol"],
            "event_type": normalized["event_type"],
            "sentiment": normalized["sentiment"].capitalize(),
            "importance": normalized["importance"],
            "confidence": normalized["confidence"],
            "horizon": normalized["horizon"],
            "uncertainty": normalized["uncertainty"],
            "summary": normalized["summary"],
            "bull_points": normalized["bull_points"],
            "bear_points": normalized["bear_points"],
            "bull_evidence_ids": normalized["bull_evidence_ids"],
            "bear_evidence_ids": normalized["bear_evidence_ids"],
            "key_metrics": normalized["key_metrics"],
            "catalyst_timeline": normalized["catalyst_timeline"],
            "open_questions": normalized["open_questions"],
            "cited_doc_ids": normalized["cited_doc_ids"],
            "_meta": {
                "primary_model": self.model_name,
                "producing_model": producing_model,
                "fallback_enabled": self.enable_experimental_fallback,
                "fallback_model": self.fallback_model if self.enable_experimental_fallback else None,
                "fallback_available": fallback_available,
                "fallback_used": fallback_used,
                "total_latency_s": round(total_latency, 2),
                "primary_latency_s": round(primary_latency, 2),
                "fallback_latency_s": round(fallback_latency, 2),
                "retry_count": retries_used,
                "chunks_used": chunks_used,
                "prompt_char_count": len(prompt),
                "lens": task_type,
                "context_horizon": horizon,
                "language": language,
                "language_warning": language_warning,
            },
        }

        return result
