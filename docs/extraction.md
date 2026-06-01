# Extraction Implementation

Extraction is split into two layers:

- Lean-facing extraction orchestration in `src/priorproof/extraction/snapshots.py`.
- Corpus construction from normalized declaration JSONL in `src/priorproof/corpus/snapshots.py` and `src/priorproof/corpus/pipeline.py`.

The orchestration layer does not hard-code a single extractor. Instead, it prepares a detached Mathlib worktree for each snapshot commit, runs an extractor command template if provided, and normalizes the raw extractor output into the repository's declaration schema.

Install the package before using the commands below:

```bash
python3 -m pip install -e ".[dev]"
```

## Snapshot Manifest

Create a manifest from an explicit commit map:

```bash
priorproof-make-snapshot-manifest \
  --commits configs/snapshot_commits.example.json \
  --out artifacts/extraction/manifest.json
```

Each manifest item has:

- `snapshot_id`: usually `YYYYQn`.
- `start_date`: cutoff date for the snapshot.
- `commit`: Mathlib commit frozen at that cutoff.

## Extraction Orchestration

Run with an extractor command template:

```bash
priorproof-extract-declarations \
  --manifest artifacts/extraction/manifest.json \
  --mathlib-repo /path/to/mathlib4 \
  --worktrees-dir artifacts/extraction/worktrees \
  --raw-dir artifacts/extraction/raw \
  --normalized-dir artifacts/extraction/normalized \
  --out-declarations data/declarations.jsonl \
  --out-snapshots artifacts/corpus/snapshots.json \
  --report artifacts/extraction/report.json \
  --adapter auto \
  --extractor-command "python3 /path/to/extractor.py --repo {worktree} --out {raw_path}" \
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
