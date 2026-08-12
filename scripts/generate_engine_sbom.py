#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Generate the deterministic CycloneDX E0 source/native-profile SBOM."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any
import urllib.parse
import uuid


SELF_ARTIFACT_ID = "sbom-engine-e0-source-native"
PROFILE = "e0-source-native"
PROJECT_VERSION = "0.0.1"
LOCK_FILES = (
    "requirements/cmake-e0.lock",
    "requirements/engine-ci.lock",
    "requirements/report-ci.lock",
    "requirements/reuse-build-e0.lock",
    "requirements/reuse-e0.lock",
)
LICENSE_FILES = {
    "LICENSE": "MIT",
    "LICENSE-MIT": "MIT",
    "LICENSE-APACHE": "Apache-2.0",
    "LICENSES/Apache-2.0.txt": "Apache-2.0",
    "LICENSES/CC-BY-4.0.txt": "CC-BY-4.0",
    "LICENSES/LicenseRef-Morphoia-Baseline.txt": "LicenseRef-Morphoia-Baseline",
    "LICENSES/LicenseRef-Morphoia-Brand-Assets.txt": "LicenseRef-Morphoia-Brand-Assets",
    "LICENSES/MIT.txt": "MIT",
    "LICENSES/OFL-1.1.txt": "OFL-1.1",
    "NOTICE": "CC-BY-4.0",
}
SOURCE_GLOBS = (
    "CMakeLists.txt",
    "CMakePresets.json",
    "cmake/*.cmake",
    "cmake/*.cmake.in",
    "cmake/*.map",
    "cpp/**/*.h",
    "cpp/**/*.c",
    "cpp/**/*.cc",
    "cpp/**/*.cpp",
    "scripts/bootstrap-engine.sh",
    "scripts/run-engine-sanitizers.sh",
    "tests/native/**/*.c",
    "tests/native/**/*.cc",
    "tests/native/**/*.cpp",
    "tests/native/**/CMakeLists.txt",
)
PACKAGE_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\?$")
HASH_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})(?:\s*\\)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def component_hash(path: Path) -> list[dict[str, str]]:
    return [{"alg": "SHA-256", "content": sha256_file(path)}]


def safe_root_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("file path must be a non-empty string")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "." in posix.parts:
        raise ValueError(f"unsafe repository path: {relative!r}")
    path = root.joinpath(*posix.parts)
    if not path.is_file():
        raise ValueError(f"required SBOM input is not a regular file: {relative}")
    if path.is_symlink():
        raise ValueError(f"SBOM input must not be a symbolic link: {relative}")
    try:
        path.resolve(strict=True).relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"SBOM input escapes repository root: {relative}") from error
    return path


def license_choice(expression: str) -> list[dict[str, str]]:
    if expression == "NOASSERTION":
        return [{"license": {"name": "NOASSERTION"}}]
    return [{"expression": expression}]


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
        "hashes": component_hash(path),
        "licenses": license_choice(license_expression),
        "properties": sorted(properties, key=lambda item: (item["name"], item["value"])),
    }


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_locks(root: Path) -> dict[tuple[str, str], dict[str, set[str]]]:
    packages: dict[tuple[str, str], dict[str, set[str]]] = {}
    for relative in LOCK_FILES:
        path = safe_root_file(root, relative)
        current: tuple[str, str] | None = None
        expecting_hash = False
        for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            package_match = PACKAGE_RE.fullmatch(line)
            if package_match:
                if expecting_hash and current is not None and not packages[current]["hashes"]:
                    raise ValueError(
                        f"locked package has no SHA-256 digest before {relative}:{number}"
                    )
                current = (normalize_package_name(package_match.group(1)), package_match.group(2))
                entry = packages.setdefault(current, {"hashes": set(), "locks": set()})
                entry["locks"].add(relative)
                expecting_hash = True
                continue
            hash_match = HASH_RE.fullmatch(line)
            if hash_match and current is not None:
                packages[current]["hashes"].add(hash_match.group(1))
                expecting_hash = False
                continue
            raise ValueError(f"unsupported lock syntax at {relative}:{number}: {raw_line!r}")
    for (name, version), values in packages.items():
        if not values["hashes"]:
            raise ValueError(f"locked package has no SHA-256 digest: {name}=={version}")
    return packages


def collect_source_files(root: Path) -> list[str]:
    values: set[str] = set()
    for pattern in SOURCE_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                values.add(path.relative_to(root).as_posix())
    if not values:
        raise ValueError("native source profile did not select any files")
    return sorted(values)


def validate_manifest(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("manifest_document_license") != "CC-BY-4.0":
        raise ValueError("artifact manifest must declare manifest_document_license=CC-BY-4.0")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("artifact manifest artifacts must be an array")
    selected: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ValueError(f"artifact {index} must be an object")
        identifier = artifact.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError(f"artifact {index} has a missing or duplicate id")
        identifiers.add(identifier)
        if identifier == SELF_ARTIFACT_ID:
            continue
        relative = artifact.get("path")
        digest = artifact.get("sha256")
        size = artifact.get("size_bytes")
        license_expression = artifact.get("license_expression")
        if not all(
            isinstance(value, str) and value
            for value in (relative, digest, license_expression)
        ):
            raise ValueError(f"artifact {identifier} lacks path, hash, or license expression")
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"artifact {identifier} has an invalid SHA-256 digest")
        path = safe_root_file(root, relative)
        if sha256_file(path) != digest or path.stat().st_size != size:
            raise ValueError(f"artifact {identifier} digest or size does not match {relative}")
        selected.append(artifact)
    return selected


def build_bom(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = read_json(manifest_path)
    artifacts = validate_manifest(root, manifest)
    packages = parse_locks(root)

    components: list[dict[str, Any]] = []
    for artifact in artifacts:
        properties = [
            {"name": "morphoia:artifact:id", "value": artifact["id"]},
            {"name": "morphoia:artifact:kind", "value": artifact["kind"]},
            {
                "name": "morphoia:evidence:verification-status",
                "value": artifact["verification_status"],
            },
        ]
        components.append(
            file_component(
                root,
                artifact["path"],
                f"urn:morphoia:artifact:{artifact['id']}",
                artifact["license_expression"],
                properties,
            )
        )

    for relative, expression in sorted(LICENSE_FILES.items()):
        components.append(
            file_component(
                root,
                relative,
                f"urn:morphoia:license-file:{urllib.parse.quote(relative, safe='')}",
                expression,
                [{"name": "morphoia:role", "value": "license-or-notice-file"}],
            )
        )

    for relative in LOCK_FILES:
        components.append(
            file_component(
                root,
                relative,
                f"urn:morphoia:lock:{urllib.parse.quote(relative, safe='')}",
                "Apache-2.0 OR MIT",
                [
                    {"name": "morphoia:profile", "value": PROFILE},
                    {"name": "morphoia:role", "value": "hashed-python-lock"},
                ],
            )
        )

    for relative in collect_source_files(root):
        components.append(
            file_component(
                root,
                relative,
                f"urn:morphoia:native-source:{urllib.parse.quote(relative, safe='')}",
                "Apache-2.0 OR MIT",
                [{"name": "morphoia:role", "value": "native-source"}],
            )
        )

    for (name, version), values in sorted(packages.items()):
        purl = f"pkg:pypi/{urllib.parse.quote(name)}@{urllib.parse.quote(version)}"
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
                "licenses": license_choice("NOASSERTION"),
                "properties": [
                    {
                        "name": "morphoia:license-review-status",
                        "value": "NOT_RUN",
                    },
                    {
                        "name": "morphoia:provisioning",
                        "value": "lock-only-not-redistributed-by-sbom",
                    },
                    {
                        "name": "morphoia:source-locks",
                        "value": ",".join(sorted(values["locks"])),
                    },
                ],
            }
        )

    components.sort(key=lambda component: component["bom-ref"])
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
    root_ref = f"pkg:generic/morphoia-engine@{PROJECT_VERSION}"
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
                "name": "morphoia-engine",
                "version": PROJECT_VERSION,
                "licenses": license_choice("Apache-2.0 OR MIT"),
                "externalReferences": [
                    {
                        "type": "vcs",
                        "url": "https://github.com/Aminoside/morphoia",
                    }
                ],
                "properties": [
                    {"name": "morphoia:profile", "value": PROFILE},
                    {"name": "morphoia:sbom-content", "value": "source-and-declared-tools"},
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
            {"ref": root_ref, "dependsOn": []},
            *({"ref": component["bom-ref"], "dependsOn": []} for component in components),
        ],
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            Path(temporary_name).unlink()
        except FileNotFoundError:
            pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/manifest.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/sbom/engine-e0-source-native.cdx.json"),
    )
    parser.add_argument("--check", action="store_true", help="fail if output is not exact")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    root = arguments.root.resolve()
    manifest = arguments.manifest if arguments.manifest.is_absolute() else root / arguments.manifest
    output = arguments.output if arguments.output.is_absolute() else root / arguments.output
    try:
        content = canonical_json(build_bom(root, manifest))
        if arguments.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != content:
                print(
                    f"FAIL: SBOM is missing or differs from deterministic output: {output}",
                    file=sys.stderr,
                )
                return 1
        else:
            write_atomic(output, content)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    verb = "matches" if arguments.check else "wrote"
    print(f"PASS: {verb} deterministic CycloneDX SBOM {output} (sha256:{digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
