from __future__ import annotations

from datetime import date

from priorproof.extraction.snapshots import (
    SnapshotManifestItem,
    manifest_from_commit_map,
    normalize_raw_row,
    render_command_template,
)


def test_manifest_from_commit_map_infers_quarter_start() -> None:
    snapshots = manifest_from_commit_map({"2024Q2": "abc123", "2024Q1": "def456"})
    assert [snapshot.snapshot_id for snapshot in snapshots] == ["2024Q1", "2024Q2"]
    assert snapshots[0].start_date == date(2024, 1, 1)
    assert snapshots[1].commit == "abc123"


def test_flexible_normalizer_handles_nested_theorem_and_premises() -> None:
    snapshot = SnapshotManifestItem("2024Q1", date(2024, 1, 1), "abc123")
    row = {
        "theorem": {
            "full_name": "Mathlib.Algebra.foo",
            "statement": "forall x, x = x",
            "file_path": "Mathlib/Algebra/Group.lean",
        },
        "premises": [
            {"full_name": "Mathlib.Algebra.bar", "kind": "const", "file_path": "Mathlib/Algebra/Group.lean"},
            "Mathlib.Init.baz",
        ],
        "dependency_edges": [{"parent": "local", "child": "Mathlib.Algebra.bar"}],
        "subterms": [{"conclusion": "forall y, y = y", "dependencies": ["local"]}],
    }
    record = normalize_raw_row(row, adapter="auto", snapshot=snapshot)[0]
    assert record.name == "Mathlib.Algebra.foo"
    assert record.module == "Mathlib.Algebra.Group"
    assert [dep.name for dep in record.dependencies] == ["Mathlib.Algebra.bar", "Mathlib.Init.baz"]
    assert record.dependency_edges == (("local", "Mathlib.Algebra.bar"),)
    assert record.subterms[0]["dependencies"] == ["local"]


def test_command_template_renders_shell_words() -> None:
    command = render_command_template(
        "python extractor.py --repo {worktree} --out {raw_path}",
        {"worktree": "/tmp/mathlib", "raw_path": "/tmp/raw.jsonl"},
    )
    assert command.argv == ("python", "extractor.py", "--repo", "/tmp/mathlib", "--out", "/tmp/raw.jsonl")

