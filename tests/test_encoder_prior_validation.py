from __future__ import annotations

from datetime import date

from priorproof.modeling.contrastive import PairMiningConfig, mine_contrastive_examples
from priorproof.data.models import DeclarationRecord, Dependency, Footprint, FootprintItem, NoveltyScore
from priorproof.modeling.prior import PriorConfig, build_hierarchical_prior
from priorproof.modeling.retriever import StatementRetriever
from priorproof.metric.scoring import score_footprint
from priorproof.corpus.pipeline import build_retrieval_prior_contexts
from priorproof.cli.check_encoder_stability import self_comparison_snapshot_ids, stability_candidates
from priorproof.cli.generate_proof_narratives import apply_narratives, build_prompt, packet_narratives, validate_narrative
from priorproof.cli.run_llm_baseline import response_key
from priorproof.data.models import Snapshot
from priorproof.scope import ModuleScope, filter_records_by_scope, scope_report
from priorproof.evaluation.reports import (
    chronological_prediction_test,
    parametric_leakage_probe,
    threshold_footprint_bucket_diagnostic,
    threshold_sweep_summary,
)
from priorproof.evaluation.packets import (
    extract_lean_source,
    find_declaration_start,
    human_argument_summary,
    missing_narratives,
    packet_side,
    public_side,
    require_complete_narratives,
)
from priorproof.evaluation.llm_baseline import evaluate_llm_baseline


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


def test_scope_filter_separates_targets_from_support() -> None:
    target = DeclarationRecord(
        name="target",
        statement="P",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Topology.MetricSpace.Basic",
        namespace="Topology",
        commit="b",
    )
    support = DeclarationRecord(
        name="support",
        statement="Q",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Topology.EMetricSpace.Basic",
        namespace="Topology",
        commit="b",
    )
    outside = DeclarationRecord(
        name="outside",
        statement="R",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Analysis.Normed.Field.Basic",
        namespace="Analysis",
        commit="b",
    )
    scope = ModuleScope(
        name="topology",
        target_module_prefixes=("Mathlib.Topology.MetricSpace",),
        support_module_prefixes=("Mathlib.Topology.EMetricSpace",),
    )
    corpus, targets, support_records = filter_records_by_scope([target, support, outside], scope)
    assert [record.name for record in corpus] == ["target", "support"]
    assert [record.name for record in targets] == ["target"]
    assert [record.name for record in support_records] == ["support"]


def test_scope_report_audits_target_dependency_mix() -> None:
    target_dep = Dependency(name="target_helper", module="Mathlib.Topology.MetricSpace.Basic")
    support_dep = Dependency(name="support_helper", module="Mathlib.Topology.EMetricSpace.Basic")
    external_dep = Dependency(name="external_helper", module="Mathlib.Analysis.Normed.Basic")
    target = DeclarationRecord(
        name="target",
        statement="P",
        proof_date=date(2024, 4, 1),
        module="Mathlib.Topology.MetricSpace.Basic",
        namespace="Topology",
        commit="b",
        dependencies=(target_dep, support_dep, external_dep),
    )
    support = DeclarationRecord(
        name="support_helper",
        statement="Q",
        proof_date=date(2024, 1, 1),
        module="Mathlib.Topology.EMetricSpace.Basic",
        namespace="Topology",
        commit="a",
    )
    scope = ModuleScope(
        name="topology",
        target_module_prefixes=("Mathlib.Topology.MetricSpace",),
        support_module_prefixes=("Mathlib.Topology.EMetricSpace",),
    )

    report = scope_report([target, support], scope)

    audit = report["dependency_audit"]
    assert audit["dependency_reference_role_counts"]["target"] == 1
    assert audit["dependency_reference_role_counts"]["support"] == 1
    assert audit["dependency_reference_role_counts"]["out_of_scope"] == 1
    assert audit["target_declarations_with_scoped_dependency"] == 1
    assert audit["mean_scoped_dependencies_per_target"] == 2.0


def test_target_names_filter_scoring_contexts_without_dropping_support() -> None:
    support = record("support", "forall x, x * 1 = x", 1)
    target = record("target", "forall y, y * 1 = y", 4)
    snapshots = [Snapshot("2024Q1", date(2024, 1, 1), "a", ("support",))]
    contexts, footprints_by_decl = build_retrieval_prior_contexts(
        [support, target],
        [footprint("support", "namespace:Algebra"), footprint("target", "namespace:Algebra")],
        encoder=ToyStatementEncoder(),
        snapshots=snapshots,
        target_names={"target"},
    )
    assert set(footprints_by_decl) == {"support", "target"}
    assert [context.target.name for context in contexts] == ["target"]
    assert contexts[0].retrieval_hits[0].name == "support"


def test_packet_source_extraction_falls_back_to_module_directory(tmp_path) -> None:
    source = tmp_path / "Mathlib" / "Topology" / "Separation" / "Basic.lean"
    source.parent.mkdir(parents=True)
    source.write_text(
        "namespace SeparationQuotient\n"
        "theorem t2Space_iff : True := by\n"
        "  trivial\n"
        "\n"
        "theorem next_decl : True := by\n"
        "  trivial\n",
        encoding="utf-8",
    )
    record = DeclarationRecord(
        name="SeparationQuotient.t2Space_iff",
        statement="True",
        proof_date=date(2024, 1, 1),
        module="Mathlib.Topology.Separation",
        namespace="SeparationQuotient",
        commit="abc",
    )

    extracted = extract_lean_source(record, tmp_path)

    assert "theorem t2Space_iff" in extracted
    assert "next_decl" not in extracted


def test_packet_human_argument_summary_has_no_fallback_text() -> None:
    record = DeclarationRecord(
        name="Topology.example",
        statement="forall x, x = x",
        proof_date=date(2024, 1, 1),
        module="Mathlib.Topology.Basic",
        namespace="Topology",
        commit="abc",
    )
    score = NoveltyScore(
        declaration=record.name,
        snapshot_id="2024Q1",
        threshold=5,
        surprisal=12.5,
        mean_item_surprisal=3.0,
        prior_mass=0.2,
        item_scores=(
            {
                "family": "namespace:Mathlib.Topology.Compactness",
                "raw_name": "IsCompact.foo",
                "weighted_surprisal": 4.0,
            },
        ),
    )
    fp = Footprint(
        declaration=record.name,
        snapshot_id="2024Q1",
        threshold=5,
        items=(
            FootprintItem(
                family="namespace:Mathlib.Topology.Compactness",
                raw_name="IsCompact.foo",
                weight=1.0,
                backoff_depth=1,
                support=10,
            ),
        ),
        filtered_dependencies=("IsCompact.foo",),
    )

    summary = human_argument_summary(record, score, fp)

    assert summary == ""
    assert "surprisal" not in summary
    assert "footprint" not in summary
    assert "namespace:Mathlib.Topology.Compactness" not in summary
    assert "IsCompact.foo" not in summary
    assert "Lean" not in summary


def test_packet_side_is_public_until_private_score_is_attached() -> None:
    record = DeclarationRecord(
        name="Topology.example",
        statement="forall x, x = x",
        proof_date=date(2024, 1, 1),
        module="Mathlib.Topology.Basic",
        namespace="Topology",
        commit="abc",
    )
    score = NoveltyScore(
        declaration=record.name,
        snapshot_id="2024Q1",
        threshold=5,
        surprisal=12.5,
        mean_item_surprisal=3.0,
        prior_mass=0.2,
        item_scores=(),
    )

    side = packet_side(record, score)

    assert "score" not in side
    private_side = {**side, "score": {"surprisal": 12.5}}
    public = public_side(private_side)
    assert "score" not in public
    assert "module" not in public
    assert "namespace" not in public


def test_missing_narratives_are_hard_errors_for_public_consumers() -> None:
    packet = {
        "pairs": [
            {
                "pair_id": "p1",
                "left": {"name": "left", "human_argument": ""},
                "right": {"name": "right", "human_argument": "A real proof narrative."},
            }
        ]
    }

    assert missing_narratives(packet) == ["p1:left:left"]
    try:
        require_complete_narratives(packet, context="test")
    except ValueError as exc:
        assert "requires proof narratives" in str(exc)
    else:
        raise AssertionError("missing narratives should be rejected")


def test_proof_narrative_prompt_hides_metric_internals() -> None:
    prompt = build_prompt(
        {
            "name": "Topology.example",
            "statement": "Every compact subset is Lindelof.",
            "lean_source": "theorem example : True := by trivial",
        }
    )

    assert "surprisal" not in prompt.lower()
    assert "score" not in prompt.lower()
    assert "footprint" not in prompt.lower()
    assert "prior" not in prompt.lower()
    validate_narrative("The proof takes a finite subcover and observes that finite covers are countable.")
    validate_narrative("The construction first handles the higher-priority neighborhood condition.")


def test_proof_narrative_rejects_formal_identifiers() -> None:
    rejected = [
        "This follows from Metric.closedBall and compactness.",
        "The result rewrites IsCompact A as compactness of the image.",
        "The proof shows A ↔ B by applying the neighborhood filter 𝓝.",
        "The coLindelof filter is handled by rewriting nhds.",
        "The proof uses f '' s to describe the image.",
    ]
    for narrative in rejected:
        try:
            validate_narrative(narrative)
        except RuntimeError:
            continue
        raise AssertionError(f"narrative should be rejected: {narrative}")


def test_existing_packet_narratives_apply_to_duplicate_declarations() -> None:
    packet = {
        "pairs": [
            {
                "left": {"name": "same", "human_argument": "Use compactness to choose a finite subcover."},
                "right": {"name": "other", "human_argument": ""},
            },
            {
                "left": {"name": "same", "human_argument": ""},
                "right": {"name": "other", "human_argument": ""},
            },
        ]
    }

    apply_narratives(packet, packet_narratives(packet))

    assert packet["pairs"][1]["left"]["human_argument"] == "Use compactness to choose a finite subcover."


def test_find_declaration_start_matches_short_namespaced_name() -> None:
    lines = ["namespace Metric", "theorem cobounded_eq_cocompact : True := by", "  trivial"]

    assert find_declaration_start(lines, "Metric.cobounded_eq_cocompact") == 1


def test_find_declaration_start_matches_qualified_source_name() -> None:
    lines = [
        "lemma Topology.IsInducing.isCompact_preimage_iff {f : X → Y} : True := by",
        "  trivial",
    ]

    assert find_declaration_start(lines, "Inducing.isCompact_preimage_iff") == 0


def test_find_declaration_start_matches_alias_source_name() -> None:
    lines = [
        "theorem isCompact_iff_ultrafilter_le_nhds' : True := by",
        "  trivial",
        "alias ⟨IsCompact.ultrafilter_le_nhds', _⟩ := isCompact_iff_ultrafilter_le_nhds'",
    ]

    assert find_declaration_start(lines, "IsCompact.ultrafilter_le_nhds'") == 0


def test_find_declaration_start_matches_generated_mk_iff_name() -> None:
    lines = [
        "@[mk_iff]",
        "class R0Space (X : Type u) [TopologicalSpace X] : Prop where",
        "  specializes_symm : True",
    ]

    assert find_declaration_start(lines, "r0Space_iff") == 0


def test_find_declaration_start_matches_renamed_separated_nhds_name() -> None:
    lines = ["theorem SeparatedNhds.of_finset_finset [T2Space X] : True := by", "  trivial"]

    assert find_declaration_start(lines, "separatedNhds_of_finset_finset") == 0


def test_llm_baseline_evaluator_reports_accuracy_and_missing_responses() -> None:
    answer_key = [
        {
            "pair_id": "p1",
            "metric_preference": "left",
            "source": "canonical",
            "score_gap": 10.0,
        },
        {
            "pair_id": "p2",
            "metric_preference": "right",
            "source": "stratified",
            "score_gap": 3.0,
        },
    ]
    requests = [
        {"pair_id": "p1", "model": "m1", "strictness": "strict"},
        {"pair_id": "p2", "model": "m1", "strictness": "strict"},
    ]
    responses = [
        {"pair_id": "p1", "model": "m1", "strictness": "strict", "raw_response": "Left."},
    ]

    report = evaluate_llm_baseline(responses, answer_key, requests=requests)

    assert report["response_count"] == 1
    assert report["missing_response_count"] == 1
    assert report["summary"]["all"]["accuracy"] == 1.0
    assert report["summary"]["source:canonical"]["n"] == 1.0
    assert report["missing_responses"][0]["pair_id"] == "p2"


def test_llm_baseline_response_key_uses_pair_model_and_strictness() -> None:
    assert response_key({"pair_id": "p1", "model": "m", "strictness": "strict"}) == ("p1", "m", "strict")


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
