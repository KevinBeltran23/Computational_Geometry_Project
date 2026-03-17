#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def load_rows(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def f(x: str) -> float:
    return float(x)


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def median(xs):
    if not xs:
        return 0.0
    xs2 = sorted(xs)
    return xs2[len(xs2) // 2]


def plot_suite(rows, out_dir: Path) -> None:
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    # Prepare grouped structures
    by_subset_target_algo = defaultdict(list)
    by_subset_algo = defaultdict(list)
    for r in rows:
        key = (r["category"], r["size_bin"], f(r["compression_target"]), r["algorithm"])
        by_subset_target_algo[key].append(r)
        by_subset_algo[(r["category"], r["size_bin"], r["algorithm"])].append(r)

    categories = ["Mechanical", "Organic"]
    bins = ["small", "medium", "large"]

    # Figure 1: Compression vs Max Perpendicular Error
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), constrained_layout=True)
    for i, cat in enumerate(categories):
        for j, b in enumerate(bins):
            ax = axes[i][j]
            has_any = False
            for algo, color, marker in [("DP", "#0b5cad", "o"), ("VW", "#c23b22", "^")]:
                pts = []
                for t in sorted({f(r["compression_target"]) for r in rows}):
                    rs = by_subset_target_algo.get((cat, b, t, algo), [])
                    if rs:
                        pts.append((mean([f(x["achieved_compression"]) for x in rs]), mean([f(x["max_perp_error"]) for x in rs])))
                if pts:
                    has_any = True
                    ax.plot([x for x, _ in pts], [y for _, y in pts], marker=marker, color=color, label=algo)
            ax.set_title(f"{cat} / {b}")
            ax.set_xlabel("Achieved compression")
            ax.set_ylabel("Max perpendicular error")
            ax.grid(alpha=0.25)
            if has_any:
                ax.legend()
    fig.suptitle("Figure R1: Compression vs Max Perpendicular Error", fontsize=13)
    fig.savefig(out_dir / "res_r1_compression_vs_max_perp.png", dpi=230)
    plt.close(fig)

    # Figure 2: Compression vs Hausdorff
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), constrained_layout=True)
    for i, cat in enumerate(categories):
        for j, b in enumerate(bins):
            ax = axes[i][j]
            has_any = False
            for algo, color, marker in [("DP", "#0b5cad", "o"), ("VW", "#c23b22", "^")]:
                pts = []
                for t in sorted({f(r["compression_target"]) for r in rows}):
                    rs = by_subset_target_algo.get((cat, b, t, algo), [])
                    if rs:
                        pts.append((mean([f(x["achieved_compression"]) for x in rs]), mean([f(x["hausdorff"]) for x in rs])))
                if pts:
                    has_any = True
                    ax.plot([x for x, _ in pts], [y for _, y in pts], marker=marker, color=color, label=algo)
            ax.set_title(f"{cat} / {b}")
            ax.set_xlabel("Achieved compression")
            ax.set_ylabel("Hausdorff distance")
            ax.grid(alpha=0.25)
            if has_any:
                ax.legend()
    fig.suptitle("Figure R2: Compression vs Hausdorff Distance", fontsize=13)
    fig.savefig(out_dir / "res_r2_compression_vs_hausdorff.png", dpi=230)
    plt.close(fig)

    # Figure 3: Runtime distribution by bin + algorithm
    labels = []
    dp_vals = []
    vw_vals = []
    for cat in categories:
        for b in bins:
            labels.append(f"{cat[:4]}-{b[:3]}")
            dp_rs = by_subset_algo.get((cat, b, "DP"), [])
            vw_rs = by_subset_algo.get((cat, b, "VW"), [])
            dp_vals.append(median([f(r["runtime_ms"]) for r in dp_rs]) if dp_rs else 0.0)
            vw_vals.append(median([f(r["runtime_ms"]) for r in vw_rs]) if vw_rs else 0.0)

    fig, ax = plt.subplots(figsize=(11, 4.8), constrained_layout=True)
    x = list(range(len(labels)))
    w = 0.38
    ax.bar([i - w / 2 for i in x], dp_vals, width=w, label="DP", color="#0b5cad")
    ax.bar([i + w / 2 for i in x], vw_vals, width=w, label="VW", color="#c23b22")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_yscale("log")
    ax.set_ylabel("Median runtime (ms, log scale)")
    ax.set_title("Figure R3: Runtime Comparison by Subset")
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    fig.savefig(out_dir / "res_r3_runtime_by_subset.png", dpi=230)
    plt.close(fig)

    # Figure 4: Runtime vs input size scatter
    fig, ax = plt.subplots(figsize=(7.2, 5), constrained_layout=True)
    for algo, color, marker in [("DP", "#0b5cad", "o"), ("VW", "#c23b22", "^")]:
        rs = [r for r in rows if r["algorithm"] == algo]
        ax.scatter([f(r["original_vertices"]) for r in rs], [f(r["runtime_ms"]) for r in rs], s=16, alpha=0.65, c=color, marker=marker, label=algo)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Original vertices (log)")
    ax.set_ylabel("Runtime ms (log)")
    ax.set_title("Figure R4: Runtime Scaling")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.savefig(out_dir / "res_r4_runtime_scaling.png", dpi=230)
    plt.close(fig)

    # Figure 5: Pareto-like scatter (runtime vs Hausdorff)
    fig, ax = plt.subplots(figsize=(7.2, 5), constrained_layout=True)
    for algo, color, marker in [("DP", "#0b5cad", "o"), ("VW", "#c23b22", "^")]:
        rs = [r for r in rows if r["algorithm"] == algo]
        ax.scatter([f(r["runtime_ms"]) for r in rs], [f(r["hausdorff"]) for r in rs], s=16, alpha=0.65, c=color, marker=marker, label=algo)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Runtime ms (log)")
    ax.set_ylabel("Hausdorff distance (log)")
    ax.set_title("Figure R5: Runtime vs Hausdorff Tradeoff")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.savefig(out_dir / "res_r5_runtime_vs_hausdorff.png", dpi=230)
    plt.close(fig)


def write_analysis(rows, out_txt: Path) -> None:
    subsets = defaultdict(list)
    for r in rows:
        subsets[(r["category"], r["size_bin"], r["algorithm"])].append(r)

    lines = []
    lines.append("RESULT ANALYSIS SUMMARY")
    lines.append("=" * 72)
    lines.append(f"Total runs: {len(rows)}")
    lines.append("")

    lines.append("Per-subset means:")
    for key in sorted(subsets.keys()):
        cat, b, algo = key
        rs = subsets[key]
        lines.append(
            f"- {cat}/{b}/{algo}: n={len(rs)}, mean_runtime_ms={mean([f(r['runtime_ms']) for r in rs]):.3f}, "
            f"mean_max_perp={mean([f(r['max_perp_error']) for r in rs]):.6f}, mean_hausdorff={mean([f(r['hausdorff']) for r in rs]):.6f}, "
            f"mean_compression={mean([f(r['achieved_compression']) for r in rs]):.6f}"
        )

    # algorithm-level runtime comparison
    for b in ["small", "medium", "large"]:
        dp = [f(r["runtime_ms"]) for r in rows if r["size_bin"] == b and r["algorithm"] == "DP"]
        vw = [f(r["runtime_ms"]) for r in rows if r["size_bin"] == b and r["algorithm"] == "VW"]
        if dp and vw:
            lines.append(
                f"- Runtime median ({b}): DP={median(dp):.3f} ms, VW={median(vw):.3f} ms, speedup(DP/VW)={median(dp)/max(median(vw),1e-12):.2f}x"
            )

    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate results-phase plots and analysis text from suite runs.")
    parser.add_argument("--runs-csv", type=Path, default=Path("impl/output/suite/suite_runs.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("impl/output/results"))
    args = parser.parse_args()

    rows = load_rows(args.runs_csv)
    if not rows:
        raise SystemExit("No rows found in runs csv.")

    plot_suite(rows, args.out_dir)
    write_analysis(rows, args.out_dir / "results_analysis.txt")

    print(f"Loaded runs: {len(rows)}")
    print(f"Wrote plots + analysis to: {args.out_dir}")


if __name__ == "__main__":
    main()
