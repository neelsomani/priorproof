from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.corpus.pipeline import load_declarations, load_footprints
from priorproof.data.io import write_json, write_jsonl
from priorproof.modeling.contrastive import PairMiningConfig, mine_contrastive_examples, signal_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build proof-derived contrastive training examples for the statement encoder.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--out-examples", required=True)
    parser.add_argument("--out-report", required=True)
    parser.add_argument("--shared-family-min", type=int, default=2)
    parser.add_argument("--downstream-user-min", type=int, default=2)
    parser.add_argument("--namespace-symbol-jaccard-min", type=float, default=0.35)
    parser.add_argument("--lexical-negative-jaccard-min", type=float, default=0.25)
    parser.add_argument("--hard-negatives-per-pair", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    config = PairMiningConfig(
        shared_family_min=args.shared_family_min,
        downstream_user_min=args.downstream_user_min,
        namespace_symbol_jaccard_min=args.namespace_symbol_jaccard_min,
        lexical_negative_jaccard_min=args.lexical_negative_jaccard_min,
        hard_negatives_per_pair=args.hard_negatives_per_pair,
    )
    examples = mine_contrastive_examples(records, footprints, config)
    write_jsonl(Path(args.out_examples), examples)
    write_json(
        Path(args.out_report),
        {
            "declaration_count": len(records),
            "footprint_count": len(footprints),
            "example_count": len(examples),
            "positive_signal_counts": dict(signal_counts(examples)),
            "hard_negative_count": sum(len(example.hard_negatives) for example in examples),
        },
    )


if __name__ == "__main__":
    main()

