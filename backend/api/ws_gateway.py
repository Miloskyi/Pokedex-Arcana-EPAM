"""WebSocket Gateway — accepts connections at /ws/{session_id}.

Loads session context from MemoryManager, dispatches to Orchestrator,
and forwards the async token stream to the client as ServerEvent JSON frames.

Reconnection: stores stream_idx in Redis; on reconnect replays buffered
tokens from stream_idx + 1.

Requirements: 11.1, 11.4
"""
from __future__ import annotations

import json
from typing import Any, Optional

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter()

# Redis key for stream index: session:{session_id}:stream_idx
_STREAM_IDX_TTL = 7200  # 2 hours


def _stream_idx_key(session_id: str) -> str:
    return f"session:{session_id}:stream_idx"


def _stream_buffer_key(session_id: str) -> str:
    return f"session:{session_id}:stream_buffer"


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def _get_stream_idx(redis: aioredis.Redis, session_id: str) -> int:
    val = await redis.get(_stream_idx_key(session_id))
    return int(val) if val is not None else -1


async def _set_stream_idx(redis: aioredis.Redis, session_id: str, idx: int) -> None:
    await redis.setex(_stream_idx_key(session_id), _STREAM_IDX_TTL, idx)


async def _buffer_event(
    redis: aioredis.Redis,
    session_id: str,
    idx: int,
    event: dict,
) -> None:
    """Store an event in the stream buffer for replay on reconnect."""
    key = _stream_buffer_key(session_id)
    await redis.hset(key, str(idx), json.dumps(event))
    await redis.expire(key, _STREAM_IDX_TTL)


async def _replay_events(
    websocket: WebSocket,
    redis: aioredis.Redis,
    session_id: str,
    from_idx: int,
) -> int:
    """Replay buffered events from from_idx onward. Returns last replayed idx."""
    key = _stream_buffer_key(session_id)
    all_entries = await redis.hgetall(key)
    if not all_entries:
        return from_idx - 1

    # Sort by integer index
    sorted_entries = sorted(
        ((int(k), v) for k, v in all_entries.items()),
        key=lambda x: x[0],
    )

    last_idx = from_idx - 1
    for idx, raw in sorted_entries:
        if idx >= from_idx:
            event = json.loads(raw)
            await websocket.send_text(json.dumps(event))
            last_idx = idx

    return last_idx


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Accept WebSocket connection and handle the query/response lifecycle."""
    await websocket.accept()
    logger.info("ws_connected", session_id=session_id)

    redis: Optional[aioredis.Redis] = None
    user_id: Optional[str] = None  # tracked for session flush on disconnect
    try:
        redis = await _get_redis()
    except Exception as exc:
        logger.warning("ws_redis_unavailable", error=str(exc))

    try:
        while True:
            # Receive message from client
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("ws_disconnected", session_id=session_id)
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"event": "error", "data": "Invalid JSON"})
                )
                continue

            query = msg.get("query", "")
            user_id = msg.get("user_id")
            resume_from: Optional[int] = msg.get("stream_idx")

            if not query:
                await websocket.send_text(
                    json.dumps({"event": "error", "data": "Missing 'query' field"})
                )
                continue

            # Handle reconnection replay
            if resume_from is not None and redis is not None:
                last_replayed = await _replay_events(
                    websocket, redis, session_id, from_idx=resume_from + 1
                )
                if last_replayed >= resume_from:
                    # All buffered events replayed; continue streaming from here
                    pass

            # Load session context from MemoryManager
            memory_context: list[dict] = []
            manager = None
            try:
                from backend.memory.buffer import ConversationBuffer
                from backend.memory.entity import EntityMemory
                from backend.memory.episodic import EpisodicMemory
                from backend.memory.manager import MemoryManager
                from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

                db_url = settings.database_url
                if db_url.startswith("postgresql://"):
                    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
                elif db_url.startswith("postgres://"):
                    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

                engine = create_async_engine(db_url, echo=False)
                session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

                buffer = ConversationBuffer()
                entity = EntityMemory()
                episodic = EpisodicMemory(session_factory=session_factory)
                manager = MemoryManager(buffer=buffer, entity=entity, episodic=episodic)
                ctx = await manager.load_context(session_id, user_id=user_id)
                memory_context = ctx.get("buffer_turns", [])
            except Exception as exc:
                logger.warning("ws_memory_load_failed", session_id=session_id, error=str(exc))

            # Dispatch to Orchestrator and stream events
            from backend.agents.orchestrator import Orchestrator

            orchestrator = Orchestrator()
            event_idx = -1
            if redis is not None:
                event_idx = await _get_stream_idx(redis, session_id)

            try:
                async for event in orchestrator.stream(
                    query=query,
                    session_id=session_id,
                    memory_context=memory_context,
                ):
                    event_idx += 1
                    frame = json.dumps(event)
                    await websocket.send_text(frame)

                    # Buffer event for replay and update stream_idx
                    if redis is not None:
                        await _buffer_event(redis, session_id, event_idx, event)
                        await _set_stream_idx(redis, session_id, event_idx)

                    # Stop streaming on done event
                    if event.get("event") == "done":
                        break

            except WebSocketDisconnect:
                logger.info("ws_disconnected_mid_stream", session_id=session_id)
                break
            except Exception as exc:
                logger.error("ws_stream_error", session_id=session_id, error=str(exc))
                try:
                    await websocket.send_text(
                        json.dumps({"event": "error", "data": str(exc)})
                    )
                    await websocket.send_text(json.dumps({"event": "done", "data": None}))
                except Exception:
                    pass

            # Save turn to memory
            if manager is not None:
                try:
                    await manager.save_turn(session_id, "user", query)
                except Exception as exc:
                    logger.warning("ws_save_turn_failed", session_id=session_id, error=str(exc))

    except WebSocketDisconnect:
        logger.info("ws_disconnected_outer", session_id=session_id)
    finally:
        # Schedule session flush to PostgreSQL via Celery on disconnect
        try:
            from backend.workers.celery_app import flush_session_to_postgres
            flush_session_to_postgres.delay(session_id, user_id)
            logger.info("ws_session_flush_scheduled", session_id=session_id)
        except Exception as exc:
            logger.warning("ws_session_flush_schedule_failed", session_id=session_id, error=str(exc))

        if redis is not None:
            await redis.aclose()
        logger.info("ws_closed", session_id=session_id)
