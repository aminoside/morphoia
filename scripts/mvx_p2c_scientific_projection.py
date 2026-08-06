#!/usr/bin/env python3
"""Validate and privately project P2c v1/v2 scientific results.

Projection is deliberately fail-closed.  A slot name alone is never enough:
the result, execution plan, terminal checkpoint and local authority claim must
all validate against a frozen private continuity manifest.  Per-slot output can
fingerprint a private mesh, so it is published once below ``tmp/`` with mode
0600 and is never written to standard output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = PROJECT_ROOT / "tmp"
RUNNER_PATH = PROJECT_ROOT / "scripts" / "mvx_p2c_exact_intersections.py"
DEFAULT_PREREGISTRATION = (
    PROJECT_ROOT
    / "docs/mvx/validation/p2c/preregistration/pilot3-2026-08-06-v2/preregistration.json"
)
DEFAULT_CONTEXTS = DEFAULT_PREREGISTRATION.with_name("projection-contexts.json")

PROJECTION_SCHEMA = "morphoia.mvx.p2c.scientific-projection"
PROJECTION_SCHEMA_VERSION = "1.0.0"
COMPARISON_SCHEMA = "morphoia.mvx.p2c.scientific-projection-comparison"
COMPARISON_SCHEMA_VERSION = "1.0.0"
CONTINUITY_SCHEMA = "MVX-P2C-PRIVATE-CAMPAIGN-CONTINUITY"
CONTINUITY_SCHEMA_VERSION = "1.0.0"
CAMPAIGN_ID = "P2C-PILOT3-2026-08-06"
V1_ROOT = "f45509de33b10e7a877d264c6b99079f7fffe56b9ce30795f5916e1971222722"
V1_RUNNER_SHA256 = "adb7fe9aef50f4473a5220788004ecebaec9bfd5d81be478b14132f774534f02"
NUMERIC_MODEL = "IEEE754_BINARY64_EXACT_RATIONAL_LIFT"
AUTHORITY_TRUST_MODEL = "LOCAL_SINGLE_WRITER_IMMUTABLE_CLAIM_DIRECTORY"
MAX_JSON_BYTES = 16 * 1024 * 1024

# Updated only when the pre-execution public documents are deliberately
# versioned.  This closes validation over every nested clause, including ones
# that do not otherwise influence projection arithmetic.
FROZEN_PREREGISTRATION_VALUE_SHA256 = (
    "0acc341eb42caa429e95fd451cd3332998d19abfc4d2e984b049f6e9979db02f"
)
FROZEN_CONTEXT_SET_VALUE_SHA256 = "76e88343dda0d70b5d267c276c84c06d91033f6ee678d8643ff9985f2b93311a"

SCIENTIFIC_FIELDS = (
    "numeric_model",
    "limits",
    "mesh",
    "broadphase",
    "contact",
    "diagnostic",
    "error_code",
    "status",
)
RESULT_FIELDS = {
    "algorithm_id",
    "algorithm_version",
    "authorization",
    "broadphase",
    "contact",
    "diagnostic",
    "error_code",
    "input_binding",
    "limits",
    "mesh",
    "numeric_model",
    "plan_sha256",
    "schema",
    "schema_version",
    "source_sha256",
    "source_size_bytes",
    "status",
    "work_id",
}
PLAN_FIELDS = {
    "algorithm_id",
    "algorithm_version",
    "authority_policy",
    "code_sha256",
    "environment",
    "external_anchor_public_key_hex",
    "input_binding",
    "limits",
    "max_input_bytes",
    "schema",
    "schema_version",
    "source_sha256",
    "source_size_bytes",
    "work_id",
}
P2A_BINDING_FIELDS = {
    "audit_record_sha256",
    "execution_plan_file_sha256",
    "execution_plan_sha256",
    "materializer_code_sha256",
    "materializer_id",
    "materializer_version",
    "mesh_sha256",
    "mode",
    "p2a_terminal_checkpoint_sha256",
    "p2a_work_id",
}
TERMINAL_FIELDS = {
    "attempt",
    "claim_sha256",
    "plan_sha256",
    "previous_checkpoint_sha256",
    "result_filename",
    "result_sha256",
    "state",
    "work_id",
}
CLAIM_FIELDS = {
    "attempt",
    "plan_sha256",
    "previous_claim_sha256",
    "public_key_hex",
    "schema",
    "schema_version",
    "trust_model",
    "work_id",
}
AUTHORIZATION_FIELDS = {
    "attempt",
    "claim_sha256",
    "signature_algorithm",
    "signature_hex",
    "trust_model",
}
LIMIT_FIELDS = {
    "max_candidate_pairs",
    "max_coordinate_bits",
    "max_runtime_seconds",
    "max_triangles",
    "max_vertices",
}
BROADPHASE_FIELDS = {
    "active_pair_comparisons",
    "allowed_topological_adjacencies",
    "bbox_candidate_pairs",
    "exact_pairs_examined",
}
MESH_FIELDS = {"triangle_count", "vertex_count"}
CONTACT_FIELDS = {
    "dimension",
    "kind",
    "points",
    "shared_topological_vertices",
    "triangle_pair",
}
STATUS_VALUES = {
    "EXACT_INTERSECTION_FREE_CANDIDATE",
    "EXACT_CONTACT_FOUND",
    "RESOURCE_LIMIT",
    "ERROR",
}
RESOURCE_CODES = {
    "CHILD_CPU_LIMIT",
    "CHILD_TIMEOUT",
    "MAX_CANDIDATE_PAIRS",
    "MAX_COORDINATE_BITS",
    "MAX_INPUT_BYTES",
    "MAX_TRIANGLES",
    "MAX_VERTICES",
}
ERROR_CODES = {
    "CHILD_RETRY_EXHAUSTED",
    "EXACT_ARITHMETIC_ERROR",
    "INVALID_JSON",
    "INVALID_MESH",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA512_HEX = re.compile(r"^[0-9a-f]{128}$")
RESULT_FILENAME = re.compile(r"^attempt-[0-9]{4}-[0-9a-f]{16}\.json$")


class ProjectionError(ValueError):
    """Raised when projection evidence is ambiguous, unsafe or inconsistent."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectionError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ProjectionError("non-finite JSON numeric constant")


def _decode_json(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProjectionError("invalid UTF-8 JSON input") from error
    if not isinstance(value, dict):
        raise ProjectionError("JSON input must be an object")
    return value


def load_json(path: Path) -> dict[str, Any]:
    """Load a public JSON document without exposing private path semantics."""

    try:
        return _decode_json(path.read_bytes())
    except OSError as error:
        raise ProjectionError("cannot read public JSON input") from error


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ProjectionError("value is outside the canonical JSON domain") from error


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _private_absolute(path: Path, *, must_exist: bool) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        resolved = absolute.resolve(strict=must_exist)
        private = PRIVATE_ROOT.resolve(strict=True)
    except OSError as error:
        raise ProjectionError("private path is unavailable") from error
    if resolved != absolute or (resolved != private and private not in resolved.parents):
        raise ProjectionError("private path must be a non-symlink path below tmp")
    return resolved


def _read_private_json(
    path: Path, *, allowed_modes: set[int] | None = None
) -> tuple[bytes, dict[str, Any]]:
    selected_modes = {0o400, 0o600} if allowed_modes is None else allowed_modes
    candidate = _private_absolute(path, must_exist=True)
    try:
        before = candidate.lstat()
        descriptor = os.open(
            candidate,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise ProjectionError("cannot read private JSON evidence") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or before.st_uid != os.getuid()
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) not in selected_modes
            or stat.S_IMODE(opened.st_mode) not in selected_modes
            or before.st_size > MAX_JSON_BYTES
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        ):
            raise ProjectionError("private JSON evidence has unsafe identity or mode")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_JSON_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_JSON_BYTES:
                raise ProjectionError("private JSON evidence exceeds its size limit")
        after = os.fstat(descriptor)
    except OSError as error:
        raise ProjectionError("cannot read private JSON evidence") from error
    finally:
        os.close(descriptor)
    if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or total != after.st_size:
        raise ProjectionError("private JSON evidence has unsafe identity or mode")
    payload = b"".join(chunks)
    value = _decode_json(payload)
    if payload != canonical_bytes(value):
        raise ProjectionError("private JSON evidence is not canonical")
    return payload, value


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private_once(value: Mapping[str, Any], output: Path) -> None:
    destination = _private_absolute(output, must_exist=False)
    if destination.exists() or destination.is_symlink():
        raise ProjectionError("private output already exists")
    try:
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        parent = _private_absolute(destination.parent, must_exist=True)
        metadata = parent.stat()
    except OSError as error:
        raise ProjectionError("private output parent is unavailable") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ProjectionError("private output parent permissions are unsafe")
    payload = canonical_bytes(value)
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".mvx-p2c-projection-",
            dir=parent,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_name, destination)
        _fsync_directory(parent)
    except FileExistsError as error:
        raise ProjectionError("private output already exists") from error
    except OSError as error:
        raise ProjectionError("private output publication failed") from error
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    if stat.S_IMODE(destination.stat().st_mode) != 0o600:
        raise ProjectionError("private output mode differs from 0600")


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ProjectionError(f"{label} fields are not the frozen exact set")


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProjectionError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProjectionError(f"{label} must be a non-negative integer")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ProjectionError(f"{label} is not a lowercase SHA-256")
    return value


def _expected_slots() -> list[dict[str, Any]]:
    return [
        {
            "slot_id": "P2C-V2-01",
            "comparison_slot": "PARENT_A_DEFAULT",
            "private_parent_alias": "PARENT_A",
            "profile_id": "DEFAULT_2M",
            "max_candidate_pairs": 2_000_000,
        },
        {
            "slot_id": "P2C-V2-02",
            "comparison_slot": "PARENT_B_DEFAULT",
            "private_parent_alias": "PARENT_B",
            "profile_id": "DEFAULT_2M",
            "max_candidate_pairs": 2_000_000,
        },
        {
            "slot_id": "P2C-V2-03",
            "comparison_slot": "PARENT_C_DEFAULT",
            "private_parent_alias": "PARENT_C",
            "profile_id": "DEFAULT_2M",
            "max_candidate_pairs": 2_000_000,
        },
        {
            "slot_id": "P2C-V2-04",
            "comparison_slot": "PARENT_B_EXPANDED",
            "private_parent_alias": "PARENT_B",
            "profile_id": "EXPANDED_10M",
            "max_candidate_pairs": 10_000_000,
            "parent_rule": (
                "SAME_PRIVATE_PARENT_AS_THE_V1_DEFAULT_EXECUTION_THAT_REACHED_MAX_CANDIDATE_PAIRS"
            ),
        },
    ]


def validate_preregistration(value: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(value)
    _require_exact_keys(
        document,
        {
            "schema",
            "schema_version",
            "campaign",
            "version_domains",
            "historical_v1",
            "protocol",
            "private_parent_scope",
            "limits_common",
            "execution_slots",
            "materialization_contract",
            "preexecution_freeze",
            "authority",
            "work_identity",
            "scientific_projection",
            "clean_restore",
            "outcome_boundary",
            "publication",
        },
        "preregistration",
    )
    if (
        document.get("schema") != "morphoia.mvx.p2c.campaign-preregistration"
        or document.get("schema_version") != "1.0.0"
    ):
        raise ProjectionError("preregistration schema identity is invalid")
    campaign = document["campaign"]
    if campaign != {
        "campaign_id": CAMPAIGN_ID,
        "campaign_version": "2.0.0",
        "status": "FROZEN_BEFORE_EXECUTION",
        "predecessor_campaign_version": "v1",
        "predecessor_disposition": "UNANCHORED_DIAGNOSTIC",
        "relationship_to_p0": "POST_P0_NON_NORMATIVE_DIAGNOSTIC",
    }:
        raise ProjectionError("campaign identity or status is invalid")
    versions = document["version_domains"]
    expected_v2 = {
        "campaign_version": "2.0.0",
        "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
        "algorithm_version": "0.3.0",
        "result_schema": "MVX-P2C-EXACT-TRIANGLE-CONTACT",
        "result_schema_version": "0.3.0",
        "materializer_id": "mvx-p2c-p2a-canonical-scene-materializer",
        "materializer_version": "0.2.0",
        "drive_checkpoint_schema": "MORPHOIA-MVX-DRIVE-CHECKPOINT",
        "drive_checkpoint_schema_version": "2.3.0",
        "independence_rule": (
            "CAMPAIGN_ALGORITHM_RESULT_SCHEMA_MATERIALIZER_AND_DRIVE_CHECKPOINT_"
            "VERSIONS_ARE_DISTINCT_IDENTIFIERS"
        ),
    }
    if versions != expected_v2:
        raise ProjectionError("v2 version domains are not the frozen exact set")
    expected_v1 = {
        "campaign_version": "v1",
        "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
        "algorithm_version": "0.2.0",
        "result_schema": "MVX-P2C-EXACT-TRIANGLE-CONTACT",
        "result_schema_version": "0.2.0",
        "materializer_id": "mvx-p2c-p2a-canonical-scene-materializer",
        "materializer_version": "0.1.0",
        "runner_sha256": V1_RUNNER_SHA256,
        "vertex_index_policy": "COORDINATE_EQUAL_VERTEX_INSTANCES_WELDED",
    }
    if document["historical_v1"] != expected_v1:
        raise ProjectionError("historical v1 identity is not the frozen exact set")
    if document["protocol"] != {
        "id": "MORPHOIA-MVX-FEASIBILITY-V1",
        "version": "1.0.2-p0",
        "root_sha256": "a600436d8a51ee3c26a6070ead19829cc3568a257493a5c639c35e5a35b8a9e7",
        "gate_credit": "NONE",
        "solid_status_V_allowed": False,
    }:
        raise ProjectionError("protocol boundary is invalid")
    scope = document["private_parent_scope"]
    if (
        not isinstance(scope, dict)
        or scope.get("unique_p2a_parent_count") != 3
        or scope.get("execution_count") != 4
        or scope.get("same_parent_multiset_as_v1_required") is not True
        or scope.get("private_continuity_manifest_required_before_execution") is not True
        or scope.get("private_continuity_manifest_schema") != CONTINUITY_SCHEMA
        or scope.get("private_continuity_manifest_schema_version") != CONTINUITY_SCHEMA_VERSION
        or scope.get("v1_terminal_evidence_root_algorithm")
        != "SHA256_CANONICAL_SORTED_PLAN_RESULT_TERMINAL_ROWS_V1"
        or scope.get("v1_terminal_evidence_root_sha256") != V1_ROOT
        or scope.get("identity_publication") != "FORBIDDEN"
        or any(
            scope.get(name) != 0
            for name in (
                "public_source_identity_count",
                "public_source_hash_count",
                "public_p2a_work_id_count",
            )
        )
    ):
        raise ProjectionError("private parent continuity or privacy boundary is invalid")
    required_manifest_bindings = {
        "v1_execution_plan_sha256",
        "v1_source_sha256",
        "v1_p2a_execution_plan_sha256",
        "v1_p2a_terminal_checkpoint_sha256",
        "v1_p2a_work_id",
        "v1_work_id",
        "v2_parent_alias",
        "v2_execution_slot",
        "v2_execution_plan_sha256",
        "v2_source_sha256",
        "v2_p2a_execution_plan_sha256",
        "v2_p2a_terminal_checkpoint_sha256",
        "v2_p2a_work_id",
        "v2_work_id",
        "persistent_signer_public_key_ed25519_hex",
        "preregistration_value_sha256",
    }
    if set(scope.get("private_continuity_manifest_must_bind", [])) != required_manifest_bindings:
        raise ProjectionError("private continuity manifest bindings are incomplete")
    if document["limits_common"] != {
        "max_input_bytes": 536_870_912,
        "max_vertices": 2_000_000,
        "max_triangles": 1_000_000,
        "max_coordinate_bits": 2_048,
        "max_runtime_seconds": 120,
    }:
        raise ProjectionError("common limits differ from the frozen profile")
    if document["execution_slots"] != _expected_slots():
        raise ProjectionError("execution slots differ from the frozen ordered set")
    materialization = document["materialization_contract"]
    if (
        not isinstance(materialization, dict)
        or materialization.get("vertex_index_policy")
        != "PRESERVE_P2A_VERTEX_INSTANCE_INDICES_EXACTLY"
        or materialization.get("triangle_index_policy")
        != "PRESERVE_P2A_TRIANGLE_INDICES_AND_ORDER_EXACTLY"
        or any(
            materialization.get(name) != "FORBIDDEN"
            for name in (
                "coordinate_equal_vertex_merge",
                "vertex_reorder",
                "triangle_reorder",
                "index_remap",
                "repair",
            )
        )
    ):
        raise ProjectionError("materialization does not preserve P2a indices")
    freeze = document["preexecution_freeze"]
    if (
        not isinstance(freeze, dict)
        or freeze.get("required") is not True
        or freeze.get("must_precede_first_child_execution") is not True
        or freeze.get("public_github_commit_required_before_plan_creation") is not True
        or freeze.get("private_drive_copy_is_not_publication") is not True
        or freeze.get("change_after_freeze") != "REQUIRES_NEW_CAMPAIGN_VERSION_AND_NEW_WORK_IDS"
        or set(freeze.get("required_bindings", []))
        != {
            "git_commit_sha1",
            "git_tree_sha1",
            "runner_sha256",
            "tests_sha256",
            "runtime_sha256",
            "persistent_signer_public_key_ed25519_hex",
            "private_continuity_manifest_sha256",
            "campaign_preregistration_sha256",
        }
    ):
        raise ProjectionError("pre-execution freeze contract is open or incomplete")
    authority = document["authority"]
    if (
        not isinstance(authority, dict)
        or authority.get("model") != "OWNER_CONTROLLED_PERSISTENT_SIGNER"
        or authority.get("persistence") != "REQUIRED_BEFORE_PLAN_CREATION_AND_THROUGH_CLEAN_RESTORE"
        or authority.get("owner_controlled") is not True
        or authority.get("public_key_bound_into_each_work_id") is not True
        or authority.get("private_key_in_repository") is not False
        or authority.get("private_key_in_result_bundle") is not False
        or any(
            authority.get(name) is not False
            for name in (
                "independent_scientific_witness",
                "worm_store",
                "encryption_key",
                "g1_custodian",
                "solid_verifier",
            )
        )
    ):
        raise ProjectionError("authority claim exceeds owner-controlled continuity")
    identity = document["work_identity"]
    if (
        not isinstance(identity, dict)
        or identity.get("all_v2_work_ids_must_differ_from_v1") is not True
        or identity.get("v1_result_or_checkpoint_reuse") != "FORBIDDEN"
        or set(identity.get("direct_plan_fields_hashed_into_work_id", []))
        != PLAN_FIELDS - {"work_id"}
    ):
        raise ProjectionError("work identity or v1 reuse boundary is invalid")
    projection = document["scientific_projection"]
    if (
        not isinstance(projection, dict)
        or projection.get("projection_visibility") != "PRIVATE_PER_SLOT"
        or projection.get("comparison_unit") != "comparison_slot"
        or projection.get("scientific_payload_fields") != list(SCIENTIFIC_FIELDS)
        or projection.get("public_output")
        != "AGGREGATE_COUNTS_CHANGE_CLASSES_AND_PROJECTION_COMMITMENT_ONLY"
        or projection.get("v2_repeatability_rule")
        != "SCIENTIFIC_PAYLOAD_MUST_BE_BYTE_IDENTICAL_AFTER_CANONICAL_JSON_PROJECTION"
    ):
        raise ProjectionError("scientific projection privacy or determinism boundary is invalid")
    restore = document["clean_restore"]
    if (
        not isinstance(restore, dict)
        or restore.get("required_before_campaign_completion") is not True
        or restore.get("new_workspace_required") is not True
        or restore.get("original_run_directory_access") != "FORBIDDEN"
        or restore.get("original_signer_private_key_access_during_reuse") != "FORBIDDEN"
        or restore.get("required_terminal_action") != "SKIP_ANCHORED"
        or restore.get("geometry_recomputation_count") != 0
        or restore.get("failure_effect")
        != "CAMPAIGN_REMAINS_INCOMPLETE_AND_RESULTS_ARE_NOT_REUSABLE"
    ):
        raise ProjectionError("clean-restore contract is not closed")
    outcome = document["outcome_boundary"]
    publication = document["publication"]
    if (
        not isinstance(outcome, dict)
        or outcome.get("expected_status_counts") is not None
        or outcome.get("expected_contact_count") is not None
        or outcome.get("expected_free_candidate_count") is not None
        or outcome.get("solid_certification_count") != 0
        or outcome.get("solid_status_V_emitted_count") != 0
        or outcome.get("gate_credit") != "NONE"
        or outcome.get("independent_solid_verifier_required_after_p2c") is not True
        or not isinstance(publication, dict)
        or publication.get("preregistration_is_public") is not True
        or publication.get("private_parent_mapping_is_public") is not False
        or publication.get("per_slot_scientific_projection_is_public") is not False
        or publication.get("result_publication_requires_completed_execution") is not True
        or publication.get("no_result_is_claimed_by_this_document") is not True
    ):
        raise ProjectionError("outcome or publication boundary is invalid")
    if sha256_value(document) != FROZEN_PREREGISTRATION_VALUE_SHA256:
        raise ProjectionError("preregistration differs from the fully frozen document")
    return document


def validate_contexts(
    value: Mapping[str, Any], preregistration: Mapping[str, Any]
) -> dict[str, Any]:
    document = dict(value)
    _require_exact_keys(
        document,
        {
            "schema",
            "schema_version",
            "campaign_id",
            "campaign_version",
            "algorithm_id",
            "algorithm_version",
            "result_schema",
            "result_schema_version",
            "materializer_id",
            "materializer_version",
            "vertex_index_policy",
            "historical_v1",
            "contexts",
            "privacy",
        },
        "projection context set",
    )
    versions = preregistration["version_domains"]
    expected_v2 = {
        "campaign_id": CAMPAIGN_ID,
        "campaign_version": versions["campaign_version"],
        "algorithm_id": versions["algorithm_id"],
        "algorithm_version": versions["algorithm_version"],
        "result_schema": versions["result_schema"],
        "result_schema_version": versions["result_schema_version"],
        "materializer_id": versions["materializer_id"],
        "materializer_version": versions["materializer_version"],
        "vertex_index_policy": preregistration["materialization_contract"]["vertex_index_policy"],
    }
    if (
        document.get("schema") != "morphoia.mvx.p2c.scientific-projection-context-set"
        or document.get("schema_version") != "1.0.0"
        or any(document.get(name) != expected for name, expected in expected_v2.items())
        or document.get("historical_v1")
        != {
            name: value
            for name, value in preregistration["historical_v1"].items()
            if name != "runner_sha256"
        }
    ):
        raise ProjectionError("projection context identities differ from preregistration")
    expected_contexts = [
        {
            "slot_id": slot["slot_id"],
            "comparison_slot": slot["comparison_slot"],
            "profile_id": slot["profile_id"],
        }
        for slot in preregistration["execution_slots"]
    ]
    if document.get("contexts") != expected_contexts or document.get("privacy") != {
        "aliases_are_source_identifiers": False,
        "contains_source_hashes": False,
        "contains_p2a_work_ids": False,
        "generated_projection_visibility": "PRIVATE",
    }:
        raise ProjectionError("projection contexts or privacy boundary are invalid")
    if sha256_value(document) != FROZEN_CONTEXT_SET_VALUE_SHA256:
        raise ProjectionError("projection context set differs from the fully frozen document")
    return document


def _campaign_implementation(
    preregistration: Mapping[str, Any], campaign_key: str
) -> dict[str, Any]:
    if campaign_key == "v2":
        versions = preregistration["version_domains"]
        return {
            "campaign_version": versions["campaign_version"],
            "algorithm_id": versions["algorithm_id"],
            "algorithm_version": versions["algorithm_version"],
            "result_schema": versions["result_schema"],
            "result_schema_version": versions["result_schema_version"],
            "materializer_id": versions["materializer_id"],
            "materializer_version": versions["materializer_version"],
            "vertex_index_policy": preregistration["materialization_contract"][
                "vertex_index_policy"
            ],
        }
    if campaign_key == "v1":
        return {
            name: value
            for name, value in preregistration["historical_v1"].items()
            if name != "runner_sha256"
        }
    raise ProjectionError("unknown projection campaign")


def validate_continuity_manifest(
    value: Mapping[str, Any], preregistration: Mapping[str, Any]
) -> dict[str, Any]:
    document = dict(value)
    _require_exact_keys(
        document,
        {
            "schema",
            "schema_version",
            "campaign_id",
            "status",
            "persistent_signer_public_key_ed25519_hex",
            "preregistration_value_sha256",
            "v1_terminal_evidence_root_sha256",
            "slots",
        },
        "private continuity manifest",
    )
    if (
        document.get("schema") != CONTINUITY_SCHEMA
        or document.get("schema_version") != CONTINUITY_SCHEMA_VERSION
        or document.get("campaign_id") != CAMPAIGN_ID
        or document.get("status") != "FROZEN_BEFORE_FIRST_V2_CHILD"
        or not isinstance(document.get("persistent_signer_public_key_ed25519_hex"), str)
        or SHA256.fullmatch(document["persistent_signer_public_key_ed25519_hex"]) is None
        or document.get("preregistration_value_sha256") != sha256_value(preregistration)
        or document.get("v1_terminal_evidence_root_sha256") != V1_ROOT
    ):
        raise ProjectionError("private continuity manifest identity is invalid")
    slots = document.get("slots")
    if not isinstance(slots, list) or len(slots) != 4:
        raise ProjectionError("private continuity manifest must contain four slots")
    expected_slots = _expected_slots()
    binding_fields = {
        "execution_plan_sha256",
        "source_sha256",
        "p2a_execution_plan_sha256",
        "p2a_terminal_checkpoint_sha256",
        "p2a_work_id",
        "work_id",
    }
    for row, expected in zip(slots, expected_slots, strict=True):
        if not isinstance(row, dict):
            raise ProjectionError("private continuity slot must be an object")
        _require_exact_keys(
            row,
            {
                "slot_id",
                "comparison_slot",
                "private_parent_alias",
                "profile_id",
                "max_candidate_pairs",
                "v1",
                "v2",
            },
            "private continuity slot",
        )
        expected_public = {name: expected[name] for name in row if name not in {"v1", "v2"}}
        if any(row[name] != expected_public[name] for name in expected_public):
            raise ProjectionError("private continuity slot differs from preregistration")
        for campaign_key in ("v1", "v2"):
            binding = row[campaign_key]
            if not isinstance(binding, dict):
                raise ProjectionError("private continuity campaign binding must be an object")
            _require_exact_keys(binding, binding_fields, "private continuity campaign binding")
            for name in binding_fields:
                _require_sha256(binding[name], f"continuity {campaign_key}.{name}")
        for name in binding_fields - {"execution_plan_sha256", "work_id"}:
            if row["v1"][name] != row["v2"][name]:
                raise ProjectionError("v1 and v2 do not bind the same sealed P2a parent")
        if row["v1"]["work_id"] == row["v2"]["work_id"]:
            raise ProjectionError("v2 work ID silently reuses v1")
    for campaign_key in ("v1", "v2"):
        work_ids = [row[campaign_key]["work_id"] for row in slots]
        if len(set(work_ids)) != 4:
            raise ProjectionError("campaign work IDs are not unique")
    if {row["v1"]["work_id"] for row in slots} & {row["v2"]["work_id"] for row in slots}:
        raise ProjectionError("v2 work ID set overlaps historical v1")
    if {row["v1"]["execution_plan_sha256"] for row in slots} & {
        row["v2"]["execution_plan_sha256"] for row in slots
    }:
        raise ProjectionError("v2 execution-plan set overlaps historical v1")
    by_alias: dict[str, tuple[str, str, str, str]] = {}
    for row in slots:
        parent = row["v2"]
        identity = (
            parent["source_sha256"],
            parent["p2a_execution_plan_sha256"],
            parent["p2a_terminal_checkpoint_sha256"],
            parent["p2a_work_id"],
        )
        alias = row["private_parent_alias"]
        if alias in by_alias and by_alias[alias] != identity:
            raise ProjectionError("one private parent alias maps to multiple parents")
        by_alias[alias] = identity
    if len(set(by_alias.values())) != 3:
        raise ProjectionError("private aliases do not identify exactly three parents")
    return document


def _expected_limits(preregistration: Mapping[str, Any], slot: Mapping[str, Any]) -> dict[str, int]:
    common = preregistration["limits_common"]
    return {
        "max_candidate_pairs": slot["max_candidate_pairs"],
        "max_coordinate_bits": common["max_coordinate_bits"],
        "max_runtime_seconds": common["max_runtime_seconds"],
        "max_triangles": common["max_triangles"],
        "max_vertices": common["max_vertices"],
    }


def _validate_plan(
    plan: Mapping[str, Any],
    implementation: Mapping[str, Any],
    manifest_binding: Mapping[str, Any],
    expected_limits: Mapping[str, int],
    preregistration: Mapping[str, Any],
    campaign_key: str,
    persistent_signer_public_key: str,
) -> dict[str, Any]:
    document = dict(plan)
    _require_exact_keys(document, PLAN_FIELDS, "execution plan")
    base = {name: value for name, value in document.items() if name != "work_id"}
    plan_sha256 = sha256_value(document)
    if (
        document.get("schema") != "MVX-P2C-EXECUTION-PLAN"
        or document.get("schema_version") != "0.1.0"
        or document.get("algorithm_id") != implementation["algorithm_id"]
        or document.get("algorithm_version") != implementation["algorithm_version"]
        or document.get("authority_policy") != "REQUIRE_EXTERNAL_ANCHOR"
        or not isinstance(document.get("external_anchor_public_key_hex"), str)
        or SHA256.fullmatch(document["external_anchor_public_key_hex"]) is None
        or document.get("work_id") != sha256_value(base)
        or plan_sha256 != manifest_binding["execution_plan_sha256"]
        or document.get("work_id") != manifest_binding["work_id"]
        or document.get("source_sha256") != manifest_binding["source_sha256"]
        or document.get("limits") != dict(expected_limits)
        or document.get("max_input_bytes") != preregistration["limits_common"]["max_input_bytes"]
    ):
        raise ProjectionError(
            "execution plan differs from campaign, profile or continuity manifest"
        )
    if (
        campaign_key == "v2"
        and document["external_anchor_public_key_hex"] != persistent_signer_public_key
    ):
        raise ProjectionError("v2 execution plan does not bind the persistent campaign signer")
    _require_sha256(document.get("code_sha256"), "execution plan code hash")
    expected_code = V1_RUNNER_SHA256 if campaign_key == "v1" else _sha256(RUNNER_PATH.read_bytes())
    if document["code_sha256"] != expected_code:
        raise ProjectionError("execution plan runner hash differs from the selected campaign")
    environment = document.get("environment")
    if (
        not isinstance(environment, dict)
        or set(environment) != {"implementation", "int_max_str_digits", "version"}
        or not isinstance(environment["implementation"], str)
        or not environment["implementation"]
        or _positive_integer(environment["int_max_str_digits"], "runtime integer limit") < 1
        or not isinstance(environment["version"], list)
        or len(environment["version"]) != 3
        or any(_nonnegative_integer(item, "runtime version") < 0 for item in environment["version"])
    ):
        raise ProjectionError("execution plan runtime identity is invalid")
    binding = document.get("input_binding")
    if not isinstance(binding, dict):
        raise ProjectionError("execution plan input binding is invalid")
    _require_exact_keys(binding, P2A_BINDING_FIELDS, "P2a input binding")
    for name in P2A_BINDING_FIELDS - {"materializer_id", "materializer_version", "mode"}:
        _require_sha256(binding.get(name), f"P2a input binding {name}")
    if (
        binding.get("mode") != "P2A_BOUND"
        or binding.get("materializer_id") != implementation["materializer_id"]
        or binding.get("materializer_version") != implementation["materializer_version"]
        or binding.get("execution_plan_sha256") != manifest_binding["p2a_execution_plan_sha256"]
        or binding.get("p2a_terminal_checkpoint_sha256")
        != manifest_binding["p2a_terminal_checkpoint_sha256"]
        or binding.get("p2a_work_id") != manifest_binding["p2a_work_id"]
    ):
        raise ProjectionError("execution plan does not bind the frozen P2a parent")
    return document


def _validate_fraction(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"denominator", "numerator"}:
        raise ProjectionError("contact rational fields are invalid")
    numerator = value["numerator"]
    denominator = value["denominator"]
    if (
        not isinstance(numerator, str)
        or not isinstance(denominator, str)
        or re.fullmatch(r"0|-?[1-9][0-9]*", numerator) is None
        or re.fullmatch(r"[1-9][0-9]*", denominator) is None
    ):
        raise ProjectionError("contact rational is not canonical and reduced")
    try:
        reduced = math.gcd(int(numerator), int(denominator)) == 1
    except ValueError as error:
        raise ProjectionError("contact rational exceeds the runtime integer policy") from error
    if not reduced:
        raise ProjectionError("contact rational is not canonical and reduced")


def _validate_mesh(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectionError("result mesh must be an object or null")
    _require_exact_keys(value, MESH_FIELDS, "result mesh")
    return {name: _nonnegative_integer(value[name], f"mesh.{name}") for name in MESH_FIELDS}


def _validate_broadphase(value: Any, limits: Mapping[str, int]) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectionError("result broadphase must be an object or null")
    _require_exact_keys(value, BROADPHASE_FIELDS, "result broadphase")
    result = {
        name: _nonnegative_integer(value[name], f"broadphase.{name}") for name in BROADPHASE_FIELDS
    }
    active = result["active_pair_comparisons"]
    bbox = result["bbox_candidate_pairs"]
    exact = result["exact_pairs_examined"]
    allowed = result["allowed_topological_adjacencies"]
    if not allowed <= exact <= bbox <= active or active > limits["max_candidate_pairs"] + 1:
        raise ProjectionError("broadphase counters violate runner invariants")
    return result


def _validate_contact(value: Any, mesh: Mapping[str, int]) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectionError("result contact must be an object or null")
    _require_exact_keys(value, CONTACT_FIELDS, "result contact")
    dimension = value["dimension"]
    if isinstance(dimension, bool) or dimension not in {0, 1, 2}:
        raise ProjectionError("result contact dimension is invalid")
    if value["kind"] != ("POINT", "SEGMENT", "POLYGON")[dimension]:
        raise ProjectionError("result contact kind differs from its dimension")
    points = value["points"]
    expected_count = {0: 1, 1: 2}.get(dimension)
    if (
        not isinstance(points, list)
        or (expected_count is not None and len(points) != expected_count)
        or (dimension == 2 and len(points) < 3)
    ):
        raise ProjectionError("result contact point count is invalid")
    for point in points:
        if not isinstance(point, list) or len(point) != 3:
            raise ProjectionError("contact point is not a rational Vec3")
        for coordinate in point:
            _validate_fraction(coordinate)
    pair = value["triangle_pair"]
    if (
        not isinstance(pair, list)
        or len(pair) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in pair)
        or pair != sorted(set(pair))
        or pair[-1] >= mesh["triangle_count"]
    ):
        raise ProjectionError("result contact triangle pair is invalid")
    shared = value["shared_topological_vertices"]
    if (
        not isinstance(shared, list)
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in shared)
        or shared != sorted(set(shared))
        or len(shared) > 3
        or any(item >= mesh["vertex_count"] for item in shared)
    ):
        raise ProjectionError("result shared topological vertices are invalid")
    return dict(value)


def _validate_scientific_payload(
    value: Mapping[str, Any], expected_limits: Mapping[str, int]
) -> dict[str, Any]:
    payload = dict(value)
    _require_exact_keys(payload, set(SCIENTIFIC_FIELDS), "scientific payload")
    if payload.get("numeric_model") != NUMERIC_MODEL or payload.get("limits") != dict(
        expected_limits
    ):
        raise ProjectionError("scientific numeric model or limits differ from the plan")
    mesh = _validate_mesh(payload["mesh"])
    broadphase = _validate_broadphase(payload["broadphase"], expected_limits)
    status = payload["status"]
    if status not in STATUS_VALUES or not isinstance(payload.get("diagnostic"), str):
        raise ProjectionError("scientific status or diagnostic is invalid")
    if payload["contact"] is not None and mesh is None:
        raise ProjectionError("contact witness cannot exist without mesh counts")
    contact = None if payload["contact"] is None else _validate_contact(payload["contact"], mesh)
    if status == "EXACT_INTERSECTION_FREE_CANDIDATE":
        if (
            payload["error_code"] is not None
            or payload["diagnostic"] != "ALL_CONSERVATIVE_BROADPHASE_PAIRS_EXHAUSTED"
            or mesh is None
            or broadphase is None
            or contact is not None
        ):
            raise ProjectionError("free-candidate result contract is inconsistent")
    elif status == "EXACT_CONTACT_FOUND":
        if (
            payload["error_code"] != "EXACT_DISALLOWED_CONTACT"
            or payload["diagnostic"] != "EXACT_DISALLOWED_CONTACT_WITNESS"
            or mesh is None
            or broadphase is None
            or broadphase["exact_pairs_examined"] < 1
            or contact is None
        ):
            raise ProjectionError("exact-contact result contract is inconsistent")
    elif status == "RESOURCE_LIMIT":
        if (
            payload["error_code"] not in RESOURCE_CODES
            or contact is not None
            or payload["diagnostic"]
            not in {
                "DECLARED_DETERMINISTIC_RESOURCE_BOUND_REACHED",
                "ISOLATED_EXACT_CHILD_CPU_LIMIT",
                "ISOLATED_EXACT_CHILD_TIMEOUT",
                "SOURCE_EXCEEDS_DECLARED_INPUT_BOUND",
            }
        ):
            raise ProjectionError("resource-limit result contract is inconsistent")
        if payload["error_code"] == "MAX_CANDIDATE_PAIRS" and (
            broadphase is None
            or broadphase["active_pair_comparisons"] != expected_limits["max_candidate_pairs"] + 1
        ):
            raise ProjectionError("pair-limit result lacks its fail-fast counter")
        if payload["error_code"] in {"CHILD_CPU_LIMIT", "CHILD_TIMEOUT", "MAX_INPUT_BYTES"} and (
            mesh is not None or broadphase is not None
        ):
            raise ProjectionError("external resource result claims in-child evidence")
    elif (
        payload["error_code"] not in ERROR_CODES
        or contact is not None
        or mesh is not None
        or broadphase is not None
        or payload["diagnostic"]
        not in {
            "CANONICAL_MESH_CONTRACT_REJECTED",
            "EXACT_ARITHMETIC_FAILED_CLOSED",
            "ISOLATED_CHILD_RETRY_BUDGET_EXHAUSTED",
            "JSON_INPUT_REJECTED",
        }
    ):
        raise ProjectionError("error result contract is inconsistent")
    return payload


def _validate_result_evidence(
    result_bytes: bytes,
    result: Mapping[str, Any],
    plan: Mapping[str, Any],
    terminal: Mapping[str, Any],
    claim: Mapping[str, Any],
    implementation: Mapping[str, Any],
) -> dict[str, Any]:
    document = dict(result)
    if result_bytes != canonical_bytes(document):
        raise ProjectionError("result bytes are not the canonical result document")
    _require_exact_keys(document, RESULT_FIELDS, "P2c result")
    plan_sha256 = sha256_value(plan)
    if (
        document.get("schema") != implementation["result_schema"]
        or document.get("schema_version") != implementation["result_schema_version"]
        or document.get("algorithm_id") != implementation["algorithm_id"]
        or document.get("algorithm_version") != implementation["algorithm_version"]
        or document.get("plan_sha256") != plan_sha256
        or document.get("work_id") != plan["work_id"]
        or document.get("source_sha256") != plan["source_sha256"]
        or document.get("source_size_bytes") != plan["source_size_bytes"]
        or document.get("input_binding") != plan["input_binding"]
    ):
        raise ProjectionError("result identity or execution-plan binding is invalid")
    scientific = {name: document[name] for name in SCIENTIFIC_FIELDS}
    _validate_scientific_payload(scientific, plan["limits"])
    _require_exact_keys(terminal, TERMINAL_FIELDS, "terminal checkpoint")
    result_sha256 = _sha256(result_bytes)
    if (
        terminal.get("state") != "TERMINAL"
        or terminal.get("plan_sha256") != plan_sha256
        or terminal.get("work_id") != plan["work_id"]
        or terminal.get("result_sha256") != result_sha256
        or not isinstance(terminal.get("result_filename"), str)
        or RESULT_FILENAME.fullmatch(terminal["result_filename"]) is None
        or not isinstance(terminal.get("attempt"), int)
        or isinstance(terminal.get("attempt"), bool)
        or not 1 <= terminal["attempt"] <= 2
    ):
        raise ProjectionError("terminal checkpoint does not bind the exact result and plan")
    for name in ("claim_sha256", "previous_checkpoint_sha256"):
        _require_sha256(terminal.get(name), f"terminal {name}")
    _require_exact_keys(claim, CLAIM_FIELDS, "authority claim")
    claim_sha256 = sha256_value(claim)
    previous_claim_sha256 = claim.get("previous_claim_sha256")
    if previous_claim_sha256 is not None:
        _require_sha256(previous_claim_sha256, "previous claim")
    if (
        claim.get("schema") != "MVX-P2C-ATTEMPT-AUTHORITY-CLAIM"
        or claim.get("schema_version") != "0.1.0"
        or claim.get("trust_model") != AUTHORITY_TRUST_MODEL
        or claim.get("plan_sha256") != plan_sha256
        or claim.get("work_id") != plan["work_id"]
        or claim.get("attempt") != terminal["attempt"]
        or terminal["claim_sha256"] != claim_sha256
    ):
        raise ProjectionError("authority claim does not bind terminal result")
    public_key = claim.get("public_key_hex")
    if not isinstance(public_key, str) or SHA256.fullmatch(public_key) is None:
        raise ProjectionError("authority claim public key is invalid")
    authorization = document.get("authorization")
    if not isinstance(authorization, dict):
        raise ProjectionError("result authorization is invalid")
    _require_exact_keys(authorization, AUTHORIZATION_FIELDS, "result authorization")
    signature = authorization.get("signature_hex")
    if (
        authorization.get("attempt") != claim["attempt"]
        or authorization.get("claim_sha256") != claim_sha256
        or authorization.get("signature_algorithm") != "ED25519"
        or authorization.get("trust_model") != AUTHORITY_TRUST_MODEL
        or not isinstance(signature, str)
        or SHA512_HEX.fullmatch(signature) is None
    ):
        raise ProjectionError("result authorization fields are invalid")
    unsigned = {name: value for name, value in document.items() if name != "authorization"}
    message = canonical_bytes(
        {
            "attempt": claim["attempt"],
            "claim_sha256": claim_sha256,
            "result": unsigned,
            "signature_domain": "MVX-P2C-RESULT-AUTHORIZATION-ED25519-1",
        }
    )
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), message
        )
    except (InvalidSignature, ValueError) as error:
        raise ProjectionError("result authorization signature is invalid") from error
    return document


def project_bound_result(
    *,
    campaign_key: str,
    slot_id: str,
    preregistration: Mapping[str, Any],
    context_set: Mapping[str, Any],
    continuity_manifest: Mapping[str, Any],
    execution_plan: Mapping[str, Any],
    terminal_checkpoint: Mapping[str, Any],
    authority_claim: Mapping[str, Any],
    result_bytes: bytes,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    prereg = validate_preregistration(preregistration)
    contexts = validate_contexts(context_set, prereg)
    continuity = validate_continuity_manifest(continuity_manifest, prereg)
    slot_rows = [slot for slot in prereg["execution_slots"] if slot["slot_id"] == slot_id]
    context_rows = [row for row in contexts["contexts"] if row["slot_id"] == slot_id]
    continuity_rows = [row for row in continuity["slots"] if row["slot_id"] == slot_id]
    if len(slot_rows) != 1 or len(context_rows) != 1 or len(continuity_rows) != 1:
        raise ProjectionError("slot is not uniquely bound across public and private manifests")
    slot = slot_rows[0]
    context = context_rows[0]
    continuity_row = continuity_rows[0]
    implementation = _campaign_implementation(prereg, campaign_key)
    plan = _validate_plan(
        execution_plan,
        implementation,
        continuity_row[campaign_key],
        _expected_limits(prereg, slot),
        prereg,
        campaign_key,
        continuity["persistent_signer_public_key_ed25519_hex"],
    )
    validated_result = _validate_result_evidence(
        result_bytes,
        result,
        plan,
        terminal_checkpoint,
        authority_claim,
        implementation,
    )
    scientific_payload = {name: validated_result[name] for name in SCIENTIFIC_FIELDS}
    return {
        "schema": PROJECTION_SCHEMA,
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "campaign_version": implementation["campaign_version"],
            "comparison_slot": context["comparison_slot"],
            "profile_id": context["profile_id"],
            "slot_id": context["slot_id"],
        },
        "implementation": {
            name: implementation[name]
            for name in (
                "algorithm_id",
                "algorithm_version",
                "materializer_id",
                "materializer_version",
                "result_schema",
                "result_schema_version",
                "vertex_index_policy",
            )
        },
        "scientific_payload": scientific_payload,
        "scientific_payload_sha256": sha256_value(scientific_payload),
        "privacy": {
            "contains_authority_envelope": False,
            "contains_signature": False,
            "contains_source_identity": False,
            "contains_storage_locator": False,
            "contains_work_id": False,
            "visibility": "PRIVATE",
        },
        "interpretation": {
            "gate_credit": "NONE",
            "solid_status_V_allowed": False,
        },
    }


def validate_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    projection = dict(value)
    _require_exact_keys(
        projection,
        {
            "schema",
            "schema_version",
            "campaign",
            "implementation",
            "scientific_payload",
            "scientific_payload_sha256",
            "privacy",
            "interpretation",
        },
        "scientific projection",
    )
    if (
        projection.get("schema") != PROJECTION_SCHEMA
        or projection.get("schema_version") != PROJECTION_SCHEMA_VERSION
    ):
        raise ProjectionError("scientific projection identity is invalid")
    campaign = projection.get("campaign")
    implementation = projection.get("implementation")
    payload = projection.get("scientific_payload")
    if (
        not isinstance(campaign, dict)
        or not isinstance(implementation, dict)
        or not isinstance(payload, dict)
    ):
        raise ProjectionError("scientific projection structure is invalid")
    _require_exact_keys(
        campaign,
        {"campaign_id", "campaign_version", "comparison_slot", "profile_id", "slot_id"},
        "projection campaign",
    )
    contexts = {
        slot["slot_id"]: (slot["comparison_slot"], slot["profile_id"], slot["max_candidate_pairs"])
        for slot in _expected_slots()
    }
    slot_id = campaign.get("slot_id")
    if (
        campaign.get("campaign_id") != CAMPAIGN_ID
        or campaign.get("campaign_version") not in {"v1", "2.0.0"}
        or slot_id not in contexts
        or (campaign.get("comparison_slot"), campaign.get("profile_id")) != contexts[slot_id][:2]
    ):
        raise ProjectionError("projection campaign or slot identity is invalid")
    _require_exact_keys(
        implementation,
        {
            "algorithm_id",
            "algorithm_version",
            "materializer_id",
            "materializer_version",
            "result_schema",
            "result_schema_version",
            "vertex_index_policy",
        },
        "projection implementation",
    )
    expected_implementation = (
        {
            "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
            "algorithm_version": "0.2.0",
            "materializer_id": "mvx-p2c-p2a-canonical-scene-materializer",
            "materializer_version": "0.1.0",
            "result_schema": "MVX-P2C-EXACT-TRIANGLE-CONTACT",
            "result_schema_version": "0.2.0",
            "vertex_index_policy": "COORDINATE_EQUAL_VERTEX_INSTANCES_WELDED",
        }
        if campaign["campaign_version"] == "v1"
        else {
            "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
            "algorithm_version": "0.3.0",
            "materializer_id": "mvx-p2c-p2a-canonical-scene-materializer",
            "materializer_version": "0.2.0",
            "result_schema": "MVX-P2C-EXACT-TRIANGLE-CONTACT",
            "result_schema_version": "0.3.0",
            "vertex_index_policy": "PRESERVE_P2A_VERTEX_INSTANCE_INDICES_EXACTLY",
        }
    )
    if implementation != expected_implementation:
        raise ProjectionError("projection implementation differs from campaign version")
    limits = {
        "max_candidate_pairs": contexts[slot_id][2],
        "max_coordinate_bits": 2_048,
        "max_runtime_seconds": 120,
        "max_triangles": 1_000_000,
        "max_vertices": 2_000_000,
    }
    _validate_scientific_payload(payload, limits)
    if projection.get("scientific_payload_sha256") != sha256_value(payload):
        raise ProjectionError("scientific projection payload hash is invalid")
    if projection.get("privacy") != {
        "contains_authority_envelope": False,
        "contains_signature": False,
        "contains_source_identity": False,
        "contains_storage_locator": False,
        "contains_work_id": False,
        "visibility": "PRIVATE",
    } or projection.get("interpretation") != {
        "gate_credit": "NONE",
        "solid_status_V_allowed": False,
    }:
        raise ProjectionError("scientific projection privacy or interpretation overclaims")
    return projection


def _differences(left: Any, right: Any, path: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        differences: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}"
            if key not in left or key not in right:
                differences.append(child)
            else:
                differences.extend(_differences(left[key], right[key], child))
        return differences
    if isinstance(left, list):
        differences = [f"{path}.length"] if len(left) != len(right) else []
        for index, (left_value, right_value) in enumerate(zip(left, right, strict=False)):
            differences.extend(_differences(left_value, right_value, f"{path}[{index}]"))
        return differences
    return [] if left == right else [path]


def compare_projections(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    first = validate_projection(left)
    second = validate_projection(right)
    if first["campaign"]["comparison_slot"] != second["campaign"]["comparison_slot"]:
        raise ProjectionError("projections do not address the same comparison slot")
    versions = {first["campaign"]["campaign_version"], second["campaign"]["campaign_version"]}
    if versions == {"v1", "2.0.0"}:
        comparison_kind = "HISTORICAL_V1_TO_V2"
    elif versions == {"2.0.0"}:
        comparison_kind = "V2_REPEATABILITY"
    else:
        raise ProjectionError("comparison requires v1-to-v2 or v2 repeatability evidence")
    changed = _differences(first["scientific_payload"], second["scientific_payload"])
    return {
        "schema": COMPARISON_SCHEMA,
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_slot": first["campaign"]["comparison_slot"],
        "comparison_kind": comparison_kind,
        "scientific_payload_equal": not changed,
        "changed_paths": changed,
        "left_scientific_payload_sha256": first["scientific_payload_sha256"],
        "right_scientific_payload_sha256": second["scientific_payload_sha256"],
        "comparison_scope": "SCIENTIFIC_PAYLOAD_ONLY_ENVELOPES_AND_SIGNATURES_EXCLUDED",
        "visibility": "PRIVATE",
        "gate_credit": "NONE",
        "solid_status_V_allowed": False,
    }


def _add_project_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--terminal-checkpoint", type=Path, required=True)
    parser.add_argument("--authority-claim", type=Path, required=True)
    parser.add_argument("--continuity-manifest", type=Path, required=True)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    parser.add_argument("--contexts", type=Path, default=DEFAULT_CONTEXTS)
    parser.add_argument("--output", type=Path, required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prereg = commands.add_parser("validate-preregistration")
    prereg.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    prereg.add_argument("--contexts", type=Path, default=DEFAULT_CONTEXTS)
    continuity = commands.add_parser("validate-continuity-manifest")
    continuity.add_argument("--manifest", type=Path, required=True)
    continuity.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    _add_project_arguments(commands.add_parser("project", help="project one bound P2c v2 result"))
    _add_project_arguments(
        commands.add_parser(
            "project-historical-v1",
            help="project one bound historical P2c v1 result",
        )
    )
    validate = commands.add_parser("validate-projection")
    validate.add_argument("--projection", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--left", type=Path, required=True)
    compare.add_argument("--right", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser


def _project_command(arguments: argparse.Namespace, campaign_key: str) -> None:
    preregistration = validate_preregistration(load_json(arguments.preregistration))
    contexts = validate_contexts(load_json(arguments.contexts), preregistration)
    _, continuity = _read_private_json(arguments.continuity_manifest)
    _, plan = _read_private_json(arguments.execution_plan)
    _, terminal = _read_private_json(arguments.terminal_checkpoint)
    _, claim = _read_private_json(arguments.authority_claim)
    result_bytes, result = _read_private_json(arguments.result)
    projection = project_bound_result(
        campaign_key=campaign_key,
        slot_id=arguments.slot_id,
        preregistration=preregistration,
        context_set=contexts,
        continuity_manifest=continuity,
        execution_plan=plan,
        terminal_checkpoint=terminal,
        authority_claim=claim,
        result_bytes=result_bytes,
        result=result,
    )
    _write_private_once(projection, arguments.output)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "validate-preregistration":
            preregistration = validate_preregistration(load_json(arguments.preregistration))
            validate_contexts(load_json(arguments.contexts), preregistration)
            print("P2C_V2_PREREGISTRATION_VALID")
            return 0
        if arguments.command == "validate-continuity-manifest":
            preregistration = validate_preregistration(load_json(arguments.preregistration))
            _, manifest = _read_private_json(arguments.manifest)
            validate_continuity_manifest(manifest, preregistration)
            print("P2C_PRIVATE_CONTINUITY_VALID")
            return 0
        if arguments.command == "project":
            _project_command(arguments, "v2")
            print("P2C_PRIVATE_V2_PROJECTION_WRITTEN")
            return 0
        if arguments.command == "project-historical-v1":
            _project_command(arguments, "v1")
            print("P2C_PRIVATE_V1_PROJECTION_WRITTEN")
            return 0
        if arguments.command == "validate-projection":
            _, projection = _read_private_json(arguments.projection)
            validate_projection(projection)
            print("P2C_SCIENTIFIC_PROJECTION_VALID")
            return 0
        if arguments.command == "compare":
            _, left = _read_private_json(arguments.left)
            _, right = _read_private_json(arguments.right)
            _write_private_once(compare_projections(left, right), arguments.output)
            print("P2C_PRIVATE_COMPARISON_WRITTEN")
            return 0
    except ProjectionError as error:
        print(f"P2C_PROJECTION_INVALID: {error}", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - never disclose private paths through a traceback
        print("P2C_PROJECTION_INVALID: INTERNAL_ERROR", file=sys.stderr)
        return 3
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
