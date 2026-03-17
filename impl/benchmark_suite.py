#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from simplify.douglas_peucker import simplify_dp_to_count
from simplify.geometry import compression_ratio, max_perpendicular_error, symmetric_hausdorff
from simplify.io import load_curves, size_bin
from simplify.types import Curve
from simplify.visvalingam_whyatt import simplify_vw_to_count


@dataclass
class SuiteRow:
    curve_id: str
    category: str
    source: str
    size_bin: str
    algorithm: str
    compression_target: float
    original_vertices: int
    simplified_vertices: int
    achieved_compression: float
    max_perp_error: float
    hausdorff: float
    runtime_ms: float


def subsample(points, max_points: int):
    if len(points) <= max_points:
        return list(points)
    step = (len(points) - 1) / max(1, max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


def run_one(
    curve: Curve,
    target: float,
    metric_max_points: int,
    dp_steps: int,
    algo_input_max_points: int,
) -> List[SuiteRow]:
    orig_n = len(curve.points)
    pts = subsample(curve.points, algo_input_max_points) if algo_input_max_points > 0 else curve.points
    n = len(pts)
    target_n = max(2, int(math.ceil(n * max(0.0, min(1.0, 1.0 - target)))))
    sb = size_bin(orig_n)

    t0 = time.perf_counter()
    dp_pts = simplify_dp_to_count(pts, target_n, steps=dp_steps)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    vw_pts = simplify_vw_to_count(pts, target_n)
    t3 = time.perf_counter()

    op = subsample(pts, metric_max_points)
    dp_s = subsample(dp_pts, metric_max_points)
    vw_s = subsample(vw_pts, metric_max_points)

    return [
        SuiteRow(
            curve_id=curve.curve_id,
            category=curve.category,
            source=curve.source,
            size_bin=sb,
            algorithm="DP",
            compression_target=target,
            original_vertices=orig_n,
            simplified_vertices=len(dp_pts),
            achieved_compression=compression_ratio(n, len(dp_pts)),
            max_perp_error=max_perpendicular_error(op, dp_s),
            hausdorff=symmetric_hausdorff(op, dp_s),
            runtime_ms=(t1 - t0) * 1000.0,
        ),
        SuiteRow(
            curve_id=curve.curve_id,
            category=curve.category,
            source=curve.source,
            size_bin=sb,
            algorithm="VW",
            compression_target=target,
            original_vertices=orig_n,
            simplified_vertices=len(vw_pts),
            achieved_compression=compression_ratio(n, len(vw_pts)),
            max_perp_error=max_perpendicular_error(op, vw_s),
            hausdorff=symmetric_hausdorff(op, vw_s),
            runtime_ms=(t3 - t2) * 1000.0,
        ),
    ]


def sample_group(curves: Sequence[Curve], limit: int) -> List[Curve]:
    if len(curves) <= limit:
        return list(curves)
    curves = sorted(curves, key=lambda c: c.vertex_count)
    step = (len(curves) - 1) / max(1, limit - 1)
    return [curves[round(i * step)] for i in range(limit)]


def write_csv(rows: Sequence[SuiteRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        if rows:
            writer.writeheader()
            for r in rows:
                writer.writerow(asdict(r))


def write_summary(rows: Sequence[SuiteRow], path: Path) -> None:
    grouped: Dict[str, List[SuiteRow]] = defaultdict(list)
    for r in rows:
        key = f"{r.category}_{r.size_bin}_{r.algorithm}"
        grouped[key].append(r)

    out = {}
    for k, rs in sorted(grouped.items()):
        out[k] = {
            "n_runs": len(rs),
            "mean_runtime_ms": sum(x.runtime_ms for x in rs) / len(rs),
            "median_runtime_ms": sorted(x.runtime_ms for x in rs)[len(rs) // 2],
            "mean_max_perp_error": sum(x.max_perp_error for x in rs) / len(rs),
            "mean_hausdorff": sum(x.hausdorff for x in rs) / len(rs),
            "mean_achieved_compression": sum(x.achieved_compression for x in rs) / len(rs),
        }
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run broad DP/VW benchmark suite across subsets.")
    parser.add_argument("--mechanical", type=Path, default=Path("data/derived/mechanical_benchmarks.geojson"))
    parser.add_argument("--organic", type=Path, default=Path("data/derived/organic_benchmarks.geojson"))
    parser.add_argument("--out-dir", type=Path, default=Path("impl/output/suite"))
    parser.add_argument("--max-small", type=int, default=40)
    parser.add_argument("--max-medium", type=int, default=34)
    parser.add_argument("--max-large", type=int, default=8)
    parser.add_argument("--metric-max-points", type=int, default=5000)
    parser.add_argument("--dp-steps", type=int, default=18)
    parser.add_argument(
        "--algo-input-max-points",
        type=int,
        default=120000,
        help="Cap points per curve for algorithm execution via uniform subsampling (0 disables cap).",
    )
    args = parser.parse_args()

    mech = load_curves(args.mechanical, default_category="Mechanical")
    org = load_curves(args.organic, default_category="Organic")
    all_curves = mech + org

    by_subset: Dict[tuple[str, str], List[Curve]] = defaultdict(list)
    for c in all_curves:
        b = size_bin(c.vertex_count)
        if b in {"small", "medium", "large"}:
            by_subset[(c.category, b)].append(c)

    selected: List[Curve] = []
    for (cat, b), curves in sorted(by_subset.items()):
        if b == "small":
            lim = args.max_small
        elif b == "medium":
            lim = args.max_medium
        else:
            lim = args.max_large
        selected.extend(sample_group(curves, lim))

    # targets by size bin
    targets = {
        "small": [0.3, 0.5, 0.7, 0.9],
        "medium": [0.5, 0.7, 0.8, 0.9],
        "large": [0.7, 0.9],
    }

    rows: List[SuiteRow] = []
    for i, c in enumerate(selected, start=1):
        b = size_bin(c.vertex_count)
        for t in targets[b]:
            rows.extend(
                run_one(
                    c,
                    t,
                    metric_max_points=args.metric_max_points,
                    dp_steps=args.dp_steps,
                    algo_input_max_points=args.algo_input_max_points,
                )
            )
        if i % 5 == 0 or i == len(selected):
            print(f"Processed {i}/{len(selected)} curves...", flush=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / "suite_runs.csv"
    json_path = args.out_dir / "suite_summary.json"
    meta_path = args.out_dir / "suite_meta.json"

    write_csv(rows, csv_path)
    write_summary(rows, json_path)

    meta = {
        "selected_curves": len(selected),
        "total_runs": len(rows),
        "targets": targets,
        "limits": {
            "max_small": args.max_small,
            "max_medium": args.max_medium,
            "max_large": args.max_large,
        },
        "metric_max_points": args.metric_max_points,
        "dp_steps": args.dp_steps,
        "algo_input_max_points": args.algo_input_max_points,
        "subset_counts": {
            f"{cat}_{b}": len([c for c in selected if c.category == cat and size_bin(c.vertex_count) == b])
            for cat, b in sorted(by_subset.keys())
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Selected curves: {len(selected)}")
    print(f"Total runs: {len(rows)}")
    print(f"Wrote: {csv_path}")
    print(f"Wrote: {json_path}")
    print(f"Wrote: {meta_path}")


if __name__ == "__main__":
    main()
