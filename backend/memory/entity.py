"""
Redis-backed entity memory for the current session.

Stores named entities (Pokémon, items, moves, strategies) mentioned
during a conversation so they can be resolved in follow-up turns
without the user re-specifying them.

Falls back to an in-process dict when Redis is unavailable.

Feature: pokedex-arcana
"""
from __future__ import annotations

import json
from typing import Any

import structlog

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore[assignment,misc]

logger = structlog.get_logger(__name__)

_TTL_SECONDS = 7200  # 2 hours

# In-process fallback: session_id -> {name -> entity_dict}
_fallback: dict[str, dict[str, dict[str, Any]]] = {}


def _entities_key(session_id: str) -> str:
    return f"session:{session_id}:entities"


class EntityMemory:
    """Per-session entity store backed by a Redis Hash.

    Each entity is stored as a JSON-encoded value in a Hash keyed by
    the entity name (case-preserved).  The Hash itself has a 2-hour TTL
    that is reset on every write.
    """

    def __init__(self, redis: "Redis | None" = None) -> None:
        self._redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store_entity(
        self,
        session_id: str,
        name: str,
        entity_type: str,
        context: str,
    ) -> None:
        """Upsert an entity into the session's entity store."""
        entity = json.dumps(
            {"name": name, "entity_type": entity_type, "context": context}
        )
        key = _entities_key(session_id)

        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.hset(key, name, entity)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return
            except Exception as exc:
                logger.warning(
                    "redis_unavailable_fallback",
                    operation="store_entity",
                    session_id=session_id,
                    error=str(exc),
                )

        # Fallback
        _fallback.setdefault(session_id, {})[name] = {
            "name": name,
            "entity_type": entity_type,
            "context": context,
        }

    async def resolve_entity(
        self, session_id: str, name: str
    ) -> dict[str, Any] | None:
        """Return the stored entity dict for *name*, or ``None`` if not found."""
        key = _entities_key(session_id)

        if self._redis is not None:
            try:
                raw = await self._redis.hget(key, name)
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception as exc:
                logger.warning(
                    "redis_unavailable_fallback",
                    operation="resolve_entity",
                    session_id=session_id,
                    error=str(exc),
                )

        return _fallback.get(session_id, {}).get(name)

    async def get_all_entities(self, session_id: str) -> list[dict[str, Any]]:
        """Return all entities stored for *session_id*."""
        key = _entities_key(session_id)

        if self._redis is not None:
            try:
                raw: dict[bytes, bytes] = await self._redis.hgetall(key)
                return [json.loads(v) for v in raw.values()]
            except Exception as exc:
                logger.warning(
                    "redis_unavailable_fallback",
                    operation="get_all_entities",
                    session_id=session_id,
                    error=str(exc),
                )

        return list(_fallback.get(session_id, {}).values())
