from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from ..data.io import write_jsonl


DECL_START_RE = re.compile(
    r"^\s*(?:@[^\n]+\s*)*(?P<kind>theorem|lemma|example)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)?"
    r"(?P<rest>.*)$"
)
NEXT_DECL_RE = re.compile(r"^\s*(?:theorem|lemma|example|def|instance|class|structure|inductive)\b")
IDENT_RE = re.compile(r"\b[A-Z][A-Za-z0-9_']*(?:\.[A-Za-z_][A-Za-z0-9_']*)+\b")


@dataclass(frozen=True)
class SourceScanConfig:
    repo: Path
    out: Path
    commit: str
    proof_date: date
    include_private: bool = False


def extract_source_scan(config: SourceScanConfig) -> int:
    rows = list(iter_source_scan_rows(config))
    write_jsonl(config.out, rows)
    return len(rows)


def iter_source_scan_rows(config: SourceScanConfig) -> Iterable[dict[str, object]]:
    for path in sorted(config.repo.rglob("*.lean")):
        if ".lake" in path.parts:
            continue
        module = lean_module(config.repo, path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for block in declaration_blocks(text):
            row = parse_declaration_block(block, module=module, commit=config.commit, proof_date=config.proof_date)
            if row is None:
                continue
            name = str(row["name"])
            if not config.include_private and ("._private" in name or name.startswith("_private")):
                continue
            yield row


def declaration_blocks(text: str) -> Iterable[str]:
    lines = text.splitlines()
    current: list[str] = []
    in_decl = False
    for line in lines:
        if DECL_START_RE.match(line):
            if current:
                yield "\n".join(current)
            current = [line]
            in_decl = True
            continue
        if in_decl and NEXT_DECL_RE.match(line):
            if current:
                yield "\n".join(current)
            current = [line]
            in_decl = bool(DECL_START_RE.match(line))
            if not in_decl:
                current = []
            continue
        if in_decl:
            current.append(line)
    if current:
        yield "\n".join(current)


def parse_declaration_block(
    block: str,
    *,
    module: str,
    commit: str,
    proof_date: date,
) -> dict[str, object] | None:
    first_line = block.splitlines()[0]
    match = DECL_START_RE.match(first_line)
    if not match:
        return None
    raw_name = match.group("name")
    if not raw_name:
        raw_name = f"anonymous.{abs(hash(block))}"
    name = qualify_name(raw_name, module)
    statement = statement_part(block)
    dependencies = [
        {
            "name": dep,
            "kind": "const",
            "module": module_from_name(dep),
            "namespace": namespace_from_name(dep),
            "source": "source_scan",
        }
        for dep in sorted(extract_identifiers(block) - {name, raw_name})
    ]
    return {
        "name": name,
        "statement": statement,
        "proof_date": proof_date.isoformat(),
        "module": module,
        "namespace": namespace_from_name(name),
        "commit": commit,
        "dependencies": dependencies,
        "dependency_edges": [],
        "subterms": [],
        "metadata": {
            "source_adapter": "source_scan",
            "warning": "Source scanning is not elaborated proof-term extraction.",
        },
    }


def statement_part(block: str) -> str:
    head = block.split(":=", 1)[0]
    head = head.split(" by", 1)[0]
    return " ".join(part.strip() for part in head.splitlines() if part.strip())


def extract_identifiers(block: str) -> set[str]:
    return set(IDENT_RE.findall(block))


def lean_module(repo: Path, path: Path) -> str:
    relative = path.relative_to(repo).with_suffix("")
    parts = [part for part in relative.parts if part not in {"Mathlib", "Archive", "Counterexamples"}]
    if relative.parts and relative.parts[0] in {"Mathlib", "Archive", "Counterexamples"}:
        return ".".join((relative.parts[0], *parts))
    return ".".join(parts)


def qualify_name(name: str, module: str) -> str:
    if "." in name:
        return name
    namespace = module.rsplit(".", 1)[0] if "." in module else module
    return f"{namespace}.{name}" if namespace else name


def namespace_from_name(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else ""


def module_from_name(name: str) -> str:
    parts = name.split(".")
    if len(parts) <= 1:
        return ""
    return ".".join(parts[:-1])


def git_commit_date(repo: Path, commit: str) -> date:
    completed = subprocess.run(
        ("git", "-C", str(repo), "show", "-s", "--format=%cs", commit),
        check=True,
        capture_output=True,
        text=True,
    )
    return date.fromisoformat(completed.stdout.strip())

