"""
Redis-backed sliding window conversation buffer.

Maintains the last 10 turns per session with a 2-hour TTL.
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

_BUFFER_MAX = 10
_TTL_SECONDS = 7200  # 2 hours

# In-process fallback: session_id -> list[dict]
_fallback: dict[str, list[dict[str, Any]]] = {}


def _buffer_key(session_id: str) -> str:
    return f"session:{session_id}:buffer"


class ConversationBuffer:
    """Sliding-window buffer of the last 10 conversation turns per session.

    Uses Redis as the primary store. If Redis is unavailable (connection
    error), falls back transparently to an in-process dict and logs a
    warning so operators are alerted.
    """

    def __init__(self, redis: "Redis | None" = None) -> None:
        self._redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Append a turn, trim to the last 10, and reset the 2-hour TTL."""
        turn = json.dumps({"role": role, "content": content})
        key = _buffer_key(session_id)

        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.rpush(key, turn)
                pipe.ltrim(key, -_BUFFER_MAX, -1)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return
            except Exception as exc:
                logger.warning(
                    "redis_unavailable_fallback",
                    operation="add_turn",
                    session_id=session_id,
                    error=str(exc),
                )

        # Fallback
        buf = _fallback.setdefault(session_id, [])
        buf.append({"role": role, "content": content})
        _fallback[session_id] = buf[-_BUFFER_MAX:]

    async def get_turns(self, session_id: str) -> list[dict[str, Any]]:
        """Return the buffered turns as a list of {role, content} dicts."""
        key = _buffer_key(session_id)

        if self._redis is not None:
            try:
                raw: list[bytes] = await self._redis.lrange(key, 0, -1)
                return [json.loads(item) for item in raw]
            except Exception as exc:
                logger.warning(
                    "redis_unavailable_fallback",
                    operation="get_turns",
                    session_id=session_id,
                    error=str(exc),
                )

        return list(_fallback.get(session_id, []))

    async def clear(self, session_id: str) -> None:
        """Delete the buffer for *session_id*."""
        key = _buffer_key(session_id)

        if self._redis is not None:
            try:
                await self._redis.delete(key)
                return
            except Exception as exc:
                logger.warning(
                    "redis_unavailable_fallback",
                    operation="clear",
                    session_id=session_id,
                    error=str(exc),
                )

        _fallback.pop(session_id, None)
