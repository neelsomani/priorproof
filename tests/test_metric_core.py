from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

from priorproof.metric.filtering import DependencyFilter
from priorproof.metric.frontier import established_frontier
from priorproof.data.models import DeclarationRecord, Dependency, Snapshot
from priorproof.corpus.pipeline import build_footprints, load_declarations
from priorproof.metric.redundancy import (
    canonical_statement,
    detect_redundant_subterms,
    exact_statement_wrapper_flags,
)
from priorproof.metric.scoring import score_footprint


def dep(name: str, module: str = "Mathlib.Algebra.Group", namespace: str = "Algebra") -> Dependency:
    return Dependency(name=name, module=module, namespace=namespace)


def test_filter_drops_plumbing_and_deduplicates() -> None:
    deps = (
        dep("Mathlib.Real.sqrt"),
        Dependency(name="instFoo", kind="typeclass", module="Mathlib.Algebra.Group"),
        dep("Mathlib.Real.sqrt"),
    )
    kept = DependencyFilter().apply(deps)
    assert [item.name for item in kept] == ["Mathlib.Real.sqrt"]


def test_redundancy_matches_pre_t_statement() -> None:
    prior = DeclarationRecord(
        name="priorLemma",
        statement="forall x, x = x",
        proof_date=date(2024, 1, 1),
        module="Mathlib.Init",
        namespace="Mathlib",
        commit="a",
    )
    target = DeclarationRecord(
        name="target",
        statement="True",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Init",
        namespace="Mathlib",
        commit="b",
        subterms=({"id": "s1", "conclusion": "∀ y, y = y", "dependencies": ["hardWay"]},),
    )
    assert canonical_statement("∀ x, x = x") == canonical_statement("forall y, y = y")
    hits = detect_redundant_subterms(target, [prior])
    assert hits[0].matched_declaration == "priorLemma"
    assert hits[0].raw_dependencies == ("hardWay",)


def test_redundancy_matches_normalized_conclusion_key() -> None:
    prior = DeclarationRecord(
        name="priorLemma",
        statement="forall x, x = x",
        proof_date=date(2024, 1, 1),
        module="Mathlib.Init",
        namespace="Mathlib",
        commit="a",
    )
    target = DeclarationRecord(
        name="target",
        statement="True",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Init",
        namespace="Mathlib",
        commit="b",
        subterms=(
            {
                "id": "s1",
                "conclusion": "ignored pretty text",
                "normalized_conclusion": "∀ y, y = y",
                "dependencies": ["hardWay"],
            },
        ),
    )
    hits = detect_redundant_subterms(target, [prior])
    assert hits[0].matched_declaration == "priorLemma"
    assert hits[0].mode == "normalized_statement"


def test_redundancy_matches_whole_proof_exact_statement_wrapper() -> None:
    prior = DeclarationRecord(
        name="priorLemma",
        statement="forall x, x = x",
        proof_date=date(2024, 1, 1),
        module="Mathlib.Init",
        namespace="Mathlib",
        commit="a",
    )
    target = DeclarationRecord(
        name="target",
        statement="∀ y, y = y",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Init",
        namespace="Mathlib",
        commit="b",
        dependencies=(dep("priorLemma"),),
    )
    hits = exact_statement_wrapper_flags(target, {canonical_statement(prior.statement): [prior]})
    assert hits[0].matched_declaration == "priorLemma"
    assert hits[0].mode == "by_exact_statement"


def test_rederive_fixture_fires_redundancy_detector() -> None:
    fixture = Path(__file__).parent / "fixtures" / "rederive_redundancy.jsonl"
    footprints = build_footprints(load_declarations(fixture), snapshots=None, threshold=1, min_family_support=1)
    hits = {
        footprint.declaration: footprint.redundant_subterms
        for footprint in footprints
        if footprint.redundant_subterms
    }
    assert hits["Mathlib.trig_identity_exact_copy"][0]["mode"] == "by_exact_statement"
    assert hits["Mathlib.trig_identity_rederived_via_euler"][0]["matched_declaration"] == "Mathlib.trig_identity"


def test_frontier_unfolds_until_reuse_threshold() -> None:
    record = DeclarationRecord(
        name="target",
        statement="P",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Algebra.Group",
        namespace="Algebra",
        commit="b",
        dependencies=(dep("fresh"),),
    )
    snapshot = Snapshot("2024Q2", date(2024, 4, 1), "a", ("old",))
    footprint = established_frontier(
        record=record,
        snapshot=snapshot,
        reuse_counts=Counter({"fresh": 1, "established": 7}),
        dependency_lookup={"fresh": dep("fresh"), "established": dep("established")},
        dependency_graph={"fresh": {"established"}},
        threshold=5,
        filtered_dependencies=record.dependencies,
        min_family_support=1,
    )
    assert [item.raw_name for item in footprint.items] == ["established"]


def test_score_uses_weighted_surprisal() -> None:
    record = DeclarationRecord(
        name="target",
        statement="P",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Algebra.Group",
        namespace="Algebra",
        commit="b",
        dependencies=(dep("Mathlib.Algebra.foo"),),
    )
    snapshot = Snapshot("2024Q2", date(2024, 4, 1), "a", ())
    footprint = established_frontier(
        record=record,
        snapshot=snapshot,
        reuse_counts=Counter({"Mathlib.Algebra.foo": 5}),
        dependency_lookup={"Mathlib.Algebra.foo": dep("Mathlib.Algebra.foo")},
        dependency_graph={},
        threshold=5,
        filtered_dependencies=record.dependencies,
        min_family_support=1,
    )
    score = score_footprint(footprint, {footprint.items[0].family: 0.5})
    assert score.surprisal > 0
    assert score.mean_item_surprisal > 0
