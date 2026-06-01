from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..data.models import Dependency


@dataclass(frozen=True)
class Family:
    name: str
    depth: int
    support: int


def module_area(module: str) -> str:
    parts = [part for part in module.split(".") if part]
    if not parts:
        return "global"
    if parts[0] == "Mathlib" and len(parts) >= 2:
        return ".".join(parts[:2])
    return parts[0]


def namespace_parent(namespace: str) -> str:
    parts = [part for part in namespace.split(".") if part]
    if len(parts) <= 1:
        return namespace or "global"
    return ".".join(parts[:-1])


def candidate_families(dep: Dependency) -> tuple[str, ...]:
    namespace = dep.namespace or (dep.name.rsplit(".", 1)[0] if "." in dep.name else "")
    module = dep.module
    return (
        f"decl:{dep.name}",
        f"namespace:{namespace or 'global'}",
        f"namespace:{namespace_parent(namespace)}",
        f"module:{module or 'global'}",
        f"area:{module_area(module)}",
        "global",
    )


def family_supports(dependencies: list[Dependency]) -> Counter[str]:
    supports: Counter[str] = Counter()
    for dep in dependencies:
        for family in set(candidate_families(dep)):
            supports[family] += 1
    return supports


def choose_family(dep: Dependency, supports: Counter[str], min_support: int) -> Family:
    for depth, family in enumerate(candidate_families(dep)):
        support = supports.get(family, 0)
        if support >= min_support:
            return Family(family, depth, support)
    return Family("global", len(candidate_families(dep)) - 1, supports.get("global", 0))
