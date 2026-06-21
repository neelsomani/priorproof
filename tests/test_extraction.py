from __future__ import annotations

from datetime import date

from priorproof.extraction.snapshots import (
    SnapshotManifestItem,
    is_placeholder_commit,
    manifest_from_commit_map,
    normalize_raw_row,
    prepare_mathlib_worktree,
    render_command_template,
)
from priorproof.extraction.proof_term import LEAN_EXTRACTOR, ProofTermExtractorConfig, extractor_command, lake_build_command


def test_manifest_from_commit_map_infers_quarter_start() -> None:
    snapshots = manifest_from_commit_map({"2024Q2": "abc123", "2024Q1": "def456"})
    assert [snapshot.snapshot_id for snapshot in snapshots] == ["2024Q1", "2024Q2"]
    assert snapshots[0].start_date == date(2024, 1, 1)
    assert snapshots[1].commit == "abc123"


def test_placeholder_commit_detection() -> None:
    assert is_placeholder_commit("replace-with-mathlib-commit")
    assert is_placeholder_commit("auto")
    assert is_placeholder_commit("")
    assert not is_placeholder_commit("09b373db6e4ffb252c7341188d0225b789df3011")


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


def test_worktree_plan_uses_absolute_paths(tmp_path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "relative" / "worktree"
    plan = prepare_mathlib_worktree(repo, worktree, "abc123", execute=False)
    assert str(repo.resolve()) in plan[0]
    assert str(worktree.resolve()) in plan[1]
    assert str(worktree.resolve()) in plan[2]


def test_proof_term_extractor_command_uses_lean_run(tmp_path) -> None:
    command = extractor_command(
        ProofTermExtractorConfig(
            repo=tmp_path,
            out=tmp_path / "raw.jsonl",
            commit="abc123",
            proof_date=date(2024, 1, 1),
            imports=("Mathlib.Topology.Basic",),
            module_prefixes=("Mathlib.Topology",),
            lean_command=("lake", "env", "lean"),
        ),
        tmp_path / "PriorProofExtract.lean",
    )
    assert command[:4] == ("lake", "env", "lean", "--run")
    assert command[5] == "--"
    assert "--import" in command
    assert "Mathlib.Topology.Basic" in command
    assert "--module-prefix" in command
    assert "Mathlib.Topology" in command


def test_lake_build_command_builds_requested_imports(tmp_path) -> None:
    config = ProofTermExtractorConfig(
        repo=tmp_path,
        out=tmp_path / "raw.jsonl",
        commit="abc123",
        proof_date=date(2024, 1, 1),
        imports=("Mathlib.Topology.Basic", "Mathlib.Data.Nat.Basic"),
        lean_command=("lake", "env", "lean"),
    )
    assert lake_build_command(config) == ("lake", "build", "Mathlib.Topology.Basic", "Mathlib.Data.Nat.Basic")


def test_embedded_extractor_reads_theorem_values_not_source_text() -> None:
    assert ".thmInfo val" in LEAN_EXTRACTOR
    assert "val.value" in LEAN_EXTRACTOR
    assert "exprConstants value" in LEAN_EXTRACTOR
    assert "source_scan" not in LEAN_EXTRACTOR
