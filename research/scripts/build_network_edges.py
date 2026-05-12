"""Build interaction network edges and export network_edges.csv."""

from __future__ import annotations

import argparse

from research_common import add_common_export_filters, ensure_dir, parse_agent_ids

from experiment_metrics import build_network_edges
from research_exports import export_network_edges_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="research/exports")
    parser.add_argument("--no-materialize", action="store_true", help="Only export existing materialized edges.")
    parser.add_argument("--no-anonymize", action="store_true")
    add_common_export_filters(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.no_materialize:
        result = build_network_edges()
        print(f"materialized network_edges: {result}")
    path = export_network_edges_csv(
        ensure_dir(args.output_dir),
        start_at=args.start_at,
        end_at=args.end_at,
        experiment_key=args.experiment_key,
        variant_key=args.variant_key,
        market=args.market,
        agent_ids=parse_agent_ids(args.agent_ids),
        anonymize=not args.no_anonymize,
    )
    print(f"exported network_edges.csv: {path}")


if __name__ == "__main__":
    main()
