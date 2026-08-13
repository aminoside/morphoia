"""Qualified, deterministic, metadata-only inspection of Engine IR 0.1."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator, FormatChecker

from ._engine_native import (
    ABI_VERSION,
    CANONICAL_PROFILE,
    CAPABILITY_ENGINE_IR_MANIFEST,
    FORMAT_IDENTIFIER,
    FORMAT_VERSION,
    MEDIA_TYPE,
    CanonicalLimits,
    EngineCapability,
    NativeEngine,
)
from .engine_ir import ValidatedManifest, validate_manifest
from .engine_ir_contract import ContractError, _resolve_schema, load_json_strict

INSPECTION_FORMAT: Final = "morphoia.engine.ir-inspection"
INSPECTION_VERSION: Final = "0.1.0"
INSPECTION_SCHEMA_ID: Final = (
    "https://morphoia.org/schemas/engine/ir-inspection/0.1.0"
)
INSPECTION_MEDIA_TYPE: Final = "application/vnd.morphoia.ir-inspection.v0+json"
INSPECTION_PROFILE: Final = "engine-ir-core-si-0.1"
INSPECTION_SCHEMA_FILENAME: Final = (
    "morphoia-engine-ir-inspection-0.1.0.schema.json"
)
TRANSFORM_POLICY: Final = "declared-not-applied"
UNIT_POLICY: Final = "exact-literal-validation-no-conversion"
REPORT_LIMITS: Final = CanonicalLimits(
    maximum_input_bytes=8 * 1_048_576,
    maximum_string_bytes=262_144,
    maximum_values=500_000,
    maximum_depth=64,
)

DIMENSION_NAMES: Final = (
    "length",
    "mass",
    "time",
    "current",
    "temperature",
    "amount",
    "luminous_intensity",
)
LIMITATIONS: Final = (
    "literal-unit-registry-only",
    "no-unit-conversion",
    "no-payload-resolution",
    "no-transform-application",
    "no-cryptographic-signature-verification",
    "no-scientific-fidelity-acceptance",
)


class InspectionError(ContractError):
    """The bounded inspection profile cannot inspect the supplied input."""


@dataclass(frozen=True, slots=True)
class EngineIrInspection:
    document: Mapping[str, Any]
    canonical_report: bytes
    report_sha256: str
    qualified: bool


def _plain_json(value: Any, *, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        raise InspectionError(f"floating-point metadata is forbidden at {path}")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise InspectionError(f"non-string metadata key at {path}")
            result[key] = _plain_json(item, path=f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _plain_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise InspectionError(f"unsupported metadata value at {path}: {type(value).__name__}")


def _transport_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            _plain_json(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise InspectionError("inspection report cannot be encoded as bounded JSON") from error


@lru_cache(maxsize=4)
def _inspection_validator(path_text: str) -> Draft202012Validator:
    path = Path(path_text)
    schema = load_json_strict(path.read_bytes())
    Draft202012Validator.check_schema(schema)
    if schema.get("$id") != INSPECTION_SCHEMA_ID:
        raise InspectionError("inspection schema identifier mismatch")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_report(document: Mapping[str, Any]) -> None:
    resolved = _resolve_schema(INSPECTION_SCHEMA_FILENAME, None)
    errors = sorted(
        _inspection_validator(str(resolved)).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "$" + "".join(f"[{part!r}]" for part in first.absolute_path)
        raise InspectionError(f"inspection report schema rejection at {location}: {first.message}")


def _capability_document(capability: EngineCapability) -> dict[str, str]:
    return {
        "capability_name": capability.capability_name,
        "format_identifier": capability.format_identifier,
        "format_version": capability.format_version,
        "media_type": capability.media_type,
        "canonical_profile": capability.canonical_profile,
    }


def _require_capabilities(engine: NativeEngine) -> tuple[EngineCapability, EngineCapability]:
    manifest = engine.query_capability(CAPABILITY_ENGINE_IR_MANIFEST)
    inspection = engine.query_capability(INSPECTION_PROFILE)
    if manifest is None or inspection is None:
        raise InspectionError("native Engine does not support the required inspection contracts")
    if (
        manifest.capability_name != CAPABILITY_ENGINE_IR_MANIFEST
        or manifest.format_identifier != FORMAT_IDENTIFIER
        or manifest.format_version != FORMAT_VERSION
        or manifest.media_type != MEDIA_TYPE
        or manifest.canonical_profile != CANONICAL_PROFILE
        or manifest.extension_keys
        or manifest.maximum_input_bytes != 1_048_576
        or manifest.maximum_string_bytes != 262_144
        or manifest.maximum_values != 100_000
        or manifest.maximum_depth != 64
    ):
        raise InspectionError("native manifest capability constants mismatch")
    if (
        inspection.capability_name != INSPECTION_PROFILE
        or inspection.format_identifier != INSPECTION_FORMAT
        or inspection.format_version != INSPECTION_VERSION
        or inspection.media_type != INSPECTION_MEDIA_TYPE
        or inspection.canonical_profile != CANONICAL_PROFILE
        or inspection.extension_keys
        or inspection.maximum_input_bytes != 0
        or inspection.maximum_string_bytes != 0
        or inspection.maximum_values != 0
        or inspection.maximum_depth != 0
    ):
        raise InspectionError("native qualified-inspection capability constants mismatch")
    return manifest, inspection


def _diagnostic(
    *,
    code: str,
    path: str,
    message: str,
    affected: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "family": "MOR-UNIT/FRAME",
        "code": code,
        "severity": "error",
        "path": path,
        "message": message,
        "affected_elements": [affected],
        "recommendation": recommendation,
    }


def _unit_documents(
    units: Sequence[Mapping[str, Any]],
    *,
    engine: NativeEngine,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    documents: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for index, unit in enumerate(units):
        dimension = unit["dimension"]
        factor = unit["si_factor"]
        code = unit["ucum_code"]
        unit_id = unit["id"]
        values = tuple(int(dimension[name]) for name in DIMENSION_NAMES)
        validation = engine.validate_engine_ir_unit(
            code,
            dimensions=values,
            si_factor_coefficient=int(factor["coefficient"]),
            si_factor_scale=int(factor["scale"]),
        )
        expected_dimension = {
            name: validation.expected_dimensions[position]
            for position, name in enumerate(DIMENSION_NAMES)
        }
        expected_factor = {
            "coefficient": validation.expected_si_factor_coefficient,
            "scale": validation.expected_si_factor_scale,
        }
        documents.append(
            {
                "id": unit_id,
                "ucum_code": code,
                "dimension": _plain_json(dimension),
                "si_factor": _plain_json(factor),
                "qualification": {
                    "recognized": validation.recognized,
                    "dimensions_match": validation.dimensions_match,
                    "si_factor_match": validation.si_factor_match,
                    "qualified": validation.qualified,
                    "expected_dimension": expected_dimension,
                    "expected_si_factor": expected_factor,
                },
            }
        )
        path = f"$.content.units[{index}]"
        if not validation.recognized:
            diagnostics.append(
                _diagnostic(
                    code="MOR-UNIT-UNSUPPORTED",
                    path=f"{path}.ucum_code",
                    message=f"unit code {code!r} is outside the literal inspection registry",
                    affected=unit_id,
                    recommendation=(
                        "Use an exact code from engine-ir-core-si-0.1 or select a "
                        "separately validated unit profile; no conversion was attempted."
                    ),
                )
            )
        elif not validation.dimensions_match:
            diagnostics.append(
                _diagnostic(
                    code="MOR-UNIT-DIMENSION",
                    path=f"{path}.dimension",
                    message=f"declared dimensions do not match literal code {code!r}",
                    affected=unit_id,
                    recommendation=(
                        "Correct the declaration to the exact profile tuple; no implicit "
                        "normalization was applied."
                    ),
                )
            )
        if validation.recognized and not validation.si_factor_match:
            diagnostics.append(
                _diagnostic(
                    code="MOR-UNIT-SI-FACTOR",
                    path=f"{path}.si_factor",
                    message=f"declared SI factor does not match literal code {code!r}",
                    affected=unit_id,
                    recommendation=(
                        "Correct coefficient and scale to the exact profile tuple; "
                        "mathematically equivalent alternatives are not normalized."
                    ),
                )
            )
    diagnostics.sort(
        key=lambda item: (
            str(item["path"]),
            str(item["code"]),
            tuple(item["affected_elements"]),
        )
    )
    return documents, diagnostics


def _authority_documents(representations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for representation in representations:
        result.append(
            {
                "id": representation["id"],
                "kind": representation["kind"],
                "authority": representation["authority"],
                "derived_from": _plain_json(representation["derived_from"]),
                "ai_output": representation["ai_output"],
                "topology_identity": representation.get("topology_identity"),
            }
        )
    return result


def _payload_documents(
    content: Mapping[str, Any],
    representations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "source_artifact": _plain_json(content["source"].get("artifact")),
        "representations": [
            {
                "representation_id": representation["id"],
                "payload": _plain_json(representation["payload"]),
            }
            for representation in representations
        ],
        "resolution_performed": False,
    }


def _inspection_document(
    manifest: ValidatedManifest,
    *,
    engine: NativeEngine,
    manifest_capability: EngineCapability,
    inspection_capability: EngineCapability,
) -> dict[str, Any]:
    content = manifest.document["content"]
    if not isinstance(content, Mapping):  # Defensive; validate_manifest already enforces this.
        raise InspectionError("validated Engine IR content is not an object")
    units_value = content["units"]
    representations_value = content["representations"]
    if not isinstance(units_value, Sequence) or not isinstance(
        representations_value, Sequence
    ):
        raise InspectionError("validated Engine IR collections are not sequences")
    units, diagnostics = _unit_documents(units_value, engine=engine)
    qualified = not diagnostics and all(unit["qualification"]["qualified"] for unit in units)
    transforms = _plain_json(content["transforms"])
    if any(transform.get("application") != TRANSFORM_POLICY for transform in transforms):
        raise InspectionError("validated transform policy is not declared-not-applied")
    return {
        "format": INSPECTION_FORMAT,
        "format_version": INSPECTION_VERSION,
        "media_type": INSPECTION_MEDIA_TYPE,
        "profile": INSPECTION_PROFILE,
        "status": "PASS" if qualified else "FAIL",
        "qualified": qualified,
        "manifest_sha256": manifest.manifest_sha256,
        "content_sha256": manifest.content_sha256,
        "identity_and_revision": {
            "logical_id": content["logical_id"],
            "revision": content["revision"],
            "parents": _plain_json(content["parents"]),
            "identity": _plain_json(manifest.document["identity"]),
        },
        "effective_capabilities": {
            "engine_version": engine.version,
            "engine_abi_version": ABI_VERSION,
            "library_sha256": engine.library_sha256,
            "manifest_contract": _capability_document(manifest_capability),
            "inspection": _capability_document(inspection_capability),
        },
        "units": units,
        "frames": _plain_json(content["frames"]),
        "transforms": transforms,
        "tolerances": _plain_json(content["tolerances"]),
        "authority_and_derivation": _authority_documents(representations_value),
        "provenance": _plain_json(content["provenance"]),
        "fidelity_events": _plain_json(content["fidelity_events"]),
        "repairs": _plain_json(content["repairs"]),
        "losses": _plain_json(content["losses"]),
        "payload_reference_metadata": _payload_documents(
            content,
            representations_value,
        ),
        "security": _plain_json(content["security"]),
        "limitations": list(LIMITATIONS),
        "diagnostics": diagnostics,
    }


def inspect_engine_ir(
    source: bytes | bytearray | memoryview | str,
    *,
    profile: str = INSPECTION_PROFILE,
    engine: NativeEngine | None = None,
) -> EngineIrInspection:
    """Inspect declarations only; never resolve payloads, convert, repair, or transform."""

    if profile != INSPECTION_PROFILE:
        raise InspectionError(
            f"unsupported inspection profile {profile!r}; expected {INSPECTION_PROFILE!r}"
        )
    if engine is not None and not isinstance(engine, NativeEngine):
        raise TypeError("engine must be an open NativeEngine instance or None")
    if engine is None:
        with NativeEngine() as owned_engine:
            return inspect_engine_ir(
                source,
                profile=profile,
                engine=owned_engine,
            )
    manifest_capability, inspection_capability = _require_capabilities(engine)
    manifest = validate_manifest(source, engine=engine)
    document = _inspection_document(
        manifest,
        engine=engine,
        manifest_capability=manifest_capability,
        inspection_capability=inspection_capability,
    )
    _validate_report(document)
    canonical = engine.canonicalize(_transport_bytes(document), limits=REPORT_LIMITS)
    return EngineIrInspection(
        document=document,
        canonical_report=canonical.canonical,
        report_sha256=canonical.sha256,
        qualified=bool(document["qualified"]),
    )


__all__ = [
    "INSPECTION_FORMAT",
    "INSPECTION_MEDIA_TYPE",
    "INSPECTION_PROFILE",
    "INSPECTION_SCHEMA_ID",
    "INSPECTION_VERSION",
    "TRANSFORM_POLICY",
    "UNIT_POLICY",
    "EngineIrInspection",
    "InspectionError",
    "inspect_engine_ir",
]
