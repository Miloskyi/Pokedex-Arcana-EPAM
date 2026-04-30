"""Report Agent — generates structured Markdown (and optionally PDF) reports.

Sections generated:
  ## Base Stats
  ## Type Matchups
  ## Abilities
  ## Movesets
  ## Competitive Notes

Flow
----
1. Fetch Pokémon data via PokéAPI (httpx).
2. Build each Markdown section; on failure add to missing_sections and continue.
3. Call DataVizAgent.radar_chart() to get a visualization artifact.
4. If include_pdf=True: convert Markdown → HTML → PDF via WeasyPrint.
5. Return ReportResult (never raise).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Optional

import httpx

from backend.observability.tracing import trace_agent
from backend.agents.dataviz_agent import DataVizAgent, VizResult

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ReportResult:
    pokemon_name: str
    markdown: str
    pdf_bytes: Optional[bytes]
    visualizations: list[VizResult]
    missing_sections: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POKEAPI_BASE = "https://pokeapi.co/api/v2"

_ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]

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
    matchups: dict[str, float] = {}
    for atk_type in _ALL_TYPES:
        multiplier = 1.0
        for def_type in defending_types:
            chart = _TYPE_CHART.get(atk_type, {})
            multiplier *= chart.get(def_type, 1.0)
        matchups[atk_type] = multiplier
    return matchups


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    sep = " | ".join(["---"] * len(headers))
    header_row = " | ".join(headers)
    lines = [f"| {header_row} |", f"| {sep} |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


class ReportAgent:
    """Generates structured Markdown (and optionally PDF) Pokémon reports."""

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        self._dataviz = DataVizAgent()

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=15.0)
        return self._http_client

    async def _fetch_pokemon(self, name: str) -> dict:
        client = self._get_client()
        resp = await client.get(f"{_POKEAPI_BASE}/pokemon/{name.lower()}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _section_base_stats(self, data: dict) -> str:
        stat_map = {
            "hp": "HP", "attack": "Attack", "defense": "Defense",
            "special-attack": "Sp. Atk", "special-defense": "Sp. Def", "speed": "Speed",
        }
        rows = []
        bst = 0
        for entry in data.get("stats", []):
            api_name = entry["stat"]["name"]
            label = stat_map.get(api_name, api_name)
            val = entry["base_stat"]
            bst += val
            rows.append([label, str(val)])
        rows.append(["**BST**", f"**{bst}**"])
        return "## Base Stats\n\n" + _markdown_table(["Stat", "Value"], rows)

    def _section_type_matchups(self, data: dict) -> str:
        types = [t["type"]["name"] for t in sorted(data.get("types", []), key=lambda x: x["slot"])]
        matchups = _compute_type_matchups(types)

        immune = [t for t, m in matchups.items() if m == 0.0]
        quarter = [t for t, m in matchups.items() if m == 0.25]
        half = [t for t, m in matchups.items() if m == 0.5]
        neutral = [t for t, m in matchups.items() if m == 1.0]
        double = [t for t, m in matchups.items() if m == 2.0]
        quad = [t for t, m in matchups.items() if m == 4.0]

        lines = ["## Type Matchups", ""]
        lines.append(f"**Types:** {', '.join(t.title() for t in types)}")
        lines.append("")
        if immune:
            lines.append(f"**Immune (0×):** {', '.join(t.title() for t in immune)}")
        if quarter:
            lines.append(f"**Quarter damage (¼×):** {', '.join(t.title() for t in quarter)}")
        if half:
            lines.append(f"**Resists (½×):** {', '.join(t.title() for t in half)}")
        if neutral:
            lines.append(f"**Neutral (1×):** {', '.join(t.title() for t in neutral)}")
        if double:
            lines.append(f"**Weak (2×):** {', '.join(t.title() for t in double)}")
        if quad:
            lines.append(f"**4× Weak:** {', '.join(t.title() for t in quad)}")
        return "\n".join(lines)

    def _section_abilities(self, data: dict) -> str:
        abilities = data.get("abilities", [])
        rows = []
        for a in abilities:
            name = a["ability"]["name"].replace("-", " ").title()
            hidden = "Yes" if a["is_hidden"] else "No"
            rows.append([name, hidden])
        return "## Abilities\n\n" + _markdown_table(["Ability", "Hidden"], rows)

    def _section_movesets(self, data: dict) -> str:
        moves = data.get("moves", [])
        # Show up to 20 moves to keep the report concise
        sample = moves[:20]
        rows = [[m["move"]["name"].replace("-", " ").title()] for m in sample]
        if len(moves) > 20:
            rows.append([f"... and {len(moves) - 20} more"])
        return "## Movesets\n\n" + _markdown_table(["Move"], rows)

    def _section_competitive_notes(
        self,
        data: dict,
        damage_results: list | None,
        verification_status: dict | None,
    ) -> str:
        types = [t["type"]["name"] for t in sorted(data.get("types", []), key=lambda x: x["slot"])]
        matchups = _compute_type_matchups(types)
        weaknesses = [t for t, m in matchups.items() if m > 1.0]
        resistances = [t for t, m in matchups.items() if 0 < m < 1.0]

        lines = ["## Competitive Notes", ""]
        lines.append(f"**Weaknesses:** {', '.join(t.title() for t in weaknesses) or 'None'}")
        lines.append(f"**Resistances:** {', '.join(t.title() for t in resistances) or 'None'}")

        if damage_results:
            lines.append("")
            lines.append("### Damage Calculation Results")
            for dr in damage_results:
                if hasattr(dr, "attacker"):
                    lines.append(
                        f"- {dr.attacker} → {dr.move} → {dr.defender}: "
                        f"{dr.min_percent}%–{dr.max_percent}%"
                    )
                elif isinstance(dr, dict):
                    lines.append(f"- {dr}")

        if verification_status:
            lines.append("")
            lines.append("### Verification Status")
            verified = verification_status.get("verified", False)
            discrepancy = verification_status.get("discrepancy_detected", False)
            badge = "✅ Verified" if verified and not discrepancy else "⚠️ Discrepancy detected"
            lines.append(f"**Status:** {badge}")
            if discrepancy:
                lines.append(
                    f"- Agent value: {verification_status.get('agent_value')}, "
                    f"Reference value: {verification_status.get('reference_value')}"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # PDF conversion
    # ------------------------------------------------------------------

    def _markdown_to_pdf(self, markdown: str, pokemon_name: str) -> bytes:
        """Convert Markdown to PDF via WeasyPrint. Raises if WeasyPrint unavailable."""
        try:
            from weasyprint import HTML  # type: ignore
        except ImportError as exc:
            raise ImportError("weasyprint is not installed") from exc

        # Simple Markdown → HTML conversion (no external dep)
        html_body = self._simple_md_to_html(markdown)
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{pokemon_name.title()} Report</title>
<style>
  body {{ font-family: sans-serif; margin: 2cm; }}
  h1 {{ color: #CC0000; }}
  h2 {{ color: #1E3A5F; border-bottom: 1px solid #ccc; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; }}
  th {{ background: #f0f0f0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes

    def _simple_md_to_html(self, md: str) -> str:
        """Minimal Markdown → HTML (headings, bold, tables, paragraphs)."""
        import re
        lines = md.split("\n")
        html_lines: list[str] = []
        in_table = False

        for line in lines:
            # Headings
            if line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            # Table rows
            elif line.startswith("|"):
                if not in_table:
                    html_lines.append("<table>")
                    in_table = True
                cells = [c.strip() for c in line.strip("|").split("|")]
                # Skip separator rows
                if all(set(c.replace("-", "").replace(" ", "")) == set() or c.strip("-") == "" for c in cells):
                    continue
                tag = "th" if not any("<td>" in l for l in html_lines[-3:]) else "td"
                row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
                html_lines.append(f"<tr>{row}</tr>")
            else:
                if in_table:
                    html_lines.append("</table>")
                    in_table = False
                # Bold
                line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                if line.strip():
                    html_lines.append(f"<p>{line}</p>")

        if in_table:
            html_lines.append("</table>")

        return "\n".join(html_lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @trace_agent("report")
    async def run(
        self,
        pokemon_name: str,
        include_pdf: bool = False,
        damage_results: list | None = None,
        verification_status: dict | None = None,
    ) -> ReportResult:
        """Generate a Markdown (and optionally PDF) report for *pokemon_name*.

        Args:
            pokemon_name:        The Pokémon to report on.
            include_pdf:         If True, also generate a PDF via WeasyPrint.
            damage_results:      Optional list of DamageResult objects to include.
            verification_status: Optional VerificationResult dict to include.

        Returns:
            ReportResult — never raises; failures go into missing_sections.
        """
        missing_sections: list[str] = []
        sections: list[str] = []
        visualizations: list[VizResult] = []
        pokemon_data: dict | None = None

        # Fetch Pokémon data
        try:
            pokemon_data = await self._fetch_pokemon(pokemon_name)
        except Exception as exc:
            missing_sections.append("pokemon_data")
            # Return minimal report immediately if we can't fetch data
            return ReportResult(
                pokemon_name=pokemon_name,
                markdown=f"# {pokemon_name.title()} Report\n\n*Data unavailable: {exc}*",
                pdf_bytes=None,
                visualizations=[],
                missing_sections=missing_sections,
            )

        # Title
        display_name = pokemon_data.get("name", pokemon_name).title()
        sections.append(f"# {display_name} Report\n")

        # Base Stats section
        try:
            sections.append(self._section_base_stats(pokemon_data))
        except Exception:
            missing_sections.append("base_stats")

        # Type Matchups section
        try:
            sections.append(self._section_type_matchups(pokemon_data))
        except Exception:
            missing_sections.append("type_matchups")

        # Abilities section
        try:
            sections.append(self._section_abilities(pokemon_data))
        except Exception:
            missing_sections.append("abilities")

        # Movesets section
        try:
            sections.append(self._section_movesets(pokemon_data))
        except Exception:
            missing_sections.append("movesets")

        # Competitive Notes section
        try:
            sections.append(
                self._section_competitive_notes(
                    pokemon_data, damage_results, verification_status
                )
            )
        except Exception:
            missing_sections.append("competitive_notes")

        # Radar chart visualization
        try:
            stat_map = {
                "hp": "hp", "attack": "attack", "defense": "defense",
                "special-attack": "sp_atk", "special-defense": "sp_def", "speed": "speed",
            }
            stats_dict: dict[str, int] = {}
            for entry in pokemon_data.get("stats", []):
                key = stat_map.get(entry["stat"]["name"])
                if key:
                    stats_dict[key] = entry["base_stat"]
            viz = await self._dataviz.radar_chart(stats_dict, display_name)
            visualizations.append(viz)
            # Embed a note in the markdown
            sections.append(
                f"\n## Visualization\n\n"
                f"*Radar chart generated for {display_name} base stats.*"
            )
        except Exception:
            missing_sections.append("visualization")

        markdown = "\n\n".join(sections)

        # PDF generation
        pdf_bytes: Optional[bytes] = None
        if include_pdf:
            try:
                pdf_bytes = self._markdown_to_pdf(markdown, display_name)
            except ImportError:
                missing_sections.append("pdf")
            except Exception:
                missing_sections.append("pdf")

        return ReportResult(
            pokemon_name=pokemon_name,
            markdown=markdown,
            pdf_bytes=pdf_bytes,
            visualizations=visualizations,
            missing_sections=missing_sections,
        )
