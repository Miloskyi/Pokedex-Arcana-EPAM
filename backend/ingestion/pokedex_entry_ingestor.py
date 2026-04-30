"""
Pokédex entry ingestor: extracts flavor text from PokéAPI for each Pokémon,
embeds with OpenAI text-embedding-3-small, and upserts into ChromaDB
"pokedex_entries" collection.

Metadata per chunk: {pokemon_name, game_version, generation}
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

import chromadb

from backend.config import settings
from backend.llm_client import embed_texts
from backend.ingestion.pokeapi_ingestor import (
    POKEAPI_BASE,
    TOTAL_POKEMON,
    PAGE_SIZE,
    _generation_from_id,
    _is_retryable,
)

log = structlog.get_logger(__name__)

COLLECTION_NAME = "pokedex_entries"
EMBED_BATCH = 100


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    resp = await client.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _extract_flavor_texts(species_data: dict[str, Any]) -> list[dict[str, str]]:
    """Return list of {text, version} dicts from species flavor text entries."""
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for entry in species_data.get("flavor_text_entries", []):
        if entry.get("language", {}).get("name") != "en":
            continue
        text = entry["flavor_text"].replace("\n", " ").replace("\f", " ").strip()
        version = entry.get("version", {}).get("name", "unknown")
        key = f"{version}:{text}"
        if key not in seen:
            seen.add(key)
            entries.append({"text": text, "version": version})
    return entries


async def ingest_pokedex_entries() -> None:
    """Fetch Pokédex flavor texts from PokéAPI and upsert into ChromaDB."""
    log.info("pokedex_entry_ingestor.start")

    chroma_client = await chromadb.AsyncHttpClient(
        host=settings.chromadb_host, port=settings.chromadb_port
    )
    collection = await chroma_client.get_or_create_collection(COLLECTION_NAME)

    async with httpx.AsyncClient() as http:
        # 1. Collect all Pokémon slugs and IDs via pagination
        pokemon_list: list[dict[str, Any]] = []
        offset = 0
        while offset < TOTAL_POKEMON:
            page = await _get(
                http,
                f"{POKEAPI_BASE}/pokemon?limit={PAGE_SIZE}&offset={offset}",
            )
            for item in page["results"]:
                # Extract ID from URL
                pk_id = int(item["url"].rstrip("/").split("/")[-1])
                pokemon_list.append({"name": item["name"], "id": pk_id})
            offset += PAGE_SIZE

        pokemon_list = pokemon_list[:TOTAL_POKEMON]
        log.info("pokedex_entry_ingestor.pokemon_list", count=len(pokemon_list))

        # 2. Fetch species data in batches
        batch_size = 20
        all_docs: list[str] = []
        all_metadatas: list[dict] = []

        for i in range(0, len(pokemon_list), batch_size):
            batch = pokemon_list[i : i + batch_size]
            species_urls = [
                f"{POKEAPI_BASE}/pokemon-species/{p['id']}" for p in batch
            ]
            results = await asyncio.gather(
                *[_get(http, url) for url in species_urls],
                return_exceptions=True,
            )
            for pokemon, res in zip(batch, results):
                if isinstance(res, Exception):
                    log.warning(
                        "pokedex_entry_ingestor.species_error",
                        pokemon=pokemon["name"],
                        error=str(res),
                    )
                    continue
                generation = _generation_from_id(pokemon["id"])
                for entry in _extract_flavor_texts(res):
                    all_docs.append(entry["text"])
                    all_metadatas.append(
                        {
                            "pokemon_name": pokemon["name"],
                            "game_version": entry["version"],
                            "generation": str(generation),
                        }
                    )

    log.info("pokedex_entry_ingestor.entries_collected", count=len(all_docs))

    if not all_docs:
        log.warning("pokedex_entry_ingestor.no_entries")
        return

    # 3. Embed in batches and upsert using local sentence-transformers
    all_embeddings: list[list[float]] = []
    for i in range(0, len(all_docs), EMBED_BATCH):
        batch = all_docs[i : i + EMBED_BATCH]
        try:
            embeddings = await embed_texts(batch)
            all_embeddings.extend(embeddings)
        except Exception as exc:
            log.error(
                "pokedex_entry_ingestor.embed_failed",
                batch_start=i,
                error=str(exc),
            )
            # Pad with zeros to keep index alignment (384-dim for all-MiniLM-L6-v2)
            all_embeddings.extend([[0.0] * 384] * len(batch))

    ids = [
        hashlib.sha256(
            f"{meta['pokemon_name']}:{meta['game_version']}:{doc[:64]}".encode()
        ).hexdigest()
        for doc, meta in zip(all_docs, all_metadatas)
    ]

    # Upsert in batches to avoid oversized requests
    upsert_batch = 500
    for i in range(0, len(ids), upsert_batch):
        await collection.upsert(
            ids=ids[i : i + upsert_batch],
            embeddings=all_embeddings[i : i + upsert_batch],
            documents=all_docs[i : i + upsert_batch],
            metadatas=all_metadatas[i : i + upsert_batch],
        )

    log.info("pokedex_entry_ingestor.done", total_upserted=len(ids))
