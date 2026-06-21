from __future__ import annotations

import argparse
import random
from pathlib import Path

from priorproof.corpus.pipeline import load_declarations, load_footprints, load_snapshots
from priorproof.data.models import Footprint, Snapshot
from priorproof.data.io import read_json, write_json
from priorproof.modeling.neural_encoder import load_encoder_map, load_neural_statement_encoder
from priorproof.modeling.retriever import StatementRetriever, neighbor_overlap
from priorproof.cli.encoder_args import required_encoder_snapshot_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare a frozen-early encoder's neighbor sets with per-snapshot encoders."
    )
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--snapshots", required=True)
    parser.add_argument("--reference-encoder", required=True, help="Frozen-early encoder directory.")
    parser.add_argument("--encoder-map", required=True, help="JSON mapping snapshot_id to per-snapshot encoder directory.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--sample-size", type=int, default=512)
    parser.add_argument("--min-mean-overlap", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=29)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    declarations = load_declarations(args.declarations)
    footprints = load_footprints(args.footprints)
    snapshots = load_snapshots(args.snapshots)
    reference_encoder = load_neural_statement_encoder(args.reference_encoder)
    mapping = read_json(args.encoder_map)
    if not isinstance(mapping, dict):
        raise ValueError("--encoder-map must contain a JSON object")
    encoders_by_snapshot = load_encoder_map(mapping)

    by_name = {record.name: record for record in declarations}
    footprints_by_decl = {footprint.declaration: footprint for footprint in footprints}
    by_snapshot = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    missing = sorted(set(required_encoder_snapshot_ids(footprints, snapshots)) - set(encoders_by_snapshot))
    if missing:
        raise ValueError(f"--encoder-map is missing snapshots: {missing}")
    encoder_paths = resolved_encoder_paths(mapping)
    self_comparison_snapshots = self_comparison_snapshot_ids(args.reference_encoder, encoder_paths)
    all_candidates = stability_candidates(footprints, by_snapshot, set(by_name))
    candidates = [
        footprint
        for footprint in all_candidates
        if footprint.snapshot_id not in self_comparison_snapshots
    ]
    if not candidates:
        raise ValueError(
            "No cross-bin stability samples are available after excluding snapshots whose "
            "encoder path is the same as --reference-encoder."
        )
    rng = random.Random(args.seed)
    rng.shuffle(candidates)
    sample = candidates[: args.sample_size]

    rows = []
    overlaps = []
    reference_retrievers: dict[str, StatementRetriever] = {}
    sliced_retrievers: dict[str, StatementRetriever] = {}
    for footprint in sample:
        target = by_name[footprint.declaration]
        snapshot = by_snapshot[footprint.snapshot_id]
        pre_t_records = [
            by_name[name]
            for name in snapshot.declarations
            if name in by_name and name in footprints_by_decl
        ]
        if not pre_t_records:
            continue
        if footprint.snapshot_id not in reference_retrievers:
            reference_retrievers[footprint.snapshot_id] = StatementRetriever(reference_encoder, pre_t_records)
            sliced_retrievers[footprint.snapshot_id] = StatementRetriever(
                encoders_by_snapshot[footprint.snapshot_id],
                pre_t_records,
            )
        reference_hits = reference_retrievers[footprint.snapshot_id].query(target, k=args.k)
        sliced_hits = sliced_retrievers[footprint.snapshot_id].query(target, k=args.k)
        overlap = neighbor_overlap(reference_hits, sliced_hits, k=args.k)
        overlaps.append(overlap)
        rows.append(
            {
                "declaration": target.name,
                "snapshot_id": footprint.snapshot_id,
                "overlap": overlap,
                "reference_encoder": str(Path(args.reference_encoder).resolve()),
                "sliced_encoder": str(encoder_paths[footprint.snapshot_id]),
                "reference_neighbors": [hit.name for hit in reference_hits],
                "sliced_neighbors": [hit.name for hit in sliced_hits],
            }
        )

    mean_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
    write_json(
        Path(args.out),
        {
            "passed": bool(overlaps) and mean_overlap >= args.min_mean_overlap,
            "k": args.k,
            "sample_size_requested": args.sample_size,
            "sample_size_evaluated": len(overlaps),
            "candidate_count_before_cross_bin_filter": len(all_candidates),
            "candidate_count_after_cross_bin_filter": len(candidates),
            "excluded_self_comparison_snapshot_ids": sorted(self_comparison_snapshots),
            "min_mean_overlap": args.min_mean_overlap,
            "mean_overlap": mean_overlap,
            "min_overlap": min(overlaps) if overlaps else 0.0,
            "encoder_map_snapshots": sorted(encoders_by_snapshot),
            "rows": rows,
        },
    )


def resolved_encoder_paths(mapping: dict[str, object]) -> dict[str, Path]:
    return {str(snapshot_id): Path(str(path)).resolve() for snapshot_id, path in mapping.items()}


def self_comparison_snapshot_ids(reference_encoder: str | Path, encoder_paths: dict[str, Path]) -> set[str]:
    reference_path = Path(reference_encoder).resolve()
    return {
        snapshot_id
        for snapshot_id, encoder_path in encoder_paths.items()
        if encoder_path == reference_path
    }


def stability_candidates(
    footprints: list[Footprint],
    by_snapshot: dict[str, Snapshot],
    declaration_names: set[str],
) -> list[Footprint]:
    return [
        footprint
        for footprint in footprints
        if footprint.declaration in declaration_names
        and footprint.snapshot_id in by_snapshot
        and bool(by_snapshot[footprint.snapshot_id].declarations)
    ]


if __name__ == "__main__":
    main()
