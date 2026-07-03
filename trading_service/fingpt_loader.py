from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()


class FinGPTModel:
    def __init__(self, base_model_name: str, lora_model_name: str, use_8bit: bool = True, hf_token: str | None = None):
        self.base_model_name = base_model_name
        self.lora_model_name = lora_model_name
        self.use_8bit = use_8bit
        self.hf_token = hf_token
        self._model: Any | None = None
        self._tokenizer: Any | None = None

    def load(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("FinGPT model dependencies are not installed") from exc

        log.info("loading_fingpt_model", base=self.base_model_name, lora=self.lora_model_name, use_8bit=self.use_8bit)

        has_cuda = torch.cuda.is_available()
        load_kwargs = {
            "device_map": "auto" if has_cuda else {"": "cpu"},
            "low_cpu_mem_usage": True,
            "trust_remote_code": False,
            "token": self.hf_token,
        }
        if has_cuda:
            load_kwargs["torch_dtype"] = torch.float16
        else:
            load_kwargs["torch_dtype"] = torch.float32
        if self.use_8bit:
            load_kwargs["load_in_8bit"] = True

        try:
            base_model = AutoModelForCausalLM.from_pretrained(self.base_model_name, **load_kwargs)
        except Exception as exc:
            if not self.use_8bit:
                raise RuntimeError("Unable to load FinGPT base model") from exc
            log.warning("fingpt_8bit_load_failed", error=str(exc))
            load_kwargs.pop("load_in_8bit", None)
            base_model = AutoModelForCausalLM.from_pretrained(self.base_model_name, **load_kwargs)

        tokenizer = AutoTokenizer.from_pretrained(self.base_model_name, token=self.hf_token, trust_remote_code=False)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = PeftModel.from_pretrained(base_model, self.lora_model_name, token=self.hf_token)
        model.eval()

        self._model = model
        self._tokenizer = tokenizer
        log.info("fingpt_model_loaded")

    def generate_sentiment(self, text: str, instruction: str | None = None) -> str:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("PyTorch is required for sentiment inference") from exc

        self.load()

        if instruction is None:
            instruction = "What is the sentiment of this news? Please choose an answer from {negative/neutral/positive}."

        prompt = f"Instruction: {instruction}\nInput: {text}\nAnswer: "
        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )

        model_device = self._get_model_device()
        if model_device is not None:
            inputs = {key: value.to(model_device) for key, value in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=16,
                do_sample=False,
                eos_token_id=self._tokenizer.eos_token_id,
                pad_token_id=self._tokenizer.pad_token_id,
            )

        result = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
        if "Answer: " in result:
            result = result.split("Answer: ", 1)[-1].strip()
        return result.strip()

    def is_loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    def _get_model_device(self):
        if self._model is None:
            return None
        try:
            return next(self._model.parameters()).device
        except (StopIteration, AttributeError, TypeError):
            return None

