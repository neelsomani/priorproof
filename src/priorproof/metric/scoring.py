from __future__ import annotations

import math
from collections import Counter

from ..data.models import Footprint, NoveltyScore


def score_footprint(
    footprint: Footprint,
    prior: dict[str, float],
    floor: float = 1e-9,
    flags: tuple[str, ...] = (),
) -> NoveltyScore:
    item_scores: list[dict[str, object]] = []
    total = 0.0
    weight_sum = 0.0
    prior_mass = 0.0
    for item in footprint.items:
        probability = max(floor, prior.get(item.family, 0.0))
        surprisal = -math.log(probability)
        weighted = item.weight * surprisal
        total += weighted
        weight_sum += item.weight
        prior_mass += prior.get(item.family, 0.0)
        item_scores.append(
            {
                "family": item.family,
                "raw_name": item.raw_name,
                "probability": probability,
                "surprisal": surprisal,
                "weight": item.weight,
                "weighted_surprisal": weighted,
                "backoff_depth": item.backoff_depth,
            }
        )
    return NoveltyScore(
        declaration=footprint.declaration,
        snapshot_id=footprint.snapshot_id,
        threshold=footprint.threshold,
        surprisal=total,
        mean_item_surprisal=total / weight_sum if weight_sum else 0.0,
        prior_mass=prior_mass,
        item_scores=tuple(item_scores),
        flags=flags,
    )


def empirical_family_distribution(
    footprints: list[Footprint],
    alpha: float = 0.1,
) -> dict[str, float]:
    counts: Counter[str] = Counter()
    for footprint in footprints:
        for item in footprint.items:
            counts[item.family] += item.weight
    if not counts:
        return {"global": 1.0}
    total = sum(counts.values()) + alpha * len(counts)
    return {family: (count + alpha) / total for family, count in counts.items()}

