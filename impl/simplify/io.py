from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from .types import Curve, Point


def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _to_lines(geom: dict) -> List[List[Point]]:
    gtype = geom.get("type")
    c = geom.get("coordinates")
    out: List[List[Point]] = []

    if gtype == "LineString":
        if c:
            out.append([(float(x), float(y)) for x, y, *rest in c])
    elif gtype == "MultiLineString":
        for ls in c or []:
            if ls:
                out.append([(float(x), float(y)) for x, y, *rest in ls])
    elif gtype == "Polygon":
        for ring in c or []:
            if ring:
                out.append([(float(x), float(y)) for x, y, *rest in ring])
    elif gtype == "MultiPolygon":
        for poly in c or []:
            for ring in poly or []:
                if ring:
                    out.append([(float(x), float(y)) for x, y, *rest in ring])
    return [ln for ln in out if len(ln) >= 2]


def _pick_polyline(lines: Sequence[Sequence[Point]]) -> List[Point]:
    if not lines:
        return []
    line = max((list(ln) for ln in lines if len(ln) >= 2), key=len, default=[])
    if len(line) >= 2 and line[0] == line[-1]:
        line = line[:-1]
    return line


def load_curves(path: Path, default_category: str) -> List[Curve]:
    obj = load_geojson(path)
    feats = obj.get("features", []) if obj.get("type") == "FeatureCollection" else []
    curves: List[Curve] = []

    for i, feat in enumerate(feats):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        lines = _to_lines(geom)
        pts = _pick_polyline(lines)
        if len(pts) < 2:
            continue

        curve_id = str(props.get("id") or props.get("feature_id") or props.get("CountyName") or f"curve_{i}")
        category = str(props.get("category") or default_category)
        source = str(props.get("source") or path.name)
        geom_type = str(geom.get("type", "Unknown"))

        curves.append(
            Curve(
                curve_id=curve_id,
                category=category,
                source=source,
                geom_type=geom_type,
                points=pts,
            )
        )

    return curves


def size_bin(vertex_count: int) -> str:
    if vertex_count < 500:
        return "small"
    if 5000 <= vertex_count <= 20000:
        return "medium"
    if vertex_count > 100000:
        return "large"
    return "other"


def select_curves(
    curves: Sequence[Curve],
    max_per_bin: int,
    include_bins: Sequence[str] = ("small", "medium", "large"),
) -> List[Curve]:
    bins: Dict[str, List[Curve]] = {k: [] for k in include_bins}

    for c in sorted(curves, key=lambda x: x.vertex_count):
        b = size_bin(c.vertex_count)
        if b in bins:
            bins[b].append(c)

    out: List[Curve] = []
    for b in include_bins:
        group = bins[b]
        if not group:
            continue
        if len(group) <= max_per_bin:
            out.extend(group)
            continue

        # Deterministic spread sampling across sizes.
        step = (len(group) - 1) / max(1, max_per_bin - 1)
        picks = [group[round(i * step)] for i in range(max_per_bin)]
        out.extend(picks)

    return out
