from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from .douglas_peucker import simplify_dp_to_count
from .geometry import compression_ratio, max_perpendicular_error, symmetric_hausdorff
from .io import size_bin
from .types import Curve
from .visvalingam_whyatt import simplify_vw_to_count


@dataclass
class RunResult:
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


def _target_count(n: int, compression_target: float) -> int:
    keep_ratio = max(0.0, min(1.0, 1.0 - compression_target))
    return max(2, int(math.ceil(n * keep_ratio)))


def _subsample(points: Sequence[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    if len(points) <= max_points:
        return list(points)
    step = (len(points) - 1) / max(1, max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


def run_experiments(
    curves: Sequence[Curve],
    compression_targets: Sequence[float],
    metric_max_points: int = 8000,
) -> List[RunResult]:
    out: List[RunResult] = []

    for curve in curves:
        pts = curve.points
        n = len(pts)
        b = size_bin(n)

        for ct in compression_targets:
            target_n = _target_count(n, ct)

            t0 = time.perf_counter()
            dp_pts = simplify_dp_to_count(pts, target_n)
            t1 = time.perf_counter()
            out.append(
                RunResult(
                    curve_id=curve.curve_id,
                    category=curve.category,
                    source=curve.source,
                    size_bin=b,
                    algorithm="DP",
                    compression_target=ct,
                    original_vertices=n,
                    simplified_vertices=len(dp_pts),
                    achieved_compression=compression_ratio(n, len(dp_pts)),
                    max_perp_error=max_perpendicular_error(_subsample(pts, metric_max_points), _subsample(dp_pts, metric_max_points)),
                    hausdorff=symmetric_hausdorff(_subsample(pts, metric_max_points), _subsample(dp_pts, metric_max_points)),
                    runtime_ms=(t1 - t0) * 1000.0,
                )
            )

            t2 = time.perf_counter()
            vw_pts = simplify_vw_to_count(pts, target_n)
            t3 = time.perf_counter()
            out.append(
                RunResult(
                    curve_id=curve.curve_id,
                    category=curve.category,
                    source=curve.source,
                    size_bin=b,
                    algorithm="VW",
                    compression_target=ct,
                    original_vertices=n,
                    simplified_vertices=len(vw_pts),
                    achieved_compression=compression_ratio(n, len(vw_pts)),
                    max_perp_error=max_perpendicular_error(_subsample(pts, metric_max_points), _subsample(vw_pts, metric_max_points)),
                    hausdorff=symmetric_hausdorff(_subsample(pts, metric_max_points), _subsample(vw_pts, metric_max_points)),
                    runtime_ms=(t3 - t2) * 1000.0,
                )
            )

    return out


def write_results_csv(results: Sequence[RunResult], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()) if results else [])
        if results:
            writer.writeheader()
            for r in results:
                writer.writerow(asdict(r))


def summarize_results(results: Sequence[RunResult]) -> Dict[str, dict]:
    groups: Dict[tuple[str, str], List[RunResult]] = {}
    for r in results:
        groups.setdefault((r.algorithm, r.size_bin), []).append(r)

    summary: Dict[str, dict] = {}
    for (algo, b), rs in sorted(groups.items()):
        key = f"{algo}_{b}"
        summary[key] = {
            "n_runs": len(rs),
            "mean_runtime_ms": sum(x.runtime_ms for x in rs) / len(rs),
            "mean_hausdorff": sum(x.hausdorff for x in rs) / len(rs),
            "mean_max_perp_error": sum(x.max_perp_error for x in rs) / len(rs),
            "mean_achieved_compression": sum(x.achieved_compression for x in rs) / len(rs),
        }

    return summary


def write_summary_json(summary: Dict[str, dict], out_json: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
