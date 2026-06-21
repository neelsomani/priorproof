from __future__ import annotations

import argparse

from priorproof.data.io import read_json
from priorproof.data.models import Footprint
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


def load_encoder_selection(args: argparse.Namespace, footprints: list[Footprint]):
    snapshot_ids = sorted({footprint.snapshot_id for footprint in footprints})
    if args.encoder_map:
        mapping = read_json(args.encoder_map)
        if not isinstance(mapping, dict):
            raise ValueError("--encoder-map must contain a JSON object")
        encoders_by_snapshot = load_encoder_map(mapping)
        missing = sorted(set(snapshot_ids) - set(encoders_by_snapshot))
        if missing:
            raise ValueError(f"--encoder-map is missing snapshots: {missing}")
        return None, encoders_by_snapshot

    if len(snapshot_ids) > 1 and not args.allow_shared_encoder:
        raise ValueError(
            "Refusing to use one encoder across multiple snapshots. "
            "Pass --encoder-map, or pass --allow-shared-encoder only after the neighbor-stability check passes."
        )
    return load_neural_statement_encoder(args.encoder), None

