"""Admin API router — observability dashboard data."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin")


@router.get("/observability")
async def get_observability(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return observability dashboard data with computed metrics."""
    try:
        traces = await _query_traces(limit=limit, offset=offset)
        total_count = await _count_traces()
    except Exception as exc:
        logger.error("observability_query_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Failed to query traces") from exc

    # Compute summary metrics from the returned traces
    latencies = [t["total_latency_ms"] for t in traces if t["total_latency_ms"] is not None]
    tokens = [t["token_count"] for t in traces if t["token_count"] is not None]
    slow_queries = sum(1 for l in latencies if l > 10_000)

    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0
    total_tokens = sum(tokens)

    # Agent invocation counts
    agent_counts: Counter = Counter()
    agent_latencies: dict[str, list[int]] = defaultdict(list)
    for t in traces:
        spans = t.get("agent_spans") or {}
        if isinstance(spans, dict):
            for agent_name in spans:
                agent_counts[agent_name] += 1
                lat = spans[agent_name].get("latency_ms", 0) if isinstance(spans[agent_name], dict) else 0
                agent_latencies[agent_name].append(lat)

    agent_stats = [
        {
            "agent": name,
            "calls": count,
            "avg_latency_ms": round(
                sum(agent_latencies[name]) / len(agent_latencies[name])
            ) if agent_latencies[name] else 0,
        }
        for name, count in agent_counts.most_common()
    ]

    return {
        "traces": traces,
        "limit": limit,
        "offset": offset,
        "count": len(traces),
        # Summary metrics expected by the frontend dashboard
        "total_queries": total_count,
        "avg_latency_ms": avg_latency,
        "total_tokens": total_tokens,
        "slow_queries": slow_queries,
        "agent_stats": agent_stats,
    }


async def _count_traces() -> int:
    """Return total number of query traces."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from backend.config import settings
    from backend.models.ragas import QueryTrace

    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(select(func.count()).select_from(QueryTrace))
        count = result.scalar_one()

    await engine.dispose()
    return count


async def _query_traces(limit: int, offset: int) -> list[dict[str, Any]]:
    """Query the query_traces table via SQLAlchemy async."""
    from sqlalchemy import select, desc
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from backend.config import settings
    from backend.models.ragas import QueryTrace

    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        stmt = (
            select(QueryTrace)
            .order_by(desc(QueryTrace.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    await engine.dispose()

    return [
        {
            "id": str(row.id),
            "session_id": str(row.session_id) if row.session_id else None,
            "query_text": row.query_text,
            "total_latency_ms": row.total_latency_ms,
            "slowest_agent": row.slowest_agent,
            "agent_spans": row.agent_spans,
            "token_count": row.token_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
