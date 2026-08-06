"""Validate and seal the MVX P0 pre-registration package."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

PROTOCOL_VERSION = "1.0.2-p0"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
P0_DIRECTORY = PROJECT_ROOT / "docs" / "mvx" / "validation" / "p0"
SCHEMA_DIRECTORY = PROJECT_ROOT / "schemas" / "mvx" / "0.2.1"
EXAMPLE_DIRECTORY = P0_DIRECTORY / "schema-examples"
SEAL_PATH = P0_DIRECTORY / "seal.json"
G0_PATH = P0_DIRECTORY / "gates" / "G0-verdict.json"

_STATIC_NORMATIVE_PATHS = (
    "docs/mvx/specification/MORPHOIA_MVX_Rapport_de_proposition_technique_v0.2.pdf",
    "docs/mvx/specification/MORPHOIA_MVX_Addendum_Implementation_v0.2.1.pdf",
    "docs/mvx/validation/MORPHOIA_MVX_Plan_experimental_complet_vers_v1.pdf",
    "docs/mvx/validation/p0/protocol.yaml",
    "docs/mvx/validation/p0/metrics.yaml",
    "docs/mvx/validation/p0/eligibility.yaml",
    "docs/mvx/validation/p0/selection-spec.yaml",
    "docs/mvx/validation/p0/split-spec.yaml",
    "docs/mvx/validation/p0/split-test-vectors.json",
    "docs/mvx/validation/p0/statistical-plan.yaml",
    "docs/mvx/validation/p0/trusted-publishers.json",
    "docs/mvx/validation/p0/error-codes.yaml",
    "docs/mvx/validation/p0/release-criteria.yaml",
    "docs/mvx/validation/p0/roles.yaml",
    "docs/mvx/validation/p0/implementation-clarifications.yaml",
    "docs/mvx/validation/p0/audit/RED_TEAM_1.0.0.md",
    "docs/mvx/validation/p0/audit/superseded-1.0.0-p0/G0-verdict.json",
    "docs/mvx/validation/p0/audit/superseded-1.0.0-p0/seal.json",
    "docs/mvx/validation/p0/audit/superseded-1.0.0-p0/supersession.json",
    "docs/mvx/validation/p0/audit/superseded-1.0.1-p0/G0-verdict.json",
    "docs/mvx/validation/p0/audit/superseded-1.0.1-p0/seal.json",
    "docs/mvx/validation/p0/audit/superseded-1.0.1-p0/supersession.json",
    "pyproject.toml",
    "uv.lock",
    "src/morphoia/cli.py",
    "src/morphoia/mvx/artifacts.py",
    "src/morphoia/mvx/checkpoint.py",
    "src/morphoia/mvx/cli.py",
    "src/morphoia/mvx/cohort.py",
    "src/morphoia/mvx/corpus/__init__.py",
    "src/morphoia/mvx/corpus/registry.py",
    "src/morphoia/mvx/custody.py",
    "src/morphoia/mvx/hmac_rank.py",
    "src/morphoia/mvx/protocol.py",
    "src/morphoia/mvx/selection.py",
    "src/morphoia/mvx/split.py",
    "tests/test_mvx_artifacts.py",
    "tests/test_mvx_checkpoint.py",
    "tests/test_mvx_custody.py",
    "tests/test_mvx_cohort.py",
    "tests/test_mvx_corpus.py",
    "tests/test_mvx_protocol.py",
    "tests/test_mvx_protocol_semantics.py",
    "tests/test_mvx_schema_contracts.py",
    "tests/test_mvx_selection.py",
)


def _relative_glob(directory: Path, pattern: str) -> tuple[str, ...]:
    return tuple(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted(directory.glob(pattern))
        if path.is_file()
    )


def _relative_rglob(directory: Path, pattern: str) -> tuple[str, ...]:
    return tuple(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted(directory.rglob(pattern))
        if path.is_file()
    )


# The complete schema and example sets are normative.  They are discovered at
# import time so adding a schema or indexed example automatically changes the
# protocol root instead of relying on a hand-maintained partial list.
NORMATIVE_PATHS = tuple(
    sorted(
        {
            *_STATIC_NORMATIVE_PATHS,
            *_relative_rglob(PROJECT_ROOT / "src" / "morphoia", "*.py"),
            *_relative_glob(SCHEMA_DIRECTORY, "*.schema.json"),
            *_relative_glob(EXAMPLE_DIRECTORY, "*.json"),
        }
    )
)

HEX_256 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_GATES = {f"G{index}" for index in range(8)}
EXPECTED_GATE_CRITERIA = {
    "G0": (
        "G0_NORMATIVE_FILES_VALID",
        "G0_PROTOCOL_SEAL_VERIFIES",
        "G0_PROTOCOL_COMPONENTS_FROZEN",
        "G0_CUSTODY_DRY_RUN",
        "G0_SEMANTIC_CLOSURE",
    ),
    "G1": (
        "G1_SOURCE_AUDIT_SEALED",
        "G1_COHORT_RESERVE_COMPLETE",
        "G1_SPLIT_LEAKAGE_FREE",
        "G1_OBJAVERSE_INGESTION_COMPLETE",
        "G1_CUSTODY_REDACTION_VERIFIED",
    ),
    "G2": (
        "G2_NESTED_100_REPRODUCIBLE",
        "G2_C0_C2_PASS",
        "G2_D_R32_R16_CONFORM",
        "G2_REQUIRED_COMMANDS_EXECUTABLE",
        "G2_GOLDEN_FILES_PUBLISHABLE",
    ),
    "G3": (
        "G3_C0_C6_C8_PASS",
        "G3_ANALYTIC_AMBIGUITY_CLOSED",
        "G3_BINARY_CORE_DOMAIN_DELIMITED",
    ),
    "G4": (
        "G4_CONFIGURATION_JUSTIFIED",
        "G4_OVERFLOW_WITHIN_LIMIT",
        "G4_NO_CRITICAL_OMISSION",
        "G4_NO_SYSTEMATIC_DISADVANTAGE",
    ),
    "G5": (
        "G5_INTEROPERABILITY_EXACT",
        "G5_SAFETY_LICENCE_CLEAR",
        "G5_BLIND_INPUTS_SEALED",
    ),
    "G6": (
        "G6_NO_BLIND_CRITICAL_BLOCKER",
        "G6_FROZEN_THRESHOLDS_PASS",
        "G6_MINI_NEURAL_PASS",
        "G6_NO_SILENT_STRATUM_DEGRADATION",
    ),
    "G7": (
        "G7_RELEASE_BLOCKERS_CLOSED",
        "G7_AI_CRITIQUES_CLOSED",
        "G7_HUMAN_REVIEWS_CLOSED",
        "G7_CLAIMS_AND_LIMITS_PUBLISHED",
    ),
}
EXPECTED_G4_THRESHOLDS = {
    "hd95_symmetric_p": ("max", 2.0),
    "chamfer_symmetric_rms_p": ("max", 0.75),
    "occupancy_iou": ("min", 0.99),
    "normal_median_deg": ("max", 1.0),
    "normal_p95_deg": ("max", 5.0),
    "relative_volume_error": ("max", 0.02),
    "relative_area_error": ("max", 0.05),
    "topology_exact_ge_8p": ("equal", True),
    "openings_recall_ge_8p": ("min", 0.95),
    "cross_view_agreement_real": ("min", 0.9999),
    "cross_view_agreement_oracle": ("equal", 1.0),
    "cross_view_eligible_coverage": ("min", 0.95),
    "ray_overflow_fraction": ("max", 0.001),
    "topologically_critical_omission_count": ("equal", 0),
}
REQUIRED_G4_CHANNELS = {
    "Z",
    "Nx",
    "Ny",
    "Nz",
    "valid",
    "normal_valid",
    "event_kind",
    "observation_state",
    "count_status",
    "ray_flags",
    "total_count_value",
    "retained_count",
    "omitted_count",
    "crossing_count",
}
ALLOWED_G4_CHANNELS = REQUIRED_G4_CHANNELS | {
    "source_rank",
    "label_before",
    "label_after",
}
EXPECTED_ERROR_CODES = {
    "MVX-OK",
    "MVX-I001",
    "MVX-I002",
    "MVX-I003",
    "MVX-I004",
    "MVX-I005",
    "MVX-I006",
    "MVX-I007",
    "MVX-I008",
    "MVX-R001",
    "MVX-R002",
    "MVX-R003",
    "MVX-R004",
    "MVX-G001",
    "MVX-G002",
    "MVX-G003",
    "MVX-E001",
    "MVX-E002",
    "MVX-V001",
    "MVX-V002",
    "MVX-V003",
    "MVX-P001",
    "MVX-P002",
    "MVX-P003",
    "MVX-S001",
    "MVX-S002",
    "MVX-X001",
    "MVX-X002",
}
EXPECTED_ERROR_PRECEDENCE = (
    "MVX-S001",
    "MVX-S002",
    "MVX-P002",
    "MVX-P003",
    "MVX-P001",
    "MVX-X002",
    "MVX-X001",
    "MVX-I008",
    "MVX-I002",
    "MVX-I006",
    "MVX-I007",
    "MVX-I003",
    "MVX-I005",
    "MVX-I004",
    "MVX-I001",
    "MVX-V001",
    "MVX-V002",
    "MVX-V003",
    "MVX-R003",
    "MVX-R004",
    "MVX-R001",
    "MVX-R002",
    "MVX-G002",
    "MVX-G001",
    "MVX-G003",
)
EXPECTED_ERROR_TERMINAL_MAPPING = {
    "PASS": ("MVX-OK",),
    "DECLARED_LIMIT": (
        "MVX-R001",
        "MVX-R002",
        "MVX-R003",
        "MVX-R004",
        "MVX-G001",
        "MVX-G002",
        "MVX-G003",
    ),
    "REJECT": (
        "MVX-I001",
        "MVX-I002",
        "MVX-I003",
        "MVX-I004",
        "MVX-I005",
        "MVX-I006",
        "MVX-I007",
        "MVX-I008",
        "MVX-V001",
        "MVX-V002",
        "MVX-V003",
    ),
    "FAIL": (
        "MVX-P001",
        "MVX-P002",
        "MVX-P003",
        "MVX-S001",
        "MVX-S002",
        "MVX-X001",
    ),
    "no_manifest_possible": ("MVX-X002",),
}
EXPECTED_PDF_HASHES = {
    "docs/mvx/specification/MORPHOIA_MVX_Rapport_de_proposition_technique_v0.2.pdf": "2b2d6dd6d565aad7d962ccd260008fd700fec400f5fb284eb1b59fa30add6f2e",
    "docs/mvx/specification/MORPHOIA_MVX_Addendum_Implementation_v0.2.1.pdf": "02ca052fad3655292583b3ea411e712e2ea343bbf690517e4e581b4e56569d06",
    "docs/mvx/validation/MORPHOIA_MVX_Plan_experimental_complet_vers_v1.pdf": "3cddc9d1ba515afaa0558b26d703cc9bdb2600f9ebf59d22d9ab94d45dc8322b",
}
EXPECTED_CONFIRMATION_TARGETS = {
    "fixtures_C0_C9": {"total": 100, "development": 50, "calibration": 20, "blind": 30},
    "objaverse": {"total": 600, "development": 300, "calibration": 120, "blind": 180},
    "modelnet40": {"total": 100, "development": 50, "calibration": 20, "blind": 30},
    "thingi10k": {"total": 80, "development": 40, "calibration": 16, "blind": 24},
    "google_scanned_objects": {
        "total": 60,
        "development": 30,
        "calibration": 12,
        "blind": 18,
    },
    "human_anatomy": {"total": 50, "development": 25, "calibration": 10, "blind": 15},
    "plants": {"total": 10, "development": 5, "calibration": 2, "blind": 3},
}
PREDECESSOR_PROTOCOL_ROOT = "a56a7dcfd5b02c60b28035a1830e40a2d30993f50bd390c3207f30f55b4b994d"
PREDECESSOR_SEAL_SHA256 = "599288d882b8970b5942e014da816a606427a0caa9932cb511d2fee412408b58"
SUPERSESSION_RECORD_SHA256 = "60a2403b21b6ae5b62e02d9bcaa6bd6375f7e091ca218573039b4a536ee5375b"


@dataclass(frozen=True)
class ProtocolCheck:
    identifier: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class ProtocolVerification:
    checks: tuple[ProtocolCheck, ...]
    root_sha256: str | None

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[ProtocolCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON for string/integer hash manifests.

    Seal manifests contain no floating-point values, so this is equivalent to
    RFC 8785 for the value domain used here. MVX payload manifests will use a
    separately qualified full JCS implementation.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _fsync_directory(directory: Path) -> None:
    """Durably record directory-entry changes on the current filesystem."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _existing_artifact_matches(path: Path, expected: bytes, *, artifact: str) -> bool:
    """Return true only for an exact regular-file match; reject every conflict."""

    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise FileExistsError(
            f"refusing to replace non-regular existing {artifact}: {path}"
        )
    try:
        actual = path.read_bytes()
    except OSError as error:
        raise FileExistsError(f"cannot verify existing {artifact}: {path}") from error
    if actual != expected:
        raise FileExistsError(
            f"refusing to overwrite differing or corrupt existing {artifact}: {path}"
        )
    return True


def _publish_write_once_json(path: Path, value: Any, *, artifact: str) -> None:
    """Atomically publish canonical JSON without ever replacing an existing path.

    A fully written and fsynced sibling temporary file is hard-linked into place,
    which gives publication no-overwrite semantics. A concurrent or repeated
    publisher may reuse only the exact canonical bytes it independently derived.
    """

    expected = canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if _existing_artifact_matches(path, expected, artifact=artifact):
        return

    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    published = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            if not _existing_artifact_matches(path, expected, artifact=artifact):
                raise AssertionError("unreachable existing-artifact state")
        else:
            published = True
            _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)
        if published:
            _fsync_directory(path.parent)


def load_yaml(relative_path: str) -> dict[str, Any]:
    value = yaml.safe_load((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{relative_path} must contain a YAML mapping")
    return value


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_schema(name: str) -> dict[str, Any]:
    value = _load_json(SCHEMA_DIRECTORY / name)
    if not isinstance(value, dict):
        raise TypeError(f"{name} must contain a JSON object")
    return value


def _file_manifest() -> list[dict[str, str]]:
    return [
        {"path": relative, "sha256": sha256_file(PROJECT_ROOT / relative)}
        for relative in sorted(NORMATIVE_PATHS)
    ]


def _root_from_files(files: Iterable[dict[str, str]]) -> str:
    payload = {"algorithm": "SHA-256", "files": list(files)}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def protocol_root() -> str:
    """Return the verified current protocol root, never a stale seal value."""

    verification = verify_protocol(require_seal=True)
    if not verification.ok or verification.root_sha256 is None:
        detail = "; ".join(
            f"{check.identifier}: {check.evidence}" for check in verification.failures
        )
        raise ValueError(f"MVX P0 protocol is not verified: {detail}")
    return verification.root_sha256


def _metric_checks(protocol: Mapping[str, Any], metrics: Mapping[str, Any]) -> list[ProtocolCheck]:
    metric_items = metrics.get("metrics")
    if not isinstance(metric_items, list):
        return [
            ProtocolCheck("METRIC_IDS_UNIQUE", False, "metrics.metrics must be an array"),
            ProtocolCheck("ENDPOINT_HIERARCHY_CLOSED", False, "metric dictionary is unavailable"),
        ]
    valid_items = [item for item in metric_items if isinstance(item, Mapping)]
    metric_ids = [item.get("id") for item in valid_items]
    ids_valid = (
        len(valid_items) == len(metric_items)
        and bool(metric_ids)
        and all(isinstance(identifier, str) and identifier for identifier in metric_ids)
        and len(metric_ids) == len(set(metric_ids))
    )
    id_check = ProtocolCheck(
        "METRIC_IDS_UNIQUE",
        ids_valid,
        f"metrics={len(metric_ids)}, unique={len(set(metric_ids))}",
    )

    hierarchy = protocol.get("endpoint_hierarchy")
    if not isinstance(hierarchy, Mapping):
        return [
            id_check,
            ProtocolCheck(
                "ENDPOINT_HIERARCHY_CLOSED", False, "endpoint_hierarchy must be a mapping"
            ),
        ]
    hierarchy_valid = True
    details: list[str] = []
    endpoint_occurrences: list[str] = []
    metric_levels = {item.get("level") for item in valid_items}
    if not all(isinstance(level, str) and level for level in metric_levels):
        hierarchy_valid = False
        details.append("one or more metric levels are empty or invalid")
    if set(hierarchy) != metric_levels:
        hierarchy_valid = False
        details.append(
            f"levels hierarchy={sorted(map(str, hierarchy))}, metrics={sorted(map(str, metric_levels))}"
        )
    for level, endpoint_value in hierarchy.items():
        if not isinstance(endpoint_value, list) or not all(
            isinstance(identifier, str) and identifier for identifier in endpoint_value
        ):
            hierarchy_valid = False
            details.append(f"{level!r} is not a non-empty-ID array")
            continue
        endpoint_occurrences.extend(endpoint_value)
        expected = [item["id"] for item in valid_items if item.get("level") == level]
        if len(endpoint_value) != len(set(endpoint_value)):
            hierarchy_valid = False
            details.append(f"duplicate endpoint in {level}")
        if set(endpoint_value) != set(expected) or len(endpoint_value) != len(expected):
            hierarchy_valid = False
            details.append(
                f"{level}: missing={sorted(set(expected) - set(endpoint_value))}, "
                f"extra={sorted(set(endpoint_value) - set(expected))}"
            )
    if len(endpoint_occurrences) != len(set(endpoint_occurrences)):
        hierarchy_valid = False
        details.append("an endpoint occurs in more than one hierarchy level")

    expected_aggregate = {
        "loader_throughput_ratio",
        "gpu_idle_median",
        "overfit32_loss_reduction",
        "terminal_usable_fraction",
        "class_A_fraction_verified_closed",
        "release_critical_blocker_count",
        "systematic_stratum_disadvantage",
    }
    expected_units = {
        "critical_failure": "boolean",
        "core_conformance": "boolean",
        "terminal_processing": "boolean",
        "interoperability_exact": "boolean",
        "fidelity_primary_failure": "boolean",
        "usability_class": "class",
        "terminal_status_correct": "boolean",
        "provenance_complete": "boolean",
        "wire_roundtrip_exact": "boolean",
        "hd95_symmetric_p": "pixel_pitch",
        "topology_exact_ge_8p": "boolean",
        "chamfer_symmetric_rms_p": "pixel_pitch",
        "occupancy_iou": "ratio",
        "normal_median_deg": "degree",
        "normal_p95_deg": "degree",
        "relative_volume_error": "relative_error",
        "relative_area_error": "relative_error",
        "openings_recall_ge_8p": "ratio",
        "cross_view_agreement_real": "ratio",
        "cross_view_agreement_oracle": "ratio",
        "cross_view_eligible_coverage": "ratio",
        "ray_overflow_fraction": "ratio",
        "topologically_critical_omission_count": "count",
        "loader_throughput_ratio": "ratio_to_cost_matched_contiguous_tensor",
        "gpu_idle_median": "ratio",
        "package_size_bytes": "byte",
        "encode_seconds": "second",
        "decode_seconds": "second",
        "overfit32_loss_reduction": "ratio",
        "terminal_usable_fraction": "ratio",
        "class_A_fraction_verified_closed": "ratio",
        "release_critical_blocker_count": "count",
        "systematic_stratum_disadvantage": "boolean",
        "curvature_error": "inverse_pixel_pitch",
        "spectral_error": "normalized_l2_error",
        "perceptual_embedding_distance": "embedding_distance",
        "learned_decoder_quality": "ratio",
    }
    bounded_ratios = {
        "occupancy_iou",
        "openings_recall_ge_8p",
        "cross_view_agreement_real",
        "cross_view_agreement_oracle",
        "cross_view_eligible_coverage",
        "ray_overflow_fraction",
        "gpu_idle_median",
        "overfit32_loss_reduction",
        "terminal_usable_fraction",
        "class_A_fraction_verified_closed",
        "learned_decoder_quality",
    }
    nonnegative = {
        "hd95_symmetric_p",
        "chamfer_symmetric_rms_p",
        "relative_volume_error",
        "relative_area_error",
        "topologically_critical_omission_count",
        "loader_throughput_ratio",
        "package_size_bytes",
        "encode_seconds",
        "decode_seconds",
        "release_critical_blocker_count",
        "curvature_error",
        "spectral_error",
        "perceptual_embedding_distance",
    }
    by_id = {item.get("id"): item for item in valid_items if isinstance(item.get("id"), str)}
    contract_errors: list[str] = []
    if set(metrics.get("scope_contract", {})) != {"LINEAGE", "AGGREGATE"}:
        contract_errors.append("scope_contract must define LINEAGE and AGGREGATE exactly")
    if set(by_id) != set(expected_units):
        contract_errors.append("unit contract does not cover the exact metric dictionary")
    for identifier, expected_unit in expected_units.items():
        item = by_id.get(identifier, {})
        expected_scope = "AGGREGATE" if identifier in expected_aggregate else "LINEAGE"
        if item.get("scope") != expected_scope:
            contract_errors.append(f"{identifier} scope={item.get('scope')!r}")
        if item.get("unit") != expected_unit:
            contract_errors.append(f"{identifier} unit={item.get('unit')!r}")
        metric_range = item.get("range")
        if identifier in bounded_ratios and metric_range != {"minimum": 0.0, "maximum": 1.0}:
            contract_errors.append(f"{identifier} must be bounded [0,1]")
        if identifier in {"normal_median_deg", "normal_p95_deg"} and metric_range != {
            "minimum": 0.0,
            "maximum": 180.0,
        }:
            contract_errors.append(f"{identifier} must be bounded [0,180]")
        if identifier in nonnegative and metric_range not in (
            {"minimum": 0.0},
            {"minimum": 0},
        ):
            contract_errors.append(f"{identifier} must be non-negative")
    critical_definition = str(by_id.get("critical_failure", {}).get("definition", "")).lower()
    blocker_definition = str(
        by_id.get("release_critical_blocker_count", {}).get("definition", "")
    ).lower()
    if (
        "per-lineage" not in critical_definition
        or "never encodes a population-level rule" not in critical_definition
    ):
        contract_errors.append("critical_failure must be strictly lineage-scoped")
    if "only metric that incorporates population-level" not in blocker_definition:
        contract_errors.append("population blockers must be isolated in the aggregate metric")
    try:
        lineage_schema = _load_schema("metric-record.schema.json")
        aggregate_schema = _load_schema("aggregate-metric-record.schema.json")
        lineage_schema_ids = set(lineage_schema["properties"]["metric_id"]["enum"])
        aggregate_schema_ids = set(aggregate_schema["properties"]["metric_id"]["enum"])
        schema_scope_valid = (
            lineage_schema["properties"]["scope"] == {"const": "LINEAGE"}
            and aggregate_schema["properties"]["scope"] == {"const": "AGGREGATE"}
            and lineage_schema_ids == set(by_id) - expected_aggregate
            and aggregate_schema_ids == expected_aggregate
            and not lineage_schema_ids & aggregate_schema_ids
        )
        if not schema_scope_valid:
            contract_errors.append("lineage/aggregate schema metric enums do not partition metrics")
    except (KeyError, TypeError, OSError, ValueError, json.JSONDecodeError) as error:
        schema_scope_valid = False
        contract_errors.append(f"metric schema scope check failed: {error}")
    return [
        id_check,
        ProtocolCheck(
            "ENDPOINT_HIERARCHY_CLOSED",
            ids_valid and hierarchy_valid,
            "exact level-by-level equality with no duplicate endpoints"
            if ids_valid and hierarchy_valid
            else "; ".join(details) or "metric identifiers are invalid",
        ),
        ProtocolCheck(
            "METRIC_SCOPE_UNITS_BOUNDS_CLOSED",
            ids_valid and not contract_errors,
            "30 lineage and 7 aggregate metrics have exact units and metric-specific bounds"
            if ids_valid and not contract_errors
            else "; ".join(contract_errors),
        ),
        ProtocolCheck(
            "METRIC_SCHEMAS_SCOPE_CLOSED",
            ids_valid and schema_scope_valid,
            "lineage and aggregate schema enums are disjoint and cover all 37 metrics",
        ),
    ]


def _cohort_checks(protocol: Mapping[str, Any], split: Mapping[str, Any]) -> list[ProtocolCheck]:
    from morphoia.mvx.selection import DEFAULT_VISIBLE_MILESTONES

    cohorts = protocol.get("cohorts", {})
    confirmation = split.get("confirmation_targets", {})
    protocol_confirmation = cohorts.get("confirmation_composition", {})
    milestone_composition = cohorts.get("milestone_composition", {})
    nested = split.get("nested_milestones", {})

    target_valid = confirmation == EXPECTED_CONFIRMATION_TARGETS
    target_valid = target_valid and protocol_confirmation == {
        "fixtures_C0_C9": 100,
        "objaverse": 600,
        "modelnet40": 100,
        "thingi10k": 80,
        "google_scanned_objects": 60,
        "human_anatomy": 50,
        "plants": 10,
    }
    if isinstance(confirmation, Mapping):
        totals = {
            field: sum(
                int(target.get(field, -10_000))
                for target in confirmation.values()
                if isinstance(target, Mapping)
            )
            for field in ("total", "development", "calibration", "blind")
        }
    else:
        totals = {}
    target_valid = target_valid and totals == {
        "total": 1000,
        "development": 500,
        "calibration": 200,
        "blind": 300,
    }
    ratios = split.get("ratios", {})
    target_valid = target_valid and all(
        math.isclose(float(ratios.get(name, -1)), expected)
        for name, expected in (("development", 0.5), ("calibration", 0.2), ("blind", 0.3))
    )

    n300_observable = milestone_composition.get("n300_observable")
    n300_real = cohorts.get("n300_real_composition")
    n300_nested = nested.get("n300")
    n300_valid = n300_observable == {
        "fixtures_development_or_calibration": 70,
        "real_development_or_calibration": 230,
    }
    n300_valid = n300_valid and isinstance(n300_real, Mapping) and sum(n300_real.values()) == 230
    n300_valid = n300_valid and n300_nested == DEFAULT_VISIBLE_MILESTONES["n300"]

    expected_gate_sizes = [12, 30, 100, 300, 1000]
    gates = cohorts.get("gates")
    gate_sizes = (
        [item.get("n") for item in gates if isinstance(item, Mapping)]
        if isinstance(gates, list)
        else []
    )
    milestone_sums = {
        name: sum(values.values())
        for name, values in nested.items()
        if name in {"n12", "n30", "n100", "n300", "n1000"} and isinstance(values, Mapping)
    }
    nesting_valid = gate_sizes == expected_gate_sizes and milestone_sums == {
        "n12": 12,
        "n30": 30,
        "n100": 100,
        "n300": 300,
        "n1000": 1000,
    }
    nesting_valid = nesting_valid and milestone_composition.get("n1000") == {
        "fixtures": 100,
        "real_lineages": 900,
    }
    nesting_valid = (
        nesting_valid
        and {name: nested.get(name) for name in ("n12", "n30", "n100", "n300")}
        == DEFAULT_VISIBLE_MILESTONES
    )
    return [
        ProtocolCheck(
            "CONFIRMATION_TARGETS_EXACT",
            target_valid,
            f"totals={totals}; expected total/development/calibration/blind=1000/500/200/300",
        ),
        ProtocolCheck(
            "N300_COMPOSITION_EXACT",
            n300_valid,
            "n300=70 fixtures + 230 real lineages" if n300_valid else "n300 composition mismatch",
        ),
        ProtocolCheck(
            "COHORT_NESTING_COUNTS",
            nesting_valid,
            f"gate_sizes={gate_sizes}, nested_sums={milestone_sums}",
        ),
    ]


def _seed_and_algorithm_checks(
    selection: Mapping[str, Any], split: Mapping[str, Any]
) -> list[ProtocolCheck]:
    bootstrap_seed = split.get("bootstrap_seed_hex")
    selection_policy = split.get("selection_seed_commitment_policy")
    split_policy = split.get("split_salt_commitment_policy")
    forbidden_keys = {
        "selection_seed_hex",
        "production_selection_seed_hex",
        "split_salt",
        "split_salt_hex",
        "production_split_salt_hex",
        "split_salt_sha256",
    } & set(split)
    seed_valid = (
        isinstance(bootstrap_seed, str)
        and bool(HEX_256.fullmatch(bootstrap_seed))
        and "selection_seed_hex" not in split
    )
    policy_text = f"{selection_policy!s} {split_policy!s}"
    production_salt_valid = (
        isinstance(selection_policy, Mapping)
        and isinstance(split_policy, Mapping)
        and not forbidden_keys
        and "eligible-records root is sealed" in policy_text
        and "external process-locked custodian" in policy_text
        and "No production" in policy_text
        and "shared development workspace" in policy_text
        and "Publish SHA-256" in policy_text
    )
    algorithms_valid = (
        split.get("algorithm_id") == "MVX-GROUP-STRATIFIED-HMAC-2"
        and split.get("algorithm_version") == "2.0.0"
        and selection.get("algorithm_id") == "MVX-COHORT-HMAC-2"
        and selection.get("algorithm_version") == "2.0.0"
        and split.get("selection", {}).get("specification") == "selection-spec.yaml"
        and split.get("selection", {}).get("algorithm_id") == "MVX-COHORT-HMAC-2"
        and split.get("selection", {}).get("algorithm_version") == "2.0.0"
        and "G1 external custodian" in str(selection.get("seed_source", ""))
        and "eligible-records root is sealed" in str(selection.get("seed_source", ""))
        and bool(split.get("development_diagnostic_fallback_objective", {}).get("formula"))
        and bool(split.get("production_secondary_balance", {}).get("prefix_objective"))
        and "exact two-dimensional integer dynamic programming"
        in " ".join(map(str, split.get("procedure", [])))
        and split.get("output", {}).get("production_quota_deviation")
        == "must be zero for total and every confirmation-target stratum; any non-zero value blocks G1"
        and bool(split.get("test_vectors"))
        and str(split.get("hmac_message_encoding", "")).startswith(
            "MVX-HMAC-RANK-LP-UTF8-1"
        )
        and selection.get("complexity_quantile", {}).get("tie_break_seed")
        == "The fixed public split-spec.yaml bootstrap_seed_hex, never the production selection seed or split salt."
        and bool(selection.get("complexity_quantile", {}).get("circularity_guard"))
        and split.get("custody_precommit", {}).get("required_before_secret_use") is True
        and split.get("custody_precommit", {}).get("algorithm_id")
        == "MVX-G1-PRECOMMIT-SHA256-1"
    )
    return [
        ProtocolCheck(
            "PUBLIC_SEEDS_256_BIT",
            seed_valid,
            "only the bootstrap seed is public at P0; no production selection preimage exists",
        ),
        ProtocolCheck(
            "PRODUCTION_SPLIT_SALT_COMMITTED_ONLY",
            production_salt_valid,
            "selection/split commit-reveal policies generate both preimages after the eligible root"
            if production_salt_valid
            else f"forbidden_keys={sorted(forbidden_keys)}, policies_valid=false",
        ),
        ProtocolCheck(
            "SELECTION_AND_SPLIT_SPECS_CLOSED",
            algorithms_valid,
            "selection and grouped-split algorithm contracts are linked and explicit",
        ),
    ]


def _execution_control_check(
    protocol: Mapping[str, Any], split: Mapping[str, Any]
) -> ProtocolCheck:
    control = protocol.get("execution_control")
    if not isinstance(control, Mapping):
        return ProtocolCheck(
            "EXECUTION_RESTART_GUARDS_CLOSED", False, "execution_control must be a mapping"
        )
    expected_bindings = [
        "protocol_root_sha256",
        "split_sha256",
        "source_sha256",
        "lineage_id",
        "profile_sha256",
        "config_sha256",
        "code_sha256",
        "environment_sha256",
        "phase_id",
        "stage_id",
    ]
    precommit = split.get("custody_precommit", {})
    output = split.get("output", {})
    publication_contract = str(control.get("precommit_publication", ""))
    publication_contract_tokens = (
        "Ed25519 v2",
        "raw-byte trusted-publisher registry hash",
        "registry epoch",
        "G0 seal hash",
        "Production loads no caller registry",
        "READY_FOR_PRODUCTION_G1",
    )
    passed = (
        control.get("execution_plan_schema")
        == "schemas/mvx/0.2.1/execution-plan.schema.json"
        and control.get("checkpoint_schema")
        == "schemas/mvx/0.2.1/stage-checkpoint.schema.json"
        and control.get("work_id_algorithm") == "MVX-WORK-ID-SHA256-JCS-1"
        and control.get("work_id_binds") == expected_bindings
        and "TERMINAL" in str(control.get("skip_rule", ""))
        and "SHA-256" in str(control.get("skip_rule", ""))
        and control.get("blind_open_once_interruption")
        == "FAIL_CLOSED_NO_AUTOMATIC_RERUN"
        and "COMPLETED marker" in str(control.get("backup_rule", ""))
        and "ALREADY_COMMITTED" in str(control.get("duplicate_publication", ""))
        and all(token in publication_contract for token in publication_contract_tokens)
        and isinstance(precommit, Mapping)
        and precommit.get("required_before_secret_use") is True
        and "receipt written last" in str(output.get("publication_transaction", ""))
    )
    evidence = (
        "content-derived work IDs, hash-verified terminal skips, open-once fail-closed, "
        "precommit and atomic completion markers are frozen"
        if passed
        else "execution, resume, precommit or backup contract is incomplete"
    )
    return ProtocolCheck("EXECUTION_RESTART_GUARDS_CLOSED", passed, evidence)


def _error_taxonomy_checks(errors: Mapping[str, Any]) -> list[ProtocolCheck]:
    code_items = errors.get("codes")
    if not isinstance(code_items, list):
        return [ProtocolCheck("ERROR_TAXONOMY_CLOSED", False, "codes must be an array")]
    valid_items = [item for item in code_items if isinstance(item, Mapping)]
    codes = [item.get("code") for item in valid_items]
    classes = [item.get("class") for item in valid_items]
    unique = (
        len(valid_items) == len(code_items)
        and bool(codes)
        and all(isinstance(code, str) and code.startswith("MVX-") for code in codes)
        and len(codes) == len(set(codes))
        and set(codes) == EXPECTED_ERROR_CODES
        and len(classes) == len(set(classes))
    )
    payload_states = errors.get("payload_state_codes")
    mapping = errors.get("terminal_mapping")
    expected_statuses = set(errors.get("job_terminal_statuses", []))
    if not isinstance(payload_states, list) or not isinstance(mapping, Mapping):
        return [
            ProtocolCheck(
                "ERROR_TAXONOMY_CLOSED", False, "payload_state_codes or terminal_mapping invalid"
            )
        ]
    mapping_keys_valid = set(mapping) == expected_statuses | {"no_manifest_possible"}
    mapping_exact = {
        str(status): tuple(group) if isinstance(group, list) else ()
        for status, group in mapping.items()
    } == EXPECTED_ERROR_TERMINAL_MAPPING
    mapped_occurrences = [
        code for group in mapping.values() if isinstance(group, list) for code in group
    ]
    coverage = Counter([*mapped_occurrences, *payload_states])
    coverage_valid = set(coverage) == set(codes) and all(count == 1 for count in coverage.values())
    by_code = {item.get("code"): item for item in valid_items}
    payload_valid = all(
        code in by_code
        and by_code[code].get("terminal") is False
        and by_code[code].get("scope") == "ray"
        and code not in mapped_occurrences
        for code in payload_states
    ) and payload_states == ["MVX-E001", "MVX-E002"]
    terminal_valid = all(
        by_code.get(code, {}).get("terminal") is True
        for status in expected_statuses
        for code in mapping.get(status, [])
    )
    no_manifest = mapping.get("no_manifest_possible", [])
    terminal_valid = terminal_valid and all(
        by_code.get(code, {}).get("terminal") is False for code in no_manifest
    )
    mapping_status_by_code = {
        code: status
        for status, group in mapping.items()
        if status != "no_manifest_possible" and isinstance(group, list)
        for code in group
    }
    mapping_status_by_code.update(
        {code: None for code in mapping.get("no_manifest_possible", []) if isinstance(code, str)}
    )

    precedence = errors.get("terminal_precedence")
    precedence_errors: list[str] = []
    if not isinstance(precedence, Mapping):
        precedence_errors.append("terminal_precedence must be a mapping")
        ordered_fault_codes: list[Any] = []
        coverage_vectors: list[Any] = []
        multi_fault_vectors: list[Any] = []
    else:
        ordered = precedence.get("ordered_fault_codes")
        ordered_fault_codes = list(ordered) if isinstance(ordered, list) else []
        coverage = precedence.get("coverage_vectors")
        coverage_vectors = list(coverage) if isinstance(coverage, list) else []
        multi = precedence.get("multi_fault_vectors")
        multi_fault_vectors = list(multi) if isinstance(multi, list) else []

    success_code = precedence.get("success_code") if isinstance(precedence, Mapping) else None
    no_manifest_code = (
        precedence.get("no_manifest_code") if isinstance(precedence, Mapping) else None
    )
    expected_fault_codes = set(codes) - set(payload_states) - {"MVX-OK"}
    if (
        len(ordered_fault_codes) != len(set(ordered_fault_codes))
        or set(ordered_fault_codes) != expected_fault_codes
        or tuple(ordered_fault_codes) != EXPECTED_ERROR_PRECEDENCE
    ):
        precedence_errors.append(
            "ordered_fault_codes must equal the frozen total order and cover every fault exactly once"
        )
    if success_code != "MVX-OK" or no_manifest_code != "MVX-X002":
        precedence_errors.append("success_code or no_manifest_code is not canonical")

    pipeline = precedence.get("pipeline") if isinstance(precedence, Mapping) else None
    if not isinstance(pipeline, list) or not pipeline:
        precedence_errors.append("pipeline must contain ordered non-empty stages")
        flattened_pipeline: list[Any] = []
    else:
        stage_names: list[Any] = []
        flattened_pipeline = []
        for stage in pipeline:
            if not isinstance(stage, Mapping):
                precedence_errors.append("every pipeline stage must be a mapping")
                continue
            stage_names.append(stage.get("stage"))
            stage_codes = stage.get("codes")
            if not isinstance(stage_codes, list) or not stage_codes:
                precedence_errors.append("every pipeline stage must contain codes")
                continue
            flattened_pipeline.extend(stage_codes)
        if len(stage_names) != len(set(stage_names)) or not all(
            isinstance(name, str) and name for name in stage_names
        ):
            precedence_errors.append("pipeline stage names must be unique non-empty strings")
        if flattened_pipeline != ordered_fault_codes:
            precedence_errors.append("pipeline flattening must equal ordered_fault_codes")

    rank = {code: index for index, code in enumerate(ordered_fault_codes)}

    def expected_primary(candidates: list[Any]) -> Any:
        if not candidates:
            return success_code
        if any(code not in rank for code in candidates):
            return None
        return min(candidates, key=rank.__getitem__)

    expected_coverage_keys = {"MVX-OK", *expected_fault_codes}
    coverage_primary: list[Any] = []
    coverage_ids: list[Any] = []
    for vector in coverage_vectors:
        if not isinstance(vector, Mapping):
            precedence_errors.append("coverage vector must be a mapping")
            continue
        coverage_ids.append(vector.get("id"))
        candidates = vector.get("candidates")
        candidates = list(candidates) if isinstance(candidates, list) else []
        primary = vector.get("expected_primary")
        coverage_primary.append(primary)
        singleton_valid = (primary == success_code and candidates == []) or (
            primary != success_code and candidates == [primary]
        )
        if (
            not singleton_valid
            or primary != expected_primary(candidates)
            or vector.get("expected_terminal_status") != mapping_status_by_code.get(primary)
        ):
            precedence_errors.append(f"invalid coverage vector {vector.get('id')!r}")
    if (
        len(coverage_ids) != len(set(coverage_ids))
        or len(coverage_primary) != len(set(coverage_primary))
        or set(coverage_primary) != expected_coverage_keys
    ):
        precedence_errors.append("coverage vectors must cover success and every fault exactly once")

    expected_adjacent_pairs = {
        frozenset((ordered_fault_codes[index], ordered_fault_codes[index + 1]))
        for index in range(max(0, len(ordered_fault_codes) - 1))
    }
    observed_adjacent_pairs: list[frozenset[Any]] = []
    multi_ids: list[Any] = []
    for vector in multi_fault_vectors:
        if not isinstance(vector, Mapping):
            precedence_errors.append("multi-fault vector must be a mapping")
            continue
        multi_ids.append(vector.get("id"))
        candidates = vector.get("candidates")
        candidates = list(candidates) if isinstance(candidates, list) else []
        observed_adjacent_pairs.append(frozenset(candidates))
        primary = vector.get("expected_primary")
        if (
            len(candidates) != 2
            or len(set(candidates)) != 2
            or primary != expected_primary(candidates)
            or vector.get("expected_terminal_status") != mapping_status_by_code.get(primary)
        ):
            precedence_errors.append(f"invalid multi-fault vector {vector.get('id')!r}")
    if (
        len(multi_ids) != len(set(multi_ids))
        or len(observed_adjacent_pairs) != len(set(observed_adjacent_pairs))
        or set(observed_adjacent_pairs) != expected_adjacent_pairs
    ):
        precedence_errors.append("multi-fault vectors must cover every adjacent precedence pair")

    precedence_valid = not precedence_errors
    passed = (
        unique
        and expected_statuses == {"PASS", "DECLARED_LIMIT", "REJECT", "FAIL"}
        and mapping_keys_valid
        and mapping_exact
        and coverage_valid
        and payload_valid
        and terminal_valid
        and precedence_valid
    )
    return [
        ProtocolCheck(
            "ERROR_TAXONOMY_CLOSED",
            passed,
            (
                "every unique code/class is covered once; ray payload states are non-terminal; "
                "the terminal pipeline, total order, singleton coverage and every adjacent "
                "multi-fault pair are executable"
            )
            if passed
            else (
                f"codes={len(codes)}, unique_codes={len(set(codes))}, "
                f"unique_classes={len(set(classes))}, mapping_keys={sorted(map(str, mapping))}, "
                f"precedence_errors={precedence_errors}"
            ),
        )
    ]


def _eligibility_checks(eligibility: Mapping[str, Any]) -> list[ProtocolCheck]:
    topology = eligibility.get("topology_status")
    topology_valid = isinstance(topology, Mapping) and set(topology) == {"V", "O", "N", "U"}
    if topology_valid:
        topology_valid = all(
            isinstance(topology[code], Mapping)
            and bool(topology[code].get("label"))
            and bool(topology[code].get("definition"))
            and bool(topology[code].get("primary_outcome"))
            for code in ("V", "O", "N", "U")
        )

    never_exclude = eligibility.get("never_exclude_because")
    expected_never_exclude = {
        "geometry is open, non-manifold, degenerate or difficult",
        "reconstruction fidelity is poor",
        "MVX overflows",
        "the decoder fails",
        "a profile produces an unfavourable metric",
    }
    exclusions = eligibility.get("exclude_before_split_if")
    outcome_tokens = {
        "reconstruction",
        "fidelity",
        "mvx",
        "overflow",
        "decoder",
        "profile",
        "metric",
        "topology score",
    }
    exclusion_text = (
        " ".join(map(str, exclusions)).lower() if isinstance(exclusions, list) else "<invalid>"
    )
    outcome_independent = (
        isinstance(never_exclude, list)
        and set(never_exclude) == expected_never_exclude
        and isinstance(exclusions, list)
        and bool(exclusions)
        and not any(token in exclusion_text for token in outcome_tokens)
    )

    selection_rules = eligibility.get("eligible_for_selection_only_if")
    selection_text = (
        " ".join(map(str, selection_rules)).lower() if isinstance(selection_rules, list) else ""
    )
    selection_ready = (
        "p2a source-only audit" in selection_text
        and "topology_status" in selection_text
        and "complexity_quantile" in selection_text
        and "source-only triangle count" in selection_text
        and "selection-spec.yaml" in selection_text
    )
    return [
        ProtocolCheck(
            "ELIGIBILITY_TOPOLOGY_STATES_EXACT",
            topology_valid,
            f"topology states={sorted(map(str, topology)) if isinstance(topology, Mapping) else []}",
        ),
        ProtocolCheck(
            "ELIGIBILITY_OUTCOME_FIREWALL",
            outcome_independent,
            "pre-split exclusions are source/legal/provenance only; adverse outcomes stay eligible",
        ),
        ProtocolCheck(
            "ELIGIBILITY_REQUIRES_P2A_FIELDS",
            selection_ready,
            "selection requires source-only P2a topology_status and complexity_quantile",
        ),
    ]


def _classification_and_denominator_checks(metrics: Mapping[str, Any]) -> ProtocolCheck:
    classification = metrics.get("usability_classification")
    metric_items = metrics.get("metrics")
    if not isinstance(classification, Mapping) or not isinstance(metric_items, list):
        return ProtocolCheck(
            "CLASSES_AND_DENOMINATORS_CLOSED", False, "classification or metrics array missing"
        )
    class_keys = {
        key
        for key, value in classification.items()
        if key in {"A", "B", "C", "D"} and isinstance(value, Mapping)
    }
    class_text = {
        key: " ".join(
            map(
                str,
                classification[key].get("if_all", classification[key].get("if_any", [])),
            )
        ).lower()
        for key in class_keys
    }
    by_id = {
        item.get("id"): item
        for item in metric_items
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    terminal_definition = str(
        by_id.get("terminal_usable_fraction", {}).get("definition", "")
    ).lower()
    class_a_definition = str(
        by_id.get("class_A_fraction_verified_closed", {}).get("definition", "")
    ).lower()
    aggregation = metrics.get("release_aggregation")
    passed = (
        metrics.get("dictionary_version") == "0.1.1"
        and metrics.get("failed_reconstructions") == "retained in denominators"
        and classification.get("evaluation_order") == ["D", "A", "B", "C"]
        and class_keys == {"A", "B", "C", "D"}
        and "fail or missing" in class_text["D"]
        and "terminal status is pass" in class_text["A"]
        and "pass or declared_limit" in class_text["B"]
        and "pass or declared_limit" in class_text["C"]
        and "all attempted in-domain real lineages" in terminal_definition
        and "fail, missing and class d remain in the denominator" in terminal_definition
        and "every attempted topology-status v real lineage" in class_a_definition
        and "fail, missing and classes b/c/d remain in the denominator" in class_a_definition
        and isinstance(aggregation, Mapping)
        and aggregation.get("denominator_unit") == "lineage_id after leakage grouping"
        and aggregation.get("no_file_or_pose_weighting") is True
        and "release fail" in str(aggregation.get("zero_denominator", "")).lower()
    )
    return ProtocolCheck(
        "CLASSES_AND_DENOMINATORS_CLOSED",
        passed,
        "A/B/C/D terminal rules and release denominators are explicit and failure-retaining",
    )


def _statistical_checks(
    statistical: Mapping[str, Any], protocol: Mapping[str, Any]
) -> list[ProtocolCheck]:
    del (
        protocol
    )  # Endpoint closure is checked separately; this contract is exact and self-contained.
    expected_blockers = {
        "no_lineage_critical_failure": ("critical_failure", "LINEAGE"),
        "core_conformance_exact": ("core_conformance", "LINEAGE"),
        "interoperability_exact": ("interoperability_exact", "LINEAGE"),
        "wire_roundtrip_exact": ("wire_roundtrip_exact", "LINEAGE"),
        "cross_view_oracle_exact": ("cross_view_agreement_oracle", "LINEAGE"),
        "no_topologically_critical_omission": (
            "topologically_critical_omission_count",
            "LINEAGE",
        ),
        "no_population_release_blocker": ("release_critical_blocker_count", "AGGREGATE"),
    }
    exact = statistical.get("exact_blockers")
    blocker_rules = exact.get("rules") if isinstance(exact, Mapping) else None
    observed_blockers: dict[str, tuple[Any, Any]] = {}
    blocker_valid = isinstance(blocker_rules, list) and bool(blocker_rules)
    if isinstance(blocker_rules, list):
        for rule in blocker_rules:
            if not isinstance(rule, Mapping):
                blocker_valid = False
                continue
            identifier = rule.get("id")
            if not isinstance(identifier, str) or identifier in observed_blockers:
                blocker_valid = False
                continue
            observed_blockers[identifier] = (rule.get("metric_id"), rule.get("scope"))
            blocker_valid = blocker_valid and bool(rule.get("pass_if"))
    blocker_valid = (
        blocker_valid
        and observed_blockers == expected_blockers
        and "outside Holm" in str(exact.get("rationale", ""))
        and "missing" in str(exact.get("missing", "")).lower()
        and "blocker" in str(exact.get("missing", "")).lower()
    )

    expected_hypotheses = {
        "real_geometry_and_topology": {
            "hd95_failure_rate": (
                "hd95_symmetric_p",
                "LINEAGE",
                "exact_one_sided_binomial_lower_tail",
                0.10,
                "smaller_is_better",
            ),
            "topology_failure_rate": (
                "topology_exact_ge_8p",
                "LINEAGE",
                "exact_one_sided_binomial_lower_tail",
                0.10,
                "smaller_is_better",
            ),
            "openings_failure_rate": (
                "openings_recall_ge_8p",
                "LINEAGE",
                "exact_one_sided_binomial_lower_tail",
                0.10,
                "smaller_is_better",
            ),
            "cross_view_agreement_failure_rate": (
                "cross_view_agreement_real",
                "LINEAGE",
                "exact_one_sided_binomial_lower_tail",
                0.10,
                "smaller_is_better",
            ),
            "cross_view_coverage_failure_rate": (
                "cross_view_eligible_coverage",
                "LINEAGE",
                "exact_one_sided_binomial_lower_tail",
                0.10,
                "smaller_is_better",
            ),
        },
        "release_population": {
            "terminal_usable_rate": (
                "terminal_usable_fraction",
                "AGGREGATE",
                "exact_one_sided_binomial_upper_tail",
                0.95,
                "larger_is_better",
            ),
            "verified_closed_class_A_rate": (
                "class_A_fraction_verified_closed",
                "AGGREGATE",
                "exact_one_sided_binomial_upper_tail",
                0.90,
                "larger_is_better",
            ),
        },
    }
    multiplicity = statistical.get("multiplicity")
    families = multiplicity.get("families") if isinstance(multiplicity, Mapping) else None
    hypothesis_errors: list[str] = []
    observed_hypotheses: dict[str, dict[str, tuple[Any, Any, Any, Any, Any]]] = {}
    all_hypothesis_ids: list[str] = []
    expanded_count = 0
    if not isinstance(families, Mapping):
        hypothesis_errors.append("multiplicity.families must be a mapping")
    else:
        for family_name, family in families.items():
            entries = family.get("hypotheses") if isinstance(family, Mapping) else None
            if not isinstance(entries, list):
                hypothesis_errors.append(f"{family_name}.hypotheses must be an array")
                continue
            observed_hypotheses[family_name] = {}
            for entry in entries:
                if not isinstance(entry, Mapping):
                    hypothesis_errors.append(f"{family_name} contains a non-object hypothesis")
                    continue
                identifier = entry.get("id")
                if not isinstance(identifier, str) or identifier in all_hypothesis_ids:
                    hypothesis_errors.append(f"duplicate or invalid hypothesis id {identifier!r}")
                    continue
                all_hypothesis_ids.append(identifier)
                observed_hypotheses[family_name][identifier] = (
                    entry.get("metric_id"),
                    entry.get("scope"),
                    entry.get("test"),
                    entry.get("null_boundary"),
                    entry.get("direction"),
                )
                if entry.get("strata") != ["objaverse_IID", "objaverse_OOD"]:
                    hypothesis_errors.append(f"{identifier} has invalid claim-bearing strata")
                else:
                    expanded_count += 2
                required_text = ("estimand", "H0", "H1", "raw_p_value", "missing")
                if not all(
                    isinstance(entry.get(field), str) and entry.get(field)
                    for field in required_text
                ):
                    hypothesis_errors.append(f"{identifier} lacks executable hypothesis fields")
                if "MISSING" not in str(entry.get("missing", "")):
                    hypothesis_errors.append(f"{identifier} does not fail closed on missing data")
    holm_valid = (
        isinstance(multiplicity, Mapping)
        and multiplicity.get("method") == "Holm_step_down"
        and math.isclose(float(multiplicity.get("alpha", -1)), 0.05)
        and observed_hypotheses == expected_hypotheses
        and not hypothesis_errors
        and bool(multiplicity.get("family_expansion"))
        and "0.05/(m-i+1)" in str(multiplicity.get("algorithm", ""))
        and "Every required H0 must be rejected" in str(multiplicity.get("algorithm", ""))
        and multiplicity.get("no_threshold_selection_on_blind") is True
    )

    ai = statistical.get("AI_and_loader_authorisation")
    ai_valid = (
        isinstance(ai, Mapping)
        and ai.get("multiplicity") == "outside_Holm_deterministic_gate"
        and ai.get("repetitions")
        == "5 pre-declared benchmark or training seeds fixed before calibration freeze"
        and ai.get("loader_throughput_ratio", {}).get("scope") == "AGGREGATE"
        and "0.80" in str(ai.get("loader_throughput_ratio", {}).get("pass_if", ""))
        and ai.get("overfit32_loss_reduction", {}).get("scope") == "AGGREGATE"
        and "0.90" in str(ai.get("overfit32_loss_reduction", {}).get("pass_if", ""))
        and ai.get("gpu_idle_median", {}).get("scope") == "AGGREGATE"
        and ai.get("gpu_idle_median", {}).get("reporting_only") is True
        and "missing" in str(ai.get("missing", "")).lower()
        and "fails" in str(ai.get("missing", "")).lower()
    )

    population = statistical.get("population_inference")
    failure_rate = statistical.get("failure_rate")
    weights = (
        population.get("fixed_descriptive_mixture_weights", {})
        if isinstance(population, Mapping)
        else {}
    )
    population_rule = str(population.get("rule", "")) if isinstance(population, Mapping) else ""
    prohibition = (
        str(failure_rate.get("prohibition", "")) if isinstance(failure_rate, Mapping) else ""
    )
    population_valid = (
        isinstance(population, Mapping)
        and population.get("real_blind_lineages") == 270
        and population.get("analytic_blind_fixtures") == 30
        and isinstance(weights, Mapping)
        and set(weights)
        == {
            "objaverse",
            "modelnet40",
            "thingi10k",
            "google_scanned_objects",
            "human_anatomy",
            "plants",
        }
        and math.isclose(sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-12)
        and "Do not use n270" in prohibition
        and "IID population" in prohibition
        and "not an IID population claim" in population_rule
        and "Only Objaverse has a pre-registered population claim" in population_rule
        and "other datasets are transfer stress strata" in population_rule
    )

    disadvantage = statistical.get("systematic_disadvantage")
    disadvantage_valid = (
        isinstance(disadvantage, Mapping)
        and disadvantage.get("claim_bearing_strata") == ["objaverse_IID", "objaverse_OOD"]
        and disadvantage.get("minimum_independent_clusters") == 15
        and math.isclose(float(disadvantage.get("absolute_class_A_margin", -1)), 0.10)
        and "-0.10" in str(disadvantage.get("rule", ""))
        and "INSUFFICIENT_EVIDENCE" in str(disadvantage.get("small_strata", ""))
    )
    return [
        ProtocolCheck(
            "EXACT_BLOCKERS_SEPARATED",
            blocker_valid,
            f"exact blockers={sorted(observed_blockers)}",
        ),
        ProtocolCheck(
            "HOLM_PRIMARY_FAMILIES_EXACT",
            holm_valid,
            f"families={sorted(observed_hypotheses)}, hypotheses={len(all_hypothesis_ids)}, "
            f"expanded={expanded_count}, errors={hypothesis_errors}",
        ),
        ProtocolCheck(
            "AI_AUTHORIZATION_EXECUTABLE",
            ai_valid,
            "five pre-declared aggregate repetitions; minimum threshold and missing-data fail rule",
        ),
        ProtocolCheck(
            "POPULATION_INFERENCE_BOUNDED",
            population_valid,
            f"descriptive_weight_sum={sum(float(value) for value in weights.values()):.16f}"
            if isinstance(weights, Mapping) and weights
            else "descriptive weights unavailable",
        ),
        ProtocolCheck(
            "SYSTEMATIC_DISADVANTAGE_EXACT",
            disadvantage_valid,
            "margin=0.10 and minimum independent clusters=15 for Objaverse IID/OOD",
        ),
    ]


def _clarification_checks(clarifications: Mapping[str, Any]) -> list[ProtocolCheck]:
    phase = clarifications.get("phase_order")
    phase_decision = str(phase.get("decision", "")) if isinstance(phase, Mapping) else ""
    phase_reason = str(phase.get("reason", "")) if isinstance(phase, Mapping) else ""
    phase_valid = (
        "P1a census, then P2a" in phase_decision
        and "then G1 selection/split" in phase_decision
        and "then P2b/P3" in phase_decision
        and "topology_status" in phase_reason
        and "complexity_quantile" in phase_reason
    )

    custody = clarifications.get("blind_custody")
    custody_text = (
        f"{custody.get('decision', '')} {custody.get('limitation', '')}"
        if isinstance(custody, Mapping)
        else ""
    )
    custody_valid = (
        "selection-seed and split-salt" in custody_text
        and "outside the repository" in custody_text
        and "publishes both SHA-256 commitments before use" in custody_text
        and "until G5" in custody_text
        and "process-locked holdout" in custody_text
        and "not independent human double blinding" in custody_text
        and "mandatory at G0" in custody_text
        and "mandatory before selection at G1" in custody_text
    )

    population = clarifications.get("population_bound")
    population_text = str(population.get("decision", "")) if isinstance(population, Mapping) else ""
    corpus_claim = clarifications.get("corpus_claim")
    claim_text = (
        f"{corpus_claim.get('decision', '')} {corpus_claim.get('not_claimed', '')}"
        if isinstance(corpus_claim, Mapping)
        else ""
    )
    milestone = clarifications.get("milestone_100")
    cad_text = (
        f"{milestone.get('decision', '')} {milestone.get('limitation', '')}"
        if isinstance(milestone, Mapping)
        else ""
    )
    claim_valid = (
        "Never use n=270 as a single IID population" in population_text
        and "Objaverse is the only pre-registered population claim" in population_text
        and "feasibility v1 only" in claim_text
        and "stronger multi-domain population claim" in claim_text
        and "ModelNet40" in cad_text
        and "Thingi10K" in cad_text
        and "stress proxies" in cad_text
        and "not native parametric CAD" in cad_text
        and "No native CAD-intent claim" in cad_text
    )
    return [
        ProtocolCheck(
            "CLARIFICATION_PHASE_ORDER",
            phase_valid,
            "P1a -> P2a -> G1 -> P2b/P3 is explicit and field-driven",
        ),
        ProtocolCheck(
            "CLARIFICATION_CUSTODY_BOUNDARY",
            custody_valid,
            "process-locked custody, G0 dry-run, G1 private store and G5 unlock are explicit",
        ),
        ProtocolCheck(
            "CLARIFICATION_CLAIM_BOUNDARY",
            claim_valid,
            "Objaverse-only population claim and native-CAD-proxy limits are explicit",
        ),
    ]


def _authority_check(protocol: Mapping[str, Any]) -> ProtocolCheck:
    authority = protocol.get("authority")
    if not isinstance(authority, Mapping):
        return ProtocolCheck("AUTHORITY_DOMAINS_SPLIT", False, "authority must be a mapping")
    technical = authority.get("technical_contract_precedence")
    experimental = authority.get("experimental_decision_precedence")
    boundary = str(authority.get("boundary", "")).lower()
    passed = (
        technical
        == [
            "p0_implementation_clarifications_1.0.2",
            "implementation_addendum_0.2.1",
            "technical_report_0.2",
        ]
        and experimental
        == [
            "this_pre_registration_and_its_explicit_implementation_clarifications",
            "experimental_plan_1.0",
        ]
        and "may not loosen" in boundary
        and "wire contract" in boundary
        and "precedence" not in authority
    )
    return ProtocolCheck(
        "AUTHORITY_DOMAINS_SPLIT",
        passed,
        "technical wire authority and experimental decision authority are separate",
    )


def _release_checks(release: Mapping[str, Any]) -> list[ProtocolCheck]:
    gates = release.get("gates")
    gate_ids = set(gates) if isinstance(gates, Mapping) else set()
    gate_check = ProtocolCheck(
        "GATES_COMPLETE", gate_ids == EXPECTED_GATES, f"gates={sorted(map(str, gate_ids))}"
    )
    gate_contract_errors: list[str] = []
    try:
        gate_schema = _load_schema("gate-verdict.schema.json")
        schema_catalog = gate_schema["$defs"]["gateCriterionIds"]
    except (KeyError, TypeError, ValueError) as error:
        schema_catalog = {}
        gate_contract_errors.append(f"gate criterion schema catalog unavailable: {error}")
    observed_catalog: dict[str, tuple[str, ...]] = {}
    if isinstance(schema_catalog, Mapping):
        for gate, entry in schema_catalog.items():
            values = entry.get("enum") if isinstance(entry, Mapping) else None
            if isinstance(values, list) and all(isinstance(value, str) for value in values):
                observed_catalog[str(gate)] = tuple(values)
    if observed_catalog != EXPECTED_GATE_CRITERIA:
        gate_contract_errors.append("schema gate criterion IDs differ from the frozen catalog")
    if isinstance(gates, Mapping):
        for gate, expected_ids in EXPECTED_GATE_CRITERIA.items():
            gate_entry = gates.get(gate)
            pass_if = gate_entry.get("pass_if") if isinstance(gate_entry, Mapping) else None
            if (
                not isinstance(pass_if, list)
                or len(pass_if) != len(expected_ids)
                or not all(isinstance(item, str) and item.strip() for item in pass_if)
            ):
                gate_contract_errors.append(
                    f"{gate}.pass_if must contain {len(expected_ids)} non-empty criteria"
                )
    gate_criteria_check = ProtocolCheck(
        "GATE_CRITERIA_CATALOG_CLOSED",
        not gate_contract_errors,
        "G0-G7 have exact gate-specific criterion IDs and complete non-empty pass conditions"
        if not gate_contract_errors
        else "; ".join(gate_contract_errors),
    )

    decisions = release.get("final_decisions")
    order = decisions.get("evaluation_order") if isinstance(decisions, Mapping) else None
    decision_names = (
        {
            name
            for name, value in decisions.items()
            if isinstance(decisions, Mapping)
            and isinstance(value, Mapping)
            and "conditions" in value
            and "action" in value
        }
        if isinstance(decisions, Mapping)
        else set()
    )
    expected_order = [
        "NO_GO_FORMAT",
        "NO_GO_DECODER",
        "NO_GO_INSUFFICIENT_EVIDENCE",
        "GO_R32",
        "GO_LIMITED",
        "GO",
    ]
    exclusivity = release.get("decision_exclusivity", {})
    order_valid = (
        order == expected_order
        and len(order) == len(set(order))
        and set(order) == decision_names
        and "first matching verdict only" in str(exclusivity.get("rule", ""))
        and exclusivity.get("no_match") == "NO_GO_INSUFFICIENT_EVIDENCE"
    )
    return [
        gate_check,
        gate_criteria_check,
        ProtocolCheck(
            "RELEASE_DECISION_ORDER_EXCLUSIVE",
            order_valid,
            f"evaluation_order={order}, decisions={sorted(decision_names)}",
        ),
    ]


def _role_check(roles: Mapping[str, Any]) -> ProtocolCheck:
    required_roles = {
        "maintainer_and_final_decision_authority",
        "protocol_custodian",
        "holdout_custodian",
        "holdout_unlock_authority",
        "technical_adjudicator",
        "anatomy_adjudicator",
        "statistical_reviewer",
        "second_implementation_owner",
    }
    assignments = roles.get("assignments")
    if not isinstance(assignments, Mapping):
        return ProtocolCheck("CUSTODY_ROLES_GATED", False, "assignments must be a mapping")
    holdout = assignments.get("holdout_custodian", {})
    unlock = assignments.get("holdout_unlock_authority", {})
    holdout_state = str(holdout.get("operational_state", ""))
    holdout_vacancy = str(holdout.get("vacancy_effect", ""))
    unlock_state = str(unlock.get("operational_state", ""))
    holdout_state_tokens = (
        "synthetic_dry_run_required_for_G0",
        "signed receipt v2",
        "raw registry",
        "epoch",
        "G0 seal",
        "BLOCKED",
        "READY_FOR_PRODUCTION_G1",
        "required before any G1 selection",
    )
    passed = (
        required_roles <= set(assignments)
        and all(token in holdout_state for token in holdout_state_tokens)
        and "G1" in holdout_vacancy
        and "required before G1" in unlock_state
    )
    return ProtocolCheck(
        "CUSTODY_ROLES_GATED",
        passed,
        "custody dry-run is required for G0 and production boundary/unlock integration before G1",
    )


def _authoritative_pdf_check(protocol: Mapping[str, Any]) -> ProtocolCheck:
    authority = protocol.get("authority", {})
    inputs = authority.get("normative_inputs", []) if isinstance(authority, Mapping) else []
    declared = {
        item.get("path"): item.get("sha256")
        for item in inputs
        if isinstance(item, Mapping) and isinstance(item.get("path"), str)
    }
    actual = {
        relative: sha256_file(PROJECT_ROOT / relative)
        for relative in EXPECTED_PDF_HASHES
        if (PROJECT_ROOT / relative).is_file()
    }
    passed = declared == EXPECTED_PDF_HASHES and actual == EXPECTED_PDF_HASHES
    mismatches = sorted(
        relative
        for relative, expected in EXPECTED_PDF_HASHES.items()
        if declared.get(relative) != expected or actual.get(relative) != expected
    )
    return ProtocolCheck(
        "AUTHORITATIVE_PDF_HASHES",
        passed,
        "all three authoritative PDFs match fixed SHA-256 values"
        if passed
        else f"mismatch={mismatches}",
    )


def _local_source_closure_check() -> ProtocolCheck:
    local_sources = set(_relative_rglob(PROJECT_ROOT / "src" / "morphoia", "*.py"))
    normative_sources = {
        relative
        for relative in NORMATIVE_PATHS
        if relative.startswith("src/morphoia/") and relative.endswith(".py")
    }
    missing = sorted(local_sources - normative_sources)
    extra = sorted(normative_sources - local_sources)
    passed = not missing and not extra and bool(local_sources)
    return ProtocolCheck(
        "LOCAL_SOURCE_CLOSURE_SEALED",
        passed,
        f"all {len(local_sources)} local Morphoia Python modules are normative"
        if passed
        else f"missing={missing}, extra={extra}",
    )
def _gate_verdict_contract_check() -> ProtocolCheck:
    try:
        schema = _load_schema("gate-verdict.schema.json")
        validator = Draft202012Validator(schema)

        def payload(gate: str, verdict: str = "PASS") -> dict[str, Any]:
            return {
                "schema_version": "0.1.0",
                "gate": gate,
                "verdict": verdict,
                "protocol_root_sha256": "a" * 64,
                "criteria": [
                    {"id": identifier, "passed": True, "evidence": "synthetic evidence"}
                    for identifier in EXPECTED_GATE_CRITERIA[gate]
                ],
                "blockers": [],
                "deviations": [],
            }

        contract_errors: list[str] = []
        for gate, expected_ids in EXPECTED_GATE_CRITERIA.items():
            valid = payload(gate)
            if not validator.is_valid(valid):
                contract_errors.append(f"valid {gate} PASS is rejected")

            missing = json.loads(json.dumps(valid))
            missing["criteria"].pop()
            if validator.is_valid(missing):
                contract_errors.append(f"{gate} accepts a missing criterion")

            duplicate = json.loads(json.dumps(valid))
            duplicate["criteria"][-1] = json.loads(json.dumps(duplicate["criteria"][0]))
            duplicate["criteria"][-1]["evidence"] = "different duplicate evidence"
            if validator.is_valid(duplicate):
                contract_errors.append(f"{gate} accepts a duplicate criterion ID")

            unknown = json.loads(json.dumps(valid))
            unknown["criteria"][0]["id"] = f"{gate}_UNKNOWN"
            if validator.is_valid(unknown):
                contract_errors.append(f"{gate} accepts an unknown criterion ID")

            if len(valid["criteria"]) != len(expected_ids):
                contract_errors.append(f"{gate} synthetic criterion count differs")

        empty_pass = payload("G0")
        empty_pass["criteria"] = []
        if validator.is_valid(empty_pass):
            contract_errors.append("PASS accepts an empty criterion array")

        forged_pass = payload("G0")
        forged_pass["criteria"][0]["passed"] = False
        if validator.is_valid(forged_pass):
            contract_errors.append("PASS accepts a failed criterion")

        blocked_pass = payload("G0")
        blocked_pass["blockers"] = ["unresolved blocker"]
        if validator.is_valid(blocked_pass):
            contract_errors.append("PASS accepts a blocker")

        incoherent_fail = payload("G0", "FAIL")
        incoherent_fail["blockers"] = ["declared without failed criterion"]
        if validator.is_valid(incoherent_fail):
            contract_errors.append("FAIL accepts all criteria passing")

        coherent_fail = payload("G0", "FAIL")
        coherent_fail["criteria"][0]["passed"] = False
        coherent_fail["blockers"] = ["expected failed criterion"]
        if not validator.is_valid(coherent_fail):
            contract_errors.append("coherent FAIL is rejected")

        incoherent_conditional = payload("G0", "CONDITIONAL")
        incoherent_conditional["criteria"][0]["passed"] = False
        incoherent_conditional["blockers"] = ["condition"]
        if validator.is_valid(incoherent_conditional):
            contract_errors.append("CONDITIONAL accepts no deviation/condition record")

        coherent_conditional = payload("G0", "CONDITIONAL")
        coherent_conditional["criteria"][0]["passed"] = False
        coherent_conditional["blockers"] = ["condition"]
        coherent_conditional["deviations"] = ["owned condition due before the next gate"]
        if not validator.is_valid(coherent_conditional):
            contract_errors.append("coherent CONDITIONAL is rejected")
    except Exception as error:  # noqa: BLE001 - schema contract must fail closed
        contract_errors = [str(error)]
    return ProtocolCheck(
        "GATE_VERDICT_CONTRACT_CLOSED",
        not contract_errors,
        "gate-specific IDs are exhaustive and PASS/FAIL/CONDITIONAL are coherent"
        if not contract_errors
        else "; ".join(contract_errors),
    )


def _calibration_freeze_contract_check() -> ProtocolCheck:
    try:
        schema = _load_schema("calibration-freeze.schema.json")
        validator = Draft202012Validator(schema)
        baseline = _load_json(EXAMPLE_DIRECTORY / "calibration-freeze.valid.json")
        contract_errors: list[str] = []
        if not validator.is_valid(baseline):
            contract_errors.append("baseline calibration freeze example is invalid")

        thresholds = baseline.get("thresholds") if isinstance(baseline, Mapping) else None
        if not isinstance(thresholds, Mapping) or set(thresholds) != set(EXPECTED_G4_THRESHOLDS):
            contract_errors.append("threshold keys differ from the exact G4 catalog")
        else:
            for metric_id, (direction, p0_value) in EXPECTED_G4_THRESHOLDS.items():
                value = thresholds.get(metric_id)
                if (
                    not isinstance(value, Mapping)
                    or value.get("direction") != direction
                    or value.get("p0_value") != p0_value
                ):
                    contract_errors.append(f"{metric_id} direction/P0 value differs")
                    continue

                removed = json.loads(json.dumps(baseline))
                del removed["thresholds"][metric_id]
                if validator.is_valid(removed):
                    contract_errors.append(f"missing {metric_id} is accepted")

                changed_direction = json.loads(json.dumps(baseline))
                changed_direction["thresholds"][metric_id]["direction"] = (
                    "min" if direction != "min" else "max"
                )
                if validator.is_valid(changed_direction):
                    contract_errors.append(f"changed direction for {metric_id} is accepted")

                changed_p0 = json.loads(json.dumps(baseline))
                changed_p0["thresholds"][metric_id]["p0_value"] = (
                    not p0_value if isinstance(p0_value, bool) else float(p0_value) + 0.01
                )
                if validator.is_valid(changed_p0):
                    contract_errors.append(f"changed P0 value for {metric_id} is accepted")

                relaxed = json.loads(json.dumps(baseline))
                if direction == "max":
                    relaxed_value = float(p0_value) + max(abs(float(p0_value)) * 0.01, 0.0001)
                elif direction == "min":
                    relaxed_value = float(p0_value) - 0.0001
                elif isinstance(p0_value, bool):
                    relaxed_value = not p0_value
                else:
                    relaxed_value = float(p0_value) + 1.0
                relaxed["thresholds"][metric_id]["frozen_value"] = relaxed_value
                if validator.is_valid(relaxed):
                    contract_errors.append(f"relaxed frozen threshold for {metric_id} is accepted")

                if direction in {"max", "min"}:
                    stricter = json.loads(json.dumps(baseline))
                    stricter_value = (
                        float(p0_value) / 2.0
                        if direction == "max"
                        else (float(p0_value) + 1.0) / 2.0
                    )
                    stricter["thresholds"][metric_id]["frozen_value"] = stricter_value
                    if not validator.is_valid(stricter):
                        contract_errors.append(
                            f"equal-or-stricter frozen threshold for {metric_id} is rejected"
                        )

        extra = json.loads(json.dumps(baseline))
        extra["thresholds"]["unregistered_metric"] = {
            "direction": "max",
            "p0_value": 1.0,
            "frozen_value": 1.0,
        }
        if validator.is_valid(extra):
            contract_errors.append("unregistered threshold is accepted")

        channels = baseline.get("channels") if isinstance(baseline, Mapping) else None
        if (
            not isinstance(channels, list)
            or not REQUIRED_G4_CHANNELS <= set(channels)
            or not set(channels) <= ALLOWED_G4_CHANNELS
        ):
            contract_errors.append("baseline channel set violates the Core channel catalog")
        else:
            for channel in REQUIRED_G4_CHANNELS:
                missing_channel = json.loads(json.dumps(baseline))
                missing_channel["channels"].remove(channel)
                if validator.is_valid(missing_channel):
                    contract_errors.append(f"missing mandatory channel {channel} is accepted")
            unknown_channel = json.loads(json.dumps(baseline))
            unknown_channel["channels"].append("unregistered_channel")
            if validator.is_valid(unknown_channel):
                contract_errors.append("unregistered channel is accepted")
    except Exception as error:  # noqa: BLE001 - schema contract must fail closed
        contract_errors = [str(error)]
    return ProtocolCheck(
        "CALIBRATION_FREEZE_CONTRACT_CLOSED",
        not contract_errors,
        "G4 channels and exact P0 threshold directions/values permit only equal-or-stricter freezes"
        if not contract_errors
        else "; ".join(contract_errors),
    )


def _schema_checks() -> list[ProtocolCheck]:
    schema_paths = sorted(SCHEMA_DIRECTORY.glob("*.schema.json"))
    schemas: dict[str, dict[str, Any]] = {}
    schema_errors: list[str] = []
    for path in schema_paths:
        try:
            schema = _load_json(path)
            if not isinstance(schema, dict):
                raise TypeError("schema root is not an object")
            Draft202012Validator.check_schema(schema)
            schemas[path.name] = schema
        except Exception as error:  # noqa: BLE001 - preserve validator diagnostics
            schema_errors.append(f"{path.name}: {error}")
    schemas_valid = bool(schema_paths) and not schema_errors and len(schemas) == len(schema_paths)
    schema_check = ProtocolCheck(
        "JSON_SCHEMAS_VALID",
        schemas_valid,
        f"{len(schemas)} Draft 2020-12 schemas compile"
        if schemas_valid
        else "; ".join(schema_errors) or "no schemas found",
    )

    example_errors: list[str] = []
    index_path = EXAMPLE_DIRECTORY / "index.json"
    indexed_schema_names: list[str] = []
    indexed_instance_names: list[str] = []
    if not index_path.is_file():
        example_errors.append("schema-examples/index.json is missing")
    else:
        try:
            index = _load_json(index_path)
            entries = index.get("examples") if isinstance(index, Mapping) else None
            if not isinstance(entries, list):
                raise TypeError("index.examples must be an array")
            for entry in entries:
                if not isinstance(entry, Mapping):
                    raise TypeError("every index entry must be an object")
                schema_name = entry.get("schema")
                instance_name = entry.get("instance")
                if not isinstance(schema_name, str) or not isinstance(instance_name, str):
                    raise TypeError("schema and instance names must be strings")
                if (
                    Path(schema_name).name != schema_name
                    or Path(instance_name).name != instance_name
                ):
                    raise ValueError("schema example paths must be plain file names")
                indexed_schema_names.append(schema_name)
                indexed_instance_names.append(instance_name)
                if schema_name not in schemas:
                    example_errors.append(f"unknown schema {schema_name}")
                    continue
                instance_path = EXAMPLE_DIRECTORY / instance_name
                if not instance_path.is_file():
                    example_errors.append(f"missing instance {instance_name}")
                    continue
                Draft202012Validator(schemas[schema_name]).validate(_load_json(instance_path))
        except Exception as error:  # noqa: BLE001 - preserve validator diagnostics
            example_errors.append(str(error))
    schema_names = set(schemas)
    actual_instances = {
        path.name for path in EXAMPLE_DIRECTORY.glob("*.valid.json") if path.is_file()
    }
    if len(indexed_schema_names) != len(set(indexed_schema_names)):
        example_errors.append("duplicate schema entry in example index")
    if len(indexed_instance_names) != len(set(indexed_instance_names)):
        example_errors.append("duplicate instance entry in example index")
    if set(indexed_schema_names) != schema_names:
        example_errors.append(
            "schema index coverage differs: "
            f"missing={sorted(schema_names - set(indexed_schema_names))}, "
            f"extra={sorted(set(indexed_schema_names) - schema_names)}"
        )
    if set(indexed_instance_names) != actual_instances:
        example_errors.append(
            "example file coverage differs: "
            f"unindexed={sorted(actual_instances - set(indexed_instance_names))}, "
            f"missing={sorted(set(indexed_instance_names) - actual_instances)}"
        )
    examples_valid = schemas_valid and not example_errors
    example_check = ProtocolCheck(
        "SCHEMA_EXAMPLES_VALID",
        examples_valid,
        f"{len(indexed_schema_names)} indexed examples validate with exact schema coverage"
        if examples_valid
        else "; ".join(example_errors),
    )
    return [
        schema_check,
        example_check,
        _gate_verdict_contract_check(),
        _calibration_freeze_contract_check(),
    ]


def _frozen_split_vector_check(split: Mapping[str, Any]) -> ProtocolCheck:
    try:
        from morphoia.mvx.split import assign_grouped_split

        vector = _load_json(P0_DIRECTORY / "split-test-vectors.json")
        if not isinstance(vector, Mapping):
            raise TypeError("test vector root must be an object")
        if vector.get("algorithm_id") != split.get("algorithm_id"):
            raise ValueError("test vector algorithm does not match split specification")
        salt = vector.get("salt_hex")
        if not isinstance(salt, str) or not HEX_256.fullmatch(salt):
            raise ValueError("test vector salt must encode 256 bits")
        records = vector.get("records")
        if not isinstance(records, list):
            raise TypeError("test vector records must be an array")
        expected = vector.get("expected_assignments")
        actual = assign_grouped_split(records, salt_hex=salt)
        reversed_actual = assign_grouped_split(reversed(records), salt_hex=salt)
        passed = actual == expected and reversed_actual == expected
        evidence = "frozen vector and reversed-input execution match"
    except Exception as error:  # noqa: BLE001 - fail closed on executable-vector errors
        passed = False
        evidence = str(error)
    return ProtocolCheck("FROZEN_SPLIT_VECTOR_EXECUTES", passed, evidence)


def _production_algorithms_check(split: Mapping[str, Any]) -> ProtocolCheck:
    try:
        from morphoia.mvx.selection import (
            DEFAULT_VISIBLE_MILESTONES,
            select_visible_milestones,
        )
        from morphoia.mvx.split import assign_grouped_split

        salt = "33" * 32
        targets = {
            "objaverse": {
                "total": 6,
                "development": 3,
                "calibration": 1,
                "blind": 2,
            },
            "fixtures_C0_C9": {
                "total": 4,
                "development": 2,
                "calibration": 1,
                "blind": 1,
            },
        }
        split_rows: list[dict[str, Any]] = []
        for stratum, count in (("objaverse", 6), ("fixtures_C0_C9", 4)):
            for index in range(count):
                row = {
                    "lineage_id": f"{stratum}-L{index}",
                    "leakage_group_id": f"{stratum}-G{index}",
                    "selection_stratum": stratum,
                    "dataset": stratum,
                    "topology_status": "V",
                    "complexity_quantile": index,
                    "category": "ood" if index == 0 else "visible",
                    "creator_group": f"{stratum}-C{index}",
                    "source_uid": f"{stratum}-S{index}",
                    "eligibility": "ELIGIBLE",
                }
                if stratum == "objaverse" and index == 0:
                    row["forced_split"] = "blind"
                    row["blind_scope"] = "OOD"
                split_rows.append(row)
        assignments = assign_grouped_split(
            split_rows,
            salt_hex=salt,
            exact_targets_by_stratum=targets,
        )
        exact = assignments["objaverse-L0"] == "blind"
        for stratum, target in targets.items():
            for split_name in ("development", "calibration", "blind"):
                observed = sum(
                    destination == split_name
                    for lineage, destination in assignments.items()
                    if lineage.startswith(f"{stratum}-")
                )
                exact = exact and observed == target[split_name]

        milestone_rows: list[dict[str, str]] = []
        for stratum, count in DEFAULT_VISIBLE_MILESTONES["n300"].items():
            for index in range(count):
                milestone_rows.append(
                    {
                        "lineage_id": f"{stratum}-M{index}",
                        "leakage_group_id": f"{stratum}-MG{index}",
                        "selection_stratum": stratum,
                        "split": "development" if index % 2 else "calibration",
                    }
                )
        milestones = select_visible_milestones(
            milestone_rows,
            selection_seed_hex="44" * 32,
        )
        nested = set(milestones["n12"]) < set(milestones["n30"]) < set(milestones["n100"]) < set(
            milestones["n300"]
        ) and [len(milestones[name]) for name in ("n12", "n30", "n100", "n300")] == [
            12,
            30,
            100,
            300,
        ]
        passed = exact and nested and split.get("algorithm_version") == "2.0.0"
        evidence = "exact production quotas, forced OOD and nested visible milestones execute"
    except Exception as error:  # noqa: BLE001 - executable contract must fail closed
        passed = False
        evidence = str(error)
    return ProtocolCheck("PRODUCTION_SELECTION_SPLIT_EXECUTES", passed, evidence)


def _custody_dry_run_check() -> ProtocolCheck:
    try:
        from morphoia.mvx.custody import (
            _validate_precommit_publication_receipt,
            synthetic_dry_run,
            validate_trusted_publishers,
        )
        from morphoia.mvx.custody import canonical_json_bytes as custody_json_bytes

        release = synthetic_dry_run()
        public = release["public_manifest"]
        visible = release["visible_manifest"]
        Draft202012Validator(_load_schema("custody-public.schema.json")).validate(public)
        Draft202012Validator(_load_schema("custody-visible.schema.json")).validate(visible)
        synthetic_precommit = _load_json(
            EXAMPLE_DIRECTORY / "custody-precommit.valid.json"
        )
        publication_receipt = _load_json(
            EXAMPLE_DIRECTORY / "precommit-publication-receipt.valid.json"
        )
        synthetic_publishers = _load_json(
            EXAMPLE_DIRECTORY / "trusted-publishers.valid.json"
        )
        _validate_precommit_publication_receipt(
            publication_receipt,
            precommit=synthetic_precommit,
            trusted_publishers=synthetic_publishers,
            allow_synthetic=True,
        )
        trusted_publishers = validate_trusted_publishers(
            _load_json(PROJECT_ROOT / "docs/mvx/validation/p0/trusted-publishers.json")
        )
        production_publishers = [
            publisher
            for publisher in trusted_publishers["publishers"]
            if publisher["production"]
        ]
        combined = custody_json_bytes(release).decode("utf-8")
        forbidden = (
            "SYNTH-BLIND-001",
            "SYNTH-GROUP-BLIND",
            "/synthetic/private/blind.glb",
        )
        visible_splits = {item.get("split") for item in visible.get("assignments", [])}
        freeze_id = public.get("freeze_id")
        precommit_sha256 = public.get("precommit_sha256")
        selection_commitment = public.get("selection_seed_commitment_sha256")
        split_commitment = public.get("split_salt_commitment_sha256")
        passed = (
            "assignments" not in public
            and not any(fragment in combined for fragment in forbidden)
            and visible_splits <= {"development", "calibration"}
            and public.get("counts", {}).get("blind") == 1
            and isinstance(freeze_id, str)
            and freeze_id.startswith("mvx-g1-")
            and isinstance(precommit_sha256, str)
            and bool(HEX_256.fullmatch(precommit_sha256))
            and isinstance(selection_commitment, str)
            and bool(HEX_256.fullmatch(selection_commitment))
            and isinstance(split_commitment, str)
            and bool(HEX_256.fullmatch(split_commitment))
            and selection_commitment != split_commitment
            and visible.get("freeze_id") == freeze_id
            and visible.get("precommit_sha256") == precommit_sha256
            and (
                (
                    trusted_publishers["g1_state"]
                    == "BLOCKED_UNTIL_EXTERNAL_WORM_PUBLISHER_KEY_IS_VERSIONED"
                    and not production_publishers
                )
                or (
                    trusted_publishers["g1_state"] == "READY_FOR_PRODUCTION_G1"
                    and len(production_publishers) == len(trusted_publishers["publishers"])
                    and bool(production_publishers)
                )
            )
        )
        evidence = (
            "public/visible synthetic custody views are schema-valid and blind-redacted"
            if passed
            else "synthetic custody output leaked or exposed an invalid split"
        )
    except Exception as error:  # noqa: BLE001 - fail closed on custody implementation errors
        passed = False
        evidence = str(error)
    return ProtocolCheck("CUSTODY_SYNTHETIC_DRY_RUN", passed, evidence)


def _predecessor_archive_check() -> ProtocolCheck:
    """Verify the immediate superseded seal and its effective-failure record."""

    archive = P0_DIRECTORY / "audit" / "superseded-1.0.1-p0"
    seal_path = archive / "seal.json"
    verdict_path = archive / "G0-verdict.json"
    record_path = archive / "supersession.json"
    try:
        seal = _load_json(seal_path)
        verdict = _load_json(verdict_path)
        record = _load_json(record_path)
        if not all(isinstance(item, Mapping) for item in (seal, verdict, record)):
            raise TypeError("predecessor archive documents must be JSON objects")
        seal_files = seal.get("files")
        if not isinstance(seal_files, list):
            raise TypeError("predecessor seal files must be an array")
        seal_file_hash = sha256_file(seal_path)
        verdict_file_hash = sha256_file(verdict_path)
        record_file_hash = sha256_file(record_path)
        passed = (
            seal_file_hash == PREDECESSOR_SEAL_SHA256
            and record_file_hash == SUPERSESSION_RECORD_SHA256
            and seal.get("protocol_version") == "1.0.1-p0"
            and seal.get("protocol_root_sha256") == PREDECESSOR_PROTOCOL_ROOT
            and _root_from_files(seal_files) == PREDECESSOR_PROTOCOL_ROOT
            and verdict.get("gate") == "G0"
            and verdict.get("verdict") == "PASS"
            and verdict.get("protocol_root_sha256") == PREDECESSOR_PROTOCOL_ROOT
            and record.get("superseded_protocol_version") == "1.0.1-p0"
            and record.get("superseded_protocol_root_sha256")
            == PREDECESSOR_PROTOCOL_ROOT
            and record.get("seal_file_sha256") == seal_file_hash
            and record.get("g0_verdict_file_sha256") == verdict_file_hash
            and record.get("effective_verdict") == "FAIL"
            and record.get("experimental_outcomes_observed") is False
            and record.get("production_cohort_selected") is False
            and record.get("production_split_created") is False
            and record.get("superseded_by") == PROTOCOL_VERSION
        )
        evidence = (
            "predecessor seal, original G0 PASS and effective FAIL supersession are hash-linked"
            if passed
            else "predecessor archive, hashes or effective supersession fields differ"
        )
    except Exception as error:  # noqa: BLE001 - any archive ambiguity blocks sealing
        passed = False
        evidence = str(error)
    return ProtocolCheck("PREDECESSOR_ARCHIVE_CHAIN_VALID", passed, evidence)


def _semantic_checks() -> list[ProtocolCheck]:
    checks: list[ProtocolCheck] = []
    try:
        protocol = load_yaml("docs/mvx/validation/p0/protocol.yaml")
        metrics = load_yaml("docs/mvx/validation/p0/metrics.yaml")
        eligibility = load_yaml("docs/mvx/validation/p0/eligibility.yaml")
        selection = load_yaml("docs/mvx/validation/p0/selection-spec.yaml")
        split = load_yaml("docs/mvx/validation/p0/split-spec.yaml")
        statistical = load_yaml("docs/mvx/validation/p0/statistical-plan.yaml")
        errors = load_yaml("docs/mvx/validation/p0/error-codes.yaml")
        release = load_yaml("docs/mvx/validation/p0/release-criteria.yaml")
        roles = load_yaml("docs/mvx/validation/p0/roles.yaml")
        clarifications = load_yaml("docs/mvx/validation/p0/implementation-clarifications.yaml")
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        return [ProtocolCheck("NORMATIVE_DOCUMENT_PARSE", False, str(error))]

    checks.extend(
        (
            ProtocolCheck(
                "PROTOCOL_ID_VERSION",
                protocol.get("protocol_id") == "MORPHOIA-MVX-FEASIBILITY-V1"
                and protocol.get("protocol_version") == PROTOCOL_VERSION,
                f"protocol_id={protocol.get('protocol_id')!r}, "
                f"protocol_version={protocol.get('protocol_version')!r}",
            ),
            ProtocolCheck(
                "PROTOCOL_FROZEN",
                protocol.get("status") == "FROZEN",
                f"status={protocol.get('status')!r}",
            ),
            ProtocolCheck(
                "AUXILIARY_DOCUMENT_VERSIONS",
                eligibility.get("rules_version") == "0.1.1"
                and metrics.get("dictionary_version") == "0.1.1"
                and statistical.get("plan_version") == PROTOCOL_VERSION
                and clarifications.get("clarifications_version") == PROTOCOL_VERSION,
                f"eligibility={eligibility.get('rules_version')!r}, "
                f"metrics={metrics.get('dictionary_version')!r}, "
                f"statistics={statistical.get('plan_version')!r}, "
                f"clarifications={clarifications.get('clarifications_version')!r}",
            ),
        )
    )
    try:
        checks.extend(_metric_checks(protocol, metrics))
        checks.append(_classification_and_denominator_checks(metrics))
        checks.extend(_eligibility_checks(eligibility))
        checks.extend(_cohort_checks(protocol, split))
        checks.extend(_seed_and_algorithm_checks(selection, split))
        checks.append(_execution_control_check(protocol, split))
        checks.extend(_statistical_checks(statistical, protocol))
        checks.extend(_error_taxonomy_checks(errors))
        checks.extend(_clarification_checks(clarifications))
        checks.append(_authority_check(protocol))
        checks.extend(_release_checks(release))
        checks.append(_role_check(roles))
        checks.append(_authoritative_pdf_check(protocol))
        checks.append(_predecessor_archive_check())
        checks.append(_local_source_closure_check())
        checks.extend(_schema_checks())
        checks.append(_frozen_split_vector_check(split))
        checks.append(_production_algorithms_check(split))
        checks.append(_custody_dry_run_check())
    except Exception as error:  # noqa: BLE001 - any unchecked invariant blocks sealing
        checks.append(ProtocolCheck("SEMANTIC_CHECKS_COMPLETE", False, str(error)))
    return checks


def _existing_current_seal(files: list[dict[str, str]]) -> dict[str, Any]:
    """Return an existing current seal, or reject it as an immutable conflict."""

    try:
        if not stat.S_ISREG(SEAL_PATH.lstat().st_mode):
            raise TypeError("seal path is not a regular file")
        seal = _load_json(SEAL_PATH)
        if not isinstance(seal, dict):
            raise TypeError("seal root must be an object")
        Draft202012Validator(_load_schema("protocol-seal.schema.json")).validate(seal)
    except Exception as error:
        raise FileExistsError(f"existing MVX protocol seal is invalid: {error}") from error
    expected = {
        "seal_version": "1.0.0",
        "protocol_id": "MORPHOIA-MVX-FEASIBILITY-V1",
        "protocol_version": PROTOCOL_VERSION,
        "hash_algorithm": "SHA-256",
        "canonicalisation": "deterministic JSON; RFC 8785-equivalent string/integer domain",
        "predecessor_protocol_root_sha256": PREDECESSOR_PROTOCOL_ROOT,
        "predecessor_seal_sha256": PREDECESSOR_SEAL_SHA256,
        "supersession_record_sha256": SUPERSESSION_RECORD_SHA256,
        "files": files,
        "protocol_root_sha256": _root_from_files(files),
    }
    if any(seal.get(field) != value for field, value in expected.items()):
        raise FileExistsError("existing MVX protocol seal conflicts with current normative files")
    if not _valid_utc_timestamp(seal.get("sealed_at")):
        raise FileExistsError("existing MVX protocol seal has an invalid sealed_at timestamp")
    return seal


def create_seal() -> dict[str, Any]:
    """Create or reuse one immutable protocol seal with a durable seal time."""

    missing = [relative for relative in NORMATIVE_PATHS if not (PROJECT_ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"normative files missing: {missing}")
    semantic = _semantic_checks()
    failures = [check for check in semantic if not check.passed]
    if failures:
        summary = "; ".join(f"{item.identifier}: {item.evidence}" for item in failures)
        raise ValueError(f"protocol cannot be sealed: {summary}")
    files = _file_manifest()
    if SEAL_PATH.exists() or SEAL_PATH.is_symlink():
        return _existing_current_seal(files)
    seal = {
        "seal_version": "1.0.0",
        "protocol_id": "MORPHOIA-MVX-FEASIBILITY-V1",
        "protocol_version": PROTOCOL_VERSION,
        "hash_algorithm": "SHA-256",
        "canonicalisation": "deterministic JSON; RFC 8785-equivalent string/integer domain",
        "predecessor_protocol_root_sha256": PREDECESSOR_PROTOCOL_ROOT,
        "predecessor_seal_sha256": PREDECESSOR_SEAL_SHA256,
        "supersession_record_sha256": SUPERSESSION_RECORD_SHA256,
        "sealed_at": _utc_timestamp(),
        "files": files,
        "protocol_root_sha256": _root_from_files(files),
    }
    Draft202012Validator(_load_schema("protocol-seal.schema.json")).validate(seal)
    try:
        _publish_write_once_json(SEAL_PATH, seal, artifact="MVX protocol seal")
    except FileExistsError:
        # A concurrent sealer may have won with a different second-level
        # timestamp.  Reuse it only if every normative field is identical.
        return _existing_current_seal(files)
    return seal


def verify_protocol(*, require_seal: bool = True) -> ProtocolVerification:
    checks: list[ProtocolCheck] = []
    missing = [relative for relative in NORMATIVE_PATHS if not (PROJECT_ROOT / relative).is_file()]
    checks.append(
        ProtocolCheck(
            "NORMATIVE_FILES_PRESENT",
            not missing,
            "all normative files present" if not missing else f"missing={missing}",
        )
    )
    if missing:
        return ProtocolVerification(tuple(checks), None)
    checks.extend(_semantic_checks())

    root: str | None = None
    if SEAL_PATH.exists():
        current_files = _file_manifest()
        root = _root_from_files(current_files)
        try:
            if not stat.S_ISREG(SEAL_PATH.lstat().st_mode):
                raise TypeError("seal path is not a regular file")
            seal = _load_json(SEAL_PATH)
            if not isinstance(seal, dict):
                raise TypeError("seal.json root must be an object")
            try:
                Draft202012Validator(_load_schema("protocol-seal.schema.json")).validate(seal)
                schema_valid = True
                schema_evidence = "seal validates against protocol-seal.schema.json"
            except Exception as error:  # noqa: BLE001 - preserve schema diagnostic
                schema_valid = False
                schema_evidence = str(error)
            checks.append(ProtocolCheck("SEAL_SCHEMA_VALID", schema_valid, schema_evidence))
            checks.append(
                ProtocolCheck(
                    "SEAL_VERSION",
                    seal.get("seal_version") == "1.0.0",
                    f"seal_version={seal.get('seal_version')!r}",
                )
            )
            checks.append(
                ProtocolCheck(
                    "SEAL_TIME",
                    _valid_utc_timestamp(seal.get("sealed_at")),
                    f"sealed_at={seal.get('sealed_at')!r}",
                )
            )
            checks.append(
                ProtocolCheck(
                    "SEAL_PREDECESSOR_CHAIN",
                    seal.get("predecessor_protocol_root_sha256") == PREDECESSOR_PROTOCOL_ROOT
                    and seal.get("predecessor_seal_sha256") == PREDECESSOR_SEAL_SHA256
                    and seal.get("supersession_record_sha256") == SUPERSESSION_RECORD_SHA256,
                    "predecessor root, seal and supersession record are cryptographically linked",
                )
            )
            checks.append(
                ProtocolCheck(
                    "SEAL_PROTOCOL_ID_VERSION",
                    seal.get("protocol_id") == "MORPHOIA-MVX-FEASIBILITY-V1"
                    and seal.get("protocol_version") == PROTOCOL_VERSION,
                    f"protocol_id={seal.get('protocol_id')!r}, "
                    f"protocol_version={seal.get('protocol_version')!r}",
                )
            )
            checks.append(
                ProtocolCheck(
                    "SEAL_FILE_LIST",
                    seal.get("files") == current_files,
                    "seal file list and individual SHA-256 values match",
                )
            )
            checks.append(
                ProtocolCheck(
                    "SEAL_ROOT",
                    seal.get("protocol_root_sha256") == root,
                    f"protocol_root_sha256={root}",
                )
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            checks.append(ProtocolCheck("SEAL_PARSE", False, str(error)))
    elif require_seal:
        checks.append(ProtocolCheck("SEAL_PRESENT", False, "seal.json is missing"))

    return ProtocolVerification(tuple(checks), root)


def write_g0_verdict(verification: ProtocolVerification) -> dict[str, Any]:
    """Write an honest, schema-valid G0 verdict from verification evidence."""

    if verification.root_sha256 is None:
        raise ValueError("cannot write G0 verdict without a protocol root")

    def g0_group(identifier: str) -> str:
        if identifier in {
            "NORMATIVE_FILES_PRESENT",
            "AUTHORITATIVE_PDF_HASHES",
            "JSON_SCHEMAS_VALID",
            "SCHEMA_EXAMPLES_VALID",
        }:
            return "G0_NORMATIVE_FILES_VALID"
        if identifier.startswith("SEAL_"):
            return "G0_PROTOCOL_SEAL_VERIFIES"
        if identifier in {
            "PROTOCOL_ID_VERSION",
            "PROTOCOL_FROZEN",
            "AUXILIARY_DOCUMENT_VERSIONS",
            "AUTHORITY_DOMAINS_SPLIT",
            "GATES_COMPLETE",
            "GATE_CRITERIA_CATALOG_CLOSED",
            "RELEASE_DECISION_ORDER_EXCLUSIVE",
        }:
            return "G0_PROTOCOL_COMPONENTS_FROZEN"
        if "CUSTODY" in identifier or identifier == "PRODUCTION_SPLIT_SALT_COMMITTED_ONLY":
            return "G0_CUSTODY_DRY_RUN"
        return "G0_SEMANTIC_CLOSURE"

    grouped: dict[str, list[ProtocolCheck]] = {
        identifier: [] for identifier in EXPECTED_GATE_CRITERIA["G0"]
    }
    for check in verification.checks:
        grouped[g0_group(check.identifier)].append(check)

    criteria: list[dict[str, Any]] = []
    for identifier in EXPECTED_GATE_CRITERIA["G0"]:
        checks = grouped[identifier]
        failed = [check for check in checks if not check.passed]
        passed = bool(checks) and not failed
        evidence = (
            f"{len(checks)} executable checks passed: "
            + ", ".join(check.identifier for check in checks)
            if passed
            else (
                "no executable check supplied for this gate criterion"
                if not checks
                else "; ".join(f"{check.identifier}: {check.evidence}" for check in failed)
            )
        )
        criteria.append({"id": identifier, "passed": passed, "evidence": evidence})

    blockers = [
        f"{criterion['id']}: {criterion['evidence']}"
        for criterion in criteria
        if not criterion["passed"]
    ]
    verdict = "PASS" if not blockers else "FAIL"
    payload = {
        "schema_version": "0.1.0",
        "gate": "G0",
        "verdict": verdict,
        "protocol_root_sha256": verification.root_sha256,
        "criteria": criteria,
        "blockers": blockers,
        "deviations": [
            (
                "Blind custody is process-locked access control with a schema-validated synthetic "
                "dry run; it is not human double blinding. Production private storage and the "
                "production split salt are not claimed as provisioned at G0 and are required "
                "before G1."
            ),
            (
                "Independent technical, anatomy and statistical reviewers plus the clean-room "
                "implementation owner are future gate roles. They are not claimed as provisioned "
                "at G0 and block the later gates stated in roles.yaml when absent."
            ),
        ],
        "evidence_hashes": {"seal.json": sha256_file(SEAL_PATH)},
    }
    if payload["verdict"] == "PASS" and (
        payload["blockers"] or any(not criterion["passed"] for criterion in payload["criteria"])
    ):
        raise AssertionError("a G0 PASS cannot contain blockers or failed criteria")
    Draft202012Validator(_load_schema("gate-verdict.schema.json")).validate(payload)
    _publish_write_once_json(G0_PATH, payload, artifact="G0 verdict")
    return payload
