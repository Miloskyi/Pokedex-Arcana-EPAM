"""
Shared SQLAlchemy 2.0 declarative base, async engine factory, and session maker.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def make_engine(database_url: str, **kwargs):
    """Create an async SQLAlchemy engine from a connection URL.

    The URL must use an async driver, e.g.
    ``postgresql+asyncpg://user:pass@host/db``.
    """
    return create_async_engine(database_url, **kwargs)


def make_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to *engine*."""
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that yields a database session and commits on exit.

    Usage::

        async with get_session(session_factory) as session:
            session.add(obj)
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

