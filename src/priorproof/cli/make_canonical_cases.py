from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.cli.validate import score_from_json
from priorproof.corpus.pipeline import load_declarations, load_footprints
from priorproof.data.io import read_json, read_jsonl, write_json
from priorproof.evaluation.packets import (
    extract_lean_source,
    footprint_lookup,
    metric_preference,
    packet_side,
    score_payload,
    score_lookup,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build hand-picked topology canonical cases with scores.")
    parser.add_argument("--case-spec", required=True, help="JSON case specification.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--footprints", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mathlib-repo", help="Optional mathlib checkout for Lean source snippets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = read_json(args.case_spec)
    if not isinstance(spec, dict) or not isinstance(spec.get("cases"), list):
        raise ValueError("--case-spec must contain an object with a `cases` list")
    declarations = {record.name: record for record in load_declarations(args.declarations)}
    scores = score_lookup(score_from_json(row) for row in read_jsonl(args.scores))
    footprints = footprint_lookup(load_footprints(args.footprints))
    cases = []
    for idx, item in enumerate(spec["cases"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"case {idx} must be an object")
        left_name = str(item["left"])
        right_name = str(item["right"])
        for name in (left_name, right_name):
            if name not in declarations:
                raise ValueError(f"case {idx} references missing declaration: {name}")
            if name not in scores:
                raise ValueError(f"case {idx} references unscored declaration: {name}")
        left_record = declarations[left_name]
        right_record = declarations[right_name]
        left_score = scores[left_name]
        right_score = scores[right_name]
        case_id = str(item.get("case_id") or f"canonical_{idx:03d}")
        left_side = packet_side(
            left_record,
            left_score,
            footprints.get(left_name),
            lean_source=extract_lean_source(left_record, args.mathlib_repo),
        )
        right_side = packet_side(
            right_record,
            right_score,
            footprints.get(right_name),
            lean_source=extract_lean_source(right_record, args.mathlib_repo),
        )
        if item.get("left_human_argument"):
            left_side["human_argument"] = str(item["left_human_argument"])
        if item.get("right_human_argument"):
            right_side["human_argument"] = str(item["right_human_argument"])
        left_side["score"] = score_payload(left_score)
        right_side["score"] = score_payload(right_score)
        cases.append(
            {
                "case_id": case_id,
                "title": str(item.get("title", case_id)),
                "theme": str(item.get("theme", "")),
                "interpretation": str(item.get("interpretation", "")),
                "expected_contrast": str(item.get("expected_contrast", "")),
                "metric_preference": metric_preference(left_score, right_score),
                "score_gap": abs(left_score.surprisal - right_score.surprisal),
                "left": left_side,
                "right": right_side,
            }
        )
    write_json(
        Path(args.out),
        {
            "name": str(spec.get("name", "canonical_cases")),
            "description": str(spec.get("description", "")),
            "case_count": len(cases),
            "cases": cases,
        },
    )


if __name__ == "__main__":
    main()
