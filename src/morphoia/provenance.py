"""Provenance primitives for observed, inferred and decided CAD information.

The module does not try to standardize a universal provenance ontology. It
implements the minimum evidence contract required by the Phase 1 conclusions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class EvidenceKind(str, Enum):
    DRAWING = "drawing"
    PMI = "pmi"
    CAD_MODEL = "cad_model"
    IMAGE = "image"
    POINT_CLOUD = "point_cloud"
    MESH = "mesh"
    TEXT = "text"
    HUMAN_DECISION = "human_decision"
    DERIVED_RULE = "derived_rule"


class DecisionStatus(str, Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class Evidence:
    identity: str
    kind: EvidenceKind
    source_uri: str
    source_sha256: str
    locator: str | None = None

    def __post_init__(self) -> None:
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class Decision:
    identity: str
    subject: str
    status: DecisionStatus
    evidence_ids: tuple[str, ...]
    confidence: Decimal | None = None
    decided_by: str | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not (Decimal(0) <= self.confidence <= Decimal(1)):
            raise ValueError("confidence must be in the closed interval [0, 1]")
        if self.status is DecisionStatus.ACCEPTED and not self.evidence_ids:
            raise ValueError("an accepted decision requires at least one evidence item")
        if self.status is DecisionStatus.ACCEPTED and not self.decided_by:
            raise ValueError("an accepted decision must identify the deterministic rule or person")
