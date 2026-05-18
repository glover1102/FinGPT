from pathlib import Path

import pytest

from pipelines.fingpt.evaluation import evaluate_cases, load_eval_cases, normalize_label


def test_load_eval_cases_reads_jsonl_fixture():
    path = Path("tests/fixtures/fingpt_eval_cases.jsonl")
    cases = load_eval_cases(path)
    assert len(cases) == 4
    assert cases[0].case_id == "sent-1"
    assert cases[0].task == "sentiment"


def test_evaluate_cases_counts_accuracy():
    cases = load_eval_cases(Path("tests/fixtures/fingpt_eval_cases.jsonl"))[:2]

    def predictor(case):
        return "positive" if "rose" in case.input_text else "negative"

    result = evaluate_cases(cases, route="rule-test", predictor=predictor)
    assert result.task == "sentiment"
    assert result.total == 2
    assert result.correct == 2
    assert result.accuracy == 1.0
    assert result.invalid_outputs == 0


def test_evaluate_cases_reports_mixed_task_for_mixed_fixture():
    cases = load_eval_cases(Path("tests/fixtures/fingpt_eval_cases.jsonl"))

    def predictor(case):
        return case.expected_label

    result = evaluate_cases(cases, route="mixed-test", predictor=predictor)
    assert result.task == "mixed"
    assert result.total == 4
    assert result.correct == 4


def test_normalize_label_maps_common_aliases():
    assert normalize_label("POS") == "positive"
    assert normalize_label("bearish") == "negative"
    assert normalize_label("price up") == "price_up"
    assert normalize_label("Down") == "price_down"
    assert normalize_label("foo-bar") == "foo-bar"


def test_load_eval_cases_reports_invalid_line(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        (
            '{"case_id":"ok","task":"sentiment","input_text":"ok",'
            '"expected_label":"neutral","ticker":"MSFT"}\n'
            "not-json\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Invalid evaluation case at .*cases\.jsonl:2:"):
        load_eval_cases(path)


def test_evaluate_cases_counts_predictor_exceptions():
    cases = load_eval_cases(Path("tests/fixtures/fingpt_eval_cases.jsonl"))[:1]

    def predictor(case):
        raise RuntimeError("offline model unavailable")

    result = evaluate_cases(cases, route="exception-test", predictor=predictor)
    assert result.total == 1
    assert result.correct == 0
    assert result.accuracy == 0.0
    assert result.invalid_outputs == 1


def test_evaluate_cases_counts_non_string_outputs_as_invalid():
    cases = load_eval_cases(Path("tests/fixtures/fingpt_eval_cases.jsonl"))[:1]

    result = evaluate_cases(cases, route="none-test", predictor=lambda case: None)
    assert result.total == 1
    assert result.correct == 0
    assert result.accuracy == 0.0
    assert result.invalid_outputs == 1
