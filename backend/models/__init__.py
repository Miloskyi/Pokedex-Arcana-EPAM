"""
SQLAlchemy ORM models for PokÃ©dex Arcana.

Re-exports all models and the shared Base so that Alembic and application
code can import from a single location::

    from backend.models import Base, Pokemon, PokemonStats, Session, ...
"""
from .base import Base, get_session, make_engine, make_session_factory
from .pokemon import EvolutionChain, Pokemon, PokemonAbility, PokemonStats, PokemonType
from .ragas import QueryTrace, RagasEvaluation
from .session import EntityMemory, Session, SessionTurn

__all__ = [
    # base
    "Base",
    "make_engine",
    "make_session_factory",
    "get_session",
    # pokemon
    "Pokemon",
    "PokemonType",
    "PokemonStats",
    "PokemonAbility",
    "EvolutionChain",
    # session / memory
    "Session",
    "SessionTurn",
    "EntityMemory",
    # ragas / observability
    "RagasEvaluation",
    "QueryTrace",
]

