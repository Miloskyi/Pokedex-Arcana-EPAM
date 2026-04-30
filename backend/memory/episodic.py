"""
PostgreSQL-backed episodic memory.

Persists completed sessions and retrieves the most recent N sessions
for a given user so the system can resume context across conversations.

Feature: pokedex-arcana
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.session import Session, SessionTurn

logger = structlog.get_logger(__name__)


class EpisodicMemory:
    """Persist and retrieve session-level episodic memory in PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save_session(
        self,
        session_id: str,
        user_id: str,
        turns: list[dict[str, Any]],
        summary: str,
    ) -> None:
        """Persist a completed session with its turns and summary.

        If a row for *session_id* already exists it is updated; otherwise
        a new row is inserted.  Each turn in *turns* is expected to be a
        dict with at least ``role`` and ``content`` keys.
        """
        sid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id

        async with self._factory() as db:
            # Upsert the session row
            existing = await db.get(Session, sid)
            if existing is None:
                session_row = Session(
                    id=sid,
                    user_id=user_id,
                    ended_at=datetime.now(tz=timezone.utc),
                    summary=summary,
                )
                db.add(session_row)
            else:
                existing.user_id = user_id
                existing.ended_at = datetime.now(tz=timezone.utc)
                existing.summary = summary

            # Persist turns
            for idx, turn in enumerate(turns):
                turn_row = SessionTurn(
                    session_id=sid,
                    turn_index=idx,
                    role=turn.get("role", "user"),
                    content=turn.get("content", ""),
                    agent_trace=turn.get("agent_trace"),
                )
                db.add(turn_row)

            await db.commit()
            logger.info("episodic_session_saved", session_id=str(sid), user_id=user_id)

    async def load_recent_sessions(
        self, user_id: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Return the *limit* most recent sessions for *user_id*, newest first.

        Each entry is a dict with keys: ``session_id``, ``started_at``,
        ``ended_at``, ``summary``, and ``turns`` (list of turn dicts).
        """
        async with self._factory() as db:
            stmt = (
                select(Session)
                .where(Session.user_id == user_id)
                .order_by(Session.started_at.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            sessions = result.scalars().all()

            output: list[dict[str, Any]] = []
            for s in sessions:
                # Eagerly load turns for this session
                turns_stmt = (
                    select(SessionTurn)
                    .where(SessionTurn.session_id == s.id)
                    .order_by(SessionTurn.turn_index)
                )
                turns_result = await db.execute(turns_stmt)
                turns = turns_result.scalars().all()

                output.append(
                    {
                        "session_id": str(s.id),
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                        "summary": s.summary,
                        "turns": [
                            {
                                "turn_index": t.turn_index,
                                "role": t.role,
                                "content": t.content,
                                "agent_trace": t.agent_trace,
                            }
                            for t in turns
                        ],
                    }
                )

            return output
