#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Generate the closed qualified IR inspection manifest and CycloneDX SBOM.

The profile is deliberately independent from every closed E0/E1/E2 evidence
profile.  It reads a literal file allowlist through confined descriptors,
validates the ten-unit/eight-export/20-report/frozen-predecessor invariants,
and publishes its two generated documents atomically.  Inventory generation
is not vulnerability analysis and does not promote an unexecuted requirement.
"""

from __future__ import annotations

import argparse
import ast
import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import urllib.parse
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple, NoReturn

LOT = "qualified-ir-inspection-0.1"
PROFILE = "engine-ir-core-si-0.1"
PROJECT_VERSION = "0.0.1"
SOURCE_BASE_COMMIT = "767b88ab7e89b30ed77f5b30c25372d71fa06402"
GENERATED_AT = "2026-08-12"
MANIFEST_PATH = "artifacts/manifests/engine-qualified-ir-inspection-0.1.json"
SBOM_PATH = "artifacts/sbom/engine-qualified-ir-inspection-0.1.cdx.json"
MANIFEST_SCHEMA_PATH = (
    "spec/evidence/qualified-ir-inspection-0.1-artifact-manifest.schema.json"
)
TRACEABILITY_SCHEMA_PATH = (
    "spec/evidence/qualified-ir-inspection-0.1-traceability.schema.json"
)
TRACEABILITY_PATH = "spec/evidence/qualified-ir-inspection-0.1-traceability.json"
REPORT_VECTORS_SCHEMA_PATH = (
    "spec/evidence/qualified-ir-inspection-0.1-report-vectors.schema.json"
)
REPORT_VECTORS_PATH = "spec/evidence/qualified-ir-inspection-0.1-report-vectors.json"
REPORT_PATH = "docs/engine/evidence/QUALIFIED_IR_INSPECTION_0_1_REPORT.md"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_INPUT_BYTES = 64 * 1024 * 1024
RENAME_NOREPLACE = 1
RENAME_EXCHANGE = 2
STATUS_VALUES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPORT_RE = re.compile(r"^\s+(morphoia_[a-z0-9_]+);\s*$", re.MULTILINE)
CTEST_RE = re.compile(
    r"\badd_test\s*\(\s*NAME\s+([A-Za-z0-9][A-Za-z0-9_.-]*)\b",
    re.MULTILINE,
)
UNIT_RE = re.compile(
    r'\{"([^"\\]+)",\s*Dimensions\{([^}]*)\},\s*(-?\d+),\s*(-?\d+)\}'
)
PACKAGE_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\?$")
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
LOCK_PATHS = ("requirements/engine-ci.lock", "requirements/wheel-build-e1.lock")


class EvidenceError(RuntimeError):
    """The qualified inspection evidence profile is not exact or safe."""


class ArtifactSpec(NamedTuple):
    kind: str
    media_type: str
    license_expression: str
    provenance: str


def _spec(
    kind: str,
    media_type: str,
    license_expression: str,
    provenance: str,
) -> ArtifactSpec:
    return ArtifactSpec(kind, media_type, license_expression, provenance)


CODE = _spec(
    "source-file",
    "text/plain",
    "Apache-2.0 OR MIT",
    "Bounded qualified inspection source, build, test, or validation input.",
)
PYTHON = _spec(
    "source-file",
    "text/x-python",
    "Apache-2.0 OR MIT",
    "Bounded qualified inspection Python implementation or test.",
)
CPP = _spec(
    "source-file",
    "text/x-c++src",
    "Apache-2.0 OR MIT",
    "Bounded qualified inspection C++20 implementation or test.",
)
C_SOURCE = _spec(
    "source-file",
    "text/x-c",
    "Apache-2.0 OR MIT",
    "Bounded qualified inspection C11 ABI implementation consumer or test.",
)
SHELL = _spec(
    "validation-script",
    "text/x-shellscript",
    "Apache-2.0 OR MIT",
    "Bounded qualified inspection build or validation command.",
)
DOC = _spec(
    "documentation",
    "text/markdown",
    "CC-BY-4.0",
    "Qualified inspection design, operating contract, or evidence narrative.",
)
EVIDENCE_JSON = _spec(
    "evidence-record",
    "application/json",
    "CC-BY-4.0",
    "Machine-readable qualified inspection evidence declaration.",
)
SCHEMA = _spec(
    "schema",
    "application/schema+json",
    "Apache-2.0 OR MIT",
    "Closed schema for the qualified inspection or evidence profile.",
)


# This is the exact non-generated artifact inventory for this bounded lot,
# including the final frozen living documents but excluding the cyclic
# generated manifest and SBOM outputs.
ARTIFACT_SPECS: dict[str, ArtifactSpec] = {
    ".github/workflows/build-report.yml": _spec(
        "ci-workflow", "application/yaml", "MIT",
        "Pinned hosted report workflow with full-history frozen replay checkout.",
    ),
    ".github/workflows/engine-ci.yml": _spec(
        "ci-workflow", "application/yaml", "Apache-2.0 OR MIT",
        "Pinned hosted core-CPU matrix with explicit qualified evidence validation.",
    ),
    "CMakeLists.txt": CODE,
    "CHANGELOG.md": _spec(
        "release-documentation", "text/markdown", "MIT",
        "Unreleased qualified inspection lot summary without premature release claims.",
    ),
    "REUSE.toml": _spec(
        "license-metadata", "application/toml", "CC-BY-4.0",
        "Repository SPDX path annotations including this bounded profile.",
    ),
    "cmake/morphoia_engine.map": CODE,
    "cpp/include/morphoia/engine.h": C_SOURCE,
    "cpp/src/core/unit_registry.cpp": CPP,
    "cpp/src/core/unit_registry.hpp": CPP,
    "cpp/src/engine.cpp": CPP,
    "docs/engine/EXECUTION_PLAN.md": DOC,
    "docs/engine/COMPLIANCE_MATRIX.md": DOC,
    "docs/engine/DECISIONS.md": DOC,
    "docs/engine/QUALIFIED_IR_INSPECTION_0_1.md": DOC,
    "docs/engine/STATUS.md": DOC,
    "docs/engine/THREAD_SAFETY.md": DOC,
    REPORT_PATH: _spec(
        "evidence-report", "text/markdown", "CC-BY-4.0",
        "Prospective local gate report with explicit hosted NOT_RUN boundary.",
    ),
    "pyproject.toml": _spec(
        "package-metadata", "application/toml", "MIT",
        "Python package metadata installing the qualified inspection schema.",
    ),
    "requirements/engine-ci.lock": _spec(
        "dependency-lock", "text/plain", "Apache-2.0 OR MIT",
        "Hash-locked Python 3.12/3.13 test and frozen replay dependencies.",
    ),
    "requirements/wheel-build-e1.lock": _spec(
        "dependency-lock", "text/plain", "Apache-2.0 OR MIT",
        "Hash-locked installed-wheel build dependencies.",
    ),
    "schemas/morphoia-engine-ir-inspection-0.1.0.schema.json": SCHEMA,
    "scripts/bootstrap-engine.sh": SHELL,
    "scripts/run-engine-sanitizers.sh": SHELL,
    "scripts/validate-engine-ir-lot.sh": SHELL,
    "scripts/validate-engine-wheel.sh": SHELL,
    "scripts/validate_engine_e1_public_ir_frozen.py": PYTHON,
    "scripts/generate_engine_qualified_ir_inspection_evidence.py": PYTHON,
    "spec/adr/ADR-021-qualified-ir-inspection.md": _spec(
        "architecture-decision-record", "text/markdown", "CC-BY-4.0",
        "Bounded qualified IR inspection decision and promotion boundary.",
    ),
    "spec/evidence/e1-public-ir-freeze.json": EVIDENCE_JSON,
    "spec/evidence/e1-public-ir-freeze.schema.json": SCHEMA,
    MANIFEST_SCHEMA_PATH: SCHEMA,
    REPORT_VECTORS_SCHEMA_PATH: SCHEMA,
    REPORT_VECTORS_PATH: _spec(
        "test-vector-index", "application/json", "CC-BY-4.0",
        "Exactly 20 canonical inspection report sizes and SHA-256 vectors, reproduced twice.",
    ),
    TRACEABILITY_SCHEMA_PATH: SCHEMA,
    TRACEABILITY_PATH: _spec(
        "traceability", "application/json", "CC-BY-4.0",
        "Exact three-requirement prospective mapping and command truth record.",
    ),
    "src/morphoia/__init__.py": _spec(
        "source-file", "text/x-python", "MIT",
        "Reference package exports for qualified inspection.",
    ),
    "src/morphoia/_engine_native.py": PYTHON,
    "src/morphoia/cli.py": _spec(
        "source-file", "text/x-python", "MIT",
        "Human and canonical JSON qualified inspection CLI.",
    ),
    "src/morphoia/engine_ir.py": PYTHON,
    "src/morphoia/engine_ir_contract.py": PYTHON,
    "src/morphoia/engine_ir_inspection.py": PYTHON,
    "src/morphoia/engine_ir_migration.py": PYTHON,
    "tests/fixtures/engine-ir/0.1.0/index.json": _spec(
        "test-fixture-index", "application/json", "CC-BY-4.0",
        "Immutable index for exactly 20 licensed synthetic Engine IR graphs.",
    ),
    "tests/native/consumer/main.c": C_SOURCE,
    "tests/native/core_smoke.cpp": CPP,
    "tests/native/unit_registry_test.cpp": CPP,
    "tests/native/unit_validation_c_api_test.c": C_SOURCE,
    "tests/native/unit_validation_thread_test.cpp": CPP,
    "tests/test_e1_public_ir_frozen.py": PYTHON,
    "tests/test_engine_ir_cli.py": PYTHON,
    "tests/test_engine_ir_inspection.py": PYTHON,
    "tests/test_engine_ir_native.py": PYTHON,
    "tests/test_engine_ir_replay.py": PYTHON,
    "tests/test_qualified_ir_inspection_evidence.py": PYTHON,
}

EXPECTED_ABSENT_PATHS = ("tests/test_e1_public_ir_evidence.py",)
EXPECTED_EXPORTS = {
    "morphoia_canonical_json_profile1",
    "morphoia_context_create",
    "morphoia_context_destroy",
    "morphoia_context_get_abi_version",
    "morphoia_context_query_capability",
    "morphoia_context_validate_engine_ir_unit",
    "morphoia_engine_get_version",
    "morphoia_status_name",
}
EXPECTED_PYTHON_FUNCTIONS = {
    "src/morphoia/_engine_native.py": {"resolve_native_library"},
    "src/morphoia/engine_ir.py": {
        "seal_content",
        "validate_manifest",
        "migrate_legacy_manifest",
        "create_replay_recipe",
        "read_bounded_file",
        "resolve_manifest_reference",
        "replay_manifest",
    },
    "src/morphoia/engine_ir_contract.py": {
        "load_json_strict",
        "validate_manifest",
        "validate_replay",
    },
    "src/morphoia/engine_ir_migration.py": {"build_legacy_migration_content"},
    "src/morphoia/engine_ir_inspection.py": {"inspect_engine_ir"},
}
EXPECTED_NATIVE_ENGINE_METHODS = {
    "__init__",
    "__enter__",
    "__exit__",
    "closed",
    "close",
    "query_capability",
    "canonicalize",
    "validate_engine_ir_unit",
}
EXPECTED_NATIVE_ENGINE_ATTRIBUTES = {
    "library_path",
    "library_file",
    "library_sha256",
    "version",
    "capability",
}
EXPECTED_CLI_FAMILIES = {
    "morphoia inspect",
    "morphoia engine-ir validate",
    "morphoia engine-ir replay",
}
EXPECTED_UNITS = {
    "1": ((0, 0, 0, 0, 0, 0, 0), 1, 0),
    "m": ((1, 0, 0, 0, 0, 0, 0), 1, 0),
    "mm": ((1, 0, 0, 0, 0, 0, 0), 1, -3),
    "s": ((0, 0, 1, 0, 0, 0, 0), 1, 0),
    "kg": ((0, 1, 0, 0, 0, 0, 0), 1, 0),
    "g": ((0, 1, 0, 0, 0, 0, 0), 1, -3),
    "A": ((0, 0, 0, 1, 0, 0, 0), 1, 0),
    "K": ((0, 0, 0, 0, 1, 0, 0), 1, 0),
    "mol": ((0, 0, 0, 0, 0, 1, 0), 1, 0),
    "cd": ((0, 0, 0, 0, 0, 0, 1), 1, 0),
}
EXPECTED_COMMAND_STATUSES = {
    "frozen-public-ir-bridge": "PASS",
    "direct-native-bootstrap": "PASS",
    "two-clean-cmake-builds": "PASS",
    "sanitizers": "PASS",
    "leak-sanitizer": "NOT_RUN",
    "inspection-local": "PASS",
    "public-ir-regression-lot": "PASS",
    "full-python-regression": "PASS",
    "installed-wheel": "PASS",
    "evidence-profile": "PASS",
    "license-and-hygiene": "PASS",
    "hosted-python-3-12": "NOT_RUN",
    "hosted-python-3-13": "NOT_RUN",
    "hosted-pr-and-integration": "NOT_RUN",
    "general-ucum": "NOT_RUN",
    "excluded-profiles": "NOT_RUN",
    "validated-mvx-specification": "BLOCKED",
    "vulnerability-analysis": "NOT_RUN",
    "dependency-license-review": "NOT_RUN",
}
EXPECTED_REQUIREMENT_STATUSES = {
    "MOR-IR-006": "NOT_RUN",
    "MOR-API-006": "NOT_RUN",
    "MOR-QA-017": "NOT_RUN",
}
REQUIRED_PROMOTION_COMMANDS = {
    "sanitizers",
    "inspection-local",
    "full-python-regression",
    "installed-wheel",
    "evidence-profile",
    "license-and-hygiene",
    "hosted-python-3-12",
    "hosted-python-3-13",
    "hosted-pr-and-integration",
}
EXPECTED_TRACEABILITY_SHA256 = (
    "f701162b6864081b206a2c884342dc5112d28bf1e82fef6b4477473d1ce891be"
)
EXPECTED_REPORT_VECTORS_SHA256 = (
    "bb82c92a26feb6f4c276d18630937a3d170b5b43befbeff6bdccbdb5dad34b73"
)


class DuplicateKeyError(ValueError):
    """Strict JSON input repeated a decoded object key."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_float(value: str) -> NoReturn:
    raise EvidenceError(f"floating-point JSON is outside this evidence profile: {value}")


def _reject_constant(value: str) -> NoReturn:
    raise EvidenceError(f"non-JSON numeric constant: {value}")


def _validate_json_domain(value: Any, location: str = "$") -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise EvidenceError(f"lone Unicode surrogate at {location}")
        value.encode("utf-8")
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise EvidenceError(f"unsafe JSON integer at {location}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_domain(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_json_domain(key, f"{location}.<key>")
            _validate_json_domain(item, f"{location}.{key}")
        return
    raise EvidenceError(f"unsupported JSON type at {location}: {type(value).__name__}")


def strict_json(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise EvidenceError(f"invalid strict JSON in {label}: {error}") from error
    _validate_json_domain(value)
    if not isinstance(value, dict):
        raise EvidenceError(f"strict JSON root must be an object: {label}")
    return value


def deterministic_json(value: Any) -> bytes:
    _validate_json_domain(value)
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_root(root: Path) -> Path:
    if not root.is_absolute():
        raise EvidenceError("repository root must be absolute")
    absolute = Path(os.path.abspath(root))
    if absolute != root or root.is_symlink() or not root.is_dir():
        raise EvidenceError("repository root must be a resolved non-symlink directory")
    if root.resolve(strict=True) != root:
        raise EvidenceError("repository root must not use an alias")
    return root


def _path_parts(relative: str) -> tuple[str, ...]:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise EvidenceError("repository path must be a non-empty string")
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute()
        or relative != posix.as_posix()
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise EvidenceError(f"unsafe repository path: {relative!r}")
    return posix.parts


def _open_root(root: Path) -> int:
    root = validate_root(root)
    expected = root.stat(follow_symlinks=False)
    descriptor = os.open(
        root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    )
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
        os.close(descriptor)
        raise EvidenceError("repository root changed while opening")
    return descriptor


def _open_parent(root: Path, relative: str) -> tuple[int, str]:
    parts = _path_parts(relative)
    descriptor = _open_root(root)
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        os.close(descriptor)
        raise EvidenceError(f"unsafe parent directory for {relative}: {error}") from error
    return descriptor, parts[-1]


def read_repository_file(root: Path, relative: str) -> bytes:
    parent, name = _open_parent(root, relative)
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise EvidenceError(f"repository input is not a regular single-link file: {relative}")
        if not 0 <= before.st_size <= MAX_INPUT_BYTES:
            raise EvidenceError(f"repository input exceeds size bound: {relative}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise EvidenceError(f"repository input changed while reading: {relative}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise EvidenceError(f"repository input grew while reading: {relative}")
        after = os.fstat(descriptor)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise EvidenceError(f"repository input changed while reading: {relative}")
        return b"".join(chunks)
    except OSError as error:
        raise EvidenceError(f"cannot safely read repository input {relative}: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def read_repository_json(root: Path, relative: str) -> dict[str, Any]:
    return strict_json(read_repository_file(root, relative), relative)


def _path_exists_without_following(root: Path, relative: str) -> bool:
    parent, name = _open_parent(root, relative)
    try:
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True
    finally:
        os.close(parent)


def _artifact_id(relative: str) -> str:
    return f"qualified-ir-file-{hashlib.sha256(relative.encode()).hexdigest()[:20]}"


def _normalize_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_locks(contents: dict[str, bytes]) -> dict[tuple[str, str], dict[str, set[str]]]:
    packages: dict[tuple[str, str], dict[str, set[str]]] = {}
    for relative in LOCK_PATHS:
        text = contents[relative].decode("utf-8", errors="strict")
        current: tuple[str, str] | None = None
        for number, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            package_match = PACKAGE_RE.fullmatch(line)
            if package_match:
                current = (
                    _normalize_package(package_match.group(1)),
                    package_match.group(2),
                )
                packages.setdefault(current, {"hashes": set(), "locks": set()})[
                    "locks"
                ].add(relative)
                continue
            hashes = HASH_RE.findall(line)
            residue = HASH_RE.sub("", line).replace("\\", "").strip()
            if current is None or not hashes or residue:
                raise EvidenceError(f"unparsed dependency lock line {relative}:{number}")
            packages[current]["hashes"].update(hashes)
        if current is None:
            raise EvidenceError(f"dependency lock is empty: {relative}")
    for (name, version), metadata in packages.items():
        if not metadata["hashes"]:
            raise EvidenceError(f"locked dependency has no SHA-256: {name}=={version}")
    return packages


def _validate_units(root: Path) -> None:
    source = read_repository_file(root, "cpp/src/core/unit_registry.cpp").decode(
        "utf-8", errors="strict"
    )
    found: dict[str, tuple[tuple[int, ...], int, int]] = {}
    for match in UNIT_RE.finditer(source):
        dimensions = tuple(int(item.strip()) for item in match.group(2).split(","))
        value = (dimensions, int(match.group(3)), int(match.group(4)))
        if match.group(1) in found:
            raise EvidenceError(f"duplicate unit registry literal: {match.group(1)}")
        found[match.group(1)] = value
    if found != EXPECTED_UNITS:
        raise EvidenceError("unit registry differs from the exact ten-literal profile")


def _validate_exports(root: Path) -> None:
    source = read_repository_file(root, "cmake/morphoia_engine.map").decode(
        "ascii", errors="strict"
    )
    exports = EXPORT_RE.findall(source)
    if len(exports) != 8 or set(exports) != EXPECTED_EXPORTS:
        raise EvidenceError("Linux export map differs from the exact eight-symbol profile")
    header = read_repository_file(root, "cpp/include/morphoia/engine.h").decode(
        "utf-8", errors="strict"
    )
    header_functions = set(
        re.findall(r"\b(morphoia_[a-z0-9_]+)\s*\(", header)
    )
    if header_functions != EXPECTED_EXPORTS:
        raise EvidenceError("public C header differs from the exact eight-symbol profile")
    thread_contract = read_repository_file(root, "docs/engine/THREAD_SAFETY.md").decode(
        "utf-8", errors="strict"
    )
    for symbol in EXPECTED_EXPORTS:
        if f"`{symbol}`" not in thread_contract:
            raise EvidenceError(f"thread-safety inventory omits export: {symbol}")
    for relative, expected_functions in EXPECTED_PYTHON_FUNCTIONS.items():
        tree = ast.parse(
            read_repository_file(root, relative).decode("utf-8", errors="strict"),
            filename=relative,
        )
        public_functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        }
        if public_functions != expected_functions:
            raise EvidenceError(f"public function inventory differs for {relative}")
        for function in expected_functions:
            if function not in thread_contract:
                raise EvidenceError(f"thread-safety inventory omits function: {function}")

    native_tree = ast.parse(
        read_repository_file(root, "src/morphoia/_engine_native.py").decode(
            "utf-8", errors="strict"
        ),
        filename="src/morphoia/_engine_native.py",
    )
    native_class = next(
        (
            node
            for node in native_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "NativeEngine"
        ),
        None,
    )
    if native_class is None:
        raise EvidenceError("NativeEngine class is missing")
    methods = {
        node.name
        for node in native_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and (not node.name.startswith("_") or node.name in {"__init__", "__enter__", "__exit__"})
    }
    if methods != EXPECTED_NATIVE_ENGINE_METHODS:
        raise EvidenceError("NativeEngine public method inventory differs")
    attributes: set[str] = set()
    for node in ast.walk(native_class):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and not node.attr.startswith("_")
        ):
            attributes.add(node.attr)
    if attributes != EXPECTED_NATIVE_ENGINE_ATTRIBUTES:
        raise EvidenceError("NativeEngine public attribute inventory differs")
    for method in EXPECTED_NATIVE_ENGINE_METHODS - {"__init__"}:
        token = f"NativeEngine.{method}" if not method.startswith("__") else method
        if token not in thread_contract:
            raise EvidenceError(f"thread-safety inventory omits NativeEngine method: {method}")
    for attribute in EXPECTED_NATIVE_ENGINE_ATTRIBUTES:
        if attribute not in thread_contract:
            raise EvidenceError(f"thread-safety inventory omits NativeEngine attribute: {attribute}")
    for family in EXPECTED_CLI_FAMILIES:
        if f"`{family}" not in thread_contract:
            raise EvidenceError(f"thread-safety inventory omits CLI family: {family}")

    cli_source = read_repository_file(root, "src/morphoia/cli.py").decode(
        "utf-8", errors="strict"
    )
    parser_names = re.findall(r"\.add_parser\s*\(\s*\"([a-z-]+)\"", cli_source)
    if not {"inspect", "engine-ir", "validate", "replay"}.issubset(parser_names):
        raise EvidenceError("CLI parser family inventory differs")


def _validate_corpus(root: Path) -> None:
    index = read_repository_json(root, "tests/fixtures/engine-ir/0.1.0/index.json")
    if set(index) != {"format", "format_version", "canonical_profile", "entries"}:
        raise EvidenceError("20-graph index fields differ from the frozen profile")
    if (
        index["format"] != "morphoia.engine.ir-corpus"
        or index["format_version"] != "0.1.0"
        or index["canonical_profile"] != "morphoia.canonical-json.profile1"
    ):
        raise EvidenceError("20-graph index identity differs")
    entries = index["entries"]
    if not isinstance(entries, list) or len(entries) != 20:
        raise EvidenceError("qualified inspection requires exactly 20 graph entries")
    for number, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or entry.get("id", "").split("-", 2)[:2] != [
            "graph",
            f"{number:02d}",
        ]:
            raise EvidenceError("20-graph index order or identifier differs")
        if entry.get("classification") != "synthetic" or entry.get(
            "license_expression"
        ) != "CC-BY-4.0":
            raise EvidenceError("20-graph fixture classification or license differs")
        relative = f"tests/fixtures/engine-ir/0.1.0/{entry.get('input', '')}"
        content = read_repository_file(root, relative)
        if sha256_bytes(content) != entry.get("input_sha256"):
            raise EvidenceError(f"20-graph input digest differs: {relative}")
    inspection_test = read_repository_file(root, "tests/test_engine_ir_inspection.py")
    if (
        b"test_all_twenty_reports_are_native_canonical_and_repeatable" not in inspection_test
        or b"for entry in reversed(index[\"entries\"])" not in inspection_test
        or b"payload resolver must not be called" not in inspection_test
    ):
        raise EvidenceError("20-report twice/no-payload inspection test is missing")


def _validate_report_vectors(root: Path) -> None:
    content = read_repository_file(root, REPORT_VECTORS_PATH)
    if EXPECTED_REPORT_VECTORS_SHA256 != "TO_BE_SEALED" and sha256_bytes(
        content
    ) != EXPECTED_REPORT_VECTORS_SHA256:
        raise EvidenceError("qualified inspection report-vector byte pin differs")
    document = strict_json(content, REPORT_VECTORS_PATH)
    expected_fields = {
        "$schema",
        "schema_version",
        "lot",
        "native_library_sha256",
        "profile",
        "format",
        "format_version",
        "canonical_profile",
        "source_base_commit",
        "corpus_index_sha256",
        "pass_count",
        "passes_identical",
        "vectors",
    }
    if set(document) != expected_fields:
        raise EvidenceError("report-vector document fields differ")
    expected_header = {
        "$schema": "./qualified-ir-inspection-0.1-report-vectors.schema.json",
        "schema_version": "1.0.0",
        "lot": LOT,
        "native_library_sha256": "37c06b1b93e7202872e4ca0f294f68f336c8c55726e3763ef23fb017660cb8f9",
        "profile": PROFILE,
        "format": "morphoia.engine.ir-inspection",
        "format_version": "0.1.0",
        "canonical_profile": "morphoia.canonical-json.profile1",
        "source_base_commit": SOURCE_BASE_COMMIT,
        "corpus_index_sha256": "39a9e4f2381993f88d8ccbea9d66b402b44ab30cdd4e7b16f486334bd1630ad2",
        "pass_count": 2,
        "passes_identical": True,
    }
    for field, expected in expected_header.items():
        if document.get(field) != expected:
            raise EvidenceError(f"report-vector {field} differs")
    index = read_repository_json(root, "tests/fixtures/engine-ir/0.1.0/index.json")
    vectors = document["vectors"]
    if not isinstance(vectors, list) or len(vectors) != 20:
        raise EvidenceError("report-vector document must contain exactly 20 vectors")
    identifiers: set[str] = set()
    for entry, vector in zip(index["entries"], vectors, strict=True):
        if not isinstance(vector, dict) or set(vector) != {
            "id",
            "input_sha256",
            "report_size_bytes",
            "report_sha256",
        }:
            raise EvidenceError("report-vector fields differ")
        if vector["id"] in identifiers or vector["id"] != entry["id"]:
            raise EvidenceError("report-vector identifiers are duplicate or out of order")
        identifiers.add(vector["id"])
        if vector["input_sha256"] != entry["input_sha256"]:
            raise EvidenceError(f"report-vector input digest differs: {vector['id']}")
        size = vector["report_size_bytes"]
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= 64 * 1024 * 1024:
            raise EvidenceError(f"report-vector size is invalid: {vector['id']}")
        if not isinstance(vector["report_sha256"], str) or SHA256_RE.fullmatch(
            vector["report_sha256"]
        ) is None:
            raise EvidenceError(f"report-vector SHA-256 is invalid: {vector['id']}")


def _validate_freeze(root: Path) -> None:
    declaration = read_repository_json(root, "spec/evidence/e1-public-ir-freeze.json")
    snapshot = declaration.get("git_snapshot")
    counts = declaration.get("counts")
    fixture_tree = declaration.get("fixture_tree")
    if not isinstance(snapshot, dict) or not isinstance(counts, dict):
        raise EvidenceError("public-IR freeze snapshot/counts are missing")
    if (
        snapshot.get("commit") != SOURCE_BASE_COMMIT
        or snapshot.get("entry_count") != 309
        or counts.get("historical_evidence_tests") != 22
        or counts.get("manifest_artifacts") != 123
        or counts.get("sbom_components") != 140
        or counts.get("traceability_entries") != 49
    ):
        raise EvidenceError("public-IR freeze anchors differ from the closed profile")
    if not isinstance(fixture_tree, dict) or fixture_tree.get("file_count") != 79:
        raise EvidenceError("public-IR frozen fixture count differs")
    if fixture_tree.get("aggregate_sha256") != (
        "9647bf7be7c40dd39ea533b0677fc09d42eabcdee59b8b5adc5cbdc23f1e25af"
    ):
        raise EvidenceError("public-IR frozen fixture aggregate differs")
    anchors = declaration.get("anchors")
    if not isinstance(anchors, list) or not any(
        item.get("path") == "tests/test_e1_public_ir_evidence.py"
        and item.get("sha256")
        == "6507da4071639ed70f2fc9f1fe6316597815679699417d76018bfdab34d45202"
        for item in anchors
        if isinstance(item, dict)
    ):
        raise EvidenceError("historical evidence test anchor is missing")
    if _path_exists_without_following(root, "tests/test_e1_public_ir_evidence.py"):
        raise EvidenceError("historical public-IR evidence test must not replay mutable HEAD")


def _python_test_ids(root: Path) -> set[str]:
    result: set[str] = set()
    paths = [path for path in ARTIFACT_SPECS if path.startswith("tests/test_")]
    for relative in paths:
        tree = ast.parse(
            read_repository_file(root, relative).decode("utf-8", errors="strict"),
            filename=relative,
        )
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                if node.name in result:
                    raise EvidenceError(f"duplicate Python test identifier: {node.name}")
                result.add(node.name)
    return result


def _native_test_ids(root: Path) -> set[str]:
    cmake = read_repository_file(root, "CMakeLists.txt").decode("utf-8", errors="strict")
    return set(CTEST_RE.findall(cmake))


def _validate_traceability(root: Path) -> dict[str, Any]:
    content = read_repository_file(root, TRACEABILITY_PATH)
    if EXPECTED_TRACEABILITY_SHA256 != "TO_BE_SEALED" and sha256_bytes(
        content
    ) != EXPECTED_TRACEABILITY_SHA256:
        raise EvidenceError("qualified inspection traceability byte pin differs")
    trace = strict_json(content, TRACEABILITY_PATH)
    expected_top = {
        "$schema",
        "schema_version",
        "lot",
        "profile",
        "source_base_commit",
        "execution_environment",
        "entries",
    }
    if set(trace) != expected_top:
        raise EvidenceError("qualified inspection traceability fields differ")
    if (
        trace["$schema"] != "./qualified-ir-inspection-0.1-traceability.schema.json"
        or trace["schema_version"] != "1.0.0"
        or trace["lot"] != LOT
        or trace["profile"] != PROFILE
        or trace["source_base_commit"] != SOURCE_BASE_COMMIT
    ):
        raise EvidenceError("qualified inspection traceability identity differs")
    environment = trace["execution_environment"]
    if not isinstance(environment, dict) or set(environment) != {
        "os",
        "architecture",
        "compiler",
        "python",
        "commands",
    }:
        raise EvidenceError("traceability execution environment differs")
    if environment["architecture"] != "x86_64":
        raise EvidenceError("qualified inspection local architecture must be x86_64")
    commands = environment["commands"]
    if not isinstance(commands, list):
        raise EvidenceError("traceability commands must be an array")
    observed_commands: dict[str, str] = {}
    for command in commands:
        if not isinstance(command, dict) or set(command) != {
            "id",
            "command",
            "status",
            "result",
        }:
            raise EvidenceError("traceability command fields differ")
        identifier = command["id"]
        status_value = command["status"]
        if identifier in observed_commands or status_value not in STATUS_VALUES:
            raise EvidenceError("duplicate command or invalid evidence status")
        observed_commands[identifier] = status_value
    if observed_commands != EXPECTED_COMMAND_STATUSES:
        raise EvidenceError("traceability command inventory/statuses differ")

    entries = trace["entries"]
    if not isinstance(entries, list) or len(entries) != 3:
        raise EvidenceError("traceability must contain exactly three entries")
    python_ids = _python_test_ids(root)
    native_ids = _native_test_ids(root)
    available_test_ids = python_ids | native_ids
    observed_requirements: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "requirement_id",
            "claim",
            "status",
            "test_ids",
            "evidence",
            "reason",
            "blocking_scope",
        }:
            raise EvidenceError("traceability requirement fields differ")
        requirement = entry["requirement_id"]
        status_value = entry["status"]
        if requirement in observed_requirements or status_value not in STATUS_VALUES:
            raise EvidenceError("duplicate requirement or invalid requirement status")
        observed_requirements[requirement] = status_value
        if not isinstance(entry["test_ids"], list) or len(entry["test_ids"]) != len(
            set(entry["test_ids"])
        ):
            raise EvidenceError(f"duplicate test ID in {requirement}")
        missing_tests = set(entry["test_ids"]) - available_test_ids
        if missing_tests:
            raise EvidenceError(
                f"traceability references unknown tests for {requirement}: {sorted(missing_tests)}"
            )
        if not isinstance(entry["evidence"], list) or not entry["evidence"]:
            raise EvidenceError(f"traceability evidence is empty for {requirement}")
        for relative in entry["evidence"]:
            _path_parts(relative)
            if relative not in {MANIFEST_PATH, SBOM_PATH}:
                read_repository_file(root, relative)
    if observed_requirements != EXPECTED_REQUIREMENT_STATUSES:
        raise EvidenceError("qualified requirement statuses differ")
    if any(status == "PASS" for status in observed_requirements.values()) and any(
        observed_commands.get(identifier) != "PASS"
        for identifier in REQUIRED_PROMOTION_COMMANDS
    ):
        raise EvidenceError("requirement promotion precedes mandatory ADR-021 commands")
    return trace


def validate_profile(root: Path) -> dict[str, bytes]:
    validate_root(root)
    if len(ARTIFACT_SPECS) != len(set(ARTIFACT_SPECS)):
        raise EvidenceError("artifact inventory contains a duplicate path")
    for relative in EXPECTED_ABSENT_PATHS:
        if _path_exists_without_following(root, relative):
            raise EvidenceError(f"profile requires absent mutable historical path: {relative}")
    contents = {
        relative: read_repository_file(root, relative)
        for relative in sorted(ARTIFACT_SPECS)
    }
    _validate_units(root)
    _validate_exports(root)
    _validate_corpus(root)
    _validate_report_vectors(root)
    _validate_freeze(root)
    _validate_traceability(root)
    schema_ids = {
        MANIFEST_SCHEMA_PATH: "https://morphoia.org/schemas/engine/qualified-ir-inspection-0.1-artifact-manifest-1.0.schema.json",
        REPORT_VECTORS_SCHEMA_PATH: "https://morphoia.org/schemas/engine/qualified-ir-inspection-0.1-report-vectors-1.0.schema.json",
        TRACEABILITY_SCHEMA_PATH: "https://morphoia.org/schemas/engine/qualified-ir-inspection-0.1-traceability-1.0.schema.json",
    }
    for relative, expected_id in schema_ids.items():
        schema = strict_json(contents[relative], relative)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise EvidenceError(f"evidence schema is not Draft 2020-12: {relative}")
        if schema.get("$id") != expected_id:
            raise EvidenceError(f"evidence schema identifier differs: {relative}")
    return contents


def _artifact_record(relative: str, content: bytes, spec: ArtifactSpec) -> dict[str, Any]:
    return {
        "id": _artifact_id(relative),
        "kind": spec.kind,
        "path": relative,
        "media_type": spec.media_type,
        "size_bytes": len(content),
        "sha256": sha256_bytes(content),
        "license_expression": spec.license_expression,
        "source_artifact_id": None,
        "provenance": spec.provenance,
        "verification_status": "PASS",
        "vulnerability_analysis_status": "NOT_RUN",
    }


def build_sbom(contents: dict[str, bytes]) -> dict[str, Any]:
    root_ref = f"pkg:generic/morphoia-engine@{PROJECT_VERSION}?profile={PROFILE}"
    components: list[dict[str, Any]] = []
    dependencies: list[str] = []
    for relative in sorted(contents):
        spec = ARTIFACT_SPECS[relative]
        component_ref = f"urn:morphoia:qualified-ir:{_artifact_id(relative)}"
        dependencies.append(component_ref)
        components.append(
            {
                "type": "file",
                "bom-ref": component_ref,
                "name": relative,
                "version": sha256_bytes(contents[relative])[:12],
                "hashes": [{"alg": "SHA-256", "content": sha256_bytes(contents[relative])}],
                "licenses": [{"expression": spec.license_expression}],
                "properties": [
                    {"name": "morphoia:artifact-id", "value": _artifact_id(relative)},
                    {"name": "morphoia:path", "value": relative},
                    {"name": "morphoia:verification-status", "value": "PASS"},
                    {"name": "morphoia:vulnerability-analysis-status", "value": "NOT_RUN"},
                    {"name": "morphoia:dependency-license-review-status", "value": "NOT_RUN"},
                ],
            }
        )
    for (name, version), metadata in sorted(_parse_locks(contents).items()):
        package_ref = (
            f"pkg:pypi/{urllib.parse.quote(name, safe='')}@"
            f"{urllib.parse.quote(version, safe='')}"
        )
        dependencies.append(package_ref)
        components.append(
            {
                "type": "library",
                "bom-ref": package_ref,
                "name": name,
                "version": version,
                "purl": package_ref,
                "hashes": [
                    {"alg": "SHA-256", "content": digest}
                    for digest in sorted(metadata["hashes"])
                ],
                "properties": [
                    {
                        "name": "morphoia:declared-by-locks",
                        "value": ",".join(sorted(metadata["locks"])),
                    },
                    {"name": "morphoia:verification-status", "value": "PASS"},
                    {"name": "morphoia:vulnerability-analysis-status", "value": "NOT_RUN"},
                    {"name": "morphoia:dependency-license-review-status", "value": "NOT_RUN"},
                ],
            }
        )
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://morphoia.org/evidence/{LOT}/{SOURCE_BASE_COMMIT}",
    )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": "morphoia-engine",
                "version": PROJECT_VERSION,
                "licenses": [{"expression": "Apache-2.0 OR MIT"}],
                "properties": [
                    {"name": "morphoia:lot", "value": LOT},
                    {"name": "morphoia:profile", "value": PROFILE},
                    {"name": "morphoia:source-base-commit", "value": SOURCE_BASE_COMMIT},
                    {"name": "morphoia:sbom-content", "value": "closed-source-and-evidence-inventory"},
                    {"name": "morphoia:vulnerability-analysis-status", "value": "NOT_RUN"},
                    {"name": "morphoia:dependency-license-review-status", "value": "NOT_RUN"},
                ],
            }
        },
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": dependencies},
            *({"ref": reference, "dependsOn": []} for reference in dependencies),
        ],
    }


def build_manifest(contents: dict[str, bytes], sbom_bytes: bytes) -> dict[str, Any]:
    records = [
        _artifact_record(relative, contents[relative], ARTIFACT_SPECS[relative])
        for relative in sorted(contents)
    ]
    records.append(
        {
            "id": "qualified-ir-inspection-cyclonedx",
            "kind": "cyclonedx-sbom",
            "path": SBOM_PATH,
            "media_type": "application/vnd.cyclonedx+json",
            "size_bytes": len(sbom_bytes),
            "sha256": sha256_bytes(sbom_bytes),
            "license_expression": "CC-BY-4.0",
            "source_artifact_id": None,
            "provenance": "Deterministic CycloneDX 1.5 closed inventory; vulnerability analysis NOT_RUN.",
            "verification_status": "PASS",
            "vulnerability_analysis_status": "NOT_RUN",
            "note": "This inventory is neither a vulnerability assessment nor a third-party dependency license audit.",
        }
    )
    return {
        "schema_version": "1.0.0",
        "project": "Morphoia Engine",
        "lot": LOT,
        "profile": PROFILE,
        "generated_at": GENERATED_AT,
        "manifest_document_license": "CC-BY-4.0",
        "hash_algorithm": "sha256",
        "source_base_commit": SOURCE_BASE_COMMIT,
        "artifacts": records,
    }


def generate(root: Path) -> tuple[bytes, bytes]:
    contents = validate_profile(root)
    sbom_bytes = deterministic_json(build_sbom(contents))
    manifest_bytes = deterministic_json(build_manifest(contents, sbom_bytes))
    strict_json(sbom_bytes, SBOM_PATH)
    strict_json(manifest_bytes, MANIFEST_PATH)
    return manifest_bytes, sbom_bytes


def _renameat2(
    old_directory: int,
    old_name: str,
    new_directory: int,
    new_name: str,
    flags: int,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is None:
        raise EvidenceError("Linux renameat2 is required for atomic evidence publication")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    result = function(
        old_directory,
        os.fsencode(old_name),
        new_directory,
        os.fsencode(new_name),
        flags,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _file_fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_regular_at(parent: int, name: str) -> tuple[bytes, tuple[int, ...]]:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent,
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 <= before.st_size <= MAX_INPUT_BYTES
        ):
            raise EvidenceError("evidence output has an unsafe type, link count, or size")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise EvidenceError("evidence output changed during snapshot")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise EvidenceError("evidence output grew during snapshot")
        after = os.fstat(descriptor)
        identity = _file_fingerprint(before)
        if _file_fingerprint(after) != identity:
            raise EvidenceError("evidence output changed during snapshot")
        return b"".join(chunks), identity
    finally:
        os.close(descriptor)


def _verify_published(parent: int, name: str, content: bytes) -> None:
    observed, _ = _read_regular_at(parent, name)
    if observed != content:
        raise EvidenceError("published evidence bytes differ")


def atomic_write(root: Path, relative: str, content: bytes) -> None:
    parent, target = _open_parent(root, relative)
    descriptor = -1
    temporary: str | None = None
    try:
        try:
            original_content, original_identity = _read_regular_at(parent, target)
        except FileNotFoundError:
            original_content = None
            original_identity = None
        except (OSError, EvidenceError) as error:
            raise EvidenceError(f"generated output is unsafe: {relative}") from error
        for _ in range(100):
            candidate = f".{target}.{secrets.token_hex(16)}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent,
                )
            except FileExistsError:
                continue
            temporary = candidate
            break
        if descriptor < 0 or temporary is None:
            raise EvidenceError(f"cannot allocate atomic output for {relative}")
        os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise EvidenceError(f"short write while publishing {relative}")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1

        try:
            current_content, current_identity = _read_regular_at(parent, target)
        except FileNotFoundError:
            current_content = None
            current_identity = None
        except (OSError, EvidenceError) as error:
            raise EvidenceError(f"generated output changed to an unsafe type: {relative}") from error
        if current_identity != original_identity or current_content != original_content:
            raise EvidenceError(f"generated output changed during write: {relative}")

        if original_identity is None:
            try:
                _renameat2(parent, temporary, parent, target, RENAME_NOREPLACE)
            except OSError as error:
                if error.errno == errno.EEXIST:
                    raise EvidenceError(f"evidence target appeared during publication: {relative}") from error
                raise
            temporary = None
            _verify_published(parent, target, content)
        else:
            _renameat2(parent, temporary, parent, target, RENAME_EXCHANGE)
            try:
                exchanged_content, exchanged_identity = _read_regular_at(parent, temporary)
            except (OSError, EvidenceError):
                try:
                    _renameat2(parent, temporary, parent, target, RENAME_EXCHANGE)
                except OSError as restore_error:
                    raise EvidenceError(f"cannot restore raced output: {relative}") from restore_error
                raise
            # Linux rename updates ctime. Bytes plus every stable fingerprint
            # field catch in-place mutation, inode replacement, and aliases.
            if (
                exchanged_identity[:-1] != original_identity[:-1]
                or exchanged_content != original_content
            ):
                try:
                    _renameat2(parent, temporary, parent, target, RENAME_EXCHANGE)
                except OSError as restore_error:
                    raise EvidenceError(f"cannot restore raced output: {relative}") from restore_error
                raise EvidenceError(f"evidence target changed during publication: {relative}")
            try:
                _verify_published(parent, target, content)
            except (OSError, EvidenceError):
                try:
                    _renameat2(parent, temporary, parent, target, RENAME_EXCHANGE)
                except OSError as restore_error:
                    raise EvidenceError(f"cannot restore unverified output: {relative}") from restore_error
                raise
            os.unlink(temporary, dir_fd=parent)
            temporary = None
        os.fsync(parent)
    except OSError as error:
        raise EvidenceError(f"atomic evidence publication failed for {relative}: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def check_output(root: Path, relative: str, expected: bytes) -> None:
    observed = read_repository_file(root, relative)
    if observed != expected:
        raise EvidenceError(
            f"generated evidence differs: {relative}; regenerate without --check"
        )
    strict_json(observed, relative)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        root = validate_root(arguments.root.resolve(strict=True))
        manifest_bytes, sbom_bytes = generate(root)
        if arguments.check:
            check_output(root, MANIFEST_PATH, manifest_bytes)
            check_output(root, SBOM_PATH, sbom_bytes)
        else:
            atomic_write(root, SBOM_PATH, sbom_bytes)
            atomic_write(root, MANIFEST_PATH, manifest_bytes)
            check_output(root, SBOM_PATH, sbom_bytes)
            check_output(root, MANIFEST_PATH, manifest_bytes)
    except (EvidenceError, OSError, ValueError, TypeError) as error:
        print(f"qualified-ir-inspection-evidence: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "qualified-ir-inspection-evidence: PASS "
        f"({len(ARTIFACT_SPECS) + 1} artifacts, 10 units, 8 exports, "
        "20 reports x2; vulnerability analysis NOT_RUN)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
