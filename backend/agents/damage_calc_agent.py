"""Damage Calc Agent — implements the Gen IX damage formula in pure Python.

Formula (official):
    Damage = floor(floor(floor(2×Level/5+2) × BasePower × [Atk/Def]) / 50 + 2)
             × Targets × Weather × Badge × Critical × Random
             × STAB × Type1 × Type2 × Burn × Other

Random factor: 15 rolls from 0.85 to 1.0 in steps of 1/256×15 ≈ 0.0586.
The agent returns min and max of those 15 rolls.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from backend.observability.tracing import trace_agent

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class DamageResult:
    attacker: str
    move: str
    defender: str
    min_damage: int
    max_damage: int
    min_percent: float
    max_percent: float
    modifiers_applied: dict[str, Any]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Type effectiveness chart (attacking → defending)
# ---------------------------------------------------------------------------

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

# Nature modifiers: (boosted_stat, reduced_stat) → multiplier
_NATURE_TABLE: dict[str, tuple[str, str]] = {
    "hardy":   ("", ""),
    "lonely":  ("attack", "defense"),
    "brave":   ("attack", "speed"),
    "adamant": ("attack", "sp_atk"),
    "naughty": ("attack", "sp_def"),
    "bold":    ("defense", "attack"),
    "docile":  ("", ""),
    "relaxed": ("defense", "speed"),
    "impish":  ("defense", "sp_atk"),
    "lax":     ("defense", "sp_def"),
    "timid":   ("speed", "attack"),
    "hasty":   ("speed", "defense"),
    "serious": ("", ""),
    "jolly":   ("speed", "sp_atk"),
    "naive":   ("speed", "sp_def"),
    "modest":  ("sp_atk", "attack"),
    "mild":    ("sp_atk", "defense"),
    "quiet":   ("sp_atk", "speed"),
    "bashful": ("", ""),
    "rash":    ("sp_atk", "sp_def"),
    "calm":    ("sp_def", "attack"),
    "gentle":  ("sp_def", "defense"),
    "sassy":   ("sp_def", "speed"),
    "careful": ("sp_def", "sp_atk"),
    "quirky":  ("", ""),
}

_WEATHER_MODIFIERS: dict[str, dict[str, float]] = {
    "sun":  {"fire": 1.5, "water": 0.5},
    "rain": {"water": 1.5, "fire": 0.5},
    "sand": {},
    "hail": {},
    "snow": {},
    "none": {},
}

_TERRAIN_MODIFIERS: dict[str, dict[str, float]] = {
    "electric": {"electric": 1.3},
    "grassy":   {"grass": 1.3},
    "misty":    {"dragon": 0.5},
    "psychic":  {"psychic": 1.3},
    "none":     {},
}

_ITEM_MODIFIERS: dict[str, float] = {
    "choice-band":   1.5,   # physical attack
    "choice-specs":  1.5,   # special attack
    "life-orb":      1.3,
    "expert-belt":   1.2,   # super-effective only
    "none":          1.0,
}

_POKEAPI_BASE = "https://pokeapi.co/api/v2"


def _nature_multiplier(nature: str, stat: str) -> float:
    entry = _NATURE_TABLE.get(nature.lower(), ("", ""))
    boosted, reduced = entry
    if stat == boosted:
        return 1.1
    if stat == reduced:
        return 0.9
    return 1.0


def _compute_stat(
    base: int,
    iv: int,
    ev: int,
    level: int,
    nature: str,
    stat_name: str,
    is_hp: bool = False,
) -> int:
    """Compute a single stat value using the Gen III+ formula."""
    if is_hp:
        return int((2 * base + iv + ev // 4) * level / 100) + level + 10
    raw = int((2 * base + iv + ev // 4) * level / 100) + 5
    return int(raw * _nature_multiplier(nature, stat_name))


def _type_effectiveness(move_type: str, defender_types: list[str]) -> float:
    chart = _TYPE_CHART.get(move_type, {})
    multiplier = 1.0
    for def_type in defender_types:
        multiplier *= chart.get(def_type, 1.0)
    return multiplier


def _compute_damage_rolls(
    level: int,
    base_power: int,
    attack_stat: int,
    defense_stat: int,
    stab: float,
    type_eff: float,
    weather_mod: float,
    terrain_mod: float,
    item_mod: float,
    burn_mod: float,
    is_super_effective: bool,
    held_item: str,
) -> list[int]:
    """Compute all 15 damage rolls for the Gen IX formula."""
    # Expert Belt only applies on super-effective hits
    effective_item_mod = item_mod
    if held_item == "expert-belt" and not is_super_effective:
        effective_item_mod = 1.0

    base = (
        (2 * level // 5 + 2) * base_power * attack_stat // defense_stat
    ) // 50 + 2

    rolls: list[int] = []
    for i in range(15):
        random_factor = (85 + i) / 100.0  # 0.85 to 0.99 in steps of 0.01
        dmg = base
        dmg = int(dmg * weather_mod)
        dmg = int(dmg * terrain_mod)
        dmg = int(dmg * stab)
        dmg = int(dmg * type_eff)
        dmg = int(dmg * burn_mod)
        dmg = int(dmg * effective_item_mod)
        dmg = int(dmg * random_factor)
        rolls.append(max(1, dmg))
    return rolls


class DamageCalcAgent:
    """Implements the Gen IX damage formula and returns a DamageResult."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def _fetch_json(self, url: str) -> dict:
        client = self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_pokemon(self, name: str) -> dict:
        return await self._fetch_json(f"{_POKEAPI_BASE}/pokemon/{name.lower()}")

    async def _fetch_move(self, name: str) -> dict:
        return await self._fetch_json(f"{_POKEAPI_BASE}/move/{name.lower()}")

    def _get_base_stat(self, stats: list[dict], stat_name: str) -> int:
        for s in stats:
            if s["stat"]["name"] == stat_name:
                return s["base_stat"]
        return 50  # fallback

    def _get_types(self, types_data: list[dict]) -> list[str]:
        return [t["type"]["name"] for t in sorted(types_data, key=lambda x: x["slot"])]

    @trace_agent("damage_calc")
    async def run(
        self,
        attacker_name: str,
        move_name: str,
        defender_name: str,
        attacker_level: int = 50,
        attacker_nature: str = "hardy",
        attacker_evs: dict | None = None,
        attacker_ivs: dict | None = None,
        defender_evs: dict | None = None,
        defender_ivs: dict | None = None,
        weather: str = "none",
        terrain: str = "none",
        held_item: str = "none",
    ) -> DamageResult:
        """Compute damage range for attacker using move against defender."""
        if attacker_evs is None:
            attacker_evs = {}
        if attacker_ivs is None:
            attacker_ivs = {s: 31 for s in ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]}
        if defender_evs is None:
            defender_evs = {}
        if defender_ivs is None:
            defender_ivs = {s: 31 for s in ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]}

        try:
            attacker_data, move_data, defender_data = await _gather(
                self._fetch_pokemon(attacker_name),
                self._fetch_move(move_name),
                self._fetch_pokemon(defender_name),
            )
        except httpx.HTTPStatusError as exc:
            return DamageResult(
                attacker=attacker_name,
                move=move_name,
                defender=defender_name,
                min_damage=0,
                max_damage=0,
                min_percent=0.0,
                max_percent=0.0,
                modifiers_applied={},
                error=f"PokéAPI error {exc.response.status_code}: {exc.request.url}",
            )

        move_type = move_data["type"]["name"]
        base_power = move_data.get("power") or 0
        damage_class = move_data["damage_class"]["name"]  # physical / special / status

        if damage_class == "status" or base_power == 0:
            return DamageResult(
                attacker=attacker_name,
                move=move_name,
                defender=defender_name,
                min_damage=0,
                max_damage=0,
                min_percent=0.0,
                max_percent=0.0,
                modifiers_applied={"damage_class": damage_class},
                error=f"Move '{move_name}' is a status move with no damage.",
            )

        attacker_types = self._get_types(attacker_data["types"])
        defender_types = self._get_types(defender_data["types"])

        # Determine which attack/defense stats to use
        if damage_class == "physical":
            atk_stat_name = "attack"
            def_stat_name = "defense"
        else:
            atk_stat_name = "special-attack"
            def_stat_name = "special-defense"

        atk_base = self._get_base_stat(attacker_data["stats"], atk_stat_name)
        def_base = self._get_base_stat(defender_data["stats"], def_stat_name)
        def_hp_base = self._get_base_stat(defender_data["stats"], "hp")

        atk_iv = attacker_ivs.get(atk_stat_name.replace("-", "_").replace("special_attack", "sp_atk"), 31)
        atk_ev = attacker_evs.get(atk_stat_name.replace("-", "_").replace("special_attack", "sp_atk"), 0)
        def_iv = defender_ivs.get(def_stat_name.replace("-", "_").replace("special_defense", "sp_def"), 31)
        def_ev = defender_evs.get(def_stat_name.replace("-", "_").replace("special_defense", "sp_def"), 0)
        def_hp_iv = defender_ivs.get("hp", 31)
        def_hp_ev = defender_evs.get("hp", 0)

        nature_stat = "attack" if damage_class == "physical" else "sp_atk"
        attack_stat = _compute_stat(atk_base, atk_iv, atk_ev, attacker_level, attacker_nature, nature_stat)
        defense_stat = _compute_stat(def_base, def_iv, def_ev, 50, "hardy", "defense")
        defender_hp = _compute_stat(def_hp_base, def_hp_iv, def_hp_ev, 50, "hardy", "hp", is_hp=True)

        # STAB
        stab = 1.5 if move_type in attacker_types else 1.0

        # Type effectiveness
        type_eff = _type_effectiveness(move_type, defender_types)
        is_super_effective = type_eff > 1.0

        # Weather modifier
        weather_mods = _WEATHER_MODIFIERS.get(weather.lower(), {})
        weather_mod = weather_mods.get(move_type, 1.0)

        # Terrain modifier
        terrain_mods = _TERRAIN_MODIFIERS.get(terrain.lower(), {})
        terrain_mod = terrain_mods.get(move_type, 1.0)

        # Item modifier
        item_mod = _ITEM_MODIFIERS.get(held_item.lower(), 1.0)

        # Burn: halves physical damage if attacker is burned (not modeled here — no status input)
        burn_mod = 1.0

        rolls = _compute_damage_rolls(
            level=attacker_level,
            base_power=base_power,
            attack_stat=attack_stat,
            defense_stat=defense_stat,
            stab=stab,
            type_eff=type_eff,
            weather_mod=weather_mod,
            terrain_mod=terrain_mod,
            item_mod=item_mod,
            burn_mod=burn_mod,
            is_super_effective=is_super_effective,
            held_item=held_item.lower(),
        )

        min_dmg = min(rolls)
        max_dmg = max(rolls)
        min_pct = round(min_dmg / defender_hp * 100, 2) if defender_hp > 0 else 0.0
        max_pct = round(max_dmg / defender_hp * 100, 2) if defender_hp > 0 else 0.0

        modifiers_applied = {
            "stab": stab,
            "type_effectiveness": type_eff,
            "weather": weather_mod,
            "terrain": terrain_mod,
            "item": item_mod,
            "burn": burn_mod,
            "damage_class": damage_class,
            "move_type": move_type,
            "attacker_types": attacker_types,
            "defender_types": defender_types,
            "attack_stat": attack_stat,
            "defense_stat": defense_stat,
            "defender_hp": defender_hp,
            "base_power": base_power,
        }

        return DamageResult(
            attacker=attacker_name,
            move=move_name,
            defender=defender_name,
            min_damage=min_dmg,
            max_damage=max_dmg,
            min_percent=min_pct,
            max_percent=max_pct,
            modifiers_applied=modifiers_applied,
        )


async def _gather(*coros):
    """Run coroutines concurrently."""
    return await asyncio.gather(*coros)
