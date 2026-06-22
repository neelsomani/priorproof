from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from priorproof.data.models import DeclarationRecord, Footprint, NoveltyScore


RATER_PROMPT = "Which proof uses the less standard mathematical route to its result?"


def score_lookup(scores: Iterable[NoveltyScore]) -> dict[str, NoveltyScore]:
    return {score.declaration: score for score in scores}


def footprint_lookup(footprints: Iterable[Footprint]) -> dict[str, Footprint]:
    return {footprint.declaration: footprint for footprint in footprints}


def module_source_path(mathlib_repo: str | Path, module: str) -> Path:
    return Path(mathlib_repo) / Path(*module.split(".")).with_suffix(".lean")


def extract_lean_source(
    record: DeclarationRecord,
    mathlib_repo: str | Path | None,
    max_lines: int = 160,
) -> str:
    if not mathlib_repo:
        return ""
    for path in candidate_source_paths(mathlib_repo, record):
        lines = path.read_text(encoding="utf-8").splitlines()
        start = find_declaration_start(lines, record.name)
        if start is None:
            continue
        end = min(len(lines), start + max_lines)
        for idx in range(start + 1, min(len(lines), start + max_lines)):
            if is_declaration_boundary(lines[idx]):
                end = idx
                break
        return "\n".join(lines[start:end]).strip()
    return ""


def candidate_source_paths(mathlib_repo: str | Path, record: DeclarationRecord) -> list[Path]:
    repo = Path(mathlib_repo)
    primary = module_source_path(repo, record.module)
    paths: list[Path] = []
    if primary.exists():
        paths.append(primary)
    module_dir = repo / Path(*record.module.split("."))
    if module_dir.exists() and module_dir.is_dir():
        paths.extend(sorted(module_dir.rglob("*.lean")))
    mathlib_root = repo / "Mathlib"
    if mathlib_root.exists():
        needles = tuple(source_name_candidates(record.name))
        for path in sorted(mathlib_root.rglob("*.lean")):
            if path in paths:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if any(needle in text for needle in needles):
                paths.append(path)
    return paths


def source_name_candidates(declaration_name: str) -> list[str]:
    short_name = declaration_name.rsplit(".", 1)[-1]
    candidates = [declaration_name]
    if short_name != declaration_name:
        candidates.append(short_name)
    if short_name.startswith("separatedNhds_of_"):
        suffix = short_name.removeprefix("separatedNhds_of_")
        candidates.append(f"SeparatedNhds.of_{suffix}")
    return list(dict.fromkeys(candidates))


def find_declaration_start(lines: list[str], declaration_name: str) -> int | None:
    names = source_name_candidates(declaration_name)
    for idx, line in enumerate(lines):
        for name in names:
            pattern = re.compile(
                r"^\s*(?:private\s+|protected\s+|noncomputable\s+|unsafe\s+)*"
                r"(?:theorem|lemma|def|abbrev|instance|axiom|class)\s+"
                + re.escape(name)
                + r"(?:\s|:|\(|\[|$)"
            )
            if pattern.search(line):
                return idx
            if alias_line_names_declaration(line, name):
                previous = previous_declaration_start(lines, idx)
                return idx if previous is None else previous
            if mk_iff_line_names_declaration(lines, idx, name):
                return idx
        short_name = declaration_name.rsplit(".", 1)[-1]
        qualified_short = re.compile(
            r"^\s*(?:private\s+|protected\s+|noncomputable\s+|unsafe\s+)*"
            r"(?:theorem|lemma|def|abbrev|instance|axiom|class)\s+"
            r"(?:[A-Za-z0-9_'.]+\.)+"
            + re.escape(short_name)
            + r"(?:\s|:|\(|\[|$)"
        )
        if qualified_short.search(line):
            return idx
    return None


def alias_line_names_declaration(line: str, declaration_name: str) -> bool:
    alias_match = re.search(r"^\s*alias\b(?P<body>.*)$", line)
    if not alias_match:
        return False
    declaration_pattern = (
        r"(?<![A-Za-z0-9_'.])"
        + re.escape(declaration_name)
        + r"(?![A-Za-z0-9_'.])"
    )
    return re.search(declaration_pattern, alias_match.group("body")) is not None


def mk_iff_line_names_declaration(lines: list[str], idx: int, declaration_name: str) -> bool:
    line = lines[idx].strip()
    mk_iff_match = re.match(r"^@\[\s*mk_iff(?:\s+(?P<explicit>[A-Za-z0-9_'.]+))?\s*\]", line)
    if not mk_iff_match:
        return False
    explicit = mk_iff_match.group("explicit")
    if explicit:
        return explicit == declaration_name
    for follow in lines[idx + 1 : min(len(lines), idx + 4)]:
        class_match = re.match(r"^\s*class\s+(?P<class_name>[A-Za-z0-9_'.]+)\b", follow)
        if not class_match:
            continue
        class_name = class_match.group("class_name").rsplit(".", 1)[-1]
        if class_name:
            generated = class_name[0].lower() + class_name[1:] + "_iff"
            return generated == declaration_name
    return False


def previous_declaration_start(lines: list[str], before_idx: int) -> int | None:
    for idx in range(before_idx - 1, -1, -1):
        if is_declaration_boundary(lines[idx]):
            return idx
    return None


def is_declaration_boundary(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:private\s+|protected\s+|noncomputable\s+|unsafe\s+)*"
            r"(?:theorem|lemma|def|abbrev|instance|axiom|class|structure|inductive|alias)\s+",
            line,
        )
    )


def packet_side(
    record: DeclarationRecord,
    score: NoveltyScore,
    footprint: Footprint | None = None,
    lean_source: str = "",
) -> dict[str, object]:
    return {
        "name": record.name,
        "module": record.module,
        "namespace": record.namespace,
        "statement": record.statement,
        "lean_source": lean_source,
        "human_argument": human_argument_summary(record, score, footprint),
    }


def human_argument_summary(
    record: DeclarationRecord,
    score: NoveltyScore | None = None,
    footprint: Footprint | None = None,
) -> str:
    _ = record, score, footprint
    return ""


def score_payload(score: NoveltyScore) -> dict[str, object]:
    return {
        "surprisal": score.surprisal,
        "mean_item_surprisal": score.mean_item_surprisal,
        "prior_mass": score.prior_mass,
        "threshold": score.threshold,
        "snapshot_id": score.snapshot_id,
        "item_count": len(score.item_scores),
        "top_items": top_score_items(score, limit=8),
    }


def public_side(side: dict[str, object]) -> dict[str, object]:
    private_keys = {"score", "module", "namespace"}
    return {key: value for key, value in side.items() if key not in private_keys}


def missing_narratives(packet: dict[str, object]) -> list[str]:
    missing: list[str] = []
    for pair in packet.get("pairs", []):
        if not isinstance(pair, dict):
            continue
        pair_id = str(pair.get("pair_id", "<unknown>"))
        for side_label in ("left", "right"):
            side = pair.get(side_label)
            if not isinstance(side, dict):
                missing.append(f"{pair_id}:{side_label}")
                continue
            if not str(side.get("human_argument", "")).strip():
                name = str(side.get("name", side_label))
                missing.append(f"{pair_id}:{side_label}:{name}")
    return missing


def require_complete_narratives(packet: dict[str, object], *, context: str) -> None:
    missing = missing_narratives(packet)
    if missing:
        preview = ", ".join(missing[:8])
        suffix = "" if len(missing) <= 8 else f", ... ({len(missing)} total)"
        raise ValueError(f"{context} requires proof narratives for every side; missing {preview}{suffix}")


def top_families(score: NoveltyScore, limit: int) -> list[str]:
    ordered = sorted(
        score.item_scores,
        key=lambda item: float(item.get("weighted_surprisal", item.get("surprisal", 0.0))),
        reverse=True,
    )
    result: list[str] = []
    for item in ordered:
        family = str(item.get("family", ""))
        if family and family not in result:
            result.append(family)
        if len(result) >= limit:
            break
    return result


def top_score_items(score: NoveltyScore, limit: int) -> list[dict[str, object]]:
    ordered = sorted(
        score.item_scores,
        key=lambda item: float(item.get("weighted_surprisal", item.get("surprisal", 0.0))),
        reverse=True,
    )
    return [
        {
            "family": str(item.get("family", "")),
            "raw_name": str(item.get("raw_name", "")),
            "weighted_surprisal": float(item.get("weighted_surprisal", 0.0)),
            "probability": float(item.get("probability", 0.0)),
        }
        for item in ordered[:limit]
    ]


def top_dependencies(footprint: Footprint, limit: int) -> list[str]:
    ordered = sorted(footprint.items, key=lambda item: item.weight, reverse=True)
    return [item.raw_name for item in ordered[:limit]]


def metric_preference(left: NoveltyScore, right: NoveltyScore) -> str:
    if left.surprisal > right.surprisal:
        return "left"
    if right.surprisal > left.surprisal:
        return "right"
    return "tie"
