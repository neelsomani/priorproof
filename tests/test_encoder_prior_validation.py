from __future__ import annotations

from datetime import date

from priorproof.modeling.encoder import StatementEncoder
from priorproof.data.models import DeclarationRecord, Footprint, FootprintItem
from priorproof.modeling.prior import PriorConfig, build_hierarchical_prior
from priorproof.modeling.retriever import StatementRetriever
from priorproof.metric.scoring import score_footprint
from priorproof.evaluation.reports import chronological_prediction_test, threshold_sweep_summary


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
    encoder = StatementEncoder().fit(pre_t)
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

