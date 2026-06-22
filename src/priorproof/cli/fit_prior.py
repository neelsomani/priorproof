from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import read_json, write_json
from priorproof.corpus.pipeline import (
    build_retrieval_prior_contexts,
    load_declarations,
    load_footprints,
    load_snapshots,
    score_retrieval_prior_contexts,
)
from priorproof.modeling.prior import PriorConfig, chronological_log_likelihood
from priorproof.cli.encoder_args import add_encoder_args, load_encoder_selection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grid-search prior mixture parameters by chronological likelihood.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    add_encoder_args(parser)
    parser.add_argument("--snapshots", help="Optional snapshots.json. Required for strict start-of-bin leakage discipline.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--target-declarations", help="Optional JSON list of declaration names to fit on.")
    parser.add_argument("--k", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    declarations = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    snapshots = load_snapshots(args.snapshots) if args.snapshots else None
    encoder, encoders_by_snapshot = load_encoder_selection(args, footprints, snapshots)
    contexts, footprints_by_decl = build_retrieval_prior_contexts(
        declarations,
        footprints,
        encoder,
        encoders_by_snapshot=encoders_by_snapshot,
        k=args.k,
        snapshots=snapshots,
        target_names=load_target_names(args.target_declarations),
    )
    scored_footprints = [context.footprint for context in contexts]
    candidates = [
        PriorConfig(alpha=alpha, retrieval_weight=rw, namespace_weight=nw, module_weight=mw, global_weight=gw)
        for alpha in (0.01, 0.025, 0.05, 0.1, 0.25, 0.5)
        for rw, nw, mw, gw in (
            (0.55, 0.2, 0.15, 0.1),
            (0.4, 0.25, 0.2, 0.15),
            (0.7, 0.1, 0.1, 0.1),
            (0.8, 0.08, 0.06, 0.06),
            (0.9, 0.04, 0.03, 0.03),
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 0.35, 0.3, 0.35),
        )
    ]
    rows = []
    best = None
    best_ll = float("-inf")
    for config in candidates:
        _, prior_rows = score_retrieval_prior_contexts(contexts, footprints_by_decl, config=config)
        priors = {row["declaration"]: row["prior"] for row in prior_rows}
        ll = chronological_log_likelihood(scored_footprints, priors)
        row = {
            "alpha": config.alpha,
            "retrieval_weight": config.retrieval_weight,
            "namespace_weight": config.namespace_weight,
            "module_weight": config.module_weight,
            "global_weight": config.global_weight,
            "log_likelihood": ll,
        }
        rows.append(row)
        if ll > best_ll:
            best_ll = ll
            best = row
    write_json(Path(args.out), {"best": best, "grid": rows})


def load_target_names(path: str | None) -> set[str] | None:
    if not path:
        return None
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError("--target-declarations must contain a JSON list")
    return {str(item) for item in data}


if __name__ == "__main__":
    main()
