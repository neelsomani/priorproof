#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from priorproof.cli.make_rater_ui import render_html  # noqa: E402
from priorproof.evaluation.packets import require_complete_narratives  # noqa: E402


DEFAULT_PACKET = ROOT / "artifacts/topology/study_packet/study_packet_with_narratives.json"
DEFAULT_OUT_DIR = ROOT / "release/study_packet"
FORBIDDEN_RELEASE_KEYS = {
    "answer_key",
    "canonical_case_id",
    "canonical_pair_count",
    "left_score",
    "metric_preference",
    "right_score",
    "score",
    "score_delta",
    "score_gap",
    "source",
    "stratified_pair_count",
    "surprisal",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the commit-ready blinded rater release folder.")
    parser.add_argument(
        "--packet",
        type=Path,
        default=DEFAULT_PACKET,
        help="Cleaned study_packet_with_narratives.json to sanitize for rater release.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Release directory to create. Defaults to release/study_packet.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove an existing release directory before writing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    packet_path = args.packet.resolve()
    out_dir = args.out_dir.resolve()

    if out_dir.exists():
        if not args.force:
            raise SystemExit(f"{out_dir} already exists; rerun with --force to replace it.")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    packet = read_packet(packet_path)
    blinded_packet = sanitize_packet(packet)
    require_complete_narratives(blinded_packet, context="release packet")
    assert_no_forbidden_keys(blinded_packet)

    packet_out = out_dir / "study_packet_blinded.json"
    ui_out = out_dir / "rater_ui.html"
    readme_out = out_dir / "README.md"
    manifest_out = out_dir / "MANIFEST.json"

    write_json(packet_out, blinded_packet)
    payload = json.dumps(blinded_packet).replace("</", "<\\/")
    ui_out.write_text(render_html(payload), encoding="utf-8")
    readme_out.write_text(render_readme(blinded_packet), encoding="utf-8")
    manifest = build_manifest(packet_path, out_dir, blinded_packet)
    write_json(manifest_out, manifest)

    print(f"Wrote release folder: {out_dir}")
    print(f"Pairs: {blinded_packet['pair_count']}")
    print("Files:")
    for path in sorted(out_dir.iterdir()):
        print(f"  {path.relative_to(ROOT)}")


def read_packet(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Packet not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
        raise SystemExit(f"Packet must be a JSON object with a pairs list: {path}")
    return data


def sanitize_packet(packet: dict[str, Any]) -> dict[str, Any]:
    pairs = []
    for pair in packet["pairs"]:
        pairs.append(
            {
                "pair_id": str(pair["pair_id"]),
                "prompt": str(pair["prompt"]),
                "left": sanitize_side(pair["left"]),
                "right": sanitize_side(pair["right"]),
            }
        )
    return {
        "name": str(packet.get("name", "topology_rater_packet")),
        "prompt": str(packet.get("prompt", "Which proof uses the less standard mathematical route to its result?")),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


def sanitize_side(side: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(side.get("name", "")),
        "statement": str(side.get("statement", "")),
        "human_argument": str(side.get("human_argument", "")),
        "lean_source": str(side.get("lean_source", "")),
    }


def assert_no_forbidden_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_RELEASE_KEYS:
                raise SystemExit(f"Forbidden release key {key!r} at {path}")
            assert_no_forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_forbidden_keys(child, f"{path}[{index}]")


def render_readme(packet: dict[str, Any]) -> str:
    return f"""# PriorProof Rater Packet

This folder contains the blinded rater materials for PriorProof.

## Instructions

1. Open `rater_ui.html` in a browser.
2. Answer every pair.
3. Click `Download responses`.
4. Send the downloaded `priorproof_rater_responses.jsonl` file back without editing it.

The packet contains {packet["pair_count"]} pairs. The answer key and metric scores are not included in
this release folder.
"""


def build_manifest(source_packet: Path, out_dir: Path, packet: dict[str, Any]) -> dict[str, Any]:
    files = {}
    for path in sorted(out_dir.iterdir()):
        if path.name == "MANIFEST.json":
            continue
        files[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_packet": str(source_packet.relative_to(ROOT)) if source_packet.is_relative_to(ROOT) else str(source_packet),
        "pair_count": packet["pair_count"],
        "contains_answer_key": False,
        "contains_metric_scores": False,
        "files": files,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
