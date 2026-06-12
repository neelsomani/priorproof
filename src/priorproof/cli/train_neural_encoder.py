from __future__ import annotations

import argparse

from priorproof.corpus.pipeline import load_declarations
from priorproof.data.io import read_jsonl
from priorproof.modeling.contrastive import ContrastiveExample
from priorproof.modeling.neural_encoder import NeuralEncoderConfig, train_neural_encoder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune a transformer statement encoder on proof-derived contrastive examples.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--examples", required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--max-seq-length", type=int, default=256)
    parser.add_argument("--no-hard-negatives", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_declarations(args.declarations)
    examples = [ContrastiveExample.from_json(row) for row in read_jsonl(args.examples)]
    config = NeuralEncoderConfig(
        base_model=args.base_model,
        output_dir=args.out_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        max_seq_length=args.max_seq_length,
        use_hard_negatives=not args.no_hard_negatives,
    )
    train_neural_encoder(records, examples, config)


if __name__ == "__main__":
    main()

