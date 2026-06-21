from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import read_json, write_jsonl
from priorproof.corpus.pipeline import load_declarations, load_footprints, load_snapshots, score_with_retrieval_prior
from priorproof.modeling.prior import PriorConfig
from priorproof.cli.encoder_args import add_encoder_args, load_encoder_selection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score proof-footprint novelty with a retrieval-conditioned prior.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    add_encoder_args(parser)
    parser.add_argument("--snapshots", help="Optional snapshots.json. Required for strict start-of-bin leakage discipline.")
    parser.add_argument("--out-scores", required=True)
    parser.add_argument("--out-priors", required=True)
    parser.add_argument("--prior-grid", help="Optional prior_grid JSON. Uses its `best` row for scoring parameters.")
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--retrieval-weight", type=float, default=0.55)
    parser.add_argument("--namespace-weight", type=float, default=0.2)
    parser.add_argument("--module-weight", type=float, default=0.15)
    parser.add_argument("--global-weight", type=float, default=0.1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    declarations = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    snapshots = load_snapshots(args.snapshots) if args.snapshots else None
    encoder, encoders_by_snapshot = load_encoder_selection(args, footprints, snapshots)
    config = prior_config_from_args(args)
    scores, priors = score_with_retrieval_prior(
        declarations,
        footprints,
        encoder,
        encoders_by_snapshot=encoders_by_snapshot,
        config=config,
        k=args.k,
        snapshots=snapshots,
    )
    write_jsonl(Path(args.out_scores), scores)
    write_jsonl(Path(args.out_priors), priors)


def prior_config_from_args(args: argparse.Namespace) -> PriorConfig:
    if args.prior_grid:
        data = read_json(args.prior_grid)
        if not isinstance(data, dict) or not isinstance(data.get("best"), dict):
            raise ValueError("--prior-grid must contain an object with a `best` row")
        best = data["best"]
        return PriorConfig(
            alpha=float(best["alpha"]),
            retrieval_weight=float(best["retrieval_weight"]),
            namespace_weight=float(best["namespace_weight"]),
            module_weight=float(best["module_weight"]),
            global_weight=float(best["global_weight"]),
        )
    return PriorConfig(
        alpha=args.alpha,
        retrieval_weight=args.retrieval_weight,
        namespace_weight=args.namespace_weight,
        module_weight=args.module_weight,
        global_weight=args.global_weight,
    )


if __name__ == "__main__":
    main()
