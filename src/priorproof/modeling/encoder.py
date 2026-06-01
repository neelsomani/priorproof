from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from ..data.models import DeclarationRecord


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*|[0-9]+|[^\sA-Za-z0-9_]")


def tokenize_statement(statement: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(statement)]


@dataclass(frozen=True)
class EncoderConfig:
    dimensions: int = 512
    namespace_weight: float = 0.35
    module_weight: float = 0.25
    shape_weight: float = 0.4


class StatementEncoder:
    """A deterministic statement-only encoder with weak-label fitting.

    It uses hashed tf-idf features plus optional weak-label centroids. This is
    intentionally simple and serializable; neural encoders can later implement
    the same `encode` contract.
    """

    def __init__(
        self,
        config: EncoderConfig | None = None,
        idf: dict[str, float] | None = None,
        centroids: dict[str, list[float]] | None = None,
    ) -> None:
        self.config = config or EncoderConfig()
        self.idf = idf or {}
        self.centroids = centroids or {}

    def fit(self, records: Iterable[DeclarationRecord]) -> "StatementEncoder":
        records = list(records)
        doc_freq: Counter[str] = Counter()
        for record in records:
            doc_freq.update(set(tokenize_statement(record.statement)))
        total_docs = max(1, len(records))
        self.idf = {
            token: math.log((1 + total_docs) / (1 + freq)) + 1.0
            for token, freq in doc_freq.items()
        }
        centroids: dict[str, list[float]] = {}
        grouped: dict[str, list[list[float]]] = defaultdict(list)
        for record in records:
            base = self._encode_tokens(record.statement)
            grouped[f"namespace:{record.namespace}"].append(base)
            grouped[f"module:{record.module}"].append(base)
            grouped[f"shape:{statement_shape(record.statement)}"].append(base)
        for label, vectors in grouped.items():
            centroids[label] = normalize(mean_vector(vectors))
        self.centroids = centroids
        return self

    def encode(self, record: DeclarationRecord | str) -> list[float]:
        statement = record.statement if isinstance(record, DeclarationRecord) else record
        vector = self._encode_tokens(statement)
        if isinstance(record, DeclarationRecord):
            labels = [
                (f"namespace:{record.namespace}", self.config.namespace_weight),
                (f"module:{record.module}", self.config.module_weight),
                (f"shape:{statement_shape(record.statement)}", self.config.shape_weight),
            ]
            for label, weight in labels:
                centroid = self.centroids.get(label)
                if centroid:
                    vector = add_scaled(vector, centroid, weight)
        return normalize(vector)

    def _encode_tokens(self, statement: str) -> list[float]:
        vector = [0.0] * self.config.dimensions
        counts = Counter(tokenize_statement(statement))
        if not counts:
            return vector
        for token, count in counts.items():
            idx = stable_hash(token) % self.config.dimensions
            sign = 1.0 if stable_hash("sign:" + token) % 2 == 0 else -1.0
            vector[idx] += sign * (1.0 + math.log(count)) * self.idf.get(token, 1.0)
        return normalize(vector)

    def to_json(self) -> dict[str, object]:
        return {
            "config": {
                "dimensions": self.config.dimensions,
                "namespace_weight": self.config.namespace_weight,
                "module_weight": self.config.module_weight,
                "shape_weight": self.config.shape_weight,
            },
            "idf": self.idf,
            "centroids": self.centroids,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "StatementEncoder":
        config_data = dict(data.get("config", {}))
        config = EncoderConfig(
            dimensions=int(config_data.get("dimensions", 512)),
            namespace_weight=float(config_data.get("namespace_weight", 0.35)),
            module_weight=float(config_data.get("module_weight", 0.25)),
            shape_weight=float(config_data.get("shape_weight", 0.4)),
        )
        idf = {str(k): float(v) for k, v in dict(data.get("idf", {})).items()}
        centroids = {
            str(k): [float(x) for x in v]
            for k, v in dict(data.get("centroids", {})).items()
        }
        return cls(config=config, idf=idf, centroids=centroids)


def statement_shape(statement: str) -> str:
    tokens = tokenize_statement(statement)
    has_forall = any(token in {"forall", "∀"} for token in tokens)
    has_exists = any(token in {"exists", "∃"} for token in tokens)
    has_iff = any(token in {"iff", "↔"} for token in tokens)
    has_eq = "=" in tokens
    arrows = tokens.count("->") + tokens.count("→")
    return f"forall:{has_forall}|exists:{has_exists}|iff:{has_iff}|eq:{has_eq}|arrows:{min(arrows, 3)}"


def stable_hash(value: str) -> int:
    return int(hashlib.blake2b(value.encode("utf-8"), digest_size=8).hexdigest(), 16)


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    out = [0.0] * len(vectors[0])
    for vector in vectors:
        for idx, value in enumerate(vector):
            out[idx] += value
    return [value / len(vectors) for value in out]


def add_scaled(vector: list[float], other: list[float], weight: float) -> list[float]:
    if not other:
        return vector
    return [value + weight * other[idx] for idx, value in enumerate(vector)]


def cosine(lhs: list[float], rhs: list[float]) -> float:
    return sum(a * b for a, b in zip(lhs, rhs))

