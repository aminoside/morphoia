"""Explicit three-state persistent-reference resolution.

This module deliberately never converts a ranked tie into a silent choice.
It is a small executable contract, not a claim to have solved the universal
Topological Naming Problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ResolutionStatus(str, Enum):
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    identity: str
    kind: str
    producer: str
    role: str
    signature: tuple[tuple[str, Any], ...] = ()
    adjacency: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReferenceQuery:
    kind: str
    producer: str
    role: str
    signature: tuple[tuple[str, Any], ...] = ()
    adjacent_to: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    status: ResolutionStatus
    candidates: tuple[EntityCandidate, ...]

    @property
    def entity(self) -> EntityCandidate:
        if self.status is not ResolutionStatus.UNIQUE:
            raise LookupError(f"reference is {self.status.value}, not unique")
        return self.candidates[0]


def resolve_reference(
    query: ReferenceQuery,
    candidates: list[EntityCandidate] | tuple[EntityCandidate, ...],
) -> ResolutionResult:
    """Resolve by lineage, semantic role, adjacency and exact signature terms."""

    required_signature = dict(query.signature)
    matches: list[EntityCandidate] = []
    for candidate in candidates:
        if candidate.kind != query.kind:
            continue
        if candidate.producer != query.producer or candidate.role != query.role:
            continue
        candidate_signature = dict(candidate.signature)
        if any(candidate_signature.get(key) != value for key, value in required_signature.items()):
            continue
        if any(identity not in candidate.adjacency for identity in query.adjacent_to):
            continue
        matches.append(candidate)

    matches.sort(key=lambda candidate: candidate.identity)
    if not matches:
        return ResolutionResult(ResolutionStatus.MISSING, ())
    if len(matches) > 1:
        return ResolutionResult(ResolutionStatus.AMBIGUOUS, tuple(matches))
    return ResolutionResult(ResolutionStatus.UNIQUE, tuple(matches))
