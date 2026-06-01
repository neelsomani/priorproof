from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from ..data.models import DeclarationRecord, Snapshot


@dataclass(frozen=True)
class SnapshotSpec:
    snapshot_id: str
    start_date: date
    commit: str = ""


def assign_quarter(value: date) -> str:
    quarter = ((value.month - 1) // 3) + 1
    return f"{value.year}Q{quarter}"


def build_quarterly_snapshots(
    declarations: Iterable[DeclarationRecord],
    commits_by_quarter: dict[str, str] | None = None,
) -> list[Snapshot]:
    """Build start-of-quarter slices from declaration dates.

    A declaration belongs to a snapshot only if it predates the quarter start,
    which gives each target a prior corpus built from earlier library state.
    """

    commits_by_quarter = commits_by_quarter or {}
    records = sorted(declarations, key=lambda item: (item.proof_date, item.name))
    quarters = sorted({assign_quarter(record.proof_date) for record in records})
    starts = {quarter: _quarter_start(quarter) for quarter in quarters}
    snapshots: list[Snapshot] = []
    for quarter in quarters:
        start = starts[quarter]
        names = tuple(record.name for record in records if record.proof_date < start)
        snapshots.append(
            Snapshot(
                snapshot_id=quarter,
                start_date=start,
                commit=commits_by_quarter.get(quarter, ""),
                declarations=names,
            )
        )
    return snapshots


def _quarter_start(quarter: str) -> date:
    year = int(quarter[:4])
    q = int(quarter[-1])
    return date(year, 1 + (q - 1) * 3, 1)


def snapshot_for_target(target: DeclarationRecord, snapshots: Iterable[Snapshot]) -> Snapshot | None:
    candidates = [snapshot for snapshot in snapshots if snapshot.start_date <= target.proof_date]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.start_date)


def declarations_before(
    target: DeclarationRecord,
    declarations_by_name: dict[str, DeclarationRecord],
    snapshot: Snapshot,
) -> list[DeclarationRecord]:
    return [
        declarations_by_name[name]
        for name in snapshot.declarations
        if name in declarations_by_name and declarations_by_name[name].proof_date < target.proof_date
    ]


def compute_reuse_counts(declarations: Iterable[DeclarationRecord]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in declarations:
        for dep in record.dependencies:
            counts[dep.name] += 1
    return counts


def dependency_adjacency(records: Iterable[DeclarationRecord]) -> dict[str, set[str]]:
    """Return proof-introduced dependency edges parent -> children."""

    graph: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for parent, child in record.dependency_edges:
            graph[parent].add(child)
    return dict(graph)


def module_density_by_snapshot(
    declarations: Iterable[DeclarationRecord],
    snapshots: Iterable[Snapshot],
) -> list[dict[str, object]]:
    by_name = {record.name: record for record in declarations}
    rows: list[dict[str, object]] = []
    for snapshot in snapshots:
        module_counts: Counter[str] = Counter()
        namespace_counts: Counter[str] = Counter()
        for name in snapshot.declarations:
            record = by_name.get(name)
            if record is None:
                continue
            module_counts[record.module] += 1
            namespace_counts[record.namespace] += 1
        rows.append(
            {
                "snapshot_id": snapshot.snapshot_id,
                "start_date": snapshot.start_date.isoformat(),
                "declaration_count": len(snapshot.declarations),
                "top_modules": module_counts.most_common(20),
                "top_namespaces": namespace_counts.most_common(20),
            }
        )
    return rows

