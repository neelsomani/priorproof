from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path

from .snapshots import (
    build_quarterly_snapshots,
    compute_reuse_counts,
    declarations_before,
    dependency_adjacency,
    snapshot_for_target,
)
from ..metric.filtering import DependencyFilter
from ..metric.frontier import established_frontier
from ..data.io import read_json, read_jsonl, write_json, write_jsonl
from ..data.models import DeclarationRecord, Dependency, Footprint, Snapshot
from ..modeling.prior import PriorConfig, build_hierarchical_prior
from ..metric.redundancy import detect_redundant_subterms, exact_wrapper_flags
from ..modeling.retriever import StatementEmbeddingModel, StatementRetriever
from ..metric.scoring import score_footprint


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
    output: list[Footprint] = []
    for record in sorted(declarations, key=lambda item: (item.proof_date, item.name)):
        snapshot = snapshot_for_target(record, snapshots)
        if snapshot is None:
            continue
        pre_t_records = declarations_before(record, by_name, snapshot)
        reuse_counts = compute_reuse_counts(pre_t_records)
        dependency_lookup = dependency_lookup_for(pre_t_records, record)
        graph = dependency_adjacency(pre_t_records + [record])
        filtered = dep_filter.apply(record.dependencies)
        redundancy_hits = tuple(detect_redundant_subterms(record, pre_t_records)) + tuple(
            exact_wrapper_flags(record, set(snapshot.declarations))
        )
        redundant_raw_names = {name for hit in redundancy_hits for name in hit.raw_dependencies}
        footprint = established_frontier(
            record=record,
            snapshot=snapshot,
            reuse_counts=reuse_counts,
            dependency_lookup=dependency_lookup,
            dependency_graph=graph,
            threshold=threshold,
            filtered_dependencies=filtered,
            redundant_raw_names=redundant_raw_names,
            min_family_support=min_family_support,
        )
        output.append(
            replace(footprint, redundant_subterms=tuple(hit.to_json() for hit in redundancy_hits))
        )
    return output


def dependency_lookup_for(
    pre_t_records: list[DeclarationRecord],
    target: DeclarationRecord,
) -> dict[str, Dependency]:
    lookup: dict[str, Dependency] = {}
    for record in pre_t_records + [target]:
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
    if encoder is None and not encoders_by_snapshot:
        raise ValueError("Either encoder or encoders_by_snapshot is required")
    by_name = {record.name: record for record in declarations}
    footprints_by_decl = {footprint.declaration: footprint for footprint in footprints}
    snapshots_by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots or []}
    scores = []
    prior_rows = []
    for target_name, footprint in footprints_by_decl.items():
        target = by_name.get(target_name)
        if target is None:
            continue
        snapshot = snapshots_by_id.get(footprint.snapshot_id)
        if snapshot is not None:
            pre_t_records = [
                by_name[name]
                for name in snapshot.declarations
                if name in by_name and name in footprints_by_decl
            ]
        else:
            pre_t_records = [
                record
                for record in declarations
                if record.proof_date < target.proof_date and record.name in footprints_by_decl
            ]
        active_encoder = encoder_for_snapshot(footprint.snapshot_id, encoder, encoders_by_snapshot)
        retriever = StatementRetriever(active_encoder, pre_t_records)
        hits = retriever.query(target, k=k)
        prior = build_hierarchical_prior(target, pre_t_records, footprints_by_decl, hits, config)
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
