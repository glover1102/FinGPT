# Provider Version Policy

## Purpose

FinGPT now treats provider compatibility as an operational gate, not a best-effort note. The project depends on OpenBB/Yahoo/FRED/SEC/Qdrant/FastAPI contracts remaining stable enough for local research runs, OpenBB Workspace agent streaming, and validation artifacts.

## Policy

- OpenBB core and connector packages are pinned by tested minor range.
- `openbb-ai` and `sse-starlette` are optional. Missing or drifting versions are warnings because the OpenBB Workspace adapter has a manual FastAPI SSE fallback.
- `openbb`, `openbb-core`, `openbb-news`, `openbb-yfinance`, `yfinance`, `fastapi`, `pydantic`, and `qdrant-client` are critical. Critical drift fails the validation gate.
- FMP stays auxiliary. FMP connector drift is warning-level unless the code path is explicitly promoted again.

## Current Tested Ranges

| Package | Range | Critical |
| --- | --- | --- |
| `openbb` | `>=4.7.0,<4.8.0` | yes |
| `openbb-core` | `>=1.6.0,<1.7.0` | yes |
| `openbb-news` | `>=1.6.0,<1.7.0` | yes |
| `openbb-yfinance` | `>=1.6.0,<1.7.0` | yes |
| `openbb-fred` | `>=1.6.0,<1.7.0` | no |
| `openbb-sec` | `>=1.6.0,<1.7.0` | no |
| `openbb-fmp` | `>=1.6.0,<1.7.0` | no |
| `openbb-ai` | `>=1.10.0,<1.11.0` | no |
| `sse-starlette` | `>=3.0.0,<4.0.0` | no |
| `yfinance` | `>=0.2.0,<2.0.0` | yes |
| `fastapi` | `>=0.110.0,<1.0.0` | yes |
| `pydantic` | `>=2.7.0,<3.0.0` | yes |
| `qdrant-client` | `>=1.8.0,<2.0.0` | yes |

## Commands

```powershell
python .\scripts\check_provider_versions.py
python .\scripts\validation_gate.py
```

The validation gate includes this check before live provider/API smokes so dependency drift is caught early.
