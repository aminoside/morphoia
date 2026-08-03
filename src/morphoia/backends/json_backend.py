"""Lossless backend that writes the canonical construction graph as JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..compiler import canonical_json
from .base import Backend, BackendCapabilities, BackendResult


class CanonicalJsonBackend(Backend):
    def __init__(self, output: str | Path):
        self.output = Path(output)

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name="canonical-json",
            version="0.1",
            profiles=("P1", "P2", "P3", "P4"),
            operations=("serialization",),
            exact_brep=False,
            pmi=True,
            deterministic_mode=True,
            license="MORPHOIA repository license",
        )

    def execute(self, canonical_ir: dict[str, Any]) -> BackendResult:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(canonical_json(canonical_ir), encoding="utf-8")
        return BackendResult(
            success=True,
            artifact_uri=self.output.resolve().as_uri(),
            validation_properties={"semantic_sha256": canonical_ir["semantic_sha256"]},
            losses=(),
            diagnostics=(),
        )
