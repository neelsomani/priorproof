from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.corpus.pipeline import load_declarations, load_footprints, load_snapshots
from priorproof.data.io import write_json, write_jsonl
from priorproof.modeling.contrastive import PairMiningConfig, mine_contrastive_examples, signal_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build proof-derived contrastive training examples for the statement encoder.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--snapshots", help="Snapshot file used with --train-before-snapshot.")
    parser.add_argument(
        "--train-before-snapshot",
        help="Mine examples only from declarations available in this snapshot's pre-bin corpus.",
    )
    parser.add_argument("--out-examples", required=True)
    parser.add_argument("--out-report", required=True)
    parser.add_argument("--shared-family-min", type=int, default=2)
    parser.add_argument("--downstream-user-min", type=int, default=2)
    parser.add_argument("--namespace-symbol-jaccard-min", type=float, default=0.35)
    parser.add_argument("--lexical-negative-jaccard-min", type=float, default=0.25)
    parser.add_argument("--hard-negatives-per-pair", type=int, default=4)
    parser.add_argument("--max-pairs-per-signal", type=int, default=50_000)
    parser.add_argument("--bucket-window", type=int, default=16)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    if args.train_before_snapshot:
        if not args.snapshots:
            raise ValueError("--snapshots is required with --train-before-snapshot")
        snapshots = load_snapshots(args.snapshots)
        declarations = {
            name
            for snapshot in snapshots
            if snapshot.snapshot_id == args.train_before_snapshot
            for name in snapshot.declarations
        }
        if not declarations:
            raise ValueError(f"No declarations found for snapshot {args.train_before_snapshot!r}")
        records = [record for record in records if record.name in declarations]
        footprints = [footprint for footprint in footprints if footprint.declaration in declarations]
    config = PairMiningConfig(
        shared_family_min=args.shared_family_min,
        downstream_user_min=args.downstream_user_min,
        namespace_symbol_jaccard_min=args.namespace_symbol_jaccard_min,
        lexical_negative_jaccard_min=args.lexical_negative_jaccard_min,
        hard_negatives_per_pair=args.hard_negatives_per_pair,
        max_pairs_per_signal=args.max_pairs_per_signal,
        bucket_window=args.bucket_window,
    )
    examples = mine_contrastive_examples(records, footprints, config)
    write_jsonl(Path(args.out_examples), examples)
    write_json(
        Path(args.out_report),
        {
            "declaration_count": len(records),
            "footprint_count": len(footprints),
            "train_before_snapshot": args.train_before_snapshot,
            "example_count": len(examples),
            "positive_signal_counts": dict(signal_counts(examples)),
            "hard_negative_count": sum(len(example.hard_negatives) for example in examples),
        },
    )


if __name__ == "__main__":
    main()
