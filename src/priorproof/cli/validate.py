from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import read_jsonl, write_json
from priorproof.data.models import NoveltyScore
from priorproof.corpus.pipeline import load_footprints
from priorproof.evaluation.reports import (
    ablation_delta,
    agreement_report,
    backoff_depth_decorrelation,
    chronological_prediction_test,
    metric_vs_rater_consensus,
    parametric_leakage_probe,
    redundancy_summary,
    threshold_sweep_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mechanical validation summaries from prepared artifacts.")
    parser.add_argument("--footprints", nargs="+", required=True, help="Footprint JSONL files, one per threshold.")
    parser.add_argument("--priors", required=True, help="Prior JSONL from score_novelty.")
    parser.add_argument("--scores", nargs="+", required=True, help="Score JSONL files, one per threshold.")
    parser.add_argument("--ablated-scores", nargs="*", default=[], help="Optional ablated score JSONL files.")
    parser.add_argument("--counterfactual-priors", help="Optional counterfactual prior JSONL for leakage probe.")
    parser.add_argument("--rater-responses", help="Optional JSONL rows with pair_id, left, right, and choice.")
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    first_footprints = load_footprints(args.footprints[0])
    priors = {
        str(row["declaration"]): dict(row["prior"])
        for row in read_jsonl(args.priors)
    }
    scores_by_threshold: dict[int, list[NoveltyScore]] = {}
    for path in args.scores:
        scores = [score_from_json(row) for row in read_jsonl(path)]
        if scores:
            scores_by_threshold[scores[0].threshold] = scores
    report = {
        "chronological_prediction": chronological_prediction_test(first_footprints, priors),
        "redundancy_detection": redundancy_summary(first_footprints),
        "backoff_depth_decorrelation": backoff_depth_decorrelation(
            score for scores in scores_by_threshold.values() for score in scores
        ),
        "threshold_sweep": threshold_sweep_summary(scores_by_threshold),
    }
    if args.ablated_scores:
        base_scores = {score.declaration: score for score in next(iter(scores_by_threshold.values()), [])}
        report["ablations"] = []
        for path in args.ablated_scores:
            ablated = {score.declaration: score for score in [score_from_json(row) for row in read_jsonl(path)]}
            report["ablations"].append({"path": path, **ablation_delta(base_scores, ablated)})
    if args.counterfactual_priors:
        counterfactual = {
            str(row["declaration"]): dict(row["prior"])
            for row in read_jsonl(args.counterfactual_priors)
        }
        report["parametric_leakage_probe"] = parametric_leakage_probe(priors, counterfactual, first_footprints)
    if args.rater_responses:
        rater_rows = list(read_jsonl(args.rater_responses))
        report["rater_agreement"] = agreement_report(rater_rows)
        base_scores = {score.declaration: score for score in next(iter(scores_by_threshold.values()), [])}
        report["metric_vs_rater_consensus"] = metric_vs_rater_consensus(rater_rows, base_scores)
    write_json(Path(args.out), report)


def score_from_json(data: dict) -> NoveltyScore:
    return NoveltyScore(
        declaration=str(data["declaration"]),
        snapshot_id=str(data["snapshot_id"]),
        threshold=int(data["threshold"]),
        surprisal=float(data["surprisal"]),
        mean_item_surprisal=float(data["mean_item_surprisal"]),
        prior_mass=float(data.get("prior_mass", 0.0)),
        item_scores=tuple(dict(item) for item in data.get("item_scores", [])),
        flags=tuple(str(flag) for flag in data.get("flags", [])),
    )


if __name__ == "__main__":
    main()
