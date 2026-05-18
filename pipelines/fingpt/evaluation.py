from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from core.schemas.fingpt import FinGPTEvaluationCase, FinGPTEvaluationResult


def load_eval_cases(path: Path) -> list[FinGPTEvaluationCase]:
    cases: list[FinGPTEvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(FinGPTEvaluationCase.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"Invalid evaluation case at {path}:{line_number}: {exc}") from exc
    return cases


def normalize_label(label: str) -> str:
    normalized = label.strip().lower()
    aliases = {
        "positive": "positive",
        "pos": "positive",
        "bullish": "positive",
        "negative": "negative",
        "neg": "negative",
        "bearish": "negative",
        "neutral": "neutral",
        "mixed": "mixed",
        "yes": "price_up",
        "no": "not_price_up",
        "price up": "price_up",
        "price_up": "price_up",
        "up": "price_up",
        "price down": "price_down",
        "price_down": "price_down",
        "down": "price_down",
    }
    return aliases.get(normalized, normalized)


def _result_task(cases: Sequence[FinGPTEvaluationCase]) -> str:
    if not cases:
        return "sentiment"
    tasks = {case.task for case in cases}
    return cases[0].task if len(tasks) == 1 else "mixed"


def evaluate_cases(
    cases: Sequence[FinGPTEvaluationCase],
    *,
    route: str,
    predictor: Callable[[FinGPTEvaluationCase], object],
) -> FinGPTEvaluationResult:
    started = time.perf_counter()
    task = _result_task(cases)
    total = len(cases)
    correct = 0
    invalid_outputs = 0

    for case in cases:
        try:
            predicted = predictor(case)
        except Exception:
            invalid_outputs += 1
            continue

        if not isinstance(predicted, str):
            invalid_outputs += 1
            continue

        if normalize_label(predicted) == normalize_label(case.expected_label):
            correct += 1

    accuracy = correct / total if total else 0.0
    latency_s = round(time.perf_counter() - started, 3)
    return FinGPTEvaluationResult(
        route=route,
        task=task,
        total=total,
        correct=correct,
        accuracy=accuracy,
        invalid_outputs=invalid_outputs,
        latency_s=latency_s,
    )


def result_to_json(result: FinGPTEvaluationResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
