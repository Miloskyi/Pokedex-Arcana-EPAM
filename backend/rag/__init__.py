from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["ScoredDoc"]


@dataclass
class ScoredDoc:
    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
