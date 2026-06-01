from __future__ import annotations

import math
import random
from collections import Counter
from statistics import mean
from typing import Iterable

from ..data.models import Footprint, NoveltyScore
from ..modeling.retriever import RetrievalHit, neighbor_overlap


def chronological_prediction_test(
    footprints: Iterable[Footprint],
    priors: dict[str, dict[str, float]],
    random_seed: int = 13,
) -> dict[str, float]:
    rng = random.Random(random_seed)
    footprints = list(footprints)
    all_families = sorted({item.family for fp in footprints for item in fp.items})
    observed_ll: list[float] = []
    random_ll: list[float] = []
    for footprint in footprints:
        prior = priors.get(footprint.declaration, {})
        if not footprint.items or not all_families:
            continue
        for item in footprint.items:
            observed_ll.append(math.log(max(1e-9, prior.get(item.family, 0.0))))
            random_family = rng.choice(all_families)
            random_ll.append(math.log(max(1e-9, prior.get(random_family, 0.0))))
    return {
        "observed_mean_log_prob": mean(observed_ll) if observed_ll else float("nan"),
        "random_mean_log_prob": mean(random_ll) if random_ll else float("nan"),
        "margin": (mean(observed_ll) - mean(random_ll)) if observed_ll and random_ll else float("nan"),
        "n_items": float(len(observed_ll)),
    }


def ablation_delta(
    full_scores: dict[str, NoveltyScore],
    ablated_scores: dict[str, NoveltyScore],
) -> dict[str, float]:
    common = sorted(set(full_scores) & set(ablated_scores))
    deltas = [ablated_scores[name].surprisal - full_scores[name].surprisal for name in common]
    return {
        "n": float(len(common)),
        "mean_surprisal_delta": mean(deltas) if deltas else float("nan"),
        "positive_delta_rate": sum(delta > 0 for delta in deltas) / len(deltas) if deltas else float("nan"),
    }


def parametric_leakage_probe(
    normal_priors: dict[str, dict[str, float]],
    counterfactual_priors: dict[str, dict[str, float]],
    footprints: Iterable[Footprint],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for footprint in footprints:
        normal = normal_priors.get(footprint.declaration, {})
        counterfactual = counterfactual_priors.get(footprint.declaration, {})
        normal_ll = footprint_log_prob(footprint, normal)
        counter_ll = footprint_log_prob(footprint, counterfactual)
        rows.append(
            {
                "declaration": footprint.declaration,
                "normal_log_prob": normal_ll,
                "counterfactual_log_prob": counter_ll,
                "retrieval_sensitivity": normal_ll - counter_ll,
            }
        )
    return rows


def proof_edit_stability(
    baseline: dict[str, NoveltyScore],
    variants: dict[str, list[NoveltyScore]],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for name, base in baseline.items():
        for idx, variant in enumerate(variants.get(name, [])):
            rows.append(
                {
                    "declaration": name,
                    "variant": float(idx),
                    "surprisal_delta": variant.surprisal - base.surprisal,
                    "mean_item_surprisal_delta": variant.mean_item_surprisal - base.mean_item_surprisal,
                }
            )
    return rows


def backoff_depth_decorrelation(scores: Iterable[NoveltyScore]) -> dict[str, float]:
    xs: list[float] = []
    ys: list[float] = []
    for score in scores:
        depths = [float(item.get("backoff_depth", 0.0)) for item in score.item_scores]
        if not depths:
            continue
        xs.append(mean(depths))
        ys.append(score.surprisal)
    return {"n": float(len(xs)), "pearson": pearson(xs, ys)}


def threshold_sweep_summary(scores_by_threshold: dict[int, list[NoveltyScore]]) -> dict[str, object]:
    thresholds = sorted(scores_by_threshold)
    ranks_by_threshold: dict[int, dict[str, int]] = {}
    for threshold in thresholds:
        ordered = sorted(scores_by_threshold[threshold], key=lambda item: item.surprisal, reverse=True)
        ranks_by_threshold[threshold] = {score.declaration: idx for idx, score in enumerate(ordered)}
    comparisons: list[dict[str, float]] = []
    for left, right in zip(thresholds, thresholds[1:]):
        common = sorted(set(ranks_by_threshold[left]) & set(ranks_by_threshold[right]))
        comparisons.append(
            {
                "left_threshold": float(left),
                "right_threshold": float(right),
                "rank_correlation": pearson(
                    [float(ranks_by_threshold[left][name]) for name in common],
                    [float(ranks_by_threshold[right][name]) for name in common],
                ),
                "n": float(len(common)),
            }
        )
    return {"thresholds": thresholds, "rank_correlations": comparisons}


def neighbor_stability(
    baseline_neighbors: dict[str, list[RetrievalHit]],
    candidate_neighbors: dict[str, list[RetrievalHit]],
    k: int = 32,
) -> dict[str, float]:
    overlaps = [
        neighbor_overlap(baseline_neighbors[name], candidate_neighbors[name], k=k)
        for name in baseline_neighbors.keys() & candidate_neighbors.keys()
    ]
    return {
        "n": float(len(overlaps)),
        "mean_overlap": mean(overlaps) if overlaps else float("nan"),
        "min_overlap": min(overlaps) if overlaps else float("nan"),
    }


def rater_pairs(
    scores: list[NoveltyScore],
    k: int = 100,
    min_gap: float = 0.5,
    random_seed: int = 17,
) -> list[dict[str, object]]:
    rng = random.Random(random_seed)
    ordered = sorted(scores, key=lambda item: item.surprisal)
    candidates: list[tuple[NoveltyScore, NoveltyScore]] = []
    for low_idx in range(len(ordered)):
        for high_idx in range(low_idx + 1, len(ordered)):
            low = ordered[low_idx]
            high = ordered[high_idx]
            if high.surprisal - low.surprisal >= min_gap:
                candidates.append((low, high))
    rng.shuffle(candidates)
    return [
        {
            "pair_id": f"pair_{idx:03d}",
            "left": left.declaration,
            "right": right.declaration,
            "left_score": left.surprisal,
            "right_score": right.surprisal,
        }
        for idx, (left, right) in enumerate(candidates[:k], start=1)
    ]


def footprint_log_prob(footprint: Footprint, prior: dict[str, float]) -> float:
    return sum(item.weight * math.log(max(1e-9, prior.get(item.family, 0.0))) for item in footprint.items)


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return float("nan")
    mx = mean(xs)
    my = mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denom_x == 0.0 or denom_y == 0.0:
        return float("nan")
    return numerator / (denom_x * denom_y)


def agreement_report(rows: Iterable[dict[str, str]]) -> dict[str, float]:
    by_pair: dict[str, list[str]] = {}
    for row in rows:
        by_pair.setdefault(row["pair_id"], []).append(row["choice"])
    comparable = [choices for choices in by_pair.values() if len(choices) >= 2]
    agree = sum(1 for choices in comparable if len(set(choices[:2])) == 1)
    counts = Counter(choice for choices in comparable for choice in choices[:2])
    total = sum(counts.values())
    chance = sum((count / total) ** 2 for count in counts.values()) if total else float("nan")
    observed = agree / len(comparable) if comparable else float("nan")
    kappa = (observed - chance) / (1 - chance) if comparable and chance < 1 else float("nan")
    return {"n_pairs": float(len(comparable)), "observed_agreement": observed, "cohen_kappa": kappa}


def redundancy_summary(footprints: Iterable[Footprint]) -> dict[str, object]:
    mode_counts: Counter[str] = Counter()
    hit_count = 0
    declaration_count = 0
    examples = []
    for footprint in footprints:
        if not footprint.redundant_subterms:
            continue
        declaration_count += 1
        for hit in footprint.redundant_subterms:
            hit_count += 1
            mode_counts[str(hit.get("mode", "unknown"))] += 1
        if len(examples) < 25:
            examples.append(
                {
                    "declaration": footprint.declaration,
                    "snapshot_id": footprint.snapshot_id,
                    "hits": list(footprint.redundant_subterms),
                }
            )
    return {
        "declarations_with_hits": declaration_count,
        "hit_count": hit_count,
        "mode_counts": dict(mode_counts),
        "examples": examples,
    }


def metric_vs_rater_consensus(
    rater_rows: Iterable[dict[str, str]],
    score_by_decl: dict[str, NoveltyScore],
) -> dict[str, float]:
    by_pair: dict[str, list[dict[str, str]]] = {}
    for row in rater_rows:
        by_pair.setdefault(row["pair_id"], []).append(row)
    comparable = []
    for rows in by_pair.values():
        if len(rows) < 2:
            continue
        choices = [row["choice"] for row in rows[:2]]
        if len(set(choices)) != 1:
            continue
        left = rows[0].get("left")
        right = rows[0].get("right")
        if not left or not right or left not in score_by_decl or right not in score_by_decl:
            continue
        metric_choice = left if score_by_decl[left].surprisal >= score_by_decl[right].surprisal else right
        comparable.append(metric_choice == choices[0])
    return {
        "n_consensus_pairs": float(len(comparable)),
        "metric_accuracy": sum(comparable) / len(comparable) if comparable else float("nan"),
    }
