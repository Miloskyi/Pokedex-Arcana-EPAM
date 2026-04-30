"""
Bootstrap orchestrator: runs all ingestors in dependency order.

Dependency order:
  1. pokeapi_ingestor  — populates PostgreSQL (pokemon, types, stats, abilities, chains)
  2. kaggle_ingestor   — enriches pokemon_stats from CSV (depends on pokemon rows existing)
  3. bulbapedia_ingestor — ChromaDB "bulbapedia" (independent of PG, but logically after)
  4. pdf_ingestor        — ChromaDB "pdf_guides" (independent)
  5. pokedex_entry_ingestor — ChromaDB "pokedex_entries" (needs PokéAPI, independent of PG)

Exposes run_bootstrap() which is called at application startup.
"""
from __future__ import annotations

import asyncio

import structlog

log = structlog.get_logger(__name__)


async def run_bootstrap() -> None:
    """Orchestrate all ingestors in dependency order.

    Each ingestor is idempotent (upsert semantics), so re-running is safe.
    Failures in one ingestor are logged but do not abort subsequent ingestors.
    """
    log.info("bootstrap.start")

    steps = [
        ("pokeapi", _run_pokeapi),
        ("kaggle", _run_kaggle),
        ("bulbapedia", _run_bulbapedia),
        ("pdf", _run_pdf),
        ("pokedex_entries", _run_pokedex_entries),
    ]

    for name, coro_fn in steps:
        log.info("bootstrap.step_start", step=name)
        try:
            await coro_fn()
            log.info("bootstrap.step_done", step=name)
        except Exception as exc:
            log.error("bootstrap.step_failed", step=name, error=str(exc))
            # Continue with remaining steps — partial ingestion is better than none

    log.info("bootstrap.done")


# ---------------------------------------------------------------------------
# Individual step wrappers (lazy imports to avoid circular deps at module load)
# ---------------------------------------------------------------------------

async def _run_pokeapi() -> None:
    from backend.ingestion.pokeapi_ingestor import ingest_pokeapi
    await ingest_pokeapi()


async def _run_kaggle() -> None:
    from backend.ingestion.kaggle_ingestor import ingest_kaggle
    await ingest_kaggle()


async def _run_bulbapedia() -> None:
    from backend.ingestion.bulbapedia_ingestor import ingest_bulbapedia
    await ingest_bulbapedia()


async def _run_pdf() -> None:
    from backend.ingestion.pdf_ingestor import ingest_pdfs
    await ingest_pdfs()


async def _run_pokedex_entries() -> None:
    from backend.ingestion.pokedex_entry_ingestor import ingest_pokedex_entries
    await ingest_pokedex_entries()


# ---------------------------------------------------------------------------
# Synchronous entry point (for Celery tasks or direct invocation)
# ---------------------------------------------------------------------------

def run_bootstrap_sync() -> None:
    """Synchronous wrapper around run_bootstrap() for use in Celery tasks."""
    asyncio.run(run_bootstrap())


if __name__ == "__main__":
    asyncio.run(run_bootstrap())
