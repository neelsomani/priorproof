from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import write_jsonl
from priorproof.corpus.pipeline import load_declarations, load_footprints, load_snapshots, score_with_retrieval_prior
from priorproof.modeling.prior import PriorConfig
from priorproof.cli.encoder_args import add_encoder_args, load_encoder_selection


ABLATIONS = {
    "no_retrieval": PriorConfig(retrieval_weight=0.0, namespace_weight=0.35, module_weight=0.3, global_weight=0.35),
    "no_namespace": PriorConfig(retrieval_weight=0.65, namespace_weight=0.0, module_weight=0.2, global_weight=0.15),
    "no_module": PriorConfig(retrieval_weight=0.65, namespace_weight=0.25, module_weight=0.0, global_weight=0.1),
    "global_only": PriorConfig(retrieval_weight=0.0, namespace_weight=0.0, module_weight=0.0, global_weight=1.0),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Produce validation retrieval/smoothing ablation score files.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--snapshots", required=True)
    add_encoder_args(parser)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--k", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    declarations = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    snapshots = load_snapshots(args.snapshots)
    encoder, encoders_by_snapshot = load_encoder_selection(args, footprints)
    for name, config in ABLATIONS.items():
        scores, priors = score_with_retrieval_prior(
            declarations,
            footprints,
            encoder,
            encoders_by_snapshot=encoders_by_snapshot,
            config=config,
            k=args.k,
            snapshots=snapshots,
        )
        write_jsonl(out_dir / f"{name}_scores.jsonl", scores)
        write_jsonl(out_dir / f"{name}_priors.jsonl", priors)


if __name__ == "__main__":
    main()
