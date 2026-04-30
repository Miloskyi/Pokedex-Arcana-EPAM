"""
Bulbapedia ingestor: scrapes Bulbapedia pages for each Pokémon, chunks text
with RecursiveCharacterTextSplitter (size=512, overlap=64), embeds with
OpenAI text-embedding-3-small, and upserts into ChromaDB "bulbapedia" collection.

Metadata per chunk: {pokemon_name, page_title, url}
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

import chromadb

from backend.config import settings
from backend.llm_client import embed_texts

log = structlog.get_logger(__name__)

BULBAPEDIA_BASE = "https://bulbapedia.bulbagarden.net/wiki"
COLLECTION_NAME = "bulbapedia"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
EMBED_BATCH = 50


# ---------------------------------------------------------------------------
# Simple recursive character text splitter
# ---------------------------------------------------------------------------

def _split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text recursively on paragraph/sentence/word boundaries."""
    separators = ["\n\n", "\n", ". ", " ", ""]
    return _recursive_split(text, separators, size, overlap)


def _recursive_split(text: str, separators: list[str], size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text] if text.strip() else []

    sep = separators[0] if separators else ""
    remaining_seps = separators[1:]

    parts = text.split(sep) if sep else list(text)
    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = (current + sep + part) if current else part
        if len(candidate) <= size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(part) > size and remaining_seps:
                chunks.extend(_recursive_split(part, remaining_seps, size, overlap))
                current = ""
            else:
                current = part

    if current:
        chunks.append(current)

    # Apply overlap: prepend tail of previous chunk
    if overlap > 0 and len(chunks) > 1:
        overlapped: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            tail = chunks[i - 1][-overlap:]
            overlapped.append(tail + chunks[i])
        return [c for c in overlapped if c.strip()]

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

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
async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(url, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _extract_text(html: str) -> tuple[str, str]:
    """Return (page_title, plain_text) from Bulbapedia HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("h1", id="firstHeading")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown"

    content_div = soup.find("div", id="mw-content-text")
    if content_div is None:
        return title, ""

    # Remove navigation, tables of contents, infoboxes
    for tag in content_div.find_all(["table", "div"], class_=["toc", "navbox", "infobox"]):
        tag.decompose()

    return title, content_div.get_text(separator="\n", strip=True)


async def ingest_bulbapedia(pokemon_names: list[str] | None = None) -> None:
    """Scrape Bulbapedia pages and upsert chunks into ChromaDB."""
    if pokemon_names is None:
        # Default sample list — in production, read from DB
        pokemon_names = _default_pokemon_list()

    log.info("bulbapedia_ingestor.start", count=len(pokemon_names))

    chroma_client = await chromadb.AsyncHttpClient(
        host=settings.chromadb_host, port=settings.chromadb_port
    )
    collection = await chroma_client.get_or_create_collection(COLLECTION_NAME)

    async with httpx.AsyncClient(headers={"User-Agent": "PokedexArcana/1.0"}) as http:
        for pokemon_name in pokemon_names:
            url = f"{BULBAPEDIA_BASE}/{pokemon_name.capitalize()}_(Pokémon)"
            try:
                html = await _fetch_page(http, url)
            except Exception as exc:
                log.warning(
                    "bulbapedia_ingestor.fetch_failed",
                    pokemon=pokemon_name,
                    error=str(exc),
                )
                continue

            page_title, text = _extract_text(html)
            if not text.strip():
                log.warning("bulbapedia_ingestor.empty_page", pokemon=pokemon_name)
                continue

            chunks = _split_text(text)
            if not chunks:
                continue

            # Embed in batches using local sentence-transformers
            all_embeddings: list[list[float]] = []
            for i in range(0, len(chunks), EMBED_BATCH):
                batch = chunks[i : i + EMBED_BATCH]
                try:
                    embeddings = await embed_texts(batch)
                    all_embeddings.extend(embeddings)
                except Exception as exc:
                    log.warning(
                        "bulbapedia_ingestor.embed_failed",
                        pokemon=pokemon_name,
                        error=str(exc),
                    )
                    break

            if len(all_embeddings) != len(chunks):
                continue

            # Build IDs and metadata
            ids = [
                hashlib.sha256(f"{pokemon_name}:{i}:{chunk[:64]}".encode()).hexdigest()
                for i, chunk in enumerate(chunks)
            ]
            metadatas = [
                {"pokemon_name": pokemon_name, "page_title": page_title, "url": url}
                for _ in chunks
            ]

            await collection.upsert(
                ids=ids,
                embeddings=all_embeddings,
                documents=chunks,
                metadatas=metadatas,
            )
            log.info(
                "bulbapedia_ingestor.upserted",
                pokemon=pokemon_name,
                chunks=len(chunks),
            )

    log.info("bulbapedia_ingestor.done")


def _default_pokemon_list() -> list[str]:
    """Return a representative sample of Pokémon names."""
    return [
        "Bulbasaur", "Charmander", "Squirtle", "Pikachu", "Mewtwo",
        "Mew", "Chikorita", "Cyndaquil", "Totodile", "Lugia",
        "Ho-Oh", "Treecko", "Torchic", "Mudkip", "Rayquaza",
        "Turtwig", "Chimchar", "Piplup", "Dialga", "Palkia",
        "Snivy", "Tepig", "Oshawott", "Reshiram", "Zekrom",
        "Chespin", "Fennekin", "Froakie", "Xerneas", "Yveltal",
        "Rowlet", "Litten", "Popplio", "Solgaleo", "Lunala",
        "Grookey", "Scorbunny", "Sobble", "Zacian", "Zamazenta",
        "Sprigatito", "Fuecoco", "Quaxly", "Koraidon", "Miraidon",
    ]
