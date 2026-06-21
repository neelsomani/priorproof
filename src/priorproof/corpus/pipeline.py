from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from .snapshots import (
    build_quarterly_snapshots,
    compute_reuse_counts,
    declarations_before,
    dependency_adjacency,
    snapshot_for_target,
)
from ..metric.filtering import DependencyFilter
from ..metric.families import family_supports
from ..metric.frontier import established_frontier
from ..data.io import read_json, read_jsonl, write_json, write_jsonl
from ..data.models import DeclarationRecord, Dependency, Footprint, Snapshot
from ..modeling.prior import PriorConfig, PriorCountState, build_hierarchical_prior, build_prior_count_state
from ..metric.redundancy import build_statement_index, detect_redundant_subterms, exact_wrapper_flags
from ..modeling.retriever import StatementEmbeddingModel, StatementRetriever
from ..metric.scoring import score_footprint


@dataclass(frozen=True)
class RetrievalPriorContext:
    target: DeclarationRecord
    footprint: Footprint
    retrieval_hits: list
    count_state: PriorCountState


def load_declarations(path: str | Path) -> list[DeclarationRecord]:
    return list(read_jsonl(path, DeclarationRecord.from_json))


def load_snapshots(path: str | Path) -> list[Snapshot]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError("snapshot file must contain a JSON list")
    return [Snapshot.from_json(item) for item in data]


def load_footprints(path: str | Path) -> list[Footprint]:
    rows = []
    for row in read_jsonl(path):
        rows.append(footprint_from_json(row))
    return rows


def footprint_from_json(data: dict) -> Footprint:
    from ..data.models import FootprintItem

    return Footprint(
        declaration=str(data["declaration"]),
        snapshot_id=str(data["snapshot_id"]),
        threshold=int(data["threshold"]),
        items=tuple(
            FootprintItem(
                family=str(item["family"]),
                raw_name=str(item["raw_name"]),
                weight=float(item["weight"]),
                backoff_depth=int(item["backoff_depth"]),
                support=int(item["support"]),
            )
            for item in data.get("items", [])
        ),
        filtered_dependencies=tuple(str(name) for name in data.get("filtered_dependencies", [])),
        redundant_subterms=tuple(dict(item) for item in data.get("redundant_subterms", [])),
    )


def build_footprints(
    declarations: list[DeclarationRecord],
    snapshots: list[Snapshot] | None,
    threshold: int,
    dep_filter: DependencyFilter | None = None,
    min_family_support: int = 5,
) -> list[Footprint]:
    snapshots = snapshots or build_quarterly_snapshots(declarations)
    dep_filter = dep_filter or DependencyFilter()
    by_name = {record.name: record for record in declarations}
    states = {
        snapshot.snapshot_id: snapshot_state(snapshot, by_name)
        for snapshot in snapshots
    }
    output: list[Footprint] = []
    for record in sorted(declarations, key=lambda item: (item.proof_date, item.name)):
        snapshot = snapshot_for_target(record, snapshots)
        if snapshot is None:
            continue
        state = states[snapshot.snapshot_id]
        graph = dependency_graph_for_target(state["dependency_graph"], record)
        filtered = dep_filter.apply(record.dependencies)
        redundancy_hits = tuple(
            detect_redundant_subterms(record, statement_index=state["statement_index"])
        ) + tuple(
            exact_wrapper_flags(record, state["declaration_names"])
        )
        redundant_raw_names = {name for hit in redundancy_hits for name in hit.raw_dependencies}
        footprint = established_frontier(
            record=record,
            snapshot=snapshot,
            reuse_counts=state["reuse_counts"],
            dependency_lookup=state["dependency_lookup"],
            dependency_graph=graph,
            threshold=threshold,
            filtered_dependencies=filtered,
            redundant_raw_names=redundant_raw_names,
            min_family_support=min_family_support,
            supports=state["family_supports"],
        )
        output.append(
            replace(footprint, redundant_subterms=tuple(hit.to_json() for hit in redundancy_hits))
        )
    return output


def snapshot_state(snapshot: Snapshot, by_name: dict[str, DeclarationRecord]) -> dict[str, object]:
    records = [by_name[name] for name in snapshot.declarations if name in by_name]
    reuse_counts = compute_reuse_counts(records)
    dependency_lookup = dependency_lookup_for(records)
    dependency_graph = dependency_adjacency(records)
    supported_dependencies = [
        dep for name, dep in dependency_lookup.items() if reuse_counts.get(name, 0) > 0
    ]
    return {
        "records": records,
        "declaration_names": set(snapshot.declarations),
        "reuse_counts": reuse_counts,
        "dependency_lookup": dependency_lookup,
        "dependency_graph": dependency_graph,
        "family_supports": family_supports(supported_dependencies),
        "statement_index": build_statement_index(records),
    }


def dependency_graph_for_target(
    base_graph: dict[str, set[str]],
    target: DeclarationRecord,
) -> dict[str, set[str]]:
    if not target.dependency_edges:
        return base_graph
    graph = {name: set(children) for name, children in base_graph.items()}
    for parent, child in target.dependency_edges:
        graph.setdefault(parent, set()).add(child)
    return graph


def dependency_lookup_for(
    pre_t_records: list[DeclarationRecord],
    target: DeclarationRecord | None = None,
) -> dict[str, Dependency]:
    lookup: dict[str, Dependency] = {}
    records = pre_t_records if target is None else pre_t_records + [target]
    for record in records:
        for dep in record.dependencies:
            lookup.setdefault(dep.name, dep)
    return lookup


def score_with_retrieval_prior(
    declarations: list[DeclarationRecord],
    footprints: list[Footprint],
    encoder: StatementEmbeddingModel | None = None,
    encoders_by_snapshot: dict[str, StatementEmbeddingModel] | None = None,
    config: PriorConfig | None = None,
    k: int = 32,
    snapshots: list[Snapshot] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    contexts, footprints_by_decl = build_retrieval_prior_contexts(
        declarations,
        footprints,
        encoder,
        encoders_by_snapshot=encoders_by_snapshot,
        k=k,
        snapshots=snapshots,
    )
    return score_retrieval_prior_contexts(contexts, footprints_by_decl, config)


def build_retrieval_prior_contexts(
    declarations: list[DeclarationRecord],
    footprints: list[Footprint],
    encoder: StatementEmbeddingModel | None = None,
    encoders_by_snapshot: dict[str, StatementEmbeddingModel] | None = None,
    k: int = 32,
    snapshots: list[Snapshot] | None = None,
) -> tuple[list[RetrievalPriorContext], dict[str, Footprint]]:
    if encoder is None and not encoders_by_snapshot:
        raise ValueError("Either encoder or encoders_by_snapshot is required")
    by_name = {record.name: record for record in declarations}
    footprints_by_decl = {footprint.declaration: footprint for footprint in footprints}
    snapshots_by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots or []}
    scoring_states: dict[str, dict[str, object]] = {}
    contexts: list[RetrievalPriorContext] = []
    for target_name, footprint in footprints_by_decl.items():
        target = by_name.get(target_name)
        if target is None:
            continue
        snapshot = snapshots_by_id.get(footprint.snapshot_id)
        if snapshot is not None:
            if footprint.snapshot_id not in scoring_states:
                pre_t_records = [
                    by_name[name]
                    for name in snapshot.declarations
                    if name in by_name and name in footprints_by_decl
                ]
                if pre_t_records:
                    active_encoder = encoder_for_snapshot(footprint.snapshot_id, encoder, encoders_by_snapshot)
                    scoring_states[footprint.snapshot_id] = {
                        "pre_t_records": pre_t_records,
                        "retriever": StatementRetriever(active_encoder, pre_t_records),
                        "count_state": build_prior_count_state(pre_t_records, footprints_by_decl),
                    }
                else:
                    scoring_states[footprint.snapshot_id] = {
                        "pre_t_records": [],
                        "retriever": None,
                        "count_state": None,
                    }
            state = scoring_states[footprint.snapshot_id]
            pre_t_records = state["pre_t_records"]
            retriever = state["retriever"]
            count_state = state["count_state"]
        else:
            pre_t_records = [
                record
                for record in declarations
                if record.proof_date < target.proof_date and record.name in footprints_by_decl
            ]
            if not pre_t_records:
                continue
            active_encoder = encoder_for_snapshot(footprint.snapshot_id, encoder, encoders_by_snapshot)
            retriever = StatementRetriever(active_encoder, pre_t_records)
            count_state = build_prior_count_state(pre_t_records, footprints_by_decl)
        if not pre_t_records or retriever is None:
            continue
        hits = retriever.query(target, k=k)
        contexts.append(
            RetrievalPriorContext(
                target=target,
                footprint=footprint,
                retrieval_hits=hits,
                count_state=count_state,
            )
        )
    return contexts, footprints_by_decl


def score_retrieval_prior_contexts(
    contexts: list[RetrievalPriorContext],
    footprints_by_decl: dict[str, Footprint],
    config: PriorConfig | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    scores = []
    prior_rows = []
    for context in contexts:
        target = context.target
        footprint = context.footprint
        hits = context.retrieval_hits
        prior = build_hierarchical_prior(
            target,
            [],
            footprints_by_decl,
            hits,
            config,
            count_state=context.count_state,
        )
        score = score_footprint(
            footprint,
            prior,
            flags=tuple("redundant_subterm" for _ in footprint.redundant_subterms),
        )
        scores.append(score.to_json())
        prior_rows.append(
            {
                "declaration": target.name,
                "snapshot_id": footprint.snapshot_id,
                "threshold": footprint.threshold,
                "retrieval_hits": [hit.to_json() for hit in hits],
                "prior": prior,
            }
        )
    return scores, prior_rows


def encoder_for_snapshot(
    snapshot_id: str,
    encoder: StatementEmbeddingModel | None,
    encoders_by_snapshot: dict[str, StatementEmbeddingModel] | None,
) -> StatementEmbeddingModel:
    if encoders_by_snapshot:
        try:
            return encoders_by_snapshot[snapshot_id]
        except KeyError as exc:
            raise ValueError(f"No encoder configured for snapshot {snapshot_id!r}") from exc
    if encoder is None:
        raise ValueError("No encoder configured")
    return encoder


def save_snapshots(path: str | Path, snapshots: list[Snapshot]) -> None:
    write_json(path, [snapshot.to_json() for snapshot in snapshots])


def save_footprints(path: str | Path, footprints: list[Footprint]) -> None:
    write_jsonl(path, footprints)


def family_histogram(footprints: list[Footprint]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for footprint in footprints:
        counts.update(footprint.families())
    return counts
