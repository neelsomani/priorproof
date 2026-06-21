from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.data.io import read_json
from priorproof.extraction.snapshots import (
    SnapshotManifestItem,
    is_placeholder_commit,
    manifest_from_commit_map,
    resolve_commit_at_date,
    write_snapshot_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an extraction snapshot manifest from a commit map.")
    parser.add_argument("--commits", required=True, help="JSON object/list of quarterly snapshot commits.")
    parser.add_argument(
        "--mathlib-repo",
        help="Resolve missing, `auto`, or placeholder commits to the latest local Mathlib commit before each start date.",
    )
    parser.add_argument("--out", required=True, help="Output manifest JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshots = manifest_from_commit_map(read_json(args.commits))
    if args.mathlib_repo:
        snapshots = resolve_auto_commits(Path(args.mathlib_repo), snapshots)
    write_snapshot_manifest(args.out, snapshots)


def resolve_auto_commits(repo: Path, snapshots: list[SnapshotManifestItem]) -> list[SnapshotManifestItem]:
    return [
        SnapshotManifestItem(
            snapshot_id=snapshot.snapshot_id,
            start_date=snapshot.start_date,
            commit=resolve_commit_at_date(repo, snapshot.start_date)
            if is_placeholder_commit(snapshot.commit)
            else snapshot.commit,
        )
        for snapshot in snapshots
    ]


if __name__ == "__main__":
    main()
