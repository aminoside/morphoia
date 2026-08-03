"""Backend contracts; geometry kernels are adapters, never the canonical model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    name: str
    version: str
    profiles: tuple[str, ...]
    operations: tuple[str, ...]
    exact_brep: bool
    pmi: bool
    deterministic_mode: bool
    license: str


@dataclass(frozen=True, slots=True)
class BackendResult:
    success: bool
    artifact_uri: str | None
    validation_properties: dict[str, Any]
    losses: tuple[dict[str, Any], ...]
    diagnostics: tuple[str, ...]


class Backend(ABC):
    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        raise NotImplementedError

    @abstractmethod
    def execute(self, canonical_ir: dict[str, Any]) -> BackendResult:
        raise NotImplementedError
