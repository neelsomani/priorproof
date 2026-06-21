from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .data.io import read_json
from .data.models import DeclarationRecord


@dataclass(frozen=True)
class ModuleScope:
    name: str
    target_module_prefixes: tuple[str, ...]
    support_module_prefixes: tuple[str, ...] = ()
    excluded_module_prefixes: tuple[str, ...] = ()
    description: str = ""

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "ModuleScope":
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            target_module_prefixes=tuple(str(item) for item in data.get("target_module_prefixes", [])),
            support_module_prefixes=tuple(str(item) for item in data.get("support_module_prefixes", [])),
            excluded_module_prefixes=tuple(str(item) for item in data.get("excluded_module_prefixes", [])),
        )

    @property
    def corpus_module_prefixes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.target_module_prefixes, *self.support_module_prefixes)))

    def role_for_module(self, module: str) -> str | None:
        if starts_with_any(module, self.excluded_module_prefixes):
            return None
        if starts_with_any(module, self.target_module_prefixes):
            return "target"
        if starts_with_any(module, self.support_module_prefixes):
            return "support"
        return None


def load_scope(path: str | Path) -> ModuleScope:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError("scope config must contain a JSON object")
    scope = ModuleScope.from_json(data)
    if not scope.target_module_prefixes:
        raise ValueError("scope config must define at least one target_module_prefix")
    return scope


def filter_records_by_scope(
    records: Iterable[DeclarationRecord],
    scope: ModuleScope,
) -> tuple[list[DeclarationRecord], list[DeclarationRecord], list[DeclarationRecord]]:
    corpus: list[DeclarationRecord] = []
    targets: list[DeclarationRecord] = []
    support: list[DeclarationRecord] = []
    for record in records:
        role = scope.role_for_module(record.module)
        if role is None:
            continue
        corpus.append(record)
        if role == "target":
            targets.append(record)
        else:
            support.append(record)
    return corpus, targets, support


def scope_report(records: Iterable[DeclarationRecord], scope: ModuleScope) -> dict[str, object]:
    corpus, targets, support = filter_records_by_scope(records, scope)
    roles_by_name = {record.name: scope.role_for_module(record.module) for record in corpus}
    target_prefix_counts = prefix_counts(targets, scope.target_module_prefixes)
    support_prefix_counts = prefix_counts(support, scope.support_module_prefixes)
    return {
        "scope": scope.name,
        "description": scope.description,
        "target_module_prefixes": list(scope.target_module_prefixes),
        "support_module_prefixes": list(scope.support_module_prefixes),
        "corpus_declaration_count": len(corpus),
        "target_declaration_count": len(targets),
        "support_declaration_count": len(support),
        "target_modules": Counter(record.module for record in targets).most_common(),
        "support_modules": Counter(record.module for record in support).most_common(),
        "target_quarters": Counter(quarter(record.proof_date.isoformat()) for record in targets).most_common(),
        "target_prefix_counts": target_prefix_counts,
        "support_prefix_counts": support_prefix_counts,
        "dependency_audit": dependency_audit(targets, scope, roles_by_name),
    }


def dependency_audit(
    targets: Iterable[DeclarationRecord],
    scope: ModuleScope,
    roles_by_name: dict[str, str | None],
) -> dict[str, object]:
    targets = list(targets)
    role_counts: Counter[str] = Counter()
    scoped_role_counts: Counter[str] = Counter()
    declarations_with_scoped_dependency = 0
    declarations_with_target_dependency = 0
    declarations_with_support_dependency = 0
    scoped_dependency_total = 0
    target_dependency_modules: Counter[str] = Counter()
    support_dependency_modules: Counter[str] = Counter()
    prefix_cross_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in targets:
        seen_roles: set[str] = set()
        source_prefix = matched_prefix(record.module, scope.target_module_prefixes) or record.module
        for dependency in record.dependencies:
            role = dependency_role(dependency.name, dependency.module, scope, roles_by_name)
            role_counts[role] += 1
            if role in {"target", "support"}:
                scoped_role_counts[role] += 1
                scoped_dependency_total += 1
                seen_roles.add(role)
                target_prefix = matched_prefix(
                    dependency.module,
                    scope.target_module_prefixes if role == "target" else scope.support_module_prefixes,
                ) or dependency.module
                prefix_cross_counts[source_prefix][target_prefix] += 1
                if role == "target":
                    target_dependency_modules[dependency.module] += 1
                else:
                    support_dependency_modules[dependency.module] += 1
        if seen_roles:
            declarations_with_scoped_dependency += 1
        if "target" in seen_roles:
            declarations_with_target_dependency += 1
        if "support" in seen_roles:
            declarations_with_support_dependency += 1
    dependency_total = sum(role_counts.values())
    return {
        "target_declaration_count": len(targets),
        "dependency_reference_count": dependency_total,
        "dependency_reference_role_counts": dict(sorted(role_counts.items())),
        "scoped_dependency_reference_count": scoped_dependency_total,
        "scoped_dependency_reference_role_counts": dict(sorted(scoped_role_counts.items())),
        "mean_scoped_dependencies_per_target": scoped_dependency_total / len(targets) if targets else 0.0,
        "target_declarations_with_scoped_dependency": declarations_with_scoped_dependency,
        "target_declarations_with_scoped_dependency_rate": declarations_with_scoped_dependency / len(targets)
        if targets
        else 0.0,
        "target_declarations_with_target_dependency": declarations_with_target_dependency,
        "target_declarations_with_support_dependency": declarations_with_support_dependency,
        "top_target_dependency_modules": target_dependency_modules.most_common(25),
        "top_support_dependency_modules": support_dependency_modules.most_common(25),
        "target_prefix_dependency_matrix": {
            source: counts.most_common() for source, counts in sorted(prefix_cross_counts.items())
        },
    }


def dependency_role(
    dependency_name: str,
    dependency_module: str,
    scope: ModuleScope,
    roles_by_name: dict[str, str | None],
) -> str:
    if dependency_name in roles_by_name and roles_by_name[dependency_name]:
        return str(roles_by_name[dependency_name])
    role = scope.role_for_module(dependency_module)
    if role:
        return role
    if dependency_module.startswith(("Init", "Lean", "Std")):
        return "core"
    return "out_of_scope"


def prefix_counts(records: Iterable[DeclarationRecord], prefixes: tuple[str, ...]) -> list[list[object]]:
    counts: Counter[str] = Counter()
    for record in records:
        counts[matched_prefix(record.module, prefixes) or record.module] += 1
    return [[prefix, count] for prefix, count in counts.most_common()]


def matched_prefix(module: str, prefixes: Iterable[str]) -> str | None:
    matches = [prefix for prefix in prefixes if module.startswith(prefix)]
    if not matches:
        return None
    return max(matches, key=len)


def quarter(value: str) -> str:
    year = int(value[:4])
    month = int(value[5:7])
    return f"{year}Q{((month - 1) // 3) + 1}"


def starts_with_any(value: str, prefixes: Iterable[str]) -> bool:
    return any(value.startswith(prefix) for prefix in prefixes)
