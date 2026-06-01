from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import write_json
from priorproof.extraction.snapshots import (
    ExtractionResult,
    load_snapshot_manifest,
    merge_normalized_declarations,
    normalize_extractor_file,
    prepare_mathlib_worktree,
    render_command_template,
    run_extractor_command,
    snapshots_from_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lean/Mathlib extraction orchestration.")
    parser.add_argument("--manifest", required=True, help="JSON list of snapshot_id/start_date/commit records.")
    parser.add_argument("--mathlib-repo", required=True, help="Local Mathlib git repository.")
    parser.add_argument("--worktrees-dir", required=True, help="Directory for detached Mathlib worktrees.")
    parser.add_argument("--raw-dir", required=True, help="Directory containing or receiving raw extractor output.")
    parser.add_argument("--normalized-dir", required=True, help="Directory for normalized per-snapshot JSONL.")
    parser.add_argument("--out-declarations", required=True, help="Merged declaration JSONL output.")
    parser.add_argument("--out-snapshots", required=True, help="Snapshot JSON output with declaration names.")
    parser.add_argument("--report", required=True, help="Extraction report JSON.")
    parser.add_argument(
        "--extractor-command",
        help=(
            "Optional command template. Available variables: {worktree}, {repo}, {commit}, "
            "{snapshot_id}, {start_date}, {raw_path}, {normalized_path}."
        ),
    )
    parser.add_argument("--adapter", choices=("auto", "priorproof", "leandojo", "ntp", "generic"), default="auto")
    parser.add_argument("--raw-suffix", default=".jsonl", choices=(".jsonl", ".json"))
    parser.add_argument("--execute", action="store_true", help="Actually run git and extractor commands.")
    parser.add_argument(
        "--strict-raw",
        action="store_true",
        help="Fail if a raw extractor output file is missing. Useful after --execute runs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_snapshot_manifest(args.manifest)
    repo = Path(args.mathlib_repo)
    worktrees_dir = Path(args.worktrees_dir)
    raw_dir = Path(args.raw_dir)
    normalized_dir = Path(args.normalized_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    results: list[ExtractionResult] = []
    planned_commands: list[dict[str, object]] = []
    normalized_paths: list[Path] = []
    declarations_by_snapshot: dict[str, list[str]] = {}

    for snapshot in manifest:
        worktree = worktrees_dir / f"mathlib-{snapshot.snapshot_id}"
        raw_path = raw_dir / f"{snapshot.snapshot_id}{args.raw_suffix}"
        normalized_path = normalized_dir / f"{snapshot.snapshot_id}.jsonl"
        variables = {
            "repo": str(repo),
            "worktree": str(worktree),
            "commit": snapshot.commit,
            "snapshot_id": snapshot.snapshot_id,
            "start_date": snapshot.start_date.isoformat(),
            "raw_path": str(raw_path),
            "normalized_path": str(normalized_path),
        }
        git_plan = prepare_mathlib_worktree(repo, worktree, snapshot.commit, execute=args.execute)
        command_display = None
        if args.extractor_command:
            command = render_command_template(args.extractor_command, variables)
            command_display = command.display()
            run_extractor_command(command, execute=args.execute)
        planned_commands.append(
            {
                "snapshot_id": snapshot.snapshot_id,
                "commit": snapshot.commit,
                "worktree": str(worktree),
                "git_plan": git_plan,
                "extractor_command": command_display,
                "raw_path": str(raw_path),
                "normalized_path": str(normalized_path),
            }
        )
        if not raw_path.exists():
            if args.strict_raw:
                raise FileNotFoundError(f"Missing raw extractor output: {raw_path}")
            continue
        records = normalize_extractor_file(raw_path, normalized_path, adapter=args.adapter, snapshot=snapshot)
        normalized_paths.append(normalized_path)
        declarations_by_snapshot[snapshot.snapshot_id] = [record.name for record in records]
        results.append(
            ExtractionResult(
                snapshot_id=snapshot.snapshot_id,
                commit=snapshot.commit,
                raw_path=raw_path,
                normalized_path=normalized_path,
                declaration_count=len(records),
                command=command_display,
            )
        )

    merged = merge_normalized_declarations(normalized_paths, args.out_declarations) if normalized_paths else []
    snapshots = snapshots_from_manifest(manifest, declarations_by_snapshot)
    write_json(args.out_snapshots, [snapshot.to_json() for snapshot in snapshots])
    write_json(
        args.report,
        {
            "execute": args.execute,
            "adapter": args.adapter,
            "snapshot_count": len(manifest),
            "normalized_snapshot_count": len(results),
            "merged_declaration_count": len(merged),
            "planned_commands": planned_commands,
            "results": [result.to_json() for result in results],
        },
    )


if __name__ == "__main__":
    main()
