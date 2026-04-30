"""
SQLAlchemy 2.0 ORM models for conversational memory.

Tables: sessions, session_turns, entity_memory
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import ForeignKey, Integer, SmallInteger, String, Text, func, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

TIMESTAMPTZ = DateTime(timezone=True)

from .base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    turns: Mapped[list["SessionTurn"]] = relationship(
        "SessionTurn", back_populates="session", order_by="SessionTurn.turn_index"
    )
    entities: Mapped[list["EntityMemory"]] = relationship(
        "EntityMemory", back_populates="session"
    )
    query_traces: Mapped[list["QueryTrace"]] = relationship(  # type: ignore[name-defined]
        "QueryTrace", back_populates="session"
    )

    def __repr__(self) -> str:
        return (
            f"<Session id={self.id} user_id={self.user_id!r}"
            f" started_at={self.started_at}>"
        )


class SessionTurn(Base):
    __tablename__ = "session_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )
    turn_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_trace: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )

    session: Mapped[Optional["Session"]] = relationship(
        "Session", back_populates="turns"
    )

    def __repr__(self) -> str:
        return (
            f"<SessionTurn id={self.id} session_id={self.session_id}"
            f" turn_index={self.turn_index} role={self.role!r}>"
        )


class EntityMemory(Base):
    __tablename__ = "entity_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )

    session: Mapped[Optional["Session"]] = relationship(
        "Session", back_populates="entities"
    )

    def __repr__(self) -> str:
        return (
            f"<EntityMemory id={self.id} session_id={self.session_id}"
            f" entity={self.entity_name!r} type={self.entity_type!r}>"
        )

