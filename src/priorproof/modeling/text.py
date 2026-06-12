from __future__ import annotations

import re


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*|[0-9]+|[^\sA-Za-z0-9_]")


def tokenize_statement(statement: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(statement)]


def statement_shape(statement: str) -> str:
    tokens = tokenize_statement(statement)
    has_forall = any(token in {"forall", "∀"} for token in tokens)
    has_exists = any(token in {"exists", "∃"} for token in tokens)
    has_iff = any(token in {"iff", "↔"} for token in tokens)
    has_eq = "=" in tokens
    arrows = tokens.count("->") + tokens.count("→")
    return f"forall:{has_forall}|exists:{has_exists}|iff:{has_iff}|eq:{has_eq}|arrows:{min(arrows, 3)}"

