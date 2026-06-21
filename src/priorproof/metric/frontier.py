from __future__ import annotations

import math
from collections import Counter

from .families import choose_family, family_supports
from ..data.models import DeclarationRecord, Dependency, Footprint, FootprintItem, Snapshot


def established_frontier(
    record: DeclarationRecord,
    snapshot: Snapshot,
    reuse_counts: Counter[str],
    dependency_lookup: dict[str, Dependency],
    dependency_graph: dict[str, set[str]],
    threshold: int,
    filtered_dependencies: tuple[Dependency, ...],
    redundant_raw_names: set[str] | None = None,
    min_family_support: int = 5,
    supports: dict[str, int] | None = None,
) -> Footprint:
    """Unfold proof-local dependencies until established machinery is reached."""

    redundant_raw_names = redundant_raw_names or set()
    frontier_names: list[str] = []
    for dep in filtered_dependencies:
        frontier_names.extend(
            _expand_to_frontier(dep.name, reuse_counts, dependency_graph, threshold, redundant_raw_names)
        )

    unique_frontier = sorted(set(frontier_names))
    if supports is None:
        all_pre_t_deps = [dep for name, dep in dependency_lookup.items() if reuse_counts.get(name, 0) > 0]
        supports = family_supports(all_pre_t_deps)
    items: list[FootprintItem] = []
    for raw_name in unique_frontier:
        dep = dependency_lookup.get(raw_name, Dependency(name=raw_name))
        family = choose_family(dep, supports, min_family_support)
        reuse = max(1, reuse_counts.get(raw_name, 0))
        items.append(
            FootprintItem(
                family=family.name,
                raw_name=raw_name,
                weight=1.0 / math.log2(reuse + 2.0),
                backoff_depth=family.depth,
                support=family.support,
            )
        )

    return Footprint(
        declaration=record.name,
        snapshot_id=snapshot.snapshot_id,
        threshold=threshold,
        items=tuple(items),
        filtered_dependencies=tuple(dep.name for dep in filtered_dependencies),
    )


def _expand_to_frontier(
    name: str,
    reuse_counts: Counter[str],
    graph: dict[str, set[str]],
    threshold: int,
    redundant_raw_names: set[str],
) -> list[str]:
    stack = [name]
    seen: set[str] = set()
    frontier: list[str] = []
    while stack:
        current = stack.pop()
        if current in seen or current in redundant_raw_names:
            continue
        seen.add(current)
        children = graph.get(current, set())
        if reuse_counts.get(current, 0) >= threshold or not children:
            frontier.append(current)
        else:
            stack.extend(sorted(children))
    return frontier
