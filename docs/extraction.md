# Extraction Implementation

Extraction is split into two layers:

- Lean-facing proof-term extraction in `src/priorproof/extraction/proof_term.py` and orchestration in `src/priorproof/extraction/snapshots.py`.
- Corpus construction from normalized declaration JSONL in `src/priorproof/corpus/snapshots.py` and `src/priorproof/corpus/pipeline.py`.

The default extractor runs Lean inside each detached Mathlib worktree, imports Mathlib, iterates theorem declarations in Lean's environment, and records constants from each theorem's elaborated proof value. That is the corpus path used by the metric. The source scanner is retained only for plumbing smoke checks.

Install the package before using the commands below:

```bash
python3 -m pip install -e ".[dev]"
```

The proof-term extractor also requires Lean/Lake on `PATH`, using the version pinned by Mathlib's `lean-toolchain`. Install Lean through elan if `lake --version` fails.

## Snapshot Manifest

Create a manifest from an explicit commit map:

```bash
priorproof-make-snapshot-manifest \
  --commits configs/snapshot_commits.example.json \
  --mathlib-repo external/mathlib4 \
  --out artifacts/extraction/manifest.json
```

Each manifest item has:

- `snapshot_id`: usually `YYYYQn`.
- `start_date`: cutoff date for the snapshot.
- `commit`: Mathlib commit frozen at that cutoff. Use `"auto"` with `--mathlib-repo` to resolve the latest local commit before the snapshot date.

## Extraction Orchestration

Run the proof-term extractor:

```bash
priorproof-extract-declarations \
  --manifest artifacts/extraction/manifest.json \
  --mathlib-repo external/mathlib4 \
  --worktrees-dir artifacts/extraction/worktrees \
  --raw-dir artifacts/extraction/raw \
  --normalized-dir artifacts/extraction/normalized \
  --out-declarations data/declarations.jsonl \
  --out-snapshots artifacts/corpus/snapshots.json \
  --report artifacts/extraction/report.json \
  --backend proof-term \
  --adapter priorproof \
  --execute \
  --strict-raw
```

Use `--import` and `--module-prefix` to narrow extraction to a Mathlib area during development. Both options are repeatable and default to `Mathlib`.

Run the direct extractor for one checkout:

```bash
priorproof-proof-term-extract \
  --repo external/mathlib4 \
  --out artifacts/extraction/raw/current.jsonl \
  --commit "$(git -C external/mathlib4 rev-parse HEAD)" \
  --proof-date "$(git -C external/mathlib4 show -s --format=%cs HEAD)" \
  --import Mathlib.Topology.Basic \
  --module-prefix Mathlib.Topology
```

Run with a third-party extractor command template:

```bash
priorproof-extract-declarations \
  --manifest artifacts/extraction/manifest.json \
  --mathlib-repo external/mathlib4 \
  --worktrees-dir artifacts/extraction/worktrees \
  --raw-dir artifacts/extraction/raw \
  --normalized-dir artifacts/extraction/normalized \
  --out-declarations data/declarations.jsonl \
  --out-snapshots artifacts/corpus/snapshots.json \
  --report artifacts/extraction/report.json \
  --backend command \
  --adapter auto \
  --extractor-command "python3 /path/to/extractor.py --repo {worktree} --out {raw_path}" \
  --execute \
  --strict-raw
```

Run the source scanner only for smoke checks:

```bash
priorproof-extract-declarations \
  --manifest artifacts/extraction/manifest.json \
  --mathlib-repo external/mathlib4 \
  --worktrees-dir artifacts/extraction/worktrees \
  --raw-dir artifacts/extraction/raw \
  --normalized-dir artifacts/extraction/normalized \
  --out-declarations data/declarations.jsonl \
  --out-snapshots artifacts/corpus/snapshots.json \
  --report artifacts/extraction/report.json \
  --backend source-scan \
  --adapter auto \
  --execute \
  --strict-raw
```

Available template variables:

- `{repo}`: source Mathlib repo path.
- `{worktree}`: detached worktree for the snapshot commit.
- `{commit}`: snapshot commit.
- `{snapshot_id}`: snapshot id.
- `{start_date}`: snapshot start date.
- `{raw_path}`: expected raw extractor output path.
- `{normalized_path}`: normalized JSONL output path.

Without `--execute`, the command writes a report containing planned git and extractor commands, and normalizes any raw files that already exist.

## Supported Raw Adapters

- `priorproof`: raw rows already match `docs/data_schema.md`.
- `generic`: flexible field aliases such as `name`, `statement`, `dependencies`, `dependency_edges`, and `subterms`.
- `leandojo`: flexible LeanDojo-style aliases such as nested `theorem.full_name`, `theorem.file_path`, and `premises`.
- `ntp`: flexible ntp-toolkit-style aliases such as `decl_name`, `used_premises`, and `constants`.
- `auto`: infer one of the flexible adapters from row keys.

## Corpus Artifacts

After extraction, build corpus artifacts and metric footprints:

```bash
priorproof-build-corpus \
  --declarations data/declarations.jsonl \
  --out-dir artifacts/corpus \
  --thresholds 3,5,8,13
```

This writes:

- `snapshots.json`
- `density.json`
- `footprints_t{threshold}.jsonl`
