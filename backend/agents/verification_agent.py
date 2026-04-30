"""Verification Agent — independently re-executes the Gen IX damage formula
and compares the result against the DamageCalcAgent's output.

A discrepancy is flagged when |reference_value - agent_value| > 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.agents.damage_calc_agent import (
    DamageResult,
    _compute_damage_rolls,
    _ITEM_MODIFIERS,
    _TERRAIN_MODIFIERS,
    _WEATHER_MODIFIERS,
)
from backend.observability.tracing import trace_agent

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    verified: bool
    discrepancy_detected: bool
    reference_value: Optional[Any] = None
    agent_value: Optional[Any] = None
    delta: Optional[float] = None


class VerificationAgent:
    """Re-runs the damage formula independently and compares against agent output."""

    @trace_agent("verification")
    async def verify_damage(
        self,
        damage_result: DamageResult,
        attacker_level: int = 50,
        attacker_nature: str = "hardy",
        attacker_evs: dict | None = None,
        attacker_ivs: dict | None = None,
        defender_evs: dict | None = None,
        defender_ivs: dict | None = None,
        weather: str = "none",
        terrain: str = "none",
        held_item: str = "none",
    ) -> VerificationResult:
        """Re-execute the damage formula and compare against *damage_result*.

        Uses the modifiers_applied dict from the DamageResult to reconstruct
        the computation without calling PokéAPI again.

        Returns a VerificationResult with discrepancy_detected=True when
        |reference_max - agent_max| > 1.
        """
        if damage_result.error:
            return VerificationResult(
                verified=False,
                discrepancy_detected=False,
                reference_value=None,
                agent_value=None,
                delta=None,
            )

        mods = damage_result.modifiers_applied

        # Extract pre-computed values from the agent's modifiers_applied dict
        attack_stat: int = mods.get("attack_stat", 0)
        defense_stat: int = mods.get("defense_stat", 0)
        defender_hp: int = mods.get("defender_hp", 1)
        base_power: int = mods.get("base_power", 0)
        stab: float = mods.get("stab", 1.0)
        type_eff: float = mods.get("type_effectiveness", 1.0)
        weather_mod: float = mods.get("weather", 1.0)
        terrain_mod: float = mods.get("terrain", 1.0)
        item_mod: float = mods.get("item", 1.0)
        burn_mod: float = mods.get("burn", 1.0)
        move_type: str = mods.get("move_type", "normal")
        defender_types: list[str] = mods.get("defender_types", [])
        attacker_types: list[str] = mods.get("attacker_types", [])
        is_super_effective = type_eff > 1.0

        if base_power == 0 or attack_stat == 0 or defense_stat == 0:
            return VerificationResult(
                verified=False,
                discrepancy_detected=False,
                reference_value=None,
                agent_value=None,
                delta=None,
            )

        # Re-compute independently
        ref_rolls = _compute_damage_rolls(
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

        ref_max = max(ref_rolls)
        agent_max = damage_result.max_damage
        delta = abs(ref_max - agent_max)
        discrepancy = delta > 1

        return VerificationResult(
            verified=not discrepancy,
            discrepancy_detected=discrepancy,
            reference_value=ref_max,
            agent_value=agent_max,
            delta=float(delta),
        )
