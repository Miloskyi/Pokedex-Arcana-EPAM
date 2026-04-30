"""Stats Agent — fetches Pokémon data from PokéAPI and returns a StatsResult.

Flow
----
1. GET https://pokeapi.co/api/v2/pokemon/{name}
2. GET https://pokeapi.co/api/v2/pokemon-species/{name}  (for evolution chain URL)
3. GET evolution chain URL
4. Build type matchup dict (all 18 types) using the hardcoded effectiveness chart
5. On 404: fuzzy-match the input against a known name list and return StatsResult(error=...)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import httpx
from thefuzz import process as fuzz_process

from backend.observability.tracing import trace_agent

# ---------------------------------------------------------------------------
# Result dataclass (extended with type_matchups and stab_types per spec)
# ---------------------------------------------------------------------------


@dataclass
class StatsResult:
    pokemon_name: str
    pokeapi_id: int
    types: list[str]
    base_stats: dict[str, int]  # {hp, attack, defense, sp_atk, sp_def, speed}
    bst: int
    abilities: list[dict]
    evolution_chain: list[dict]
    type_matchups: dict[str, float]  # all 18 types → multiplier
    stab_types: list[str]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Full Gen IX type effectiveness chart
# Outer key = defending type, inner key = attacking type → multiplier
# ---------------------------------------------------------------------------

_ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]

# _TYPE_CHART[attacking_type][defending_type] = multiplier
_TYPE_CHART: dict[str, dict[str, float]] = {
    "normal":   {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0, "bug": 2.0,
                 "rock": 0.5, "dragon": 0.5, "steel": 2.0},
    "water":    {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0,
                 "rock": 2.0, "dragon": 0.5},
    "electric": {"water": 2.0, "electric": 0.5, "grass": 0.5, "ground": 0.0,
                 "flying": 2.0, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5,
                 "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0,
                 "dragon": 0.5, "steel": 0.5},
    "ice":      {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5,
                 "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5,
                 "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0,
                 "dark": 2.0, "steel": 2.0, "fairy": 0.5},
    "poison":   {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5,
                 "ghost": 0.5, "steel": 0.0, "fairy": 2.0},
    "ground":   {"fire": 2.0, "electric": 2.0, "grass": 0.5, "poison": 2.0,
                 "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0},
    "flying":   {"electric": 0.5, "grass": 2.0, "fighting": 2.0, "bug": 2.0,
                 "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2.0, "poison": 2.0, "psychic": 0.5,
                 "dark": 0.0, "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5,
                 "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0,
                 "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5,
                 "flying": 2.0, "bug": 2.0, "steel": 0.5},
    "ghost":    {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon":   {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark":     {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0,
                 "dark": 0.5, "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0,
                 "rock": 2.0, "steel": 0.5, "fairy": 2.0},
    "fairy":    {"fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0,
                 "dark": 2.0, "steel": 0.5},
}


def _compute_type_matchups(defending_types: list[str]) -> dict[str, float]:
    """Return a dict of {attacking_type: multiplier} for a Pokémon's type combo."""
    matchups: dict[str, float] = {}
    for atk_type in _ALL_TYPES:
        multiplier = 1.0
        for def_type in defending_types:
            chart = _TYPE_CHART.get(atk_type, {})
            multiplier *= chart.get(def_type, 1.0)
        matchups[atk_type] = multiplier
    return matchups


# ---------------------------------------------------------------------------
# Fallback name list for fuzzy matching (first 151 + some popular ones)
# A real implementation would load this from the PostgreSQL cache.
# ---------------------------------------------------------------------------

_KNOWN_NAMES: list[str] = [
    "bulbasaur", "ivysaur", "venusaur", "charmander", "charmeleon", "charizard",
    "squirtle", "wartortle", "blastoise", "caterpie", "metapod", "butterfree",
    "weedle", "kakuna", "beedrill", "pidgey", "pidgeotto", "pidgeot",
    "rattata", "raticate", "spearow", "fearow", "ekans", "arbok",
    "pikachu", "raichu", "sandshrew", "sandslash", "nidoran-f", "nidorina",
    "nidoqueen", "nidoran-m", "nidorino", "nidoking", "clefairy", "clefable",
    "vulpix", "ninetales", "jigglypuff", "wigglytuff", "zubat", "golbat",
    "oddish", "gloom", "vileplume", "paras", "parasect", "venonat", "venomoth",
    "diglett", "dugtrio", "meowth", "persian", "psyduck", "golduck",
    "mankey", "primeape", "growlithe", "arcanine", "poliwag", "poliwhirl",
    "poliwrath", "abra", "kadabra", "alakazam", "machop", "machoke", "machamp",
    "bellsprout", "weepinbell", "victreebel", "tentacool", "tentacruel",
    "geodude", "graveler", "golem", "ponyta", "rapidash", "slowpoke", "slowbro",
    "magnemite", "magneton", "farfetchd", "doduo", "dodrio", "seel", "dewgong",
    "grimer", "muk", "shellder", "cloyster", "gastly", "haunter", "gengar",
    "onix", "drowzee", "hypno", "krabby", "kingler", "voltorb", "electrode",
    "exeggcute", "exeggutor", "cubone", "marowak", "hitmonlee", "hitmonchan",
    "lickitung", "koffing", "weezing", "rhyhorn", "rhydon", "chansey",
    "tangela", "kangaskhan", "horsea", "seadra", "goldeen", "seaking",
    "staryu", "starmie", "mr-mime", "scyther", "jynx", "electabuzz", "magmar",
    "pinsir", "tauros", "magikarp", "gyarados", "lapras", "ditto", "eevee",
    "vaporeon", "jolteon", "flareon", "porygon", "omanyte", "omastar",
    "kabuto", "kabutops", "aerodactyl", "snorlax", "articuno", "zapdos",
    "moltres", "dratini", "dragonair", "dragonite", "mewtwo", "mew",
    # Gen 2 starters + popular
    "chikorita", "bayleef", "meganium", "cyndaquil", "quilava", "typhlosion",
    "totodile", "croconaw", "feraligatr", "lugia", "ho-oh", "celebi",
    # Gen 3 starters + popular
    "treecko", "grovyle", "sceptile", "torchic", "combusken", "blaziken",
    "mudkip", "marshtomp", "swampert", "rayquaza", "deoxys",
    # Gen 4 starters + popular
    "turtwig", "grotle", "torterra", "chimchar", "monferno", "infernape",
    "piplup", "prinplup", "empoleon", "lucario", "garchomp", "giratina",
    # Gen 5 starters + popular
    "snivy", "servine", "serperior", "tepig", "pignite", "emboar",
    "oshawott", "dewott", "samurott", "zoroark", "reshiram", "zekrom",
    # Gen 6 starters + popular
    "chespin", "quilladin", "chesnaught", "fennekin", "braixen", "delphox",
    "froakie", "frogadier", "greninja", "xerneas", "yveltal",
    # Gen 7 starters + popular
    "rowlet", "dartrix", "decidueye", "litten", "torracat", "incineroar",
    "popplio", "brionne", "primarina", "cosmog", "solgaleo", "lunala",
    # Gen 8 starters + popular
    "grookey", "thwackey", "rillaboom", "scorbunny", "raboot", "cinderace",
    "sobble", "drizzile", "inteleon", "zacian", "zamazenta",
    # Gen 9 starters + popular
    "sprigatito", "floragato", "meowscarada", "fuecoco", "crocalor", "skeledirge",
    "quaxly", "quaxwell", "quaquaval", "koraidon", "miraidon",
]


class StatsAgent:
    """Fetches Pokémon stats from PokéAPI and returns a StatsResult."""

    _POKEAPI_BASE = "https://pokeapi.co/api/v2"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_json(self, url: str) -> dict:
        client = self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    def _parse_base_stats(self, stats_data: list[dict]) -> dict[str, int]:
        mapping = {
            "hp": "hp",
            "attack": "attack",
            "defense": "defense",
            "special-attack": "sp_atk",
            "special-defense": "sp_def",
            "speed": "speed",
        }
        result: dict[str, int] = {}
        for entry in stats_data:
            api_name = entry["stat"]["name"]
            if api_name in mapping:
                result[mapping[api_name]] = entry["base_stat"]
        return result

    def _parse_abilities(self, abilities_data: list[dict]) -> list[dict]:
        return [
            {
                "name": a["ability"]["name"],
                "is_hidden": a["is_hidden"],
                "slot": a["slot"],
            }
            for a in abilities_data
        ]

    def _parse_types(self, types_data: list[dict]) -> list[str]:
        return [t["type"]["name"] for t in sorted(types_data, key=lambda x: x["slot"])]

    async def _fetch_evolution_chain(self, species_url: str) -> list[dict]:
        """Fetch and flatten the evolution chain into a list of stage dicts."""
        try:
            species_data = await self._fetch_json(species_url)
            chain_url = species_data["evolution_chain"]["url"]
            chain_data = await self._fetch_json(chain_url)
            return self._flatten_chain(chain_data["chain"])
        except Exception:
            return []

    def _flatten_chain(self, node: dict, stage: int = 0) -> list[dict]:
        """Recursively flatten a PokéAPI evolution chain node."""
        entries: list[dict] = []
        name = node["species"]["name"]
        details = node.get("evolution_details", [])
        trigger = details[0]["trigger"]["name"] if details else None
        condition = {}
        if details:
            d = details[0]
            if d.get("min_level"):
                condition["min_level"] = d["min_level"]
            if d.get("item") and d["item"]:
                condition["item"] = d["item"]["name"]
            if d.get("held_item") and d["held_item"]:
                condition["held_item"] = d["held_item"]["name"]
            if d.get("known_move") and d["known_move"]:
                condition["known_move"] = d["known_move"]["name"]
            if d.get("time_of_day"):
                condition["time_of_day"] = d["time_of_day"]
            if d.get("min_happiness"):
                condition["min_happiness"] = d["min_happiness"]
        entries.append({
            "name": name,
            "stage": stage,
            "trigger": trigger,
            "condition_detail": condition,
        })
        for evolution in node.get("evolves_to", []):
            entries.extend(self._flatten_chain(evolution, stage + 1))
        return entries

    def _fuzzy_suggest(self, name: str) -> str:
        """Return the closest known Pokémon name using fuzzy matching."""
        match, score = fuzz_process.extractOne(name, _KNOWN_NAMES)
        return match

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @trace_agent("stats")
    async def run(self, pokemon_name: str) -> StatsResult:
        """Fetch stats for *pokemon_name* and return a StatsResult.

        On 404 (unknown name), returns StatsResult(error=...) with a
        fuzzy-matched suggestion embedded in the error message.
        """
        name = pokemon_name.lower().strip()

        try:
            data = await self._fetch_json(f"{self._POKEAPI_BASE}/pokemon/{name}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                suggestion = self._fuzzy_suggest(name)
                return StatsResult(
                    pokemon_name=pokemon_name,
                    pokeapi_id=0,
                    types=[],
                    base_stats={},
                    bst=0,
                    abilities=[],
                    evolution_chain=[],
                    type_matchups={t: 1.0 for t in _ALL_TYPES},
                    stab_types=[],
                    error=(
                        f"Unknown Pokémon: '{pokemon_name}'. "
                        f"Did you mean '{suggestion}'?"
                    ),
                )
            raise

        types = self._parse_types(data["types"])
        base_stats = self._parse_base_stats(data["stats"])
        bst = sum(base_stats.values())
        abilities = self._parse_abilities(data["abilities"])
        type_matchups = _compute_type_matchups(types)
        stab_types = list(types)  # STAB applies to moves matching the Pokémon's own types

        species_url = data["species"]["url"]
        evolution_chain = await self._fetch_evolution_chain(species_url)

        return StatsResult(
            pokemon_name=data["name"],
            pokeapi_id=data["id"],
            types=types,
            base_stats=base_stats,
            bst=bst,
            abilities=abilities,
            evolution_chain=evolution_chain,
            type_matchups=type_matchups,
            stab_types=stab_types,
        )
