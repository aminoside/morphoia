#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Replay the closed E1 public-IR evidence from its immutable Git snapshot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

FREEZE_PATH = Path("spec/evidence/e1-public-ir-freeze.json")
FREEZE_SCHEMA_PATH = Path("spec/evidence/e1-public-ir-freeze.schema.json")
FREEZE_SHA256 = "fd72827867859abde129612e03adc5c4c6c2fb07ed77a18e845de84dae9dc1be"
FREEZE_SCHEMA_SHA256 = (
    "ff8c49f3b12f52495c07cbfc148e0ca9f383b5063f6d4920a98fdfb3eafdaf65"
)
MAX_JSON_BYTES = 1 << 20
MAX_BLOB_BYTES = 32 << 20
MAX_SNAPSHOT_BYTES = 64 << 20
GIT_TIMEOUT_SECONDS = 30
EXPECTED_SCHEMA_ID = (
    "https://morphoia.org/schemas/e1-public-ir-freeze-1.0.schema.json"
)


class FreezeValidationError(RuntimeError):
    """The frozen evidence declaration or snapshot is not exact."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FreezeValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise FreezeValidationError(f"non-finite JSON number: {value}")


def _reject_unsupported_json(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        raise FreezeValidationError(f"floating-point JSON value at {path}")
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise FreezeValidationError(f"surrogate code point at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsupported_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_unsupported_json(key, f"{path}.<key>")
            _reject_unsupported_json(item, f"{path}.{key}")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    raise FreezeValidationError(f"unsupported JSON value at {path}")


def _read_confined_file(root: Path, relative: Path, maximum: int) -> bytes:
    if relative.is_absolute() or not relative.parts:
        raise FreezeValidationError(f"unsafe repository path: {relative}")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise FreezeValidationError(f"unsafe repository path: {relative}")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | nofollow
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(root, directory_flags))
        for part in relative.parts[:-1]:
            descriptors.append(os.open(part, directory_flags, dir_fd=descriptors[-1]))
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | nofollow,
            dir_fd=descriptors[-1],
        )
        descriptors.append(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise FreezeValidationError(f"unsafe repository file: {relative}")
        if metadata.st_size > maximum:
            raise FreezeValidationError(f"repository file exceeds limit: {relative}")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            if not chunk:
                raise FreezeValidationError(
                    f"repository file changed while reading: {relative}"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise FreezeValidationError(f"repository file exceeds snapshot: {relative}")
        after = os.fstat(descriptor)
        before_identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity:
            raise FreezeValidationError(f"repository file changed while reading: {relative}")
        return b"".join(chunks)
    except OSError as error:
        raise FreezeValidationError(f"cannot safely read repository file: {relative}") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_strict_json(root: Path, relative: Path, expected_sha256: str) -> dict[str, Any]:
    content = _read_confined_file(root, relative, MAX_JSON_BYTES)
    observed = hashlib.sha256(content).hexdigest()
    if observed != expected_sha256:
        raise FreezeValidationError(
            f"{relative} SHA-256 mismatch: expected {expected_sha256}, observed {observed}"
        )
    try:
        text = content.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreezeValidationError(f"invalid JSON in {relative}: {error}") from error
    _reject_unsupported_json(value)
    if not isinstance(value, dict):
        raise FreezeValidationError(f"JSON root must be an object: {relative}")
    return value


def load_declaration(root: Path) -> dict[str, Any]:
    schema = _read_strict_json(root, FREEZE_SCHEMA_PATH, FREEZE_SCHEMA_SHA256)
    if schema.get("$id") != EXPECTED_SCHEMA_ID:
        raise FreezeValidationError("frozen evidence schema ID mismatch")
    declaration = _read_strict_json(root, FREEZE_PATH, FREEZE_SHA256)
    if declaration.get("$schema") != "./e1-public-ir-freeze.schema.json":
        raise FreezeValidationError("frozen evidence schema reference mismatch")
    if declaration.get("schema_version") != "1.0.0":
        raise FreezeValidationError("frozen evidence schema version mismatch")
    if declaration.get("profile") != "e1-public-ir-core-cpu":
        raise FreezeValidationError("frozen evidence profile mismatch")
    if declaration.get("status") != "FROZEN":
        raise FreezeValidationError("frozen evidence status mismatch")
    return declaration


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    unsafe_exact = {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_ASKPASS",
        "GIT_COMMON_DIR",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PROXY_COMMAND",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_WORK_TREE",
        "SSH_ASKPASS",
    }
    for key in tuple(environment):
        if (
            key in unsafe_exact
            or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
        ):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    return environment


def _git_argv(root: Path, arguments: list[str]) -> list[str]:
    return [
        "git",
        "--no-lazy-fetch",
        "--no-replace-objects",
        "--no-optional-locks",
        "-c",
        "protocol.allow=never",
        "-C",
        str(root),
        *arguments,
    ]


def _git(root: Path, arguments: list[str], *, check: bool = True) -> bytes:
    completed = subprocess.run(
        _git_argv(root, arguments),
        check=False,
        capture_output=True,
        env=_git_environment(),
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if check and completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise FreezeValidationError(f"local Git object check failed: {error}")
    return completed.stdout


def _safe_git_path(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise FreezeValidationError("non-UTF-8 path in frozen Git tree") from error
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise FreezeValidationError(f"unsafe path in frozen Git tree: {value!r}")
    return value


def _parse_tree(raw: bytes) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.split(b" ")
        except ValueError as error:
            raise FreezeValidationError("malformed NUL-delimited Git tree listing") from error
        path = _safe_git_path(raw_path)
        if path in seen:
            raise FreezeValidationError(f"duplicate path in frozen Git tree: {path}")
        seen.add(path)
        if object_type != b"blob" or mode not in {b"100644", b"100755"}:
            raise FreezeValidationError(f"unsupported Git tree entry: {path}")
        try:
            object_text = object_id.decode("ascii", errors="strict")
        except UnicodeDecodeError as error:
            raise FreezeValidationError(f"invalid object ID for {path}") from error
        if len(object_text) != 40 or any(
            character not in "0123456789abcdef" for character in object_text
        ):
            raise FreezeValidationError(f"invalid object ID for {path}")
        entries.append(
            {"path": path, "mode": mode.decode("ascii"), "blob": object_text}
        )
    return entries


def _read_blobs(root: Path, entries: list[dict[str, str]]) -> dict[str, bytes]:
    request = b"".join(entry["blob"].encode("ascii") + b"\n" for entry in entries)
    completed = subprocess.run(
        _git_argv(root, ["cat-file", "--batch"]),
        input=request,
        check=False,
        capture_output=True,
        env=_git_environment(),
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise FreezeValidationError(f"local Git blob read failed: {error}")

    output = completed.stdout
    if len(output) > MAX_SNAPSHOT_BYTES:
        raise FreezeValidationError("frozen Git blob response exceeds snapshot limit")
    offset = 0
    result: dict[str, bytes] = {}
    for entry in entries:
        line_end = output.find(b"\n", offset)
        if line_end < 0:
            raise FreezeValidationError("truncated Git batch response")
        header = output[offset:line_end]
        offset = line_end + 1
        try:
            object_id, object_type, raw_size = header.split(b" ")
            size = int(raw_size)
        except (ValueError, OverflowError) as error:
            raise FreezeValidationError("malformed Git batch response") from error
        if (
            object_id.decode("ascii", errors="strict") != entry["blob"]
            or object_type != b"blob"
            or size < 0
            or size > MAX_BLOB_BYTES
        ):
            raise FreezeValidationError(f"unexpected Git blob response for {entry['path']}")
        end = offset + size
        if end >= len(output) or output[end : end + 1] != b"\n":
            raise FreezeValidationError(f"truncated Git blob for {entry['path']}")
        result[entry["path"]] = output[offset:end]
        offset = end + 1
    if offset != len(output):
        raise FreezeValidationError("unexpected trailing Git batch data")
    return result


def _verify_commit(root: Path, declaration: dict[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, bytes]]:
    snapshot = declaration["git_snapshot"]
    commit = snapshot["commit"]

    if _git(root, ["rev-parse", "--is-shallow-repository"]).strip() != b"false":
        raise FreezeValidationError("full Git history is required for frozen evidence replay")
    if _git(root, ["cat-file", "-t", commit]).strip() != b"commit":
        raise FreezeValidationError("frozen Git object is not a commit")
    if subprocess.run(
        _git_argv(root, ["merge-base", "--is-ancestor", commit, "HEAD"]),
        check=False,
        capture_output=True,
        env=_git_environment(),
        timeout=GIT_TIMEOUT_SECONDS,
    ).returncode != 0:
        raise FreezeValidationError("frozen commit is not an ancestor of HEAD")

    commit_bytes = _git(root, ["cat-file", "commit", commit])
    if len(commit_bytes) != snapshot["commit_object_size"]:
        raise FreezeValidationError("frozen commit object size mismatch")
    if hashlib.sha256(commit_bytes).hexdigest() != snapshot["commit_object_sha256"]:
        raise FreezeValidationError("frozen commit object SHA-256 mismatch")
    header = commit_bytes.split(b"\n\n", 1)[0].splitlines()
    tree_lines = [line[5:].decode("ascii") for line in header if line.startswith(b"tree ")]
    parent_lines = [
        line[7:].decode("ascii") for line in header if line.startswith(b"parent ")
    ]
    if tree_lines != [snapshot["tree"]] or parent_lines != snapshot["parents"]:
        raise FreezeValidationError("frozen commit topology mismatch")

    tree_bytes = _git(root, ["cat-file", "tree", snapshot["tree"]])
    if len(tree_bytes) != snapshot["tree_object_size"]:
        raise FreezeValidationError("frozen tree object size mismatch")
    if hashlib.sha256(tree_bytes).hexdigest() != snapshot["tree_object_sha256"]:
        raise FreezeValidationError("frozen tree object SHA-256 mismatch")

    listing = _git(root, ["ls-tree", "-rz", "--full-tree", commit])
    if hashlib.sha256(listing).hexdigest() != snapshot["ls_tree_z_sha256"]:
        raise FreezeValidationError("frozen tree listing SHA-256 mismatch")
    entries = _parse_tree(listing)
    if len(entries) != snapshot["entry_count"]:
        raise FreezeValidationError("frozen tree entry count mismatch")

    blobs = _read_blobs(root, entries)
    aggregate = hashlib.sha256()
    for entry in entries:
        content = blobs[entry["path"]]
        aggregate.update(entry["mode"].encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(entry["path"].encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(len(content)).encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(hashlib.sha256(content).hexdigest().encode("ascii"))
        aggregate.update(b"\n")
    if aggregate.hexdigest() != snapshot["content_tree_sha256"]:
        raise FreezeValidationError("frozen content tree SHA-256 mismatch")

    by_path = {entry["path"]: entry for entry in entries}
    if len(declaration["anchors"]) != 9:
        raise FreezeValidationError("frozen anchor count mismatch")
    anchor_paths: set[str] = set()
    for anchor in declaration["anchors"]:
        path = anchor["path"]
        if path in anchor_paths:
            raise FreezeValidationError(f"duplicate frozen anchor: {path}")
        anchor_paths.add(path)
        if by_path.get(path) != {
            "path": path,
            "mode": anchor["mode"],
            "blob": anchor["blob"],
        }:
            raise FreezeValidationError(f"frozen anchor Git metadata mismatch: {path}")
        content = blobs[path]
        if len(content) != anchor["size"]:
            raise FreezeValidationError(f"frozen anchor size mismatch: {path}")
        if hashlib.sha256(content).hexdigest() != anchor["sha256"]:
            raise FreezeValidationError(f"frozen anchor SHA-256 mismatch: {path}")

    fixture = declaration["fixture_tree"]
    fixture_prefix = f"{fixture['root']}/"
    fixture_paths = sorted(path for path in blobs if path.startswith(fixture_prefix))
    if len(fixture_paths) != fixture["file_count"]:
        raise FreezeValidationError("frozen fixture file count mismatch")
    fixture_aggregate = hashlib.sha256()
    for path in fixture_paths:
        relative = path.removeprefix(fixture_prefix)
        if not relative:
            raise FreezeValidationError("invalid frozen fixture path")
        fixture_aggregate.update(relative.encode("utf-8"))
        fixture_aggregate.update(b"\0")
        fixture_aggregate.update(hashlib.sha256(blobs[path]).hexdigest().encode("ascii"))
        fixture_aggregate.update(b"\n")
    if fixture_aggregate.hexdigest() != fixture["aggregate_sha256"]:
        raise FreezeValidationError("frozen fixture aggregate SHA-256 mismatch")

    counts = declaration["counts"]
    manifest = json.loads(blobs["artifacts/manifests/engine-e1-public-ir.json"])
    sbom = json.loads(blobs["artifacts/sbom/engine-e1-public-ir.cdx.json"])
    traceability = json.loads(blobs["spec/evidence/e1-public-ir-traceability.json"])
    trace_entries = traceability.get("entries", [])
    status_counts: dict[str, int] = {}
    for trace_entry in trace_entries:
        status = trace_entry.get("status")
        status_counts[status] = status_counts.get(status, 0) + 1
    if (
        len(manifest.get("artifacts", [])) != counts["manifest_artifacts"]
        or len(sbom.get("components", [])) != counts["sbom_components"]
        or len(trace_entries) != counts["traceability_entries"]
        or status_counts.get("PASS", 0) != counts["traceability_pass"]
        or status_counts.get("NOT_RUN", 0) != counts["traceability_not_run"]
        or set(status_counts) != {"PASS", "NOT_RUN"}
    ):
        raise FreezeValidationError("frozen profile count/status mismatch")
    return commit, entries, blobs


def _materialize_blobs(
    entries: list[dict[str, str]],
    blobs: dict[str, bytes],
    destination: Path,
) -> None:
    by_path = {entry["path"]: entry for entry in entries}
    if set(blobs) != set(by_path):
        raise FreezeValidationError("blob set differs from frozen Git tree")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    for path in sorted(by_path):
        entry = by_path[path]
        target = destination.joinpath(*PurePosixPath(path).parts)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            0o700 if entry["mode"] == "100755" else 0o600,
        )
        try:
            os.fchmod(descriptor, 0o755 if entry["mode"] == "100755" else 0o644)
            content = blobs[path]
            offset = 0
            while offset < len(content):
                written = os.write(descriptor, content[offset:])
                if written <= 0:
                    raise FreezeValidationError(f"cannot materialize frozen blob: {path}")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _run_snapshot_command(snapshot: Path, arguments: list[str]) -> str:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("PYTHON"):
            environment.pop(key, None)
    environment.pop("MORPHOIA_ENGINE_LIBRARY", None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-P", "-s", "-B", "-X", "utf8", *arguments],
        cwd=snapshot,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=120,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise FreezeValidationError(
            f"frozen snapshot command failed: {' '.join(arguments)}\n{output[-4000:]}"
        )
    return output


def _verify_materialized_snapshot(
    snapshot: Path,
    entries: list[dict[str, str]],
    blobs: dict[str, bytes],
) -> None:
    expected = {entry["path"]: entry for entry in entries}
    observed: set[str] = set()
    for current, directories, filenames in os.walk(snapshot, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *filenames]:
            path = current_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise FreezeValidationError("frozen replay created a symbolic link")
            if name in filenames and not stat.S_ISREG(metadata.st_mode):
                raise FreezeValidationError("frozen replay created a non-regular file")
        for name in filenames:
            path = current_path / name
            relative = path.relative_to(snapshot).as_posix()
            observed.add(relative)
            entry = expected.get(relative)
            if entry is None:
                raise FreezeValidationError(
                    f"frozen replay created an unlisted file: {relative}"
                )
            content = _read_confined_file(snapshot, Path(relative), MAX_BLOB_BYTES)
            if content != blobs[relative]:
                raise FreezeValidationError(
                    f"frozen replay changed a materialized blob: {relative}"
                )
            expected_mode = 0o755 if entry["mode"] == "100755" else 0o644
            if stat.S_IMODE(path.stat().st_mode) != expected_mode:
                raise FreezeValidationError(
                    f"frozen replay changed a materialized mode: {relative}"
                )
    if observed != set(expected):
        raise FreezeValidationError("frozen replay removed a materialized blob")


def _verify_runtime(declaration: dict[str, Any]) -> None:
    replay = declaration["replay"]
    observed_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if observed_python not in replay["python_versions"]:
        raise FreezeValidationError(
            "frozen replay Python version mismatch: "
            f"expected one of {replay['python_versions']}, observed {observed_python}"
        )
    for distribution, expected_version in replay["distributions"].items():
        try:
            observed_version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as error:
            raise FreezeValidationError(
                f"frozen replay distribution missing: {distribution}"
            ) from error
        if observed_version != expected_version:
            raise FreezeValidationError(
                "frozen replay distribution version mismatch: "
                f"{distribution} expected {expected_version}, observed {observed_version}"
            )


def validate(root: Path, *, replay: bool = True) -> dict[str, int | str]:
    root = root.resolve(strict=True)
    top_level = _git(root, ["rev-parse", "--show-toplevel"]).decode().strip()
    if Path(top_level).resolve(strict=True) != root:
        raise FreezeValidationError("--root must be the Git worktree root")

    declaration = load_declaration(root)
    _verify_runtime(declaration)
    commit, entries, blobs = _verify_commit(root, declaration)
    if replay:
        with tempfile.TemporaryDirectory(prefix="morphoia-frozen-public-ir-") as directory:
            snapshot = Path(directory) / "snapshot"
            snapshot.mkdir(mode=0o700)
            _materialize_blobs(entries, blobs, snapshot)
            _run_snapshot_command(
                snapshot,
                [
                    str(snapshot / "scripts/generate_engine_e1_public_ir_sbom.py"),
                    "--root",
                    str(snapshot),
                    "--check",
                ],
            )
            test_output = _run_snapshot_command(
                snapshot,
                [str(snapshot / "tests/test_e1_public_ir_evidence.py"), "-v"],
            )
            expected_tests = declaration["counts"]["historical_evidence_tests"]
            if f"Ran {expected_tests} tests" not in test_output or "OK" not in test_output:
                raise FreezeValidationError("historical evidence test count/result mismatch")
            _verify_materialized_snapshot(snapshot, entries, blobs)

    return {
        "commit": commit,
        "entries": len(entries),
        "historical_tests": declaration["counts"]["historical_evidence_tests"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository worktree root",
    )
    arguments = parser.parse_args()
    try:
        result = validate(arguments.root)
    except (FreezeValidationError, OSError, subprocess.SubprocessError) as error:
        print(f"frozen-public-ir: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "frozen-public-ir: PASS "
        f"(commit {result['commit']}, {result['entries']} blobs, "
        f"{result['historical_tests']} historical tests)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
