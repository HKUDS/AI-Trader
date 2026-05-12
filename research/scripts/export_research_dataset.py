"""Export the complete research dataset and schemas."""

from __future__ import annotations

import argparse

from research_common import add_common_export_filters, ensure_dir, parse_agent_ids

from research_exports import (
    export_research_dataset,
    get_research_dataset_names,
    write_research_schemas,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="research/exports")
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    parser.add_argument("--datasets", help="Comma-separated dataset names. Defaults to all primary paper datasets.")
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--no-anonymize", action="store_true")
    parser.add_argument("--public-structure-only", action="store_true")
    add_common_export_filters(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = ensure_dir(args.output_dir)
    dataset_names = [name.strip() for name in args.datasets.split(",") if name.strip()] if args.datasets else get_research_dataset_names(primary_only=True)
    written = export_research_dataset(
        output_dir,
        dataset_names=dataset_names,
        output_format=args.format,
        start_at=args.start_at,
        end_at=args.end_at,
        experiment_key=args.experiment_key,
        variant_key=args.variant_key,
        market=args.market,
        agent_ids=parse_agent_ids(args.agent_ids),
        anonymize=not args.no_anonymize,
        include_content=not args.public_structure_only,
        limit=args.limit,
    )
    schema_dir = ensure_dir(output_dir.parent / "schemas" if output_dir.name == "exports" else "research/schemas")
    schemas = write_research_schemas(schema_dir, dataset_names)
    for filename, path in sorted(written.items()):
        print(f"exported {filename}: {path}")
    for filename, path in sorted(schemas.items()):
        print(f"schema {filename}: {path}")


if __name__ == "__main__":
    main()
