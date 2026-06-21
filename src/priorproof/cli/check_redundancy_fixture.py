from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.corpus.pipeline import build_footprints, load_declarations, load_snapshots
from priorproof.data.io import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that a constructed redundancy fixture produces detector hits."
    )
    parser.add_argument("--declarations", required=True, help="Normalized declaration JSONL fixture.")
    parser.add_argument("--snapshots", help="Optional snapshot JSON file. If omitted, quarterly snapshots are inferred.")
    parser.add_argument("--out", required=True, help="JSON report path.")
    parser.add_argument("--threshold", type=int, default=1)
    parser.add_argument("--expect-hit", action="store_true", help="Exit nonzero unless at least one hit is found.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    declarations = load_declarations(args.declarations)
    snapshots = load_snapshots(args.snapshots) if args.snapshots else None
    footprints = build_footprints(declarations, snapshots, threshold=args.threshold, min_family_support=1)
    examples = [
        {
            "declaration": footprint.declaration,
            "snapshot_id": footprint.snapshot_id,
            "hits": list(footprint.redundant_subterms),
        }
        for footprint in footprints
        if footprint.redundant_subterms
    ]
    report = {
        "declaration_count": len(declarations),
        "footprint_count": len(footprints),
        "redundancy_hit_count": sum(len(item["hits"]) for item in examples),
        "declarations_with_hits": len(examples),
        "examples": examples,
    }
    write_json(Path(args.out), report)
    if args.expect_hit and report["redundancy_hit_count"] == 0:
        raise SystemExit(f"No redundancy hits found in fixture: {args.declarations}")


if __name__ == "__main__":
    main()
