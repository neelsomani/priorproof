from __future__ import annotations

import argparse

from priorproof.data.io import read_json
from priorproof.extraction.snapshots import manifest_from_commit_map, write_snapshot_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an extraction snapshot manifest from a commit map.")
    parser.add_argument("--commits", required=True, help="JSON object/list of quarterly snapshot commits.")
    parser.add_argument("--out", required=True, help="Output manifest JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshots = manifest_from_commit_map(read_json(args.commits))
    write_snapshot_manifest(args.out, snapshots)


if __name__ == "__main__":
    main()
