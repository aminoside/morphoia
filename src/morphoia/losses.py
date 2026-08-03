"""Machine-readable semantic loss register used at adapter boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class LossCategory(str, Enum):
    GEOMETRY = "geometry"
    TOPOLOGY = "topology"
    PARAMETRIC_HISTORY = "parametric_history"
    CONSTRAINT = "constraint"
    PMI = "pmi"
    MATERIAL = "material"
    ASSEMBLY = "assembly"
    PROVENANCE = "provenance"
    IDENTITY = "identity"
    BEHAVIOR = "behavior"


class LossSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class LossRecord:
    code: str
    category: LossCategory
    severity: LossSeverity
    subject: str
    message: str
    source_capability: str | None = None
    target_capability: str | None = None
    mitigation: str | None = None
    reversible: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["category"] = self.category.value
        payload["severity"] = self.severity.value
        return payload


@dataclass(frozen=True, slots=True)
class LossRegister:
    operation: str
    source_backend: str
    target_backend: str
    records: tuple[LossRecord, ...] = ()

    @property
    def blocks_commit(self) -> bool:
        return any(
            record.severity in {LossSeverity.ERROR, LossSeverity.FATAL} for record in self.records
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "morphoia.loss-register/0.1",
            "operation": self.operation,
            "source_backend": self.source_backend,
            "target_backend": self.target_backend,
            "blocks_commit": self.blocks_commit,
            "records": [record.to_dict() for record in self.records],
        }
