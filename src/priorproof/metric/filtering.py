from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from ..data.models import Dependency


DEFAULT_KIND_DENYLIST = frozenset(
    {
        "binder",
        "coercion",
        "implementationDetail",
        "notation",
        "projection",
        "recursor",
        "simpGenerated",
        "typeclass",
    }
)

DEFAULT_NAME_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"(^|\.)(_private|inst|mk|rec|casesOn|noConfusion|below|brecOn)(\.|$)",
        r"(^|\.)(OfNat|OfScientific|Nat\.succ|Eq\.mp|Eq\.mpr|HEq|propext)$",
        r"(^|\.)(ite|dite|Decidable|Subsingleton|Inhabited)(\.|$)",
        r"(^|\.)(simp|norm_num|ring_nf|omega|linarith)(\.|$)",
    )
)


@dataclass(frozen=True)
class DependencyFilter:
    kind_denylist: frozenset[str] = DEFAULT_KIND_DENYLIST
    name_patterns: tuple[re.Pattern[str], ...] = DEFAULT_NAME_PATTERNS
    module_denylist: frozenset[str] = frozenset({"Init", "Lean", "Std.Tactic"})
    keep_explicit: frozenset[str] = field(default_factory=frozenset)

    def keep(self, dep: Dependency) -> bool:
        if dep.name in self.keep_explicit:
            return True
        if dep.kind in self.kind_denylist:
            return False
        if dep.module in self.module_denylist:
            return False
        return not any(pattern.search(dep.name) for pattern in self.name_patterns)

    def apply(self, dependencies: Iterable[Dependency]) -> tuple[Dependency, ...]:
        seen: set[str] = set()
        kept: list[Dependency] = []
        for dep in dependencies:
            if dep.name in seen or not self.keep(dep):
                continue
            seen.add(dep.name)
            kept.append(dep)
        return tuple(kept)


def filter_sensitivity_grid() -> list[DependencyFilter]:
    """Small deterministic filter variants for sensitivity studies."""

    return [
        DependencyFilter(),
        DependencyFilter(kind_denylist=DEFAULT_KIND_DENYLIST - {"typeclass"}),
        DependencyFilter(module_denylist=frozenset({"Lean"})),
        DependencyFilter(name_patterns=DEFAULT_NAME_PATTERNS[:-1]),
    ]

