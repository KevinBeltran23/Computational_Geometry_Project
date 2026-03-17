from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .experiment import RunResult


def plot_diagnostics(results: Sequence[RunResult], out_dir: Path) -> None:
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) runtime vs original vertices
    fig, ax = plt.subplots(figsize=(7, 4.8), constrained_layout=True)
    for algo, color, marker in [("DP", "#0b5cad", "o"), ("VW", "#c23b22", "^")]:
        rr = [r for r in results if r.algorithm == algo]
        ax.scatter([r.original_vertices for r in rr], [r.runtime_ms for r in rr], s=18, alpha=0.7, c=color, marker=marker, label=algo)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Original vertices (log)")
    ax.set_ylabel("Runtime ms (log)")
    ax.set_title("Runtime vs Input Size")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.savefig(out_dir / "diag_runtime_vs_size.png", dpi=220)
    plt.close(fig)

    # 2) achieved compression vs Hausdorff
    fig, ax = plt.subplots(figsize=(7, 4.8), constrained_layout=True)
    for algo, color, marker in [("DP", "#0b5cad", "o"), ("VW", "#c23b22", "^")]:
        rr = [r for r in results if r.algorithm == algo]
        ax.scatter([r.achieved_compression for r in rr], [r.hausdorff for r in rr], s=18, alpha=0.7, c=color, marker=marker, label=algo)
    ax.set_xlabel("Achieved compression")
    ax.set_ylabel("Hausdorff distance")
    ax.set_title("Compression vs Hausdorff Error")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.savefig(out_dir / "diag_compression_vs_hausdorff.png", dpi=220)
    plt.close(fig)

    # 3) max perpendicular error distributions
    fig, ax = plt.subplots(figsize=(7, 4.8), constrained_layout=True)
    dp = [r.max_perp_error for r in results if r.algorithm == "DP"]
    vw = [r.max_perp_error for r in results if r.algorithm == "VW"]
    ax.boxplot([dp, vw], tick_labels=["DP", "VW"], patch_artist=True, boxprops={"facecolor": "#ddeeff"})
    ax.set_ylabel("Max perpendicular error")
    ax.set_title("Error Distribution by Algorithm")
    ax.grid(alpha=0.25, axis="y")
    fig.savefig(out_dir / "diag_error_boxplot.png", dpi=220)
    plt.close(fig)
