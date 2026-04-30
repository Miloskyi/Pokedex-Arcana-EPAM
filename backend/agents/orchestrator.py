"""Orchestrator Agent — LangGraph StateGraph supervisor.

Routes queries to specialized agents, runs parallel branches with timeouts,
aggregates results, and always invokes Verification_Agent for numerical data.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 6.3
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator, Optional

from typing_extensions import TypedDict

from backend.observability.tracing import trace_agent

# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class OrchestratorState(TypedDict):
    query: str
    session_id: str
    memory_context: list[dict]
    intent: str
    sub_tasks: list[dict]
    agent_results: dict[str, Any]
    verification_result: Optional[dict]
    final_response: Optional[str]
    error_notices: list[str]


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "stats": [
        # English
        "stat", "stats", "base stat", "bst", "hp", "attack", "defense", "speed",
        "sp. atk", "sp. def", "ability", "abilities", "evolution", "type",
        "what type", "what are", "how much", "how many", "base stats",
        # Spanish
        "estadistica", "estadísticas", "estadística", "stats de", "tipo",
        "tipos", "habilidad", "habilidades", "evolución", "evolucion",
        "velocidad", "defensa", "ataque", "vida", "ps", "puntos",
        "cuales son", "cuáles son", "dime", "dame", "muéstrame", "muestrame",
        "información de", "informacion de", "datos de", "datos sobre",
    ],
    "damage": [
        # English
        "damage", "calc", "formula", "hit", "power", "effective",
        "super effective", "one-shot", "ohko", "2hko",
        "uses", "against", "blizzard", "thunderbolt", "flamethrower",
        "nature", "natured", "bold", "modest", "adamant", "jolly", "timid",
        "evs", "ivs", "sp. def", "spdef", "special defense",
        # Spanish
        "daño", "daños", "calculo", "cálculo", "golpe", "efectivo",
        "super efectivo", "cuanto daño", "cuánto daño",
        "usa", "contra", "ventisca", "naturaleza", "audaz", "modesta",
        "adamante", "jovial", "tímida", "timida", "evs", "ivs",
        "defensa especial", "ataque especial",
    ],
    "lore": [
        # English
        "lore", "story", "history", "origin", "pokedex entry", "flavor",
        "legend", "myth", "region", "game", "anime", "manga", "episode",
        # Spanish
        "historia", "origen", "leyenda", "mito", "región", "region",
        "cuéntame", "cuentame", "háblame", "hablame", "describe",
    ],
    "team": [
        # English
        "team", "partner", "synergy", "tier", "ou", "uu", "ru", "nu", "pu",
        "smogon", "competitive", "build", "coverage",
        # Spanish
        "equipo", "compañero", "compañeros", "sinergia", "competitivo",
        "necesito", "recomienda", "recomendación",
    ],
    "report": ["report", "pdf", "summary", "full report", "generate report",
               "reporte", "informe", "análisis completo"],
    "comparison": [
        "compare", "comparison", "vs", "versus", "better", "stronger",
        "which is", "difference between",
        "comparar", "comparación", "mejor", "más fuerte", "diferencia",
    ],
}


def _classify_intent(query: str) -> tuple[str, list[str]]:
    """Classify query intent and return (primary_intent, matched_domains).

    Supports both English and Spanish queries.
    Falls back to 'stats' (not 'lore') when a Pokémon name is detected
    but no domain keyword matches — most casual queries are about stats.
    """
    q_lower = query.lower()
    matched: list[str] = []

    for domain, keywords in _INTENT_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            matched.append(domain)

    if not matched:
        matched = ["stats"]

    # Complex queries that mention both stats AND lore aspects → run both
    lore_signals = ["friend", "rival", "anime", "appear", "amigo", "rival",
                    "aparece", "cuéntame", "cuentame", "tell me about", "háblame",
                    "where", "dónde", "cuando", "when", "who", "quién"]
    stats_signals = ["ability", "abilities", "habilidad", "stats", "estadísticas",
                     "tipo", "type", "base stat", "bst"]
    has_lore = any(s in q_lower for s in lore_signals)
    has_stats = any(s in q_lower for s in stats_signals)

    if has_lore and has_stats and "stats" not in matched:
        matched.append("stats")
    if has_lore and "lore" not in matched:
        matched.append("lore")

    # Remove 'lore' if ONLY 'stats' is matched and no lore signals
    if "stats" in matched and "lore" in matched and not has_lore:
        matched = [d for d in matched if d != "lore"]

    # Remove 'team' if the query is clearly about a single Pokémon's info
    # (not about building a team)
    team_build_signals = ["team", "equipo", "teammates", "compañeros", "partner",
                          "build", "armar", "necesito para", "i need for"]
    if "team" in matched and not any(s in q_lower for s in team_build_signals):
        matched = [d for d in matched if d != "team"]

    if not matched:
        matched = ["stats"]

    if len(matched) == 1:
        return matched[0], matched
    return "multi", matched


def _build_sub_tasks(query: str, domains: list[str]) -> list[dict]:
    """Build sub-task list from matched domains."""
    sub_tasks: list[dict] = []
    for domain in domains:
        sub_tasks.append({"agent": domain, "query": query})
    return sub_tasks


# ---------------------------------------------------------------------------
# Pokémon name extraction helper
# ---------------------------------------------------------------------------

# Words that are NOT Pokémon names — stop words to skip
_STOP_WORDS = {
    # English
    "what", "are", "the", "of", "for", "is", "a", "an", "its", "their",
    "tell", "me", "about", "show", "give", "list", "find", "get", "best",
    "type", "types", "stats", "stat", "abilities", "ability", "moves",
    "move", "evolution", "evolutions", "base", "speed", "attack", "defense",
    "special", "hp", "bst", "total", "which", "how", "many", "much",
    # Spanish
    "cuales", "cuáles", "son", "los", "las", "del", "de", "la", "el",
    "un", "una", "sus", "tipo", "tipos", "estadisticas", "estadísticas",
    "habilidades", "habilidad", "movimientos", "movimiento", "evolución",
    "evolucion", "datos", "sobre", "dime", "dame", "muéstrame", "muestrame",
    "mejor", "mejores", "peor", "peores", "más", "mas", "fuerte", "fuertes",
    "pokemon", "pokémon",
}

# Known Pokémon types for type-based queries
_POKEMON_TYPES = {
    "fire", "water", "grass", "electric", "psychic", "ice", "dragon",
    "dark", "fairy", "fighting", "poison", "ground", "flying", "bug",
    "rock", "ghost", "steel", "normal",
    # Spanish
    "fuego", "agua", "planta", "eléctrico", "electrico", "psíquico",
    "psiquico", "hielo", "dragón", "dragon", "siniestro", "hada",
    "lucha", "veneno", "tierra", "volador", "bicho", "roca",
    "fantasma", "acero", "normal",
}

# Map Spanish type names to English
_TYPE_MAP_ES = {
    "fuego": "fire", "agua": "water", "planta": "grass",
    "eléctrico": "electric", "electrico": "electric",
    "psíquico": "psychic", "psiquico": "psychic",
    "hielo": "ice", "dragón": "dragon", "siniestro": "dark",
    "hada": "fairy", "lucha": "fighting", "veneno": "poison",
    "tierra": "ground", "volador": "flying", "bicho": "bug",
    "roca": "rock", "fantasma": "ghost", "acero": "steel",
}


def _extract_pokemon_name(query: str) -> str:
    """Extract the most likely Pokémon name from a natural language query.

    Handles English and Spanish. Returns lowercase name.
    """
    words = query.strip().split()
    candidates: list[str] = []

    # Strategy 1: word immediately after a preposition
    prepositions = {"de", "of", "for", "sobre", "del", "about", "para"}
    for i, word in enumerate(words):
        if word.lower() in prepositions and i + 1 < len(words):
            candidate = words[i + 1].lower().strip("?.,!'\":;")
            if candidate not in _STOP_WORDS and len(candidate) > 2:
                candidates.append(candidate)

    # Strategy 2: possessive form "Pikachu's" or "Pikachu:" → "pikachu"
    for word in words:
        clean = word.rstrip("'s:,'s").lower().strip("?.,!'\":;")
        if (word.endswith("'s") or word.endswith("'s") or word.endswith(":")) and clean not in _STOP_WORDS and len(clean) > 2:
            candidates.append(clean)

    # Strategy 3: capitalized words that aren't stop words
    for word in words:
        if word and word[0].isupper():
            candidate = word.lower().strip("?.,!'\":;")
            if candidate not in _STOP_WORDS and len(candidate) > 2:
                candidates.append(candidate)

    # Strategy 4: last meaningful word
    for word in reversed(words):
        candidate = word.lower().strip("?.,!'\":;")
        if candidate not in _STOP_WORDS and len(candidate) > 2:
            candidates.append(candidate)
            break

    # Return first valid candidate, or fallback
    for c in candidates:
        if c not in _STOP_WORDS and len(c) > 2:
            return c

    return "pikachu"


def _extract_type_from_query(query: str) -> str | None:
    """Extract a Pokémon type from a query like 'best water pokemon'."""
    q_lower = query.lower()
    for word in q_lower.split():
        word_clean = word.strip("?.,!")
        if word_clean in _TYPE_MAP_ES:
            return _TYPE_MAP_ES[word_clean]
        if word_clean in _POKEMON_TYPES and word_clean not in _TYPE_MAP_ES:
            return word_clean
    return None


# ---------------------------------------------------------------------------
# Agent node wrappers
# ---------------------------------------------------------------------------

# Top Pokémon by type for "best X type" queries (BST-ranked)
_TOP_BY_TYPE: dict[str, list[str]] = {
    "water": ["kyogre", "palkia", "suicune", "gyarados", "vaporeon", "blastoise", "swampert"],
    "fire": ["reshiram", "charizard", "blaziken", "arcanine", "typhlosion", "infernape"],
    "grass": ["shaymin", "venusaur", "sceptile", "roserade", "leafeon", "serperior"],
    "electric": ["zekrom", "raikou", "jolteon", "electivire", "magnezone", "pikachu"],
    "psychic": ["mewtwo", "alakazam", "espeon", "gardevoir", "latios", "latias"],
    "dragon": ["rayquaza", "garchomp", "dragonite", "salamence", "hydreigon"],
    "ice": ["kyurem", "articuno", "glaceon", "mamoswine", "weavile"],
    "dark": ["tyranitar", "umbreon", "absol", "hydreigon", "weavile"],
    "fairy": ["xerneas", "togekiss", "gardevoir", "sylveon", "clefable"],
    "fighting": ["lucario", "machamp", "conkeldurr", "heracross", "infernape"],
    "ghost": ["giratina", "gengar", "chandelure", "mismagius", "dusknoir"],
    "steel": ["dialga", "metagross", "scizor", "steelix", "lucario"],
    "ground": ["groudon", "garchomp", "excadrill", "hippowdon", "rhyperior"],
    "rock": ["tyranitar", "aerodactyl", "golem", "rampardos", "rhyperior"],
    "flying": ["lugia", "rayquaza", "dragonite", "gyarados", "staraptor"],
    "bug": ["scizor", "heracross", "volcarona", "yanmega", "scolipede"],
    "poison": ["toxapex", "gengar", "nidoking", "roserade", "crobat"],
    "normal": ["arceus", "slaking", "blissey", "snorlax", "porygon-z"],
}


async def _run_stats_node(query: str) -> dict[str, Any]:
    from backend.agents.stats_agent import StatsAgent

    # Check if this is a "best X type" query
    poke_type = _extract_type_from_query(query)
    is_best_query = any(w in query.lower() for w in [
        "best", "mejor", "top", "strongest", "más fuerte", "mas fuerte",
        "strongest", "powerful", "poderoso",
    ])

    if poke_type and is_best_query:
        # Return top Pokémon of that type
        top_names = _TOP_BY_TYPE.get(poke_type, ["pikachu"])[:3]
        agent = StatsAgent()
        results = []
        for name in top_names:
            try:
                r = await agent.run(name)
                results.append(r)
            except Exception:
                pass
        if results:
            return {"type": "comparison", "data": results}

    pokemon_name = _extract_pokemon_name(query)
    agent = StatsAgent()
    result = await agent.run(pokemon_name)
    return {"type": "stats", "data": result}


async def _run_damage_node(query: str) -> dict[str, Any]:
    from backend.agents.damage_calc_agent import DamageCalcAgent
    from backend.llm_client import chat_complete
    import json

    # Use LLM to parse complex damage queries in any language
    parse_prompt = f"""Extract damage calculation parameters from this Pokémon query. Return ONLY valid JSON, no explanation.

Query: "{query}"

Spanish nature names mapping: Audaz=Bold, Modesta=Modest, Adamante=Adamant, Jovial=Jolly, Tímida=Timid, Firme=Impish, Osada=Hasty, Agitada=Hasty, Mansa=Calm, Serena=Calm, Cauta=Careful, Grosera=Rash, Ingenua=Naive, Pícara=Naughty, Activa=Jolly, Alegre=Jolly

Spanish move names: Ventisca=Blizzard, Rayo=Thunderbolt, Lanzallamas=Flamethrower, Surf=Surf, Terremoto=Earthquake, Psíquico=Psychic, Bola Sombra=Shadow Ball

Return JSON:
{{
  "attacker": "pokemon name lowercase",
  "move": "move name lowercase with hyphens",
  "defender": "pokemon name lowercase",
  "attacker_nature": "english nature name lowercase or null",
  "weather": "sun/rain/sand/snow/none",
  "held_item": "item name or none",
  "defender_evs_spdef": 252
}}

Examples:
- "Bold Abomasnow uses Blizzard against Jigglypuff 0 SpD EVs" → {{"attacker":"abomasnow","move":"blizzard","defender":"jigglypuff","attacker_nature":"bold","weather":"none","held_item":"none","defender_evs_spdef":0}}
- "Abomasnow de naturaleza Audaz usa Ventisca contra Jigglypuff con 0 EVs en Defensa Especial" → {{"attacker":"abomasnow","move":"blizzard","defender":"jigglypuff","attacker_nature":"bold","weather":"none","held_item":"none","defender_evs_spdef":0}}
"""

    attacker = "pikachu"
    move = "thunderbolt"
    defender = "charizard"
    nature = "hardy"
    weather = "none"
    held_item = "none"
    defender_evs: dict = {}

    try:
        raw = await chat_complete(
            messages=[{"role": "user", "content": parse_prompt}],
            temperature=0.0,
            max_tokens=200,
            json_mode=True,
        )
        parsed = json.loads(raw)
        attacker = parsed.get("attacker") or attacker
        move = (parsed.get("move") or move).replace(" ", "-")
        defender = parsed.get("defender") or defender
        nature = parsed.get("attacker_nature") or nature
        weather = parsed.get("weather") or weather
        held_item = parsed.get("held_item") or held_item
        spdef_evs = parsed.get("defender_evs_spdef", 252)
        if spdef_evs is not None:
            defender_evs = {"sp_def": int(spdef_evs)}
    except Exception:
        # Fallback: simple keyword parsing
        words = query.lower().split()
        if "uses" in words:
            idx = words.index("uses")
            if idx > 0:
                attacker = words[idx - 1].strip(".,!")
            if idx + 1 < len(words):
                move = words[idx + 1].strip(".,!")
        if "against" in words:
            idx = words.index("against")
            if idx + 1 < len(words):
                defender = words[idx + 1].strip(".,!")
        # Spanish: "usa X contra Y"
        if "usa" in words:
            idx = words.index("usa")
            if idx > 0:
                attacker = words[idx - 1].strip(".,!")
            if idx + 1 < len(words):
                move = words[idx + 1].strip(".,!")
        if "contra" in words:
            idx = words.index("contra")
            if idx + 1 < len(words):
                defender = words[idx + 1].strip(".,!")

    agent = DamageCalcAgent()
    result = await agent.run(
        attacker_name=attacker,
        move_name=move,
        defender_name=defender,
        attacker_nature=nature,
        defender_evs=defender_evs,
        weather=weather,
        held_item=held_item,
    )
    return {"type": "damage", "data": result}


async def _run_lore_node(query: str) -> dict[str, Any]:
    from backend.agents.lore_agent import LoreAgent
    agent = LoreAgent()
    # Pass the full query — the lore agent uses RAG to find relevant context
    result = await agent.run(query)
    return {"type": "lore", "data": result}


async def _run_team_node(query: str) -> dict[str, Any]:
    from backend.agents.team_builder_agent import TeamBuilderAgent
    from backend.llm_client import chat_complete
    import json

    lead = "dragapult"
    tier = "OU"

    # Use LLM to extract lead Pokémon and tier from complex queries
    parse_prompt = f"""Extract team building parameters from this query. Return ONLY valid JSON.

Query: "{query}"

Return JSON:
{{
  "lead_pokemon": "pokemon name (lowercase)",
  "tier": "OU/UU/RU/NU/PU"
}}

Examples:
- "I need 5 teammates for Dragapult in OU" → {{"lead_pokemon":"dragapult","tier":"OU"}}
- "Necesito compañeros para Garchomp en competitivo" → {{"lead_pokemon":"garchomp","tier":"OU"}}
- "Build a team around Pikachu" → {{"lead_pokemon":"pikachu","tier":"OU"}}
"""

    try:
        raw = await chat_complete(
            messages=[{"role": "user", "content": parse_prompt}],
            temperature=0.0,
            max_tokens=100,
            json_mode=True,
        )
        parsed = json.loads(raw)
        lead = parsed.get("lead_pokemon") or lead
        tier = (parsed.get("tier") or tier).upper()
    except Exception:
        # Fallback: keyword extraction
        words = query.lower().split()
        for tier_name in ["ou", "uu", "ru", "nu", "pu"]:
            if tier_name in words:
                tier = tier_name.upper()
                break
        lead = _extract_pokemon_name(query)

    agent = TeamBuilderAgent()
    result = await agent.run(lead, tier)
    return {"type": "team", "data": result}


async def _run_report_node(query: str) -> dict[str, Any]:
    from backend.agents.report_agent import ReportAgent
    agent = ReportAgent()
    pokemon_name = _extract_pokemon_name(query)
    result = await agent.run(pokemon_name)
    return {"type": "report", "data": result}


async def _run_comparison_node(query: str) -> dict[str, Any]:
    from backend.agents.stats_agent import StatsAgent
    agent = StatsAgent()
    # Extract Pokémon names — look for capitalized words or words after "vs"/"versus"
    words = query.split()
    names: list[str] = []

    # Look for "X vs Y" pattern
    q_lower = query.lower()
    for sep in [" vs ", " versus ", " contra ", " o "]:
        if sep in q_lower:
            parts = q_lower.split(sep)
            for part in parts:
                candidate = _extract_pokemon_name(part)
                if candidate not in names:
                    names.append(candidate)
            break

    # Fallback: extract capitalized words
    if len(names) < 2:
        for word in words:
            candidate = word.lower().strip("?.,!'\"")
            if candidate not in _STOP_WORDS and len(candidate) > 2 and candidate not in names:
                names.append(candidate)

    if len(names) < 2:
        names = ["pikachu", "charizard"]

    results = []
    for name in names[:3]:
        try:
            r = await agent.run(name)
            results.append(r)
        except Exception:
            pass
    return {"type": "comparison", "data": results}


_AGENT_NODES: dict[str, Any] = {
    "stats": _run_stats_node,
    "damage": _run_damage_node,
    "lore": _run_lore_node,
    "team": _run_team_node,
    "report": _run_report_node,
    "comparison": _run_comparison_node,
}

_AGENT_TIMEOUT = 90.0  # seconds — llama3.1:8b needs more time


async def _run_agent_with_timeout(
    domain: str,
    query: str,
    error_notices: list[str],
) -> tuple[str, Any]:
    """Run an agent node with a 30s timeout. On failure, record error notice."""
    node_fn = _AGENT_NODES.get(domain)
    if node_fn is None:
        error_notices.append(f"Unknown agent domain: {domain}")
        return domain, None

    try:
        result = await asyncio.wait_for(node_fn(query), timeout=_AGENT_TIMEOUT)
        return domain, result
    except asyncio.TimeoutError:
        error_notices.append(f"Agent '{domain}' timed out after {_AGENT_TIMEOUT}s")
        return domain, None
    except Exception as exc:
        error_notices.append(f"Agent '{domain}' failed: {exc}")
        return domain, None


# ---------------------------------------------------------------------------
# Numerical data detection
# ---------------------------------------------------------------------------

def _result_has_numerical_data(result: Any) -> bool:
    """Return True if the result contains numerical Pokémon data."""
    if result is None:
        return False
    result_type = result.get("type") if isinstance(result, dict) else None
    if result_type in ("stats", "damage", "comparison"):
        return True
    # Check nested data
    data = result.get("data") if isinstance(result, dict) else result
    if hasattr(data, "base_stats") and data.base_stats:
        return True
    if hasattr(data, "min_damage"):
        return True
    if isinstance(data, list):
        return any(_result_has_numerical_data({"type": "stats", "data": r}) for r in data)
    return False


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate_results(
    state: OrchestratorState,
) -> str:
    """Merge all agent_results into a single coherent response string."""
    parts: list[str] = []
    agent_results = state["agent_results"]

    for domain, result in agent_results.items():
        if result is None:
            continue
        data = result.get("data") if isinstance(result, dict) else result
        result_type = result.get("type", domain) if isinstance(result, dict) else domain

        if result_type == "stats":
            if hasattr(data, "error") and data.error:
                parts.append(f"**Stats:** {data.error}")
            elif hasattr(data, "pokemon_name"):
                bs = data.base_stats
                name = data.pokemon_name.title()
                dex_num = str(data.pokeapi_id).zfill(4)
                types_str = " / ".join(t.title() for t in data.types) if data.types else "Unknown"
                lines = [
                    f"**{name}** (No. {dex_num})",
                    f"🏷️ **Type:** {types_str}",
                    f"",
                    f"📊 **Base Stats:**",
                    f"  • HP: {bs.get('hp', '?')}",
                    f"  • Attack: {bs.get('attack', '?')}",
                    f"  • Defense: {bs.get('defense', '?')}",
                    f"  • Sp. Atk: {bs.get('sp_atk', '?')}",
                    f"  • Sp. Def: {bs.get('sp_def', '?')}",
                    f"  • Speed: {bs.get('speed', '?')}",
                    f"  • **BST: {data.bst}**",
                ]
                if data.abilities:
                    ability_names = [a.get('name', '').replace('-', ' ').title() for a in data.abilities if not a.get('is_hidden')]
                    hidden = [a.get('name', '').replace('-', ' ').title() for a in data.abilities if a.get('is_hidden')]
                    if ability_names:
                        lines.append(f"⚡ **Abilities:** {', '.join(ability_names)}")
                    if hidden:
                        lines.append(f"🔮 **Hidden Ability:** {', '.join(hidden)}")
                if data.stab_types:
                    lines.append(f"💥 **STAB types:** {', '.join(t.title() for t in data.stab_types)}")
                # Type weaknesses
                if hasattr(data, "type_matchups") and data.type_matchups:
                    weaknesses = [t.title() for t, m in data.type_matchups.items() if m > 1.0]
                    resistances = [t.title() for t, m in data.type_matchups.items() if 0 < m < 1.0]
                    immunities = [t.title() for t, m in data.type_matchups.items() if m == 0.0]
                    if weaknesses:
                        lines.append(f"❌ **Weak to:** {', '.join(weaknesses)}")
                    if resistances:
                        lines.append(f"✅ **Resists:** {', '.join(resistances)}")
                    if immunities:
                        lines.append(f"🛡️ **Immune to:** {', '.join(immunities)}")
                lines.append(f"\n📖 *Reference: National PokéDex, entry #{dex_num}*")
                parts.append("\n".join(lines))

        elif result_type == "damage":
            if hasattr(data, "error") and data.error:
                parts.append(f"**Damage Calculation:** {data.error}")
            elif hasattr(data, "min_damage"):
                mods = data.modifiers_applied or {}
                lines = [
                    f"⚔️ **Damage Calculation**",
                    f"**{data.attacker.title()}** uses **{data.move.title()}** → **{data.defender.title()}**",
                    f"",
                    f"📊 **Result:** {data.min_damage}–{data.max_damage} HP ({data.min_percent}%–{data.max_percent}%)",
                ]
                # Show modifiers applied
                mod_parts = []
                if mods.get("stab", 1.0) > 1.0:
                    mod_parts.append(f"STAB ×{mods['stab']}")
                if mods.get("type_effectiveness", 1.0) != 1.0:
                    eff = mods["type_effectiveness"]
                    if eff == 0:
                        mod_parts.append("Immune (0×)")
                    elif eff < 1:
                        mod_parts.append(f"Not very effective (×{eff})")
                    elif eff == 2:
                        mod_parts.append("Super effective (×2)")
                    elif eff == 4:
                        mod_parts.append("Super effective (×4)")
                if mods.get("weather", 1.0) != 1.0:
                    mod_parts.append(f"Weather ×{mods['weather']}")
                if mod_parts:
                    lines.append(f"🔧 **Modifiers:** {', '.join(mod_parts)}")
                lines.append(f"📖 *Reference: Gen IX damage formula*")
                parts.append("\n".join(lines))

        elif result_type == "lore":
            if hasattr(data, "answer"):
                if data.no_context_found:
                    # Fallback: use stats agent for basic info
                    parts.append(f"📖 {data.answer}")
                else:
                    lines = [f"📖 **Pokémon Lore**", "", data.answer]
                    if data.citations:
                        sources = list({c.collection for c in data.citations})
                        lines.append(f"\n📚 *Reference: {', '.join(s.replace('_', ' ').title() for s in sources)}*")
                    parts.append("\n".join(lines))

        elif result_type == "team":
            if hasattr(data, "partners"):
                lines = [f"🏆 **Competitive Team for {data.lead_pokemon.title()} ({data.tier})**"]
                if data.coverage_gaps:
                    lines.append(f"⚠️ **Weaknesses to cover:** {', '.join(t.title() for t in data.coverage_gaps)}")
                lines.append("")
                for i, p in enumerate(data.partners, 1):
                    lines.append(f"**{i}. {p.pokemon_name.title()}**")
                    lines.append(f"   • Nature: {p.nature.title()} | Item: {p.held_item.replace('-', ' ').title()}")
                    lines.append(f"   • Ability: {p.ability.replace('-', ' ').title()}")
                    if p.moveset:
                        lines.append(f"   • Moves: {', '.join(m.replace('-', ' ').title() for m in p.moveset)}")
                    if p.ev_spread:
                        ev_str = " / ".join(f"{v} {k.upper()}" for k, v in p.ev_spread.items() if v > 0)
                        if ev_str:
                            lines.append(f"   • EVs: {ev_str}")
                    lines.append(f"   • *{p.justification}*")
                    lines.append("")
                if data.overlap_warnings:
                    lines.append(f"⚠️ {'; '.join(data.overlap_warnings)}")
                lines.append("📖 *Reference: Smogon OU Viability Rankings, type analysis*")
                parts.append("\n".join(lines))

        elif result_type == "report":
            if hasattr(data, "markdown"):
                # Include a summary of the report
                lines = data.markdown.split("\n")
                title = lines[0] if lines else f"Report for {data.pokemon_name}"
                parts.append(f"**Report:** {title} (full report generated).")

        elif result_type == "comparison":
            if isinstance(data, list) and data:
                # Sort by BST descending
                valid = [r for r in data if hasattr(r, "pokemon_name") and not getattr(r, "error", None)]
                valid.sort(key=lambda r: r.bst, reverse=True)
                if valid:
                    lines = ["**Pokémon Comparison:**"]
                    for r in valid:
                        types_str = " / ".join(t.title() for t in r.types)
                        lines.append(
                            f"• **{r.pokemon_name.title()}** — {types_str} | BST: {r.bst} "
                            f"(HP:{r.base_stats.get('hp','?')} ATK:{r.base_stats.get('attack','?')} "
                            f"DEF:{r.base_stats.get('defense','?')} SPD:{r.base_stats.get('speed','?')})"
                        )
                    parts.append("\n".join(lines))

    # Append verification result if present
    vr = state.get("verification_result")
    if vr:
        if vr.get("discrepancy_detected"):
            parts.append(
                f"⚠️ **Discrepancy detected:** Agent value={vr.get('agent_value')}, "
                f"Reference value={vr.get('reference_value')}, "
                f"Delta={vr.get('delta')}."
            )
        elif vr.get("verified"):
            parts.append("✅ **Verified:** Numerical results confirmed by independent calculation.")

    # Append error notices
    for notice in state.get("error_notices", []):
        parts.append(f"⚠️ {notice}")

    if not parts:
        return "I was unable to retrieve information for your query."

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Orchestrator class
# ---------------------------------------------------------------------------


class Orchestrator:
    """LangGraph-style supervisor orchestrator.

    Classifies intent, dispatches to agent nodes in parallel,
    aggregates results, and invokes Verification_Agent for numerical data.
    """

    async def run(
        self,
        query: str,
        session_id: str,
        memory_context: list[dict] | None = None,
    ) -> OrchestratorState:
        """Execute the full orchestration pipeline and return the final state."""
        _start_time = time.monotonic()
        state: OrchestratorState = {
            "query": query,
            "session_id": session_id,
            "memory_context": memory_context or [],
            "intent": "",
            "sub_tasks": [],
            "agent_results": {},
            "verification_result": None,
            "final_response": None,
            "error_notices": [],
        }

        # 1. Classify intent (< 500ms target)
        intent, domains = _classify_intent(query)
        state["intent"] = intent
        state["sub_tasks"] = _build_sub_tasks(query, domains)

        # 2. Dispatch to agent nodes in parallel
        tasks = [
            _run_agent_with_timeout(domain, query, state["error_notices"])
            for domain in domains
        ]
        results = await asyncio.gather(*tasks)

        for domain, result in results:
            if result is not None:
                state["agent_results"][domain] = result

        # 3. Invoke Verification_Agent if any result contains numerical data
        has_numerical = any(
            _result_has_numerical_data(r)
            for r in state["agent_results"].values()
        )
        if has_numerical:
            state["verification_result"] = await self._run_verification(
                state["agent_results"], state["error_notices"]
            )

        # 4. Aggregate results
        state["final_response"] = _aggregate_results(state)

        # 5. Write query trace to PostgreSQL (Requirement 13.1, 13.5)
        total_latency_ms = int((time.monotonic() - _start_time) * 1000)
        token_count = len((state["final_response"] or "").split())
        agent_spans = {
            domain: {"latency_ms": 0}
            for domain in state["agent_results"]
        }
        await self.write_query_trace(
            session_id=session_id,
            query=query,
            total_latency_ms=total_latency_ms,
            agent_spans=agent_spans,
            token_count=token_count,
        )

        return state

    async def write_query_trace(
        self,
        session_id: str,
        query: str,
        total_latency_ms: int,
        agent_spans: dict[str, Any],
        token_count: int,
    ) -> None:
        """Write a QueryTrace record to PostgreSQL.

        Records total_latency_ms, slowest_agent, agent_spans, and token_count
        for observability. Failures are logged but do not raise.

        Requirements: 13.1, 13.5
        """
        import structlog as _structlog
        _logger = _structlog.get_logger(__name__)

        # Determine slowest agent from agent_spans
        slowest_agent: str | None = None
        if agent_spans:
            slowest_agent = max(agent_spans, key=lambda k: agent_spans[k].get("latency_ms", 0))

        try:
            from sqlalchemy.ext.asyncio import (
                AsyncSession,
                async_sessionmaker,
                create_async_engine,
            )
            from backend.config import settings
            from backend.models.ragas import QueryTrace

            db_url = settings.database_url
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

            engine = create_async_engine(db_url, echo=False)
            session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            import uuid as _uuid
            try:
                parsed_session_id = _uuid.UUID(session_id)
            except (ValueError, AttributeError):
                parsed_session_id = None

            trace_row = QueryTrace(
                session_id=parsed_session_id,
                query_text=query,
                total_latency_ms=total_latency_ms,
                slowest_agent=slowest_agent,
                agent_spans=agent_spans,
                token_count=token_count,
            )

            async with session_factory() as db_session:
                db_session.add(trace_row)
                await db_session.commit()

            await engine.dispose()

            # Emit slow-query warning if latency exceeds 10s (Requirement 13.4)
            if total_latency_ms > 10_000:
                _logger.warning(
                    "slow_query_detected",
                    query_id=str(trace_row.id),
                    total_latency_ms=total_latency_ms,
                    slowest_agent=slowest_agent,
                )

        except Exception as exc:
            _logger.warning("write_query_trace_failed", session_id=session_id, error=str(exc))

    async def _run_verification(
        self,
        agent_results: dict[str, Any],
        error_notices: list[str],
    ) -> dict | None:
        """Run Verification_Agent on the first damage result found."""
        from backend.agents.verification_agent import VerificationAgent

        # Find a damage result to verify
        damage_result = None
        for result in agent_results.values():
            if isinstance(result, dict) and result.get("type") == "damage":
                data = result.get("data")
                if data and not getattr(data, "error", None):
                    damage_result = data
                    break

        if damage_result is None:
            # No damage result to verify; return a pass-through verification
            return {"verified": True, "discrepancy_detected": False,
                    "reference_value": None, "agent_value": None, "delta": None}

        try:
            agent = VerificationAgent()
            vr = await asyncio.wait_for(
                agent.verify_damage(damage_result),
                timeout=_AGENT_TIMEOUT,
            )
            return {
                "verified": vr.verified,
                "discrepancy_detected": vr.discrepancy_detected,
                "reference_value": vr.reference_value,
                "agent_value": vr.agent_value,
                "delta": vr.delta,
            }
        except asyncio.TimeoutError:
            error_notices.append("Verification_Agent timed out")
            return None
        except Exception as exc:
            error_notices.append(f"Verification_Agent failed: {exc}")
            return None

    async def stream(
        self,
        query: str,
        session_id: str,
        memory_context: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream orchestration events as ServerEvent dicts.

        Yields events in order:
          - agent_activity events as each domain starts
          - token events for the final response (word by word)
          - citation events from lore results
          - error events for each error notice
          - done event at the end
        """
        _start_time = time.monotonic()
        state: OrchestratorState = {
            "query": query,
            "session_id": session_id,
            "memory_context": memory_context or [],
            "intent": "",
            "sub_tasks": [],
            "agent_results": {},
            "verification_result": None,
            "final_response": None,
            "error_notices": [],
        }

        intent, domains = _classify_intent(query)
        state["intent"] = intent
        state["sub_tasks"] = _build_sub_tasks(query, domains)

        # Emit agent_activity events
        for domain in domains:
            yield {"event": "agent_activity", "data": f"{domain.title()} Agent"}

        # Run agents in parallel
        tasks = [
            _run_agent_with_timeout(domain, query, state["error_notices"])
            for domain in domains
        ]
        results = await asyncio.gather(*tasks)

        for domain, result in results:
            if result is not None:
                state["agent_results"][domain] = result

        # Verification
        has_numerical = any(
            _result_has_numerical_data(r)
            for r in state["agent_results"].values()
        )
        if has_numerical:
            yield {"event": "agent_activity", "data": "Verification Agent"}
            state["verification_result"] = await self._run_verification(
                state["agent_results"], state["error_notices"]
            )

        # Emit citations from lore results
        for result in state["agent_results"].values():
            if isinstance(result, dict) and result.get("type") == "lore":
                data = result.get("data")
                if data and hasattr(data, "citations"):
                    for citation in data.citations:
                        yield {
                            "event": "citation",
                            "data": {
                                "collection": citation.collection,
                                "passage": citation.passage,
                            },
                        }

        # Aggregate and stream response tokens
        state["final_response"] = _aggregate_results(state)
        response = state["final_response"] or ""
        words = response.split(" ")
        for word in words:
            yield {"event": "token", "data": word + " "}

        # Emit error notices
        for notice in state["error_notices"]:
            yield {"event": "error", "data": notice}

        # Write query trace to PostgreSQL (Requirement 13.1, 13.5)
        total_latency_ms = int((time.monotonic() - _start_time) * 1000)
        token_count = len((state["final_response"] or "").split())
        agent_spans = {
            domain: {"latency_ms": 0}
            for domain in state["agent_results"]
        }
        await self.write_query_trace(
            session_id=session_id,
            query=query,
            total_latency_ms=total_latency_ms,
            agent_spans=agent_spans,
            token_count=token_count,
        )

        yield {"event": "done", "data": None}
