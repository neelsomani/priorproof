from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import read_json, read_jsonl, write_json
from priorproof.evaluation.llm_baseline import evaluate_llm_baseline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate LLM baseline responses against a study-packet answer key.")
    parser.add_argument("--responses", required=True, help="JSONL rows from priorproof-llm-baseline --execute.")
    parser.add_argument("--answer-key", required=True, help="answer_key.json from priorproof-study-packet.")
    parser.add_argument("--requests", help="Optional requests.jsonl to report missing responses.")
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    answer_key = read_json(args.answer_key)
    if not isinstance(answer_key, list):
        raise ValueError("--answer-key must contain a JSON list")
    requests = list(read_jsonl(args.requests)) if args.requests else None
    report = evaluate_llm_baseline(
        responses=read_jsonl(args.responses),
        answer_key=answer_key,
        requests=requests,
    )
    write_json(Path(args.out), report)


if __name__ == "__main__":
    main()
