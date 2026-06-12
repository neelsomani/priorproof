from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..data.models import DeclarationRecord
from .contrastive import ContrastiveExample


@dataclass(frozen=True)
class NeuralEncoderConfig:
    base_model: str
    output_dir: str
    epochs: int = 1
    batch_size: int = 64
    learning_rate: float = 2e-5
    warmup_ratio: float = 0.1
    max_seq_length: int = 256
    use_hard_negatives: bool = True


class NeuralStatementEncoder:
    """Sentence-transformer statement encoder.

    This class is intentionally a thin adapter. Heavy ML dependencies are lazy
    imports so the rest of PriorProof remains installable and testable without
    GPU/transformer packages.
    """

    def __init__(self, model_dir: str | Path) -> None:
        SentenceTransformer = import_sentence_transformer()
        self.model = SentenceTransformer(str(model_dir))

    def encode(self, record: DeclarationRecord | str) -> list[float]:
        statement = record.statement if isinstance(record, DeclarationRecord) else record
        vector = self.model.encode([statement], normalize_embeddings=True)[0]
        return [float(value) for value in vector]


def load_neural_statement_encoder(path: str | Path) -> NeuralStatementEncoder:
    source = Path(path)
    if not source.is_dir():
        raise ValueError(f"Expected a trained neural encoder directory, got: {source}")
    return NeuralStatementEncoder(source)


def train_neural_encoder(
    records: list[DeclarationRecord],
    examples: list[ContrastiveExample],
    config: NeuralEncoderConfig,
) -> None:
    SentenceTransformer, InputExample, losses = import_training_objects()
    record_by_name = {record.name: record for record in records}
    model = SentenceTransformer(config.base_model)
    model.max_seq_length = config.max_seq_length

    train_examples = []
    for example in examples:
        anchor = record_by_name.get(example.anchor)
        positive = record_by_name.get(example.positive)
        if anchor is None or positive is None:
            continue
        if config.use_hard_negatives and example.hard_negatives:
            for negative_name in example.hard_negatives:
                negative = record_by_name.get(negative_name)
                if negative is None:
                    continue
                train_examples.append(InputExample(texts=[anchor.statement, positive.statement, negative.statement]))
        else:
            train_examples.append(InputExample(texts=[anchor.statement, positive.statement]))

    if not train_examples:
        raise ValueError("No trainable contrastive examples were produced")

    loader = import_torch_dataloader()(train_examples, shuffle=True, batch_size=config.batch_size)
    loss = losses.MultipleNegativesRankingLoss(model)
    warmup_steps = int(len(loader) * config.epochs * config.warmup_ratio)
    model.fit(
        train_objectives=[(loader, loss)],
        epochs=config.epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": config.learning_rate},
        output_path=config.output_dir,
    )
    write_training_metadata(config, examples)


def write_training_metadata(config: NeuralEncoderConfig, examples: Iterable[ContrastiveExample]) -> None:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "base_model": config.base_model,
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "learning_rate": config.learning_rate,
        "warmup_ratio": config.warmup_ratio,
        "max_seq_length": config.max_seq_length,
        "use_hard_negatives": config.use_hard_negatives,
        "example_count": sum(1 for _ in examples),
    }
    (output_dir / "priorproof_training.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def import_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError("Install ML dependencies with `python3 -m pip install -e '.[ml]'`.") from exc
    return SentenceTransformer


def import_training_objects():
    try:
        from sentence_transformers import InputExample, SentenceTransformer, losses
    except ImportError as exc:
        raise ImportError("Install ML dependencies with `python3 -m pip install -e '.[ml]'`.") from exc
    return SentenceTransformer, InputExample, losses


def import_torch_dataloader():
    try:
        from torch.utils.data import DataLoader
    except ImportError as exc:
        raise ImportError("Install ML dependencies with `python3 -m pip install -e '.[ml]'`.") from exc
    return DataLoader
