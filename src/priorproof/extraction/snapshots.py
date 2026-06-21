from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from ..data.io import read_json, read_jsonl, write_json, write_jsonl
from ..data.models import DeclarationRecord, Dependency, Snapshot, parse_date


@dataclass(frozen=True)
class SnapshotManifestItem:
    snapshot_id: str
    start_date: date
    commit: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SnapshotManifestItem":
        return cls(
            snapshot_id=str(data["snapshot_id"]),
            start_date=parse_date(data["start_date"]),
            commit=str(data["commit"]),
        )

    def to_json(self) -> dict[str, str]:
        return {
            "snapshot_id": self.snapshot_id,
            "start_date": self.start_date.isoformat(),
            "commit": self.commit,
        }


@dataclass(frozen=True)
class ExtractorCommand:
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)

    def format(self, variables: dict[str, str]) -> "ExtractorCommand":
        return ExtractorCommand(
            argv=tuple(part.format(**variables) for part in self.argv),
            cwd=Path(str(self.cwd).format(**variables)) if self.cwd else None,
            env={key: value.format(**variables) for key, value in self.env.items()},
        )

    def display(self) -> str:
        prefix = f"(cd {shlex.quote(str(self.cwd))} && " if self.cwd else ""
        body = " ".join(shlex.quote(part) for part in self.argv)
        return f"{prefix}{body}{')' if prefix else ''}"


@dataclass(frozen=True)
class ExtractionResult:
    snapshot_id: str
    commit: str
    raw_path: Path
    normalized_path: Path
    declaration_count: int
    command: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "commit": self.commit,
            "raw_path": str(self.raw_path),
            "normalized_path": str(self.normalized_path),
            "declaration_count": self.declaration_count,
            "command": self.command,
        }


def load_snapshot_manifest(path: str | Path) -> list[SnapshotManifestItem]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError("Snapshot manifest must be a JSON list")
    return [SnapshotManifestItem.from_json(item) for item in data]


def write_snapshot_manifest(path: str | Path, snapshots: Iterable[SnapshotManifestItem]) -> None:
    write_json(path, [snapshot.to_json() for snapshot in snapshots])


def snapshots_from_manifest(snapshots: Iterable[SnapshotManifestItem], declarations_by_snapshot: dict[str, list[str]]) -> list[Snapshot]:
    return [
        Snapshot(
            snapshot_id=snapshot.snapshot_id,
            start_date=snapshot.start_date,
            commit=snapshot.commit,
            declarations=tuple(declarations_by_snapshot.get(snapshot.snapshot_id, [])),
        )
        for snapshot in snapshots
    ]


def prepare_mathlib_worktree(repo: Path, worktree: Path, commit: str, *, execute: bool) -> list[str]:
    repo = repo.resolve()
    worktree = worktree.resolve()
    commands = [
        f"git -C {shlex.quote(str(repo))} fetch --all --tags",
        f"git -C {shlex.quote(str(repo))} worktree add --detach {shlex.quote(str(worktree))} {shlex.quote(commit)}",
        f"git -C {shlex.quote(str(worktree))} checkout --detach {shlex.quote(commit)}",
    ]
    if execute:
        worktree.parent.mkdir(parents=True, exist_ok=True)
        run_command(("git", "-C", str(repo), "fetch", "--all", "--tags"))
        if not worktree.exists():
            run_command(("git", "-C", str(repo), "worktree", "add", "--detach", str(worktree), commit))
        else:
            run_command(("git", "-C", str(worktree), "checkout", "--detach", commit))
    return commands


def validate_snapshot_commits(repo: Path, snapshots: Iterable[SnapshotManifestItem]) -> None:
    repo = repo.resolve()
    bad_placeholders = [snapshot.snapshot_id for snapshot in snapshots if is_placeholder_commit(snapshot.commit)]
    if bad_placeholders:
        raise ValueError(
            "Snapshot manifest contains placeholder commits for "
            f"{bad_placeholders}. Regenerate it with "
            "`priorproof-make-snapshot-manifest --commits configs/snapshot_commits.example.json "
            "--mathlib-repo external/mathlib4 --out artifacts/extraction/manifest.json`, "
            "or replace each commit with a real Mathlib commit hash."
        )
    unresolved = [
        (snapshot.snapshot_id, snapshot.commit)
        for snapshot in snapshots
        if not git_commit_exists(repo, snapshot.commit)
    ]
    if unresolved:
        formatted = ", ".join(f"{snapshot_id}={commit}" for snapshot_id, commit in unresolved)
        raise ValueError(f"Snapshot manifest contains commits not present in {repo}: {formatted}")


def is_placeholder_commit(commit: str) -> bool:
    text = commit.strip().lower()
    return not text or "replace-with" in text or text in {"placeholder", "todo", "auto"}


def git_commit_exists(repo: Path, commit: str) -> bool:
    completed = subprocess.run(
        ("git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"),
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


def resolve_commit_at_date(repo: Path, cutoff: date) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), "rev-list", "-n", "1", f"--before={cutoff.isoformat()} 23:59:59", "HEAD"),
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Could not resolve Mathlib commit before {cutoff.isoformat()}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    commit = completed.stdout.strip()
    if not commit:
        raise ValueError(f"No Mathlib commit found before {cutoff.isoformat()} in {repo}")
    return commit


def run_extractor_command(command: ExtractorCommand, *, execute: bool) -> None:
    if not execute:
        return
    run_command(command.argv, cwd=command.cwd, env=command.env or None)


def normalize_extractor_file(
    raw_path: str | Path,
    out_path: str | Path,
    *,
    adapter: str,
    snapshot: SnapshotManifestItem,
) -> list[DeclarationRecord]:
    records = [
        record
        for row in iter_raw_rows(raw_path)
        for record in normalize_raw_row(row, adapter=adapter, snapshot=snapshot)
    ]
    records.sort(key=lambda item: (item.proof_date, item.module, item.name))
    write_jsonl(out_path, records)
    return records


def merge_normalized_declarations(paths: Iterable[str | Path], out_path: str | Path) -> list[DeclarationRecord]:
    by_name: dict[str, DeclarationRecord] = {}
    for path in paths:
        for record in read_jsonl(path, DeclarationRecord.from_json):
            previous = by_name.get(record.name)
            if previous is None or record.proof_date < previous.proof_date:
                by_name[record.name] = record
    records = sorted(by_name.values(), key=lambda item: (item.proof_date, item.module, item.name))
    write_jsonl(out_path, records)
    return records


def iter_raw_rows(path: str | Path) -> Iterable[dict[str, Any]]:
    source = Path(path)
    if source.suffix == ".jsonl":
        yield from read_jsonl(source)
        return
    data = read_json(source)
    if isinstance(data, list):
        yield from data
    elif isinstance(data, dict):
        for key in ("declarations", "theorems", "records", "traced_theorems"):
            value = data.get(key)
            if isinstance(value, list):
                yield from value
                return
        yield data
    else:
        raise ValueError(f"Unsupported extractor output in {path}")


def normalize_raw_row(
    row: dict[str, Any],
    *,
    adapter: str,
    snapshot: SnapshotManifestItem,
) -> list[DeclarationRecord]:
    if adapter == "priorproof":
        return [DeclarationRecord.from_json(with_snapshot_defaults(row, snapshot))]
    if adapter == "leandojo":
        return [normalize_flexible_row(row, snapshot=snapshot, source_adapter="leandojo")]
    if adapter == "generic":
        return [normalize_flexible_row(row, snapshot=snapshot, source_adapter="generic")]
    if adapter == "ntp":
        return [normalize_flexible_row(row, snapshot=snapshot, source_adapter="ntp")]
    if adapter == "auto":
        return [normalize_flexible_row(row, snapshot=snapshot, source_adapter=infer_adapter(row))]
    raise ValueError(f"Unknown adapter: {adapter}")


def with_snapshot_defaults(row: dict[str, Any], snapshot: SnapshotManifestItem) -> dict[str, Any]:
    data = dict(row)
    data.setdefault("proof_date", snapshot.start_date.isoformat())
    data.setdefault("commit", snapshot.commit)
    return data


def normalize_flexible_row(
    row: dict[str, Any],
    *,
    snapshot: SnapshotManifestItem,
    source_adapter: str,
) -> DeclarationRecord:
    theorem = first_dict(row, "theorem", "decl", "declaration") or row
    name = first_string(theorem, "full_name", "name", "decl_name", "theorem_name") or first_string(row, "full_name", "name")
    if not name:
        raise ValueError(f"Extractor row has no declaration name: {row!r}")
    statement = (
        first_string(theorem, "statement", "pp_statement", "type", "formal_statement")
        or first_string(row, "statement", "pp_statement", "type", "formal_statement")
        or ""
    )
    module = (
        first_string(theorem, "module", "module_name", "file_path")
        or first_string(row, "module", "module_name", "file_path")
        or ""
    )
    module = normalize_module(module)
    namespace = (
        first_string(theorem, "namespace")
        or first_string(row, "namespace")
        or namespace_from_name(name)
    )
    dependency_source = row if has_any_list(row, "dependencies", "premises", "used_premises", "constants", "imports") else theorem
    dependencies = tuple(normalize_dependencies(dependency_source, default_module=module))
    dependency_edges = tuple(normalize_edges(row))
    subterms = tuple(normalize_subterms(row))
    proof_date = parse_date(
        first_string(row, "proof_date", "date", "commit_date")
        or first_string(theorem, "proof_date", "date", "commit_date")
        or snapshot.start_date.isoformat()
    )
    commit = first_string(row, "commit") or first_string(theorem, "commit") or snapshot.commit
    return DeclarationRecord(
        name=name,
        statement=statement,
        proof_date=proof_date,
        module=module,
        namespace=namespace,
        commit=commit,
        dependencies=dependencies,
        dependency_edges=dependency_edges,
        subterms=subterms,
        metadata={
            "source_adapter": source_adapter,
            "snapshot_id": snapshot.snapshot_id,
            "raw_keys": sorted(row.keys()),
        },
    )


def normalize_dependencies(row: dict[str, Any], *, default_module: str) -> list[Dependency]:
    values = first_list(row, "dependencies", "premises", "used_premises", "constants", "imports") or []
    deps: list[Dependency] = []
    for value in values:
        if isinstance(value, str):
            deps.append(
                Dependency(
                    name=value,
                    module=default_module,
                    namespace=namespace_from_name(value),
                )
            )
        elif isinstance(value, dict):
            name = first_string(value, "full_name", "name", "decl_name", "premise", "constant")
            if not name:
                continue
            module = normalize_module(first_string(value, "module", "module_name", "file_path") or default_module)
            deps.append(
                Dependency(
                    name=name,
                    kind=first_string(value, "kind", "type") or "const",
                    module=module,
                    namespace=first_string(value, "namespace") or namespace_from_name(name),
                    digest=first_string(value, "digest", "hash"),
                    source=first_string(value, "source", "span", "file_path"),
                )
            )
    return dedupe_dependencies(deps)


def normalize_edges(row: dict[str, Any]) -> list[tuple[str, str]]:
    values = first_list(row, "dependency_edges", "edges", "dep_edges") or []
    edges: list[tuple[str, str]] = []
    for value in values:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            edges.append((str(value[0]), str(value[1])))
        elif isinstance(value, dict):
            parent = first_string(value, "parent", "from", "source")
            child = first_string(value, "child", "to", "target")
            if parent and child:
                edges.append((parent, child))
    return edges


def normalize_subterms(row: dict[str, Any]) -> list[dict[str, Any]]:
    values = first_list(row, "subterms", "subproofs", "local_lemmas") or []
    subterms: list[dict[str, Any]] = []
    for idx, value in enumerate(values):
        if not isinstance(value, dict):
            continue
        subterm = {
            "id": str(value.get("id", f"subterm:{idx}")),
            "conclusion": first_string(value, "conclusion", "statement", "type") or "",
        }
        normalized = first_string(value, "normalized_conclusion", "normalized_statement")
        if normalized:
            subterm["normalized_conclusion"] = normalized
        exact = first_string(value, "exact", "exact_decl", "by_exact")
        if exact:
            subterm["exact"] = exact
        dependencies = first_list(value, "dependencies", "premises", "constants") or []
        subterm["dependencies"] = [str(item) if not isinstance(item, dict) else str(item.get("name", "")) for item in dependencies]
        subterms.append(subterm)
    return subterms


def dedupe_dependencies(dependencies: Iterable[Dependency]) -> list[Dependency]:
    seen: set[str] = set()
    output: list[Dependency] = []
    for dep in dependencies:
        if dep.name in seen:
            continue
        seen.add(dep.name)
        output.append(dep)
    return output


def infer_adapter(row: dict[str, Any]) -> str:
    keys = set(row)
    if {"traced_tactics", "theorem"} & keys:
        return "leandojo"
    if {"premises", "used_premises"} & keys:
        return "ntp"
    return "generic"


def first_dict(row: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return None


def first_list(row: dict[str, Any], *keys: str) -> list[Any] | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, list):
            return value
    return None


def has_any_list(row: dict[str, Any], *keys: str) -> bool:
    return first_list(row, *keys) is not None


def first_string(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value)
            if text:
                return text
    return None


def normalize_module(value: str) -> str:
    if not value:
        return ""
    text = value.removesuffix(".lean").replace("/", ".")
    marker = "Mathlib."
    if marker in text:
        text = text[text.index(marker) :]
    while text.startswith("."):
        text = text[1:]
    return text


def namespace_from_name(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else ""


def render_command_template(template: str, variables: dict[str, str]) -> ExtractorCommand:
    return ExtractorCommand(argv=tuple(shlex.split(template.format(**variables))))


def run_command(
    argv: Iterable[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(
        tuple(argv),
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        command = " ".join(str(part) for part in argv)
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {command}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def manifest_from_commit_map(data: object) -> list[SnapshotManifestItem]:
    if isinstance(data, list):
        return sorted((SnapshotManifestItem.from_json(item) for item in data), key=lambda item: item.start_date)
    if isinstance(data, dict):
        snapshots: list[SnapshotManifestItem] = []
        for snapshot_id, value in data.items():
            if isinstance(value, str):
                snapshots.append(
                    SnapshotManifestItem(
                        snapshot_id=str(snapshot_id),
                        start_date=quarter_start(str(snapshot_id)),
                        commit=value,
                    )
                )
            elif isinstance(value, dict):
                row = {"snapshot_id": snapshot_id, **value}
                row.setdefault("start_date", quarter_start(str(snapshot_id)).isoformat())
                snapshots.append(SnapshotManifestItem.from_json(row))
            else:
                raise ValueError(f"Unsupported manifest entry for {snapshot_id!r}: {value!r}")
        return sorted(snapshots, key=lambda item: item.start_date)
    raise ValueError("Commit map must be a JSON object or list")


def quarter_start(snapshot_id: str) -> date:
    if len(snapshot_id) == 6 and snapshot_id[4] == "Q" and snapshot_id[5].isdigit():
        year = int(snapshot_id[:4])
        quarter = int(snapshot_id[5])
        return date(year, 1 + 3 * (quarter - 1), 1)
    raise ValueError(f"Cannot infer quarter start from snapshot id: {snapshot_id}")
