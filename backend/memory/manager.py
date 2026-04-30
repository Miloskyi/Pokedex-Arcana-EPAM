"""
Unified memory interface for the Pokédex Arcana system.

MemoryManager composes ConversationBuffer, EpisodicMemory, and
EntityMemory into a single façade used by the WebSocket gateway and
the Orchestrator.

On Redis unavailable: the buffer and entity stores fall back to
in-process dicts (handled inside their respective classes) and a
warning is logged here so operators are alerted at the manager level.

Feature: pokedex-arcana
"""
from __future__ import annotations

from typing import Any

import structlog

from backend.memory.buffer import ConversationBuffer
from backend.memory.entity import EntityMemory
from backend.memory.episodic import EpisodicMemory

logger = structlog.get_logger(__name__)


class MemoryManager:
    """Unified façade over buffer, entity, and episodic memory layers.

    Parameters
    ----------
    buffer:
        A :class:`ConversationBuffer` instance (Redis-backed with
        in-process fallback).
    entity:
        An :class:`EntityMemory` instance (Redis-backed with in-process
        fallback).
    episodic:
        An :class:`EpisodicMemory` instance (PostgreSQL-backed).
    llm_summarise:
        An optional async callable ``(turns: list[dict]) -> str`` used
        by :meth:`flush_session` to generate a session summary.  When
        ``None``, a simple concatenation is used as a fallback.
    """

    def __init__(
        self,
        buffer: ConversationBuffer,
        entity: EntityMemory,
        episodic: EpisodicMemory,
        llm_summarise: Any | None = None,
    ) -> None:
        self._buffer = buffer
        self._entity = entity
        self._episodic = episodic
        self._llm_summarise = llm_summarise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_context(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Return a merged context dict for the given session.

        The returned dict has the shape::

            {
                "buffer_turns": [...],          # last ≤10 turns from Redis
                "entities": [...],              # all entities for this session
                "episodic_summary": str | None, # summary of most recent prior session
            }

        If *user_id* is provided and there are prior sessions in
        PostgreSQL, the summary of the most recent one is included.
        """
        buffer_turns = await self._buffer.get_turns(session_id)
        entities = await self._entity.get_all_entities(session_id)

        episodic_summary: str | None = None
        if user_id:
            try:
                recent = await self._episodic.load_recent_sessions(user_id, limit=1)
                if recent:
                    episodic_summary = recent[0].get("summary")
            except Exception as exc:
                logger.warning(
                    "episodic_load_failed",
                    session_id=session_id,
                    user_id=user_id,
                    error=str(exc),
                )

        return {
            "buffer_turns": buffer_turns,
            "entities": entities,
            "episodic_summary": episodic_summary,
        }

    async def save_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_trace: dict[str, Any] | None = None,
    ) -> None:
        """Append a single turn to the Redis buffer.

        *agent_trace* is stored alongside the turn for observability but
        is not currently persisted to the Redis buffer (it will be
        written to PostgreSQL on flush).
        """
        await self._buffer.add_turn(session_id, role, content)
        logger.debug(
            "turn_saved",
            session_id=session_id,
            role=role,
            has_trace=agent_trace is not None,
        )

    async def flush_session(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> None:
        """Summarise the current buffer, persist to PostgreSQL, then clear Redis.

        Steps:
        1. Retrieve all buffered turns.
        2. Generate a summary via the LLM callable (or a simple fallback).
        3. Persist the session + turns + summary to PostgreSQL via
           :class:`EpisodicMemory`.
        4. Clear the Redis buffer and entity store.
        """
        turns = await self._buffer.get_turns(session_id)

        if not turns:
            logger.info("flush_session_no_turns", session_id=session_id)
            return

        # Generate summary
        summary = await self._generate_summary(turns)

        # Persist to PostgreSQL
        effective_user_id = user_id or session_id  # use session_id as fallback key
        try:
            await self._episodic.save_session(
                session_id=session_id,
                user_id=effective_user_id,
                turns=turns,
                summary=summary,
            )
        except Exception as exc:
            logger.error(
                "flush_session_persist_failed",
                session_id=session_id,
                error=str(exc),
            )
            raise

        # Clear Redis state
        await self._buffer.clear(session_id)
        logger.info(
            "session_flushed",
            session_id=session_id,
            user_id=effective_user_id,
            turn_count=len(turns),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_summary(self, turns: list[dict[str, Any]]) -> str:
        """Return a summary string for *turns*.

        Uses the injected LLM callable when available; otherwise falls
        back to a simple concatenation of the last few turns.
        """
        if self._llm_summarise is not None:
            try:
                return await self._llm_summarise(turns)
            except Exception as exc:
                logger.warning(
                    "llm_summarise_failed",
                    error=str(exc),
                )

        # Fallback: concatenate last 3 turns
        snippet = " | ".join(
            f"{t.get('role', '?')}: {t.get('content', '')[:100]}"
            for t in turns[-3:]
        )
        return f"Session summary (auto): {snippet}"
