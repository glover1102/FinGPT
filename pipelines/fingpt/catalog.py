from __future__ import annotations

from core.schemas.fingpt import FinGPTDatasetSpec, FinGPTModelSpec, FinGPTTask


FINGPT_DATASETS: tuple[FinGPTDatasetSpec, ...] = (
    FinGPTDatasetSpec(
        task="sentiment",
        hf_id="FinGPT/fingpt-sentiment-train",
        expected_columns=["input", "output"],
        use_case="Financial sentiment classification for news and filing snippets.",
    ),
    FinGPTDatasetSpec(
        task="headline",
        hf_id="FinGPT/fingpt-headline",
        expected_columns=["input", "output"],
        use_case="Headline-level market event and stance classification.",
    ),
    FinGPTDatasetSpec(
        task="ner",
        hf_id="FinGPT/fingpt-ner",
        expected_columns=["input", "output"],
        use_case="Financial named entity extraction for companies, tickers, people, and instruments.",
    ),
    FinGPTDatasetSpec(
        task="relation",
        hf_id="FinGPT/fingpt-relation",
        expected_columns=["input", "output"],
        use_case="Financial relation extraction between entities in market text.",
    ),
    FinGPTDatasetSpec(
        task="fiqa_qa",
        hf_id="FinGPT/fingpt-fiqa_qa",
        expected_columns=["instruction", "input", "output"],
        use_case="Financial question answering over FIQA-style prompts.",
    ),
    FinGPTDatasetSpec(
        task="forecaster",
        hf_id="FinGPT/fingpt-forecaster",
        expected_columns=["instruction", "input", "output"],
        use_case="Market-aware forecasting prompts for price direction and thesis evaluation.",
    ),
)


FINGPT_MODELS: tuple[FinGPTModelSpec, ...] = (
    FinGPTModelSpec(
        task="sentiment",
        hf_id="FinGPT/fingpt-mt_llama2-7b_lora",
        base_model="meta-llama/Llama-2-7b-hf",
        recommended_for=["sentiment", "headline"],
    ),
    FinGPTModelSpec(
        task="headline",
        hf_id="FinGPT/fingpt-mt_llama2-7b_lora",
        base_model="meta-llama/Llama-2-7b-hf",
        recommended_for=["headline", "sentiment"],
    ),
    FinGPTModelSpec(
        task="ner",
        hf_id="FinGPT/fingpt-ner_llama2-7b_lora",
        base_model="meta-llama/Llama-2-7b-hf",
        recommended_for=["ner"],
    ),
    FinGPTModelSpec(
        task="relation",
        hf_id="FinGPT/fingpt-relation_llama2-7b_lora",
        base_model="meta-llama/Llama-2-7b-hf",
        recommended_for=["relation"],
    ),
    FinGPTModelSpec(
        task="fiqa_qa",
        hf_id="FinGPT/fingpt-fiqa_qa_llama2-7b_lora",
        base_model="meta-llama/Llama-2-7b-hf",
        recommended_for=["fiqa_qa"],
    ),
    FinGPTModelSpec(
        task="forecaster",
        hf_id="FinGPT/fingpt-forecaster_dow30_llama2-7b_lora",
        base_model="meta-llama/Llama-2-7b-hf",
        recommended_for=["forecaster"],
    ),
)


def dataset_for_task(task: FinGPTTask) -> FinGPTDatasetSpec:
    for dataset in FINGPT_DATASETS:
        if dataset.task == task:
            return dataset.model_copy(deep=True)
    raise ValueError(f"unsupported FinGPT dataset task: {task}")


def model_for_task(task: FinGPTTask) -> FinGPTModelSpec:
    for model in FINGPT_MODELS:
        if model.task == task:
            return model.model_copy(deep=True)
    raise ValueError(f"unsupported FinGPT model task: {task}")
