from __future__ import annotations

import argparse

from priorproof.modeling.encoder import EncoderConfig, StatementEncoder
from priorproof.data.io import write_json
from priorproof.corpus.pipeline import load_declarations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the statement-only encoder on preselected declaration records.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dimensions", type=int, default=512)
    parser.add_argument("--namespace-weight", type=float, default=0.35)
    parser.add_argument("--module-weight", type=float, default=0.25)
    parser.add_argument("--shape-weight", type=float, default=0.4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_declarations(args.declarations)
    encoder = StatementEncoder(
        EncoderConfig(
            dimensions=args.dimensions,
            namespace_weight=args.namespace_weight,
            module_weight=args.module_weight,
            shape_weight=args.shape_weight,
        )
    ).fit(records)
    write_json(args.out, encoder.to_json())


if __name__ == "__main__":
    main()

