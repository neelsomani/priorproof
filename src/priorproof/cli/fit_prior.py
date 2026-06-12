from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.modeling.neural_encoder import load_neural_statement_encoder
from priorproof.data.io import write_json
from priorproof.corpus.pipeline import load_declarations, load_footprints, load_snapshots, score_with_retrieval_prior
from priorproof.modeling.prior import PriorConfig, chronological_log_likelihood


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grid-search prior mixture parameters by chronological likelihood.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--snapshots", help="Optional snapshots.json. Required for strict start-of-bin leakage discipline.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--k", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    declarations = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    snapshots = load_snapshots(args.snapshots) if args.snapshots else None
    encoder = load_neural_statement_encoder(args.encoder)
    candidates = [
        PriorConfig(alpha=alpha, retrieval_weight=rw, namespace_weight=nw, module_weight=mw, global_weight=gw)
        for alpha in (0.1, 0.25, 0.5)
        for rw, nw, mw, gw in (
            (0.55, 0.2, 0.15, 0.1),
            (0.4, 0.25, 0.2, 0.15),
            (0.7, 0.1, 0.1, 0.1),
            (0.0, 0.35, 0.3, 0.35),
        )
    ]
    rows = []
    best = None
    best_ll = float("-inf")
    for config in candidates:
        _, prior_rows = score_with_retrieval_prior(
            declarations,
            footprints,
            encoder,
            config=config,
            k=args.k,
            snapshots=snapshots,
        )
        priors = {row["declaration"]: row["prior"] for row in prior_rows}
        ll = chronological_log_likelihood(footprints, priors)
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


if __name__ == "__main__":
    main()
