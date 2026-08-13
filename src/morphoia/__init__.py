"""Morphoia Engine IR API and experimental construction-graph prototype.

Author and project initiator: Olivier Ami.
"""

from .compiler import canonical_json, compile_document, semantic_hash
from .engine_ir import (
    ReplayCancelledError,
    ReplayError,
    ReplayTimeoutError,
    ValidatedManifest,
    create_replay_recipe,
    migrate_legacy_manifest,
    replay_manifest,
    seal_content,
)
from .engine_ir import (
    validate_manifest as validate_engine_ir_manifest,
)
from .engine_ir_inspection import (
    EngineIrInspection,
    InspectionError,
    inspect_engine_ir,
)
from .parser import parse
from .runtime import RuntimeStore
from .validator import validate_file, validate_source

__author__ = "Olivier Ami"
__version__ = "0.2.0.dev0"

__all__ = [
    "EngineIrInspection",
    "InspectionError",
    "ReplayCancelledError",
    "ReplayError",
    "ReplayTimeoutError",
    "RuntimeStore",
    "ValidatedManifest",
    "canonical_json",
    "compile_document",
    "create_replay_recipe",
    "inspect_engine_ir",
    "migrate_legacy_manifest",
    "parse",
    "replay_manifest",
    "seal_content",
    "semantic_hash",
    "validate_engine_ir_manifest",
    "validate_file",
    "validate_source",
]
