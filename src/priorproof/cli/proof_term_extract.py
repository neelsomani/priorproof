from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from priorproof.data.models import parse_date
from priorproof.extraction.proof_term import ProofTermExtractorConfig, extract_proof_terms


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Lean proof-term extractor for a Mathlib checkout.")
    parser.add_argument("--repo", required=True, help="Mathlib checkout.")
    parser.add_argument("--out", required=True, help="Raw priorproof JSONL output.")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--proof-date", required=True)
    parser.add_argument("--import", dest="imports", action="append", default=[], help="Lean import. Repeatable.")
    parser.add_argument(
        "--module-prefix",
        dest="module_prefixes",
        action="append",
        default=[],
        help="Module prefix to retain. Repeatable.",
    )
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--lean-command", help="Override Lean runner, e.g. 'lake env lean'.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extract_proof_terms(
        ProofTermExtractorConfig(
            repo=Path(args.repo),
            out=Path(args.out),
            commit=args.commit,
            proof_date=parse_date(args.proof_date),
            imports=tuple(args.imports or ["Mathlib"]),
            module_prefixes=tuple(args.module_prefixes or ["Mathlib"]),
            include_private=args.include_private,
            lean_command=tuple(shlex.split(args.lean_command)) if args.lean_command else None,
        )
    )


if __name__ == "__main__":
    main()
