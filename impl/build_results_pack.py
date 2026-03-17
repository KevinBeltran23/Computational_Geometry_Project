#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from analyze_results import plot_suite, write_analysis


def read_csv(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge batch run CSVs and build final results plots/text.")
    parser.add_argument("--out-dir", type=Path, default=Path("impl/output/results_pack"))
    parser.add_argument(
        "--inputs",
        nargs="*",
        default=[
            "impl/output/batch_small/experiment_runs.csv",
            "impl/output/batch_medium_a/experiment_runs.csv",
            "impl/output/batch_medium_b/experiment_runs.csv",
            "impl/output/batch_large/suite_runs.csv",
        ],
    )
    args = parser.parse_args()

    rows = []
    for p in args.inputs:
        path = Path(p)
        if path.exists():
            rows.extend(read_csv(path))

    if not rows:
        raise SystemExit("No input run CSVs found.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    merged = args.out_dir / "all_runs_merged.csv"
    with merged.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    plot_suite(rows, args.out_dir)
    write_analysis(rows, args.out_dir / "results_analysis.txt")

    print(f"Merged runs: {len(rows)}")
    print(f"Wrote: {merged}")
    print(f"Wrote results plots and analysis in: {args.out_dir}")


if __name__ == "__main__":
    main()
