from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from priorproof.data.io import read_json, read_jsonl, write_json, write_jsonl
from priorproof.evaluation.packets import require_complete_narratives


STRICTNESS_PROMPTS = {
    "concise": "Choose the proof that uses the less standard mathematical route. Reply with only left or right.",
    "strict": (
        "You are judging the mathematical route of the proof, not theorem importance, originality, beauty, "
        "or theorem difficulty. Use only the theorem statement, proof source, and proof narrative. "
        "Choose exactly one side. Reply with only left or right."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or prepare the naive LLM baseline on a rater packet.")
    parser.add_argument("--packet", required=True, help="study_packet.json from priorproof-study-packet.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--model", action="append", required=True, help="Model to evaluate. Repeat for both models.")
    parser.add_argument(
        "--strictness",
        action="append",
        choices=sorted(STRICTNESS_PROMPTS),
        default=[],
        help="Prompt strictness to evaluate. Defaults to concise and strict.",
    )
    parser.add_argument("--execute", action="store_true", help="Call the OpenAI API. Default writes request JSONL only.")
    parser.add_argument("--limit", type=int, help="Optional maximum number of pairs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    packet = read_json(args.packet)
    if not isinstance(packet, dict) or not isinstance(packet.get("pairs"), list):
        raise ValueError("--packet must contain an object with a `pairs` list")
    require_complete_narratives(packet, context="priorproof-llm-baseline")
    strictness_values = args.strictness or ["concise", "strict"]
    pairs = list(packet["pairs"])
    if args.limit is not None:
        pairs = pairs[: args.limit]
    out_dir = Path(args.out_dir)
    requests = [
        {
            "pair_id": pair["pair_id"],
            "model": model,
            "strictness": strictness,
            "prompt": build_prompt(pair, strictness),
        }
        for model in args.model
        for strictness in strictness_values
        for pair in pairs
    ]
    write_jsonl(out_dir / "requests.jsonl", requests)
    write_json(
        out_dir / "manifest.json",
        {
            "packet": args.packet,
            "pair_count": len(pairs),
            "models": args.model,
            "strictness": strictness_values,
            "request_count": len(requests),
            "executed": bool(args.execute),
            "responses": str(out_dir / "responses.jsonl") if args.execute else None,
        },
    )
    if not args.execute:
        return
    response_path = out_dir / "responses.jsonl"
    write_jsonl(response_path, run_openai_requests(requests, response_path=response_path))


def build_prompt(pair: dict[str, object], strictness: str) -> str:
    left = dict(pair["left"])
    right = dict(pair["right"])
    return "\n\n".join(
        [
            STRICTNESS_PROMPTS[strictness],
            f"Question: {pair['prompt']}",
            side_prompt("left", left),
            side_prompt("right", right),
            "Answer:",
        ]
    )


def side_prompt(label: str, side: dict[str, object]) -> str:
    return (
        f"{label.upper()}\n"
        f"Name: {side.get('name', '')}\n"
        f"Statement: {side.get('statement', '')}\n"
        f"Proof narrative: {side.get('human_argument', '')}\n"
        f"Proof source:\n{side.get('lean_source', '')}"
    )


def run_openai_requests(requests: list[dict[str, object]], *, response_path: Path) -> list[dict[str, object]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set when using --execute")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the optional `openai` package to use --execute") from exc
    client = OpenAI(api_key=api_key)
    rows = existing_responses(response_path)
    completed = {response_key(row) for row in rows}
    for request in requests:
        key = response_key(request)
        if key in completed:
            continue
        response = client.responses.create(
            model=str(request["model"]),
            input=str(request["prompt"]),
        )
        text = response.output_text.strip()
        rows.append(
            {
                "pair_id": request["pair_id"],
                "model": request["model"],
                "strictness": request["strictness"],
                "choice": normalize_choice(text),
                "raw_response": text,
            }
        )
        write_jsonl(response_path, rows)
        completed.add(key)
    return rows


def existing_responses(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows = []
    for row in read_jsonl(path):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def response_key(row: dict[str, object]) -> tuple[str, str, str]:
    return (str(row["pair_id"]), str(row["model"]), str(row["strictness"]))


def normalize_choice(text: str) -> str:
    lowered = text.strip().lower()
    if lowered.startswith("left"):
        return "left"
    if lowered.startswith("right"):
        return "right"
    return "invalid"


if __name__ == "__main__":
    main()
