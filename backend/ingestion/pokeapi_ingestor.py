"""
PokéAPI ingestor: fetches all 1025 Pokémon, normalises data, and upserts into
PostgreSQL tables: pokemon, pokemon_types, pokemon_stats, pokemon_abilities,
evolution_chains.

Uses httpx.AsyncClient for async HTTP and tenacity for exponential backoff
(3 retries) on 5xx / rate-limit responses.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import settings
from backend.models.base import make_engine, make_session_factory
from backend.models.pokemon import (
    EvolutionChain,
    Pokemon,
    PokemonAbility,
    PokemonStats,
    PokemonType,
)

log = structlog.get_logger(__name__)

POKEAPI_BASE = "https://pokeapi.co/api/v2"
TOTAL_POKEMON = 1025
PAGE_SIZE = 100


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


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


def _generation_from_id(pokeapi_id: int) -> int:
    """Map PokéAPI Pokémon ID to generation number."""
    thresholds = [151, 251, 386, 493, 649, 721, 809, 905, 1025]
    for gen, threshold in enumerate(thresholds, start=1):
        if pokeapi_id <= threshold:
            return gen
    return 9


def _parse_pokemon(data: dict[str, Any]) -> dict[str, Any]:
    """Extract normalised fields from a PokéAPI Pokémon response."""
    stats_map = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}
    return {
        "pokeapi_id": data["id"],
        "name": data["name"],
        "slug": data["name"],
        "generation": _generation_from_id(data["id"]),
        "is_legendary": data.get("is_legendary", False),
        "is_mythical": data.get("is_mythical", False),
        "types": [
            {"slot": t["slot"], "type_name": t["type"]["name"]}
            for t in data["types"]
        ],
        "stats": {
            "hp": stats_map.get("hp", 0),
            "attack": stats_map.get("attack", 0),
            "defense": stats_map.get("defense", 0),
            "sp_atk": stats_map.get("special-attack", 0),
            "sp_def": stats_map.get("special-defense", 0),
            "speed": stats_map.get("speed", 0),
        },
        "abilities": [
            {
                "ability_name": a["ability"]["name"],
                "is_hidden": a["is_hidden"],
                "slot": a["slot"],
            }
            for a in data["abilities"]
        ],
        "species_url": data["species"]["url"],
    }


def _walk_chain(chain_node: dict, chain_id: int, links: list[dict]) -> None:
    """Recursively walk an evolution chain node and collect (from, to) links."""
    for evolution in chain_node.get("evolves_to", []):
        trigger_detail = evolution["evolution_details"][0] if evolution["evolution_details"] else {}
        trigger = trigger_detail.get("trigger", {}).get("name") if trigger_detail else None
        condition: dict[str, Any] = {}
        if trigger_detail:
            for key, val in trigger_detail.items():
                if key == "trigger" or val is None or val == "" or val is False:
                    continue
                if isinstance(val, dict):
                    condition[key] = val.get("name", val)
                else:
                    condition[key] = val
        links.append(
            {
                "chain_id": chain_id,
                "from_name": chain_node["species"]["name"],
                "to_name": evolution["species"]["name"],
                "trigger": trigger,
                "condition_detail": condition or None,
            }
        )
        _walk_chain(evolution, chain_id, links)


async def _upsert_pokemon(session, parsed: dict[str, Any]) -> int:
    """Upsert a single Pokémon row and return its internal DB id."""
    stmt = (
        pg_insert(Pokemon)
        .values(
            pokeapi_id=parsed["pokeapi_id"],
            name=parsed["name"],
            slug=parsed["slug"],
            generation=parsed["generation"],
            is_legendary=parsed["is_legendary"],
            is_mythical=parsed["is_mythical"],
        )
        .on_conflict_do_update(
            index_elements=["pokeapi_id"],
            set_={
                "name": parsed["name"],
                "slug": parsed["slug"],
                "generation": parsed["generation"],
                "is_legendary": parsed["is_legendary"],
                "is_mythical": parsed["is_mythical"],
            },
        )
        .returning(Pokemon.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def _upsert_types(session, pokemon_id: int, types: list[dict]) -> None:
    for t in types:
        stmt = (
            pg_insert(PokemonType)
            .values(pokemon_id=pokemon_id, slot=t["slot"], type_name=t["type_name"])
            .on_conflict_do_update(
                index_elements=["pokemon_id", "slot"],
                set_={"type_name": t["type_name"]},
            )
        )
        await session.execute(stmt)


async def _upsert_stats(session, pokemon_id: int, stats: dict[str, int]) -> None:
    stmt = (
        pg_insert(PokemonStats)
        .values(pokemon_id=pokemon_id, **stats)
        .on_conflict_do_update(
            index_elements=["pokemon_id"],
            set_=stats,
        )
    )
    await session.execute(stmt)


async def _upsert_abilities(session, pokemon_id: int, abilities: list[dict]) -> None:
    for ab in abilities:
        stmt = (
            pg_insert(PokemonAbility)
            .values(pokemon_id=pokemon_id, **ab)
            .on_conflict_do_nothing()
        )
        await session.execute(stmt)


async def _upsert_evolution_links(
    session, links: list[dict], name_to_id: dict[str, int]
) -> None:
    for link in links:
        from_id = name_to_id.get(link["from_name"])
        to_id = name_to_id.get(link["to_name"])
        if from_id is None or to_id is None:
            continue
        stmt = (
            pg_insert(EvolutionChain)
            .values(
                chain_id=link["chain_id"],
                from_pokemon_id=from_id,
                to_pokemon_id=to_id,
                trigger=link["trigger"],
                condition_detail=link["condition_detail"],
            )
            .on_conflict_do_nothing()
        )
        await session.execute(stmt)


async def ingest_pokeapi() -> None:
    """Fetch all Pokémon from PokéAPI and upsert into PostgreSQL."""
    log.info("pokeapi_ingestor.start", total=TOTAL_POKEMON)
    engine = make_engine(settings.database_url, echo=False)
    session_factory = make_session_factory(engine)

    async with httpx.AsyncClient() as client:
        # 1. Collect all Pokémon URLs via pagination
        urls: list[str] = []
        offset = 0
        while offset < TOTAL_POKEMON:
            page = await _get(
                client,
                f"{POKEAPI_BASE}/pokemon?limit={PAGE_SIZE}&offset={offset}",
            )
            urls.extend(r["url"] for r in page["results"])
            offset += PAGE_SIZE

        urls = urls[:TOTAL_POKEMON]
        log.info("pokeapi_ingestor.urls_collected", count=len(urls))

        # 2. Fetch each Pokémon concurrently in batches of 20
        all_parsed: list[dict[str, Any]] = []
        batch_size = 20
        for i in range(0, len(urls), batch_size):
            batch = urls[i : i + batch_size]
            results = await asyncio.gather(
                *[_get(client, url) for url in batch], return_exceptions=True
            )
            for url, res in zip(batch, results):
                if isinstance(res, Exception):
                    log.warning("pokeapi_ingestor.fetch_error", url=url, error=str(res))
                    continue
                all_parsed.append(_parse_pokemon(res))

        log.info("pokeapi_ingestor.fetched", count=len(all_parsed))

        # 3. Upsert core Pokémon rows and collect name→id mapping
        name_to_id: dict[str, int] = {}
        async with session_factory() as session:
            for parsed in all_parsed:
                pk_id = await _upsert_pokemon(session, parsed)
                name_to_id[parsed["slug"]] = pk_id
                await _upsert_types(session, pk_id, parsed["types"])
                await _upsert_stats(session, pk_id, parsed["stats"])
                await _upsert_abilities(session, pk_id, parsed["abilities"])
            await session.commit()

        log.info("pokeapi_ingestor.pokemon_upserted", count=len(name_to_id))

        # 4. Fetch species data to get evolution chain URLs (deduplicated)
        species_urls = list({p["species_url"] for p in all_parsed})
        chain_urls: dict[int, str] = {}  # chain_id → chain URL
        for i in range(0, len(species_urls), batch_size):
            batch = species_urls[i : i + batch_size]
            results = await asyncio.gather(
                *[_get(client, url) for url in batch], return_exceptions=True
            )
            for url, res in zip(batch, results):
                if isinstance(res, Exception):
                    log.warning("pokeapi_ingestor.species_error", url=url, error=str(res))
                    continue
                chain_url = res.get("evolution_chain", {}).get("url")
                if chain_url:
                    chain_id = int(chain_url.rstrip("/").split("/")[-1])
                    chain_urls[chain_id] = chain_url

        # 5. Fetch evolution chains and upsert links
        all_links: list[dict] = []
        chain_items = list(chain_urls.items())
        for i in range(0, len(chain_items), batch_size):
            batch = chain_items[i : i + batch_size]
            results = await asyncio.gather(
                *[_get(client, url) for _, url in batch], return_exceptions=True
            )
            for (chain_id, url), res in zip(batch, results):
                if isinstance(res, Exception):
                    log.warning("pokeapi_ingestor.chain_error", url=url, error=str(res))
                    continue
                links: list[dict] = []
                _walk_chain(res["chain"], chain_id, links)
                all_links.extend(links)

        async with session_factory() as session:
            await _upsert_evolution_links(session, all_links, name_to_id)
            await session.commit()

        log.info("pokeapi_ingestor.evolution_links_upserted", count=len(all_links))

    await engine.dispose()
    log.info("pokeapi_ingestor.done")
