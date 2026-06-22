from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from priorproof.data.io import read_json, read_jsonl, write_json, write_jsonl
from priorproof.evaluation.packets import require_complete_narratives


FORBIDDEN_NARRATIVE_TERMS = (
    "surprisal",
    "prior",
    "probability",
    "score",
    "footprint",
    "dependency",
    "lean",
    "mathlib",
    "namespace:",
    "module:",
)

FORBIDDEN_NARRATIVE_PATTERNS = (
    (re.compile(r"\b[A-Z][A-Za-z0-9_']*\.[A-Za-z0-9_'.]*\b"), "source identifier"),
    (re.compile(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z0-9_']*\b"), "camelCase source identifier"),
    (re.compile(r"\b(?:coLindel\w*|nhds\w*|neBot\w*|mapClusterPt\w*)\b"), "source abbreviation"),
    (re.compile(r"''"), "source image notation"),
    (re.compile(r"[↔↑𝓝⤳∀∃]"), "formal proof symbol"),
)

SYSTEM_PROMPT = (
    "You translate formal proof source into ordinary mathematical exposition for mathematicians. "
    "Explain the proof route in standard mathematical language. Do not mention formal-system "
    "metadata, software-specific names, source identifiers, evaluation machinery, numerical ratings, "
    "or whether the proof is standard or surprising. Translate formal identifiers into ordinary "
    "phrases such as compact, Lindelof, neighborhood, closure, filter, or projection; do not copy "
    "raw source names, camelCase identifiers, dot-qualified names, or proof-code symbols. For "
    "example, write 'the set is compact' instead of `IsCompact`, 'the neighborhoods of x' instead "
    "of `𝓝 x`, 'if and only if' instead of `↔`, and 'eventually for large radii' instead of "
    "`atTop`. Write 'the co-Lindelof filter' with a hyphen, not a source identifier like "
    "`coLindelof`, and write 'the image of a set under f' instead of source image notation. If "
    "the source is too terse to reconstruct every step, explain only what follows from the "
    "statement and proof source without inventing details."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate blinded mathematical proof narratives for a study packet.")
    parser.add_argument("--packet", required=True, help="Blinded study_packet.json.")
    parser.add_argument("--out-packet", required=True, help="Study packet with generated proof narratives.")
    parser.add_argument("--out-dir", required=True, help="Directory for request/response/manifest artifacts.")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--execute", action="store_true", help="Call the OpenAI API. Default writes request JSONL only.")
    parser.add_argument("--responses", help="Existing narrative response JSONL to validate and merge.")
    parser.add_argument("--limit", type=int, help="Optional maximum number of unique sides to generate.")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries per narrative when validation fails.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    packet = read_json(args.packet)
    if not isinstance(packet, dict) or not isinstance(packet.get("pairs"), list):
        raise ValueError("--packet must contain an object with a `pairs` list")
    out_dir = Path(args.out_dir)
    apply_narratives(packet, packet_narratives(packet))
    if args.responses:
        apply_narratives(packet, list(existing_responses(Path(args.responses)).values()))
    requests = narrative_requests(packet, model=args.model, limit=args.limit)
    write_jsonl(out_dir / "narrative_requests.jsonl", requests)
    write_json(
        out_dir / "narrative_manifest.json",
        {
            "packet": args.packet,
            "out_packet": args.out_packet,
            "model": args.model,
            "request_count": len(requests),
            "executed": bool(args.execute),
            "responses": str(out_dir / "narrative_responses.jsonl") if args.execute else None,
        },
    )
    if not args.execute:
        if requests:
            return
        require_complete_narratives(packet, context="proof narrative packet export")
        write_json(args.out_packet, packet)
        return
    response_path = out_dir / "narrative_responses.jsonl"
    existing = existing_responses(response_path)
    pending = [request for request in requests if str(request["name"]) not in existing]
    responses = run_openai_requests(
        pending,
        response_path=response_path,
        existing=list(existing.values()),
        max_retries=args.max_retries,
    )
    apply_narratives(packet, responses)
    require_complete_narratives(packet, context="proof narrative packet export")
    write_json(args.out_packet, packet)


def narrative_requests(packet: dict[str, object], model: str, limit: int | None = None) -> list[dict[str, object]]:
    seen: set[str] = set()
    requests: list[dict[str, object]] = []
    for pair in packet["pairs"]:
        for side_label in ("left", "right"):
            side = dict(pair[side_label])
            name = str(side.get("name", ""))
            if not name or name in seen:
                continue
            seen.add(name)
            current = str(side.get("human_argument", ""))
            if current.strip():
                continue
            requests.append(
                {
                    "name": name,
                    "model": model,
                    "prompt": build_prompt(side),
                }
            )
            if limit is not None and len(requests) >= limit:
                return requests
    return requests


def build_prompt(side: dict[str, object]) -> str:
    return "\n\n".join(
        [
            SYSTEM_PROMPT,
            "Write a concise proof narrative of 3-6 sentences. Use ordinary mathematical terminology.",
            f"Theorem statement:\n{side.get('statement', '')}",
            f"Proof source:\n{side.get('lean_source', '')}",
            "Proof narrative:",
        ]
    )


def run_openai_requests(
    requests: list[dict[str, object]],
    *,
    response_path: Path,
    existing: list[dict[str, object]] | None = None,
    max_retries: int = 2,
) -> list[dict[str, object]]:
    load_env_file(Path(".env"))
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set when using --execute")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the optional `openai` package to use --execute") from exc
    client = OpenAI(api_key=api_key)
    rows = list(existing or [])
    for request in requests:
        narrative = generate_valid_narrative(client, request, max_retries=max_retries)
        rows.append({"name": request["name"], "model": request["model"], "human_argument": narrative})
        write_jsonl(response_path, rows)
    return rows


def generate_valid_narrative(client: object, request: dict[str, object], *, max_retries: int) -> str:
    prompt = str(request["prompt"])
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.responses.create(
                model=str(request["model"]),
                input=prompt,
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI request failed while generating {request['name']}: {exc}") from exc
        narrative = response.output_text.strip()
        try:
            validate_narrative(narrative)
            if not narrative:
                raise RuntimeError("Generated narrative was empty")
            return narrative
        except RuntimeError as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            prompt = "\n\n".join(
                [
                    str(request["prompt"]),
                    f"The previous answer was rejected: {exc}. Rewrite it as ordinary mathematical prose only. "
                    "Do not use raw theorem names, camelCase identifiers, dot-qualified identifiers, symbols "
                    "such as ↔, 𝓝, ↑, ∀, or ∃, or any commentary about the task.",
                    "Proof narrative:",
                ]
            )
    raise RuntimeError(f"Could not generate a valid narrative for {request['name']}: {last_error}")


def existing_responses(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, object]] = {}
    for row in read_jsonl(path):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", ""))
        narrative = str(row.get("human_argument", ""))
        if name and narrative:
            validate_narrative(narrative)
            rows[name] = row
    return rows


def apply_narratives(packet: dict[str, object], responses: list[dict[str, object]]) -> None:
    by_name = {str(row["name"]): str(row["human_argument"]) for row in responses}
    for pair in packet["pairs"]:
        for side_label in ("left", "right"):
            side = pair[side_label]
            name = str(side.get("name", ""))
            if name in by_name:
                side["human_argument"] = by_name[name]


def packet_narratives(packet: dict[str, object]) -> list[dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for pair in packet.get("pairs", []):
        if not isinstance(pair, dict):
            continue
        for side_label in ("left", "right"):
            side = pair.get(side_label)
            if not isinstance(side, dict):
                continue
            name = str(side.get("name", ""))
            narrative = str(side.get("human_argument", "")).strip()
            if not name or not narrative:
                continue
            validate_narrative(narrative)
            rows[name] = {"name": name, "human_argument": narrative}
    return list(rows.values())


def validate_narrative(narrative: str) -> None:
    lowered = narrative.lower()
    hits = [
        term
        for term in FORBIDDEN_NARRATIVE_TERMS
        if re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", lowered)
    ]
    hits.extend(label for pattern, label in FORBIDDEN_NARRATIVE_PATTERNS if pattern.search(narrative))
    if hits:
        raise RuntimeError(f"Generated narrative contains forbidden terms: {', '.join(hits)}")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
