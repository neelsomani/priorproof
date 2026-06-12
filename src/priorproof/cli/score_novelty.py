from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.modeling.neural_encoder import load_neural_statement_encoder
from priorproof.data.io import write_jsonl
from priorproof.corpus.pipeline import load_declarations, load_footprints, load_snapshots, score_with_retrieval_prior
from priorproof.modeling.prior import PriorConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score proof-footprint novelty with a retrieval-conditioned prior.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--snapshots", help="Optional snapshots.json. Required for strict start-of-bin leakage discipline.")
    parser.add_argument("--out-scores", required=True)
    parser.add_argument("--out-priors", required=True)
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
    encoder = load_neural_statement_encoder(args.encoder)
    config = PriorConfig(
        alpha=args.alpha,
        retrieval_weight=args.retrieval_weight,
        namespace_weight=args.namespace_weight,
        module_weight=args.module_weight,
        global_weight=args.global_weight,
    )
    scores, priors = score_with_retrieval_prior(
        declarations,
        footprints,
        encoder,
        config=config,
        k=args.k,
        snapshots=snapshots,
    )
    write_jsonl(Path(args.out_scores), scores)
    write_jsonl(Path(args.out_priors), priors)


if __name__ == "__main__":
    main()
