from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def evaluate_llm_baseline(
    responses: Iterable[dict[str, object]],
    answer_key: Iterable[dict[str, object]],
    requests: Iterable[dict[str, object]] | None = None,
) -> dict[str, object]:
    answers = {str(row["pair_id"]): dict(row) for row in answer_key}
    response_rows = [normalize_response_row(row, answers) for row in responses]
    request_rows = [dict(row) for row in requests] if requests is not None else []
    observed_keys = {
        (
            str(row.get("pair_id", "")),
            str(row.get("model", "")),
            str(row.get("strictness", "")),
        )
        for row in response_rows
    }
    missing = [
        {
            "pair_id": str(row.get("pair_id", "")),
            "model": str(row.get("model", "")),
            "strictness": str(row.get("strictness", "")),
        }
        for row in request_rows
        if (
            str(row.get("pair_id", "")),
            str(row.get("model", "")),
            str(row.get("strictness", "")),
        )
        not in observed_keys
    ]
    groups = {
        "all": response_rows,
        **group_by(response_rows, "model", prefix="model:"),
        **group_by(response_rows, "strictness", prefix="strictness:"),
        **group_by(response_rows, "source", prefix="source:"),
        **group_by_tuple(response_rows, ("model", "strictness"), prefix="model_strictness:"),
    }
    return {
        "response_count": len(response_rows),
        "request_count": len(request_rows) if request_rows else None,
        "missing_response_count": len(missing) if request_rows else None,
        "missing_responses": missing[:100],
        "summary": {name: summarize_rows(rows) for name, rows in sorted(groups.items())},
        "rows": response_rows,
    }


def normalize_response_row(row: dict[str, object], answers: dict[str, dict[str, object]]) -> dict[str, object]:
    pair_id = str(row.get("pair_id", ""))
    answer = answers.get(pair_id, {})
    choice = normalize_choice(str(row.get("choice", row.get("raw_response", ""))))
    expected = str(answer.get("metric_preference", "missing"))
    return {
        "pair_id": pair_id,
        "model": str(row.get("model", "")),
        "strictness": str(row.get("strictness", "")),
        "choice": choice,
        "expected": expected,
        "correct": bool(choice == expected and expected in {"left", "right"}),
        "invalid": choice not in {"left", "right"},
        "source": str(answer.get("source", "")),
        "canonical_case_id": answer.get("canonical_case_id"),
        "score_gap": float(answer.get("score_gap", 0.0) or 0.0),
        "raw_response": str(row.get("raw_response", "")),
    }


def normalize_choice(text: str) -> str:
    lowered = text.strip().lower()
    if lowered.startswith("left"):
        return "left"
    if lowered.startswith("right"):
        return "right"
    return "invalid"


def group_by(rows: list[dict[str, object]], key: str, prefix: str) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        result[f"{prefix}{row.get(key, '')}"].append(row)
    return dict(result)


def group_by_tuple(
    rows: list[dict[str, object]],
    keys: tuple[str, ...],
    prefix: str,
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        value = "/".join(str(row.get(key, "")) for key in keys)
        result[f"{prefix}{value}"].append(row)
    return dict(result)


def summarize_rows(rows: list[dict[str, object]]) -> dict[str, float]:
    n = len(rows)
    correct = sum(bool(row["correct"]) for row in rows)
    invalid = sum(bool(row["invalid"]) for row in rows)
    return {
        "n": float(n),
        "accuracy": correct / n if n else float("nan"),
        "correct": float(correct),
        "invalid": float(invalid),
        "invalid_rate": invalid / n if n else float("nan"),
        "mean_score_gap": sum(float(row["score_gap"]) for row in rows) / n if n else float("nan"),
    }
