from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from ..data.models import DeclarationRecord, Footprint
from .retriever import RetrievalHit


@dataclass(frozen=True)
class PriorConfig:
    alpha: float = 0.25
    retrieval_weight: float = 0.55
    namespace_weight: float = 0.2
    module_weight: float = 0.15
    global_weight: float = 0.1
    retrieval_temperature: float = 0.2

    def normalized(self) -> "PriorConfig":
        total = self.retrieval_weight + self.namespace_weight + self.module_weight + self.global_weight
        if total <= 0:
            return self
        return PriorConfig(
            alpha=self.alpha,
            retrieval_weight=self.retrieval_weight / total,
            namespace_weight=self.namespace_weight / total,
            module_weight=self.module_weight / total,
            global_weight=self.global_weight / total,
            retrieval_temperature=self.retrieval_temperature,
        )


@dataclass(frozen=True)
class PriorCountState:
    namespace_counts: dict[str, Counter[str]]
    module_counts: dict[str, Counter[str]]
    global_counts: Counter[str]


def build_hierarchical_prior(
    target: DeclarationRecord,
    pre_t_records: list[DeclarationRecord],
    footprints_by_decl: dict[str, Footprint],
    retrieval_hits: list[RetrievalHit],
    config: PriorConfig | None = None,
    count_state: PriorCountState | None = None,
) -> dict[str, float]:
    config = (config or PriorConfig()).normalized()
    available_hits = [hit for hit in retrieval_hits if hit.name in footprints_by_decl]
    retrieval = weighted_family_counts(
        [footprints_by_decl[hit.name] for hit in available_hits],
        weights=softmax_weights([hit.score for hit in available_hits], config.retrieval_temperature),
    )
    if count_state is None:
        count_state = build_prior_count_state(pre_t_records, footprints_by_decl)
    namespace = count_state.namespace_counts.get(target.namespace, Counter())
    module = count_state.module_counts.get(target.module, Counter())
    global_counts = count_state.global_counts
    families = set(retrieval) | set(namespace) | set(module) | set(global_counts) | {"global"}
    distributions = {
        "retrieval": smooth_distribution(retrieval, families, config.alpha),
        "namespace": smooth_distribution(namespace, families, config.alpha),
        "module": smooth_distribution(module, families, config.alpha),
        "global": smooth_distribution(global_counts, families, config.alpha),
    }
    prior: dict[str, float] = {}
    for family in families:
        prior[family] = (
            config.retrieval_weight * distributions["retrieval"][family]
            + config.namespace_weight * distributions["namespace"][family]
            + config.module_weight * distributions["module"][family]
            + config.global_weight * distributions["global"][family]
        )
    return normalize_distribution(prior)


def build_prior_count_state(
    pre_t_records: list[DeclarationRecord],
    footprints_by_decl: dict[str, Footprint],
) -> PriorCountState:
    namespace_counts: dict[str, Counter[str]] = {}
    module_counts: dict[str, Counter[str]] = {}
    global_counts: Counter[str] = Counter()
    for record in pre_t_records:
        footprint = footprints_by_decl.get(record.name)
        if footprint is None:
            continue
        counts = family_counts([footprint])
        namespace_counts.setdefault(record.namespace, Counter()).update(counts)
        module_counts.setdefault(record.module, Counter()).update(counts)
        global_counts.update(counts)
    return PriorCountState(
        namespace_counts=namespace_counts,
        module_counts=module_counts,
        global_counts=global_counts,
    )


def family_counts(footprints: Iterable[Footprint]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for footprint in footprints:
        for item in footprint.items:
            counts[item.family] += item.weight
    return counts


def weighted_family_counts(footprints: Iterable[Footprint], weights: list[float]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for idx, footprint in enumerate(footprints):
        weight = weights[idx] if idx < len(weights) else 1.0
        for item in footprint.items:
            counts[item.family] += weight * item.weight
    return counts


def smooth_distribution(counts: Counter[str], families: set[str], alpha: float) -> dict[str, float]:
    total = sum(counts.values()) + alpha * len(families)
    if total <= 0:
        return {family: 1.0 / len(families) for family in families}
    return {family: (counts.get(family, 0.0) + alpha) / total for family in families}


def normalize_distribution(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        return {key: 1.0 / len(values) for key in values}
    return {key: value / total for key, value in values.items()}


def softmax_weights(scores: list[float], temperature: float) -> list[float]:
    if not scores:
        return []
    temp = max(1e-6, temperature)
    peak = max(scores)
    exps = [math.exp((score - peak) / temp) for score in scores]
    total = sum(exps)
    return [value / total for value in exps]


def chronological_log_likelihood(footprints: Iterable[Footprint], priors: dict[str, dict[str, float]]) -> float:
    total = 0.0
    for footprint in footprints:
        prior = priors.get(footprint.declaration, {})
        for item in footprint.items:
            total += item.weight * math.log(max(1e-9, prior.get(item.family, 0.0)))
    return total


def grid_search_prior(
    candidates: list[PriorConfig],
    scored_footprints: list[Footprint],
    prior_builder,
) -> tuple[PriorConfig, list[dict[str, float]]]:
    """Fit config by chronological log likelihood.

    `prior_builder` is called as `prior_builder(config)` and must return a
    mapping declaration -> family distribution for the chronological fold.
    """

    rows: list[dict[str, float]] = []
    best_config = candidates[0]
    best_ll = -math.inf
    for config in candidates:
        priors = prior_builder(config)
        ll = chronological_log_likelihood(scored_footprints, priors)
        rows.append(
            {
                "alpha": config.alpha,
                "retrieval_weight": config.retrieval_weight,
                "namespace_weight": config.namespace_weight,
                "module_weight": config.module_weight,
                "global_weight": config.global_weight,
                "retrieval_temperature": config.retrieval_temperature,
                "log_likelihood": ll,
            }
        )
        if ll > best_ll:
            best_ll = ll
            best_config = config
    return best_config, rows
