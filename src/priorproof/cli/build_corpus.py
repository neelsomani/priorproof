from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.corpus import build_quarterly_snapshots, module_density_by_snapshot
from priorproof.data.io import write_json
from priorproof.corpus.pipeline import build_footprints, load_declarations, save_footprints, save_snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build snapshots and metric footprints from extracted declarations.")
    parser.add_argument("--declarations", required=True, help="Input JSONL declaration records.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    parser.add_argument("--thresholds", default="3,5,8,13", help="Comma-separated reuse thresholds.")
    parser.add_argument("--min-family-support", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    declarations = load_declarations(args.declarations)
    snapshots = build_quarterly_snapshots(declarations)
    save_snapshots(out_dir / "snapshots.json", snapshots)
    write_json(out_dir / "density.json", module_density_by_snapshot(declarations, snapshots))
    for threshold in [int(value) for value in args.thresholds.split(",") if value.strip()]:
        footprints = build_footprints(
            declarations,
            snapshots,
            threshold=threshold,
            min_family_support=args.min_family_support,
        )
        save_footprints(out_dir / f"footprints_t{threshold}.jsonl", footprints)


if __name__ == "__main__":
    main()

