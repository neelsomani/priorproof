from __future__ import annotations

import argparse
import random
from pathlib import Path

from priorproof.cli.validate import score_from_json
from priorproof.corpus.pipeline import load_declarations, load_footprints
from priorproof.data.io import read_json, read_jsonl, write_json, write_jsonl
from priorproof.evaluation.packets import (
    RATER_PROMPT,
    extract_lean_source,
    footprint_lookup,
    metric_preference,
    packet_side,
    public_side,
    score_payload,
    score_lookup,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the rater/LLM packet from canonical and stratified pairs.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--canonical-cases", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--mathlib-repo", help="Optional mathlib checkout for Lean source snippets.")
    parser.add_argument("--stratified-count", type=int, default=64)
    parser.add_argument("--canonical-repeats", type=int, default=3)
    parser.add_argument("--min-gap", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=41)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    out_dir = Path(args.out_dir)
    declarations = {record.name: record for record in load_declarations(args.declarations)}
    scores = score_lookup(score_from_json(row) for row in read_jsonl(args.scores))
    footprints = footprint_lookup(load_footprints(args.footprints))
    canonical_data = read_json(args.canonical_cases)
    if not isinstance(canonical_data, dict) or not isinstance(canonical_data.get("cases"), list):
        raise ValueError("--canonical-cases must contain a canonical case JSON object")
    canonical_cases = list(canonical_data["cases"])
    canonical_pairs = {
        frozenset((str(case["left"]["name"]), str(case["right"]["name"])))
        for case in canonical_cases
    }
    packet_rows = canonical_packet_rows(canonical_cases, args.canonical_repeats, rng)
    packet_rows.extend(
        stratified_packet_rows(
            declarations,
            scores,
            footprints,
            canonical_pairs,
            args.stratified_count,
            args.min_gap,
            args.mathlib_repo,
            rng,
        )
    )
    rng.shuffle(packet_rows)
    for idx, row in enumerate(packet_rows, start=1):
        row["pair_id"] = f"study_{idx:03d}"
    answer_key = [
        {
            "pair_id": row["pair_id"],
            "source": row["source"],
            "canonical_case_id": row.get("canonical_case_id"),
            "left": row["left"]["name"],
            "right": row["right"]["name"],
            "left_score": row["left"]["score"]["surprisal"],
            "right_score": row["right"]["score"]["surprisal"],
            "metric_preference": row["metric_preference"],
            "score_gap": row["score_gap"],
        }
        for row in packet_rows
    ]
    packet = {
        "name": "topology_rater_packet",
        "prompt": RATER_PROMPT,
        "pair_count": len(packet_rows),
        "canonical_pair_count": sum(1 for row in packet_rows if row["source"] == "canonical"),
        "stratified_pair_count": sum(1 for row in packet_rows if row["source"] == "stratified"),
        "pairs": blinded_rows(packet_rows),
    }
    write_json(out_dir / "study_packet.json", packet)
    write_jsonl(out_dir / "study_packet.jsonl", packet["pairs"])
    write_json(out_dir / "answer_key.json", answer_key)


def canonical_packet_rows(cases: list[object], repeats: int, rng: random.Random) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for repeat in range(repeats):
        for raw_case in cases:
            case = dict(raw_case)
            left = dict(case["left"])
            right = dict(case["right"])
            if rng.random() < 0.5:
                left, right = right, left
            rows.append(
                {
                    "source": "canonical",
                    "canonical_case_id": case["case_id"],
                    "canonical_title": case["title"],
                    "canonical_theme": case.get("theme", ""),
                    "canonical_interpretation": case.get("interpretation", ""),
                    "repeat": repeat + 1,
                    "prompt": RATER_PROMPT,
                    "left": left,
                    "right": right,
                    "metric_preference": metric_preference_from_sides(left, right),
                    "score_gap": abs(float(left["score"]["surprisal"]) - float(right["score"]["surprisal"])),
                }
            )
    return rows


def stratified_packet_rows(
    declarations: dict[str, object],
    scores: dict[str, object],
    footprints: dict[str, object],
    excluded_pairs: set[frozenset[str]],
    count: int,
    min_gap: float,
    mathlib_repo: str | None,
    rng: random.Random,
) -> list[dict[str, object]]:
    ordered = sorted(scores.values(), key=lambda score: score.surprisal)
    candidates: list[tuple[object, object, float]] = []
    for left_idx, low in enumerate(ordered):
        for high in ordered[left_idx + 1:]:
            gap = high.surprisal - low.surprisal
            if gap < min_gap:
                continue
            pair_key = frozenset((low.declaration, high.declaration))
            if pair_key in excluded_pairs:
                continue
            candidates.append((low, high, gap))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[2])
    buckets = [candidates[0::3], candidates[1::3], candidates[2::3]]
    for bucket in buckets:
        rng.shuffle(bucket)
    rows: list[dict[str, object]] = []
    seen: set[frozenset[str]] = set()
    bucket_idx = 0
    while len(rows) < count and any(buckets):
        bucket = buckets[bucket_idx % len(buckets)]
        bucket_idx += 1
        if not bucket:
            continue
        low, high, gap = bucket.pop()
        pair_key = frozenset((low.declaration, high.declaration))
        if pair_key in seen:
            continue
        seen.add(pair_key)
        left_score, right_score = (low, high)
        if rng.random() < 0.5:
            left_score, right_score = right_score, left_score
        left_record = declarations[left_score.declaration]
        right_record = declarations[right_score.declaration]
        left = packet_side(
            left_record,
            left_score,
            footprints.get(left_score.declaration),
            lean_source=extract_lean_source(left_record, mathlib_repo),
        )
        right = packet_side(
            right_record,
            right_score,
            footprints.get(right_score.declaration),
            lean_source=extract_lean_source(right_record, mathlib_repo),
        )
        left["score"] = score_payload(left_score)
        right["score"] = score_payload(right_score)
        rows.append(
            {
                "source": "stratified",
                "prompt": RATER_PROMPT,
                "left": left,
                "right": right,
                "metric_preference": metric_preference(left_score, right_score),
                "score_gap": gap,
            }
        )
    return rows


def metric_preference_from_sides(left: dict[str, object], right: dict[str, object]) -> str:
    left_score = float(left["score"]["surprisal"])
    right_score = float(right["score"]["surprisal"])
    if left_score > right_score:
        return "left"
    if right_score > left_score:
        return "right"
    return "tie"


def blinded_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    result = []
    for row in rows:
        result.append(
            {
                "pair_id": row["pair_id"],
                "source": row["source"],
                "canonical_case_id": row.get("canonical_case_id"),
                "prompt": row["prompt"],
                "left": public_side(dict(row["left"])),
                "right": public_side(dict(row["right"])),
            }
        )
    return result


if __name__ == "__main__":
    main()
