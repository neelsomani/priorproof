from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from ..data.models import DeclarationRecord, Footprint
from .text import statement_shape, tokenize_statement


@dataclass(frozen=True)
class PairMiningConfig:
    shared_family_min: int = 2
    downstream_user_min: int = 2
    namespace_symbol_jaccard_min: float = 0.35
    lexical_negative_jaccard_min: float = 0.25
    max_pairs_per_signal: int = 250_000
    hard_negatives_per_pair: int = 4


@dataclass(frozen=True)
class StatementPair:
    left: str
    right: str
    signal: str
    strength: float

    def to_json(self) -> dict[str, object]:
        return {
            "left": self.left,
            "right": self.right,
            "signal": self.signal,
            "strength": self.strength,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "StatementPair":
        return cls(
            left=str(data["left"]),
            right=str(data["right"]),
            signal=str(data["signal"]),
            strength=float(data.get("strength", 1.0)),
        )


@dataclass(frozen=True)
class ContrastiveExample:
    anchor: str
    positive: str
    positive_signal: str
    hard_negatives: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "anchor": self.anchor,
            "positive": self.positive,
            "positive_signal": self.positive_signal,
            "hard_negatives": list(self.hard_negatives),
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "ContrastiveExample":
        return cls(
            anchor=str(data["anchor"]),
            positive=str(data["positive"]),
            positive_signal=str(data.get("positive_signal", "")),
            hard_negatives=tuple(str(name) for name in data.get("hard_negatives", [])),
        )


def mine_contrastive_examples(
    records: list[DeclarationRecord],
    footprints: list[Footprint],
    config: PairMiningConfig | None = None,
) -> list[ContrastiveExample]:
    config = config or PairMiningConfig()
    positives = mine_positive_pairs(records, footprints, config)
    negatives = mine_hard_negative_pairs(records, footprints, config)
    negatives_by_anchor: dict[str, list[str]] = defaultdict(list)
    for pair in negatives:
        negatives_by_anchor[pair.left].append(pair.right)
        negatives_by_anchor[pair.right].append(pair.left)

    examples: list[ContrastiveExample] = []
    for pair in positives:
        hard_negatives = tuple(sorted(set(negatives_by_anchor.get(pair.left, [])))[: config.hard_negatives_per_pair])
        examples.append(
            ContrastiveExample(
                anchor=pair.left,
                positive=pair.right,
                positive_signal=pair.signal,
                hard_negatives=hard_negatives,
            )
        )
    return examples


def mine_positive_pairs(
    records: list[DeclarationRecord],
    footprints: list[Footprint],
    config: PairMiningConfig | None = None,
) -> list[StatementPair]:
    config = config or PairMiningConfig()
    by_name = {record.name: record for record in records}
    family_sets = footprint_family_sets(footprints)
    pairs: list[StatementPair] = []
    seen: set[tuple[str, str, str]] = set()

    for left, right in combinations(sorted(family_sets), 2):
        overlap = family_sets[left] & family_sets[right]
        if len(overlap) >= config.shared_family_min:
            add_pair(pairs, seen, left, right, "shared_premise_families", float(len(overlap)))
            if len(pairs) >= config.max_pairs_per_signal:
                break

    downstream = downstream_users(records)
    downstream_positive_count = 0
    for left, right in combinations(sorted(by_name), 2):
        shared_users = downstream.get(left, set()) & downstream.get(right, set())
        if len(shared_users) >= config.downstream_user_min:
            add_pair(pairs, seen, left, right, "shared_downstream_users", float(len(shared_users)))
            downstream_positive_count += 1
            if downstream_positive_count >= config.max_pairs_per_signal:
                break

    dependency_positive_count = 0
    for record in records:
        for dep in record.dependencies:
            if dep.name in by_name:
                add_pair(pairs, seen, record.name, dep.name, "major_dependency", 1.0)
                dependency_positive_count += 1
                if dependency_positive_count >= config.max_pairs_per_signal:
                    break

    namespace_positive_count = 0
    for left, right in combinations(sorted(by_name), 2):
        left_record = by_name[left]
        right_record = by_name[right]
        if left_record.namespace != right_record.namespace:
            continue
        similarity = token_jaccard(left_record.statement, right_record.statement)
        if similarity >= config.namespace_symbol_jaccard_min:
            add_pair(pairs, seen, left, right, "namespace_symbol_overlap", similarity)
            namespace_positive_count += 1
            if namespace_positive_count >= config.max_pairs_per_signal:
                break

    return pairs


def mine_hard_negative_pairs(
    records: list[DeclarationRecord],
    footprints: list[Footprint],
    config: PairMiningConfig | None = None,
) -> list[StatementPair]:
    config = config or PairMiningConfig()
    by_name = {record.name: record for record in records}
    family_sets = footprint_family_sets(footprints)
    pairs: list[StatementPair] = []
    seen: set[tuple[str, str, str]] = set()

    for left, right in combinations(sorted(by_name), 2):
        left_record = by_name[left]
        right_record = by_name[right]
        overlap = family_sets.get(left, set()) & family_sets.get(right, set())
        if left_record.namespace == right_record.namespace and not overlap:
            add_pair(pairs, seen, left, right, "same_namespace_no_dependency_overlap", 1.0)
            continue
        if statement_head(left_record.statement) == statement_head(right_record.statement):
            if statement_shape(left_record.statement) != statement_shape(right_record.statement):
                add_pair(pairs, seen, left, right, "same_head_different_shape", 1.0)
                continue
        lexical = token_jaccard(left_record.statement, right_record.statement)
        if left_record.module != right_record.module and lexical >= config.lexical_negative_jaccard_min:
            add_pair(pairs, seen, left, right, "cross_module_lexical_false_friend", lexical)
    return pairs


def footprint_family_sets(footprints: Iterable[Footprint]) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    for footprint in footprints:
        output[footprint.declaration] = {item.family for item in footprint.items}
    return output


def downstream_users(records: Iterable[DeclarationRecord]) -> dict[str, set[str]]:
    users: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for dep in record.dependencies:
            users[dep.name].add(record.name)
    return dict(users)


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(tokenize_statement(left))
    right_tokens = set(tokenize_statement(right))
    if not left_tokens and not right_tokens:
        return 1.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def statement_head(statement: str) -> str:
    tokens = [token for token in tokenize_statement(statement) if token.isidentifier()]
    return tokens[0] if tokens else ""


def signal_counts(pairs: Iterable[StatementPair] | Iterable[ContrastiveExample]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in pairs:
        signal = item.signal if isinstance(item, StatementPair) else item.positive_signal
        counts[signal] += 1
    return counts


def add_pair(
    pairs: list[StatementPair],
    seen: set[tuple[str, str, str]],
    left: str,
    right: str,
    signal: str,
    strength: float,
) -> None:
    if left == right:
        return
    ordered = tuple(sorted((left, right)))
    key = (ordered[0], ordered[1], signal)
    if key in seen:
        return
    seen.add(key)
    pairs.append(StatementPair(ordered[0], ordered[1], signal, strength))
