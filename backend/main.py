"""FastAPI application factory for Pokédex Arcana.

Lifespan:
  - startup: run bootstrap ingestion, initialize OTel, configure structlog
  - shutdown: graceful cleanup

Routers:
  - ws_gateway  (/ws/{session_id})
  - rest_router (/health, /reports/{id}, /ingest)
  - admin_router (/admin/observability)

Requirements: 14.4
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.observability.logging import configure_logging
from backend.observability.tracing import setup_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    # --- Startup ---
    # 1. Configure structured logging FIRST (before any logger calls)
    configure_logging(log_level=settings.log_level)

    # Now we can safely use structlog
    _logger = structlog.get_logger(__name__)
    _logger.info("startup.logging_configured", log_level=settings.log_level)

    # 2. Initialize OpenTelemetry
    try:
        setup_tracing(service_name="pokedex-arcana")
        _logger.info("startup.otel_initialized")
    except Exception as exc:
        _logger.warning("startup.otel_failed", error=str(exc))

    # 3. Run bootstrap ingestion (idempotent)
    # Skip bootstrap on restart if data already exists — run manually via POST /ingest
    _skip_bootstrap = True  # Set to False to force re-ingestion on startup
    if not _skip_bootstrap:
        try:
            from backend.ingestion.bootstrap import run_bootstrap
            _logger.info("startup.bootstrap_start")
            await run_bootstrap()
            _logger.info("startup.bootstrap_done")
        except Exception as exc:
            _logger.error("startup.bootstrap_failed", error=str(exc))
    else:
        _logger.info("startup.bootstrap_skipped", reason="data already ingested")

    _logger.info("startup.complete", host=settings.backend_host, port=settings.backend_port)

    yield

    # --- Shutdown ---
    _logger.info("shutdown.complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Pokédex Arcana",
        description="Multi-agent AI system for Pokémon queries",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow all origins in development; tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from backend.api.ws_gateway import router as ws_router
    from backend.api.rest_router import router as rest_router
    from backend.api.admin_router import router as admin_router

    app.include_router(ws_router)
    app.include_router(rest_router)
    app.include_router(admin_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
