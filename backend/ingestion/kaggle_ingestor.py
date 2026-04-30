"""
Kaggle CSV ingestor: reads data/raw/pokemon.csv, normalises stat columns,
and upserts into the pokemon_stats table.

Missing columns are handled gracefully — only present columns are updated.
"""
from __future__ import annotations

from pathlib import Path

import structlog

from backend.config import settings
from backend.models.base import make_engine, make_session_factory
from backend.models.pokemon import Pokemon, PokemonStats

log = structlog.get_logger(__name__)

CSV_PATH = Path("data/raw/pokemon.csv")

# Mapping from CSV column names to ORM field names
STAT_COLUMN_MAP: dict[str, str] = {
    "hp": "hp",
    "HP": "hp",
    "attack": "attack",
    "Attack": "attack",
    "defense": "defense",
    "Defense": "defense",
    "sp. atk": "sp_atk",
    "Sp. Atk": "sp_atk",
    "special-attack": "sp_atk",
    "sp. def": "sp_def",
    "Sp. Def": "sp_def",
    "special-defense": "sp_def",
    "speed": "speed",
    "Speed": "speed",
}

NAME_COLUMNS = ["name", "Name", "pokemon", "Pokemon"]


async def ingest_kaggle(csv_path: Path = CSV_PATH) -> None:
    """Read Kaggle CSV and upsert stats into PostgreSQL."""
    try:
        import pandas as pd
    except ImportError:
        log.error("kaggle_ingestor.pandas_missing")
        return

    if not csv_path.exists():
        log.warning("kaggle_ingestor.csv_not_found", path=str(csv_path))
        return

    log.info("kaggle_ingestor.start", path=str(csv_path))

    df = pd.read_csv(csv_path)

    # Identify name column
    name_col: str | None = None
    for col in NAME_COLUMNS:
        if col in df.columns:
            name_col = col
            break

    if name_col is None:
        log.error("kaggle_ingestor.no_name_column", columns=list(df.columns))
        return

    # Identify available stat columns
    available: dict[str, str] = {}  # csv_col → orm_field
    for csv_col, orm_field in STAT_COLUMN_MAP.items():
        if csv_col in df.columns and orm_field not in available.values():
            available[csv_col] = orm_field

    if not available:
        log.warning("kaggle_ingestor.no_stat_columns", columns=list(df.columns))
        return

    log.info("kaggle_ingestor.columns_found", stat_columns=list(available.keys()))

    engine = make_engine(settings.database_url, echo=False)
    session_factory = make_session_factory(engine)

    upserted = 0
    skipped = 0

    async with session_factory() as session:
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        for _, row in df.iterrows():
            slug = str(row[name_col]).lower().strip()

            # Look up the Pokémon by slug
            result = await session.execute(
                select(Pokemon).where(Pokemon.slug == slug)
            )
            pokemon = result.scalar_one_or_none()
            if pokemon is None:
                skipped += 1
                continue

            # Build stats dict from available columns
            stats: dict[str, int] = {}
            for csv_col, orm_field in available.items():
                val = row.get(csv_col)
                if val is not None and not (isinstance(val, float) and val != val):
                    stats[orm_field] = int(val)

            if not stats:
                skipped += 1
                continue

            stmt = (
                pg_insert(PokemonStats)
                .values(pokemon_id=pokemon.id, **{
                    "hp": 0, "attack": 0, "defense": 0,
                    "sp_atk": 0, "sp_def": 0, "speed": 0,
                    **stats,
                })
                .on_conflict_do_update(
                    index_elements=["pokemon_id"],
                    set_=stats,
                )
            )
            await session.execute(stmt)
            upserted += 1

        await session.commit()

    await engine.dispose()
    log.info("kaggle_ingestor.done", upserted=upserted, skipped=skipped)
