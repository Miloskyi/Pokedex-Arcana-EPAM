"""Team Builder Agent — recommends competitive team partners for a given lead Pokémon.

Flow
----
1. Validate the requested tier against the hardcoded Smogon tier data.
2. Call OpenAI (structured output) to generate up to 5 partner recommendations.
3. Detect type overlap: if 2+ partners share the same primary type, add overlap_warnings.
4. Identify coverage gaps from the lead's type weaknesses (types with multiplier > 1.0).
5. Return a TeamResult.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from backend.llm_client import chat_complete
from backend.observability.tracing import trace_agent

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TeamMember:
    pokemon_name: str
    nature: str
    ev_spread: dict[str, int]
    held_item: str
    ability: str
    moveset: list[str]
    justification: str


@dataclass
class TeamResult:
    lead_pokemon: str
    tier: str
    partners: list[TeamMember]
    coverage_gaps: list[str]
    overlap_warnings: list[str]


# ---------------------------------------------------------------------------
# Hardcoded Smogon tier data (representative Pokémon per tier)
# ---------------------------------------------------------------------------

_SMOGON_TIERS: dict[str, list[str]] = {
    "OU": [
        "garchomp", "landorus-therian", "toxapex", "ferrothorn", "corviknight",
        "clefable", "heatran", "volcarona", "weavile", "dragapult",
        "urshifu-single-strike", "urshifu-rapid-strike", "rillaboom", "cinderace",
        "blissey", "slowbro", "slowking", "tapu-koko", "tapu-lele", "tapu-bulu",
        "tapu-fini", "kartana", "celesteela", "buzzwole", "pheromosa",
        "zapdos", "moltres", "articuno-galar", "tornadus-therian", "thundurus-therian",
        "gliscor", "garchomp", "excadrill", "tyranitar", "hippowdon",
        "rotom-wash", "rotom-heat", "magnezone", "scizor", "lucario",
        "alakazam", "gengar", "starmie", "latios", "latias",
        "iron-valiant", "iron-moth", "iron-treads", "great-tusk", "roaring-moon",
        "flutter-mane", "sandy-shocks", "walking-wake", "gouging-fire",
        "kingambit", "gholdengo", "skeledirge", "meowscarada", "iron-hands",
        "palafin", "annihilape", "clodsire", "dondozo", "tatsugiri",
    ],
    "UU": [
        "salamence", "hydreigon", "nidoking", "nidoqueen", "togekiss",
        "sylveon", "umbreon", "espeon", "jolteon", "vaporeon",
        "scrafty", "mienshao", "cobalion", "terrakion", "virizion",
        "azumarill", "mamoswine", "rhyperior", "donphan", "steelix",
        "empoleon", "infernape", "torterra", "roserade", "staraptor",
        "heracross", "sharpedo", "milotic", "flygon", "absol",
        "krookodile", "conkeldurr", "reuniclus", "chandelure", "haxorus",
        "bisharp", "mandibuzz", "braviary", "golurk", "cofagrigus",
        "arcanine", "ninetales", "ninetales-alola", "sandslash-alola", "raichu-alola",
    ],
    "RU": [
        "metagross", "aggron", "camerupt", "torkoal", "claydol",
        "slowking", "malamar", "barbaracle", "clawitzer", "dragalge",
        "vikavolt", "ribombee", "comfey", "tsareena", "lurantis",
        "mudsdale", "bewear", "passimian", "oranguru", "togedemaru",
        "incineroar", "primarina", "decidueye", "lycanroc", "mudbray",
        "toxicroak", "qwilfish", "skuntank", "drapion", "carnivine",
        "rotom-mow", "rotom-frost", "rotom-fan", "electivire", "magmortar",
    ],
    "NU": [
        "liepard", "purugly", "persian", "persian-alola", "meowth-galar",
        "simisage", "simisear", "simipour", "audino", "alomomola",
        "leavanny", "scolipede", "whimsicott", "lilligant", "sawsbuck",
        "emolga", "karrablast", "shelmet", "accelgor", "escavalier",
        "amoonguss", "foongus", "ferroseed", "klink", "klang",
        "elgyem", "beheeyem", "litwick", "lampent", "chandelure",
        "axew", "fraxure", "cubchoo", "beartic", "cryogonal",
        "shelmet", "stunfisk", "golett", "pawniard", "vullaby",
    ],
    "PU": [
        "rattata", "raticate", "pidgey", "pidgeot", "spearow",
        "fearow", "ekans", "arbok", "sandshrew", "sandslash",
        "nidoran-f", "nidoran-m", "clefairy", "jigglypuff", "zubat",
        "oddish", "paras", "venonat", "diglett", "meowth",
        "psyduck", "mankey", "growlithe", "poliwag", "abra",
        "machop", "bellsprout", "tentacool", "geodude", "ponyta",
        "slowpoke", "magnemite", "farfetchd", "doduo", "seel",
        "grimer", "shellder", "gastly", "onix", "drowzee",
        "krabby", "voltorb", "exeggcute", "cubone", "lickitung",
    ],
}

# All 18 types for coverage gap detection
_ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]

# Type chart: attacking_type → {defending_type: multiplier}
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


def _compute_weaknesses(defending_types: list[str]) -> list[str]:
    """Return attacking types that deal super-effective damage (multiplier > 1.0)."""
    weaknesses: list[str] = []
    for atk_type in _ALL_TYPES:
        multiplier = 1.0
        for def_type in defending_types:
            chart = _TYPE_CHART.get(atk_type, {})
            multiplier *= chart.get(def_type, 1.0)
        if multiplier > 1.0:
            weaknesses.append(atk_type)
    return weaknesses


_TEAM_SYSTEM_PROMPT = """\
You are a competitive Pokémon team-building expert with deep knowledge of Smogon formats.
Given a lead Pokémon and a competitive tier, recommend up to 5 partner Pokémon.

For each partner provide:
- pokemon_name: lowercase hyphenated name (e.g. "iron-valiant")
- nature: one of the 25 standard natures
- ev_spread: dict with keys hp, attack, defense, sp_atk, sp_def, speed (values 0-252, total ≤ 510)
- held_item: a competitive held item (e.g. "choice-scarf", "leftovers")
- ability: the ability name
- moveset: list of exactly 4 move names
- justification: 1-2 sentence explanation of why this partner complements the lead

Respond ONLY with a JSON array of partner objects. No extra text.
"""


class TeamBuilderAgent:
    """Recommends competitive team partners for a given lead Pokémon."""

    def _get_tier_pokemon(self, tier: str) -> list[str]:
        return _SMOGON_TIERS.get(tier.upper(), _SMOGON_TIERS["OU"])

    def _detect_overlap(self, partners: list[TeamMember]) -> list[str]:
        type_counts: dict[str, list[str]] = {}
        for partner in partners:
            pt = getattr(partner, "_primary_type", None)
            if pt:
                type_counts.setdefault(pt, []).append(partner.pokemon_name)
        warnings: list[str] = []
        for ptype, names in type_counts.items():
            if len(names) >= 2:
                warnings.append(f"Type overlap ({ptype}): {', '.join(names)}")
        return warnings

    def _parse_partners(self, raw: list[dict], tier_pokemon: list[str]) -> list[TeamMember]:
        partners: list[TeamMember] = []
        for item in raw[:5]:
            name = str(item.get("pokemon_name", "")).lower().strip()
            ev_raw = item.get("ev_spread", {})
            ev_spread = {
                k: int(v) for k, v in ev_raw.items()
                if k in ("hp", "attack", "defense", "sp_atk", "sp_def", "speed")
            }
            moveset = [str(m) for m in item.get("moveset", [])][:4]
            member = TeamMember(
                pokemon_name=name,
                nature=str(item.get("nature", "hardy")),
                ev_spread=ev_spread,
                held_item=str(item.get("held_item", "leftovers")),
                ability=str(item.get("ability", "")),
                moveset=moveset,
                justification=str(item.get("justification", "")),
            )
            member._primary_type = str(item.get("primary_type", "")).lower()  # type: ignore[attr-defined]
            partners.append(member)
        return partners

    @trace_agent("team_builder")
    async def run(self, lead_pokemon: str, tier: str = "OU") -> TeamResult:
        tier_upper = tier.upper()
        tier_pokemon = self._get_tier_pokemon(tier_upper)

        user_prompt = (
            f"Lead Pokémon: {lead_pokemon}\n"
            f"Competitive tier: {tier_upper}\n"
            f"Recommend up to 5 partner Pokémon. "
            f"For each partner, also include a 'primary_type' field with the Pokémon's "
            f"primary (first) type so overlap detection can work correctly."
        )

        try:
            content = await chat_complete(
                messages=[
                    {"role": "system", "content": _TEAM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
                json_mode=True,
            )
            parsed = json.loads(content)
            if isinstance(parsed, list):
                raw_partners = parsed
            else:
                raw_partners = (
                    parsed.get("partners")
                    or parsed.get("team")
                    or parsed.get("recommendations")
                    or []
                )
        except Exception:
            raw_partners = []

        partners = self._parse_partners(raw_partners, tier_pokemon)
        overlap_warnings = self._detect_overlap(partners)

        lead_weaknesses = _compute_weaknesses(
            _LEAD_TYPE_HINTS.get(lead_pokemon.lower(), ["normal"])
        )
        partner_types = {getattr(p, "_primary_type", "") for p in partners}
        coverage_gaps = [w for w in lead_weaknesses if w not in partner_types]

        return TeamResult(
            lead_pokemon=lead_pokemon,
            tier=tier_upper,
            partners=partners,
            coverage_gaps=coverage_gaps,
            overlap_warnings=overlap_warnings,
        )


# ---------------------------------------------------------------------------
# Lightweight type hints for common lead Pokémon (used for coverage gap calc)
# A real implementation would call StatsAgent; this avoids a circular import.
# ---------------------------------------------------------------------------

_LEAD_TYPE_HINTS: dict[str, list[str]] = {
    "garchomp": ["dragon", "ground"],
    "charizard": ["fire", "flying"],
    "blastoise": ["water"],
    "venusaur": ["grass", "poison"],
    "pikachu": ["electric"],
    "gengar": ["ghost", "poison"],
    "tyranitar": ["rock", "dark"],
    "dragonite": ["dragon", "flying"],
    "mewtwo": ["psychic"],
    "lucario": ["fighting", "steel"],
    "togekiss": ["fairy", "flying"],
    "ferrothorn": ["grass", "steel"],
    "toxapex": ["poison", "water"],
    "corviknight": ["flying", "steel"],
    "heatran": ["fire", "steel"],
    "landorus-therian": ["ground", "flying"],
    "clefable": ["fairy"],
    "volcarona": ["bug", "fire"],
    "weavile": ["dark", "ice"],
    "dragapult": ["dragon", "ghost"],
    "iron-valiant": ["fairy", "fighting"],
    "gholdengo": ["steel", "ghost"],
    "kingambit": ["dark", "steel"],
    "great-tusk": ["ground", "fighting"],
    "flutter-mane": ["ghost", "fairy"],
}
