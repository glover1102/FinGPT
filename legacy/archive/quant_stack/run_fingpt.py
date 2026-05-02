# Retrieve top Qdrant documents, build a FinGPT-style event-extraction prompt, and run local inference.
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import traceback

from app.config import EXPECTED_TRANSFORMERS_VERSION, load_settings
from app.preflight import check_model, check_qdrant, configure_huggingface_env, ensure_supported_runtime
from app.pipeline import build_event_extraction_prompt, extract_json_object, get_qdrant_client, search_documents


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal FinGPT-style event extraction step on retrieved docs.")
    parser.add_argument("--query", default=None, help="Search query used to retrieve supporting documents.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of retrieved documents to pass into the prompt.")
    return parser.parse_args()


def ensure_transformers_guard() -> None:
    installed = metadata.version("transformers")
    if installed != EXPECTED_TRANSFORMERS_VERSION:
        raise RuntimeError(
            "run_fingpt.py requires the pinned Transformers version. "
            f"Expected {EXPECTED_TRANSFORMERS_VERSION}, found {installed}. "
            "Run: pip install -r quant_stack/requirements-quant-stack.txt -c quant_stack/constraints-quant-stack.txt"
        )


def verify_model_access(settings) -> None:
    model_check = check_model(settings)
    if not model_check.ok:
        raise RuntimeError(model_check.details.get("error", "model preflight failed"))


def load_model_and_tokenizer(settings):
    ensure_transformers_guard()
    configure_huggingface_env(settings)

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "run_fingpt.py requires torch, transformers, and peft in the active environment. "
            f"Original error: {exc}"
        ) from exc

    token = settings.hf_token or None
    tokenizer = AutoTokenizer.from_pretrained(settings.base_model_name, trust_remote_code=True, token=token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token

    model_kwargs: dict[str, object] = {
        "trust_remote_code": True,
        "low_cpu_mem_usage": True,
        "token": token,
    }

    if torch.cuda.is_available():
        model_kwargs["device_map"] = "auto"
        if settings.enable_4bit:
            # 4bit loading is the preferred GPU path for constrained local inference.
            # If bitsandbytes or the installed CUDA stack cannot support it, the code falls back to fp16 GPU.
            try:
                from transformers import BitsAndBytesConfig

                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )
                print("Model load path: 4bit GPU")
            except Exception as exc:
                print(f"4bit loading is unavailable, falling back to fp16 GPU: {exc}")
                model_kwargs["torch_dtype"] = torch.float16
        else:
            print("Model load path: fp16 GPU")
            model_kwargs["torch_dtype"] = torch.float16
    else:
        print("Model load path: fp32 CPU (slow)")
        model_kwargs["torch_dtype"] = torch.float32

    model = AutoModelForCausalLM.from_pretrained(settings.base_model_name, **model_kwargs)
    if settings.adapter_model_name:
        model = PeftModel.from_pretrained(model, settings.adapter_model_name, token=token)
    model.eval()
    return tokenizer, model


def main() -> None:
    ensure_supported_runtime()
    args = parse_args()
    settings = load_settings()
    query_text = args.query or f"What are the most important short-term risks and catalysts for {settings.symbol}?"

    qdrant_check = check_qdrant(settings)
    if not qdrant_check.ok:
        raise RuntimeError(qdrant_check.details.get("error", "qdrant preflight failed"))

    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    hits = search_documents(
        client=client,
        collection_name=settings.collection_name,
        symbol=settings.symbol,
        query_text=query_text,
        limit=args.top_k,
    )
    if not hits:
        print(
            f"No Qdrant documents were found for symbol={settings.symbol}. "
            "Run collect_openbb.py and ingest_qdrant.py before model inference."
        )
        return

    verify_model_access(settings)
    prompt = build_event_extraction_prompt(settings.symbol, query_text, hits)

    import torch

    tokenizer, model = load_model_and_tokenizer(settings)
    model_device = next(model.parameters()).device
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
    inputs = {key: value.to(model_device) for key, value in inputs.items()}

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            do_sample=False,
            temperature=0.1,
            max_new_tokens=settings.max_new_tokens,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    prompt_tokens = inputs["input_ids"].shape[1]
    generated_text = tokenizer.decode(output_ids[0][prompt_tokens:], skip_special_tokens=True).strip()
    json_text = extract_json_object(generated_text)
    parsed = json.loads(json_text)
    print(json.dumps(parsed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI behavior
        print(f"run_fingpt.py failed: {exc}")
        traceback.print_exc()
        raise SystemExit(1) from exc
