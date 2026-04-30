"""REST API router.

Endpoints:
  GET  /health          — liveness check
  GET  /reports/{id}    — PDF download
  POST /ingest          — trigger collection ingestion

Requirements: 7.2, 13.2
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict:
    """Liveness probe — returns 200 OK with service status."""
    return {"status": "ok", "service": "pokedex-arcana"}


# ---------------------------------------------------------------------------
# PDF report download
# ---------------------------------------------------------------------------


@router.get("/reports/{report_id}")
async def get_report(report_id: str) -> Response:
    """Download a previously generated PDF report by ID.

    The report must have been generated via the Celery task
    `generate_pdf_report` which stores the PDF bytes in Redis
    under key `report:{report_id}`.
    """
    import redis as redis_lib

    try:
        r = redis_lib.from_url(settings.redis_url)
        pdf_bytes = r.get(f"report:{report_id}")
    except Exception as exc:
        logger.error("report_redis_error", report_id=report_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Storage unavailable") from exc

    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report-{report_id}.pdf"'
        },
    )


# ---------------------------------------------------------------------------
# Ingest trigger
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    collection: str  # bulbapedia | pdf_guides | pokedex_entries


@router.post("/ingest", status_code=202)
async def trigger_ingest(body: IngestRequest) -> dict:
    """Trigger async ingestion for a ChromaDB collection via Celery.

    Accepted collection names: bulbapedia, pdf_guides, pokedex_entries.
    Returns 202 Accepted with the Celery task ID.
    """
    valid_collections = {"bulbapedia", "pdf_guides", "pokedex_entries"}
    if body.collection not in valid_collections:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection '{body.collection}'. "
                   f"Valid options: {sorted(valid_collections)}",
        )

    try:
        from backend.workers.celery_app import async_ingest_collection
        task = async_ingest_collection.delay(body.collection)
        logger.info("ingest_triggered", collection=body.collection, task_id=task.id)
        return {"status": "accepted", "task_id": task.id, "collection": body.collection}
    except Exception as exc:
        logger.error("ingest_trigger_failed", collection=body.collection, error=str(exc))
        raise HTTPException(status_code=503, detail="Failed to enqueue ingestion task") from exc
