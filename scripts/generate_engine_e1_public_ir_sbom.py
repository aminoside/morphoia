#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Generate and verify the bounded E1 public-IR manifest and CycloneDX SBOM.

This profile inventories only an explicit allowlist.  It verifies artifact
bytes and provenance without treating inventory generation as a vulnerability
assessment or as evidence for an unexecuted backend.
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
import stat
import sys
import urllib.parse
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple, NoReturn

PROFILE = "e1-public-ir-core-cpu"
PROJECT_VERSION = "0.0.1"
SOURCE_BASE_COMMIT = "c475288961d40bb16c4cc10a333034a247acb451"
GENERATED_AT = "2026-08-12"
MANIFEST_PATH = "artifacts/manifests/engine-e1-public-ir.json"
OUTPUT_PATH = "artifacts/sbom/engine-e1-public-ir.cdx.json"
TRACEABILITY_PATH = "spec/evidence/e1-public-ir-traceability.json"
SELF_ARTIFACT_ID = "sbom-engine-e1-public-ir"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_INPUT_BYTES = 64 * 1024 * 1024
STATUS_VALUES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"}
EXECUTION_COMMAND_IDS = (
    "public-ir-lot",
    "direct-bootstrap",
    "sanitizers",
    "clean-cmake-builds",
    "wheel-smoke",
    "frozen-evidence",
    "hygiene",
    "evidence-profile",
    "corrective-hosted-engine",
    "corrective-hosted-report",
    "python-3-13",
    "final-evidence-head-hosted",
    "public-ir-integration-postmerge",
    "vulnerability-analysis",
)
INTEGRATION_COMMAND = (
    "PR #8 integrated evidence head 74b8ddb60ddd8257166b4547c1222a17f47884c6 "
    "into engine at merge 9c845f9ea4586a65f25985a4d1f92ebdf407a2f4, tree "
    "ad816e3c1fbeb9959d82bc47e27c2fc68af49fe0, parents "
    "12656708ccc3031670c4b3efd43996e46fa27998 and "
    "74b8ddb60ddd8257166b4547c1222a17f47884c6; GitHub Actions exact-merge "
    "Engine run 31615797169 executed the integrated tree"
)
FINAL_EVIDENCE_HEAD_COMMAND = (
    "GitHub Actions exact-head push Engine run 31615539072 and PR Engine run "
    "31615542865 for evidence head 74b8ddb60ddd8257166b4547c1222a17f47884c6; "
    "PR report run 31615542750 also evaluated that PR head"
)
FINAL_EVIDENCE_HEAD_RESULT = (
    "Push jobs Python 3.12 94177289278, REUSE 94177289283, native 94177289284, "
    "Python 3.13 94177289377, and hygiene 94177289508 passed. PR jobs Python "
    "3.12 94177302576, native 94177302606, hygiene 94177302631, Python 3.13 "
    "94177302636, and REUSE 94177302725 passed. PR report job 94177301425 passed."
)
INTEGRATION_RESULT = (
    "Hygiene job 94178151865, REUSE job 94178151884, Python 3.13 job "
    "94178151890, Python 3.12 job 94178151961, and native job 94178151978 "
    "passed. The merge tree equals the evidence-head tree, and main remained "
    "at 66b26f2f6dbccac6a132c8ebc72652e37fcf27b9."
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,127}$")
REQUIREMENT_RE = re.compile(r"^MOR-[A-Z]+-[0-9]{3}$")
TEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$")
PACKAGE_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\?$")
HASH_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})(?:\s*\\)?$")
CMAKE_ADD_TEST_RE = re.compile(
    r"\badd_test\s*\(\s*NAME\s+([A-Za-z0-9][A-Za-z0-9_.-]{0,255})\b",
    re.MULTILINE,
)
RENAME_NOREPLACE = 1
RENAME_EXCHANGE = 2

LOCK_FILES = (
    "requirements/engine-ci.lock",
    "requirements/wheel-build-e1.lock",
)
LICENSE_FILES = {
    "LICENSE": "MIT",
    "LICENSE-APACHE": "Apache-2.0",
    "LICENSE-MIT": "MIT",
    "LICENSES/Apache-2.0.txt": "Apache-2.0",
    "LICENSES/CC-BY-4.0.txt": "CC-BY-4.0",
    "LICENSES/MIT.txt": "MIT",
    "NOTICE": "CC-BY-4.0",
}


class ArtifactSpec(NamedTuple):
    identifier: str
    kind: str
    media_type: str
    license_expression: str
    source_artifact_id: str | None
    provenance: str
    note: str | None = None


# Filled as a literal closed set below. Directory discovery and globs are
# intentionally prohibited because later lots must not change this profile.
ARTIFACT_SPECS: dict[str, ArtifactSpec] = {}

EXPECTED_FIXTURE_PATHS = (
    "tests/fixtures/engine-ir/0.1.0/DATA_CARD.md",
    *(
        f"tests/fixtures/engine-ir/0.1.0/goldens/graph-{number:02d}-{slug}.content.cjson"
        for number, slug in (
            (1, "brep-source"),
            (2, "points-source"),
            (3, "voxel-source"),
            (4, "transform"),
            (5, "derived-mesh"),
            (6, "field-derived"),
            (7, "scene-derived"),
            (8, "tensor-derived"),
            (9, "ai-candidate"),
            (10, "fidelity-loss"),
            (11, "assembly"),
            (12, "instances"),
            (13, "topology-unstable"),
            (14, "tolerance"),
            (15, "repair"),
            (16, "multiple-units"),
            (17, "two-frames"),
            (18, "provenance-chain"),
            (19, "reverse-dns-extension"),
            (20, "revision-parent"),
        )
    ),
    "tests/fixtures/engine-ir/0.1.0/index.json",
    *(
        f"tests/fixtures/engine-ir/0.1.0/inputs/graph-{number:02d}-{slug}.json"
        for number, slug in (
            (1, "brep-source"),
            (2, "points-source"),
            (3, "voxel-source"),
            (4, "transform"),
            (5, "derived-mesh"),
            (6, "field-derived"),
            (7, "scene-derived"),
            (8, "tensor-derived"),
            (9, "ai-candidate"),
            (10, "fidelity-loss"),
            (11, "assembly"),
            (12, "instances"),
            (13, "topology-unstable"),
            (14, "tolerance"),
            (15, "repair"),
            (16, "multiple-units"),
            (17, "two-frames"),
            (18, "provenance-chain"),
            (19, "reverse-dns-extension"),
            (20, "revision-parent"),
        )
    ),
    *(
        f"tests/fixtures/engine-ir/0.1.0/invalid/{name}.json"
        for name in (
            "duplicate-id",
            "duplicate-key",
            "fraction",
            "index",
            "inline-payload",
            "invalid-extension",
            "lone-surrogate",
            "source-offset-time",
            "unknown-core",
            "unknown-frame-unit",
            "uppercase-uuid",
            "uri-digest-mismatch",
            "verified-self-claim",
            "zero-axis",
        )
    ),
    *(
        f"tests/fixtures/engine-ir/0.1.0/migration/{name}"
        for name in (
            "expected-content.json",
            "legacy-input.json",
            "metadata.json",
        )
    ),
    *(
        f"tests/fixtures/engine-ir/0.1.0/replays/graph-{number:02d}-{slug}.replay.json"
        for number, slug in (
            (1, "brep-source"),
            (2, "points-source"),
            (3, "voxel-source"),
            (4, "transform"),
            (5, "derived-mesh"),
            (6, "field-derived"),
            (7, "scene-derived"),
            (8, "tensor-derived"),
            (9, "ai-candidate"),
            (10, "fidelity-loss"),
            (11, "assembly"),
            (12, "instances"),
            (13, "topology-unstable"),
            (14, "tolerance"),
            (15, "repair"),
            (16, "multiple-units"),
            (17, "two-frames"),
            (18, "provenance-chain"),
            (19, "reverse-dns-extension"),
            (20, "revision-parent"),
        )
    ),
)

PUBLIC_IR_OWNED_SPECS: dict[str, ArtifactSpec] = {
    "spec/adr/ADR-020-public-engine-ir-v0.1.md": ArtifactSpec(
        "adr-020-public-engine-ir", "architecture-decision-record", "text/markdown",
        "CC-BY-4.0", None,
        "Accepted public Engine IR 0.1 identity-domain decision with exact integration evidence.",
    ),
    "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json": ArtifactSpec(
        "engine-ir-manifest-schema-0.1.0", "ir-schema", "application/schema+json",
        "Apache-2.0 OR MIT", "adr-020-public-engine-ir",
        "Closed Draft 2020-12 public Engine IR manifest schema.",
    ),
    "schemas/morphoia-engine-ir-replay-0.1.0.schema.json": ArtifactSpec(
        "engine-ir-replay-schema-0.1.0", "ir-schema", "application/schema+json",
        "Apache-2.0 OR MIT", "adr-020-public-engine-ir",
        "Closed Draft 2020-12 deterministic replay schema.",
    ),
    "src/morphoia/engine_ir_contract.py": ArtifactSpec(
        "engine-ir-contract", "contract-implementation", "text/x-python",
        "Apache-2.0 OR MIT", "engine-ir-manifest-schema-0.1.0",
        "Strict lexical, schema, and semantic validation implementation.",
    ),
    "src/morphoia/engine_ir_migration.py": ArtifactSpec(
        "engine-ir-migration", "migration-implementation", "text/x-python",
        "Apache-2.0 OR MIT", "engine-ir-contract",
        "Explicit unsealed legacy-domain migration implementation.",
    ),
    "src/morphoia/_engine_native.py": ArtifactSpec(
        "engine-native-binding", "python-binding", "text/x-python",
        "Apache-2.0 OR MIT", "engine-c-abi-header",
        "Required-native ctypes binding with no authoritative Python fallback.",
    ),
    "src/morphoia/engine_ir.py": ArtifactSpec(
        "engine-ir-python-api", "python-api", "text/x-python",
        "Apache-2.0 OR MIT", "engine-native-binding",
        "Reference Python validation, sealing, migration, resolver, and replay API.",
    ),
    "src/morphoia/cli.py": ArtifactSpec(
        "engine-ir-cli", "cli-implementation", "text/x-python",
        "MIT", "engine-ir-python-api",
        "Human and machine-readable public Engine IR CLI commands.",
    ),
    "src/morphoia/__init__.py": ArtifactSpec(
        "engine-ir-package-api", "python-api", "text/x-python", "MIT",
        "engine-ir-python-api", "Package exports for the public Engine IR Python API.",
    ),
    "pyproject.toml": ArtifactSpec(
        "python-project-metadata", "package-metadata", "application/toml",
        "MIT", "engine-ir-package-api",
        "Python 3.12/3.13 package metadata and dependency declaration.",
    ),
    "cpp/include/morphoia/engine.h": ArtifactSpec(
        "engine-c-abi-header", "c-abi", "text/x-c",
        "Apache-2.0 OR MIT", "adr-020-public-engine-ir",
        "Versioned public C11 ABI declarations for capability query and canonicalization.",
    ),
    "cpp/src/engine.cpp": ArtifactSpec(
        "engine-c-abi-implementation", "c-abi", "text/x-c++src",
        "Apache-2.0 OR MIT", "engine-c-abi-header",
        "C++20 implementation of the bounded public C ABI.",
    ),
    "cmake/morphoia_engine.map": ArtifactSpec(
        "engine-export-map", "build-contract", "text/plain",
        "Apache-2.0 OR MIT", "engine-c-abi-header",
        "Exact seven-symbol Linux public export allowlist.",
    ),
    "CMakeLists.txt": ArtifactSpec(
        "engine-cmake-build", "build-contract", "text/x-cmake",
        "Apache-2.0 OR MIT", "engine-export-map",
        "Strict C++20/C11 build, install, and native public-IR tests.",
    ),
    "scripts/bootstrap-engine.sh": ArtifactSpec(
        "engine-bootstrap", "validation-script", "text/x-shellscript",
        "Apache-2.0 OR MIT", "engine-cmake-build",
        "Direct compiler bootstrap and exact export verification.",
    ),
    "scripts/run-engine-sanitizers.sh": ArtifactSpec(
        "engine-sanitizer-runner", "validation-script", "text/x-shellscript",
        "Apache-2.0 OR MIT", "engine-cmake-build",
        "Bounded AddressSanitizer and fail-fast UndefinedBehaviorSanitizer execution.",
    ),
    "scripts/validate_engine_ir_corpus.py": ArtifactSpec(
        "engine-ir-corpus-validator", "validation-script", "text/x-python",
        "Apache-2.0 OR MIT", "engine-ir-python-api",
        "Native execution and checkpoint replay validator for exactly 20 graphs.",
    ),
    "scripts/validate-engine-ir-lot.sh": ArtifactSpec(
        "engine-ir-lot-runner", "validation-script", "text/x-shellscript",
        "Apache-2.0 OR MIT", "engine-ir-corpus-validator",
        "Bounded native and Python public-IR lot runner.",
    ),
    "scripts/validate-engine-wheel.sh": ArtifactSpec(
        "engine-ir-wheel-validator", "validation-script", "text/x-shellscript",
        "Apache-2.0 OR MIT", "python-project-metadata",
        "Isolated installed-wheel smoke with exact hash-locked Python build dependencies.",
        "Byte-for-byte distribution reproducibility remains NOT_RUN.",
    ),
    "tests/native/canonical_json_c_api_test.c": ArtifactSpec(
        "canonical-json-c-api-test", "native-test", "text/x-c",
        "Apache-2.0 OR MIT", "engine-c-abi-implementation",
        "C11 capability, limits, diagnostic, buffer, and digest test.",
    ),
    "tests/native/ir_replay_test.cpp": ArtifactSpec(
        "native-ir-replay-test", "native-test", "text/x-c++src",
        "Apache-2.0 OR MIT", "engine-cmake-build",
        "Twenty-golden replay through two verified POSIX CAS roots.",
    ),
    "tests/native/consumer/CMakeLists.txt": ArtifactSpec(
        "installed-consumer-build", "build-contract", "text/x-cmake",
        "Apache-2.0 OR MIT", "engine-cmake-build",
        "External installed-package C11 consumer build and CTest registration.",
    ),
    "tests/native/consumer/main.c": ArtifactSpec(
        "installed-c-consumer", "native-test", "text/x-c",
        "Apache-2.0 OR MIT", "installed-consumer-build",
        "Installed external C consumer of capability and canonicalization exports.",
    ),
    "tests/test_engine_ir_contract.py": ArtifactSpec(
        "engine-ir-contract-tests", "python-test", "text/x-python",
        "Apache-2.0 OR MIT", "engine-ir-contract",
        "Lexical, schema, semantic, invalid, and 20-graph corpus tests.",
    ),
    "tests/test_engine_ir_migration.py": ArtifactSpec(
        "engine-ir-migration-tests", "python-test", "text/x-python",
        "Apache-2.0 OR MIT", "engine-ir-migration",
        "Explicit migration mutation and legacy-byte preservation tests.",
    ),
    "tests/test_engine_ir_native.py": ArtifactSpec(
        "engine-ir-native-binding-tests", "python-test", "text/x-python",
        "Apache-2.0 OR MIT", "engine-native-binding",
        "Required-native binding, lifetime, diagnostic, and concurrency tests.",
    ),
    "tests/test_engine_ir_replay.py": ArtifactSpec(
        "engine-ir-replay-tests", "python-test", "text/x-python",
        "Apache-2.0 OR MIT", "engine-ir-python-api",
        "Native agreement, resolver, checkpoint, timeout, cancellation, and migration tests.",
    ),
    "tests/test_engine_ir_cli.py": ArtifactSpec(
        "engine-ir-cli-tests", "python-test", "text/x-python",
        "Apache-2.0 OR MIT", "engine-ir-cli",
        "Human, JSON, stable-exit, replay, checkpoint, timeout, and cancellation CLI tests.",
    ),
    "docs/engine/IR_MANIFEST_0_1.md": ArtifactSpec(
        "engine-ir-guide", "documentation", "text/markdown",
        "CC-BY-4.0", "adr-020-public-engine-ir",
        "Public Engine IR 0.1 contract and thread-safety guide.",
    ),
    "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md": ArtifactSpec(
        "e1-public-ir-report", "evidence-report", "text/markdown",
        "CC-BY-4.0", "e1-public-ir-traceability",
        "Bounded public-IR gate report and truth boundary.",
    ),
    "spec/evidence/e1-public-ir-traceability.schema.json": ArtifactSpec(
        "e1-public-ir-traceability-schema", "evidence-schema", "application/schema+json",
        "Apache-2.0 OR MIT", "e1-public-ir-artifact-manifest-schema",
        "Closed traceability schema with honest status vocabulary.",
    ),
    "spec/evidence/e1-public-ir-traceability.json": ArtifactSpec(
        "e1-public-ir-traceability", "traceability", "application/json",
        "CC-BY-4.0", "e1-public-ir-traceability-schema",
        "Exact requirement-to-test-to-evidence mapping.",
    ),
    "spec/evidence/e1-public-ir-artifact-manifest.schema.json": ArtifactSpec(
        "e1-public-ir-artifact-manifest-schema", "evidence-schema",
        "application/schema+json", "Apache-2.0 OR MIT", "adr-020-public-engine-ir",
        "Closed schema for the bounded public-IR artifact manifest.",
    ),
    "scripts/generate_engine_e1_public_ir_sbom.py": ArtifactSpec(
        "e1-public-ir-evidence-generator", "evidence-generator", "text/x-python",
        "Apache-2.0 OR MIT", "e1-public-ir-artifact-manifest-schema",
        "Deterministic fail-closed manifest and CycloneDX generator.",
    ),
    "tests/test_e1_public_ir_evidence.py": ArtifactSpec(
        "e1-public-ir-evidence-tests", "evidence-test", "text/x-python",
        "Apache-2.0 OR MIT", "e1-public-ir-evidence-generator",
        "Closed-profile, mutation, confinement, and atomic-publication evidence tests.",
    ),
    ".github/workflows/engine-ci.yml": ArtifactSpec(
        "engine-core-cpu-workflow", "ci-workflow", "application/yaml",
        "Apache-2.0 OR MIT", "engine-ir-lot-runner",
        "Pinned-action hosted core-CPU matrix and public-IR lot execution.",
    ),
    "REUSE.toml": ArtifactSpec(
        "reuse-annotations", "license-metadata", "application/toml",
        "CC-BY-4.0", "engine-core-cpu-workflow",
        "Per-path SPDX copyright and license annotations for the bounded lot.",
    ),
    "spec/requirements/requirements-tracking.yaml": ArtifactSpec(
        "requirements-tracking", "requirements-traceability", "application/json",
        "CC-BY-4.0", None,
        "Byte-frozen E0 all-NOT_RUN global overlay pending separate change control.",
        "The 33 PASS and 16 NOT_RUN public-IR mappings live only in the profile-specific traceability file.",
    ),
    "CHANGELOG.md": ArtifactSpec(
        "project-changelog", "release-documentation", "text/markdown",
        "MIT", "e1-public-ir-report",
        "Unreleased public-IR lot summary without premature release claims.",
    ),
}

FROZEN_E1_SPECS = {
    "scripts/validate_engine_e1_native_evidence.py": ArtifactSpec(
        "frozen-e1-native-validator", "evidence-validator", "text/x-python",
        "Apache-2.0 OR MIT", None,
        "Byte-exact fail-closed validator for integrated E1 native evidence.",
    ),
    "docs/engine/evidence/E1_NATIVE_CORE_REPORT.md": ArtifactSpec(
        "frozen-e1-native-report", "evidence-report", "text/markdown",
        "CC-BY-4.0", "frozen-e1-native-validator",
        "Integrated native Profile 1 and POSIX CAS execution report.",
    ),
    "artifacts/e1/manifest.json": ArtifactSpec(
        "frozen-e1-native-manifest", "artifact-manifest", "application/json",
        "CC-BY-4.0", "frozen-e1-native-validator",
        "Byte-frozen E1 native artifact manifest.",
    ),
    "artifacts/sbom/engine-e1-native-core.cdx.json": ArtifactSpec(
        "frozen-e1-native-sbom", "cyclonedx-sbom", "application/vnd.cyclonedx+json",
        "CC-BY-4.0", "frozen-e1-native-manifest",
        "Byte-frozen E1 native CycloneDX inventory; vulnerability analysis remains NOT_RUN.",
    ),
}

FROZEN_E1_DIGESTS = {
    "scripts/validate_engine_e1_native_evidence.py":
        "c410050aa462eaf597ede5d20ebd15a75a359f74dd0fb017dcd6b1cf27c0498e",
    "docs/engine/evidence/E1_NATIVE_CORE_REPORT.md":
        "6f98f5c1f6045f2df983471531ed936652266566f04d09d28b834bf64521b964",
    "artifacts/e1/manifest.json":
        "2fee29f645651dafbeafa5d240e9148cad12334f1eac0045d5c27fb7ddee273b",
    "artifacts/sbom/engine-e1-native-core.cdx.json":
        "e098c130a535bb0a0f8d92f89c76015051d9296e3228475bfee5cc1afa214176",
}

# E0 tests and the frozen E0 artifact manifest define this global overlay as a
# fail-closed all-NOT_RUN baseline. Public-IR promotions are therefore confined
# to TRACEABILITY_PATH until a separate change control makes the global overlay
# safely evolvable and updates its frozen consumers together.
FROZEN_REQUIREMENTS_TRACKING_DIGEST = (
    "7af677456e74f0fece87dbbae7db3637892ab1c24271dcc4603df2633e57dec4"
)


def fixture_spec(relative: str) -> ArtifactSpec:
    filename = PurePosixPath(relative).name
    if relative.endswith("DATA_CARD.md"):
        kind, media_type = "data-card", "text/markdown"
        identifier = "engine-ir-corpus-data-card"
        source = "adr-020-public-engine-ir"
    elif "/goldens/" in relative:
        kind, media_type = "canonical-golden", "application/json"
        identifier = f"engine-ir-golden-{filename.removesuffix('.content.cjson')}"
        source = "engine-ir-corpus-index"
    elif "/inputs/" in relative:
        kind, media_type = "ir-fixture", "application/json"
        identifier = f"engine-ir-input-{filename.removesuffix('.json')}"
        source = "engine-ir-corpus-index"
    elif "/replays/" in relative:
        kind, media_type = "replay-fixture", "application/json"
        identifier = f"engine-ir-replay-{filename.removesuffix('.replay.json')}"
        source = "engine-ir-corpus-index"
    elif "/invalid/" in relative:
        kind, media_type = "invalid-fixture", "application/json"
        identifier = f"engine-ir-invalid-{filename.removesuffix('.json')}"
        source = "engine-ir-corpus-data-card"
    elif "/migration/" in relative:
        kind, media_type = "migration-fixture", "application/json"
        identifier = f"engine-ir-migration-{filename.removesuffix('.json')}"
        source = "engine-ir-corpus-data-card"
    else:
        kind, media_type = "corpus-index", "application/json"
        identifier = "engine-ir-corpus-index"
        source = "engine-ir-corpus-data-card"
    return ArtifactSpec(
        identifier, kind, media_type, "CC-BY-4.0", source,
        "Synthetic public Engine IR 0.1 fixture recorded by the corpus data card.",
        "Synthetic metadata and invented payload references only; no payload import is claimed.",
    )


ARTIFACT_SPECS.update(PUBLIC_IR_OWNED_SPECS)
ARTIFACT_SPECS.update(FROZEN_E1_SPECS)
ARTIFACT_SPECS.update({relative: fixture_spec(relative) for relative in EXPECTED_FIXTURE_PATHS})


def verify_fixture_allowlist(root: Path) -> None:
    """Reject missing, extra, aliased, or unlicensed public-IR fixture files."""

    expected = tuple(sorted(EXPECTED_FIXTURE_PATHS))
    fixture_root = root / "tests" / "fixtures" / "engine-ir" / "0.1.0"
    discovered = tuple(fixture_root.rglob("*"))
    aliases = sorted(
        path.relative_to(root).as_posix()
        for path in discovered
        if path.is_symlink()
    )
    if aliases:
        raise ValueError(f"public-IR fixture tree contains symlink aliases: {aliases}")
    actual = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in discovered
            if path.is_file()
        )
    )
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(
            f"public-IR fixture allowlist differs; missing={missing}, extra={extra}"
        )
    for relative in expected:
        if relative not in ARTIFACT_SPECS:
            raise ValueError(f"public-IR fixture is absent from artifact allowlist: {relative}")
        if ARTIFACT_SPECS[relative].license_expression != "CC-BY-4.0":
            raise ValueError(f"public-IR fixture license is not CC-BY-4.0: {relative}")
        read_repository_file(root, relative)

SELF_SPEC = ArtifactSpec(
    SELF_ARTIFACT_ID,
    "cyclonedx-sbom",
    "application/vnd.cyclonedx+json",
    "CC-BY-4.0",
    "e1-public-ir-evidence-generator",
    "Deterministic CycloneDX 1.5 inventory generated from the closed public-IR profile.",
    "Inventory only; vulnerability analysis, optional backends, and MVX remain NOT_RUN.",
)

TRACEABILITY_ORDER = (
    *(f"MOR-IR-{number:03d}" for number in range(1, 19)),
    *(f"MOR-API-{number:03d}" for number in (2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18)),
    *(f"MOR-DEV-{number:03d}" for number in (1, 2, 3, 5, 8, 9, 10, 11, 12, 14)),
    *(f"MOR-CAS-{number:03d}" for number in (1, 3, 4, 6, 8, 10, 12)),
    "MOR-QA-013",
)
TRACEABILITY_REQUIREMENTS = set(TRACEABILITY_ORDER)

TRACEABILITY_TESTS: dict[str, tuple[str, ...]] = {
    "MOR-IR-001": ("test_schema_identifiers_constants_and_integer_domain_are_frozen",),
    "MOR-IR-002": (
        "native.canonical_json_c_api",
        "test_profile1_two_pass_bytes_and_digest_agree",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-003": (
        "test_identity_is_only_verified_against_native_result",
        "test_linear_revision_and_nonnegative_tolerance_are_explicit",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-004": (
        "test_committed_invalid_fixtures_are_rejected_by_declared_stage",
        "test_exactly_twenty_synthetic_inputs_have_indexed_hashes_and_lf_free_goldens",
    ),
    "MOR-IR-005": (
        "test_digest_uri_ids_and_references_are_consistent",
        "test_resolver_rejects_mismatch_before_returning_bytes",
    ),
    "MOR-IR-006": ("test_dimensions_transforms_and_timestamps_are_explicit",),
    "MOR-IR-007": (
        "test_dimensions_transforms_and_timestamps_are_explicit",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-008": ("test_dimensions_transforms_and_timestamps_are_explicit",),
    "MOR-IR-009": (
        "test_spdx_expression_and_invalid_signature_evidence_rules",
        "test_dimensions_transforms_and_timestamps_are_explicit",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-010": (
        "test_provenance_and_product_cycles_are_rejected",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-011": (
        "test_closed_schema_rejects_unknown_core_inline_payload_and_unsafe_integer",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-012": (
        "test_authority_derivation_ai_and_provenance_invariants",
        "test_provenance_inputs_define_exact_acyclic_time_ordered_parents",
        "test_provenance_and_product_cycles_are_rejected",
    ),
    "MOR-IR-013": (
        "test_schema_identifiers_constants_and_integer_domain_are_frozen",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-014": (
        "test_spdx_expression_and_invalid_signature_evidence_rules",
        "test_verified_signature_self_claim_is_rejected_without_crypto_result",
    ),
    "MOR-IR-015": (
        "test_closed_schema_rejects_unknown_core_inline_payload_and_unsafe_integer",
        "test_committed_invalid_fixtures_are_rejected_by_declared_stage",
    ),
    "MOR-IR-016": (
        "test_schema_identifiers_constants_and_integer_domain_are_frozen",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-017": (
        "test_authority_derivation_ai_and_provenance_invariants",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-IR-018": (
        "test_loader_accepts_native_depth_boundary_and_rejects_one_more_container",
        "test_committed_invalid_fixtures_are_rejected_by_declared_stage",
        "test_explicit_migration_matches_golden_and_preserves_input_bytes",
        "test_public_migration_natively_seals_and_keeps_legacy_bytes",
    ),
    "MOR-API-002": ("native.abi_c_smoke", "native.canonical_json_c_api"),
    "MOR-API-003": (
        "native.canonical_json_c_api",
        "test_explicit_length_diagnostic_decoder_preserves_utf8_and_nul",
    ),
    "MOR-API-006": ("test_wrapper_serializes_context_lifetime_across_threads",),
    "MOR-API-007": (
        "native.canonical_json_c_api",
        "test_native_invalid_json_exposes_structured_diagnostic",
    ),
    "MOR-API-008": (
        "native.canonical_json_c_api",
        "test_explicit_library_negotiates_exact_capability",
    ),
    "MOR-API-009": ("test_context_manager_closes_deterministically",),
    "MOR-API-010": (
        "test_validate_json_and_human_output_are_stable",
        "test_invalid_manifest_and_missing_native_library_return_one",
    ),
    "MOR-API-011": ("test_timeout_and_cancellation_are_bounded",),
    "MOR-API-012": (
        "test_operation_key_tracks_python_and_native_implementation",
        "test_replay_executes_then_resumes_exact_checkpoint",
    ),
    "MOR-API-013": (
        "test_dimensions_transforms_and_timestamps_are_explicit",
        "test_timeout_and_cancellation_are_bounded",
    ),
    "MOR-API-014": (
        "test_schema_identifiers_constants_and_integer_domain_are_frozen",
        "test_explicit_library_negotiates_exact_capability",
    ),
    "MOR-API-015": (
        "test_explicit_migration_matches_golden_and_preserves_input_bytes",
        "test_public_migration_natively_seals_and_keeps_legacy_bytes",
    ),
    "MOR-API-018": ("test_extension_namespace_preserves_internal_core_homonyms",),
    "MOR-DEV-001": ("native.canonical_json", "native.ir_replay"),
    "MOR-DEV-002": (
        "native.abi_c_smoke",
        "native.canonical_json_c_api",
        "installed.c_consumer",
    ),
    "MOR-DEV-003": (
        "test_explicit_library_negotiates_exact_capability",
        "test_validate_json_and_human_output_are_stable",
    ),
    "MOR-DEV-005": (
        "native.abi_c_smoke",
        "native.ir_replay",
        "installed.c_consumer",
    ),
    "MOR-DEV-008": ("native.canonical_json_c_api", "native.ir_replay"),
    "MOR-DEV-009": ("native.core_smoke", "native.canonical_json_c_api"),
    "MOR-DEV-010": ("native.core_smoke",),
    "MOR-DEV-011": (
        "test_committed_invalid_fixtures_are_rejected_by_declared_stage",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
    ),
    "MOR-DEV-012": ("test_committed_outputs_are_deterministic_and_cli_verified",),
    "MOR-DEV-014": ("test_fixture_tree_is_exactly_79_cc_by_files_with_13_invalid_cases",),
    "MOR-CAS-001": ("native.sha256", "native.posix_cas", "native.ir_replay"),
    "MOR-CAS-003": (
        "native.posix_cas",
        "test_checkpoint_no_clobber_handles_identical_and_different_writers",
    ),
    "MOR-CAS-004": ("native.posix_cas",),
    "MOR-CAS-006": ("native.ir_replay",),
    "MOR-CAS-008": (
        "native.posix_cas",
        "test_resolver_rejects_mismatch_before_returning_bytes",
    ),
    "MOR-CAS-010": (
        "test_resolver_rejects_symlink_components_final_alias_and_hardlink",
    ),
    "MOR-CAS-012": (
        "test_explicit_migration_matches_golden_and_preserves_input_bytes",
        "test_public_migration_natively_seals_and_keeps_legacy_bytes",
    ),
    "MOR-QA-013": (
        "native.ir_replay",
        "test_all_twenty_native_content_bytes_and_digests_match_goldens",
        "test_exactly_twenty_synthetic_inputs_have_indexed_hashes_and_lf_free_goldens",
    ),
}
TRACEABILITY_EVIDENCE: dict[str, tuple[str, ...]] = {
    "MOR-IR-001": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-002": (
        "cpp/include/morphoia/engine.h",
        "tests/native/canonical_json_c_api_test.c",
        "tests/native/ir_replay_test.cpp",
        "tests/test_engine_ir_native.py",
    ),
    "MOR-IR-003": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "tests/test_engine_ir_replay.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-IR-004": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "tests/fixtures/engine-ir/0.1.0/DATA_CARD.md",
    ),
    "MOR-IR-005": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "tests/test_engine_ir_replay.py",
        "docs/engine/IR_MANIFEST_0_1.md",
    ),
    "MOR-IR-006": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "docs/engine/IR_MANIFEST_0_1.md",
    ),
    "MOR-IR-007": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-008": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "docs/engine/IR_MANIFEST_0_1.md",
    ),
    "MOR-IR-009": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-010": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-011": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "docs/engine/IR_MANIFEST_0_1.md",
    ),
    "MOR-IR-012": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-013": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "tests/fixtures/engine-ir/0.1.0/inputs/graph-10-fidelity-loss.json",
    ),
    "MOR-IR-014": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "docs/engine/IR_MANIFEST_0_1.md",
    ),
    "MOR-IR-015": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-016": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/fixtures/engine-ir/0.1.0/inputs/graph-13-topology-unstable.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-017": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/fixtures/engine-ir/0.1.0/inputs/graph-09-ai-candidate.json",
        "tests/test_engine_ir_contract.py",
    ),
    "MOR-IR-018": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "schemas/morphoia-engine-ir-replay-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "tests/test_engine_ir_migration.py",
        "tests/test_engine_ir_replay.py",
        "tests/fixtures/engine-ir/0.1.0/DATA_CARD.md",
    ),
    "MOR-API-002": (
        "cpp/include/morphoia/engine.h",
        "tests/native/canonical_json_c_api_test.c",
    ),
    "MOR-API-003": (
        "cpp/include/morphoia/engine.h",
        "tests/native/canonical_json_c_api_test.c",
        "tests/test_engine_ir_native.py",
    ),
    "MOR-API-006": (
        "cpp/include/morphoia/engine.h",
        "src/morphoia/_engine_native.py",
        "tests/test_engine_ir_native.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-API-007": (
        "cpp/include/morphoia/engine.h",
        "tests/native/canonical_json_c_api_test.c",
        "tests/test_engine_ir_native.py",
    ),
    "MOR-API-008": (
        "cpp/include/morphoia/engine.h",
        "tests/native/canonical_json_c_api_test.c",
        "tests/test_engine_ir_native.py",
    ),
    "MOR-API-009": (
        "src/morphoia/_engine_native.py",
        "tests/test_engine_ir_native.py",
    ),
    "MOR-API-010": (
        "src/morphoia/cli.py",
        "tests/test_engine_ir_cli.py",
    ),
    "MOR-API-011": (
        "src/morphoia/engine_ir.py",
        "tests/test_engine_ir_replay.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-API-012": (
        "src/morphoia/engine_ir.py",
        "tests/test_engine_ir_replay.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-API-013": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "src/morphoia/engine_ir.py",
        "tests/test_engine_ir_contract.py",
        "tests/test_engine_ir_replay.py",
    ),
    "MOR-API-014": (
        "pyproject.toml",
        "cpp/include/morphoia/engine.h",
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-API-015": (
        "src/morphoia/engine_ir_migration.py",
        "tests/test_engine_ir_migration.py",
        "tests/test_engine_ir_replay.py",
        "tests/fixtures/engine-ir/0.1.0/migration/legacy-input.json",
        "tests/fixtures/engine-ir/0.1.0/migration/expected-content.json",
    ),
    "MOR-API-018": (
        "schemas/morphoia-engine-ir-manifest-0.1.0.schema.json",
        "tests/test_engine_ir_contract.py",
        "tests/fixtures/engine-ir/0.1.0/inputs/graph-19-reverse-dns-extension.json",
    ),
    "MOR-DEV-001": (
        "CMakeLists.txt",
        "cpp/src/engine.cpp",
        "tests/native/ir_replay_test.cpp",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-002": (
        "CMakeLists.txt",
        "cpp/include/morphoia/engine.h",
        "cmake/morphoia_engine.map",
        "tests/native/consumer/CMakeLists.txt",
        "tests/native/consumer/main.c",
    ),
    "MOR-DEV-003": (
        "pyproject.toml",
        ".github/workflows/engine-ci.yml",
        "tests/test_engine_ir_native.py",
        "tests/test_engine_ir_cli.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-005": (
        "CMakeLists.txt",
        "tests/native/consumer/CMakeLists.txt",
        ".github/workflows/engine-ci.yml",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-008": (
        "CMakeLists.txt",
        ".github/workflows/engine-ci.yml",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-009": (
        "cpp/src/engine.cpp",
        "tests/native/canonical_json_c_api_test.c",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-010": (
        "cpp/src/engine.cpp",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-011": (
        ".github/workflows/engine-ci.yml",
        "tests/test_engine_ir_contract.py",
        "tests/test_engine_ir_replay.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-012": (
        "pyproject.toml",
        "artifacts/sbom/engine-e1-public-ir.cdx.json",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-DEV-014": (
        "tests/fixtures/engine-ir/0.1.0/DATA_CARD.md",
        "scripts/generate_engine_e1_public_ir_sbom.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-CAS-001": (
        "scripts/validate_engine_e1_native_evidence.py",
        "docs/engine/evidence/E1_NATIVE_CORE_REPORT.md",
        "artifacts/e1/manifest.json",
        "tests/native/ir_replay_test.cpp",
    ),
    "MOR-CAS-003": (
        "scripts/validate_engine_e1_native_evidence.py",
        "docs/engine/evidence/E1_NATIVE_CORE_REPORT.md",
        "artifacts/e1/manifest.json",
        "tests/test_engine_ir_replay.py",
    ),
    "MOR-CAS-004": (
        "scripts/validate_engine_e1_native_evidence.py",
        "docs/engine/evidence/E1_NATIVE_CORE_REPORT.md",
        "artifacts/e1/manifest.json",
    ),
    "MOR-CAS-006": (
        "tests/native/ir_replay_test.cpp",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-CAS-008": (
        "scripts/validate_engine_e1_native_evidence.py",
        "docs/engine/evidence/E1_NATIVE_CORE_REPORT.md",
        "artifacts/e1/manifest.json",
        "tests/test_engine_ir_replay.py",
    ),
    "MOR-CAS-010": (
        "src/morphoia/engine_ir.py",
        "tests/test_engine_ir_replay.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-CAS-012": (
        "src/morphoia/engine_ir_migration.py",
        "tests/test_engine_ir_migration.py",
        "tests/test_engine_ir_replay.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
    "MOR-QA-013": (
        "tests/fixtures/engine-ir/0.1.0/DATA_CARD.md",
        "tests/fixtures/engine-ir/0.1.0/index.json",
        "tests/native/ir_replay_test.cpp",
        "tests/test_engine_ir_contract.py",
        "docs/engine/evidence/E1_PUBLIC_IR_REPORT.md",
    ),
}
TRACEABILITY_CLAIMS: dict[str, str] = {
    "MOR-IR-001": "The normative public Engine IR manifest uses JSON Schema Draft 2020-12.",
    "MOR-IR-002": "The signable form uses the published and tested Morphoia Canonical "
    "JSON Profile 1.",
    "MOR-IR-003": "Each public Engine IR object distinguishes a logical identity, "
    "revision, and content digest.",
    "MOR-IR-004": "Public Engine IR logical identities use lowercase UUIDv7 text as "
    "defined by RFC 9562.",
    "MOR-IR-005": "Each binary reference carries a SHA-256 digest, byte size, media type, "
    "and resolvable URI.",
    "MOR-IR-006": "Units use an unambiguous UCUM-compatible notation with a verifiable "
    "factor to SI.",
    "MOR-IR-007": "Each frame declares dimension, origin, axes, handedness, matrix order, "
    "and unit.",
    "MOR-IR-008": "Frame transforms are preserved explicitly and are never applied silently.",
    "MOR-IR-009": "The source block carries URI, license, author or holder, date, source "
    "tool, and byte digest.",
    "MOR-IR-010": "The product block preserves available assemblies, instances, names, "
    "colors, layers, and properties.",
    "MOR-IR-011": "B-Rep, mesh, points, voxels, volumes, fields, scenes, tensors, and "
    "future opaque MVX representations remain separately typed.",
    "MOR-IR-012": "Provenance is an acyclic DAG carrying tool, version, commit, "
    "parameters, parents, environment, seeds, and timestamps.",
    "MOR-IR-013": "Each fidelity event carries property, before and after values, metric, "
    "threshold, severity, and decision.",
    "MOR-IR-014": "The security block declares classification, sensitivity, access "
    "policy, signature, and trust level.",
    "MOR-IR-015": "Massive arrays and binary payload bytes are not embedded in the JSON manifest.",
    "MOR-IR-016": "An unstable topological identifier carries its matching strategy and "
    "confidence.",
    "MOR-IR-017": "An AI output creates a reviewable branch and never directly replaces a "
    "geometry authority.",
    "MOR-IR-018": "The schemas provide valid, invalid, boundary, and migration fixtures and tests.",
    "MOR-API-002": "Each extensible C structure begins with struct_size and abi_version.",
    "MOR-API-003": "C ABI strings are UTF-8 views with explicit lengths and no implicit "
    "termination assumption.",
    "MOR-API-006": "Thread-safety behavior is documented for every public API family in "
    "this profile.",
    "MOR-API-007": "Errors expose a stable code, severity, context, cause, affected "
    "elements, and recommendation.",
    "MOR-API-008": "The module exposes capability negotiation and its effective versions.",
    "MOR-API-009": "The Python API provides context managers and deterministic resource release.",
    "MOR-API-010": "The CLI provides human output, machine-readable JSON, and stable exit codes.",
    "MOR-API-011": "Long operations expose progress, timeout, cancellation, and terminal state.",
    "MOR-API-012": "Replayable requests accept an idempotency key.",
    "MOR-API-013": "Dates use UTC RFC 3339 and durations use explicit units.",
    "MOR-API-014": "Packages, APIs, and protocols follow SemVer.",
    "MOR-API-015": "Incompatible schema changes include a migration tool and "
    "before-and-after fixtures.",
    "MOR-API-018": "Unknown namespaced extensions are preserved by a round trip that does "
    "not invalidate them.",
    "MOR-DEV-001": "The native core uses C++20.",
    "MOR-DEV-002": "The public binary contract uses a versioned C11 ABI.",
    "MOR-DEV-003": "The reference distribution targets Python 3.13 and remains compatible "
    "with Python 3.12 during P0-P1.",
    "MOR-DEV-005": "The native build uses CMake and versioned CMake Presets.",
    "MOR-DEV-008": "New compiler warnings in Morphoia code fail Tier 1 CI.",
    "MOR-DEV-009": "C++ exceptions never cross the C ABI.",
    "MOR-DEV-010": "Owned memory follows RAII and new code has no owning raw pointers.",
    "MOR-DEV-011": "Python code is formatted, linted, typed, and tested automatically.",
    "MOR-DEV-012": "Dependencies are locked or concretized with versions, options, and hashes.",
    "MOR-DEV-014": "Secrets, patient data, and large binaries are never committed to the "
    "public repository.",
    "MOR-CAS-001": "The CAS uses SHA-256 as its published identity.",
    "MOR-CAS-003": "A block is published atomically only after its size and hash are verified.",
    "MOR-CAS-004": "CAS reads and writes operate in streaming mode.",
    "MOR-CAS-006": "A local cache and at least one POSIX or remote object backend share "
    "the same identities.",
    "MOR-CAS-008": "Transfer corruption is detected before data is exposed to a consumer.",
    "MOR-CAS-010": "External URIs are resolved through an adapter and never treated as "
    "arbitrary unvalidated paths.",
    "MOR-CAS-012": "Each transformation creates a new block and provenance node without "
    "modifying its input in place.",
    "MOR-QA-013": "The minimum corpus includes 20 IR graphs, 20 STEP files, 20 SMESH "
    "meshes, 10 MED files, and three artifacts larger than 2 GiB.",
}
TRACEABILITY_STATUSES: dict[str, str] = {
    "MOR-IR-001": "PASS",
    "MOR-IR-002": "PASS",
    "MOR-IR-003": "NOT_RUN",
    "MOR-IR-004": "PASS",
    "MOR-IR-005": "NOT_RUN",
    "MOR-IR-006": "NOT_RUN",
    "MOR-IR-007": "PASS",
    "MOR-IR-008": "PASS",
    "MOR-IR-009": "PASS",
    "MOR-IR-010": "PASS",
    "MOR-IR-011": "NOT_RUN",
    "MOR-IR-012": "PASS",
    "MOR-IR-013": "PASS",
    "MOR-IR-014": "PASS",
    "MOR-IR-015": "PASS",
    "MOR-IR-016": "PASS",
    "MOR-IR-017": "PASS",
    "MOR-IR-018": "PASS",
    "MOR-API-002": "PASS",
    "MOR-API-003": "PASS",
    "MOR-API-006": "NOT_RUN",
    "MOR-API-007": "PASS",
    "MOR-API-008": "PASS",
    "MOR-API-009": "PASS",
    "MOR-API-010": "PASS",
    "MOR-API-011": "NOT_RUN",
    "MOR-API-012": "NOT_RUN",
    "MOR-API-013": "PASS",
    "MOR-API-014": "NOT_RUN",
    "MOR-API-015": "PASS",
    "MOR-API-018": "PASS",
    "MOR-DEV-001": "PASS",
    "MOR-DEV-002": "PASS",
    "MOR-DEV-003": "PASS",
    "MOR-DEV-005": "PASS",
    "MOR-DEV-008": "PASS",
    "MOR-DEV-009": "PASS",
    "MOR-DEV-010": "NOT_RUN",
    "MOR-DEV-011": "NOT_RUN",
    "MOR-DEV-012": "NOT_RUN",
    "MOR-DEV-014": "NOT_RUN",
    "MOR-CAS-001": "PASS",
    "MOR-CAS-003": "PASS",
    "MOR-CAS-004": "PASS",
    "MOR-CAS-006": "NOT_RUN",
    "MOR-CAS-008": "PASS",
    "MOR-CAS-010": "NOT_RUN",
    "MOR-CAS-012": "NOT_RUN",
    "MOR-QA-013": "NOT_RUN",
}
TRACEABILITY_BLOCKING_SCOPES: dict[str, str] = {
    "MOR-IR-001": "none-public-ir-core-cpu-profile",
    "MOR-IR-002": "none-public-ir-core-cpu-profile",
    "MOR-IR-003": "universal-object-coverage-not-executed",
    "MOR-IR-004": "none-public-ir-core-cpu-profile",
    "MOR-IR-005": "referenced-payload-bytes-and-complete-resolution-not-executed",
    "MOR-IR-006": "complete-UCUM-code-dimension-factor-verifier-not-implemented",
    "MOR-IR-007": "none-public-ir-core-cpu-profile",
    "MOR-IR-008": "none-public-ir-core-cpu-profile",
    "MOR-IR-009": "none-public-ir-core-cpu-profile",
    "MOR-IR-010": "none-public-ir-core-cpu-profile",
    "MOR-IR-011": "owner-validated-MVX-type-and-contract-absent",
    "MOR-IR-012": "none-public-ir-core-cpu-profile",
    "MOR-IR-013": "none-public-ir-core-cpu-profile",
    "MOR-IR-014": "none-public-ir-core-cpu-profile",
    "MOR-IR-015": "none-public-ir-core-cpu-profile",
    "MOR-IR-016": "none-public-ir-core-cpu-profile",
    "MOR-IR-017": "none-public-ir-core-cpu-profile",
    "MOR-IR-018": "none-public-ir-core-cpu-profile",
    "MOR-API-002": "none-public-ir-core-cpu-profile",
    "MOR-API-003": "none-public-ir-core-cpu-profile",
    "MOR-API-006": "per-family-thread-safety-documentation-and-review-not-executed",
    "MOR-API-007": "none-public-ir-core-cpu-profile",
    "MOR-API-008": "none-public-ir-core-cpu-profile",
    "MOR-API-009": "none-public-ir-core-cpu-profile",
    "MOR-API-010": "none-public-ir-core-cpu-profile",
    "MOR-API-011": "long-operation-progress-and-terminal-state-not-implemented",
    "MOR-API-012": "idempotency-key-contract-not-implemented",
    "MOR-API-013": "none-public-ir-core-cpu-profile",
    "MOR-API-014": "package-version-is-not-a-final-SemVer-release",
    "MOR-API-015": "none-public-ir-core-cpu-profile",
    "MOR-API-018": "none-public-ir-core-cpu-profile",
    "MOR-DEV-001": "none-public-ir-core-cpu-profile",
    "MOR-DEV-002": "none-public-ir-core-cpu-profile",
    "MOR-DEV-003": "none-public-ir-core-cpu-profile",
    "MOR-DEV-005": "none-public-ir-core-cpu-profile",
    "MOR-DEV-008": "none-public-ir-core-cpu-profile",
    "MOR-DEV-009": "none-public-ir-core-cpu-profile",
    "MOR-DEV-010": "complete-owned-memory-inspection-not-executed",
    "MOR-DEV-011": "static-type-checker-not-executed",
    "MOR-DEV-012": "system-toolchain-image-is-not-hash-concretized",
    "MOR-DEV-014": "final-committed-public-tree-policy-check-not-executed",
    "MOR-CAS-001": "none-public-ir-core-cpu-profile",
    "MOR-CAS-003": "none-public-ir-core-cpu-profile",
    "MOR-CAS-004": "none-public-ir-core-cpu-profile",
    "MOR-CAS-006": "distinct-local-cache-and-backend-roles-not-executed",
    "MOR-CAS-008": "none-public-ir-core-cpu-profile",
    "MOR-CAS-010": "external-URI-resolver-adapter-not-implemented",
    "MOR-CAS-012": "new-transformed-CAS-block-and-provenance-write-not-executed",
    "MOR-QA-013": "STEP-SMESH-MED-and-three-greater-than-2-GiB-segments-not-executed",
}
DECLARED_NON_PYTHON_TEST_IDS: set[str] = set()


class DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a decoded key."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def reject_float(value: str) -> NoReturn:
    raise ValueError(f"floating-point JSON value is outside this evidence profile: {value}")


def reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-JSON numeric constant: {value}")


def validate_json_value(value: Any, location: str = "$") -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError(f"lone Unicode surrogate at {location}")
        value.encode("utf-8")
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise ValueError(f"unsafe JSON integer at {location}")
        return
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


def validate_root(root: Path) -> Path:
    if not root.is_absolute():
        raise ValueError("repository root must be absolute")
    absolute = Path(os.path.abspath(root))
    if absolute != root or root.is_symlink() or not root.is_dir():
        raise ValueError("repository root must be a resolved non-symlink directory")
    resolved = root.resolve(strict=True)
    if resolved != root:
        raise ValueError("repository root must not use an alias")
    return root


def validate_relative_path(relative: str) -> tuple[str, ...]:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("repository path must be a non-empty string")
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute()
        or relative != posix.as_posix()
        or "." in posix.parts
        or ".." in posix.parts
        or "\\" in relative
    ):
        raise ValueError(f"unsafe repository path: {relative!r}")
    return posix.parts


def _open_root(root: Path) -> int:
    root = validate_root(root)
    expected = root.stat(follow_symlinks=False)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
        os.close(descriptor)
        raise ValueError("repository root changed while opening")
    return descriptor


def read_repository_file(root: Path, relative: str) -> bytes:
    """Read one confined regular single-link file through openat/O_NOFOLLOW."""

    parts = validate_relative_path(relative)
    root_descriptor = _open_root(root)
    directory_descriptor = root_descriptor
    file_descriptor = -1
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
            if directory_descriptor != root_descriptor:
                os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_descriptor,
        )
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"repository input is not a regular file: {relative}")
        if before.st_nlink != 1:
            raise ValueError(f"repository input is a hard-link alias: {relative}")
        if not 0 <= before.st_size <= MAX_INPUT_BYTES:
            raise ValueError(f"repository input exceeds the evidence size bound: {relative}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise ValueError(f"repository input changed during read: {relative}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise ValueError(f"repository input grew during read: {relative}")
        after = os.fstat(file_descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity:
            raise ValueError(f"repository input changed during read: {relative}")
        return b"".join(chunks)
    except OSError as error:
        raise ValueError(f"cannot safely read repository input {relative}: {error}") from error
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if directory_descriptor != root_descriptor:
            os.close(directory_descriptor)
        os.close(root_descriptor)


def read_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    try:
        text = content.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"cannot read strict JSON {label}: {error}") from error
    if not isinstance(value, dict):
        raise TypeError(f"{label} must contain a JSON object")
    validate_json_value(value)
    return value


def read_repository_json(root: Path, relative: str) -> dict[str, Any]:
    return read_json_bytes(read_repository_file(root, relative), relative)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_locks(root: Path) -> dict[tuple[str, str], dict[str, set[str]]]:
    packages: dict[tuple[str, str], dict[str, set[str]]] = {}
    for relative in LOCK_FILES:
        text = read_repository_file(root, relative).decode("utf-8", errors="strict")
        current: tuple[str, str] | None = None
        declaration_has_hash = False
        for number, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            package_match = PACKAGE_RE.fullmatch(line)
            if package_match:
                if current is not None and not declaration_has_hash:
                    raise ValueError(f"locked package has no digest before {relative}:{number}")
                current = (
                    normalize_package_name(package_match.group(1)),
                    package_match.group(2),
                )
                packages.setdefault(current, {"hashes": set(), "locks": set()})["locks"].add(
                    relative
                )
                declaration_has_hash = False
                continue
            hash_match = HASH_RE.fullmatch(line)
            if hash_match and current is not None:
                packages[current]["hashes"].add(hash_match.group(1))
                declaration_has_hash = True
                continue
            raise ValueError(f"unparsed lock line {relative}:{number}")
        if current is not None and not declaration_has_hash:
            raise ValueError(f"locked package has no digest at end of {relative}")
    if not packages:
        raise ValueError("public-IR dependency inventory is empty")
    return packages


def deterministic_json(value: Any) -> bytes:
    validate_json_value(value)
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _artifact_entry(
    path: str,
    spec: ArtifactSpec,
    content: bytes,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": spec.identifier,
        "kind": spec.kind,
        "path": path,
        "media_type": spec.media_type,
        "size_bytes": len(content),
        "sha256": sha256_bytes(content),
        "license_expression": spec.license_expression,
        "source_artifact_id": spec.source_artifact_id,
        "provenance": spec.provenance,
        "verification_status": "PASS",
        "vulnerability_analysis_status": "NOT_RUN",
    }
    if spec.note is not None:
        entry["note"] = spec.note
    return entry


def _regular_file_fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
    """Capture identity and mutation-sensitive metadata for one regular file."""

    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def build_artifact_entries(root: Path) -> list[dict[str, Any]]:
    if not ARTIFACT_SPECS:
        raise ValueError("public-IR artifact allowlist is empty")
    verify_fixture_allowlist(root)
    identifiers = [spec.identifier for spec in ARTIFACT_SPECS.values()]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("public-IR artifact identifiers are not unique")
    entries: list[dict[str, Any]] = []
    for relative, spec in sorted(ARTIFACT_SPECS.items()):
        content = read_repository_file(root, relative)
        if (
            relative == "spec/requirements/requirements-tracking.yaml"
            and sha256_bytes(content) != FROZEN_REQUIREMENTS_TRACKING_DIGEST
        ):
            raise ValueError("frozen global requirements tracking overlay differs")
        if relative in FROZEN_E1_DIGESTS:
            actual_digest = sha256_bytes(content)
            if actual_digest != FROZEN_E1_DIGESTS[relative]:
                raise ValueError(f"frozen E1 evidence digest differs: {relative}")
        entries.append(_artifact_entry(relative, spec, content))
    return entries


def _python_test_ids(root: Path) -> set[str]:
    locations: dict[str, str] = {}
    for relative, spec in ARTIFACT_SPECS.items():
        if spec.kind not in {"python-test", "evidence-test", "schema-test"}:
            continue
        try:
            tree = ast.parse(
                read_repository_file(root, relative).decode("utf-8", errors="strict"),
                filename=relative,
            )
        except (SyntaxError, UnicodeError) as error:
            raise ValueError(f"cannot parse test source {relative}") from error
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            ):
                previous = locations.get(node.name)
                if previous is not None:
                    raise ValueError(
                        f"duplicate Python test id {node.name}: {previous}, {relative}"
                    )
                locations[node.name] = relative
    return set(locations)


def _cmake_test_ids(root: Path) -> set[str]:
    """Read registered CTest names from the allowlisted build contracts."""

    identifiers: list[str] = []
    for relative in ("CMakeLists.txt", "tests/native/consumer/CMakeLists.txt"):
        source = read_repository_file(root, relative).decode("utf-8", errors="strict")
        identifiers.extend(CMAKE_ADD_TEST_RE.findall(source))
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate CTest id in the public-IR build contract")
    return set(identifiers)


def validate_traceability(root: Path, value: dict[str, Any]) -> None:
    expected_fields = {
        "$schema",
        "schema_version",
        "profile",
        "source_base_commit",
        "execution_environment",
        "entries",
    }
    if set(value) != expected_fields:
        raise ValueError("public-IR traceability fields do not match the closed profile")
    expected_values = {
        "$schema": "./e1-public-ir-traceability.schema.json",
        "schema_version": "1.0.0",
        "profile": PROFILE,
        "source_base_commit": SOURCE_BASE_COMMIT,
    }
    for field, expected in expected_values.items():
        if value[field] != expected:
            raise ValueError(f"public-IR traceability {field} must be {expected!r}")
    environment = value["execution_environment"]
    if not isinstance(environment, dict) or set(environment) != {
        "os",
        "architecture",
        "compiler",
        "python",
        "commands",
    }:
        raise ValueError("public-IR execution environment fields are invalid")
    for field in ("os", "architecture", "compiler", "python"):
        if not isinstance(environment[field], str) or not environment[field]:
            raise ValueError(f"public-IR execution environment {field} is invalid")
    commands = environment["commands"]
    if not isinstance(commands, list) or not commands:
        raise ValueError("public-IR execution commands must be a non-empty array")
    command_ids: set[str] = set()
    for command in commands:
        if not isinstance(command, dict) or set(command) != {
            "id",
            "command",
            "status",
            "result",
        }:
            raise ValueError("public-IR execution command fields are invalid")
        if (
            not isinstance(command["id"], str)
            or not IDENTIFIER_RE.fullmatch(command["id"])
            or command["id"] in command_ids
        ):
            raise ValueError("public-IR execution command id is invalid")
        command_ids.add(command["id"])
        if command["status"] not in STATUS_VALUES:
            raise ValueError(f"invalid execution status for {command['id']}")
        if not isinstance(command["command"], str) or not command["command"]:
            raise ValueError(f"missing execution command for {command['id']}")
        if not isinstance(command["result"], str) or not command["result"]:
            raise ValueError(f"missing execution result for {command['id']}")
    if tuple(command["id"] for command in commands) != EXECUTION_COMMAND_IDS:
        raise ValueError("public-IR execution command order and allowlist are not exact")
    final_head_command = commands[EXECUTION_COMMAND_IDS.index("final-evidence-head-hosted")]
    if final_head_command != {
        "id": "final-evidence-head-hosted",
        "command": FINAL_EVIDENCE_HEAD_COMMAND,
        "status": "PASS",
        "result": FINAL_EVIDENCE_HEAD_RESULT,
    }:
        raise ValueError("public-IR final evidence-head hosted evidence is not exact")
    integration_command = commands[EXECUTION_COMMAND_IDS.index("public-ir-integration-postmerge")]
    if integration_command != {
        "id": "public-ir-integration-postmerge",
        "command": INTEGRATION_COMMAND,
        "status": "PASS",
        "result": INTEGRATION_RESULT,
    }:
        raise ValueError("public-IR integration and post-merge evidence is not exact")

    if set(TRACEABILITY_TESTS) != TRACEABILITY_REQUIREMENTS:
        raise ValueError("public-IR traceability test allowlist is incomplete")
    if set(TRACEABILITY_EVIDENCE) != TRACEABILITY_REQUIREMENTS:
        raise ValueError("public-IR traceability evidence allowlist is incomplete")
    if set(TRACEABILITY_CLAIMS) != TRACEABILITY_REQUIREMENTS:
        raise ValueError("public-IR traceability claim allowlist is incomplete")
    if set(TRACEABILITY_STATUSES) != TRACEABILITY_REQUIREMENTS:
        raise ValueError("public-IR traceability status allowlist is incomplete")
    if set(TRACEABILITY_BLOCKING_SCOPES) != TRACEABILITY_REQUIREMENTS:
        raise ValueError("public-IR traceability blocking-scope allowlist is incomplete")
    python_tests = _python_test_ids(root)
    cmake_tests = _cmake_test_ids(root)
    overlap = python_tests & cmake_tests
    if overlap:
        raise ValueError(f"ambiguous Python/CTest ids: {sorted(overlap)}")
    known_tests = python_tests | cmake_tests | DECLARED_NON_PYTHON_TEST_IDS
    entries = value["entries"]
    if not isinstance(entries, list) or len(entries) != len(TRACEABILITY_REQUIREMENTS):
        raise ValueError("public-IR traceability entry count is invalid")
    actual_order = tuple(
        entry.get("requirement_id") if isinstance(entry, dict) else None for entry in entries
    )
    if actual_order != TRACEABILITY_ORDER:
        raise ValueError("public-IR traceability requirement order differs")
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {
            "requirement_id",
            "claim",
            "status",
            "test_ids",
            "evidence",
            "reason",
            "blocking_scope",
        }:
            raise ValueError(f"public-IR traceability entry {index} fields are invalid")
        requirement = entry["requirement_id"]
        if (
            not isinstance(requirement, str)
            or not REQUIREMENT_RE.fullmatch(requirement)
            or requirement in seen
        ):
            raise ValueError(f"public-IR traceability requirement is invalid at {index}")
        seen.add(requirement)
        if requirement not in TRACEABILITY_REQUIREMENTS:
            raise ValueError(f"requirement is outside the public-IR profile: {requirement}")
        if entry["claim"] != TRACEABILITY_CLAIMS[requirement]:
            raise ValueError(f"public-IR claim mapping is not exact: {requirement}")
        status_value = entry["status"]
        if status_value != TRACEABILITY_STATUSES[requirement]:
            raise ValueError(f"public-IR status mapping is not exact: {requirement}")
        if requirement == "MOR-QA-013" and status_value != "NOT_RUN":
            raise ValueError("MOR-QA-013 must remain NOT_RUN in the 20-graph-only profile")
        test_ids = entry["test_ids"]
        if (
            not isinstance(test_ids, list)
            or len(test_ids) != len(set(test_ids))
            or not all(isinstance(item, str) and TEST_ID_RE.fullmatch(item) for item in test_ids)
            or tuple(test_ids) != TRACEABILITY_TESTS[requirement]
        ):
            raise ValueError(f"public-IR test mapping is not exact: {requirement}")
        undefined = sorted(set(test_ids) - known_tests)
        if undefined:
            raise ValueError(f"public-IR traceability references undefined tests: {undefined}")
        evidence = entry["evidence"]
        if (
            not isinstance(evidence, list)
            or len(evidence) != len(set(evidence))
            or tuple(evidence) != TRACEABILITY_EVIDENCE[requirement]
        ):
            raise ValueError(f"public-IR evidence mapping is not exact: {requirement}")
        for relative in evidence:
            validate_relative_path(relative)
            if relative not in ARTIFACT_SPECS and relative not in {MANIFEST_PATH, OUTPUT_PATH}:
                raise ValueError(f"traceability evidence is outside the allowlist: {requirement}")
            if relative in ARTIFACT_SPECS:
                read_repository_file(root, relative)
        if status_value in {"PASS", "FAIL"} and (not test_ids or not evidence):
            raise ValueError(f"executed status lacks test/evidence: {requirement}")
        if not isinstance(entry["reason"], str) or not entry["reason"]:
            raise ValueError(f"public-IR reason is missing: {requirement}")
        if len(entry["reason"]) > 4096:
            raise ValueError(f"public-IR reason exceeds its bound: {requirement}")
        if entry["blocking_scope"] != TRACEABILITY_BLOCKING_SCOPES[requirement]:
            raise ValueError(f"public-IR blocking scope is not exact: {requirement}")
    if seen != TRACEABILITY_REQUIREMENTS:
        raise ValueError("public-IR traceability requirement set is incomplete")


def validate_manifest(root: Path, value: dict[str, Any], verify_self: bool) -> None:
    expected_fields = {
        "schema_version",
        "project",
        "profile",
        "generated_at",
        "manifest_document_license",
        "hash_algorithm",
        "source_base_commit",
        "artifacts",
    }
    if set(value) != expected_fields:
        raise ValueError("public-IR manifest fields do not match the closed profile")
    expected_values = {
        "schema_version": "1.0.0",
        "project": "Morphoia Engine",
        "profile": PROFILE,
        "generated_at": GENERATED_AT,
        "manifest_document_license": "CC-BY-4.0",
        "hash_algorithm": "sha256",
        "source_base_commit": SOURCE_BASE_COMMIT,
    }
    for field, expected in expected_values.items():
        if value[field] != expected:
            raise ValueError(f"public-IR manifest {field} must be {expected!r}")
    artifacts = value["artifacts"]
    if not isinstance(artifacts, list):
        raise TypeError("public-IR manifest artifacts must be an array")
    expected_specs = {**ARTIFACT_SPECS, OUTPUT_PATH: SELF_SPEC}
    expected_paths = tuple(sorted(expected_specs))
    actual_paths = tuple(item.get("path") for item in artifacts if isinstance(item, dict))
    if actual_paths != expected_paths:
        raise ValueError("public-IR artifact path allowlist or order differs")
    identifiers: dict[str, str] = {}
    sources: dict[str, str] = {}
    for artifact in artifacts:
        relative = artifact["path"]
        spec = expected_specs[relative]
        required_fields = {
            "id",
            "kind",
            "path",
            "media_type",
            "size_bytes",
            "sha256",
            "license_expression",
            "source_artifact_id",
            "provenance",
            "verification_status",
            "vulnerability_analysis_status",
        }
        if spec.note is not None:
            required_fields.add("note")
        if set(artifact) != required_fields:
            raise ValueError(f"public-IR artifact fields differ: {relative}")
        expected_static = {
            "id": spec.identifier,
            "kind": spec.kind,
            "media_type": spec.media_type,
            "license_expression": spec.license_expression,
            "source_artifact_id": spec.source_artifact_id,
            "provenance": spec.provenance,
            "verification_status": "PASS",
            "vulnerability_analysis_status": "NOT_RUN",
        }
        if spec.note is not None:
            expected_static["note"] = spec.note
        for field, expected in expected_static.items():
            if artifact[field] != expected:
                raise ValueError(f"public-IR artifact {field} differs: {relative}")
        identifier = artifact["id"]
        if not IDENTIFIER_RE.fullmatch(identifier) or identifier in identifiers:
            raise ValueError(f"public-IR artifact id is invalid or duplicated: {identifier}")
        identifiers[identifier] = relative
        source = artifact["source_artifact_id"]
        if source is not None:
            if not isinstance(source, str) or not IDENTIFIER_RE.fullmatch(source):
                raise ValueError(f"public-IR artifact source id is invalid: {relative}")
            sources[identifier] = source
        size = artifact["size_bytes"]
        digest = artifact["sha256"]
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_SAFE_INTEGER:
            raise ValueError(f"public-IR artifact size is invalid: {relative}")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(f"public-IR artifact digest is invalid: {relative}")
        if relative != OUTPUT_PATH or verify_self:
            content = read_repository_file(root, relative)
            if len(content) != size or sha256_bytes(content) != digest:
                raise ValueError(f"public-IR artifact bytes differ: {relative}")
    for identifier, source in sources.items():
        if source not in identifiers:
            raise ValueError(f"public-IR artifact {identifier} has dangling source {source}")
    for identifier in identifiers:
        visited: set[str] = set()
        cursor = identifier
        while cursor in sources:
            if cursor in visited:
                raise ValueError(f"public-IR provenance cycle at {cursor}")
            visited.add(cursor)
            cursor = sources[cursor]


def _file_component(
    relative: str,
    identifier: str,
    license_expression: str,
    content: bytes,
    properties: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "type": "file",
        "bom-ref": identifier,
        "name": relative,
        "hashes": [{"alg": "SHA-256", "content": sha256_bytes(content)}],
        "licenses": [{"expression": license_expression}],
        "properties": sorted(properties, key=lambda item: (item["name"], item["value"])),
    }


def build_bom(root: Path, artifact_entries: list[dict[str, Any]]) -> dict[str, Any]:
    validate_root(root)
    validate_traceability(root, read_repository_json(root, TRACEABILITY_PATH))
    packages = parse_locks(root)
    components: list[dict[str, Any]] = []
    for artifact in artifact_entries:
        relative = artifact["path"]
        content = read_repository_file(root, relative)
        if (
            len(content) != artifact["size_bytes"]
            or sha256_bytes(content) != artifact["sha256"]
        ):
            raise ValueError(f"public-IR artifact changed while building SBOM: {relative}")
        components.append(
            _file_component(
                relative,
                f"urn:morphoia:e1-public-ir-artifact:{artifact['id']}",
                artifact["license_expression"],
                content,
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
            _file_component(
                relative,
                f"urn:morphoia:e1-public-ir-license:{urllib.parse.quote(relative, safe='')}",
                expression,
                read_repository_file(root, relative),
                [{"name": "morphoia:role", "value": "license-or-notice-file"}],
            )
        )
    for relative in LOCK_FILES:
        components.append(
            _file_component(
                relative,
                f"urn:morphoia:e1-public-ir-lock:{urllib.parse.quote(relative, safe='')}",
                "Apache-2.0 OR MIT",
                read_repository_file(root, relative),
                [
                    {"name": "morphoia:profile", "value": PROFILE},
                    {"name": "morphoia:source-base-commit", "value": SOURCE_BASE_COMMIT},
                    {"name": "morphoia:role", "value": "hashed-test-lock"},
                ],
            )
        )
    for (name, version), values in sorted(packages.items()):
        purl = (
            f"pkg:pypi/{urllib.parse.quote(name, safe='')}@{urllib.parse.quote(version, safe='')}"
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
                    {"alg": "SHA-256", "content": digest} for digest in sorted(values["hashes"])
                ],
                "licenses": [{"license": {"name": "NOASSERTION"}}],
                "properties": [
                    {"name": "morphoia:license-review-status", "value": "NOT_RUN"},
                    {"name": "morphoia:provisioning", "value": "lock-only-not-shipped-by-sbom"},
                    {"name": "morphoia:source-locks", "value": ",".join(sorted(values["locks"]))},
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
                    "bom-ref": component["bom-ref"],
                    "hashes": component.get("hashes", []),
                    "version": component.get("version"),
                }
                for component in components
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)
    root_ref = f"pkg:generic/morphoia-engine-e1-public-ir@{PROJECT_VERSION}"
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
                "name": "morphoia-engine-e1-public-ir",
                "version": PROJECT_VERSION,
                "licenses": [{"expression": "Apache-2.0 OR MIT"}],
                "externalReferences": [
                    {"type": "vcs", "url": "https://github.com/Aminoside/morphoia"}
                ],
                "properties": [
                    {"name": "morphoia:profile", "value": PROFILE},
                    {"name": "morphoia:source-base-commit", "value": SOURCE_BASE_COMMIT},
                    {"name": "morphoia:execution-scope", "value": "core-cpu-public-ir"},
                    {"name": "morphoia:mvx-status", "value": "NOT_RUN"},
                    {"name": "morphoia:optional-backends-status", "value": "NOT_RUN"},
                    {"name": "morphoia:vulnerability-analysis-status", "value": "NOT_RUN"},
                    {
                        "name": "morphoia:vulnerability-analysis-note",
                        "value": "Inventory generation is not a vulnerability assessment",
                    },
                ],
            }
        },
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": [item["bom-ref"] for item in components]},
            *({"ref": item["bom-ref"], "dependsOn": []} for item in components),
        ],
    }


def build_outputs(root: Path) -> tuple[bytes, bytes]:
    root = validate_root(root)
    artifact_entries = build_artifact_entries(root)
    for relative, spec in ARTIFACT_SPECS.items():
        if (
            spec.media_type in {"application/json", "application/schema+json"}
            and spec.kind not in {"invalid-fixture", "migration-fixture"}
        ):
            read_repository_json(root, relative)
    sbom_bytes = deterministic_json(build_bom(root, artifact_entries))
    self_entry = _artifact_entry(OUTPUT_PATH, SELF_SPEC, sbom_bytes)
    manifest = {
        "schema_version": "1.0.0",
        "project": "Morphoia Engine",
        "profile": PROFILE,
        "generated_at": GENERATED_AT,
        "manifest_document_license": "CC-BY-4.0",
        "hash_algorithm": "sha256",
        "source_base_commit": SOURCE_BASE_COMMIT,
        "artifacts": sorted([*artifact_entries, self_entry], key=lambda item: item["path"]),
    }
    manifest_bytes = deterministic_json(manifest)
    validate_manifest_without_repository_self(root, manifest, sbom_bytes)
    return manifest_bytes, sbom_bytes


def validate_manifest_without_repository_self(
    root: Path, value: dict[str, Any], sbom_bytes: bytes
) -> None:
    """Validate generated output before its self-referenced SBOM is published."""

    expected = next(item for item in value["artifacts"] if item["path"] == OUTPUT_PATH)
    if expected["sha256"] != sha256_bytes(sbom_bytes) or expected["size_bytes"] != len(sbom_bytes):
        raise ValueError("public-IR generated self metadata is inconsistent")
    # Validate all static fields and non-self artifacts through the same path.
    validate_manifest(root, value, verify_self=False)


def _open_parent_directory(root: Path, relative: str) -> tuple[int, str]:
    parts = validate_relative_path(relative)
    if len(parts) < 2:
        raise ValueError("generated output must not target the repository root")
    root_descriptor = _open_root(root)
    directory_descriptor = root_descriptor
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
            if directory_descriptor != root_descriptor:
                os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        if directory_descriptor == root_descriptor:
            duplicate = os.dup(root_descriptor)
        else:
            duplicate = directory_descriptor
            directory_descriptor = root_descriptor
        return duplicate, parts[-1]
    except OSError as error:
        raise ValueError(f"cannot safely open output parent {relative}: {error}") from error
    finally:
        if directory_descriptor != root_descriptor:
            os.close(directory_descriptor)
        os.close(root_descriptor)


def _renameat2(
    source_directory: int,
    source_name: str,
    destination_directory: int,
    destination_name: str,
    flags: int,
) -> None:
    """Call Linux renameat2 without a shell or unresolved path."""

    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is None:
        raise ValueError("atomic evidence publication requires Linux renameat2")
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    result = function(
        source_directory,
        os.fsencode(source_name),
        destination_directory,
        os.fsencode(destination_name),
        flags,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _read_regular_at(parent_descriptor: int, basename: str) -> tuple[bytes, tuple[int, ...]]:
    """Snapshot one bounded, regular, single-link file relative to a trusted dirfd."""

    descriptor = os.open(
        basename,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=parent_descriptor,
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 <= before.st_size <= MAX_INPUT_BYTES
        ):
            raise ValueError("evidence output has an unsafe type, link count, or size")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise ValueError("evidence output changed during snapshot")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("evidence output grew during snapshot")
        after = os.fstat(descriptor)
        before_identity = _regular_file_fingerprint(before)
        if _regular_file_fingerprint(after) != before_identity:
            raise ValueError("evidence output changed during snapshot")
        return b"".join(chunks), before_identity
    finally:
        os.close(descriptor)


def _verify_published_bytes(parent_descriptor: int, basename: str, content: bytes) -> None:
    published, _ = _read_regular_at(parent_descriptor, basename)
    if published != content:
        raise ValueError("published evidence output differs after atomic publication")


def write_atomic(
    root: Path,
    relative: str,
    content: bytes,
    *,
    before_publish: Callable[[int, str, tuple[int, ...] | None], None] | None = None,
    before_exchange: Callable[[int, str, tuple[int, ...] | None], None] | None = None,
) -> None:
    root = validate_root(root)
    parent_descriptor, basename = _open_parent_directory(root, relative)
    descriptor = -1
    temporary: str | None = None
    try:
        try:
            original_content, original_identity = _read_regular_at(
                parent_descriptor, basename
            )
        except FileNotFoundError:
            original_content = None
            original_identity = None
        except OSError as error:
            raise ValueError(
                f"generated output has an unsafe alias or type: {relative}"
            ) from error
        for _ in range(100):
            candidate = f".{basename}.{uuid.uuid4().hex}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary = candidate
            break
        if descriptor < 0 or temporary is None:
            raise ValueError(f"cannot allocate atomic output for {relative}")
        os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("short atomic evidence write")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            current_content, current_identity = _read_regular_at(parent_descriptor, basename)
        except FileNotFoundError:
            current_content = None
            current_identity = None
        except OSError as error:
            raise ValueError(f"generated output changed to an unsafe type: {relative}") from error
        if current_identity != original_identity or current_content != original_content:
            raise ValueError(f"generated output changed during write: {relative}")
        if before_publish is not None:
            before_publish(parent_descriptor, basename, original_identity)
        try:
            publish_content, publish_identity = _read_regular_at(parent_descriptor, basename)
        except FileNotFoundError:
            publish_content = None
            publish_identity = None
        except OSError as error:
            raise ValueError(f"generated output changed to an unsafe type: {relative}") from error
        if publish_identity != original_identity or publish_content != original_content:
            raise ValueError(f"generated output changed immediately before publication: {relative}")
        if before_exchange is not None:
            before_exchange(parent_descriptor, basename, original_identity)
        if original_identity is None:
            try:
                _renameat2(
                    parent_descriptor,
                    temporary,
                    parent_descriptor,
                    basename,
                    RENAME_NOREPLACE,
                )
            except OSError as error:
                if error.errno == errno.EEXIST:
                    raise ValueError(
                        f"generated output appeared during publication: {relative}"
                    ) from error
                raise
            temporary = None
        else:
            _renameat2(
                parent_descriptor,
                temporary,
                parent_descriptor,
                basename,
                RENAME_EXCHANGE,
            )
            try:
                exchanged_content, exchanged_identity = _read_regular_at(
                    parent_descriptor, temporary
                )
            except (OSError, ValueError):
                try:
                    _renameat2(
                        parent_descriptor,
                        temporary,
                        parent_descriptor,
                        basename,
                        RENAME_EXCHANGE,
                    )
                except OSError as restore_error:
                    raise ValueError(
                        f"cannot restore raced evidence output: {relative}"
                    ) from restore_error
                raise
            # A successful rename changes ctime on Linux. The immediately
            # preceding snapshot and the exchanged bytes cover in-place byte
            # mutation; compare every stable metadata field here except ctime.
            if (
                exchanged_identity[:-1] != original_identity[:-1]
                or exchanged_content != original_content
            ):
                try:
                    _renameat2(
                        parent_descriptor,
                        temporary,
                        parent_descriptor,
                        basename,
                        RENAME_EXCHANGE,
                    )
                except OSError as restore_error:
                    raise ValueError(
                        f"cannot restore raced evidence output: {relative}"
                    ) from restore_error
                raise ValueError(f"generated output raced before publication: {relative}")
            try:
                _verify_published_bytes(parent_descriptor, basename, content)
            except (OSError, ValueError):
                try:
                    _renameat2(
                        parent_descriptor,
                        temporary,
                        parent_descriptor,
                        basename,
                        RENAME_EXCHANGE,
                    )
                except OSError as restore_error:
                    raise ValueError(
                        f"cannot restore unverified evidence output: {relative}"
                    ) from restore_error
                raise
            os.unlink(temporary, dir_fd=parent_descriptor)
            temporary = None
        if original_identity is None:
            _verify_published_bytes(parent_descriptor, basename, content)
        os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def check_outputs(root: Path, manifest_bytes: bytes, sbom_bytes: bytes) -> None:
    committed_manifest = read_repository_file(root, MANIFEST_PATH)
    committed_sbom = read_repository_file(root, OUTPUT_PATH)
    if committed_manifest != manifest_bytes:
        raise ValueError("public-IR artifact manifest differs from deterministic output")
    if committed_sbom != sbom_bytes:
        raise ValueError("public-IR SBOM differs from deterministic output")
    manifest = read_json_bytes(committed_manifest, MANIFEST_PATH)
    validate_manifest(root, manifest, verify_self=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        root = validate_root(arguments.root)
        manifest_bytes, sbom_bytes = build_outputs(root)
        if arguments.check:
            check_outputs(root, manifest_bytes, sbom_bytes)
            action = "matches"
        else:
            write_atomic(root, OUTPUT_PATH, sbom_bytes)
            write_atomic(root, MANIFEST_PATH, manifest_bytes)
            check_outputs(root, manifest_bytes, sbom_bytes)
            action = "wrote"
    except (OSError, TypeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        f"PASS: {action} E1 public-IR manifest and CycloneDX SBOM "
        f"(manifest sha256:{sha256_bytes(manifest_bytes)}, "
        f"sbom sha256:{sha256_bytes(sbom_bytes)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
