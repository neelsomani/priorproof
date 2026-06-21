from __future__ import annotations

from datetime import date

from priorproof.modeling.contrastive import PairMiningConfig, mine_contrastive_examples
from priorproof.data.models import DeclarationRecord, Footprint, FootprintItem
from priorproof.modeling.prior import PriorConfig, build_hierarchical_prior
from priorproof.modeling.retriever import StatementRetriever
from priorproof.metric.scoring import score_footprint
from priorproof.cli.check_encoder_stability import self_comparison_snapshot_ids, stability_candidates
from priorproof.data.models import Snapshot
from priorproof.evaluation.reports import (
    chronological_prediction_test,
    parametric_leakage_probe,
    threshold_footprint_bucket_diagnostic,
    threshold_sweep_summary,
)


class ToyStatementEncoder:
    def encode(self, record: DeclarationRecord | str) -> list[float]:
        statement = record.statement if isinstance(record, DeclarationRecord) else record
        if "*" in statement:
            return [1.0, 0.0]
        if "+" in statement:
            return [0.0, 1.0]
        return [0.5, 0.5]


def record(name: str, statement: str, day: int, namespace: str = "Algebra") -> DeclarationRecord:
    return DeclarationRecord(
        name=name,
        statement=statement,
        proof_date=date(2024, 1, day),
        module="Mathlib.Algebra.Group",
        namespace=namespace,
        commit=str(day),
    )


def footprint(name: str, family: str, threshold: int = 5) -> Footprint:
    return Footprint(
        declaration=name,
        snapshot_id="2024Q1",
        threshold=threshold,
        items=(FootprintItem(family=family, raw_name=family, weight=1.0, backoff_depth=0, support=3),),
        filtered_dependencies=(family,),
    )


def test_encoder_retriever_and_prior_build() -> None:
    pre_t = [
        record("a", "forall x, x * 1 = x", 1),
        record("b", "forall x, 1 * x = x", 2),
        record("c", "forall n, n + 0 = n", 3, namespace="Nat"),
    ]
    target = record("target", "forall y, y * 1 = y", 4)
    encoder = ToyStatementEncoder()
    hits = StatementRetriever(encoder, pre_t).query(target, k=2)
    footprints = {"a": footprint("a", "namespace:Algebra"), "b": footprint("b", "namespace:Algebra")}
    prior = build_hierarchical_prior(target, pre_t, footprints, hits, PriorConfig())
    assert prior["namespace:Algebra"] > 0
    assert abs(sum(prior.values()) - 1.0) < 1e-9


def test_validation_summaries() -> None:
    fp = footprint("a", "family")
    priors = {"a": {"family": 0.9, "other": 0.1}}
    report = chronological_prediction_test([fp], priors)
    assert report["n_items"] == 1.0
    score_low = score_footprint(fp, {"family": 0.9})
    score_high = score_footprint(footprint("a", "family", threshold=8), {"family": 0.8})
    sweep = threshold_sweep_summary({5: [score_low], 8: [score_high]})
    assert sweep["thresholds"] == [5, 8]


def test_threshold_bucket_diagnostic_reports_identical_and_changed_buckets() -> None:
    t3 = [
        footprint("same", "family", threshold=3),
        footprint("changed", "family:old", threshold=3),
    ]
    t8 = [
        footprint("same", "family", threshold=8),
        footprint("changed", "family:new", threshold=8),
    ]
    report = threshold_footprint_bucket_diagnostic(
        {3: t3, 8: t8},
        sample_declaration="same",
    )
    assert report["sample_identical_family_buckets"] is True
    assert report["all_family_buckets_identical"] is False
    assert report["identical_family_bucket_count"] == 1
    assert report["common_declaration_count"] == 2
    assert report["changed_examples"][0]["declaration"] == "changed"


def test_parametric_leakage_probe_summarizes_retrieval_nonempty_rows() -> None:
    fp_a = footprint("a", "family")
    fp_b = footprint("b", "family")
    report = parametric_leakage_probe(
        normal_priors={"a": {"family": 0.9}, "b": {"family": 0.8}},
        counterfactual_priors={"a": {"family": 0.3}, "b": {"family": 0.2}},
        footprints=[fp_a, fp_b],
        retrieval_hit_counts={"a": 2, "b": 0},
    )
    assert report["all"]["n"] == 2.0
    assert report["retrieval_nonempty"]["n"] == 1.0
    assert report["retrieval_empty"]["n"] == 1.0
    assert report["rows"][0]["retrieval_nonempty"] is True


def test_stability_candidate_helpers_exclude_self_comparison_bins(tmp_path) -> None:
    reference = tmp_path / "encoder_a"
    same = tmp_path / "encoder_a"
    other = tmp_path / "encoder_b"
    reference.mkdir()
    other.mkdir()
    self_snapshots = self_comparison_snapshot_ids(
        reference,
        {"2024Q1": same.resolve(), "2024Q2": other.resolve()},
    )
    assert self_snapshots == {"2024Q1"}

    snapshots = {
        "2024Q1": Snapshot("2024Q1", date(2024, 1, 1), "a", ("prior",)),
        "2024Q2": Snapshot("2024Q2", date(2024, 4, 1), "b", ("prior",)),
        "2024Q3": Snapshot("2024Q3", date(2024, 7, 1), "c", ()),
    }
    candidates = stability_candidates(
        [footprint("a", "family", threshold=5), footprint("b", "family", threshold=5)],
        snapshots,
        {"a", "b"},
    )
    assert [candidate.declaration for candidate in candidates] == ["a", "b"]


def test_contrastive_example_mining_from_shared_families_and_hard_negatives() -> None:
    records = [
        record("a", "forall x, compact x -> closed x", 1),
        record("b", "forall y, compact y -> bounded y", 2),
        record("c", "forall z, z + 0 = z", 3),
    ]
    footprints = [
        footprint("a", "namespace:Topology"),
        Footprint(
            declaration="b",
            snapshot_id="2024Q1",
            threshold=5,
            items=(
                FootprintItem("namespace:Topology", "top", 1.0, 0, 3),
                FootprintItem("namespace:Compact", "compact", 1.0, 0, 3),
            ),
            filtered_dependencies=("top", "compact"),
        ),
        footprint("c", "namespace:Nat"),
    ]
    examples = mine_contrastive_examples(
        records,
        footprints,
        PairMiningConfig(shared_family_min=1, namespace_symbol_jaccard_min=0.1),
    )
    assert any(example.anchor == "a" and example.positive == "b" for example in examples)
