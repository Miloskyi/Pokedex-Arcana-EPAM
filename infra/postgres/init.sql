-- Pokédex Arcana — PostgreSQL initialization script
-- Requirements: 9.4, 10.2, 13.5

-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Core Pokémon data (populated by ingestion pipeline)
-- ---------------------------------------------------------------------------

-- Stores one row per Pokémon species with identity and classification data.
COMMENT ON SCHEMA public IS 'Pokédex Arcana application schema';

CREATE TABLE pokemon (
    id           SERIAL PRIMARY KEY,
    pokeapi_id   INTEGER UNIQUE NOT NULL,
    name         VARCHAR(100) NOT NULL,
    slug         VARCHAR(100) UNIQUE NOT NULL,  -- e.g. "charizard"
    generation   SMALLINT NOT NULL,
    is_legendary BOOLEAN DEFAULT FALSE,
    is_mythical  BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE pokemon IS
    'One row per Pokémon species; canonical identity and classification data populated by the ingestion pipeline.';

-- Stores the elemental type(s) for each Pokémon (slot 1 = primary, slot 2 = secondary).
CREATE TABLE pokemon_types (
    pokemon_id  INTEGER REFERENCES pokemon(id),
    slot        SMALLINT NOT NULL,  -- 1 = primary, 2 = secondary
    type_name   VARCHAR(20) NOT NULL,
    PRIMARY KEY (pokemon_id, slot)
);

COMMENT ON TABLE pokemon_types IS
    'Elemental type assignments per Pokémon; slot 1 is the primary type, slot 2 the optional secondary type.';

-- Stores the six base stats for each Pokémon; BST is auto-computed as a generated column.
CREATE TABLE pokemon_stats (
    pokemon_id  INTEGER REFERENCES pokemon(id) PRIMARY KEY,
    hp          SMALLINT NOT NULL,
    attack      SMALLINT NOT NULL,
    defense     SMALLINT NOT NULL,
    sp_atk      SMALLINT NOT NULL,
    sp_def      SMALLINT NOT NULL,
    speed       SMALLINT NOT NULL,
    bst         SMALLINT GENERATED ALWAYS AS (hp + attack + defense + sp_atk + sp_def + speed) STORED
);

COMMENT ON TABLE pokemon_stats IS
    'Six base stats per Pokémon; the bst (Base Stat Total) column is a generated column computed from the six individual stats.';

-- Stores all abilities (including hidden abilities) for each Pokémon.
CREATE TABLE pokemon_abilities (
    id           SERIAL PRIMARY KEY,
    pokemon_id   INTEGER REFERENCES pokemon(id),
    ability_name VARCHAR(100) NOT NULL,
    is_hidden    BOOLEAN DEFAULT FALSE,
    slot         SMALLINT NOT NULL
);

COMMENT ON TABLE pokemon_abilities IS
    'Abilities available to each Pokémon, including hidden abilities; slot indicates the ability position.';

-- Stores directed evolution relationships between Pokémon species.
CREATE TABLE evolution_chains (
    id               SERIAL PRIMARY KEY,
    chain_id         INTEGER NOT NULL,  -- PokéAPI chain ID
    from_pokemon_id  INTEGER REFERENCES pokemon(id),
    to_pokemon_id    INTEGER REFERENCES pokemon(id),
    trigger          VARCHAR(50),        -- level-up, use-item, trade, etc.
    condition_detail JSONB               -- e.g. {min_level: 16} or {item: "fire-stone"}
);

COMMENT ON TABLE evolution_chains IS
    'Directed evolution relationships; each row represents one evolution step from from_pokemon_id to to_pokemon_id with its trigger and conditions.';

-- ---------------------------------------------------------------------------
-- Conversational memory
-- ---------------------------------------------------------------------------

-- Represents a single user conversation session.
CREATE TABLE sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    VARCHAR(255),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at   TIMESTAMPTZ,
    summary    TEXT
);

COMMENT ON TABLE sessions IS
    'One row per conversation session; summary is populated when the session is flushed to episodic memory.';

-- Stores individual turns (user and assistant messages) within a session.
CREATE TABLE session_turns (
    id          SERIAL PRIMARY KEY,
    session_id  UUID REFERENCES sessions(id),
    turn_index  SMALLINT NOT NULL,
    role        VARCHAR(10) NOT NULL,  -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    agent_trace JSONB,                 -- which agents were invoked
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE session_turns IS
    'Individual turns within a session; role is either "user" or "assistant"; agent_trace records which agents were invoked.';

-- Stores named entities extracted from a session for cross-turn reference resolution.
CREATE TABLE entity_memory (
    id          SERIAL PRIMARY KEY,
    session_id  UUID REFERENCES sessions(id),
    entity_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50),           -- 'pokemon' | 'item' | 'move' | 'strategy'
    context     TEXT NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE entity_memory IS
    'Named entities extracted from a session (Pokémon, items, moves, strategies) enabling cross-turn entity resolution.';

-- ---------------------------------------------------------------------------
-- RAGAS evaluation
-- ---------------------------------------------------------------------------

-- Stores RAGAS benchmark evaluation results; passed_threshold is auto-computed.
CREATE TABLE ragas_evaluations (
    id                SERIAL PRIMARY KEY,
    evaluated_at      TIMESTAMPTZ DEFAULT NOW(),
    system_version    VARCHAR(50),
    query_id          VARCHAR(100) NOT NULL,
    query_category    VARCHAR(50),   -- 'stats' | 'lore' | 'damage' | 'team'
    faithfulness      FLOAT,
    answer_relevancy  FLOAT,
    context_precision FLOAT,
    context_recall    FLOAT,
    passed_threshold  BOOLEAN GENERATED ALWAYS AS (
        faithfulness >= 0.70
        AND answer_relevancy >= 0.70
        AND context_precision >= 0.70
        AND context_recall >= 0.70
    ) STORED
);

COMMENT ON TABLE ragas_evaluations IS
    'RAGAS benchmark evaluation results per query; passed_threshold is a generated column that is TRUE when all four metrics are >= 0.70.';

-- ---------------------------------------------------------------------------
-- Observability
-- ---------------------------------------------------------------------------

-- Stores per-query OpenTelemetry trace summaries for latency analysis.
CREATE TABLE query_traces (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       UUID REFERENCES sessions(id),
    query_text       TEXT,
    total_latency_ms INTEGER,
    slowest_agent    VARCHAR(100),
    agent_spans      JSONB,
    token_count      INTEGER,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE query_traces IS
    'Per-query OpenTelemetry trace summaries; agent_spans stores individual agent latency spans as JSON for slow-query analysis.';

-- ---------------------------------------------------------------------------
-- Indexes on frequently queried columns
-- ---------------------------------------------------------------------------

CREATE INDEX idx_pokemon_slug        ON pokemon (slug);
CREATE INDEX idx_pokemon_pokeapi_id  ON pokemon (pokeapi_id);
CREATE INDEX idx_session_turns_sid   ON session_turns (session_id);
CREATE INDEX idx_entity_memory_sid   ON entity_memory (session_id);
CREATE INDEX idx_ragas_category      ON ragas_evaluations (query_category);
CREATE INDEX idx_query_traces_sid    ON query_traces (session_id);
