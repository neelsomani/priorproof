from __future__ import annotations

import argparse
from pathlib import Path

from priorproof.corpus.pipeline import load_declarations
from priorproof.data.io import write_json, write_jsonl
from priorproof.scope import filter_records_by_scope, load_scope, scope_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter normalized declarations to a named module scope.")
    parser.add_argument("--declarations", required=True)
    parser.add_argument("--scope", required=True, help="Scope JSON config.")
    parser.add_argument("--out-declarations", required=True, help="Scoped corpus declarations JSONL.")
    parser.add_argument("--out-targets", required=True, help="JSON list of target declaration names.")
    parser.add_argument("--report", required=True, help="Scope density and role report JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scope = load_scope(args.scope)
    records = load_declarations(args.declarations)
    corpus, targets, support = filter_records_by_scope(records, scope)
    target_names = [record.name for record in targets]
    write_jsonl(Path(args.out_declarations), corpus)
    write_json(Path(args.out_targets), target_names)
    write_json(Path(args.report), scope_report(records, scope))


if __name__ == "__main__":
    main()
