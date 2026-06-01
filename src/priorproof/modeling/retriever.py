from __future__ import annotations

from dataclasses import dataclass

from .encoder import StatementEncoder, cosine
from ..data.models import DeclarationRecord


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
    def __init__(self, encoder: StatementEncoder, records: list[DeclarationRecord]) -> None:
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

