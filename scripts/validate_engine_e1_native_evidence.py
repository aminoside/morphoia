# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Validate the closed E1 native-core evidence profile without regeneration.

The E1 generator selected an evolving native-source tree.  Once that bounded
profile is closed, replaying its source globs against later Engine phases would
silently change the evidence domain.  This validator instead pins the
generator and the three retained evidence files byte for byte, then validates
the manifest/SBOM relationship and the profile's explicit truth boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

PROFILE = "e1-native-core"
PROJECT_VERSION = "0.0.1"
GENERATOR_PATH = "scripts/generate_engine_e1_sbom.py"
REPORT_PATH = "docs/engine/evidence/E1_NATIVE_CORE_REPORT.md"
MANIFEST_PATH = "artifacts/e1/manifest.json"
SBOM_PATH = "artifacts/sbom/engine-e1-native-core.cdx.json"
REPORT_ARTIFACT_ID = "e1-native-core-report"
ADR_ARTIFACT_ID = "adr-018-canonical-json-posix-cas"
SELF_ARTIFACT_ID = "sbom-engine-e1-native-core"
SAFE_INTEGER_MAX = 9_007_199_254_740_991
SHA256_RE = re.compile(r"[0-9a-f]{64}")

# Freeze-point constants.  The integrator updates only the affected digest(s)
# after the final, reviewed E1-profile regeneration and before publishing the
# close-out checkpoint.  Later phases must not regenerate this profile.
FROZEN_FILES = {
    GENERATOR_PATH: (
        "957ee603e6ae58635d05eca0b921c41905f09a8c4b884ef5190d1369f6e35a40"
    ),
    REPORT_PATH: (
        "6f98f5c1f6045f2df983471531ed936652266566f04d09d28b834bf64521b964"
    ),
    MANIFEST_PATH: (
        "2fee29f645651dafbeafa5d240e9148cad12334f1eac0045d5c27fb7ddee273b"
    ),
    SBOM_PATH: (
        "e098c130a535bb0a0f8d92f89c76015051d9296e3228475bfee5cc1afa214176"
    ),
}

EXPECTED_ARTIFACTS = {
    REPORT_ARTIFACT_ID: {
        "kind": "evidence-report",
        "path": REPORT_PATH,
        "media_type": "text/markdown",
        "license_expression": "CC-BY-4.0",
        "verification_status": "PASS",
        "extra_fields": {"note"},
    },
    ADR_ARTIFACT_ID: {
        "kind": "architecture-decision-record",
        "path": "spec/adr/ADR-018-canonical-json-profile-posix-cas.md",
        "media_type": "text/markdown",
        "license_expression": "CC-BY-4.0",
        "verification_status": "PASS",
        "extra_fields": set(),
    },
    SELF_ARTIFACT_ID: {
        "kind": "sbom",
        "path": SBOM_PATH,
        "media_type": "application/vnd.cyclonedx+json",
        "license_expression": "CC-BY-4.0",
        "verification_status": "PASS",
        "vulnerability_analysis_status": "NOT_RUN",
        "extra_fields": {"note", "vulnerability_analysis_status"},
    },
}
EXPECTED_ARTIFACT_ORDER = tuple(EXPECTED_ARTIFACTS)
MANIFEST_FIELDS = {
    "schema_version",
    "project",
    "generated_at",
    "manifest_document_license",
    "hash_algorithm",
    "artifacts",
}
BASE_ARTIFACT_FIELDS = {
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolved_root(root: Path) -> Path:
    absolute = Path(os.path.abspath(root))
    if absolute.is_symlink():
        raise ValueError("frozen E1 evidence root must not be a symbolic link")
    resolved = absolute.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("frozen E1 evidence root must be a directory")
    return resolved


def repository_file(root: Path, relative: str) -> Path:
    """Return a confined, regular, single-link repository file."""

    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("frozen E1 evidence path must be a non-empty string")
    if "\\" in relative:
        raise ValueError(f"unsafe frozen E1 evidence path: {relative!r}")
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute()
        or relative != posix.as_posix()
        or "." in posix.parts
        or ".." in posix.parts
    ):
        raise ValueError(f"unsafe frozen E1 evidence path: {relative!r}")

    resolved_root = _resolved_root(root)
    path = resolved_root
    for index, part in enumerate(posix.parts):
        path = path / part
        try:
            metadata = path.stat(follow_symlinks=False)
        except FileNotFoundError as error:
            raise ValueError(f"frozen E1 evidence file is missing: {relative}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(
                f"frozen E1 evidence path contains a symbolic link: {relative}"
            )
        if index < len(posix.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(
                f"frozen E1 evidence path has a non-directory component: {relative}"
            )

    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(
            f"frozen E1 evidence is not a regular non-symlink file: {relative}"
        )
    if metadata.st_nlink != 1:
        raise ValueError(f"frozen E1 evidence file is a hard-link alias: {relative}")
    path.resolve(strict=True).relative_to(resolved_root)
    return path


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-JSON numeric constant: {value}")


def _reject_float(value: str) -> NoReturn:
    raise ValueError(f"floating-point value is outside the frozen evidence profile: {value}")


def _validate_json_domain(value: Any, location: str = "document") -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError(f"lone Unicode surrogate in {location}")
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if not -SAFE_INTEGER_MAX <= value <= SAFE_INTEGER_MAX:
            raise ValueError(f"unsafe JSON integer in {location}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_domain(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_json_domain(key, f"{location} key")
            _validate_json_domain(item, f"{location}.{key}")
        return
    raise ValueError(f"unsupported JSON value in {location}: {type(value).__name__}")


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        text = path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid UTF-8 JSON: {path}") from error
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
        parse_float=_reject_float,
    )
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    _validate_json_domain(value)
    return value


def _property_map(value: Any, location: str) -> dict[str, str]:
    if not isinstance(value, list):
        raise TypeError(f"{location} properties must be an array")
    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "value"}:
            raise ValueError(f"{location} property must contain only name and value")
        name = item["name"]
        property_value = item["value"]
        if not isinstance(name, str) or not isinstance(property_value, str):
            raise TypeError(f"{location} property name and value must be strings")
        if name in result:
            raise ValueError(f"duplicate {location} property: {name}")
        result[name] = property_value
    return result


def validate_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if set(manifest) != MANIFEST_FIELDS:
        raise ValueError("frozen E1 manifest fields differ from the exact profile")
    expected_header = {
        "schema_version": "1.0.0",
        "project": "Morphoia Engine",
        "manifest_document_license": "CC-BY-4.0",
        "hash_algorithm": "sha256",
    }
    for field, expected in expected_header.items():
        if manifest.get(field) != expected:
            raise ValueError(f"frozen E1 manifest {field} must be {expected!r}")
    generated_at = manifest.get("generated_at")
    if not isinstance(generated_at, str):
        raise TypeError("frozen E1 manifest generated_at must be a date string")
    try:
        parsed_date = date.fromisoformat(generated_at)
    except ValueError as error:
        raise ValueError("frozen E1 manifest generated_at is not a calendar date") from error
    if parsed_date.isoformat() != generated_at:
        raise ValueError("frozen E1 manifest generated_at must use YYYY-MM-DD")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(EXPECTED_ARTIFACTS):
        raise ValueError("frozen E1 manifest must contain exactly three artifacts")
    identifiers = [item.get("id") if isinstance(item, dict) else None for item in artifacts]
    if identifiers != list(EXPECTED_ARTIFACT_ORDER):
        raise ValueError("frozen E1 manifest artifact order or identifiers differ")

    by_id: dict[str, dict[str, Any]] = {}
    seen_paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise TypeError("frozen E1 manifest artifact must be an object")
        identifier = artifact.get("id")
        expected = EXPECTED_ARTIFACTS.get(identifier)
        if expected is None:
            raise ValueError(f"artifact is outside the frozen E1 profile: {identifier!r}")
        expected_fields = BASE_ARTIFACT_FIELDS | expected["extra_fields"]
        if set(artifact) != expected_fields:
            raise ValueError(f"frozen E1 artifact fields differ for {identifier}")
        for field in (
            "kind",
            "path",
            "media_type",
            "license_expression",
            "verification_status",
        ):
            if artifact.get(field) != expected[field]:
                raise ValueError(f"frozen E1 artifact {identifier} has wrong {field}")
        if identifier == SELF_ARTIFACT_ID and artifact.get(
            "vulnerability_analysis_status"
        ) != "NOT_RUN":
            raise ValueError("frozen E1 manifest vulnerability status must remain NOT_RUN")
        if not isinstance(artifact.get("provenance"), str) or not artifact["provenance"]:
            raise ValueError(f"frozen E1 artifact {identifier} has empty provenance")
        if "note" in expected_fields and (
            not isinstance(artifact.get("note"), str) or not artifact["note"]
        ):
            raise ValueError(f"frozen E1 artifact {identifier} has empty note")
        size = artifact.get("size_bytes")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 <= size <= SAFE_INTEGER_MAX
        ):
            raise ValueError(f"frozen E1 artifact {identifier} has invalid size")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"frozen E1 artifact {identifier} has invalid SHA-256")
        relative = artifact["path"]
        if relative in seen_paths:
            raise ValueError("frozen E1 manifest contains a duplicate path")
        seen_paths.add(relative)
        source = repository_file(root, relative)
        if source.stat().st_size != size or sha256_file(source) != digest:
            raise ValueError(
                f"frozen E1 artifact {identifier} digest or size differs from {relative}"
            )
        by_id[identifier] = artifact

    if by_id[REPORT_ARTIFACT_ID]["sha256"] != FROZEN_FILES[REPORT_PATH]:
        raise ValueError("frozen E1 report digest differs between manifest and pin")
    if by_id[SELF_ARTIFACT_ID]["sha256"] != FROZEN_FILES[SBOM_PATH]:
        raise ValueError("frozen E1 SBOM digest differs between manifest and pin")
    return by_id


def validate_sbom(sbom: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> None:
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.5":
        raise ValueError("frozen E1 SBOM must be CycloneDX 1.5")
    if sbom.get("version") != 1:
        raise ValueError("frozen E1 SBOM version must be 1")
    if "vulnerabilities" in sbom:
        raise ValueError("frozen E1 inventory must not claim vulnerability results")

    metadata = sbom.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise TypeError("frozen E1 SBOM metadata component is missing")
    root_component = metadata["component"]
    root_ref = f"pkg:generic/morphoia-engine@{PROJECT_VERSION}?profile={PROFILE}"
    if root_component.get("bom-ref") != root_ref:
        raise ValueError("frozen E1 SBOM root reference has the wrong profile")
    if root_component.get("name") != "morphoia-engine" or root_component.get(
        "version"
    ) != PROJECT_VERSION:
        raise ValueError("frozen E1 SBOM root component identity differs")
    if root_component.get("licenses") != [{"expression": "Apache-2.0 OR MIT"}]:
        raise ValueError("frozen E1 SBOM root license differs")
    root_properties = _property_map(root_component.get("properties"), "root component")
    if root_properties.get("morphoia:profile") != PROFILE:
        raise ValueError(f"frozen E1 SBOM profile must remain {PROFILE}")
    if root_properties.get("morphoia:vulnerability-analysis-status") != "NOT_RUN":
        raise ValueError("frozen E1 SBOM vulnerability status must remain NOT_RUN")
    if root_properties.get("morphoia:sbom-content") != "source-and-declared-tools":
        raise ValueError("frozen E1 SBOM content description differs")

    components = sbom.get("components")
    if not isinstance(components, list):
        raise TypeError("frozen E1 SBOM components must be an array")
    by_ref: dict[str, dict[str, Any]] = {}
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("bom-ref"), str):
            raise TypeError("frozen E1 SBOM component has no string bom-ref")
        reference = component["bom-ref"]
        if reference in by_ref:
            raise ValueError(f"duplicate frozen E1 SBOM component reference: {reference}")
        by_ref[reference] = component

    for identifier in (REPORT_ARTIFACT_ID, ADR_ARTIFACT_ID):
        artifact = artifacts[identifier]
        reference = f"urn:morphoia:artifact:{identifier}"
        component = by_ref.get(reference)
        if component is None:
            raise ValueError(f"frozen E1 SBOM omits artifact component {identifier}")
        if component.get("type") != "file" or component.get("name") != artifact["path"]:
            raise ValueError(f"frozen E1 SBOM artifact component identity differs: {identifier}")
        if component.get("hashes") != [
            {"alg": "SHA-256", "content": artifact["sha256"]}
        ]:
            raise ValueError(f"frozen E1 SBOM artifact component hash differs: {identifier}")
        if component.get("licenses") != [
            {"expression": artifact["license_expression"]}
        ]:
            raise ValueError(f"frozen E1 SBOM artifact component license differs: {identifier}")
        properties = _property_map(component.get("properties"), f"artifact {identifier}")
        expected_properties = {
            "morphoia:artifact:id": identifier,
            "morphoia:artifact:kind": artifact["kind"],
            "morphoia:evidence:verification-status": artifact["verification_status"],
        }
        if properties != expected_properties:
            raise ValueError(
                f"frozen E1 SBOM artifact component properties differ: {identifier}"
            )
    if f"urn:morphoia:artifact:{SELF_ARTIFACT_ID}" in by_ref:
        raise ValueError("frozen E1 SBOM must not recursively contain itself as a component")

    dependencies = sbom.get("dependencies")
    if not isinstance(dependencies, list):
        raise TypeError("frozen E1 SBOM dependencies must be an array")
    dependency_refs: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != {"ref", "dependsOn"}:
            raise ValueError("frozen E1 dependency must contain only ref and dependsOn")
        reference = dependency["ref"]
        if not isinstance(reference, str) or reference in dependency_refs:
            raise ValueError("frozen E1 dependency reference is invalid or duplicate")
        if dependency["dependsOn"] != []:
            raise ValueError("frozen E1 source inventory dependencies must be empty")
        dependency_refs.add(reference)
    expected_refs = {root_ref, *by_ref}
    if dependency_refs != expected_refs:
        raise ValueError("frozen E1 SBOM dependency/component references differ")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        root = _resolved_root(root)
    except (OSError, ValueError) as error:
        return [str(error)]

    for relative, expected in FROZEN_FILES.items():
        try:
            actual = sha256_file(repository_file(root, relative))
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        if actual != expected:
            errors.append(f"frozen E1 digest differs for {relative}: {actual}")

    manifest: dict[str, Any] | None = None
    sbom: dict[str, Any] | None = None
    try:
        manifest = read_json_object(repository_file(root, MANIFEST_PATH))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"frozen E1 manifest is invalid: {error}")
    try:
        sbom = read_json_object(repository_file(root, SBOM_PATH))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"frozen E1 SBOM is invalid: {error}")

    artifacts: dict[str, dict[str, Any]] | None = None
    if manifest is not None:
        try:
            artifacts = validate_manifest(root, manifest)
        except (OSError, TypeError, ValueError) as error:
            errors.append(str(error))
    if sbom is not None and artifacts is not None:
        try:
            validate_sbom(sbom, artifacts)
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            errors.append(str(error))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    errors = validate(arguments.root)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: frozen E1 native-core generator, report, manifest, and SBOM are byte-exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
