from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import read_jsonl, write_json, write_jsonl
from priorproof.corpus.pipeline import load_declarations
from priorproof.evaluation.reports import rater_pairs
from priorproof.cli.validate import score_from_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create blinded pairwise rater packet for proof-route nonstandardness.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--min-gap", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    declarations = {record.name: record for record in load_declarations(args.declarations)}
    scores = [score_from_json(row) for row in read_jsonl(args.scores)]
    pairs = rater_pairs(scores, k=args.n, min_gap=args.min_gap)
    blinded = []
    for pair in pairs:
        left = declarations.get(str(pair["left"]))
        right = declarations.get(str(pair["right"]))
        blinded.append(
            {
                "pair_id": pair["pair_id"],
                "left": {"name": left.name if left else pair["left"], "statement": left.statement if left else ""},
                "right": {"name": right.name if right else pair["right"], "statement": right.statement if right else ""},
                "prompt": "Which proof uses the less standard mathematical route to its result?",
            }
        )
    write_jsonl(out_dir / "pairs_blinded.jsonl", blinded)
    write_json(out_dir / "answer_key.json", pairs)


if __name__ == "__main__":
    main()
