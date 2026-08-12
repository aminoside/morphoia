#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Execute the frozen 20-graph public Engine IR corpus through the native ABI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

from morphoia._engine_native import NativeEngine
from morphoia.engine_ir import replay_manifest, validate_manifest
from morphoia.engine_ir_contract import load_json_strict


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _open_corpus_root(root: Path) -> int:
    """Open an absolute, owner-controlled corpus root without following aliases."""

    if not root.is_absolute():
        raise ValueError("corpus root must be absolute")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in root.parts[1:]:
            if component in ("", ".", ".."):
                raise ValueError("corpus root has an unsafe path component")
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise ValueError(
                "corpus root must be owner-controlled and not group/world writable"
            )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_confined(root: Path, relative: object) -> bytes:
    if not isinstance(relative, str):
        raise TypeError("corpus index path must be a string")
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(
        component in ("", ".", "..") for component in path.parts
    ):
        raise ValueError(f"unsafe corpus index path: {relative!r}")
    root_descriptor = _open_corpus_root(root)
    descriptor = root_descriptor
    try:
        for component in path.parts[:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            if descriptor != root_descriptor:
                os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(
            path.parts[-1],
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=descriptor,
        )
        try:
            metadata = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid()
                or metadata.st_size > 1_048_576
            ):
                raise ValueError(f"unsafe corpus fixture metadata: {relative}")
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = os.read(file_descriptor, min(65_536, 1_048_577 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > 1_048_576:
                    raise ValueError(f"corpus fixture exceeds byte limit: {relative}")
                chunks.append(chunk)
            after = os.fstat(file_descriptor)
            if (
                (
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                )
                != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                )
            ):
                raise ValueError(f"corpus fixture changed during snapshot: {relative}")
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    finally:
        if descriptor != root_descriptor:
            os.close(descriptor)
        os.close(root_descriptor)


def validate_corpus(root: Path, library: Path) -> dict[str, object]:
    if not root.is_absolute():
        root = (Path.cwd() / root).absolute()
    root_descriptor = _open_corpus_root(root)
    os.close(root_descriptor)
    index = load_json_strict(_read_confined(root, "index.json"))
    if (
        index.get("format") != "morphoia.engine.ir-corpus"
        or index.get("format_version") != "0.1.0"
        or index.get("canonical_profile") != "morphoia.canonical-json.profile1"
    ):
        raise ValueError("public IR corpus index identity is unsupported")
    entries = index.get("entries")
    if not isinstance(entries, list) or len(entries) != 20:
        raise ValueError("public IR corpus must contain exactly 20 indexed entries")
    unique_fields = (
        "id",
        "input",
        "golden",
        "replay",
        "input_sha256",
        "content_sha256",
        "replay_sha256",
    )
    if any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("every public IR corpus entry must be an object")
    for field in unique_fields:
        values = [entry.get(field) for entry in entries]
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError(f"public IR corpus entry field {field} must be a string")
        if len(set(values)) != len(values):
            raise ValueError(f"public IR corpus entry field {field} must be unique")
    entry_results: list[dict[str, object]] = []
    with NativeEngine(library) as engine, tempfile.TemporaryDirectory(
        prefix="morphoia-public-ir-replay-"
    ) as temporary_text:
        temporary = Path(temporary_text)
        os.chmod(temporary, 0o700)
        for ordinal, entry in enumerate(entries, start=1):
            entry_id = entry["id"]
            input_path = root / entry["input"]
            input_bytes = _read_confined(root, entry["input"])
            golden_bytes = _read_confined(root, entry["golden"])
            replay_bytes = _read_confined(root, entry["replay"])
            observed_files = {
                "input_sha256": _sha256(input_bytes),
                "content_sha256": _sha256(golden_bytes),
                "replay_sha256": _sha256(replay_bytes),
            }
            for key, observed in observed_files.items():
                if entry[key] != observed:
                    raise ValueError(f"{entry_id}: {key} differs from corpus index")
            manifest = validate_manifest(input_bytes, engine=engine)
            if manifest.canonical_content != golden_bytes:
                raise ValueError(f"{entry_id}: native canonical bytes differ from golden")
            if manifest.content_sha256 != entry["content_sha256"]:
                raise ValueError(f"{entry_id}: native content identity differs from index")

            workspace = temporary / f"workspace-a-{ordinal:02d}"
            second_workspace = temporary / f"workspace-b-{ordinal:02d}"
            workspace.mkdir(mode=0o700)
            second_workspace.mkdir(mode=0o700)
            first = replay_manifest(
                replay_bytes,
                input_path,
                workspace_root=workspace,
                engine=engine,
            )
            resumed = replay_manifest(
                replay_bytes,
                input_path,
                workspace_root=workspace,
                engine=engine,
            )
            independent = replay_manifest(
                replay_bytes,
                input_path,
                workspace_root=second_workspace,
                engine=engine,
            )
            if (
                first.resumed
                or not resumed.resumed
                or independent.resumed
                or first.operation_key != resumed.operation_key
                or first.operation_key != independent.operation_key
                or first.canonical_content != independent.canonical_content
            ):
                raise ValueError(f"{entry_id}: checkpoint execute/resume invariant failed")
            entry_results.append(
                {
                    "id": entry_id,
                    "content_sha256": manifest.content_sha256,
                    "input_sha256": entry["input_sha256"],
                    "canonical_content_size": len(manifest.canonical_content),
                    "operation_key": first.operation_key,
                    "status": "PASS",
                }
            )
    return {
        "schema_version": "1.0.0",
        "profile": "core-cpu-public-ir-0.1.0",
        "canonical_profile": "morphoia.canonical-json.profile1",
        "entry_count": len(entry_results),
        "entries": entry_results,
        "status": "PASS",
        "large_payload_over_2_gib": "NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("tests/fixtures/engine-ir/0.1.0"),
    )
    parser.add_argument("--library", type=Path, required=True)
    arguments = parser.parse_args()
    report = validate_corpus(arguments.root, arguments.library)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
