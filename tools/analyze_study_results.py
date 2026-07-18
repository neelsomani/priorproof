#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ANSWER_KEY = Path("PriorProof Answer Key/study_packet/answer_key.json")
DEFAULT_STUDY_PACKET = Path("PriorProof Answer Key/study_packet/study_packet.json")
DEFAULT_LLM_REPORT = Path("PriorProof Answer Key/llm_baseline/report.json")
SUBSETS = ("overall", "canonical", "stratified")
QUARTILE_NAMES = ("smallest", "second", "third", "largest")


@dataclass(frozen=True)
class Presentation:
    pair_id: str
    left: str
    right: str
    source: str
    metric_preference: str
    score_gap: float
    order_index: int

    @property
    def group_key(self) -> tuple[str, str]:
        return tuple(sorted((self.left, self.right)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze retained rater responses against PriorProof and LLM choices. "
            "By default, duplicate underlying proof-pairs in the answer key fail closed. "
            "Use --allow-repeats-with-collapse to normalize left/right choices to proof identities "
            "and report distinct-pair analyses."
        )
    )
    parser.add_argument("--answer-key", type=Path, default=DEFAULT_ANSWER_KEY)
    parser.add_argument("--study-packet", type=Path, default=DEFAULT_STUDY_PACKET)
    parser.add_argument("--llm-report", type=Path, default=DEFAULT_LLM_REPORT)
    parser.add_argument(
        "--rater-response",
        action="append",
        default=[],
        metavar="PATH",
        help="Retained rater response JSONL. Repeat once per rater. NAME=PATH is optional but anonymized by default.",
    )
    parser.add_argument(
        "--screening-response",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Additional rater response JSONL used only for repeat-consistency screening. "
            "These responses do not enter the retained-rater majority or outcome statistics. "
            "NAME=PATH is optional but anonymized by default."
        ),
    )
    parser.add_argument(
        "--preserve-rater-labels",
        action="store_true",
        help="Use labels supplied as NAME=PATH in the output. Off by default to avoid leaking rater names.",
    )
    parser.add_argument(
        "--allow-repeats-with-collapse",
        action="store_true",
        help="Permit repeated underlying proof-pairs and run both distinct-pair collapse analyses.",
    )
    parser.add_argument("--json-out", type=Path, help="Optional path for the full computed report.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.rater_response:
        raise SystemExit("At least one --rater-response path is required.")

    packet_lookup = read_packet_lookup(args.study_packet)
    presentations = read_presentations(args.answer_key, packet_lookup)
    raters_raw = read_raters(
        args.rater_response,
        anonymized_prefix="Retained rater",
        preserve_labels=args.preserve_rater_labels,
    )
    screening_raw = (
        read_raters(
            args.screening_response,
            anonymized_prefix="Screening rater",
            preserve_labels=args.preserve_rater_labels,
        )
        if args.screening_response
        else {}
    )
    duplicate_screening_names = set(raters_raw) & set(screening_raw)
    if duplicate_screening_names:
        raise SystemExit(f"Rater names cannot appear in both retained and screening-only inputs: {sorted(duplicate_screening_names)}")
    llm_raw = read_llm_conditions(args.llm_report)
    inventory = repeat_inventory(presentations)

    if inventory["duplicate_underlying_pair_count"] and not args.allow_repeats_with_collapse:
        raise SystemExit(format_duplicate_error(inventory))

    pair_ids = [presentation.pair_id for presentation in presentations]
    check_coverage("answer_key", pair_ids, {presentation.pair_id: presentation for presentation in presentations})
    for name, labels in raters_raw.items():
        check_coverage(name, pair_ids, labels)
    for name, labels in screening_raw.items():
        check_coverage(name, pair_ids, labels)
    for name, labels in llm_raw.items():
        check_coverage(name, pair_ids, labels)

    report: dict[str, Any] = {
        "repeat_inventory": inventory,
        "presentation_level_old": presentation_level_report(presentations, raters_raw, llm_raw),
    }
    if inventory["duplicate_underlying_pair_count"]:
        report["collapsed_majority_across_presentations"] = collapsed_report(
            presentations, raters_raw, llm_raw, screening_raw, mode="majority_across_presentations"
        )
        report["collapsed_first_presentation"] = collapsed_report(
            presentations, raters_raw, llm_raw, screening_raw, mode="first_presentation"
        )

    print_full_report(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_packet_lookup(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    pairs = payload.get("pairs") if isinstance(payload, dict) else payload
    if not isinstance(pairs, list):
        raise SystemExit(f"Study packet must be a list or an object with a pairs list: {path}")
    lookup = {}
    for row in pairs:
        if not isinstance(row, dict):
            raise SystemExit(f"Study-packet rows must be JSON objects: {path}")
        pair_id = require_str(row, "pair_id", path)
        if pair_id in lookup:
            raise SystemExit(f"Duplicate pair_id in study packet: {pair_id}")
        lookup[pair_id] = row
    return lookup


def read_presentations(path: Path, packet_lookup: dict[str, dict[str, Any]]) -> list[Presentation]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"Answer key must be a JSON list: {path}")

    seen_pair_ids: set[str] = set()
    presentations = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SystemExit(f"Answer-key rows must be JSON objects: {path}")
        pair_id = require_str(row, "pair_id", path)
        if pair_id in seen_pair_ids:
            raise SystemExit(f"Duplicate pair_id in answer key: {pair_id}")
        seen_pair_ids.add(pair_id)

        packet_row = packet_lookup.get(pair_id, {})
        left = proof_side_id(row, packet_row, "left", path, pair_id)
        right = proof_side_id(row, packet_row, "right", path, pair_id)
        if left == right:
            raise SystemExit(f"Answer-key pair {pair_id} compares a proof with itself: {left}")
        metric_preference = require_str(row, "metric_preference", path)
        if metric_preference not in {"left", "right"}:
            raise SystemExit(f"Invalid metric_preference for {pair_id}: {metric_preference!r}")
        source = str(row.get("source") or packet_row.get("source") or "unknown")
        if source not in {"canonical", "stratified"}:
            raise SystemExit(f"Invalid source for {pair_id}: {source!r}")
        score_gap = score_gap_for_row(row, pair_id, path)
        presentations.append(
            Presentation(
                pair_id=pair_id,
                left=left,
                right=right,
                source=source,
                metric_preference=metric_preference,
                score_gap=score_gap,
                order_index=index,
            )
        )
    return presentations


def score_gap_for_row(row: dict[str, Any], pair_id: str, path: Path) -> float:
    if isinstance(row.get("score_gap"), (int, float)):
        return float(row["score_gap"])
    if isinstance(row.get("left_score"), (int, float)) and isinstance(row.get("right_score"), (int, float)):
        return abs(float(row["left_score"]) - float(row["right_score"]))
    raise SystemExit(f"Missing score_gap or left_score/right_score for {pair_id} in {path}")


def read_raters(specs: list[str], anonymized_prefix: str, preserve_labels: bool = False) -> dict[str, dict[str, str]]:
    raters: dict[str, dict[str, str]] = {}
    for index, spec in enumerate(specs, start=1):
        supplied_name, path = parse_named_path(spec)
        name = supplied_name if preserve_labels else f"{anonymized_prefix} {index}"
        rows = read_jsonl(path)
        labels: dict[str, str] = {}
        for row in rows:
            pair_id = require_str(row, "pair_id", path)
            if pair_id in labels:
                raise SystemExit(f"Duplicate pair_id in rater response {name}: {pair_id}")
            choice = require_str(row, "choice", path)
            if choice not in {"left", "right"}:
                raise SystemExit(f"Invalid rater choice for {name}/{pair_id}: {choice!r}")
            labels[pair_id] = choice
        if name in raters:
            raise SystemExit(f"Duplicate rater name: {name}")
        raters[name] = labels
    return raters


def read_llm_conditions(path: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise SystemExit(f"LLM report must be a list or an object with a rows list: {path}")

    conditions: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        pair_id = require_str(row, "pair_id", path)
        model = require_str(row, "model", path)
        strictness = require_str(row, "strictness", path)
        choice = require_str(row, "choice", path)
        if choice not in {"left", "right"}:
            continue
        condition = f"LLM {model}/{strictness}"
        if pair_id in conditions[condition]:
            raise SystemExit(f"Duplicate pair_id in LLM condition {condition}: {pair_id}")
        conditions[condition][pair_id] = choice
    return dict(sorted(conditions.items()))


def repeat_inventory(presentations: list[Presentation]) -> dict[str, Any]:
    groups = grouped_presentations(presentations)
    duplicate_groups = {key: rows for key, rows in groups.items() if len(rows) > 1}
    distinct_by_subset = {}
    presentation_by_subset = Counter(presentation.source for presentation in presentations)
    mixed_source_groups = []
    for subset in ("canonical", "stratified"):
        distinct_by_subset[subset] = sum(1 for rows in groups.values() if {row.source for row in rows} == {subset})
    for key, rows in groups.items():
        sources = sorted({row.source for row in rows})
        if len(sources) > 1:
            mixed_source_groups.append({"proof_pair": list(key), "sources": sources, "pair_ids": [row.pair_id for row in rows]})

    twin_sets = []
    for key, rows in sorted(duplicate_groups.items(), key=lambda item: item[1][0].order_index):
        orders = [(row.left, row.right) for row in rows]
        twin_sets.append(
            {
                "proof_pair": list(key),
                "source": sorted({row.source for row in rows}),
                "pair_ids": [row.pair_id for row in rows],
                "presentation_orders": [
                    {"pair_id": row.pair_id, "left": row.left, "right": row.right} for row in rows
                ],
                "has_swapped_order": len(set(orders)) > 1,
            }
        )

    canonical_group_sizes = [
        len(rows) for rows in groups.values() if {row.source for row in rows} == {"canonical"}
    ]
    stratified_duplicate_sets = [
        twin_set for twin_set in twin_sets if twin_set["source"] == ["stratified"]
    ]
    return {
        "presentation_count": len(presentations),
        "presentation_counts_by_subset": dict(presentation_by_subset),
        "distinct_underlying_pair_count": len(groups),
        "distinct_underlying_pair_counts_by_subset": distinct_by_subset,
        "mixed_source_groups": mixed_source_groups,
        "duplicate_underlying_pair_count": sum(len(rows) - 1 for rows in duplicate_groups.values()),
        "duplicate_underlying_pair_group_count": len(duplicate_groups),
        "twin_sets": twin_sets,
        "canonical_repeats_check": {
            "passed": distinct_by_subset["canonical"] == 12
            and presentation_by_subset["canonical"] == 36
            and canonical_group_sizes
            and all(size == 3 for size in canonical_group_sizes),
            "distinct_canonical_pairs": distinct_by_subset["canonical"],
            "canonical_presentations": presentation_by_subset["canonical"],
            "canonical_group_sizes": sorted(canonical_group_sizes),
        },
        "stratified_duplicate_check": {
            "passed": len(stratified_duplicate_sets) == 0,
            "distinct_stratified_pairs": distinct_by_subset["stratified"],
            "stratified_presentations": presentation_by_subset["stratified"],
            "duplicate_sets": stratified_duplicate_sets,
        },
    }


def presentation_level_report(
    presentations: list[Presentation],
    raters_raw: dict[str, dict[str, str]],
    llm_raw: dict[str, dict[str, str]],
) -> dict[str, Any]:
    pair_ids = [presentation.pair_id for presentation in presentations]
    presentation_by_id = {presentation.pair_id: presentation for presentation in presentations}
    subsets = {
        "overall": pair_ids,
        "canonical": [pair_id for pair_id in pair_ids if presentation_by_id[pair_id].source == "canonical"],
        "stratified": [pair_id for pair_id in pair_ids if presentation_by_id[pair_id].source == "stratified"],
    }
    score_gaps = {presentation.pair_id: presentation.score_gap for presentation in presentations}
    systems = {
        "PriorProof": {presentation.pair_id: presentation.metric_preference for presentation in presentations},
        **llm_raw,
    }
    systems["LLM majority (ties excluded)"] = condition_majority(pair_ids, llm_raw)
    return analyze_units(pair_ids, subsets, score_gaps, raters_raw, systems)


def collapsed_report(
    presentations: list[Presentation],
    raters_raw: dict[str, dict[str, str]],
    llm_raw: dict[str, dict[str, str]],
    screening_raw: dict[str, dict[str, str]],
    mode: str,
) -> dict[str, Any]:
    groups = grouped_presentations(presentations)
    group_ids = [group_id(key) for key in groups]
    orientations = canonical_orientations(groups)
    source_by_group = {}
    score_gaps = {}
    priorproof: dict[str, str] = {}
    sanity = {
        "priorproof_deterministic": True,
        "priorproof_inconsistent_groups": [],
        "score_gap_inconsistent_groups": [],
    }

    for key, rows in groups.items():
        gid = group_id(key)
        sources = {row.source for row in rows}
        if len(sources) != 1:
            raise SystemExit(f"Underlying pair has mixed sources: {key}: {sources}")
        source_by_group[gid] = next(iter(sources))

        metric_votes = [choice_to_proof(row, row.metric_preference) for row in rows]
        if len(set(metric_votes)) != 1:
            sanity["priorproof_deterministic"] = False
            sanity["priorproof_inconsistent_groups"].append({"group": list(key), "votes": metric_votes})
        priorproof[gid] = proof_to_binary_label(metric_votes[0], orientations[key])

        gaps = [row.score_gap for row in rows]
        if max(gaps) - min(gaps) > 1e-9:
            sanity["score_gap_inconsistent_groups"].append({"group": list(key), "score_gaps": gaps})
        score_gaps[gid] = gaps[0]

    if not sanity["priorproof_deterministic"]:
        raise SystemExit(f"PriorProof is not deterministic across repeated presentations: {sanity}")

    subsets = {
        "overall": group_ids,
        "canonical": [gid for gid in group_ids if source_by_group[gid] == "canonical"],
        "stratified": [gid for gid in group_ids if source_by_group[gid] == "stratified"],
    }
    raters = collapse_entity_labels(groups, raters_raw, mode, orientations)
    llm_conditions = collapse_entity_labels(groups, llm_raw, mode, orientations)
    systems = {"PriorProof": priorproof, **llm_conditions}
    systems["LLM majority (ties excluded)"] = condition_majority(group_ids, llm_conditions)
    presentation_ids = [presentation.pair_id for presentation in presentations]
    raw_systems = {
        "PriorProof": {presentation.pair_id: presentation.metric_preference for presentation in presentations},
        **llm_raw,
        "LLM majority (ties excluded)": condition_majority(presentation_ids, llm_raw),
    }
    report = analyze_units(group_ids, subsets, score_gaps, raters, systems)
    report["collapse_mode"] = mode
    report["sanity_checks"] = sanity
    report["binary_orientation_check"] = binary_orientation_check(group_ids, raters, systems)
    report["dropped_votes_by_entity"] = dropped_vote_report(groups, raters_raw | llm_raw, mode)
    report["repeat_consistency"] = repeat_consistency(
        groups,
        {"PriorProof": raw_systems["PriorProof"], **raters_raw, **screening_raw, **raw_systems},
    )
    report["repeat_consistency_baseline"] = repeat_consistency_baseline(groups)
    return report


def analyze_units(
    unit_ids: list[str],
    subsets: dict[str, list[str]],
    score_gaps: dict[str, float],
    raters: dict[str, dict[str, str]],
    systems: dict[str, dict[str, str]],
) -> dict[str, Any]:
    majority, no_majority = majority_labels(unit_ids, raters)
    return {
        "unit_count": len(unit_ids),
        "subset_counts": {subset: len(ids) for subset, ids in subsets.items()},
        "human_majority": {
            "n": len(majority),
            "label_counts": dict(Counter(majority.values())),
            "unanimous_count": unanimous_count(unit_ids, raters),
            "no_majority_units": no_majority,
        },
        "inter_rater_agreement": inter_rater_report(raters, subsets),
        "accuracy_vs_majority": accuracy_report(systems, majority, subsets),
        "calibration_quartiles": calibration_report(score_gaps, systems["PriorProof"], majority, subsets["overall"]),
        "mcnemar_priorproof_vs_llm": mcnemar_report(systems, majority, subsets),
        "rater_agreement_with_systems": rater_system_report(unit_ids, raters, systems),
        "llm_majority_ties_excluded": sorted(set(unit_ids) - set(systems["LLM majority (ties excluded)"])),
    }


def collapse_entity_labels(
    groups: dict[tuple[str, str], list[Presentation]],
    raw_entities: dict[str, dict[str, str]],
    mode: str,
    orientations: dict[tuple[str, str], tuple[str, str]],
) -> dict[str, dict[str, str]]:
    collapsed: dict[str, dict[str, str]] = {}
    for entity, raw_labels in raw_entities.items():
        collapsed[entity] = {}
        for key, rows in groups.items():
            gid = group_id(key)
            if mode == "first_presentation":
                first = rows[0]
                if first.pair_id in raw_labels:
                    proof = choice_to_proof(first, raw_labels[first.pair_id])
                    collapsed[entity][gid] = proof_to_binary_label(proof, orientations[key])
            elif mode == "majority_across_presentations":
                votes = [
                    proof_to_binary_label(choice_to_proof(row, raw_labels[row.pair_id]), orientations[key])
                    for row in rows
                    if row.pair_id in raw_labels
                ]
                winner = strict_majority(votes)
                if winner is not None:
                    collapsed[entity][gid] = winner
            else:
                raise SystemExit(f"Unknown collapse mode: {mode}")
    return collapsed


def dropped_vote_report(
    groups: dict[tuple[str, str], list[Presentation]],
    raw_entities: dict[str, dict[str, str]],
    mode: str,
) -> dict[str, list[str]]:
    if mode != "majority_across_presentations":
        return {entity: [] for entity in raw_entities}
    dropped: dict[str, list[str]] = {}
    for entity, raw_labels in raw_entities.items():
        dropped[entity] = []
        for key, rows in groups.items():
            votes = [
                choice_to_proof(row, raw_labels[row.pair_id])
                for row in rows
                if row.pair_id in raw_labels
            ]
            if votes and strict_majority(votes) is None:
                dropped[entity].append(group_id(key))
    return dropped


def repeat_consistency(
    groups: dict[tuple[str, str], list[Presentation]],
    raw_entities: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    repeated_groups = {key: rows for key, rows in groups.items() if len(rows) > 1}
    report = {}
    for entity, raw_labels in raw_entities.items():
        consistent_votes = 0
        total_votes = 0
        fully_consistent_groups = 0
        observed_groups = 0
        missing_presentations = []
        inconsistent_groups = []
        for key, rows in repeated_groups.items():
            votes = [
                choice_to_proof(row, raw_labels[row.pair_id])
                for row in rows
                if row.pair_id in raw_labels
            ]
            missing = [row.pair_id for row in rows if row.pair_id not in raw_labels]
            if missing:
                missing_presentations.extend(missing)
            if not votes:
                continue
            observed_groups += 1
            counts = Counter(votes)
            consistent_votes += max(counts.values())
            total_votes += len(votes)
            if len(counts) == 1 and len(votes) == len(rows):
                fully_consistent_groups += 1
            elif len(counts) > 1:
                inconsistent_groups.append({"group": list(key), "votes": dict(counts)})
        report[entity] = {
            "consistent_votes": consistent_votes,
            "total_repeat_presentations": total_votes,
            "fully_consistent_groups": fully_consistent_groups,
            "observed_repeat_groups": observed_groups,
            "total_repeat_groups": len(repeated_groups),
            "missing_presentations": missing_presentations,
            "inconsistent_group_count": len(inconsistent_groups),
            "inconsistent_groups": inconsistent_groups,
        }
    return report


def repeat_consistency_baseline(groups: dict[tuple[str, str], list[Presentation]]) -> dict[str, Any]:
    repeated_groups = [rows for rows in groups.values() if len(rows) > 1]
    total_presentations = sum(len(rows) for rows in repeated_groups)
    vote_floor = sum(math.ceil(len(rows) / 2) for rows in repeated_groups)
    expected_votes = sum(expected_binary_majority_match_count(len(rows)) for rows in repeated_groups)
    expected_full_groups = sum(2 / (2 ** len(rows)) for rows in repeated_groups)
    return {
        "repeat_group_count": len(repeated_groups),
        "total_repeat_presentations": total_presentations,
        "majority_match_vote_floor": vote_floor,
        "majority_match_vote_chance_expectation": expected_votes,
        "fully_consistent_group_chance_expectation": expected_full_groups,
    }


def expected_binary_majority_match_count(n_presentations: int) -> float:
    return sum(
        max(k, n_presentations - k) * math.comb(n_presentations, k) / (2 ** n_presentations)
        for k in range(n_presentations + 1)
    )


def binary_orientation_check(
    unit_ids: list[str],
    raters: dict[str, dict[str, str]],
    systems: dict[str, dict[str, str]],
) -> dict[str, Any]:
    allowed = {"first", "second"}
    offenders = {}
    for collection_name, collection in {"raters": raters, "systems": systems}.items():
        for name, labels in collection.items():
            observed = {labels[unit_id] for unit_id in unit_ids if unit_id in labels}
            unexpected = sorted(observed - allowed)
            if unexpected:
                offenders[f"{collection_name}:{name}"] = unexpected
    if offenders:
        raise SystemExit(f"Collapsed labels must be binary first/second, found {offenders}")
    return {"allowed_labels": sorted(allowed), "passed": True}


def canonical_orientations(
    groups: dict[tuple[str, str], list[Presentation]],
) -> dict[tuple[str, str], tuple[str, str]]:
    return {key: (rows[0].left, rows[0].right) for key, rows in groups.items()}


def proof_to_binary_label(proof: str, orientation: tuple[str, str]) -> str:
    if proof == orientation[0]:
        return "first"
    if proof == orientation[1]:
        return "second"
    raise SystemExit(f"Proof {proof!r} is not in orientation {orientation!r}")


def grouped_presentations(presentations: list[Presentation]) -> dict[tuple[str, str], list[Presentation]]:
    groups: dict[tuple[str, str], list[Presentation]] = {}
    for presentation in presentations:
        groups.setdefault(presentation.group_key, []).append(presentation)
    for rows in groups.values():
        rows.sort(key=lambda row: row.order_index)
    return groups


def choice_to_proof(presentation: Presentation, choice: str) -> str:
    if choice == "left":
        return presentation.left
    if choice == "right":
        return presentation.right
    raise SystemExit(f"Invalid side choice for {presentation.pair_id}: {choice!r}")


def condition_majority(unit_ids: list[str], conditions: dict[str, dict[str, str]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for unit_id in unit_ids:
        votes = [condition[unit_id] for condition in conditions.values() if unit_id in condition]
        winner = strict_majority(votes)
        if winner is not None:
            labels[unit_id] = winner
    return labels


def majority_labels(unit_ids: list[str], raters: dict[str, dict[str, str]]) -> tuple[dict[str, str], list[str]]:
    majority = {}
    no_majority = []
    for unit_id in unit_ids:
        votes = [labels[unit_id] for labels in raters.values() if unit_id in labels]
        winner = strict_majority(votes)
        if winner is None or len(votes) < 2:
            no_majority.append(unit_id)
        else:
            majority[unit_id] = winner
    return majority, no_majority


def strict_majority(votes: list[str]) -> str | None:
    if not votes:
        return None
    counts = Counter(votes)
    choice, count = counts.most_common(1)[0]
    if count > len(votes) / 2:
        return choice
    return None


def accuracy_report(
    systems: dict[str, dict[str, str]],
    majority: dict[str, str],
    subsets: dict[str, list[str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        name: {subset: accuracy_entry(labels, majority, ids) for subset, ids in subsets.items()}
        for name, labels in systems.items()
    }


def accuracy_entry(labels: dict[str, str], target: dict[str, str], unit_ids: list[str]) -> dict[str, Any]:
    available = [unit_id for unit_id in unit_ids if unit_id in labels and unit_id in target]
    correct = sum(labels[unit_id] == target[unit_id] for unit_id in available)
    lower, upper = wilson(correct, len(available))
    return {
        "n": len(available),
        "correct": correct,
        "accuracy": correct / len(available) if available else None,
        "wilson_95": [lower, upper],
    }


def calibration_report(
    score_gaps: dict[str, float],
    priorproof: dict[str, str],
    majority: dict[str, str],
    unit_ids: list[str],
) -> list[dict[str, Any]]:
    eligible = [
        unit_id for unit_id in unit_ids if unit_id in score_gaps and unit_id in priorproof and unit_id in majority
    ]
    eligible.sort(key=lambda unit_id: (score_gaps[unit_id], unit_id))
    rows = []
    n = len(eligible)
    for index, name in enumerate(QUARTILE_NAMES):
        start = index * n // 4
        end = (index + 1) * n // 4
        bucket = eligible[start:end]
        correct = sum(priorproof[unit_id] == majority[unit_id] for unit_id in bucket)
        lower, upper = wilson(correct, len(bucket))
        rows.append(
            {
                "quartile": name,
                "n": len(bucket),
                "correct": correct,
                "accuracy": correct / len(bucket) if bucket else None,
                "wilson_95": [lower, upper],
                "min_score_gap": score_gaps[bucket[0]] if bucket else None,
                "max_score_gap": score_gaps[bucket[-1]] if bucket else None,
            }
        )
    return rows


def mcnemar_report(
    systems: dict[str, dict[str, str]],
    majority: dict[str, str],
    subsets: dict[str, list[str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    priorproof = systems["PriorProof"]
    rows: dict[str, dict[str, dict[str, Any]]] = {}
    for name, labels in systems.items():
        if not name.startswith("LLM"):
            continue
        rows[name] = {}
        for subset, unit_ids in subsets.items():
            available = [
                unit_id
                for unit_id in unit_ids
                if unit_id in priorproof and unit_id in labels and unit_id in majority
            ]
            pp_correct = {unit_id: priorproof[unit_id] == majority[unit_id] for unit_id in available}
            llm_correct = {unit_id: labels[unit_id] == majority[unit_id] for unit_id in available}
            both = sum(pp_correct[unit_id] and llm_correct[unit_id] for unit_id in available)
            neither = sum((not pp_correct[unit_id]) and (not llm_correct[unit_id]) for unit_id in available)
            b_pp_only = sum(pp_correct[unit_id] and not llm_correct[unit_id] for unit_id in available)
            c_llm_only = sum((not pp_correct[unit_id]) and llm_correct[unit_id] for unit_id in available)
            rows[name][subset] = {
                "n": len(available),
                "priorproof_correct": sum(pp_correct.values()),
                "llm_correct": sum(llm_correct.values()),
                "both_correct": both,
                "neither_correct": neither,
                "priorproof_only_correct": b_pp_only,
                "llm_only_correct": c_llm_only,
                "exact_two_sided_p": exact_mcnemar_p(b_pp_only, c_llm_only),
            }
    return rows


def inter_rater_report(
    raters: dict[str, dict[str, str]],
    subsets: dict[str, list[str]],
) -> dict[str, Any]:
    names = list(raters)
    pairwise = {}
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1 :]:
            key = f"{left_name} vs {right_name}"
            pairwise[key] = {
                subset: agreement_entry(raters[left_name], raters[right_name], ids)
                for subset, ids in subsets.items()
            }
    return {
        "pairwise": pairwise,
        "fleiss_kappa": {
            subset: fleiss_kappa([raters[name] for name in names], ids) for subset, ids in subsets.items()
        },
    }


def agreement_entry(left: dict[str, str], right: dict[str, str], unit_ids: list[str]) -> dict[str, Any]:
    available = [unit_id for unit_id in unit_ids if unit_id in left and unit_id in right]
    agree = sum(left[unit_id] == right[unit_id] for unit_id in available)
    return {
        "n": len(available),
        "agree": agree,
        "agreement": agree / len(available) if available else None,
        "cohen_kappa": cohen_kappa(left, right, available),
    }


def rater_system_report(
    unit_ids: list[str],
    raters: dict[str, dict[str, str]],
    systems: dict[str, dict[str, str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    rows: dict[str, dict[str, dict[str, Any]]] = {}
    for rater_name, rater_labels in raters.items():
        rows[rater_name] = {}
        for system_name, system_labels in systems.items():
            available = [unit_id for unit_id in unit_ids if unit_id in rater_labels and unit_id in system_labels]
            agree = sum(rater_labels[unit_id] == system_labels[unit_id] for unit_id in available)
            rows[rater_name][system_name] = {
                "n": len(available),
                "agree": agree,
                "agreement": agree / len(available) if available else None,
            }
    return rows


def unanimous_count(unit_ids: list[str], raters: dict[str, dict[str, str]]) -> int:
    count = 0
    for unit_id in unit_ids:
        votes = [labels[unit_id] for labels in raters.values() if unit_id in labels]
        if len(votes) == len(raters) and len(set(votes)) == 1:
            count += 1
    return count


def cohen_kappa(left: dict[str, str], right: dict[str, str], unit_ids: list[str]) -> float | None:
    if not unit_ids:
        return None
    observed = sum(left[unit_id] == right[unit_id] for unit_id in unit_ids) / len(unit_ids)
    labels = set(left[unit_id] for unit_id in unit_ids) | set(right[unit_id] for unit_id in unit_ids)
    left_counts = Counter(left[unit_id] for unit_id in unit_ids)
    right_counts = Counter(right[unit_id] for unit_id in unit_ids)
    expected = sum((left_counts[label] / len(unit_ids)) * (right_counts[label] / len(unit_ids)) for label in labels)
    if expected == 1.0:
        return None
    return (observed - expected) / (1 - expected)


def fleiss_kappa(raters: list[dict[str, str]], unit_ids: list[str]) -> dict[str, Any]:
    complete = [unit_id for unit_id in unit_ids if all(unit_id in rater for rater in raters)]
    if not complete or len(raters) < 2:
        return {"n": len(complete), "kappa": None}
    n_raters = len(raters)
    p_i = []
    category_totals = Counter()
    for unit_id in complete:
        counts = Counter(rater[unit_id] for rater in raters)
        category_totals.update(counts)
        p_i.append((sum(count * count for count in counts.values()) - n_raters) / (n_raters * (n_raters - 1)))
    p_bar = sum(p_i) / len(p_i)
    p_e = sum((count / (len(complete) * n_raters)) ** 2 for count in category_totals.values())
    if p_e == 1.0:
        return {"n": len(complete), "kappa": None}
    return {"n": len(complete), "kappa": (p_bar - p_e) / (1 - p_e)}


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return center - half, center + half


def exact_mcnemar_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    lower_tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / (2**n)
    return min(1.0, 2 * lower_tail)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_named_path(spec: str) -> tuple[str, Path]:
    if "=" in spec:
        name, raw_path = spec.split("=", 1)
        return name, Path(raw_path)
    path = Path(spec)
    return path.stem, path


def proof_side_id(row: dict[str, Any], packet_row: dict[str, Any], key: str, path: Path, pair_id: str) -> str:
    value = row.get(key)
    candidate = side_id_from_value(value)
    if candidate is not None:
        return candidate
    candidate = side_id_from_value(packet_row.get(key))
    if candidate is not None:
        return candidate
    raise SystemExit(f"Missing proof identifier for {pair_id}.{key} in {path}")


def side_id_from_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for candidate_key in ("name", "declaration", "declaration_name", "id"):
            candidate = value.get(candidate_key)
            if isinstance(candidate, str):
                return candidate
    return None


def require_str(row: dict[str, Any], key: str, path: Path) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise SystemExit(f"Missing string key {key!r} in {path}")
    return value


def check_coverage(name: str, expected_ids: list[str], labels: dict[str, Any]) -> None:
    expected = set(expected_ids)
    observed = set(labels)
    missing = expected - observed
    extra = observed - expected
    if missing or extra:
        raise SystemExit(f"{name} coverage mismatch: missing={len(missing)}, extra={len(extra)}")


def group_id(key: tuple[str, str]) -> str:
    return f"{key[0]} || {key[1]}"


def print_full_report(report: dict[str, Any]) -> None:
    print_inventory(report["repeat_inventory"])
    print_analysis("Presentation-level old analysis", report["presentation_level_old"])
    if "collapsed_majority_across_presentations" in report:
        print_analysis(
            "Distinct pairs: majority across repeated presentations",
            report["collapsed_majority_across_presentations"],
        )
        print_analysis("Distinct pairs: first presentation only", report["collapsed_first_presentation"])
        print_changed_claims(report["presentation_level_old"], report["collapsed_majority_across_presentations"])


def print_inventory(inventory: dict[str, Any]) -> None:
    print("Repeat inventory")
    print(f"presentations: {inventory['presentation_count']}")
    print(f"presentation counts by subset: {inventory['presentation_counts_by_subset']}")
    print(f"distinct underlying pairs: {inventory['distinct_underlying_pair_count']}")
    print(f"distinct underlying pairs by subset: {inventory['distinct_underlying_pair_counts_by_subset']}")
    print(
        "canonical = 12 distinct x 3 presentations:",
        "PASS" if inventory["canonical_repeats_check"]["passed"] else "FAIL",
    )
    print(
        "stratified duplicate check:",
        "PASS" if inventory["stratified_duplicate_check"]["passed"] else "FAIL",
    )
    print(
        f"twin sets: {inventory['duplicate_underlying_pair_group_count']} groups, "
        f"{inventory['duplicate_underlying_pair_count']} extra rows"
    )
    for twin in inventory["twin_sets"]:
        swapped = "swapped" if twin["has_swapped_order"] else "same order"
        print(f"  {twin['pair_ids']} [{twin['source'][0]}] {swapped}")
        for order in twin["presentation_orders"]:
            print(f"    {order['pair_id']}: {order['left']} vs {order['right']}")


def print_analysis(title: str, analysis: dict[str, Any]) -> None:
    print(f"\n{title}")
    print(f"units: {analysis['unit_count']}; subsets: {analysis['subset_counts']}")
    majority = analysis["human_majority"]
    label_counts = majority["label_counts"]
    label_count_text = label_counts if len(label_counts) <= 4 else f"{len(label_counts)} proof identities"
    print(
        f"human majority n={majority['n']} labels={label_count_text} "
        f"unanimous={majority['unanimous_count']}"
    )
    if majority["no_majority_units"]:
        print(f"no-majority units: {len(majority['no_majority_units'])}")

    print("inter-rater agreement")
    for name, subsets in analysis["inter_rater_agreement"]["pairwise"].items():
        entry = subsets["overall"]
        print(f"  {name}: {format_count(entry['agree'], entry['n'])}, kappa={format_float(entry['cohen_kappa'])}")
    for subset, entry in analysis["inter_rater_agreement"]["fleiss_kappa"].items():
        print(f"  Fleiss {subset}: n={entry['n']}, kappa={format_float(entry['kappa'])}")

    print("accuracy vs human majority")
    for name, subsets in analysis["accuracy_vs_majority"].items():
        print(f"  {name}")
        for subset in SUBSETS:
            entry = subsets[subset]
            print(f"    {subset}: {format_count(entry['correct'], entry['n'])}, Wilson {format_interval(entry['wilson_95'])}")

    print("calibration quartiles")
    for row in analysis["calibration_quartiles"]:
        print(
            f"  {row['quartile']}: {format_count(row['correct'], row['n'])}, "
            f"Wilson {format_interval(row['wilson_95'])}"
        )

    print("McNemar vs PriorProof")
    for name, subsets in analysis["mcnemar_priorproof_vs_llm"].items():
        entry = subsets["overall"]
        print(
            f"  {name}: n={entry['n']}, PP={entry['priorproof_correct']}, LLM={entry['llm_correct']}, "
            f"b_PP_only={entry['priorproof_only_correct']}, c_LLM_only={entry['llm_only_correct']}, "
            f"p={entry['exact_two_sided_p']:.4f}"
        )

    if "sanity_checks" in analysis:
        sanity = analysis["sanity_checks"]
        print(f"sanity: PriorProof deterministic across presentations = {sanity['priorproof_deterministic']}")
        dropped = analysis["dropped_votes_by_entity"]
        dropped_nonzero = {name: ids for name, ids in dropped.items() if ids}
        print(f"dropped collapse ties: {dropped_nonzero if dropped_nonzero else 'none'}")
        print("repeat consistency")
        for name, entry in analysis["repeat_consistency"].items():
            print(
                f"  {name}: {entry['consistent_votes']}/{entry['total_repeat_presentations']} "
                f"presentation votes align with within-pair majority; "
                f"{entry['fully_consistent_groups']}/{entry['total_repeat_groups']} repeat groups fully consistent"
            )
        baseline = analysis["repeat_consistency_baseline"]
        print(
            "  chance baseline: "
            f"majority-match votes floor "
            f"{format_number(baseline['majority_match_vote_floor'])}/"
            f"{baseline['total_repeat_presentations']}, "
            f"chance expectation "
            f"{format_number(baseline['majority_match_vote_chance_expectation'])}/"
            f"{baseline['total_repeat_presentations']}; "
            f"fully consistent groups chance expectation "
            f"{format_number(baseline['fully_consistent_group_chance_expectation'])}/"
            f"{baseline['repeat_group_count']}"
        )


def print_changed_claims(old: dict[str, Any], collapsed: dict[str, Any]) -> None:
    print("\nREADME-impact summary")
    for system in ("PriorProof", "LLM gpt-5-mini/strict", "LLM majority (ties excluded)"):
        if system not in old["accuracy_vs_majority"] or system not in collapsed["accuracy_vs_majority"]:
            continue
        old_entry = old["accuracy_vs_majority"][system]["overall"]
        new_entry = collapsed["accuracy_vs_majority"][system]["overall"]
        print(
            f"  {system}: old {format_count(old_entry['correct'], old_entry['n'])} -> "
            f"distinct {format_count(new_entry['correct'], new_entry['n'])}"
        )
    old_canon = old["accuracy_vs_majority"]["PriorProof"]["canonical"]
    new_canon = collapsed["accuracy_vs_majority"]["PriorProof"]["canonical"]
    old_strat = old["accuracy_vs_majority"]["PriorProof"]["stratified"]
    new_strat = collapsed["accuracy_vs_majority"]["PriorProof"]["stratified"]
    print(
        f"  PriorProof canonical: old {format_count(old_canon['correct'], old_canon['n'])} -> "
        f"distinct {format_count(new_canon['correct'], new_canon['n'])}, "
        f"Wilson {format_interval(new_canon['wilson_95'])}"
    )
    print(
        f"  PriorProof stratified: old {format_count(old_strat['correct'], old_strat['n'])} -> "
        f"distinct {format_count(new_strat['correct'], new_strat['n'])}"
    )


def format_duplicate_error(inventory: dict[str, Any]) -> str:
    lines = [
        f"Answer key contains {inventory['duplicate_underlying_pair_count']} duplicate underlying proof-pair rows "
        f"across {inventory['duplicate_underlying_pair_group_count']} twin sets.",
        "Repeated screening pairs must be removed or analyzed with --allow-repeats-with-collapse.",
    ]
    for twin in inventory["twin_sets"][:10]:
        lines.append(f"  {twin['pair_ids']}: {twin['proof_pair']}")
    if len(inventory["twin_sets"]) > 10:
        lines.append(f"  ... {len(inventory['twin_sets']) - 10} more")
    return "\n".join(lines)


def format_count(k: int, n: int) -> str:
    if n == 0:
        return "0/0 (n/a)"
    return f"{k}/{n} ({100 * k / n:.1f}%)"


def format_interval(values: list[float]) -> str:
    if any(math.isnan(value) for value in values):
        return "[n/a, n/a]"
    return f"[{100 * values[0]:.1f}, {100 * values[1]:.1f}]"


def format_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def format_number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if math.isclose(float(value), round(float(value))):
        return str(int(round(float(value))))
    return f"{float(value):.3f}"


if __name__ == "__main__":
    main()
