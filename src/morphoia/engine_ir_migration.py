"""Explicit, fail-closed migration from the legacy construction-graph domain.

The legacy payload remains immutable and authoritative in its historical
domain. Migration builds unsealed Engine content that references those bytes,
records provenance, and declares losses. It never edits the input, constructs
a sealed manifest, or derives an Engine content identity in Python.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

from .engine_ir_contract import ContractError, SchemaError, load_json_strict

LEGACY_FORMAT = "morphoia.canonical-construction-graph"
LEGACY_VERSION = "0.1"
LEGACY_MEDIA_TYPE = "application/vnd.morphoia.legacy-construction-graph.v0+json"

_METADATA_KEYS = frozenset(
    {
        "assembly_ids",
        "ended_at",
        "frame",
        "license_expression",
        "logical_id",
        "loss_ids",
        "migration_tool",
        "provenance_id",
        "representation_id",
        "rights_holder",
        "security",
        "source_artifact",
        "source_created_at",
        "source_tool",
        "source_uri",
        "started_at",
        "unit",
    }
)


class MigrationError(ContractError):
    """The legacy input or explicit migration metadata is incomplete."""


def _legacy_schema_path() -> Path:
    filename = "morphoia-ir-0.1.schema.json"
    candidates = (
        Path(__file__).resolve().parents[2] / "schemas" / filename,
        Path(sys.prefix) / "share" / "morphoia" / "schemas" / filename,
    )
    for path in candidates:
        if path.is_file():
            return path
    rendered = ", ".join(str(path) for path in candidates)
    raise MigrationError(f"legacy schema is unavailable: {rendered}")


def _validate_legacy(document: Mapping[str, Any]) -> None:
    try:
        schema = load_json_strict(_legacy_schema_path().read_bytes())
        Draft202012Validator(schema).validate(document)
    except SchemaError as exc:
        raise MigrationError("legacy schema cannot be loaded") from exc
    except Exception as exc:
        raise MigrationError("legacy input does not match the frozen 0.1 schema") from exc
    if document["format"] != LEGACY_FORMAT or document["format_version"] != LEGACY_VERSION:
        raise MigrationError("legacy format identity is not the frozen 0.1 domain")


def _reject_legacy_constant(value: str) -> NoReturn:
    raise MigrationError(f"non-finite legacy JSON number is forbidden: {value}")


def _parse_legacy_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise MigrationError("invalid exact decimal in legacy JSON") from exc
    if not parsed.is_finite() or len(parsed.as_tuple().digits) > 256:
        raise MigrationError("legacy exact decimal exceeds the bounded migration profile")
    return parsed


def _parse_legacy_integer(value: str) -> int:
    if len(value.lstrip("-")) > 256:
        raise MigrationError("legacy integer exceeds the bounded migration profile")
    return int(value)


def _unique_legacy_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError(f"duplicate decoded legacy JSON object key: {key}")
        result[key] = value
    return result


def _load_legacy_json(raw: bytes) -> dict[str, Any]:
    if len(raw) > 1_048_576:
        raise MigrationError("legacy JSON exceeds the 1 MiB migration limit")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MigrationError("legacy JSON must be valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_legacy_object,
            parse_int=_parse_legacy_integer,
            parse_float=_parse_legacy_decimal,
            parse_constant=_reject_legacy_constant,
        )
    except MigrationError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MigrationError("legacy input is invalid bounded JSON") from exc
    if not isinstance(value, dict):
        raise MigrationError("legacy input root must be an object")
    stack: list[tuple[Any, int]] = [(value, 0)]
    value_count = 0
    while stack:
        item, depth = stack.pop()
        value_count += 1
        if value_count > 100_000:
            raise MigrationError("legacy JSON exceeds the 100000 value migration limit")
        if isinstance(item, str):
            try:
                encoded = item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise MigrationError("legacy JSON contains an invalid Unicode scalar value") from exc
            if len(encoded) > 262_144:
                raise MigrationError("legacy JSON string exceeds the migration limit")
        elif isinstance(item, Mapping):
            if depth + 1 > 64:
                raise MigrationError("legacy JSON exceeds the 64-container migration limit")
            for key, child in item.items():
                try:
                    encoded_key = key.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise MigrationError(
                        "legacy JSON key contains an invalid Unicode scalar value"
                    ) from exc
                if len(encoded_key) > 262_144:
                    raise MigrationError("legacy JSON key exceeds the migration limit")
                stack.append((child, depth + 1))
        elif isinstance(item, list):
            if depth + 1 > 64:
                raise MigrationError("legacy JSON exceeds the 64-container migration limit")
            stack.extend((child, depth + 1) for child in item)
    return value


def _require_exact_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(_METADATA_KEYS - set(metadata))
    extra = sorted(set(metadata) - _METADATA_KEYS)
    if missing:
        raise MigrationError(f"migration metadata is missing: {missing[0]}")
    if extra:
        raise MigrationError(f"unknown migration metadata field: {extra[0]}")
    copied = deepcopy(dict(metadata))
    if not isinstance(copied["assembly_ids"], list):
        raise MigrationError("migration metadata assembly_ids must be a list")
    if not isinstance(copied["loss_ids"], list) or len(copied["loss_ids"]) != 4:
        raise MigrationError("migration metadata loss_ids must contain exactly four IDs")
    for field in (
        "frame",
        "migration_tool",
        "security",
        "source_artifact",
        "source_tool",
        "unit",
    ):
        if not isinstance(copied[field], dict):
            raise MigrationError(f"migration metadata {field} must be an object")
    return copied


def _verify_source_bytes(raw: bytes, reference: Mapping[str, Any]) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    if reference.get("sha256") != digest:
        raise MigrationError("source_artifact SHA-256 does not match the immutable legacy bytes")
    if reference.get("size_bytes") != len(raw):
        raise MigrationError("source_artifact size does not match the immutable legacy bytes")
    if reference.get("uri") != f"morphoia-cas://sha256/{digest}":
        raise MigrationError("source_artifact CAS URI does not match its SHA-256")
    if reference.get("media_type") != LEGACY_MEDIA_TYPE:
        raise MigrationError(f"source_artifact media_type must be {LEGACY_MEDIA_TYPE}")


def build_legacy_migration_content(
    legacy_document: str | bytes,
    *,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Build unsealed Engine content without mutating or re-identifying input.

    This helper intentionally returns only ``content``.  A public migration
    path must pass that object to the native Profile 1 canonicalizer, use the
    native digest to construct an envelope, and then call ``validate_manifest``
    with that digest.  Accepting a caller-supplied digest here would be a
    self-attestation bug.  The immutable legacy byte hash is independently
    checked because it is a payload fingerprint, not a new Engine identity.
    """

    if isinstance(legacy_document, str):
        try:
            raw = legacy_document.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise MigrationError("legacy input contains an invalid Unicode scalar value") from exc
    elif isinstance(legacy_document, bytes):
        raw = legacy_document
    else:
        raise TypeError("legacy_document must be str or bytes so its byte identity is preserved")

    legacy = _load_legacy_json(raw)
    _validate_legacy(legacy)
    supplied = _require_exact_metadata(metadata)
    _verify_source_bytes(raw, supplied["source_artifact"])

    models = legacy["models"]
    assembly_ids = supplied["assembly_ids"]
    if len(assembly_ids) != len(models):
        raise MigrationError("assembly_ids count must exactly match legacy models")

    assemblies = [
        {"id": assembly_id, "name": model["name"]}
        for assembly_id, model in zip(assembly_ids, models, strict=True)
    ]
    names = [
        {"subject_id": assembly_id, "value": model["name"]}
        for assembly_id, model in zip(assembly_ids, models, strict=True)
    ]
    properties = [
        {"subject_id": assembly_id, "name": "legacy_model_id", "value": model["id"]}
        for assembly_id, model in zip(assembly_ids, models, strict=True)
    ]

    representation_id = supplied["representation_id"]
    content = {
        "logical_id": supplied["logical_id"],
        "revision": 1,
        "parents": [],
        "units": [supplied["unit"]],
        "frames": [supplied["frame"]],
        "transforms": [],
        "source": {
            "uri": supplied["source_uri"],
            "license_expression": supplied["license_expression"],
            "rights_holder": supplied["rights_holder"],
            "created_at": supplied["source_created_at"],
            "source_tool": supplied["source_tool"],
            "artifact": supplied["source_artifact"],
        },
        "product": {
            "assemblies": assemblies,
            "instances": [],
            "names": names,
            "colors": [],
            "layers": [],
            "properties": properties,
        },
        "representations": [
            {
                "id": representation_id,
                "kind": "opaque",
                "authority": "source",
                "frame_id": supplied["frame"]["id"],
                "unit_id": supplied["unit"]["id"],
                "payload": supplied["source_artifact"],
                "derived_from": [],
                "ai_output": False,
            }
        ],
        "provenance": [
            {
                "id": supplied["provenance_id"],
                "activity": "explicit-legacy-domain-migration",
                "tool": supplied["migration_tool"],
                "parameters": {
                    "legacy_format": legacy["format"],
                    "legacy_format_version": legacy["format_version"],
                    "legacy_semantic_sha256": legacy["semantic_sha256"],
                    "migration_policy": "preserve-opaque-source",
                },
                "parents": [],
                "environment": {
                    "profile": "core-cpu-legacy-migration",
                    "os": "platform-independent",
                },
                "seeds": [],
                "started_at": supplied["started_at"],
                "ended_at": supplied["ended_at"],
                "inputs": [],
                "outputs": [representation_id],
            }
        ],
        "tolerances": [],
        "fidelity_events": [],
        "repairs": [],
        "losses": [
            {
                "id": supplied["loss_ids"][0],
                "subject_id": representation_id,
                "category": "identity",
                "property": "semantic-identity-domain",
                "before": f"legacy:{legacy['semantic_sha256']}",
                "after": "engine-content-identity-in-envelope",
                "severity": "warning",
                "decision": "retain-source",
                "description": (
                    "The legacy semantic hash is retained as provenance but is not an "
                    "authoritative Engine content identity."
                ),
            },
            {
                "id": supplied["loss_ids"][1],
                "subject_id": representation_id,
                "category": "parametric-history",
                "property": "structured-construction-history",
                "before": "legacy imports, declarations, expressions, units, and dependency order",
                "after": "retained only in the immutable opaque legacy payload",
                "severity": "warning",
                "decision": "retain-source",
                "description": (
                    "The bounded migration preserves all legacy bytes but does not map construction "
                    "history into structured Engine fields."
                ),
            },
            {
                "id": supplied["loss_ids"][2],
                "subject_id": representation_id,
                "category": "behavior",
                "property": "execution-contract",
                "before": "legacy execution_contract",
                "after": "retained only in the immutable opaque legacy payload",
                "severity": "warning",
                "decision": "retain-source",
                "description": (
                    "The bounded migration does not reinterpret the legacy execution contract as "
                    "Engine runtime behavior."
                ),
            },
            {
                "id": supplied["loss_ids"][3],
                "subject_id": representation_id,
                "category": "metadata",
                "property": "legacy-imports-and-model-attributes",
                "before": "legacy imports and model attributes",
                "after": "model names and IDs mapped; remaining metadata retained in opaque payload",
                "severity": "warning",
                "decision": "retain-source",
                "description": (
                    "Only model names and legacy IDs receive structured product records in this "
                    "bounded migration profile."
                ),
            },
        ],
        "security": supplied["security"],
        "extensions": {
            "org.morphoia.legacy": {
                "namespace": legacy["namespace"],
                "source_language": legacy["source_language"],
            }
        },
    }
    return content


__all__ = [
    "LEGACY_FORMAT",
    "LEGACY_MEDIA_TYPE",
    "LEGACY_VERSION",
    "MigrationError",
    "build_legacy_migration_content",
]
