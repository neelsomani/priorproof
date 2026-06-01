"""Dependency-footprint construction and novelty scoring."""

from .filtering import DependencyFilter
from .frontier import established_frontier
from .redundancy import detect_redundant_subterms
from .scoring import score_footprint

__all__ = [
    "DependencyFilter",
    "detect_redundant_subterms",
    "established_frontier",
    "score_footprint",
]

