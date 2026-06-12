# Learned Statement Encoder

The retrieval model is a contrastively fine-tuned transformer statement encoder:

- Input at inference: Lean theorem statement text only.
- Output: fixed-dimensional embedding for retrieval.
- Training signal: proof-derived positive pairs and mechanical hard negatives mined from the pre-time corpus.
- Training data discipline: examples must come only from proofs available before the target time bin.

## Contrastive Examples

Build training examples from declarations and footprints:

```bash
priorproof-build-contrastive-data \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --out-examples artifacts/encoder/contrastive_examples_t5.jsonl \
  --out-report artifacts/encoder/contrastive_report_t5.json
```

Positive signals:

- Shared premise families in proof footprints.
- Shared downstream users.
- Theorem and major proof dependency.
- Same namespace/file with high symbol overlap.

Hard negative signals:

- Same namespace with no dependency-family overlap.
- Same head symbols but different theorem shape.
- Different module with accidental lexical similarity.

## Training

Install ML dependencies only when training the neural encoder:

```bash
python3 -m pip install -e ".[ml]"
```

Fine-tune a base sentence-transformer checkpoint:

```bash
priorproof-train-neural-encoder \
  --declarations data/declarations.jsonl \
  --examples artifacts/encoder/contrastive_examples_t5.jsonl \
  --base-model sentence-transformers/all-MiniLM-L6-v2 \
  --out-dir artifacts/encoder/neural_t5 \
  --epochs 1 \
  --batch-size 64
```

This command is GPU-appropriate. A 24GB consumer GPU or a single A100-class device is the intended scale for the small transformer fine-tunes.

## Time Slicing

Two valid regimes:

- Frozen-early encoder: train only on the earliest slice, then validate that neighbor sets are close to per-bin encoders on a sample.
- Per-snapshot encoders: train one encoder per time bin using only pre-bin positives.

Final reported results should use the frozen-early encoder only if the neighbor-stability check passes. Otherwise use per-snapshot encoders.
