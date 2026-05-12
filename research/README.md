# Research Analysis Pipeline

This directory turns AI-Trader platform data into reproducible paper datasets,
metrics, statistical tables, and figures for the 4k+ agent competition and
cooperation study.

PostgreSQL production data is the authoritative source. The scripts read from
the unified backend export layer in `service/server/research_exports.py` or from
CSV files that were produced by that layer. SQLite is only a local fixture or
small-sample fallback.

## One-Command Workflows

Export the full anonymized research dataset:

```bash
python research/scripts/export_research_dataset.py --output-dir research/exports
```

Generate the main paper tables from exported CSVs:

```bash
python research/scripts/analyze_experiments.py --input-dir research/exports --output-dir research/exports/tables
```

Generate the main paper figures:

```bash
python research/scripts/generate_figures.py --input-dir research/exports --tables-dir research/exports/tables --output-dir research/exports/figures
```

## Dataset Filters

All export commands support:

- `--start-at` and `--end-at`
- `--experiment-key`
- `--variant-key`
- `--market`
- `--agent-ids` as a comma-separated allowlist
- `--no-anonymize` for private internal exports
- `--public-structure-only` to replace free text content with stable hashes

Exports default to anonymized output. Agent integer IDs are retained and paired
with stable `agent_hash` columns. Agent names are hashed. Metadata JSON is
redacted for token, email, wallet, password, secret, session, and auth fields.

## Scripts

- `export_research_dataset.py`: writes all paper CSVs and schemas.
- `build_agent_features.py`: computes agent-level behavioral and performance features.
- `build_network_edges.py`: materializes interaction network edges.
- `compute_metrics.py`: computes competition, cooperation, and content metrics.
- `analyze_experiments.py`: produces A/B, DiD, regression, HTE, bootstrap CI, and FDR tables.
- `generate_figures.py`: generates the eight paper figures.
