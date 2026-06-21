from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol, Sequence

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
        vectors = encode_many(encoder, records)
        self._index = VectorIndex(records, vectors)
        self.vectors = [] if self._index.is_accelerated else vectors

    def query(self, target: DeclarationRecord, k: int = 32) -> list[RetrievalHit]:
        target_vector = self.encoder.encode(target.statement)
        return self._index.query(target_vector, target.name, k)


class VectorIndex:
    def __init__(self, records: list[DeclarationRecord], vectors: list[list[float]]) -> None:
        self.records = records
        self.vectors = vectors
        self._matrix = None
        self.is_accelerated = False
        if not records:
            return
        try:
            import numpy as np
        except ImportError:
            return
        matrix = np.asarray(vectors, dtype="float32")
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            return
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.maximum(norms, 1e-12)
        self._matrix = matrix
        self.vectors = []
        self.is_accelerated = True

    def query(self, target_vector: list[float], target_name: str, k: int) -> list[RetrievalHit]:
        if not self.records:
            return []
        if self._matrix is not None:
            return self._query_numpy(target_vector, target_name, k)
        return self._query_python(target_vector, target_name, k)

    def _query_numpy(self, target_vector: list[float], target_name: str, k: int) -> list[RetrievalHit]:
        import numpy as np

        query = np.asarray([target_vector], dtype="float32")
        query = query / np.maximum(np.linalg.norm(query, axis=1, keepdims=True), 1e-12)
        scores = self._matrix @ query[0]
        limit = min(len(self.records), k + 1)
        if limit < len(scores):
            indices = np.argpartition(scores, -limit)[-limit:]
            indices = indices[np.argsort(scores[indices])[::-1]]
        else:
            indices = np.argsort(scores)[::-1]
        hits = []
        for idx in indices:
            record = self.records[int(idx)]
            if record.name == target_name:
                continue
            hits.append(
                RetrievalHit(
                    name=record.name,
                    score=float(scores[int(idx)]),
                    module=record.module,
                    namespace=record.namespace,
                )
            )
            if len(hits) >= k:
                break
        return hits

    def _query_python(self, target_vector: list[float], target_name: str, k: int) -> list[RetrievalHit]:
        hits = [
            RetrievalHit(
                name=record.name,
                score=cosine(target_vector, vector),
                module=record.module,
                namespace=record.namespace,
            )
            for record, vector in zip(self.records, self.vectors)
            if record.name != target_name
        ]
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:k]


def encode_many(encoder: StatementEmbeddingModel, records: Sequence[DeclarationRecord | str]) -> list[list[float]]:
    batch_encoder = getattr(encoder, "encode_many", None)
    if batch_encoder is not None:
        return batch_encoder(records)
    return [encoder.encode(record) for record in records]


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
