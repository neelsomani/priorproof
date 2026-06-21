from __future__ import annotations

import argparse
import random
from pathlib import Path

from priorproof.cli.encoder_args import add_encoder_args, validate_encoder_selection
from priorproof.data.io import write_jsonl
from priorproof.corpus.pipeline import load_declarations, load_footprints, load_snapshots
from priorproof.modeling.prior import PriorConfig, build_hierarchical_prior, build_prior_count_state
from priorproof.modeling.retriever import RetrievalHit
from priorproof.metric.scoring import score_footprint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build unrelated-context priors for the parametric-leakage probe.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--snapshots", required=True)
    add_encoder_args(parser)
    parser.add_argument("--out-scores", required=True)
    parser.add_argument("--out-priors", required=True)
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--seed", type=int, default=29)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    declarations = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    snapshots = load_snapshots(args.snapshots)
    validate_encoder_selection(args, footprints, snapshots)
    by_name = {record.name: record for record in declarations}
    by_snapshot = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    footprints_by_decl = {footprint.declaration: footprint for footprint in footprints}
    count_states = {}
    pre_t_records_by_snapshot = {}
    scores = []
    priors = []
    for footprint in footprints:
        target = by_name.get(footprint.declaration)
        snapshot = by_snapshot.get(footprint.snapshot_id)
        if target is None or snapshot is None:
            continue
        if footprint.snapshot_id not in pre_t_records_by_snapshot:
            pre_t_records_by_snapshot[footprint.snapshot_id] = [
                by_name[name]
                for name in snapshot.declarations
                if name in by_name and name in footprints_by_decl
            ]
            count_states[footprint.snapshot_id] = build_prior_count_state(
                pre_t_records_by_snapshot[footprint.snapshot_id],
                footprints_by_decl,
            )
        pre_t_records = pre_t_records_by_snapshot[footprint.snapshot_id]
        if not pre_t_records:
            continue
        pool = [record for record in pre_t_records if record.namespace != target.namespace] or pre_t_records
        sampled = rng.sample(pool, k=min(args.k, len(pool))) if pool else []
        hits = [
            RetrievalHit(name=record.name, score=0.0, module=record.module, namespace=record.namespace)
            for record in sampled
        ]
        prior = build_hierarchical_prior(
            target,
            pre_t_records,
            footprints_by_decl,
            hits,
            PriorConfig(),
            count_state=count_states[footprint.snapshot_id],
        )
        score = score_footprint(footprint, prior, flags=("counterfactual_retrieval",))
        scores.append(score.to_json())
        priors.append(
            {
                "declaration": target.name,
                "snapshot_id": footprint.snapshot_id,
                "threshold": footprint.threshold,
                "retrieval_hits": [hit.to_json() for hit in hits],
                "prior": prior,
            }
        )
    write_jsonl(Path(args.out_scores), scores)
    write_jsonl(Path(args.out_priors), priors)


if __name__ == "__main__":
    main()
