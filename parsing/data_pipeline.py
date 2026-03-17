#!/usr/bin/env python3
"""End-to-end data pipeline for CSC 570 report prep.

Builds derived mechanical benchmark datasets from curated + Overpass inputs,
then runs characterization + diagrams over derived data.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

Point = Tuple[float, float]


def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_points(coords) -> int:
    if not isinstance(coords, list) or not coords:
        return 0
    if isinstance(coords[0], (int, float)):
        return 1
    return sum(count_points(c) for c in coords)


def flatten_lines(geom: dict) -> List[List[Point]]:
    gt = geom.get("type")
    c = geom.get("coordinates")
    out: List[List[Point]] = []

    if gt == "LineString":
        if c:
            out.append([(float(x), float(y)) for x, y, *rest in c])
    elif gt == "MultiLineString":
        for ls in c or []:
            if ls:
                out.append([(float(x), float(y)) for x, y, *rest in ls])
    elif gt == "Polygon":
        for ring in c or []:
            if ring:
                out.append([(float(x), float(y)) for x, y, *rest in ring])
    elif gt == "MultiPolygon":
        for poly in c or []:
            for ring in poly or []:
                if ring:
                    out.append([(float(x), float(y)) for x, y, *rest in ring])

    return [ln for ln in out if len(ln) >= 2]


def line_signature(line: Sequence[Point], ndigits: int = 7) -> Tuple[Tuple[float, float], ...]:
    a = tuple((round(p[0], ndigits), round(p[1], ndigits)) for p in line)
    b = tuple(reversed(a))
    return a if a <= b else b


def path_length(points: Sequence[Point]) -> float:
    return sum(math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]) for i in range(1, len(points)))


def concat_lines(lines: Sequence[Sequence[Point]]) -> List[Point]:
    # Runtime stress-test line: concatenate segments in a deterministic order.
    pts: List[Point] = []
    for line in lines:
        if not line:
            continue
        if not pts:
            pts.extend(line)
            continue
        if pts[-1] == line[0]:
            pts.extend(line[1:])
        else:
            pts.extend(line)
    return pts


def make_feature(fid: str, source: str, category: str, geom_type: str, coords, properties: dict | None = None) -> dict:
    props = {
        "id": fid,
        "source": source,
        "category": category,
    }
    if properties:
        props.update(properties)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": geom_type,
            "coordinates": coords,
        },
    }


def build_mechanical_derived(
    county_trails: Path,
    proposed_trails: Path,
    overpass_tiles: Sequence[Path],
    out_path: Path,
) -> Dict[str, int]:
    features: List[dict] = []
    stats: Dict[str, int] = {}

    # 1) Curated individual trails (small-scale realism)
    for src_path, key in [(county_trails, "TrailName"), (proposed_trails, "Trail_Name")]:
        obj = load_geojson(src_path)
        feats = obj.get("features", [])
        by_name_lines: Dict[str, List[List[Point]]] = defaultdict(list)
        for i, f in enumerate(feats):
            props = f.get("properties") or {}
            name = str(props.get(key, "")).strip() or f"UNNAMED_{i}"
            lines = flatten_lines(f.get("geometry") or {})
            by_name_lines[name].extend(lines)

        for name, lines in sorted(by_name_lines.items()):
            if not lines:
                continue
            # Keep largest part for shape snapshots; preserves line semantics.
            main = max(lines, key=len)
            features.append(
                make_feature(
                    fid=name,
                    source=src_path.name,
                    category="Mechanical",
                    geom_type="LineString",
                    coords=[[x, y] for x, y in main],
                    properties={"dataset_level": "curated"},
                )
            )

    stats["curated_features"] = len(features)

    # 2) Overpass segments: deduplicate exact/reversed duplicates
    uniq: Dict[Tuple[Tuple[float, float], ...], List[Point]] = {}
    raw_segments = 0

    for tile in overpass_tiles:
        obj = load_geojson(tile)
        for f in obj.get("features", []):
            for line in flatten_lines(f.get("geometry") or {}):
                raw_segments += 1
                sig = line_signature(line)
                if sig not in uniq:
                    uniq[sig] = line

    uniq_lines = list(uniq.values())
    uniq_lines.sort(key=lambda ln: len(ln), reverse=True)

    stats["overpass_raw_segments"] = raw_segments
    stats["overpass_unique_segments"] = len(uniq_lines)
    stats["overpass_unique_vertices"] = sum(len(ln) for ln in uniq_lines)

    # 3) Medium bundles (5k-20k vertices) for algorithm quality evaluation
    medium_targets: List[List[List[Point]]] = []
    bucket: List[List[Point]] = []
    bucket_v = 0

    for ln in uniq_lines:
        lv = len(ln)
        if bucket_v + lv > 15000 and bucket_v >= 5000:
            medium_targets.append(bucket)
            bucket = []
            bucket_v = 0
        bucket.append(ln)
        bucket_v += lv

    if 5000 <= bucket_v <= 20000:
        medium_targets.append(bucket)

    # Cap to a practical count for report plots/experiments.
    medium_targets = medium_targets[:12]

    for i, group in enumerate(medium_targets, start=1):
        coords = concat_lines(group)
        features.append(
            make_feature(
                fid=f"OVERPASS_MEDIUM_{i:02d}",
                source="overpass_tiles",
                category="Mechanical",
                geom_type="LineString",
                coords=[[x, y] for x, y in coords],
                properties={
                    "dataset_level": "synthetic_bundle",
                    "bundle_type": "medium",
                    "segment_count": len(group),
                    "vertex_count": len(coords),
                },
            )
        )

    stats["medium_bundles"] = len(medium_targets)

    # 4) Large bundles (>100k vertices) for runtime stress tests
    # Split unique lines by descending length into two deterministic large bundles.
    large_a: List[List[Point]] = []
    large_b: List[List[Point]] = []
    va = vb = 0
    for ln in uniq_lines:
        if va <= vb:
            large_a.append(ln)
            va += len(ln)
        else:
            large_b.append(ln)
            vb += len(ln)

    large_groups = [("A", large_a, va), ("B", large_b, vb)]
    for tag, group, v in large_groups:
        coords = concat_lines(group)
        features.append(
            make_feature(
                fid=f"OVERPASS_LARGE_{tag}",
                source="overpass_tiles",
                category="Mechanical",
                geom_type="LineString",
                coords=[[x, y] for x, y in coords],
                properties={
                    "dataset_level": "synthetic_bundle",
                    "bundle_type": "large",
                    "segment_count": len(group),
                    "vertex_count": len(coords),
                },
            )
        )

    stats["large_bundle_a_vertices"] = va
    stats["large_bundle_b_vertices"] = vb

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = {"type": "FeatureCollection", "features": features}
    out_path.write_text(json.dumps(out), encoding="utf-8")
    stats["derived_mechanical_features"] = len(features)
    return stats


def build_organic_derived(ca_counties: Path, out_path: Path) -> Dict[str, int]:
    obj = load_geojson(ca_counties)
    feats = obj.get("features", [])

    # Keep original county features for medium-scale organic.
    features = []
    for i, f in enumerate(feats):
        props = f.get("properties") or {}
        fid = props.get("CountyName") or f"county_{i}"
        features.append(
            make_feature(
                fid=str(fid),
                source=ca_counties.name,
                category="Organic",
                geom_type=(f.get("geometry") or {}).get("type", "Polygon"),
                coords=(f.get("geometry") or {}).get("coordinates", []),
                properties={"dataset_level": "curated"},
            )
        )

    # Add one large organic aggregate by concatenating all outer rings.
    rings: List[List[Point]] = []
    for f in feats:
        geom = f.get("geometry") or {}
        gt = geom.get("type")
        c = geom.get("coordinates")
        if gt == "Polygon":
            if c and c[0]:
                rings.append([(float(x), float(y)) for x, y, *rest in c[0]])
        elif gt == "MultiPolygon":
            for poly in c or []:
                if poly and poly[0]:
                    rings.append([(float(x), float(y)) for x, y, *rest in poly[0]])

    large = concat_lines(rings)
    features.append(
        make_feature(
            fid="CA_ORGANIC_LARGE_AGG",
            source=ca_counties.name,
            category="Organic",
            geom_type="LineString",
            coords=[[x, y] for x, y in large],
            properties={"dataset_level": "synthetic_bundle", "bundle_type": "large", "vertex_count": len(large)},
        )
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = {"type": "FeatureCollection", "features": features}
    out_path.write_text(json.dumps(out), encoding="utf-8")
    return {
        "derived_organic_features": len(features),
        "organic_large_vertices": len(large),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build derived datasets + run characterization")
    parser.add_argument("--county-trails", type=Path, default=Path("data/County_Trails.geojson"))
    parser.add_argument("--proposed-trails", type=Path, default=Path("data/Proposed_Trails.geojson"))
    parser.add_argument("--coast", type=Path, default=Path("data/California_Counties_68233851330457591.geojson"))
    parser.add_argument("--tiles-glob", default="data/slo_mech_tile_*.geojson*")
    parser.add_argument("--derived-dir", type=Path, default=Path("data/derived"))
    args = parser.parse_args()

    tiles = sorted(Path('.').glob(args.tiles_glob))
    if not tiles:
        raise SystemExit(f"No Overpass tile files found for pattern: {args.tiles_glob}")

    mech_out = args.derived_dir / "mechanical_benchmarks.geojson"
    org_out = args.derived_dir / "organic_benchmarks.geojson"

    ms = build_mechanical_derived(args.county_trails, args.proposed_trails, tiles, mech_out)
    os = build_organic_derived(args.coast, org_out)

    # Run characterization on derived sets.
    import subprocess

    cmd = [
        str(Path("./.venv/bin/python")),
        "parsing/data_characterization.py",
        "--coast",
        str(org_out),
        "--county-trails",
        str(mech_out),
        "--output-dir",
        "parsing/output",
    ]
    env = dict(**__import__("os").environ, MPLCONFIGDIR="/tmp/matplotlib")
    subprocess.run(cmd, check=True, env=env)

    summary = {
        **ms,
        **os,
        "tiles_used": len(tiles),
    }
    (Path("parsing/output") / "pipeline_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
