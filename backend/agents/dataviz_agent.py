"""DataViz Agent — generates visual artifacts for Pokémon data.

Produces:
- Radar chart: 6 base stats scaled 0–255
- Type effectiveness grid: 18 type entries with multipliers
- Evolution chain diagram: N nodes connected by arrows
- BST grouped bar chart: N Pokémon × 6 stat bars

All charts are returned as SVG strings (format="svg").
"""
from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from backend.observability.tracing import trace_agent

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class VizResult:
    viz_type: str   # "radar", "type_grid", "evolution", "bst_bar"
    format: str     # "svg" or "png"
    data: str       # SVG string or base64-encoded PNG
    title: str


# ---------------------------------------------------------------------------
# Type color map (official Pokémon type colors)
# ---------------------------------------------------------------------------

_TYPE_COLORS: dict[str, str] = {
    "normal":   "#A8A878",
    "fire":     "#F08030",
    "water":    "#6890F0",
    "electric": "#F8D030",
    "grass":    "#78C850",
    "ice":      "#98D8D8",
    "fighting": "#C03028",
    "poison":   "#A040A0",
    "ground":   "#E0C068",
    "flying":   "#A890F0",
    "psychic":  "#F85888",
    "bug":      "#A8B820",
    "rock":     "#B8A038",
    "ghost":    "#705898",
    "dragon":   "#7038F8",
    "dark":     "#705848",
    "steel":    "#B8B8D0",
    "fairy":    "#EE99AC",
}

_ALL_TYPES = list(_TYPE_COLORS.keys())

_STAT_LABELS = ["HP", "Attack", "Defense", "Sp. Atk", "Sp. Def", "Speed"]
_STAT_KEYS   = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]


def _fig_to_svg(fig: plt.Figure) -> str:
    """Render a matplotlib figure to an SVG string."""
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


class DataVizAgent:
    """Generates visual artifacts for Pokémon data using matplotlib."""

    # ------------------------------------------------------------------
    # Radar chart
    # ------------------------------------------------------------------

    @trace_agent("dataviz")
    async def radar_chart(
        self,
        stats: dict[str, int],
        pokemon_name: str,
    ) -> VizResult:
        """Generate a radar chart for the 6 base stats (scale 0–255).

        Args:
            stats:        Dict with keys hp, attack, defense, sp_atk, sp_def, speed.
            pokemon_name: Pokémon name used as the chart title.

        Returns:
            VizResult with viz_type="radar", format="svg".
        """
        # Ensure all 6 stats are present; default missing to 0
        values = [min(255, max(0, stats.get(k, 0))) for k in _STAT_KEYS]

        N = len(_STAT_LABELS)
        angles = [n / float(N) * 2 * math.pi for n in range(N)]
        angles += angles[:1]  # close the polygon
        values_plot = values + values[:1]

        fig, ax = plt.subplots(figsize=(5, 5), subplot_kw={"polar": True})
        ax.set_theta_offset(math.pi / 2)
        ax.set_theta_direction(-1)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(_STAT_LABELS, size=9)
        ax.set_ylim(0, 255)
        ax.set_yticks([50, 100, 150, 200, 255])
        ax.set_yticklabels(["50", "100", "150", "200", "255"], size=7)

        ax.plot(angles, values_plot, linewidth=2, linestyle="solid", color="#CC0000")
        ax.fill(angles, values_plot, alpha=0.25, color="#CC0000")

        ax.set_title(
            f"{pokemon_name.title()} — Base Stats",
            size=11,
            fontweight="bold",
            pad=15,
        )

        svg_data = _fig_to_svg(fig)
        return VizResult(
            viz_type="radar",
            format="svg",
            data=svg_data,
            title=f"{pokemon_name.title()} Base Stats Radar",
        )

    # ------------------------------------------------------------------
    # Type effectiveness grid
    # ------------------------------------------------------------------

    @trace_agent("dataviz")
    async def type_effectiveness_grid(
        self,
        type_matchups: dict[str, float],
        pokemon_name: str,
    ) -> VizResult:
        """Generate a type effectiveness grid (18 entries).

        Args:
            type_matchups: Dict mapping each of the 18 attacking types to a multiplier.
            pokemon_name:  Pokémon name used as the chart title.

        Returns:
            VizResult with viz_type="type_grid", format="svg".
        """
        # Ensure all 18 types are present
        multipliers = [type_matchups.get(t, 1.0) for t in _ALL_TYPES]

        # Color-code cells by effectiveness
        def _cell_color(mult: float) -> str:
            if mult == 0.0:
                return "#555555"
            if mult == 0.25:
                return "#4CAF50"
            if mult == 0.5:
                return "#8BC34A"
            if mult == 1.0:
                return "#FFFFFF"
            if mult == 2.0:
                return "#FF9800"
            if mult == 4.0:
                return "#F44336"
            return "#FFFFFF"

        fig, ax = plt.subplots(figsize=(10, 3))
        ax.set_xlim(0, 18)
        ax.set_ylim(0, 1)
        ax.axis("off")

        for i, (t, mult) in enumerate(zip(_ALL_TYPES, multipliers)):
            x = i
            # Type color background
            type_color = _TYPE_COLORS.get(t, "#AAAAAA")
            ax.add_patch(mpatches.FancyBboxPatch(
                (x + 0.05, 0.55), 0.9, 0.38,
                boxstyle="round,pad=0.02",
                facecolor=type_color,
                edgecolor="none",
            ))
            ax.text(
                x + 0.5, 0.74, t.capitalize(),
                ha="center", va="center", fontsize=6.5, color="white",
                fontweight="bold",
            )
            # Multiplier cell
            cell_color = _cell_color(mult)
            ax.add_patch(mpatches.FancyBboxPatch(
                (x + 0.05, 0.05), 0.9, 0.42,
                boxstyle="round,pad=0.02",
                facecolor=cell_color,
                edgecolor="#CCCCCC",
                linewidth=0.5,
            ))
            label = "0×" if mult == 0 else f"{mult:g}×"
            ax.text(
                x + 0.5, 0.26, label,
                ha="center", va="center", fontsize=8,
                color="white" if mult == 0 else "black",
                fontweight="bold",
            )

        ax.set_title(
            f"{pokemon_name.title()} — Type Effectiveness",
            fontsize=11, fontweight="bold", pad=8,
        )

        svg_data = _fig_to_svg(fig)
        return VizResult(
            viz_type="type_grid",
            format="svg",
            data=svg_data,
            title=f"{pokemon_name.title()} Type Effectiveness Grid",
        )

    # ------------------------------------------------------------------
    # Evolution chain diagram
    # ------------------------------------------------------------------

    @trace_agent("dataviz")
    async def evolution_chain_diagram(
        self,
        chain: list[dict],
        pokemon_name: str,
    ) -> VizResult:
        """Generate an evolution chain diagram with N nodes.

        Args:
            chain:        List of stage dicts with keys: name, stage, trigger,
                          condition_detail.
            pokemon_name: Used as the chart title.

        Returns:
            VizResult with viz_type="evolution", format="svg".
        """
        n = len(chain)
        if n == 0:
            chain = [{"name": pokemon_name, "stage": 0, "trigger": None, "condition_detail": {}}]
            n = 1

        fig_width = max(4, n * 2.5)
        fig, ax = plt.subplots(figsize=(fig_width, 2.5))
        ax.set_xlim(-0.5, n - 0.5)
        ax.set_ylim(-0.5, 1.5)
        ax.axis("off")

        for i, stage in enumerate(chain):
            # Node circle
            circle = plt.Circle((i, 0.5), 0.35, color="#CC0000", zorder=3)
            ax.add_patch(circle)
            ax.text(
                i, 0.5, stage.get("name", "?").title(),
                ha="center", va="center", fontsize=7.5,
                color="white", fontweight="bold", zorder=4,
            )
            # Evolution condition label above arrow
            if i > 0:
                trigger = stage.get("trigger") or ""
                cond = stage.get("condition_detail") or {}
                cond_str = ""
                if cond.get("min_level"):
                    cond_str = f"Lv.{cond['min_level']}"
                elif cond.get("item"):
                    cond_str = cond["item"].replace("-", " ").title()
                elif trigger:
                    cond_str = trigger.replace("-", " ").title()
                ax.text(
                    i - 0.5, 1.1, cond_str,
                    ha="center", va="bottom", fontsize=6.5, color="#555555",
                )
                # Arrow
                ax.annotate(
                    "",
                    xy=(i - 0.36, 0.5),
                    xytext=(i - 1 + 0.36, 0.5),
                    arrowprops=dict(arrowstyle="->", color="#333333", lw=1.5),
                    zorder=2,
                )

        ax.set_title(
            f"{pokemon_name.title()} — Evolution Chain",
            fontsize=11, fontweight="bold",
        )

        svg_data = _fig_to_svg(fig)
        return VizResult(
            viz_type="evolution",
            format="svg",
            data=svg_data,
            title=f"{pokemon_name.title()} Evolution Chain",
        )

    # ------------------------------------------------------------------
    # BST grouped bar chart
    # ------------------------------------------------------------------

    @trace_agent("dataviz")
    async def bst_comparison_chart(
        self,
        pokemon_stats_list: list[dict],
    ) -> VizResult:
        """Generate a grouped bar chart comparing base stats across N Pokémon.

        Args:
            pokemon_stats_list: List of dicts, each with keys:
                                  name, hp, attack, defense, sp_atk, sp_def, speed.

        Returns:
            VizResult with viz_type="bst_bar", format="svg".
        """
        if not pokemon_stats_list:
            pokemon_stats_list = [{"name": "unknown", "hp": 0, "attack": 0,
                                   "defense": 0, "sp_atk": 0, "sp_def": 0, "speed": 0}]

        n = len(pokemon_stats_list)
        x = np.arange(n)
        bar_width = 0.12
        offsets = np.linspace(-(len(_STAT_KEYS) - 1) / 2, (len(_STAT_KEYS) - 1) / 2, len(_STAT_KEYS))
        stat_colors = ["#E53935", "#FB8C00", "#FDD835", "#43A047", "#1E88E5", "#8E24AA"]

        fig, ax = plt.subplots(figsize=(max(6, n * 2), 5))

        for j, (key, label, color) in enumerate(zip(_STAT_KEYS, _STAT_LABELS, stat_colors)):
            values = [min(255, max(0, p.get(key, 0))) for p in pokemon_stats_list]
            ax.bar(
                x + offsets[j] * bar_width,
                values,
                width=bar_width,
                label=label,
                color=color,
                alpha=0.85,
            )

        names = [p.get("name", f"Pokémon {i+1}").title() for i, p in enumerate(pokemon_stats_list)]
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontsize=9)
        ax.set_ylim(0, 270)
        ax.set_ylabel("Base Stat Value", fontsize=9)
        ax.set_title("BST Comparison", fontsize=11, fontweight="bold")
        ax.legend(loc="upper right", fontsize=8, ncol=3)
        ax.grid(axis="y", alpha=0.3)

        svg_data = _fig_to_svg(fig)
        title = "BST Comparison: " + ", ".join(names)
        return VizResult(
            viz_type="bst_bar",
            format="svg",
            data=svg_data,
            title=title,
        )
