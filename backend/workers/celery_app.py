"""Celery application definition and task registration.

Broker: Redis (settings.celery_broker_url)
Backend: Redis (settings.celery_result_backend)

Registered tasks:
  - flush_session_to_postgres
  - async_ingest_collection
  - generate_pdf_report

Retry policy: autoretry_for=(Exception,), max_retries=3, countdown=5
This covers PostgreSQL-unavailable scenarios where the task should be
retried after a short delay.

Requirements: 14.1
"""
from __future__ import annotations

import asyncio

from celery import Celery

from backend.config import settings

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

celery_app = Celery(
    "pokedex_arcana",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Retry policy defaults applied per-task via autoretry_for
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@celery_app.task(
    name="workers.flush_session_to_postgres",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def flush_session_to_postgres(self, session_id: str, user_id: str | None = None) -> dict:
    """Flush a session's Redis buffer to PostgreSQL.

    Retries up to 3 times with a 5-second delay on any exception,
    covering PostgreSQL-unavailable scenarios.
    """
    async def _flush() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from backend.memory.buffer import ConversationBuffer
        from backend.memory.entity import EntityMemory
        from backend.memory.episodic import EpisodicMemory
        from backend.memory.manager import MemoryManager

        db_url = settings.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

        engine = create_async_engine(db_url, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        buffer = ConversationBuffer()
        entity = EntityMemory()
        episodic = EpisodicMemory(session_factory=session_factory)
        manager = MemoryManager(buffer=buffer, entity=entity, episodic=episodic)
        await manager.flush_session(session_id=session_id, user_id=user_id)
        await engine.dispose()

    asyncio.run(_flush())
    return {"status": "flushed", "session_id": session_id}


@celery_app.task(
    name="workers.async_ingest_collection",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def async_ingest_collection(self, collection_name: str) -> dict:
    """Trigger ingestion for a specific ChromaDB collection.

    Supported collection names: bulbapedia, pdf_guides, pokedex_entries.
    Retries up to 3 times on failure.
    """
    async def _ingest() -> None:
        if collection_name == "bulbapedia":
            from backend.ingestion.bulbapedia_ingestor import ingest_bulbapedia
            await ingest_bulbapedia()
        elif collection_name == "pdf_guides":
            from backend.ingestion.pdf_ingestor import ingest_pdfs
            await ingest_pdfs()
        elif collection_name == "pokedex_entries":
            from backend.ingestion.pokedex_entry_ingestor import ingest_pokedex_entries
            await ingest_pokedex_entries()
        else:
            raise ValueError(f"Unknown collection: {collection_name}")

    asyncio.run(_ingest())
    return {"status": "ingested", "collection": collection_name}


@celery_app.task(
    name="workers.generate_pdf_report",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def generate_pdf_report(self, pokemon_name: str, report_id: str) -> dict:
    """Generate a PDF report for a Pokémon and store it.

    The report_id is used as a key to store the resulting PDF bytes
    in Redis so it can be retrieved via GET /reports/{id}.

    Retries up to 3 times on failure.
    """
    import redis as redis_lib

    async def _generate() -> bytes:
        from backend.agents.report_agent import ReportAgent
        agent = ReportAgent()
        result = await agent.run(pokemon_name, include_pdf=True)
        return result.pdf_bytes or b""

    pdf_bytes = asyncio.run(_generate())

    # Store in Redis with a 1-hour TTL
    r = redis_lib.from_url(settings.redis_url)
    r.setex(f"report:{report_id}", 3600, pdf_bytes)

    return {"status": "generated", "report_id": report_id, "size_bytes": len(pdf_bytes)}
