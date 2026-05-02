import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from core.schemas.request import AnalysisRequest
from core.schemas.response import AnalysisResponse
from core.config.settings import load_settings
from core.utils.logger import get_logger
from pipelines.collect.models import CollectionOutcome
from pipelines.output.run_history import archive_run

logger = get_logger("pipelines.output")


def _dataclass_list(items):
    return [asdict(item) if is_dataclass(item) else dict(item) for item in items]


def _collection_sidecar(request: Any, collection_outcome: CollectionOutcome) -> dict:
    return {
        "ticker": getattr(request, "ticker", None) or getattr(request, "theme", None) or "TOPIC",
        "lookback_days": request.lookback_days,
        "run_started_at": collection_outcome.run_started_at,
        "current_doc_ids": list(collection_outcome.current_doc_ids),
        "source_results": _dataclass_list(collection_outcome.source_results),
        "provider_results": _dataclass_list(collection_outcome.provider_results),
        "freshness_cutoff": collection_outcome.freshness_cutoff,
        "retrieval_policy": collection_outcome.retrieval_policy,
        "cache_hit": bool(getattr(collection_outcome, "cache_hit", False)),
        "cached_at": getattr(collection_outcome, "cached_at", "") or "",
        "cache_age_s": float(getattr(collection_outcome, "cache_age_s", 0.0) or 0.0),
    }


def save_outputs(
    request: Any,
    response: Any,
    report_md: str,
    report_html: str,
    *,
    collection_outcome: CollectionOutcome | None = None,
):
    settings = load_settings()
    out_dir = Path(request.output_dir) if request.output_dir else settings.outputs_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    request_json = request.model_dump_json(indent=2)
    response_json = response.model_dump_json(indent=2)
    collection_payload = (
        _collection_sidecar(request, collection_outcome) if collection_outcome is not None else None
    )

    try:
        (out_dir / "latest_request.json").write_text(request_json, encoding="utf-8")
        (out_dir / "latest_response.json").write_text(response_json, encoding="utf-8")
        (out_dir / "latest_report.md").write_text(report_md, encoding="utf-8")
        (out_dir / "latest_report.html").write_text(report_html, encoding="utf-8")

        if collection_payload is not None:
            (out_dir / "latest_collection.json").write_text(
                json.dumps(collection_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        logger.info(f"Outputs saved to {out_dir}")

        # Best-effort archival into runs/{ticker}/{timestamp}/. The live `latest_*`
        # files above remain authoritative for backwards compatibility.
        archive_run(
            outputs_dir=out_dir,
            request_json=request_json,
            response_json=response_json,
            report_md=report_md,
            report_html=report_html,
            collection_sidecar=collection_payload,
            ticker=(getattr(request, "ticker", None) or getattr(response, "theme", None) or "TOPIC"),
            question=request.question,
            status=response.status,
            sentiment=getattr(response, "sentiment", "Neutral"),
            confidence=getattr(response, "confidence", 0.0),
            model=request.model,
            lookback_days=request.lookback_days,
            top_k=request.top_k,
            sources=list(getattr(request, "sources", []) or []),
            error_metadata=response.error_metadata,
        )

    except Exception as e:
        logger.error(f"Failed to save outputs: {e}")
        raise
