from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.corpus import build_quarterly_snapshots, module_density_by_snapshot
from priorproof.data.io import write_json
from priorproof.corpus.pipeline import build_footprints, load_declarations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute gate density and redundancy-feasibility gate artifacts.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    declarations = load_declarations(args.declarations)
    snapshots = build_quarterly_snapshots(declarations)
    density = module_density_by_snapshot(declarations, snapshots)
    footprints = build_footprints(declarations, snapshots, threshold=args.threshold)
    redundancy_hits = [
        {
            "declaration": footprint.declaration,
            "snapshot_id": footprint.snapshot_id,
            "hits": list(footprint.redundant_subterms),
        }
        for footprint in footprints
        if footprint.redundant_subterms
    ]
    write_json(
        Path(args.out),
        {
            "density": density,
            "redundancy_hit_count": len(redundancy_hits),
            "redundancy_examples": redundancy_hits[:50],
        },
    )


if __name__ == "__main__":
    main()

