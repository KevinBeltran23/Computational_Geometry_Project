#!/usr/bin/env python3
"""Data characterization pipeline for CSC 570 report.

Inputs (defaults):
- data/California_Counties_68233851330457591.geojson
- data/County_Trails.geojson
- data/Proposed_Trails.geojson

Outputs:
- parsing/output/dataset_summary.csv
- parsing/output/report_metrics.txt
- parsing/output/diagram_analysis.md
- parsing/output/fig_*.png
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

Point = Tuple[float, float]


@dataclass
class FeatureRecord:
    source: str
    feature_id: str
    geom_type: str
    category: str
    vertex_count: int
    path_length: float
    bbox_width: float
    bbox_height: float
    sinuosity: float
    turn_mean_abs: float
    turn_std_abs: float


def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_points_from_coordinates(coords) -> int:
    if not isinstance(coords, list) or not coords:
        return 0
    if isinstance(coords[0], (int, float)):
        return 1
    return sum(count_points_from_coordinates(c) for c in coords)


def flatten_to_lines(geom: dict) -> List[List[Point]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    if gtype == "LineString":
        return [[(float(x), float(y)) for x, y, *rest in coords]] if coords else []

    if gtype == "MultiLineString":
        out: List[List[Point]] = []
        for ls in coords or []:
            if ls:
                out.append([(float(x), float(y)) for x, y, *rest in ls])
        return out

    if gtype == "Polygon":
        out = []
        for ring in coords or []:
            if ring:
                out.append([(float(x), float(y)) for x, y, *rest in ring])
        return out

    if gtype == "MultiPolygon":
        out = []
        for poly in coords or []:
            for ring in poly or []:
                if ring:
                    out.append([(float(x), float(y)) for x, y, *rest in ring])
        return out

    if gtype == "GeometryCollection":
        out = []
        for g in geom.get("geometries", []):
            out.extend(flatten_to_lines(g))
        return out

    return []


def feature_name(feature: dict, default: str) -> str:
    props = feature.get("properties") or {}
    for key in ("name", "Name", "NAME", "CountyName", "trail", "ref", "TrailName", "Trail_Name"):
        if key in props and props[key]:
            return str(props[key]).strip()
    return default


def path_length(points: Sequence[Point]) -> float:
    return sum(math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]) for i in range(1, len(points)))


def bbox(points: Sequence[Point]) -> Tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def turning_angles(points: Sequence[Point]) -> List[float]:
    vals: List[float] = []
    for i in range(1, len(points) - 1):
        p0 = points[i - 1]
        p1 = points[i]
        p2 = points[i + 1]
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        n1 = math.hypot(v1[0], v1[1])
        n2 = math.hypot(v2[0], v2[1])
        if n1 == 0 or n2 == 0:
            continue
        dot = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        dot = max(-1.0, min(1.0, dot))
        vals.append(abs(math.degrees(math.acos(dot))))
    return vals


def safe_mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def safe_std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = safe_mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def size_bin(v: int) -> str:
    if v < 500:
        return "Small (<500)"
    if 5000 <= v <= 20000:
        return "Medium (5k-20k)"
    if v > 100000:
        return "Large (>100k)"
    return "Uncategorized"


def as_polyline(lines: Sequence[Sequence[Point]]) -> List[Point]:
    if not lines:
        return []
    line = max((list(line) for line in lines if len(line) >= 2), key=len, default=[])
    if len(line) >= 2 and line[0] == line[-1]:
        line = line[:-1]
    return line


def build_record(source_label: str, fid: str, geom_type: str, category: str, line: List[Point], vertex_count: int) -> FeatureRecord:
    if len(line) >= 2:
        plen = path_length(line)
        bw, bh = bbox(line)
        end_to_end = math.hypot(line[-1][0] - line[0][0], line[-1][1] - line[0][1])
        diag = math.hypot(bw, bh)
        denom = end_to_end
        # Closed or near-closed boundaries make endpoint distance unstable.
        if denom < max(1e-12, 0.01 * diag):
            denom = max(diag, 1e-12)
        sinu = plen / denom
        turns = turning_angles(line)
        mean_t = safe_mean(turns)
        std_t = safe_std(turns)
    else:
        plen = 0.0
        bw = bh = 0.0
        sinu = 0.0
        mean_t = std_t = 0.0

    return FeatureRecord(
        source=source_label,
        feature_id=fid,
        geom_type=geom_type,
        category=category,
        vertex_count=vertex_count,
        path_length=plen,
        bbox_width=bw,
        bbox_height=bh,
        sinuosity=sinu,
        turn_mean_abs=mean_t,
        turn_std_abs=std_t,
    )


def collect_records(path: Path, source_label: str, category: str, group_key: str | None = None) -> Tuple[List[FeatureRecord], List[List[Point]]]:
    obj = load_geojson(path)
    feats = obj.get("features", []) if obj.get("type") == "FeatureCollection" else [obj]

    records: List[FeatureRecord] = []
    polylines: List[List[Point]] = []

    if group_key:
        has_group_key = any(
            bool(((feat.get("properties") if feat.get("type") == "Feature" else {}) or {}).get(group_key))
            for feat in feats
        )
        if not has_group_key:
            group_key = None

    if group_key:
        grouped_lines: Dict[str, List[List[Point]]] = defaultdict(list)
        grouped_vertices: Dict[str, int] = defaultdict(int)
        grouped_geom_type: Dict[str, str] = defaultdict(str)

        for i, feat in enumerate(feats):
            geom = (feat.get("geometry") if feat.get("type") == "Feature" else feat) or {}
            props = (feat.get("properties") if feat.get("type") == "Feature" else {}) or {}
            gid = str(props.get(group_key, "")).strip() or "UNNAMED"
            grouped_geom_type[gid] = geom.get("type", "Unknown")
            grouped_vertices[gid] += count_points_from_coordinates(geom.get("coordinates"))
            grouped_lines[gid].extend(flatten_to_lines(geom))

        for gid in sorted(grouped_lines.keys()):
            line = as_polyline(grouped_lines[gid])
            if len(line) >= 2:
                polylines.append(line)
            records.append(
                build_record(
                    source_label=source_label,
                    fid=gid,
                    geom_type=grouped_geom_type.get(gid, "Unknown"),
                    category=category,
                    line=line,
                    vertex_count=grouped_vertices[gid],
                )
            )

        return records, polylines

    for i, feat in enumerate(feats):
        if feat.get("type") == "Feature":
            geom = feat.get("geometry") or {}
            fid = feature_name(feat, f"{source_label}_{i}")
        else:
            geom = feat
            fid = f"{source_label}_{i}"

        vcount = count_points_from_coordinates(geom.get("coordinates")) if geom.get("type") != "GeometryCollection" else sum(
            count_points_from_coordinates((g or {}).get("coordinates")) for g in geom.get("geometries", [])
        )
        line = as_polyline(flatten_to_lines(geom))
        if len(line) >= 2:
            polylines.append(line)

        records.append(
            build_record(
                source_label=source_label,
                fid=fid,
                geom_type=geom.get("type", "Unknown"),
                category=category,
                line=line,
                vertex_count=vcount,
            )
        )

    return records, polylines


def write_csv(records: Sequence[FeatureRecord], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "source",
                "feature_id",
                "geom_type",
                "category",
                "vertex_count",
                "size_bin",
                "path_length",
                "bbox_width",
                "bbox_height",
                "sinuosity",
                "turn_mean_abs",
                "turn_std_abs",
            ]
        )
        for r in records:
            writer.writerow(
                [
                    r.source,
                    r.feature_id,
                    r.geom_type,
                    r.category,
                    r.vertex_count,
                    size_bin(r.vertex_count),
                    f"{r.path_length:.8f}",
                    f"{r.bbox_width:.8f}",
                    f"{r.bbox_height:.8f}",
                    f"{r.sinuosity:.8f}",
                    f"{r.turn_mean_abs:.8f}",
                    f"{r.turn_std_abs:.8f}",
                ]
            )


def summarize(records: Sequence[FeatureRecord]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for r in records:
        out.setdefault(r.category, {"total": 0, "small": 0, "medium": 0, "large": 0, "uncat": 0})
        out[r.category]["total"] += 1
        b = size_bin(r.vertex_count)
        if b.startswith("Small"):
            out[r.category]["small"] += 1
        elif b.startswith("Medium"):
            out[r.category]["medium"] += 1
        elif b.startswith("Large"):
            out[r.category]["large"] += 1
        else:
            out[r.category]["uncat"] += 1
    return out


def category_stats(records: Sequence[FeatureRecord], category: str) -> Dict[str, float]:
    rs = [r for r in records if r.category == category]
    vertices = [r.vertex_count for r in rs]
    sinu = [r.sinuosity for r in rs if r.sinuosity > 0 and math.isfinite(r.sinuosity)]
    turns = [r.turn_mean_abs for r in rs if r.turn_mean_abs > 0]

    return {
        "n": len(rs),
        "vertex_mean": safe_mean(vertices),
        "vertex_min": min(vertices) if vertices else 0,
        "vertex_max": max(vertices) if vertices else 0,
        "sinu_mean": safe_mean(sinu),
        "turn_mean": safe_mean(turns),
    }


def create_plots(
    records: Sequence[FeatureRecord],
    mechanical_polyline: Sequence[Point],
    organic_polyline: Sequence[Point],
    output_dir: Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError("matplotlib is required. Install via ./.venv/bin/pip install matplotlib") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    mech = [r for r in records if r.category == "Mechanical"]
    org = [r for r in records if r.category == "Organic"]

    # Figure 1: scale coverage
    labels = ["Small", "Medium", "Large", "Uncat"]
    mvals = [
        sum(1 for r in mech if size_bin(r.vertex_count).startswith("Small")),
        sum(1 for r in mech if size_bin(r.vertex_count).startswith("Medium")),
        sum(1 for r in mech if size_bin(r.vertex_count).startswith("Large")),
        sum(1 for r in mech if size_bin(r.vertex_count) == "Uncategorized"),
    ]
    ovals = [
        sum(1 for r in org if size_bin(r.vertex_count).startswith("Small")),
        sum(1 for r in org if size_bin(r.vertex_count).startswith("Medium")),
        sum(1 for r in org if size_bin(r.vertex_count).startswith("Large")),
        sum(1 for r in org if size_bin(r.vertex_count) == "Uncategorized"),
    ]

    fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    x = list(range(len(labels)))
    w = 0.38
    ax.bar([i - w / 2 for i in x], mvals, width=w, label="Mechanical", color="#0b5cad")
    ax.bar([i + w / 2 for i in x], ovals, width=w, label="Organic", color="#1b7f3b")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Feature count")
    ax.set_title("Figure 1: Dataset Scale Coverage")
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    fig.savefig(output_dir / "fig1_scale_coverage.png", dpi=220)
    plt.close(fig)

    # Figure 2: vertex vs path length
    fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    ax.scatter([r.vertex_count for r in mech], [r.path_length for r in mech], s=22, alpha=0.72, label="Mechanical", color="#0b5cad")
    ax.scatter([r.vertex_count for r in org], [r.path_length for r in org], s=28, alpha=0.7, marker="^", label="Organic", color="#1b7f3b")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Vertex count (log)")
    ax.set_ylabel("Path length (log)")
    ax.set_title("Figure 2: Vertex Count vs Path Length")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.savefig(output_dir / "fig2_vertex_vs_length.png", dpi=220)
    plt.close(fig)

    # Figure 3: sinuosity boxplot
    m_s = [r.sinuosity for r in mech if math.isfinite(r.sinuosity) and r.sinuosity > 0]
    o_s = [r.sinuosity for r in org if math.isfinite(r.sinuosity) and r.sinuosity > 0]
    fig, ax = plt.subplots(figsize=(6.8, 4.5), constrained_layout=True)
    ax.boxplot(
        [m_s, o_s],
        tick_labels=["Mechanical", "Organic"],
        patch_artist=True,
        boxprops={"facecolor": "#d7e9ff"},
        medianprops={"color": "#111111"},
    )
    ax.set_ylabel("Sinuosity")
    ax.set_title("Figure 3: Sinuosity Distribution")
    ax.grid(alpha=0.25, axis="y")
    fig.savefig(output_dir / "fig3_sinuosity_boxplot.png", dpi=220)
    plt.close(fig)

    # Figure 4: turning-angle hist
    fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    m_t = [r.turn_mean_abs for r in mech if r.turn_mean_abs > 0]
    o_t = [r.turn_mean_abs for r in org if r.turn_mean_abs > 0]
    ax.hist(m_t, bins=20, alpha=0.65, label="Mechanical", color="#0b5cad")
    ax.hist(o_t, bins=18, alpha=0.65, label="Organic", color="#1b7f3b")
    ax.set_xlabel("Mean absolute turning angle (degrees)")
    ax.set_ylabel("Feature count")
    ax.set_title("Figure 4: Local Angular Complexity")
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    fig.savefig(output_dir / "fig4_turning_angle_hist.png", dpi=220)
    plt.close(fig)

    # Figure 5: A/B/C panel
    random.seed(7)
    edge_x = [i / 249 for i in range(250)]
    edge_clean = [(x, 0.0) for x in edge_x]
    edge_noisy = [(x, random.gauss(0.0, 0.02)) for x in edge_x]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    mx, my = zip(*mechanical_polyline)
    axes[0].plot(mx, my, color="#0b5cad", linewidth=1.4)
    axes[0].set_title("A: Mechanical SLO Trail")
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].grid(alpha=0.25)

    ox, oy = zip(*organic_polyline)
    axes[1].plot(ox, oy, color="#1b7f3b", linewidth=1.4)
    axes[1].set_title("B: Organic CA Boundary Section")
    axes[1].set_aspect("equal", adjustable="box")
    axes[1].grid(alpha=0.25)

    cx, cy = zip(*edge_clean)
    nx, ny = zip(*edge_noisy)
    axes[2].plot(cx, cy, color="#111111", label="Before noise", linewidth=1.5)
    axes[2].plot(nx, ny, color="#c23b22", label="After Gaussian noise", linewidth=1.0)
    axes[2].set_title("C: Edge Case")
    axes[2].legend(loc="best")
    axes[2].grid(alpha=0.25)

    for ax in axes:
        ax.set_xlabel("x")
        ax.set_ylabel("y")

    fig.savefig(output_dir / "fig5_abc_snapshots.png", dpi=240)
    plt.close(fig)


def write_metrics_report(records: Sequence[FeatureRecord], output_txt: Path) -> List[str]:
    output_txt.parent.mkdir(parents=True, exist_ok=True)

    by_cat = summarize(records)
    total = len(records)

    mech_stats = category_stats(records, "Mechanical")
    org_stats = category_stats(records, "Organic")

    lines: List[str] = []
    lines.append("DATA CHARACTERIZATION REPORT")
    lines.append("=" * 72)
    lines.append(f"Total features: {total}")
    lines.append("")
    lines.append("Scale coverage by category:")
    for cat, vals in by_cat.items():
        lines.append(
            f"- {cat}: total={vals['total']}, small={vals['small']}, medium={vals['medium']}, large={vals['large']}, uncategorized={vals['uncat']}"
        )

    lines.append("")
    lines.append("Mechanical summary:")
    lines.append(
        f"- vertex_count: mean={mech_stats['vertex_mean']:.2f}, min={mech_stats['vertex_min']:.0f}, max={mech_stats['vertex_max']:.0f}"
    )
    lines.append(f"- sinuosity mean={mech_stats['sinu_mean']:.3f}")
    lines.append(f"- turn_mean_abs mean={mech_stats['turn_mean']:.3f}")

    lines.append("")
    lines.append("Organic summary:")
    lines.append(
        f"- vertex_count: mean={org_stats['vertex_mean']:.2f}, min={org_stats['vertex_min']:.0f}, max={org_stats['vertex_max']:.0f}"
    )
    lines.append(f"- sinuosity mean={org_stats['sinu_mean']:.3f}")
    lines.append(f"- turn_mean_abs mean={org_stats['turn_mean']:.3f}")

    insufficient: List[str] = []
    if sum(1 for r in records if size_bin(r.vertex_count).startswith("Small")) < 10:
        insufficient.append("Need more Small (<500) curves for stable statistics (target >= 10).")
    if sum(1 for r in records if size_bin(r.vertex_count).startswith("Medium")) < 10:
        insufficient.append("Need more Medium (5k-20k) curves for balanced comparison (target >= 10).")
    if sum(1 for r in records if size_bin(r.vertex_count).startswith("Large")) < 2:
        insufficient.append("Need at least 2 Large (>100k) curves for credible stress-test claims.")

    lines.append("")
    lines.append("Data sufficiency check:")
    if insufficient:
        for msg in insufficient:
            lines.append(f"- INSUFFICIENT: {msg}")
    else:
        lines.append("- Current data appears sufficient for the planned report scope.")

    output_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return insufficient


def write_diagram_analysis(records: Sequence[FeatureRecord], insufficiency: Sequence[str], output_md: Path) -> None:
    output_md.parent.mkdir(parents=True, exist_ok=True)

    mech = [r for r in records if r.category == "Mechanical"]
    org = [r for r in records if r.category == "Organic"]

    def mean(xs: Sequence[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    m_vertices = [r.vertex_count for r in mech]
    o_vertices = [r.vertex_count for r in org]
    m_sinu = [r.sinuosity for r in mech if r.sinuosity > 0 and math.isfinite(r.sinuosity)]
    o_sinu = [r.sinuosity for r in org if r.sinuosity > 0 and math.isfinite(r.sinuosity)]
    m_turn = [r.turn_mean_abs for r in mech if r.turn_mean_abs > 0]
    o_turn = [r.turn_mean_abs for r in org if r.turn_mean_abs > 0]

    m_small = sum(1 for r in mech if size_bin(r.vertex_count).startswith("Small"))
    m_med = sum(1 for r in mech if size_bin(r.vertex_count).startswith("Medium"))
    m_lg = sum(1 for r in mech if size_bin(r.vertex_count).startswith("Large"))

    o_small = sum(1 for r in org if size_bin(r.vertex_count).startswith("Small"))
    o_med = sum(1 for r in org if size_bin(r.vertex_count).startswith("Medium"))
    o_lg = sum(1 for r in org if size_bin(r.vertex_count).startswith("Large"))

    if m_med == 0 and m_lg == 0:
        mech_scale_sentence = (
            f"Mechanical datasets are concentrated in the Small bin (n={m_small}), "
            f"with no Medium or Large mechanical curves (Medium={m_med}, Large={m_lg})."
        )
    else:
        mech_scale_sentence = (
            f"Mechanical datasets span all intended scales with Small={m_small}, "
            f"Medium={m_med}, and Large={m_lg}."
        )

    if mean(o_vertices) > mean(m_vertices):
        sep_sentence = (
            f"Organic curves occupy a higher-vertex regime (mean vertices={mean(o_vertices):.1f}) "
            f"than mechanical curves (mean vertices={mean(m_vertices):.1f})."
        )
    else:
        sep_sentence = (
            f"Mechanical curves occupy a higher-vertex regime (mean vertices={mean(m_vertices):.1f}) "
            f"than organic curves (mean vertices={mean(o_vertices):.1f}), mainly due to synthetic stress-test bundles."
        )

    text = [
        "# Diagram Analysis (Report-Ready)",
        "",
        "Suggested text for the Data Characterization section:",
        "",
        "## Figure 1: Dataset Scale Coverage",
        f"{mech_scale_sentence} Organic datasets are distributed as Medium={o_med}, Small={o_small}, Large={o_lg}, with additional Uncategorized county boundaries.",
        "",
        "## Figure 2: Vertex Count vs Path Length (log-log)",
        f"{sep_sentence} This supports category contrast while still providing cross-scale stress-test coverage for algorithm runtime and fidelity analysis.",
        "",
        "## Figure 3: Sinuosity Distribution",
        f"Mechanical sinuosity has mean {mean(m_sinu):.3f}; organic sinuosity has mean {mean(o_sinu):.3f}. This indicates different path-efficiency/curvature behaviors between categories and provides a quantitative basis for evaluating shape preservation under compression.",
        "",
        "## Figure 4: Local Angular Complexity",
        f"Mean absolute turning angle is higher for mechanical data ({mean(m_turn):.3f} deg) than organic data ({mean(o_turn):.3f} deg) in the current sample, likely because many mechanical inputs are short segmented polylines with sharp joins. This further supports consolidating trail segments before final algorithm comparison.",
        "",
        "## Figure 5: A/B/C Snapshots",
        "Plot A and Plot B provide visual anchors for category differences (human-constrained trail vs irregular boundary). Plot C illustrates sensitivity to high-frequency perturbations and justifies including a noise edge-case in the algorithm evaluation protocol.",
        "",
        "## Data Sufficiency Note",
    ]

    if insufficiency:
        text.append("Current dataset is not yet sufficient for a polished final comparison:")
        for msg in insufficiency:
            text.append(f"- {msg}")
    else:
        text.append("Current dataset coverage is sufficient for the planned comparison.")

    output_md.write_text("\n".join(text) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare characterization outputs for report-ready data section.")
    parser.add_argument("--coast", type=Path, default=Path("data/California_Counties_68233851330457591.geojson"))
    parser.add_argument("--county-trails", type=Path, default=Path("data/County_Trails.geojson"))
    parser.add_argument("--proposed-trails", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("parsing/output"))
    args = parser.parse_args()

    records: List[FeatureRecord] = []

    county_records, county_lines = collect_records(
        args.county_trails,
        source_label=args.county_trails.stem,
        category="Mechanical",
        group_key="TrailName",
    )
    proposed_records: List[FeatureRecord] = []
    proposed_lines: List[List[Point]] = []
    if args.proposed_trails:
        proposed_records, proposed_lines = collect_records(
            args.proposed_trails,
            source_label=args.proposed_trails.stem,
            category="Mechanical",
            group_key="Trail_Name",
        )
    coast_records, coast_lines = collect_records(
        args.coast,
        source_label=args.coast.stem,
        category="Organic",
        group_key=None,
    )

    records.extend(county_records)
    records.extend(proposed_records)
    records.extend(coast_records)

    dedup: Dict[Tuple[str, str, str], FeatureRecord] = {}
    for r in records:
        dedup[(r.source, r.feature_id, r.category)] = r
    records = list(dedup.values())

    write_csv(records, args.output_dir / "dataset_summary.csv")

    mechanical_line = max(county_lines + proposed_lines, key=len, default=[])
    organic_line = max(coast_lines, key=len, default=[])
    if len(mechanical_line) < 2 or len(organic_line) < 2:
        raise RuntimeError("Could not extract representative polylines for snapshot plots.")

    create_plots(records, mechanical_line, organic_line, args.output_dir)
    insuff = write_metrics_report(records, args.output_dir / "report_metrics.txt")
    write_diagram_analysis(records, insuff, args.output_dir / "diagram_analysis.md")

    print("Wrote:")
    for name in [
        "dataset_summary.csv",
        "report_metrics.txt",
        "diagram_analysis.md",
        "fig1_scale_coverage.png",
        "fig2_vertex_vs_length.png",
        "fig3_sinuosity_boxplot.png",
        "fig4_turning_angle_hist.png",
        "fig5_abc_snapshots.png",
    ]:
        print(f"- {args.output_dir / name}")


if __name__ == "__main__":
    main()
