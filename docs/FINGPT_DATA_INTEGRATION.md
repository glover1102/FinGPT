# FinGPT Data Integration

## Purpose

FinGPT integration is an optional augmentation layer for task-specific financial NLP signals. The core local research flow remains the default path: market data collection, retrieval, local inference, analysis, and report generation continue to work without FinGPT datasets or task adapters.

The `/api/v1/config` response exposes the integration state through a top-level `fingpt` object so the web UI and contract tests can report whether optional FinGPT paths are active.

## Default Behavior

The default behavior is `disabled_fail_open`.

By default:

- `fingpt_datasets_enabled` is `false`.
- `fingpt_task_model_enabled` is `false`.
- Dataset loading does not run during ordinary local startup.
- Task-model adapters are not required for the baseline qwen/gemma4 analysis paths.
- If optional FinGPT features are disabled or unavailable, the application continues through the standard analysis route.

This keeps offline workstation use reproducible and avoids making Hugging Face datasets or task-specific model adapters startup-critical.

## Config Surface

`GET /api/v1/config` includes:

```json
{
  "fingpt": {
    "datasets_enabled": false,
    "task_model_enabled": false,
    "task_model": "FinGPT/fingpt-mt_llama3-8b_lora",
    "tasks": ["sentiment", "headline", "ner", "relation", "fiqa_qa", "forecaster"],
    "default_behavior": "disabled_fail_open"
  }
}
```

The web UI renders this state near the inference route selector. When both optional switches are disabled it reports that the baseline analysis path is unaffected. When either switch is enabled it lists the available task families.

## Enabling Optional Paths

Set these values in `.env` when the workstation is prepared for optional FinGPT task data or model evaluation:

```env
FINGPT_DATASETS_ENABLED=true
FINGPT_DATASET_CACHE_DIR=data/fingpt_datasets
FINGPT_DATASET_MAX_ROWS=500
FINGPT_TASK_MODEL_ENABLED=true
FINGPT_TASK_MODEL_NAME=FinGPT/fingpt-mt_llama3-8b_lora
```

Use dataset paths only when the local environment has the required dataset dependencies and network/cache access. Use task-model paths only when the selected adapter and its runtime dependencies are installed and validated for the target hardware.

## Acceptance Criteria

- `/api/v1/config` returns a top-level `fingpt` object.
- The object includes dataset and task-model enablement booleans, task-model name, the task list, and `default_behavior`.
- The web UI contains `id="fingptStatus"`.
- The UI renders a disabled/fail-open message when config fetch fails or optional paths are disabled.
- The UI toggles `is-enabled` when either optional FinGPT path is active.
- Existing qwen/gemma4 model selection behavior is unchanged.

## Verification

Run the focused contract tests:

```powershell
.\venv311\Scripts\python.exe -m pytest tests\test_api_routing_contract.py tests\test_ui_routing_contract.py -q
```
