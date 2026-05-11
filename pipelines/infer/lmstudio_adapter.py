"""
LM Studio-based inference adapter for the FinGPT pipeline.
OpenAI-compatible API implementation with dynamic model discovery.

Architecture:
  Primary model  : Dynamically discovered (Gemma-family)
  Fallback model : Dynamically discovered (Mistral-family)

Fallback rules (strict):
  - Same prompt, no modification
  - No output merging or blending
  - Fallback is logged explicitly (fallback_used, fallback_model)
  - If fallback also fails → raises ValueError → pipeline status: failed
"""
import time
import json
import httpx
from typing import List, Dict, Any, Optional

from pipelines.infer.base import BaseModelRunner
from core.schemas.retrieval import RetrievalItem
from core.utils.logger import get_logger

logger = get_logger("pipelines.infer.lmstudio")

# LM Studio default port
LMSTUDIO_BASE_URL = "http://localhost:1234"
LMSTUDIO_MODELS_URL = f"{LMSTUDIO_BASE_URL}/v1/models"
LMSTUDIO_CHAT_URL = f"{LMSTUDIO_BASE_URL}/v1/chat/completions"

# Soft cap to prevent context overflow or fragmentation
MAX_PROMPT_CHARS = 12000

_OUTPUT_SCHEMA = {
    "symbol": "string",
    "event_type": "string",
    "sentiment": "positive|negative|neutral|mixed",
    "importance": "low|medium|high|critical",
    "confidence": 0.0,
    "horizon": "immediate|days|weeks|months|unclear",
    "uncertainty": "string",
    "summary": "string",
    "bull_points": ["string"],
    "bear_points": ["string"],
    "cited_doc_ids": ["string"],
}

_SYSTEM_PROMPT = (
    "You are a Senior Equity Research Analyst, an expert at synthesizing scattered financial data into high-density investment theses. "
    "Your objective is to provide professional-grade insight, not a simple news summary.\n\n"
    "ANALYTICAL DOCTRINE:\n"
    "1. SYNTHESIS > SUMMARIZATION: Do not list events chronologically. Connect disparate facts to identify underlying trends, operational momentum, or strategic shifts.\n"
    "2. THESIS-DRIVEN BULLETS: Every bull and bear point must follow the 'Observation → Significance' pattern. Don't just state what happened; explain why it matters for the stock price or company valuation.\n"
    "3. CROSS-DOCUMENT VALIDATION: Prioritize evidence that is corroborated by multiple sources. Note contradictions if they are material.\n"
    "4. PRECISION: Be specific with numbers, names, and technical terms. Avoid vague boilerplate like 'increased competition'—instead specify who the competitor is and what the impact is.\n\n"
    "CRITICAL GENERATION RULES:\n"
    "1. Return ONLY a single valid JSON object.\n"
    "2. No markdown fences, no commentary, no padding.\n"
    "3. bull_points: List distinct bullish catalysts or drivers. Explain the 'So What?' for each.\n"
    "4. bear_points: List distinct risks or headwinds. Explain the 'So What?' for each.\n"
    "5. Use the requested Lens and Horizon to filter and weight the significance of evidence."
)

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _discover_models() -> Dict[str, str]:
    """
    Queries LM Studio to dynamically identify Gemma and Mistral families.
    Returns: {"primary": "id", "fallback": "id"}
    """
    try:
        resp = httpx.get(LMSTUDIO_MODELS_URL, timeout=5.0)
        if resp.status_code != 200:
            raise RuntimeError(f"LM Studio returned status {resp.status_code}")
        
        models_data = resp.json().get("data", [])
        model_ids = [m.get("id") for m in models_data if m.get("id")]
        
        logger.info(f"[DISCOVERY] Available in LM Studio: {model_ids}")
        
        # Selection logic (deterministic)
        gemma_candidates = sorted([mid for mid in model_ids if "gemma" in mid.lower()])
        mistral_candidates = sorted([mid for mid in model_ids if "mistral" in mid.lower()])
        
        mapping = {}
        if gemma_candidates:
            mapping["primary"] = gemma_candidates[0]
            logger.info(f"[DISCOVERY] Selected Primary (Gemma): {mapping['primary']}")
        else:
            logger.warning("[DISCOVERY] No Gemma-family model found in LM Studio!")
            
        if mistral_candidates:
            mapping["fallback"] = mistral_candidates[0]
            logger.info(f"[DISCOVERY] Selected Fallback (Mistral): {mapping['fallback']}")
        else:
            logger.warning("[DISCOVERY] No Mistral-family model found in LM Studio!")
            
        return mapping
        
    except Exception as e:
        logger.error(f"[DISCOVERY] Failed to query LM Studio: {e}")
        return {}

# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

def _build_messages(
    symbol: str,
    question: str,
    context_items: List[RetrievalItem],
    task_type: str = "general",
    horizon: str = "unspecified"
) -> tuple[List[Dict[str, str]], int]:
    """
    Builds OpenAI-style messages list.
    """
    schema_json = json.dumps(_OUTPUT_SCHEMA, indent=2)
    
    lens_instr = (
        f"ANALYTICAL LENS: {task_type.upper()}\n"
        f"TIME HORIZON: {horizon.upper()}\n"
        "INSTRUCTION: Prioritize evidence and reasoning that aligns with this lens and horizon."
    )

    user_overhead = (
        f"{lens_instr}\n\n"
        f"Target symbol: {symbol}\nUser question: {question}\n\n"
        f"Required output JSON schema:\n{schema_json}\n\n"
        f"Retrieved context documents:\n"
    )

    budget = MAX_PROMPT_CHARS - len(user_overhead) - 500 # padding for tail
    context_blocks: List[str] = []
    used_chunks = 0
    current_length = 0

    for i, item in enumerate(context_items, start=1):
        doc_id = getattr(item, "doc_id", i)
        source = getattr(item, "source", "Unknown")
        date   = getattr(item, "date", "Unknown")
        title  = getattr(item, "title", "Financial News")
        chunk  = getattr(item, "chunk", "")

        snippet = " ".join(chunk.split())
        block = (
            f"--- DOCUMENT {i} [ID: {doc_id}] ---\n"
            f"SOURCE: {source} | DATE: {date}\n"
            f"TITLE: {title}\n"
            f"CONTENT: {snippet}\n"
        )

        if current_length + len(block) > budget and used_chunks > 0:
            break

        context_blocks.append(block)
        current_length += len(block)
        used_chunks += 1

    user_content = user_overhead + "\n".join(context_blocks) + "\n\nNow return the JSON object:"
    
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]
    return messages, used_chunks

# ---------------------------------------------------------------------------
# API Call
# ---------------------------------------------------------------------------

def _call_lmstudio(model_id: str, messages: List[Dict[str, str]], timeout: float = 300.0) -> str:
    """POST to LM Studio /v1/chat/completions."""
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.1,
        "stream": False
    }
    
    try:
        resp = httpx.post(LMSTUDIO_CHAT_URL, json=payload, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"LM Studio API Error {resp.status_code}: {resp.text[:200]}")
        
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        raise ConnectionError(f"LM Studio request failed: {e}")

# ---------------------------------------------------------------------------
# Parsing & Validation
# ---------------------------------------------------------------------------

def _extract_json(raw_text: str) -> Dict[str, Any]:
    """Extracted from ollama_adapter.py - identical logic."""
    start = raw_text.find("{")
    if start < 0:
        raise ValueError("No JSON payload found.")

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(raw_text)):
        ch = raw_text[idx]
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
                json_str = raw_text[start: idx + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    raise ValueError(f"JSON malformed: {e}")
    raise ValueError("JSON truncated or unclosed.")

def _validate_response(parsed: Dict[str, Any]) -> None:
    REQUIRED = ["symbol", "sentiment", "summary", "bull_points", "bear_points"]
    for key in REQUIRED:
        if key not in parsed:
            raise ValueError(f"Schema violation: missing required field '{key}'")
    if not str(parsed.get("summary", "")).strip():
        raise ValueError("Schema violation: 'summary' is empty.")
    if not isinstance(parsed.get("bull_points"), list):
        raise ValueError("Schema violation: 'bull_points' must be an array.")
    if not isinstance(parsed.get("bear_points"), list):
        raise ValueError("Schema violation: 'bear_points' must be an array.")

# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class LMStudioAdapter(BaseModelRunner):
    """
    Inference adapter backed by LM Studio (OpenAI-compatible) with dynamic model discovery.
    """

    def __init__(self, settings, model_name: Optional[str] = None):
        self.settings = settings
        self._mapping = {} # To be populated by discovery

    def run_inference(
        self,
        ticker: str,
        question: str,
        context: List[RetrievalItem],
        task_type: str = "general",
        horizon: str = "unspecified"
    ) -> Dict[str, Any]:

        # 1. Discover models if not already mapped
        if not self._mapping:
            self._mapping = _discover_models()
        
        primary_id = self._mapping.get("primary")
        fallback_id = self._mapping.get("fallback")
        
        if not primary_id:
            raise RuntimeError("No primary (Gemma) model discovered in LM Studio.")

        messages, chunks_used = _build_messages(ticker, question, context, task_type, horizon)
        logger.info(f"[INFERENCE] primary={primary_id} task={task_type} chunks={chunks_used}")

        start_t = time.time()
        fallback_used = False
        producing_model = primary_id

        try:
            # ── 1. Primary generation
            raw_text = _call_lmstudio(primary_id, messages)
            if not raw_text.strip():
                raise ValueError("Empty output")
            
            parsed = _extract_json(raw_text)
            _validate_response(parsed)
            logger.info("[INFERENCE] Primary generation succeeded.")

        except Exception as primary_err:
            # ── 2. Fallback
            if not fallback_id:
                raise ValueError(f"Primary failed ({primary_err}) and no Mistral fallback discovered.")
            
            logger.warning(f"[INFERENCE] Primary failed ({primary_err}). Activating fallback={fallback_id}...")
            
            try:
                raw_text = _call_lmstudio(fallback_id, messages)
                if not raw_text.strip():
                    raise ValueError("Fallback returned empty string.")
                
                parsed = _extract_json(raw_text)
                _validate_response(parsed)
                
                fallback_used = True
                producing_model = fallback_id
                logger.info("[INFERENCE] Fallback generation succeeded.")
                
            except Exception as second_err:
                logger.error(f"[INFERENCE] Critical failure in both models. Last error: {second_err}")
                raise ValueError(f"Inference pipeline failed: Both models produced invalid output. (Last: {second_err})")

        latency = time.time() - start_t
        
        # ── 3. Normalize Result
        result = {
            "symbol":        parsed.get("symbol", ticker),
            "event_type":    parsed.get("event_type", "general"),
            "sentiment":     parsed.get("sentiment", "Neutral").capitalize(),
            "importance":    parsed.get("importance", "medium"),
            "confidence":    float(parsed.get("confidence", 0.5)),
            "horizon":       parsed.get("horizon", horizon),
            "uncertainty":   parsed.get("uncertainty", ""),
            "summary":       parsed.get("summary", ""),
            "bull_points":   parsed.get("bull_points", []),
            "bear_points":   parsed.get("bear_points", []),
            "cited_doc_ids": parsed.get("cited_doc_ids", []),
            "_meta": {
                "producing_model": producing_model,
                "fallback_used":   fallback_used,
                "latency_s":       round(latency, 2),
                "chunks_used":     chunks_used,
                "lens":            task_type,
                "context_horizon": horizon,
                "adapter":         "lmstudio"
            },
        }

        return result
