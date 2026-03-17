#!/usr/bin/env python3
"""GeoJSON report helper for computational geometry snapshots and metrics.

What this script does:
1) Parses a GeoJSON FeatureCollection and prints a summary table.
2) Builds a 1x3 figure with:
   - Plot A: "Mechanical" SLO trail snapshot.
   - Plot B: "Organic" CA coastline snapshot.
   - Plot C: straight line before/after Gaussian noise.
3) For one Medium dataset, prints start and final vertex counts for 90% compression.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

Point = Tuple[float, float]


def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_points_from_coordinates(coords) -> int:
    if not isinstance(coords, list) or not coords:
        return 0
    if isinstance(coords[0], (int, float)):
        return 1
    return sum(count_points_from_coordinates(c) for c in coords)


def count_feature_vertices(feature: dict) -> int:
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    if gtype == "GeometryCollection":
        return sum(count_feature_vertices({"geometry": g}) for g in geom.get("geometries", []))
    return count_points_from_coordinates(geom.get("coordinates"))


def iter_rings(feature: dict) -> Iterable[List[Point]]:
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    if gtype == "Polygon":
        for ring in coords or []:
            if isinstance(ring, list) and ring:
                yield [(float(p[0]), float(p[1])) for p in ring]
    elif gtype == "MultiPolygon":
        for poly in coords or []:
            for ring in poly or []:
                if isinstance(ring, list) and ring:
                    yield [(float(p[0]), float(p[1])) for p in ring]


def longest_ring(feature: dict) -> List[Point]:
    rings = list(iter_rings(feature))
    if not rings:
        return []
    return max(rings, key=len)


def path_length(points: Sequence[Point]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        total += math.hypot(dx, dy)
    return total


def point_line_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    projx = ax + t * dx
    projy = ay + t * dy
    return math.hypot(px - projx, py - projy)


def douglas_peucker(points: Sequence[Point], epsilon: float) -> List[Point]:
    if len(points) <= 2:
        return list(points)

    start = points[0]
    end = points[-1]
    max_dist = -1.0
    max_idx = -1

    for i in range(1, len(points) - 1):
        d = point_line_distance(points[i], start, end)
        if d > max_dist:
            max_dist = d
            max_idx = i

    if max_dist > epsilon:
        left = douglas_peucker(points[: max_idx + 1], epsilon)
        right = douglas_peucker(points[max_idx:], epsilon)
        return left[:-1] + right
    return [start, end]


def simplify_to_target(points: Sequence[Point], target_count: int, steps: int = 30) -> List[Point]:
    if len(points) <= target_count:
        return list(points)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    lo, hi = 0.0, max(diag, 1e-12)

    best = list(points)
    best_delta = abs(len(best) - target_count)

    for _ in range(steps):
        mid = (lo + hi) / 2.0
        candidate = douglas_peucker(points, mid)
        delta = abs(len(candidate) - target_count)
        if delta < best_delta or (delta == best_delta and len(candidate) < len(best)):
            best = candidate
            best_delta = delta

        if len(candidate) > target_count:
            lo = mid
        else:
            hi = mid

    return best


def feature_name(feature: dict, default: str) -> str:
    props = feature.get("properties") or {}
    for key in ("CountyName", "name", "NAME", "Name"):
        if key in props and props[key]:
            return str(props[key])
    return default


def category_label(n_vertices: int) -> str:
    if n_vertices < 500:
        return "Small (<500)"
    if 5000 <= n_vertices <= 20000:
        return "Medium (5k-20k)"
    if n_vertices > 100000:
        return "Large (>100k)"
    return "Uncategorized"


def print_summary(features: Sequence[dict]) -> Dict[str, List[Tuple[str, int]]]:
    buckets: Dict[str, List[Tuple[str, int]]] = {
        "Small (<500)": [],
        "Medium (5k-20k)": [],
        "Large (>100k)": [],
        "Uncategorized": [],
    }

    for i, f in enumerate(features):
        n = count_feature_vertices(f)
        label = category_label(n)
        buckets[label].append((feature_name(f, f"feature_{i}"), n))

    print("\nSummary")
    print("=" * 74)
    print(f"Total features: {len(features)}")
    print("=" * 74)
    print(f"{'Category':<24}{'Feature Count':>14}{'Total Vertices':>18}{'Min Vertices':>14}{'Max Vertices':>14}")
    print("-" * 74)

    for label in ["Small (<500)", "Medium (5k-20k)", "Large (>100k)", "Uncategorized"]:
        values = [v for _, v in buckets[label]]
        if values:
            print(
                f"{label:<24}{len(values):>14}{sum(values):>18}{min(values):>14}{max(values):>14}"
            )
        else:
            print(f"{label:<24}{0:>14}{0:>18}{'-':>14}{'-':>14}")
    print("=" * 74)
    return buckets


def pick_feature_by_name(features: Sequence[dict], needle: str) -> dict | None:
    needle_lower = needle.lower()
    for i, f in enumerate(features):
        name = feature_name(f, f"feature_{i}").lower()
        if needle_lower in name:
            return f
    return None


def choose_medium_feature(features: Sequence[dict]) -> dict:
    medium = []
    for i, f in enumerate(features):
        n = count_feature_vertices(f)
        if 5000 <= n <= 20000:
            medium.append((abs(n - 10000), i, f, n))
    if medium:
        medium.sort(key=lambda x: x[0])
        return medium[0][2]

    fallback = max(((count_feature_vertices(f), f) for f in features), key=lambda x: x[0], default=(0, None))[1]
    if fallback is None:
        raise ValueError("No features found in GeoJSON.")
    return fallback


def normalize_open_polyline(points: Sequence[Point]) -> List[Point]:
    pts = list(points)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def middle_window(points: Sequence[Point], frac_start: float = 0.25, frac_end: float = 0.65) -> List[Point]:
    pts = list(points)
    if len(pts) < 3:
        return pts
    i0 = max(0, int(len(pts) * frac_start))
    i1 = min(len(pts), int(len(pts) * frac_end))
    if i1 - i0 < 2:
        return pts
    return pts[i0:i1]


def load_first_linestring(path: Path) -> List[Point]:
    obj = load_geojson(path)

    def from_geom(geom: dict) -> List[Point]:
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if gtype == "LineString" and coords:
            return [(float(p[0]), float(p[1])) for p in coords]
        if gtype == "MultiLineString" and coords and coords[0]:
            return [(float(p[0]), float(p[1])) for p in coords[0]]
        return []

    if obj.get("type") == "FeatureCollection":
        for feat in obj.get("features", []):
            pts = from_geom(feat.get("geometry") or {})
            if pts:
                return pts
    elif obj.get("type") == "Feature":
        pts = from_geom(obj.get("geometry") or {})
        if pts:
            return pts
    else:
        pts = from_geom(obj)
        if pts:
            return pts

    raise ValueError(f"No LineString found in {path}")


def make_noise_edge_case(n: int = 250, sigma: float = 0.02, seed: int = 7) -> Tuple[List[Point], List[Point]]:
    random.seed(seed)
    clean = [(i / (n - 1), 0.0) for i in range(n)]
    noisy = [(x, y + random.gauss(0.0, sigma)) for x, y in clean]
    return clean, noisy


def maybe_plot(
    mechanical: Sequence[Point],
    organic: Sequence[Point],
    edge_clean: Sequence[Point],
    edge_noisy: Sequence[Point],
    output_path: Path,
    dpi: int,
) -> bool:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("\nPlotting skipped: matplotlib is not installed.")
        print("Install it with: ./.venv/bin/pip install matplotlib")
        return False

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)

    mx, my = zip(*mechanical)
    axes[0].plot(mx, my, color="#0b5cad", linewidth=1.8)
    axes[0].set_title("Plot A: Mechanical SLO Trail")
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].grid(alpha=0.25)

    ox, oy = zip(*organic)
    axes[1].plot(ox, oy, color="#1b7f3b", linewidth=1.5)
    axes[1].set_title("Plot B: Organic CA Coastline")
    axes[1].set_aspect("equal", adjustable="box")
    axes[1].grid(alpha=0.25)

    cx, cy = zip(*edge_clean)
    nx, ny = zip(*edge_noisy)
    axes[2].plot(cx, cy, label="Before noise", color="#111111", linewidth=1.7)
    axes[2].plot(nx, ny, label="After Gaussian noise", color="#c23b22", linewidth=1.1)
    axes[2].set_title("Plot C: Edge Case (Noise)")
    axes[2].grid(alpha=0.25)
    axes[2].legend(loc="best")

    for ax in axes:
        ax.set_xlabel("x")
        ax.set_ylabel("y")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    print(f"\nSaved figure: {output_path}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse GeoJSON and create report figures/metrics.")
    parser.add_argument(
        "--geojson",
        type=Path,
        default=Path("data/California_Counties_68233851330457591.geojson"),
        help="Path to the main GeoJSON FeatureCollection.",
    )
    parser.add_argument(
        "--mechanical-geojson",
        type=Path,
        default=None,
        help="Optional LineString GeoJSON for Plot A (Mechanical SLO trail).",
    )
    parser.add_argument(
        "--organic-geojson",
        type=Path,
        default=None,
        help="Optional LineString GeoJSON for Plot B (Organic coastline section).",
    )
    parser.add_argument(
        "--plot-output",
        type=Path,
        default=Path("parsing/report_snapshots.png"),
        help="Output image for side-by-side plots.",
    )
    parser.add_argument("--dpi", type=int, default=220, help="Figure DPI.")
    args = parser.parse_args()

    data = load_geojson(args.geojson)
    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection.")

    features = data.get("features", [])
    if not features:
        raise ValueError("No features in GeoJSON.")

    _ = print_summary(features)

    medium_feature = choose_medium_feature(features)
    medium_name = feature_name(medium_feature, "medium_feature")
    medium_line = normalize_open_polyline(longest_ring(medium_feature))
    if len(medium_line) < 2:
        raise ValueError("Could not extract a usable line from the chosen medium feature.")

    start_n = len(medium_line)
    target_n = max(2, int(math.ceil(start_n * 0.10)))
    compressed_line = simplify_to_target(medium_line, target_n)
    final_n = len(compressed_line)

    print("\nCompression Metric (90% compression target)")
    print("=" * 74)
    print(f"Selected Medium dataset: {medium_name}")
    print(f"Starting vertex count: {start_n}")
    print(f"Final vertex count (after simplification): {final_n}")
    print(f"Target kept vertices (10% of start): {target_n}")
    print("=" * 74)

    if args.mechanical_geojson:
        mechanical = normalize_open_polyline(load_first_linestring(args.mechanical_geojson))
    else:
        slo = pick_feature_by_name(features, "San Luis Obispo") or medium_feature
        slo_line = normalize_open_polyline(longest_ring(slo))
        mechanical = simplify_to_target(slo_line, max(25, int(len(slo_line) * 0.08)))

    if args.organic_geojson:
        organic = normalize_open_polyline(load_first_linestring(args.organic_geojson))
    else:
        slo = pick_feature_by_name(features, "San Luis Obispo") or medium_feature
        slo_line = normalize_open_polyline(longest_ring(slo))
        organic = middle_window(slo_line, 0.18, 0.62)

    edge_clean, edge_noisy = make_noise_edge_case()

    if len(mechanical) < 2 or len(organic) < 2:
        print("\nSkipping figure generation: insufficient points for Plot A or Plot B.")
        return

    maybe_plot(mechanical, organic, edge_clean, edge_noisy, args.plot_output, args.dpi)


if __name__ == "__main__":
    main()
