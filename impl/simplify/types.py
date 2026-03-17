from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

Point = Tuple[float, float]


@dataclass
class Curve:
    curve_id: str
    category: str
    source: str
    geom_type: str
    points: List[Point]

    @property
    def vertex_count(self) -> int:
        return len(self.points)
