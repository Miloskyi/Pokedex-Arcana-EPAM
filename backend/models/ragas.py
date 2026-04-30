"""
SQLAlchemy 2.0 ORM models for RAGAS evaluation and observability.

Tables: ragas_evaluations, query_traces
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, func, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

TIMESTAMPTZ = DateTime(timezone=True)

from .base import Base


class RagasEvaluation(Base):
    __tablename__ = "ragas_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )
    system_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    query_id: Mapped[str] = mapped_column(String(100), nullable=False)
    query_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    faithfulness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_precision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_recall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Generated column: BOOLEAN GENERATED ALWAYS AS (all metrics >= 0.70) STORED
    passed_threshold: Mapped[Optional[bool]] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RagasEvaluation id={self.id} query_id={self.query_id!r}"
            f" category={self.query_category!r} passed={self.passed_threshold}>"
        )


class QueryTrace(Base):
    __tablename__ = "query_traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )
    query_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    slowest_agent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    agent_spans: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )

    session: Mapped[Optional["Session"]] = relationship(  # type: ignore[name-defined]
        "Session", back_populates="query_traces"
    )

    def __repr__(self) -> str:
        return (
            f"<QueryTrace id={self.id} session_id={self.session_id}"
            f" latency_ms={self.total_latency_ms}>"
        )

