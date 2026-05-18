from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.fingpt.evaluation import evaluate_cases, load_eval_cases, result_to_json


def rule_predictor(case):
    text = case.input_text.lower()
    if any(token in text for token in ("rose", "expanded", "beat", "climb", "strong")):
        return "positive" if case.task == "sentiment" else "price_up"
    if any(token in text for token in ("cut", "weaker", "falls", "investigation", "higher costs")):
        return "negative" if case.task == "sentiment" else "price_down"
    return "neutral"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate FinGPT-style financial task cases.")
    parser.add_argument("--cases", default="tests/fixtures/fingpt_eval_cases.jsonl")
    parser.add_argument("--route", default="rule-baseline")
    args = parser.parse_args()
    cases = load_eval_cases(Path(args.cases))
    result = evaluate_cases(cases, route=args.route, predictor=rule_predictor)
    print(result_to_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
