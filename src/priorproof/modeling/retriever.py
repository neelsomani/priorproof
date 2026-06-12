from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol

from ..data.models import DeclarationRecord


class StatementEmbeddingModel(Protocol):
    def encode(self, record: DeclarationRecord | str) -> list[float]:
        ...


@dataclass(frozen=True)
class RetrievalHit:
    name: str
    score: float
    module: str
    namespace: str

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "score": self.score,
            "module": self.module,
            "namespace": self.namespace,
        }


class StatementRetriever:
    def __init__(self, encoder: StatementEmbeddingModel, records: list[DeclarationRecord]) -> None:
        self.encoder = encoder
        self.records = records
        self.vectors = {record.name: encoder.encode(record) for record in records}

    def query(self, target: DeclarationRecord, k: int = 32) -> list[RetrievalHit]:
        target_vector = self.encoder.encode(target.statement)
        hits = [
            RetrievalHit(
                name=record.name,
                score=cosine(target_vector, self.vectors[record.name]),
                module=record.module,
                namespace=record.namespace,
            )
            for record in self.records
            if record.name != target.name
        ]
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:k]


def neighbor_overlap(lhs: list[RetrievalHit], rhs: list[RetrievalHit], k: int | None = None) -> float:
    if k is None:
        k = min(len(lhs), len(rhs))
    left = {hit.name for hit in lhs[:k]}
    right = {hit.name for hit in rhs[:k]}
    if not left and not right:
        return 1.0
    return len(left & right) / max(1, len(left | right))


def cosine(lhs: list[float], rhs: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(lhs, rhs))
    lhs_norm = sqrt(sum(value * value for value in lhs))
    rhs_norm = sqrt(sum(value * value for value in rhs))
    if lhs_norm == 0.0 or rhs_norm == 0.0:
        return 0.0
    return numerator / (lhs_norm * rhs_norm)
