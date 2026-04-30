"""
SQLAlchemy 2.0 ORM models for core PokÃ©mon data.

Tables: pokemon, pokemon_types, pokemon_stats, pokemon_abilities, evolution_chains
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

TIMESTAMPTZ = DateTime(timezone=True)

from .base import Base


class Pokemon(Base):
    __tablename__ = "pokemon"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pokeapi_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    generation: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_legendary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mythical: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )

    # Relationships
    stats: Mapped[Optional["PokemonStats"]] = relationship(
        "PokemonStats", back_populates="pokemon", uselist=False
    )
    types: Mapped[list["PokemonType"]] = relationship(
        "PokemonType", back_populates="pokemon", order_by="PokemonType.slot"
    )
    abilities: Mapped[list["PokemonAbility"]] = relationship(
        "PokemonAbility", back_populates="pokemon", order_by="PokemonAbility.slot"
    )
    evolutions_from: Mapped[list["EvolutionChain"]] = relationship(
        "EvolutionChain",
        foreign_keys="EvolutionChain.from_pokemon_id",
        back_populates="from_pokemon",
    )
    evolutions_to: Mapped[list["EvolutionChain"]] = relationship(
        "EvolutionChain",
        foreign_keys="EvolutionChain.to_pokemon_id",
        back_populates="to_pokemon",
    )

    def __repr__(self) -> str:
        return f"<Pokemon id={self.id} name={self.name!r} slug={self.slug!r}>"


class PokemonType(Base):
    __tablename__ = "pokemon_types"

    pokemon_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pokemon.id"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    type_name: Mapped[str] = mapped_column(String(20), nullable=False)

    pokemon: Mapped["Pokemon"] = relationship("Pokemon", back_populates="types")

    def __repr__(self) -> str:
        return (
            f"<PokemonType pokemon_id={self.pokemon_id} slot={self.slot}"
            f" type={self.type_name!r}>"
        )


class PokemonStats(Base):
    __tablename__ = "pokemon_stats"

    pokemon_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pokemon.id"), primary_key=True
    )
    hp: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    attack: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    defense: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sp_atk: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sp_def: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    speed: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Generated column: SMALLINT GENERATED ALWAYS AS (hp+attack+defense+sp_atk+sp_def+speed) STORED
    bst: Mapped[Optional[int]] = mapped_column(
        SmallInteger, server_default=None, nullable=True
    )

    pokemon: Mapped["Pokemon"] = relationship("Pokemon", back_populates="stats")

    def __repr__(self) -> str:
        return (
            f"<PokemonStats pokemon_id={self.pokemon_id} bst={self.bst}"
            f" hp={self.hp} atk={self.attack} def={self.defense}"
            f" spa={self.sp_atk} spd={self.sp_def} spe={self.speed}>"
        )


class PokemonAbility(Base):
    __tablename__ = "pokemon_abilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pokemon_id: Mapped[int] = mapped_column(Integer, ForeignKey("pokemon.id"))
    ability_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    pokemon: Mapped["Pokemon"] = relationship("Pokemon", back_populates="abilities")

    def __repr__(self) -> str:
        return (
            f"<PokemonAbility id={self.id} pokemon_id={self.pokemon_id}"
            f" ability={self.ability_name!r} hidden={self.is_hidden}>"
        )


class EvolutionChain(Base):
    __tablename__ = "evolution_chains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    from_pokemon_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("pokemon.id"), nullable=True
    )
    to_pokemon_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("pokemon.id"), nullable=True
    )
    trigger: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    condition_detail: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    from_pokemon: Mapped[Optional["Pokemon"]] = relationship(
        "Pokemon",
        foreign_keys=[from_pokemon_id],
        back_populates="evolutions_from",
    )
    to_pokemon: Mapped[Optional["Pokemon"]] = relationship(
        "Pokemon",
        foreign_keys=[to_pokemon_id],
        back_populates="evolutions_to",
    )

    def __repr__(self) -> str:
        return (
            f"<EvolutionChain id={self.id} chain_id={self.chain_id}"
            f" from={self.from_pokemon_id} to={self.to_pokemon_id}"
            f" trigger={self.trigger!r}>"
        )

