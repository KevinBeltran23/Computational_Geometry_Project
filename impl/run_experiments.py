#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from simplify.diagnostics import plot_diagnostics
from simplify.experiment import run_experiments, summarize_results, write_results_csv, write_summary_json
from simplify.io import load_curves, select_curves


def parse_targets(raw: str) -> list[float]:
    vals = []
    for x in raw.split(","):
        x = x.strip()
        if not x:
            continue
        vals.append(float(x))
    return vals


def parse_bins(raw: str) -> tuple[str, ...]:
    vals = tuple(x.strip().lower() for x in raw.split(",") if x.strip())
    if not vals:
        return ("small", "medium", "large")
    return vals


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DP/VW simplification experiments on derived datasets.")
    parser.add_argument("--mechanical", type=Path, default=Path("data/derived/mechanical_benchmarks.geojson"))
    parser.add_argument("--organic", type=Path, default=Path("data/derived/organic_benchmarks.geojson"))
    parser.add_argument("--out-dir", type=Path, default=Path("impl/output"))
    parser.add_argument("--max-per-bin", type=int, default=8, help="Max curves per size bin per category.")
    parser.add_argument("--targets", type=str, default="0.5,0.7,0.9", help="Comma-separated compression targets.")
    parser.add_argument("--metric-max-points", type=int, default=8000, help="Max points used when computing error metrics.")
    parser.add_argument("--include-bins", type=str, default="small,medium,large", help="Comma-separated bins to include.")
    parser.add_argument("--max-vertices", type=int, default=0, help="If >0, ignore curves larger than this many vertices.")
    args = parser.parse_args()

    targets = parse_targets(args.targets)
    include_bins = parse_bins(args.include_bins)
    if not targets:
        raise SystemExit("No compression targets provided.")

    mech_curves = load_curves(args.mechanical, default_category="Mechanical")
    org_curves = load_curves(args.organic, default_category="Organic")

    selected = []
    selected.extend(select_curves(mech_curves, max_per_bin=args.max_per_bin, include_bins=include_bins))
    selected.extend(select_curves(org_curves, max_per_bin=args.max_per_bin, include_bins=include_bins))
    if args.max_vertices > 0:
        selected = [c for c in selected if c.vertex_count <= args.max_vertices]

    if not selected:
        raise SystemExit("No curves selected. Check input files.")

    results = run_experiments(selected, targets, metric_max_points=args.metric_max_points)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = args.out_dir / "experiment_runs.csv"
    out_json = args.out_dir / "experiment_summary.json"

    write_results_csv(results, out_csv)
    summary = summarize_results(results)
    write_summary_json(summary, out_json)
    plot_diagnostics(results, args.out_dir)

    print(f"Selected curves: {len(selected)}")
    print(f"Runs: {len(results)}")
    print(f"Wrote: {out_csv}")
    print(f"Wrote: {out_json}")
    print(f"Wrote diagnostics in: {args.out_dir}")


if __name__ == "__main__":
    main()
