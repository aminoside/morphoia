#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Validate the immutable E0 evidence profile without regenerating it.

E0 source selection described the closed E0 tree. Later phases add source
files, so replaying the E0 globbing generator against a later tree is not a
meaningful reproducibility check. This validator instead pins the three E0
evidence files byte for byte and checks their self-consistency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import sys
from typing import Any


FROZEN_FILES = {
    "scripts/generate_engine_sbom.py": (
        "99b865057cdb0f3283b81b4cb53be662a0eb76e9648c9eeccc73721c5fd13103"
    ),
    "artifacts/manifest.json": (
        "df017341a5bdbb43dacd8a39bcb0cc5037c2fc885e60cb568392f7c93f8a312d"
    ),
    "artifacts/sbom/engine-e0-source-native.cdx.json": (
        "30db23e7e3fc1edacce0627386152d0246f909adf0ffbefc7b441926b583414b"
    ),
}
SELF_ARTIFACT_ID = "sbom-engine-e0-source-native"
SBOM_PATH = "artifacts/sbom/engine-e0-source-native.cdx.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repository_file(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or "." in posix.parts or ".." in posix.parts:
        raise ValueError(f"unsafe frozen evidence path: {relative!r}")
    resolved_root = root.resolve(strict=True)
    path = resolved_root
    for index, part in enumerate(posix.parts):
        path = path / part
        if path.is_symlink():
            raise ValueError(f"frozen E0 evidence path contains a symbolic link: {relative}")
        if index < len(posix.parts) - 1 and not path.is_dir():
            raise ValueError(f"frozen E0 evidence has a non-directory component: {relative}")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"frozen E0 evidence is not a regular non-symlink file: {relative}")
    path.resolve(strict=True).relative_to(resolved_root)
    return path


def read_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON numeric constant: {value}")

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    for relative, expected in FROZEN_FILES.items():
        try:
            actual = sha256_file(repository_file(root, relative))
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        if actual != expected:
            errors.append(f"frozen E0 digest differs for {relative}: {actual}")

    try:
        manifest = read_json(repository_file(root, "artifacts/manifest.json"))
        sbom_path = repository_file(root, SBOM_PATH)
        sbom = read_json(sbom_path)
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            errors.append("frozen E0 manifest artifacts must be an array")
        else:
            self_entries = [item for item in artifacts if item.get("id") == SELF_ARTIFACT_ID]
            if len(self_entries) != 1:
                errors.append("frozen E0 manifest must contain exactly one SBOM self entry")
            else:
                entry = self_entries[0]
                if entry.get("path") != SBOM_PATH:
                    errors.append("frozen E0 SBOM self entry has the wrong path")
                if entry.get("sha256") != sha256_file(sbom_path):
                    errors.append("frozen E0 SBOM self entry has the wrong SHA-256")
                if entry.get("size_bytes") != sbom_path.stat().st_size:
                    errors.append("frozen E0 SBOM self entry has the wrong size")
        root_component = sbom.get("metadata", {}).get("component", {})
        properties = {
            item.get("name"): item.get("value")
            for item in root_component.get("properties", [])
            if isinstance(item, dict)
        }
        if properties.get("morphoia:profile") != "e0-source-native":
            errors.append("frozen E0 SBOM profile is not e0-source-native")
        if properties.get("morphoia:vulnerability-analysis-status") != "NOT_RUN":
            errors.append("frozen E0 vulnerability status must remain NOT_RUN")
    except (AttributeError, OSError, TypeError, ValueError) as error:
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
    print("PASS: frozen E0 generator, manifest, and source SBOM are byte-exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
