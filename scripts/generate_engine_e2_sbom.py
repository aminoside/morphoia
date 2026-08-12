#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Generate and verify the bounded E2 SALOME protocol-contract SBOM."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
import urllib.parse
import uuid
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

PROFILE = "e2-salome-protocol-contract"
PROJECT_VERSION = "0.0.1"
SOURCE_COMMIT = "aec106f79e277b3cd3c6dabafe1107280f039aa9"
SELF_ARTIFACT_ID = "sbom-engine-e2-salome-protocol"
MANIFEST_PATH = "artifacts/manifests/engine-e2-salome-protocol.json"
OUTPUT_PATH = "artifacts/sbom/engine-e2-salome-protocol.cdx.json"
TRACEABILITY_PATH = "spec/evidence/e2-salome-protocol-traceability.json"
LOCK_FILES = ("requirements/engine-ci.lock",)
LICENSE_FILES = {
    "LICENSE": "MIT",
    "LICENSE-APACHE": "Apache-2.0",
    "LICENSE-MIT": "MIT",
    "LICENSES/Apache-2.0.txt": "Apache-2.0",
    "LICENSES/CC-BY-4.0.txt": "CC-BY-4.0",
    "LICENSES/MIT.txt": "MIT",
    "NOTICE": "CC-BY-4.0",
}
ARTIFACT_LICENSES = {
    "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md": "CC-BY-4.0",
    "schemas/morphoia-salome-protocol-0.1.schema.json": "MIT",
    "scripts/generate_engine_e2_sbom.py": "Apache-2.0 OR MIT",
    "spec/adr/ADR-019-salome-control-protocol-v0.1.md": "CC-BY-4.0",
    "spec/evidence/e2-salome-protocol-artifact-manifest.schema.json": (
        "Apache-2.0 OR MIT"
    ),
    "spec/evidence/e2-salome-protocol-traceability.json": "CC-BY-4.0",
    "spec/evidence/e2-salome-protocol-traceability.schema.json": (
        "Apache-2.0 OR MIT"
    ),
    "src/morphoia/salome_protocol/__init__.py": "MIT",
    "src/morphoia/salome_protocol/contract.py": "MIT",
    "src/morphoia/salome_protocol/fake_agent.py": "MIT",
    "tests/test_e2_evidence.py": "Apache-2.0 OR MIT",
    "tests/test_salome_protocol.py": "Apache-2.0 OR MIT",
    "tests/test_schemas.py": "MIT",
    OUTPUT_PATH: "CC-BY-4.0",
}
ARTIFACT_MEDIA_TYPES = {
    "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md": "text/markdown",
    "schemas/morphoia-salome-protocol-0.1.schema.json": "application/schema+json",
    "scripts/generate_engine_e2_sbom.py": "text/x-python",
    "spec/adr/ADR-019-salome-control-protocol-v0.1.md": "text/markdown",
    "spec/evidence/e2-salome-protocol-artifact-manifest.schema.json": (
        "application/schema+json"
    ),
    "spec/evidence/e2-salome-protocol-traceability.json": "application/json",
    "spec/evidence/e2-salome-protocol-traceability.schema.json": (
        "application/schema+json"
    ),
    "src/morphoia/salome_protocol/__init__.py": "text/x-python",
    "src/morphoia/salome_protocol/contract.py": "text/x-python",
    "src/morphoia/salome_protocol/fake_agent.py": "text/x-python",
    "tests/test_e2_evidence.py": "text/x-python",
    "tests/test_salome_protocol.py": "text/x-python",
    "tests/test_schemas.py": "text/x-python",
    OUTPUT_PATH: "application/vnd.cyclonedx+json",
}
ARTIFACT_IDS = {
    "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md": "e2-protocol-gate-report",
    "schemas/morphoia-salome-protocol-0.1.schema.json": "salome-protocol-schema-0.1",
    "scripts/generate_engine_e2_sbom.py": "e2-sbom-generator",
    "spec/adr/ADR-019-salome-control-protocol-v0.1.md": "adr-019",
    "spec/evidence/e2-salome-protocol-artifact-manifest.schema.json": (
        "e2-artifact-manifest-schema"
    ),
    "spec/evidence/e2-salome-protocol-traceability.json": "e2-traceability",
    "spec/evidence/e2-salome-protocol-traceability.schema.json": (
        "e2-traceability-schema"
    ),
    "src/morphoia/salome_protocol/__init__.py": "salome-protocol-package-init",
    "src/morphoia/salome_protocol/contract.py": "salome-protocol-contract",
    "src/morphoia/salome_protocol/fake_agent.py": "fake-salome-agent",
    "tests/test_e2_evidence.py": "e2-evidence-tests",
    "tests/test_salome_protocol.py": "salome-protocol-contract-tests",
    "tests/test_schemas.py": "schema-tests",
    OUTPUT_PATH: SELF_ARTIFACT_ID,
}
ARTIFACT_KINDS = {
    "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md": "gate-report",
    "schemas/morphoia-salome-protocol-0.1.schema.json": "protocol-schema",
    "scripts/generate_engine_e2_sbom.py": "evidence-generator",
    "spec/adr/ADR-019-salome-control-protocol-v0.1.md": (
        "architecture-decision-record"
    ),
    "spec/evidence/e2-salome-protocol-artifact-manifest.schema.json": (
        "evidence-schema"
    ),
    "spec/evidence/e2-salome-protocol-traceability.json": "traceability",
    "spec/evidence/e2-salome-protocol-traceability.schema.json": "evidence-schema",
    "src/morphoia/salome_protocol/__init__.py": "contract-implementation",
    "src/morphoia/salome_protocol/contract.py": "contract-implementation",
    "src/morphoia/salome_protocol/fake_agent.py": "contract-implementation",
    "tests/test_e2_evidence.py": "evidence-test",
    "tests/test_salome_protocol.py": "contract-test",
    "tests/test_schemas.py": "schema-test",
    OUTPUT_PATH: "cyclonedx-sbom",
}
ARTIFACT_SOURCES = {
    "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md": "e2-traceability",
    "schemas/morphoia-salome-protocol-0.1.schema.json": "adr-019",
    "scripts/generate_engine_e2_sbom.py": "e2-artifact-manifest-schema",
    "spec/adr/ADR-019-salome-control-protocol-v0.1.md": None,
    "spec/evidence/e2-salome-protocol-artifact-manifest.schema.json": None,
    "spec/evidence/e2-salome-protocol-traceability.json": "e2-traceability-schema",
    "spec/evidence/e2-salome-protocol-traceability.schema.json": (
        "e2-artifact-manifest-schema"
    ),
    "src/morphoia/salome_protocol/__init__.py": "fake-salome-agent",
    "src/morphoia/salome_protocol/contract.py": "salome-protocol-schema-0.1",
    "src/morphoia/salome_protocol/fake_agent.py": "salome-protocol-contract",
    "tests/test_e2_evidence.py": "e2-sbom-generator",
    "tests/test_salome_protocol.py": "salome-protocol-package-init",
    "tests/test_schemas.py": "e2-traceability-schema",
    OUTPUT_PATH: "e2-sbom-generator",
}
ARTIFACT_PROVENANCE = {
    "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md": (
        "Gate report preserving local and hosted results and their evidence limits."
    ),
    "schemas/morphoia-salome-protocol-0.1.schema.json": (
        "Versioned control schema implementing the boundary selected by ADR-019."
    ),
    "scripts/generate_engine_e2_sbom.py": (
        "Deterministic standard-library generator and fail-closed checker."
    ),
    "spec/adr/ADR-019-salome-control-protocol-v0.1.md": (
        "Original E2 protocol-boundary decision authored for Morphoia Engine."
    ),
    "spec/evidence/e2-salome-protocol-artifact-manifest.schema.json": (
        "Closed schema for the bounded E2 evidence profile."
    ),
    "spec/evidence/e2-salome-protocol-traceability.json": (
        "Requirement-to-test-to-evidence mapping for source commit aec106f."
    ),
    "spec/evidence/e2-salome-protocol-traceability.schema.json": (
        "Closed schema separating contract evidence from real SALOME status."
    ),
    "src/morphoia/salome_protocol/__init__.py": (
        "Public package exports for the bounded E2 contract surface."
    ),
    "src/morphoia/salome_protocol/contract.py": (
        "Strict bounded JSON transport helpers for the protocol schema."
    ),
    "src/morphoia/salome_protocol/fake_agent.py": (
        "Explicitly fake contract lifecycle implementation with no SALOME runtime."
    ),
    "tests/test_e2_evidence.py": (
        "Mutation, immutability, schema, allowlist, lock, and deterministic-output tests."
    ),
    "tests/test_salome_protocol.py": (
        "Positive, negative, lifecycle, and truth-boundary tests for the fake contract."
    ),
    "tests/test_schemas.py": (
        "Draft 2020-12 meta-schema checks extended for the E2 evidence schemas."
    ),
    OUTPUT_PATH: (
        "Deterministic CycloneDX 1.5 inventory generated from this closed profile."
    ),
}
ARTIFACT_NOTES = {
    "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md": (
        "The report artifact is verified; the published hosted checkpoint remains FAIL."
    ),
    "src/morphoia/salome_protocol/fake_agent.py": (
        "Contract-test fake only; it is not real SALOME execution evidence."
    ),
    OUTPUT_PATH: (
        "Inventory only; no vulnerability analysis or real SALOME execution is claimed."
    ),
}
PUBLISHED_SOURCE_DIGESTS = {
    "schemas/morphoia-salome-protocol-0.1.schema.json": (
        "8c20efe80430168151cb197bd27f45d86515f7ee05451a910ff92e32fe249963"
    ),
    "spec/adr/ADR-019-salome-control-protocol-v0.1.md": (
        "7581e07695e567690df5ff61784acdfae33d8b3eb8a160cd68721da0fc82fda7"
    ),
    "src/morphoia/salome_protocol/__init__.py": (
        "7d26ad9a946a166206ce304240f81b7b78651c3a526da4b52cc909ff87d2a2c7"
    ),
    "src/morphoia/salome_protocol/contract.py": (
        "c06b3f4187e0ad855cd5e25e90e79e864a5f9ca04804e7c32135fffdcdacb19e"
    ),
    "src/morphoia/salome_protocol/fake_agent.py": (
        "3e4ba847a3df3fcd5dcc1b405d2ebd82519d86e75458aa22bec5b8c791d01320"
    ),
    "tests/test_salome_protocol.py": (
        "85065138701cb4d1da1adf02cd7fabe6b9973d7747ad4896204542a7856446b8"
    ),
}
TRACEABILITY_TESTS = {
    "MOR-ARC-002": ("test_protocol_package_has_no_forbidden_salome_runtime_imports",),
    "MOR-ARC-007": (
        "test_artifact_references_are_hash_size_uri_metadata_only",
        "test_control_plane_rejects_inline_payload_fields_and_unbounded_strings",
    ),
    "MOR-SAL-010": ("test_large_artifact_reference_is_not_transfer_evidence",),
    "MOR-SAL-015": ("test_all_six_request_and_fake_response_contracts_validate",),
    "MOR-SAL-016": (
        "test_fake_capabilities_are_truthful_about_not_running_salome",
        "test_schema_rejects_a_fake_agent_that_claims_real_capability",
    ),
    "MOR-SAL-017": (
        "test_artifact_references_are_hash_size_uri_metadata_only",
        "test_submit_and_cancel_are_idempotent_in_the_fake_contract_lifecycle",
    ),
    "MOR-SAL-018": (
        "test_attempt_state_and_terminality_cannot_contradict_each_other",
        "test_submit_and_cancel_are_idempotent_in_the_fake_contract_lifecycle",
    ),
    "MOR-SAL-019": ("test_fake_publish_never_claims_a_salome_artifact",),
    "MOR-SAL-020": ("test_attempt_state_and_terminality_cannot_contradict_each_other",),
}
TRACEABILITY_EVIDENCE = {
    "MOR-ARC-002": (
        "tests/test_salome_protocol.py",
        "docs/engine/evidence/E2_PROTOCOL_GATE_REPORT.md",
    ),
    "MOR-ARC-007": (
        "schemas/morphoia-salome-protocol-0.1.schema.json",
        "tests/test_salome_protocol.py",
    ),
    **{
        requirement: (
            "schemas/morphoia-salome-protocol-0.1.schema.json",
            "tests/test_salome_protocol.py",
        )
        for requirement in (
            "MOR-SAL-010",
            "MOR-SAL-015",
            "MOR-SAL-016",
            "MOR-SAL-017",
            "MOR-SAL-018",
            "MOR-SAL-019",
            "MOR-SAL-020",
        )
    },
}
STATUS_VALUES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"}
TRACEABILITY_REQUIREMENTS = {
    "MOR-ARC-002",
    "MOR-ARC-007",
    "MOR-SAL-010",
    "MOR-SAL-015",
    "MOR-SAL-016",
    "MOR-SAL-017",
    "MOR-SAL-018",
    "MOR-SAL-019",
    "MOR-SAL-020",
}
MANIFEST_FIELDS = {
    "schema_version",
    "project",
    "profile",
    "generated_at",
    "manifest_document_license",
    "hash_algorithm",
    "artifacts",
}
REQUIRED_ARTIFACT_FIELDS = {
    "id",
    "kind",
    "path",
    "media_type",
    "size_bytes",
    "sha256",
    "license_expression",
    "provenance",
    "verification_status",
}
OPTIONAL_ARTIFACT_FIELDS = {
    "source_artifact_id",
    "vulnerability_analysis_status",
    "note",
}
PACKAGE_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\?$")
HASH_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})(?:\s*\\)?$")
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_SAFE_INTEGER = 9_007_199_254_740_991
REQUIREMENT_RE = re.compile(r"^MOR-[A-Z]+-[0-9]{3}$")
TEST_ID_RE = re.compile(r"^test_[a-z0-9_]+$")


class DuplicateKeyError(ValueError):
    """Raised when JSON repeats an object key."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def validate_json_value(value: Any, location: str = "$") -> None:
    """Reject values that cannot cross the bounded JSON control boundary safely."""

    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError(f"lone Unicode surrogate at {location}")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError(f"invalid Unicode string at {location}") from error
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise ValueError(f"integer outside the exact binary64 range at {location}")
        return
    if isinstance(value, float):
        # This is a value-domain rejection after JSON parsing, not an API type error.
        raise ValueError(  # noqa: TRY004
            f"floating-point values are not allowed at {location}"
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_value(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            validate_json_value(key, f"{location}.<key>")
            validate_json_value(item, f"{location}.{key}")
        return
    raise ValueError(f"unsupported JSON value at {location}")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {item}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"cannot read strict JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    validate_json_value(value)
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_root(root: Path) -> Path:
    if not root.is_absolute():
        raise ValueError("repository root must be absolute")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("repository root must be a non-symlink directory")
    resolved = root.resolve(strict=True)
    if resolved != root:
        raise ValueError("repository root must be resolved without aliases")
    return root


def validate_relative_path(relative: str) -> PurePosixPath:
    if not isinstance(relative, str) or not relative:
        raise ValueError("file path must be a non-empty string")
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute()
        or "." in posix.parts
        or ".." in posix.parts
        or "\\" in relative
        or posix.as_posix() != relative
    ):
        raise ValueError(f"unsafe repository path: {relative!r}")
    return posix


def safe_root_file(root: Path, relative: str) -> Path:
    root = validate_root(root)
    posix = validate_relative_path(relative)
    path = root.joinpath(*posix.parts)
    cursor = root
    for part in posix.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"required input traverses a symbolic link: {relative}")
    if not path.is_file():
        raise ValueError(f"required input is not a regular non-symlink file: {relative}")
    try:
        path.resolve(strict=True).relative_to(root)
    except ValueError as error:
        raise ValueError(f"input escapes repository root: {relative}") from error
    return path


def safe_root_output(root: Path, relative: str) -> Path:
    root = validate_root(root)
    posix = validate_relative_path(relative)
    path = root.joinpath(*posix.parts)
    cursor = root
    for part in posix.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"output parent traverses a symbolic link: {relative}")
        if not cursor.is_dir():
            raise ValueError(f"output parent is not an existing directory: {relative}")
        if cursor.resolve(strict=True).parent == cursor.resolve(strict=True):
            raise ValueError(f"invalid output parent: {relative}")
    parent = path.parent
    if parent.resolve(strict=True).relative_to(root) == Path("."):
        raise ValueError("E2 output must not target the repository root directly")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"output target is not a regular non-symlink file: {relative}")
    try:
        parent.resolve(strict=True).relative_to(root)
    except ValueError as error:
        raise ValueError(f"output parent escapes repository root: {relative}") from error
    if path.exists():
        resolved = path.resolve(strict=True)
        if resolved != path or resolved.parent != parent.resolve(strict=True):
            raise ValueError(f"output target uses an alias: {relative}")
        target_stat = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_nlink != 1:
            raise ValueError(f"output target has an unsafe alias or type: {relative}")
        for input_relative in (*ARTIFACT_LICENSES, *LOCK_FILES, *LICENSE_FILES):
            if input_relative == relative:
                continue
            input_path = root.joinpath(*PurePosixPath(input_relative).parts)
            if input_path.is_file() and not input_path.is_symlink():
                input_stat = input_path.stat(follow_symlinks=False)
                if (
                    input_stat.st_dev == target_stat.st_dev
                    and input_stat.st_ino == target_stat.st_ino
                ):
                    raise ValueError(f"output aliases an input file: {relative}")
    return path


def license_choice(expression: str) -> list[dict[str, Any]]:
    return [{"expression": expression}]


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_locks(root: Path) -> dict[tuple[str, str], dict[str, set[str]]]:
    packages: dict[tuple[str, str], dict[str, set[str]]] = {}
    for relative in LOCK_FILES:
        path = safe_root_file(root, relative)
        current: tuple[str, str] | None = None
        declaration_has_hash = False
        for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            package_match = PACKAGE_RE.fullmatch(line)
            if package_match:
                if current is not None and not declaration_has_hash:
                    raise ValueError(
                        f"locked package has no digest before {relative}:{number}"
                    )
                current = (
                    normalize_package_name(package_match.group(1)),
                    package_match.group(2),
                )
                packages.setdefault(current, {"hashes": set(), "locks": set()})[
                    "locks"
                ].add(relative)
                declaration_has_hash = False
                continue
            hash_match = HASH_RE.fullmatch(line)
            if hash_match and current is not None:
                packages[current]["hashes"].add(hash_match.group(1))
                declaration_has_hash = True
                continue
            raise ValueError(f"unsupported lock syntax at {relative}:{number}")
        if current is not None and not declaration_has_hash:
            raise ValueError(f"locked package has no digest at end of {relative}")
    return packages


def validate_manifest(
    root: Path,
    manifest: dict[str, Any],
    *,
    verify_self: bool,
) -> list[dict[str, Any]]:
    if set(manifest) != MANIFEST_FIELDS:
        raise ValueError("E2 manifest fields do not match the closed contract")
    expected_values = {
        "schema_version": "1.0.0",
        "project": "Morphoia Engine",
        "profile": PROFILE,
        "manifest_document_license": "CC-BY-4.0",
        "hash_algorithm": "sha256",
    }
    for field, expected in expected_values.items():
        if manifest[field] != expected:
            raise ValueError(f"E2 manifest {field} must be {expected!r}")
    generated_at = manifest["generated_at"]
    if not isinstance(generated_at, str) or not DATE_RE.fullmatch(generated_at):
        raise ValueError("E2 manifest generated_at must be YYYY-MM-DD")
    try:
        date.fromisoformat(generated_at)
    except ValueError as error:
        raise ValueError("E2 manifest generated_at is not a calendar date") from error
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list):
        raise TypeError("E2 manifest artifacts must be an array")

    if set(ARTIFACT_LICENSES) != set(ARTIFACT_SOURCES):
        raise ValueError("internal E2 source graph allowlist is inconsistent")
    if set(ARTIFACT_LICENSES) != set(ARTIFACT_PROVENANCE):
        raise ValueError("internal E2 provenance allowlist is inconsistent")
    identifiers: set[str] = set()
    paths: set[str] = set()
    sources: dict[str, str] = {}
    selected: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise TypeError(f"artifact {index} must be an object")
        fields = set(artifact)
        if not REQUIRED_ARTIFACT_FIELDS.issubset(fields) or not fields.issubset(
            REQUIRED_ARTIFACT_FIELDS | OPTIONAL_ARTIFACT_FIELDS
        ):
            raise ValueError(f"artifact {index} fields do not match the closed contract")
        identifier = artifact["id"]
        if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
            raise ValueError(f"artifact {index} has an invalid id")
        if identifier in identifiers:
            raise ValueError(f"artifact id is duplicated: {identifier}")
        identifiers.add(identifier)
        relative = artifact["path"]
        if not isinstance(relative, str):
            raise TypeError(f"artifact {index} path must be a string")
        if relative in paths:
            raise ValueError(f"artifact path is duplicated: {relative}")
        paths.add(relative)
        if relative not in ARTIFACT_LICENSES:
            raise ValueError(f"artifact is outside the E2 allowlist: {relative}")
        if artifact["id"] != ARTIFACT_IDS[relative]:
            raise ValueError(f"artifact id does not match allowlist: {relative}")
        if artifact["kind"] != ARTIFACT_KINDS[relative]:
            raise ValueError(f"artifact kind does not match allowlist: {relative}")
        if artifact["license_expression"] != ARTIFACT_LICENSES[relative]:
            raise ValueError(f"artifact license does not match allowlist: {relative}")
        if artifact["media_type"] != ARTIFACT_MEDIA_TYPES[relative]:
            raise ValueError(f"artifact media type does not match allowlist: {relative}")
        if artifact["verification_status"] != "PASS":
            raise ValueError(f"artifact verification status must be PASS: {relative}")
        if artifact["provenance"] != ARTIFACT_PROVENANCE[relative]:
            raise ValueError(f"artifact provenance does not match allowlist: {relative}")
        if not isinstance(artifact["size_bytes"], int) or isinstance(
            artifact["size_bytes"], bool
        ):
            raise TypeError(f"artifact size is not an integer: {relative}")
        if not 0 <= artifact["size_bytes"] <= MAX_SAFE_INTEGER:
            raise ValueError(f"artifact size is outside the safe range: {relative}")
        if not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(
            artifact["sha256"]
        ):
            raise ValueError(f"artifact digest is invalid: {relative}")
        expected_source = ARTIFACT_SOURCES[relative]
        source = artifact.get("source_artifact_id")
        if ("source_artifact_id" in artifact) != (expected_source is not None):
            raise ValueError(f"artifact source field presence is invalid: {relative}")
        if source != expected_source:
            raise ValueError(f"artifact source edge does not match allowlist: {relative}")
        if source is not None:
            if not isinstance(source, str) or not IDENTIFIER_RE.fullmatch(source):
                raise ValueError(f"artifact source id is invalid: {relative}")
            sources[identifier] = source
        status = artifact.get("vulnerability_analysis_status")
        if status != "NOT_RUN":
            raise ValueError(
                f"artifact vulnerability analysis must be NOT_RUN: {relative}"
            )
        note = artifact.get("note")
        if ("note" in artifact) != (relative in ARTIFACT_NOTES):
            raise ValueError(f"artifact note field presence is invalid: {relative}")
        if note != ARTIFACT_NOTES.get(relative):
            raise ValueError(f"artifact note does not match allowlist: {relative}")
        pinned_digest = PUBLISHED_SOURCE_DIGESTS.get(relative)
        if pinned_digest is not None and artifact["sha256"] != pinned_digest:
            raise ValueError(
                f"published source digest does not match {SOURCE_COMMIT}: {relative}"
            )
        if relative != OUTPUT_PATH or verify_self:
            path = safe_root_file(root, relative)
            if path.stat().st_size != artifact["size_bytes"]:
                raise ValueError(f"artifact size does not match: {relative}")
            if sha256_file(path) != artifact["sha256"]:
                raise ValueError(f"artifact digest does not match: {relative}")
        if relative != OUTPUT_PATH:
            selected.append(artifact)

    if paths != set(ARTIFACT_LICENSES):
        missing = sorted(set(ARTIFACT_LICENSES) - paths)
        extra = sorted(paths - set(ARTIFACT_LICENSES))
        raise ValueError(f"E2 artifact allowlist mismatch; missing={missing}, extra={extra}")
    self_entries = [item for item in artifacts if item["id"] == SELF_ARTIFACT_ID]
    if len(self_entries) != 1 or self_entries[0]["path"] != OUTPUT_PATH:
        raise ValueError("E2 manifest must contain exactly one SBOM self entry")
    for identifier, source in sources.items():
        if source not in identifiers:
            raise ValueError(f"artifact {identifier} has dangling source {source}")
    for identifier in identifiers:
        visited: set[str] = set()
        cursor = identifier
        while cursor in sources:
            if cursor in visited:
                raise ValueError(f"artifact provenance cycle at {cursor}")
            visited.add(cursor)
            cursor = sources[cursor]
    return selected


def validate_traceability(root: Path, value: dict[str, Any]) -> None:
    expected_fields = {
        "$schema",
        "schema_version",
        "profile",
        "source_commit",
        "real_salome_status",
        "entries",
    }
    if set(value) != expected_fields:
        raise ValueError("E2 traceability fields do not match the closed contract")
    expected_values = {
        "$schema": "./e2-salome-protocol-traceability.schema.json",
        "schema_version": "1.0.0",
        "profile": PROFILE,
        "source_commit": SOURCE_COMMIT,
        "real_salome_status": "NOT_RUN",
    }
    for field, expected in expected_values.items():
        if value[field] != expected:
            raise ValueError(f"E2 traceability {field} must be {expected!r}")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise TypeError("E2 traceability entries must be an array")
    entry_fields = {
        "requirement_id",
        "contract_status",
        "real_salome_status",
        "test_ids",
        "evidence",
        "reason",
    }
    if set(TRACEABILITY_TESTS) != set(TRACEABILITY_EVIDENCE):
        raise ValueError("internal E2 traceability allowlists are inconsistent")
    test_source = safe_root_file(root, "tests/test_salome_protocol.py")
    try:
        syntax = ast.parse(test_source.read_text(encoding="utf-8"), filename=str(test_source))
    except (SyntaxError, UnicodeError) as error:
        raise ValueError("cannot parse protocol test source") from error
    defined_tests = {
        node.name
        for node in ast.walk(syntax)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }
    expected_test_ids = {
        test_id for values in TRACEABILITY_TESTS.values() for test_id in values
    }
    missing_test_ids = sorted(expected_test_ids - defined_tests)
    if missing_test_ids:
        raise ValueError(
            f"E2 traceability references undefined tests: {missing_test_ids}"
        )
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != entry_fields:
            raise ValueError(f"traceability entry {index} fields are invalid")
        requirement = entry["requirement_id"]
        if (
            not isinstance(requirement, str)
            or not REQUIREMENT_RE.fullmatch(requirement)
            or requirement in seen
        ):
            raise ValueError(f"traceability entry {index} requirement is invalid")
        seen.add(requirement)
        if entry["contract_status"] != "PASS":
            raise ValueError(f"traceability contract status is not PASS: {requirement}")
        if entry["real_salome_status"] != "NOT_RUN":
            raise ValueError(f"traceability real SALOME status is not NOT_RUN: {requirement}")
        test_ids = entry["test_ids"]
        if (
            not isinstance(test_ids, list)
            or not test_ids
            or len(test_ids) != len(set(test_ids))
            or not all(
                isinstance(item, str)
                and len(item) <= 256
                and TEST_ID_RE.fullmatch(item)
                for item in test_ids
            )
        ):
            raise ValueError(f"traceability test IDs are invalid: {requirement}")
        if tuple(test_ids) != TRACEABILITY_TESTS.get(requirement):
            raise ValueError(f"traceability test mapping is not exact: {requirement}")
        evidence = entry["evidence"]
        if (
            not isinstance(evidence, list)
            or not evidence
            or len(evidence) != len(set(evidence))
        ):
            raise ValueError(f"traceability evidence is invalid: {requirement}")
        if tuple(evidence) != TRACEABILITY_EVIDENCE.get(requirement):
            raise ValueError(f"traceability evidence mapping is not exact: {requirement}")
        for relative in evidence:
            if not isinstance(relative, str) or relative not in ARTIFACT_LICENSES:
                raise ValueError(
                    f"traceability evidence is outside the E2 allowlist: {requirement}"
                )
            safe_root_file(root, relative)
        reason = entry["reason"]
        if not isinstance(reason, str) or not reason or len(reason) > 2048:
            raise ValueError(f"traceability reason is invalid: {requirement}")
    if seen != TRACEABILITY_REQUIREMENTS:
        raise ValueError("E2 traceability requirement set does not match the closed profile")


def file_component(
    root: Path,
    relative: str,
    bom_ref: str,
    license_expression: str,
    properties: list[dict[str, str]],
) -> dict[str, Any]:
    path = safe_root_file(root, relative)
    return {
        "type": "file",
        "bom-ref": bom_ref,
        "name": relative,
        "hashes": [{"alg": "SHA-256", "content": sha256_file(path)}],
        "licenses": license_choice(license_expression),
        "properties": sorted(properties, key=lambda item: (item["name"], item["value"])),
    }


def build_bom(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = validate_root(root)
    expected_manifest = safe_root_file(root, MANIFEST_PATH)
    if not manifest_path.is_absolute() or manifest_path != expected_manifest:
        raise ValueError("E2 manifest path must be the exact in-root profile path")
    manifest = read_json(expected_manifest)
    artifacts = validate_manifest(root, manifest, verify_self=False)
    for relative, media_type in ARTIFACT_MEDIA_TYPES.items():
        if media_type == "application/schema+json":
            read_json(safe_root_file(root, relative))
    validate_traceability(root, read_json(safe_root_file(root, TRACEABILITY_PATH)))
    packages = parse_locks(root)
    components: list[dict[str, Any]] = []
    for artifact in artifacts:
        components.append(
            file_component(
                root,
                artifact["path"],
                f"urn:morphoia:e2-artifact:{artifact['id']}",
                artifact["license_expression"],
                [
                    {"name": "morphoia:artifact:id", "value": artifact["id"]},
                    {"name": "morphoia:artifact:kind", "value": artifact["kind"]},
                    {
                        "name": "morphoia:evidence:verification-status",
                        "value": artifact["verification_status"],
                    },
                ],
            )
        )
    for relative, expression in sorted(LICENSE_FILES.items()):
        components.append(
            file_component(
                root,
                relative,
                f"urn:morphoia:e2-license:{urllib.parse.quote(relative, safe='')}",
                expression,
                [{"name": "morphoia:role", "value": "license-or-notice-file"}],
            )
        )
    for relative in LOCK_FILES:
        components.append(
            file_component(
                root,
                relative,
                f"urn:morphoia:e2-lock:{urllib.parse.quote(relative, safe='')}",
                "Apache-2.0 OR MIT",
                [
                    {"name": "morphoia:profile", "value": PROFILE},
                    {
                        "name": "morphoia:implementation-base-commit",
                        "value": SOURCE_COMMIT,
                    },
                    {"name": "morphoia:role", "value": "hashed-test-lock"},
                ],
            )
        )
    for (name, version), values in sorted(packages.items()):
        purl = (
            f"pkg:pypi/{urllib.parse.quote(name, safe='')}"
            f"@{urllib.parse.quote(version, safe='')}"
        )
        components.append(
            {
                "type": "library",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "scope": "excluded",
                "purl": purl,
                "hashes": [
                    {"alg": "SHA-256", "content": digest}
                    for digest in sorted(values["hashes"])
                ],
                "licenses": [{"license": {"name": "NOASSERTION"}}],
                "properties": [
                    {"name": "morphoia:license-review-status", "value": "NOT_RUN"},
                    {
                        "name": "morphoia:provisioning",
                        "value": "lock-only-not-shipped-by-sbom",
                    },
                    {
                        "name": "morphoia:source-locks",
                        "value": ",".join(sorted(values["locks"])),
                    },
                ],
            }
        )
    components.sort(key=lambda item: item["bom-ref"])
    serial_seed = json.dumps(
        {
            "profile": PROFILE,
            "version": PROJECT_VERSION,
            "components": [
                {
                    "bom-ref": item["bom-ref"],
                    "hashes": item.get("hashes", []),
                    "version": item.get("version"),
                }
                for item in components
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)
    root_ref = f"pkg:generic/morphoia-engine-e2-salome-protocol@{PROJECT_VERSION}"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "group": "org.morphoia",
                "name": "morphoia-engine-e2-salome-protocol",
                "version": PROJECT_VERSION,
                "licenses": license_choice("Apache-2.0 OR MIT"),
                "externalReferences": [
                    {"type": "vcs", "url": "https://github.com/Aminoside/morphoia"}
                ],
                "properties": [
                    {"name": "morphoia:profile", "value": PROFILE},
                    {
                        "name": "morphoia:implementation-base-commit",
                        "value": SOURCE_COMMIT,
                    },
                    {"name": "morphoia:execution-scope", "value": "contract-only"},
                    {"name": "morphoia:salome-runtime-status", "value": "NOT_RUN"},
                    {
                        "name": "morphoia:vulnerability-analysis-status",
                        "value": "NOT_RUN",
                    },
                    {
                        "name": "morphoia:vulnerability-analysis-note",
                        "value": "Inventory generation is not a vulnerability assessment",
                    },
                ],
            }
        },
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": []},
            *({"ref": item["bom-ref"], "dependsOn": []} for item in components),
        ],
    }


def deterministic_json(value: Any) -> str:
    """Serialize the generated inventory reproducibly, without IR semantics."""

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_atomic(root: Path, relative: str, content: str) -> None:
    path = safe_root_output(root, relative)
    parent = path.parent
    expected_parent_stat = parent.stat(follow_symlinks=False)
    parent_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = -1
    temporary_basename: str | None = None
    try:
        opened_parent_stat = os.fstat(parent_descriptor)
        if (
            opened_parent_stat.st_dev != expected_parent_stat.st_dev
            or opened_parent_stat.st_ino != expected_parent_stat.st_ino
        ):
            raise ValueError("output parent changed before opening")
        initial_target: tuple[int, int] | None
        try:
            target_stat = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            initial_target = None
        else:
            if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_nlink != 1:
                raise ValueError("output target has an unsafe alias or type")
            initial_target = (target_stat.st_dev, target_stat.st_ino)
        for _ in range(100):
            candidate = f".{path.name}.{uuid.uuid4().hex}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_basename = candidate
            break
        if descriptor < 0 or temporary_basename is None:
            raise ValueError("cannot allocate a unique in-directory temporary output")
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        current_parent_stat = parent.stat(follow_symlinks=False)
        if (
            current_parent_stat.st_dev != opened_parent_stat.st_dev
            or current_parent_stat.st_ino != opened_parent_stat.st_ino
        ):
            raise ValueError("output parent changed during write")
        try:
            target_stat = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            current_target = None
        else:
            if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_nlink != 1:
                raise ValueError("output target changed to an unsafe alias or type")
            current_target = (target_stat.st_dev, target_stat.st_ino)
        if current_target != initial_target:
            raise ValueError("output target changed during write")
        os.replace(
            temporary_basename,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_basename = None
        os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_basename is not None:
            try:
                os.unlink(temporary_basename, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        root = validate_root(arguments.root)
        manifest = safe_root_file(root, MANIFEST_PATH)
        output = safe_root_output(root, OUTPUT_PATH)
        content = deterministic_json(build_bom(root, manifest))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if arguments.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != content:
                raise ValueError(f"E2 SBOM differs from deterministic output: {output}")
            manifest_value = read_json(manifest)
            validate_manifest(root, manifest_value, verify_self=True)
            self_entry = next(
                item
                for item in manifest_value["artifacts"]
                if item["id"] == SELF_ARTIFACT_ID
            )
            if self_entry["sha256"] != digest or self_entry["size_bytes"] != len(
                content.encode("utf-8")
            ):
                raise ValueError("E2 manifest SBOM self metadata is stale")
        else:
            write_atomic(root, OUTPUT_PATH, content)
    except (OSError, TypeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    verb = "matches" if arguments.check else "wrote"
    print(f"PASS: {verb} E2 CycloneDX SBOM {output} (sha256:{digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
