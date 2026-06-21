from __future__ import annotations

import argparse

from priorproof.data.io import read_json
from priorproof.data.models import Footprint, Snapshot
from priorproof.modeling.neural_encoder import load_encoder_map, load_neural_statement_encoder


def add_encoder_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--encoder", help="Single trained neural encoder directory.")
    group.add_argument("--encoder-map", help="JSON mapping snapshot_id to trained neural encoder directory.")
    parser.add_argument(
        "--allow-shared-encoder",
        action="store_true",
        help="Allow one encoder across multiple snapshots. Use only for frozen-early runs after stability validation.",
    )


def load_encoder_selection(
    args: argparse.Namespace,
    footprints: list[Footprint],
    snapshots: list[Snapshot] | None = None,
):
    snapshot_ids = required_encoder_snapshot_ids(footprints, snapshots)
    if args.encoder_map:
        mapping = read_json(args.encoder_map)
        validate_encoder_map(mapping, snapshot_ids)
        encoders_by_snapshot = load_encoder_map(mapping)
        return None, encoders_by_snapshot

    validate_shared_encoder_allowed(snapshot_ids, args.allow_shared_encoder)
    return load_neural_statement_encoder(args.encoder), None


def validate_encoder_selection(
    args: argparse.Namespace,
    footprints: list[Footprint],
    snapshots: list[Snapshot] | None = None,
) -> None:
    snapshot_ids = required_encoder_snapshot_ids(footprints, snapshots)
    if args.encoder_map:
        validate_encoder_map(read_json(args.encoder_map), snapshot_ids)
        return
    validate_shared_encoder_allowed(snapshot_ids, args.allow_shared_encoder)


def validate_encoder_map(mapping: object, snapshot_ids: list[str]) -> None:
    if not isinstance(mapping, dict):
        raise ValueError("--encoder-map must contain a JSON object")
    missing = sorted(set(snapshot_ids) - {str(snapshot_id) for snapshot_id in mapping})
    if missing:
        raise ValueError(f"--encoder-map is missing snapshots: {missing}")


def validate_shared_encoder_allowed(snapshot_ids: list[str], allow_shared_encoder: bool) -> None:
    if len(snapshot_ids) > 1 and not allow_shared_encoder:
        raise ValueError(
            "Refusing to use one encoder across multiple snapshots. "
            "Pass --encoder-map, or pass --allow-shared-encoder only after the neighbor-stability check passes."
        )


def required_encoder_snapshot_ids(
    footprints: list[Footprint],
    snapshots: list[Snapshot] | None = None,
) -> list[str]:
    snapshot_ids = {footprint.snapshot_id for footprint in footprints}
    if snapshots is None:
        return sorted(snapshot_ids)
    scoreable = {
        snapshot.snapshot_id
        for snapshot in snapshots
        if snapshot.snapshot_id in snapshot_ids and snapshot.declarations
    }
    return sorted(scoreable)
