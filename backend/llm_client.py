"""
Centralised LLM and embedding client factory.

Uses Ollama's OpenAI-compatible API so all agents can use the same
AsyncOpenAI client pointed at the local Ollama server.

Embeddings use sentence-transformers locally (no network required).
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import structlog

from backend.config import settings

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM client (Ollama via OpenAI-compatible API)
# ---------------------------------------------------------------------------

def get_llm_client():
    """Return an AsyncOpenAI client pointed at the local Ollama server."""
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        base_url=f"{settings.ollama_base_url}/v1",
        api_key="ollama",          # Ollama ignores the key but the client requires one
        timeout=120.0,             # llama3.1:8b can take up to 2 minutes on first load
    )


def get_model_name() -> str:
    """Return the configured Ollama model name."""
    return settings.ollama_model


# ---------------------------------------------------------------------------
# Embedding client (sentence-transformers, runs fully locally)
# ---------------------------------------------------------------------------

_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"   # 22 MB, fast, 384-dim, no internet needed
_embed_model = None
_embed_lock = asyncio.Lock()


def _load_embed_model():
    """Load the sentence-transformers model (lazy, cached)."""
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            log.info("embedding_model.loading", model=_EMBED_MODEL_NAME)
            _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
            log.info("embedding_model.loaded", model=_EMBED_MODEL_NAME)
        except Exception as exc:
            log.error("embedding_model.load_failed", error=str(exc))
            raise
    return _embed_model


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using sentence-transformers (runs in thread pool)."""
    loop = asyncio.get_event_loop()

    def _encode():
        model = _load_embed_model()
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()

    return await loop.run_in_executor(None, _encode)


async def embed_text(text: str) -> list[float]:
    """Embed a single text string."""
    results = await embed_texts([text])
    return results[0]


# ---------------------------------------------------------------------------
# Convenience: chat completion with the local model
# ---------------------------------------------------------------------------

async def chat_complete(
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> str:
    """Run a chat completion against the local Ollama model.

    Args:
        messages:    List of {role, content} dicts.
        temperature: Sampling temperature.
        max_tokens:  Maximum tokens to generate.
        json_mode:   If True, instruct the model to respond with JSON.

    Returns:
        The assistant's response text.
    """
    client = get_llm_client()
    model = get_model_name()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Ollama supports json format via response_format
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as exc:
        log.error("chat_complete.failed", model=model, error=str(exc))
        raise
