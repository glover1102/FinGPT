from typing import List, Dict, Any
import json
from pipelines.infer.base import BaseModelRunner
from core.schemas.retrieval import RetrievalItem
from core.utils.logger import get_logger

logger = get_logger("pipelines.infer.fingpt")

class FinGPTAdapter(BaseModelRunner):
    def __init__(self, settings):
        self.settings = settings

    def run_inference(self, ticker: str, question: str, context: List[RetrievalItem]) -> Dict[str, Any]:
        logger.info(f"Running FinGPT adapter for {ticker}...")

        if not context:
            logger.warning("No context provided, the response may hallucinate or be empty.")
            return {
                "summary": "No relevant context found.",
                "sentiment": "Neutral",
                "risk_flags": []
            }

        try:
            from core.utils.prompt_helpers import build_event_extraction_prompt, extract_json_object
            import torch

            def load_model_and_tokenizer(settings):
                from transformers import AutoModelForCausalLM, AutoTokenizer
                from peft import PeftModel
                token = settings.hf_token or None
                tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-2-7b-hf", trust_remote_code=True, token=token)
                model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-2-7b-hf", trust_remote_code=True, low_cpu_mem_usage=True, token=token)
                return tokenizer, model

            
            # Repackage context for legacy prompt builder
            legacy_hits = []
            for item in context:
                legacy_hits.append({
                    "metadata": {"doc_id": "doc", "title": item.title, "published_at": item.date, "source": item.source},
                    "document": item.chunk
                })
                
            prompt = build_event_extraction_prompt(ticker, question, legacy_hits)

            logger.info("Loading model/tokenizer...")
            tokenizer, model = load_model_and_tokenizer(self.settings)
            
            # Simple inference fallback to avoid CUDA requirement crashing it if unavailable
            if torch.cuda.is_available():
                model_device = next(model.parameters()).device
                inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
                inputs = {key: value.to(model_device) for key, value in inputs.items()}
                
                with torch.inference_mode():
                    output_ids = model.generate(
                        **inputs,
                        do_sample=False,
                        temperature=0.1,
                        max_new_tokens=self.settings.max_new_tokens,
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                    )
            
                prompt_tokens = inputs["input_ids"].shape[1]
                generated_text = tokenizer.decode(output_ids[0][prompt_tokens:], skip_special_tokens=True).strip()
            else:
                # Fast fallback or mock for testing without CUDA to avoid killing hours
                logger.warning("CUDA unavailable. Running a generic mock fallback instead of slow CPU to prevent blocking testing.")
                generated_text = '{"summary": "Mock summary due to CPU. Real model requires GPU.", "sentiment": "Neutral", "risk_flags": ["CPU bottleneck"]}'
            
            json_text = extract_json_object(generated_text)
            parsed = json.loads(json_text)
            return parsed
            
        except ImportError as ie:
            logger.error(f"Cannot import models: {ie}")
            return {"summary": "Failed to import inference dependencies.", "sentiment": "Neutral", "risk_flags": []}
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            return {"summary": "Inference error occurred.", "sentiment": "Neutral", "risk_flags": []}
