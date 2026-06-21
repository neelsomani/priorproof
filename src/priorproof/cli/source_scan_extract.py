from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from priorproof.extraction.source_scan import SourceScanConfig, extract_source_scan, git_commit_date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract theorem declarations from Lean source files.")
    parser.add_argument("--repo", required=True, help="Mathlib worktree or Lean project directory.")
    parser.add_argument("--out", required=True, help="Raw JSONL output path.")
    parser.add_argument("--commit", default="", help="Commit hash used for metadata.")
    parser.add_argument("--proof-date", help="ISO date used for extracted declarations. Defaults to commit date if possible.")
    parser.add_argument("--include-private", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = Path(args.repo)
    proof_date = date.fromisoformat(args.proof_date) if args.proof_date else None
    if proof_date is None:
        if not args.commit:
            raise ValueError("--proof-date is required when --commit is not provided")
        proof_date = git_commit_date(repo, args.commit)
    count = extract_source_scan(
        SourceScanConfig(
            repo=repo,
            out=Path(args.out),
            commit=args.commit,
            proof_date=proof_date,
            include_private=args.include_private,
        )
    )
    print(f"wrote {count} declarations to {args.out}")


if __name__ == "__main__":
    main()

