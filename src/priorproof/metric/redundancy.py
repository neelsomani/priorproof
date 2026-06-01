from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from ..data.models import DeclarationRecord


_SPACE_RE = re.compile(r"\s+")
_IMPLICIT_RE = re.compile(r"\{[^{}]*\}")
_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_'.]*)\b")


@dataclass(frozen=True)
class RedundancyHit:
    subterm_id: str
    conclusion: str
    matched_declaration: str
    mode: str
    raw_dependencies: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "subterm_id": self.subterm_id,
            "conclusion": self.conclusion,
            "matched_declaration": self.matched_declaration,
            "mode": self.mode,
            "raw_dependencies": list(self.raw_dependencies),
        }


def canonical_statement(statement: str) -> str:
    """A deliberately conservative trivial-equivalence key.

    This catches formatting, implicit-argument, and alpha-ish binder changes. It
    is not a replacement for Lean elaboration; records that need stronger
    equivalence should include extractor-produced normalized conclusions.
    """

    text = statement.strip()
    text = _IMPLICIT_RE.sub(" ", text)
    text = text.replace("↔", " iff ").replace("→", " -> ").replace("∀", " forall ")
    text = _SPACE_RE.sub(" ", text)
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        word = match.group(1)
        if len(word) == 1 and word.islower():
            replacements.setdefault(word, f"v{len(replacements)}")
            return replacements[word]
        return word

    return _NAME_RE.sub(replace, text).strip()


def build_statement_index(records: Iterable[DeclarationRecord]) -> dict[str, list[DeclarationRecord]]:
    index: dict[str, list[DeclarationRecord]] = defaultdict(list)
    for record in records:
        key = canonical_statement(record.statement)
        index[key].append(record)
    return dict(index)


def detect_redundant_subterms(
    target: DeclarationRecord,
    pre_t_records: Iterable[DeclarationRecord],
) -> tuple[RedundancyHit, ...]:
    index = build_statement_index(pre_t_records)
    hits: list[RedundancyHit] = []
    for idx, subterm in enumerate(target.subterms):
        conclusion = str(subterm.get("conclusion") or subterm.get("normalized_conclusion") or "")
        if not conclusion:
            continue
        normalized = str(subterm.get("normalized_conclusion") or canonical_statement(conclusion))
        candidates = index.get(normalized, [])
        if not candidates:
            continue
        matched = sorted(candidates, key=lambda item: item.proof_date)[0]
        mode = "normalized_statement" if subterm.get("normalized_conclusion") else "canonical_statement"
        hits.append(
            RedundancyHit(
                subterm_id=str(subterm.get("id", f"subterm:{idx}")),
                conclusion=conclusion,
                matched_declaration=matched.name,
                mode=mode,
                raw_dependencies=tuple(str(name) for name in subterm.get("dependencies", [])),
            )
        )
    return tuple(hits)


def exact_wrapper_flags(target: DeclarationRecord, pre_t_names: set[str]) -> tuple[RedundancyHit, ...]:
    hits: list[RedundancyHit] = []
    for idx, subterm in enumerate(target.subterms):
        exact = subterm.get("exact")
        if exact and exact in pre_t_names:
            hits.append(
                RedundancyHit(
                    subterm_id=str(subterm.get("id", f"subterm:{idx}")),
                    conclusion=str(subterm.get("conclusion", "")),
                    matched_declaration=str(exact),
                    mode="by_exact",
                    raw_dependencies=tuple(str(name) for name in subterm.get("dependencies", [])),
                )
            )
    return tuple(hits)

