# CSC 570 Final Project

## Project Info

- Project Title: `Experimental Comparison of Visvalingam-Whyatt and Douglas-Peucker Line Simplification`
- Author: `Kevin Beltran`
- Course: `CSC 570 Computational Geometry`
- Term: `Winter 2026`
- Report Source: `CG_Project_KevinBeltran.tex`

## Repository Layout

- `data/`: raw and derived datasets
- `data/derived/`: benchmark-ready mechanical/organic GeoJSON files
- `parsing/`: data parsing, characterization, and prep pipeline scripts
- `parsing/output/`: characterization tables and figures
- `impl/`: algorithm implementations, benchmark runners, and analysis scripts
- `impl/output/`: experiment CSV/JSON outputs and results figures

## Environment Setup

```bash
source .venv/bin/activate
uv sync
```

## Data Preparation and Characterization

### Quick parser

Script: `parsing/geojson_report_parser.py`

Default run:

```bash
uv run parsing/geojson_report_parser.py
```

Optional explicit paths:

```bash
uv run parsing/geojson_report_parser.py \
  --geojson data/California_Counties_68233851330457591.geojson \
  --plot-output parsing/report_snapshots.png
```

### Full characterization

Script: `parsing/data_characterization.py`

Outputs include:

- `parsing/output/dataset_summary.csv`
- `parsing/output/report_metrics.txt`
- `parsing/output/diagram_analysis.md`
- `parsing/output/fig1_scale_coverage.png`
- `parsing/output/fig2_vertex_vs_length.png`
- `parsing/output/fig3_sinuosity_boxplot.png`
- `parsing/output/fig4_turning_angle_hist.png`
- `parsing/output/fig5_abc_snapshots.png`

Run:

```bash
MPLCONFIGDIR=/tmp/matplotlib uv run parsing/data_characterization.py
```

### End-to-end prep pipeline

Script: `parsing/data_pipeline.py`

This pipeline:

- reads curated trail files + Overpass tile files
- deduplicates segments
- builds derived benchmark datasets
- regenerates characterization outputs

Run:

```bash
uv run parsing/data_pipeline.py
```

## Algorithm Implementation and Benchmarking

### Implementation structure

- `impl/simplify/douglas_peucker.py`
- `impl/simplify/visvalingam_whyatt.py`
- `impl/simplify/geometry.py`
- `impl/simplify/io.py`
- `impl/simplify/experiment.py`
- `impl/simplify/diagnostics.py`
- `impl/run_experiments.py`
- `impl/benchmark_suite.py`
- `impl/analyze_results.py`
- `impl/build_results_pack.py`

### Experiment runs

Quick debug:

```bash
MPLCONFIGDIR=/tmp/matplotlib uv run impl/run_experiments.py \
  --max-per-bin 1 \
  --targets 0.9 \
  --include-bins small \
  --max-vertices 5000 \
  --metric-max-points 1000
```

Balanced run:

```bash
MPLCONFIGDIR=/tmp/matplotlib uv run impl/run_experiments.py \
  --max-per-bin 3 \
  --targets 0.7,0.9 \
  --include-bins small,medium \
  --metric-max-points 3000
```

### Build consolidated results pack

```bash
MPLCONFIGDIR=/tmp/matplotlib uv run impl/build_results_pack.py \
  --inputs \
    impl/output/batch_small/experiment_runs.csv \
    impl/output/batch_medium_a/experiment_runs.csv \
    impl/output/batch_medium_b/experiment_runs.csv \
    impl/output/batch_mech_medium_a/experiment_runs.csv \
    impl/output/batch_org_medium_a/experiment_runs.csv \
    impl/output/batch_org_medium_b/experiment_runs.csv \
    impl/output/batch_large/suite_runs.csv \
  --out-dir impl/output/results_pack
```

Results pack outputs:

- `impl/output/results_pack/all_runs_merged.csv`
- `impl/output/results_pack/results_analysis.txt`
- `impl/output/results_pack/res_r1_compression_vs_max_perp.png`
- `impl/output/results_pack/res_r2_compression_vs_hausdorff.png`
- `impl/output/results_pack/res_r3_runtime_by_subset.png`
- `impl/output/results_pack/res_r4_runtime_scaling.png`
- `impl/output/results_pack/res_r5_runtime_vs_hausdorff.png`

## References

1. Ramer, U. (1972). _An iterative procedure for the polygonal approximation of plane curves_. Computer Graphics and Image Processing, 1(3), 244-256. <https://www.sciencedirect.com/science/article/abs/pii/S0146664X72800170>
2. Douglas, D. H., and Peucker, T. K. (1973). _Algorithms for the reduction of the number of points required to represent a digitized line or its caricature_. The Canadian Cartographer, 10(2), 112-122. <https://utppublishing.com/doi/abs/10.3138/FM57-6770-U75U-7727>
3. Visvalingam, M., and Whyatt, J. D. (1992). _Line generalisation by repeated elimination of points_. The Cartographic Journal, 30(1), 46-51. <https://www.tandfonline.com/doi/abs/10.1179/000870493786962263>
4. SciPy Community. (2024). `scipy.spatial.distance.directed_hausdorff` [Software Documentation]. <https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.directed_hausdorff.html>
5. Agafonkin, V. (2024). _Simplify.js: A high-performance polyline simplification library_. GitHub. <https://github.com/mourner/simplify-js>
6. Raifer, M. (2024). _Overpass Turbo: OpenStreetMap Data Extraction Tool_. <https://overpass-turbo.eu/>
7. California Department of Technology. (2024). _California County Boundaries_ [Dataset]. California Open Data Portal. <https://data.ca.gov/dataset/california-counties>
8. County of San Luis Obispo. (2024). _Parks and Recreation GIS Data Hub_ [Dataset]. SLO County Open Data. <https://opendata-slocounty.hub.arcgis.com/search?tags=Parks%20%26%20Recreation>
