#!/usr/bin/env python3
"""Build and verify the private P2c v2 pre-execution continuity package.

The tool has two deliberately separate freeze points:

* ``build`` creates a deterministic, owner-private input bundle before any v2
  plan or work ID exists.  It preserves the three P2a parents and the four v1
  predecessor chains, and embeds an exact ``git archive`` of the selected
  pre-execution commit.
* ``freeze-continuity`` runs only after the bound pre-execution commit has been
  published and independently confirmed, then after the four deterministic v2
  plans have been created but before the first geometry child.  It emits the
  exact private continuity manifest consumed by the scientific projector plus
  a detached, domain-separated owner signature.  Publication confirmation is
  an orchestrator precondition; this local tool does not claim to prove it.

Neither command performs geometry work.  Private keys are always external to
the bundle.  CLI output is restricted to stable action/error codes and never
contains paths, source identities, hashes, signatures, or key material.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

INPUT_SCHEMA = "MVX-P2C-V2-CONTINUITY-INPUT"
PREFREEZE_SCHEMA = "MVX-P2C-V2-PRIVATE-PREFREEZE-BUNDLE"
CONTINUITY_SCHEMA = "MVX-P2C-PRIVATE-CAMPAIGN-CONTINUITY"
SIGNATURE_SCHEMA = "MVX-P2C-V2-DETACHED-CONTINUITY-SIGNATURE"
SCHEMA_VERSION = "1.0.0"
CAMPAIGN_ID = "P2C-PILOT3-2026-08-06"
CAMPAIGN_VERSION = "2.1.0"
COMPROMISED_V2_SIGNER_PUBLIC_KEY = (
    "c060c44469a0b0be1732943056a7c10b53d2efd77f362c166957f8d180ec429c"
)
V1_ROOT = "f45509de33b10e7a877d264c6b99079f7fffe56b9ce30795f5916e1971222722"
V1_RUNNER_SHA256 = "adb7fe9aef50f4473a5220788004ecebaec9bfd5d81be478b14132f774534f02"

PREFREEZE_SIGNATURE_DOMAIN = "MVX-P2C-V2-PREFREEZE-BUNDLE-ED25519-1"
CONTINUITY_SIGNATURE_DOMAIN = "MVX-P2C-V2-CONTINUITY-MANIFEST-ED25519-1"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = REPOSITORY_ROOT / "tmp"
MAX_INPUT_BYTES = 768 * 1024 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
HEX_SIGNATURE = re.compile(r"^[0-9a-f]{128}$")
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")

CODE_BINDING_NAMES = (
    "preregistration",
    "projection_contexts",
    "v1_disposition",
    "runner",
    "runner_test",
    "signer",
    "signer_test",
    "projector",
    "projector_test",
    "continuity",
    "continuity_test",
    "runtime_lock",
    "signer_challenge",
    "signer_manifest",
)
TEST_BINDING_NAMES = ("runner_test", "signer_test", "projector_test", "continuity_test")
PARENT_ALIASES = ("A", "B", "C")
SLOT_ROWS = (
    ("01", "P2C-V2-01", "PARENT_A_DEFAULT", "A", "DEFAULT_2M", 2_000_000),
    ("02", "P2C-V2-02", "PARENT_B_DEFAULT", "B", "DEFAULT_2M", 2_000_000),
    ("03", "P2C-V2-03", "PARENT_C_DEFAULT", "C", "DEFAULT_2M", 2_000_000),
    ("04", "P2C-V2-04", "PARENT_B_EXPANDED", "B", "EXPANDED_10M", 10_000_000),
)

FORBIDDEN_MANIFEST_KEYS = {
    "absolute_path",
    "drive_file_id",
    "drive_id",
    "drive_parent_id",
    "lineage",
    "lineage_id",
    "source_path",
    "source_title",
    "source_uid",
    "title",
    "uid",
    "uri",
    "url",
    "v2_work_id",
}


class ContinuityError(RuntimeError):
    """Fail-closed error carrying only a non-sensitive stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Artifact:
    """One already-snapshotted private bundle member."""

    bundle_path: str
    payload: bytes
    mode: int
    kind: str
    semantic_algorithm: str | None = None
    semantic_sha256: str | None = None

    def descriptor(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "bundle_path": self.bundle_path,
            "content_kind": self.kind,
            "mode": format(self.mode, "04o"),
            "raw_bytes_sha256": _sha256(self.payload),
            "size_bytes": len(self.payload),
        }
        if self.kind == "JSON":
            value["canonical_json_sha256"] = _sha256(_canonical_bytes(_decode_json(self.payload)))
        if self.semantic_algorithm is not None:
            value["typed_canonical_algorithm"] = self.semantic_algorithm
            value["typed_canonical_sha256"] = self.semantic_sha256
        return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reject_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ContinuityError("DUPLICATE_JSON_KEY")
        value[key] = child
    return value


def _reject_constant(_: str) -> None:
    raise ContinuityError("INVALID_JSON_NUMBER")


def _decode_json(payload: bytes) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ContinuityError("INVALID_JSON") from error


def _canonical_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ContinuityError("NON_CANONICAL_JSON_VALUE") from error
    return payload + (b"\n" if newline else b"")


def _p2c_hash(value: Any) -> str:
    return _sha256(_canonical_bytes(value, newline=True))


def _p2a_plan_hash(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _p2a_checkpoint_hash(value: Mapping[str, Any]) -> str:
    stable = dict(value)
    stable.pop("volatile", None)
    return _sha256(_canonical_bytes(stable))


def _require_sha256(value: Any, code: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ContinuityError(code)
    return value


def _require_sha1(value: Any, code: str) -> str:
    if not isinstance(value, str) or SHA1.fullmatch(value) is None:
        raise ContinuityError(code)
    return value


def _safe_relative(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContinuityError(code)
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContinuityError(code)
    return path.as_posix()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_private_output(path: Path, private_root: Path) -> Path:
    try:
        root = private_root.resolve(strict=True)
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise ContinuityError("PRIVATE_OUTPUT_PARENT_UNAVAILABLE") from error
    destination = parent / path.name
    if not _inside(destination, root):
        raise ContinuityError("PRIVATE_OUTPUT_OUTSIDE_TMP")
    metadata = parent.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or parent.is_symlink()
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ContinuityError("PRIVATE_OUTPUT_PARENT_PERMISSIONS")
    return destination


def _make_private_parents(path: Path, private_root: Path) -> None:
    try:
        root = private_root.resolve(strict=True)
    except OSError as error:
        raise ContinuityError("PRIVATE_ROOT_UNAVAILABLE") from error
    pending: list[Path] = []
    current = path
    while not current.exists():
        pending.append(current)
        current = current.parent
    try:
        current_resolved = current.resolve(strict=True)
    except OSError as error:
        raise ContinuityError("PRIVATE_OUTPUT_PARENT_UNAVAILABLE") from error
    if not _inside(current_resolved, root):
        raise ContinuityError("PRIVATE_OUTPUT_OUTSIDE_TMP")
    for directory in reversed(pending):
        try:
            directory.mkdir(mode=0o700)
        except OSError as error:
            raise ContinuityError("PRIVATE_OUTPUT_PARENT_UNAVAILABLE") from error


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ContinuityError("OUTPUT_FSYNC_FAILED") from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise ContinuityError("OUTPUT_FSYNC_FAILED") from error
    finally:
        os.close(descriptor)


def _write_new_private(
    path: Path, payload: bytes, private_root: Path, *, mode: int = 0o600
) -> None:
    _make_private_parents(path.parent, private_root)
    destination = _require_private_output(path, private_root)
    if destination.exists() or destination.is_symlink():
        raise ContinuityError("OUTPUT_ALREADY_EXISTS")
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".mvx-p2c-v2-", dir=destination.parent)
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        _fsync_directory(destination.parent)
    except FileExistsError as error:
        raise ContinuityError("OUTPUT_ALREADY_EXISTS") from error
    except OSError as error:
        raise ContinuityError("OUTPUT_PUBLICATION_FAILED") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _publish_validated_bundle(
    path: Path, payload: bytes, private_root: Path, repository: Path
) -> None:
    _make_private_parents(path.parent, private_root)
    destination = _require_private_output(path, private_root)
    if destination.exists() or destination.is_symlink():
        raise ContinuityError("OUTPUT_ALREADY_EXISTS")
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".mvx-p2c-v2-bundle-", dir=destination.parent
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        validate_bundle(Path(temporary), repository=repository)
        os.link(temporary, destination)
        _fsync_directory(destination.parent)
    except FileExistsError as error:
        raise ContinuityError("OUTPUT_ALREADY_EXISTS") from error
    except ContinuityError:
        raise
    except OSError as error:
        raise ContinuityError("OUTPUT_PUBLICATION_FAILED") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _safe_read(
    path: Path, *, limit: int = MAX_INPUT_BYTES, private_modes: set[int] | None = None
) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise ContinuityError("INPUT_UNAVAILABLE") from error
    if not stat.S_ISREG(before.st_mode) or path.is_symlink() or before.st_uid != os.getuid():
        raise ContinuityError("INPUT_NOT_OWNER_REGULAR")
    if before.st_size > limit:
        raise ContinuityError("INPUT_SIZE_LIMIT")
    if private_modes is not None and stat.S_IMODE(before.st_mode) not in private_modes:
        raise ContinuityError("PRIVATE_INPUT_MODE")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ContinuityError("INPUT_SAFE_OPEN_FAILED") from error
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ContinuityError("INPUT_CHANGED")
        with os.fdopen(descriptor, "rb") as stream:
            payload = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
    except OSError as error:
        raise ContinuityError("INPUT_READ_FAILED") from error
    if len(payload) > limit or len(payload) != before.st_size:
        raise ContinuityError("INPUT_SIZE_LIMIT")
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ):
        raise ContinuityError("INPUT_CHANGED")
    return payload


def _private_spec(path: Path) -> dict[str, Any]:
    payload = _safe_read(path, private_modes={0o400, 0o600})
    value = _decode_json(payload)
    if not isinstance(value, dict):
        raise ContinuityError("SPEC_NOT_OBJECT")
    return value


def _resolve_input(spec_path: Path, value: Any, code: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContinuityError(code)
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = spec_path.parent / candidate
    try:
        return candidate.resolve(strict=True)
    except OSError as error:
        raise ContinuityError(code) from error


def _json_artifact(
    path: Path, bundle_path: str, semantic: str | None = None
) -> tuple[Artifact, Any]:
    payload = _safe_read(path)
    value = _decode_json(payload)
    semantic_hash: str | None = None
    if semantic == "P2A_PLAN":
        semantic_hash = _p2a_plan_hash(value)
        algorithm = "MVX_P2A_EXECUTION_PLAN_JCS_1"
    elif semantic == "P2A_CHECKPOINT":
        if not isinstance(value, dict):
            raise ContinuityError("P2A_CHECKPOINT_NOT_OBJECT")
        semantic_hash = _p2a_checkpoint_hash(value)
        algorithm = "MVX_CHECKPOINT_STABLE_WITHOUT_VOLATILE_JCS_1"
    elif semantic == "P2C_CANONICAL":
        semantic_hash = _p2c_hash(value)
        algorithm = "MVX_P2C_NEWLINE_CANONICAL_JSON_1"
    else:
        algorithm = None
    original_mode = stat.S_IMODE(path.stat().st_mode)
    mode = 0o400 if original_mode == 0o400 else 0o600
    return Artifact(bundle_path, payload, mode, "JSON", algorithm, semantic_hash), value


def _raw_artifact(path: Path, bundle_path: str, *, kind: str = "BINARY") -> Artifact:
    payload = _safe_read(path)
    original_mode = stat.S_IMODE(path.stat().st_mode)
    mode = 0o400 if original_mode == 0o400 else 0o600
    return Artifact(bundle_path, payload, mode, kind)


def _git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as error:
        raise ContinuityError("GIT_UNAVAILABLE") from error
    if completed.returncode != 0:
        raise ContinuityError("GIT_BINDING_FAILED")
    return completed.stdout


def _git_line(repository: Path, *arguments: str) -> str:
    try:
        value = _git(repository, *arguments).decode("ascii").strip()
    except UnicodeError as error:
        raise ContinuityError("GIT_BINDING_FAILED") from error
    return value


def _runtime_freeze(runtime_lock_sha256: str) -> dict[str, Any]:
    identity = {
        "byteorder": sys.byteorder,
        "implementation": sys.implementation.name,
        "int_max_str_digits": sys.get_int_max_str_digits(),
        "machine": platform.machine(),
        "python_version": list(sys.version_info[:3]),
        "system": platform.system(),
        "system_release": platform.release(),
    }
    return {
        "identity": identity,
        "runner_environment": {
            "implementation": sys.implementation.name,
            "int_max_str_digits": sys.get_int_max_str_digits(),
            "version": list(sys.version_info[:3]),
        },
        "runtime_lock_raw_bytes_sha256": runtime_lock_sha256,
    }


def _validate_signer_challenge(
    challenge: Any,
    signer_manifest: Any,
    preexecution: Mapping[str, Any],
    code_commit_sha1: str,
    git_tree_sha1: str,
) -> None:
    expected_fields = {
        "campaign_id",
        "code_commit_sha1",
        "git_tree_sha1",
        "preregistration_sha256",
        "runner_sha256",
        "runtime_sha256",
        "schema",
        "schema_version",
        "tests_sha256",
    }
    if (
        not isinstance(challenge, dict)
        or set(challenge) != expected_fields
        or challenge.get("schema") != "MVX-P2C-V2-PERSISTENT-SIGNER-CHALLENGE"
        or challenge.get("schema_version") != SCHEMA_VERSION
        or challenge.get("campaign_id") != CAMPAIGN_ID
        or challenge.get("code_commit_sha1") != code_commit_sha1
        or challenge.get("git_tree_sha1") != git_tree_sha1
        or challenge.get("runner_sha256") != preexecution.get("runner_sha256")
        or challenge.get("tests_sha256") != preexecution.get("tests_sha256")
        or challenge.get("runtime_sha256") != preexecution.get("runtime_sha256")
        or challenge.get("preregistration_sha256") != preexecution.get("preregistration_sha256")
        or not isinstance(signer_manifest, dict)
        or signer_manifest.get("challenge_hex") != _p2c_hash(challenge)
    ):
        raise ContinuityError("SIGNER_CHALLENGE_BINDING")


def _code_artifacts(
    spec: Mapping[str, Any], repository: Path
) -> tuple[dict[str, Any], list[Artifact], dict[str, Any]]:
    code = spec.get("code")
    if not isinstance(code, dict) or set(code) != {"bindings", "commit_sha1", "tree_sha1"}:
        raise ContinuityError("CODE_SPEC_FIELDS")
    commit = _require_sha1(code["commit_sha1"], "CODE_COMMIT_SHA1")
    tree = _require_sha1(code["tree_sha1"], "CODE_TREE_SHA1")
    actual_commit = _git_line(repository, "rev-parse", f"{commit}^{{commit}}")
    actual_tree = _git_line(repository, "rev-parse", f"{commit}^{{tree}}")
    if actual_commit != commit or actual_tree != tree:
        raise ContinuityError("CODE_GIT_BINDING_MISMATCH")
    archive_payload = _git(repository, "archive", "--format=tar", "--prefix=source/", commit)
    archive = Artifact("code/source.tar", archive_payload, 0o600, "GIT_ARCHIVE")
    embedded_commit = _git_line_from_archive(repository, archive_payload)
    if embedded_commit != commit:
        raise ContinuityError("CODE_ARCHIVE_COMMIT_MISMATCH")

    bindings = code["bindings"]
    if not isinstance(bindings, dict) or tuple(sorted(bindings)) != tuple(
        sorted(CODE_BINDING_NAMES)
    ):
        raise ContinuityError("CODE_BINDING_FIELDS")
    artifacts = [archive]
    descriptors: dict[str, Any] = {}
    binding_values: dict[str, Any] = {}
    for name in CODE_BINDING_NAMES:
        repository_path = _safe_relative(bindings[name], "CODE_BINDING_PATH")
        payload = _git(repository, "show", f"{commit}:{repository_path}")
        suffix = PurePosixPath(repository_path).suffix or ".bin"
        bundle_path = f"bindings/{name}{suffix}"
        if suffix == ".json":
            value = _decode_json(payload)
            artifact = Artifact(bundle_path, payload, 0o600, "JSON")
            binding_values[name] = value
        else:
            artifact = Artifact(bundle_path, payload, 0o600, "TEXT_OR_BINARY")
        artifacts.append(artifact)
        descriptor = artifact.descriptor()
        descriptor["repository_path"] = repository_path
        descriptors[name] = descriptor
    tests = [
        {
            "binding": name,
            "raw_bytes_sha256": descriptors[name]["raw_bytes_sha256"],
        }
        for name in TEST_BINDING_NAMES
    ]
    runtime = _runtime_freeze(descriptors["runtime_lock"]["raw_bytes_sha256"])
    preexecution_bindings = {
        "continuity_sha256": descriptors["continuity"]["raw_bytes_sha256"],
        "preregistration_sha256": descriptors["preregistration"]["raw_bytes_sha256"],
        "projection_contexts_sha256": descriptors["projection_contexts"]["raw_bytes_sha256"],
        "projector_sha256": descriptors["projector"]["raw_bytes_sha256"],
        "runner_sha256": descriptors["runner"]["raw_bytes_sha256"],
        "runtime": runtime,
        "runtime_sha256": _p2c_hash(runtime),
        "signer_sha256": descriptors["signer"]["raw_bytes_sha256"],
        "test_suite": tests,
        "tests_sha256": _p2c_hash(tests),
    }
    challenge_commit = _git_line(repository, "rev-parse", f"{commit}^")
    challenge_tree = _git_line(repository, "rev-parse", f"{challenge_commit}^{{tree}}")
    _validate_signer_challenge(
        binding_values["signer_challenge"],
        binding_values["signer_manifest"],
        preexecution_bindings,
        challenge_commit,
        challenge_tree,
    )
    manifest_code = {
        "bindings": descriptors,
        "challenge_code_commit_sha1": challenge_commit,
        "challenge_git_tree_sha1": challenge_tree,
        "code_archive": archive.descriptor(),
        "code_commit_sha1": commit,
        "git_tree_sha1": tree,
        "preexecution_bindings": preexecution_bindings,
    }
    return manifest_code, artifacts, binding_values


def _git_line_from_archive(repository: Path, payload: bytes) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), "get-tar-commit-id"],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        value = completed.stdout.decode("ascii").strip()
    except (OSError, UnicodeError) as error:
        raise ContinuityError("CODE_ARCHIVE_COMMIT_MISMATCH") from error
    if completed.returncode != 0 or SHA1.fullmatch(value) is None:
        raise ContinuityError("CODE_ARCHIVE_COMMIT_MISMATCH")
    return value


def _require_sequence(value: Any, length: int, code: str) -> list[Any]:
    if not isinstance(value, list) or len(value) != length:
        raise ContinuityError(code)
    return value


def _parent_artifacts(
    spec_path: Path, rows: Any
) -> tuple[list[dict[str, Any]], list[Artifact], dict[str, dict[str, Any]]]:
    parents = _require_sequence(rows, 3, "PARENT_COUNT")
    manifest_rows: list[dict[str, Any]] = []
    artifacts: list[Artifact] = []
    contexts: dict[str, dict[str, Any]] = {}
    expected_fields = {
        "alias",
        "p2a_audit_record",
        "p2a_checkpoints",
        "p2a_execution_plan",
        "p2a_source_receipt",
        "p2a_work_id",
        "source_glb",
    }
    for expected_alias, row in zip(PARENT_ALIASES, parents, strict=True):
        if (
            not isinstance(row, dict)
            or set(row) != expected_fields
            or row["alias"] != expected_alias
        ):
            raise ContinuityError("PARENT_FIELDS")
        work_id = _require_sha256(row["p2a_work_id"], "P2A_WORK_ID")
        root = f"parents/{expected_alias}"
        source_path = _resolve_input(spec_path, row["source_glb"], "SOURCE_GLB_PATH")
        source = _raw_artifact(source_path, f"{root}/source.glb", kind="GLB")
        plan_artifact, plan = _json_artifact(
            _resolve_input(spec_path, row["p2a_execution_plan"], "P2A_PLAN_PATH"),
            f"{root}/p2a/execution-plan.json",
            "P2A_PLAN",
        )
        audit_artifact, audit = _json_artifact(
            _resolve_input(spec_path, row["p2a_audit_record"], "P2A_AUDIT_PATH"),
            f"{root}/p2a/audit-record.json",
        )
        receipt_artifact, receipt = _json_artifact(
            _resolve_input(spec_path, row["p2a_source_receipt"], "P2A_RECEIPT_PATH"),
            f"{root}/p2a/source-receipt.json",
        )
        if (
            source.mode != 0o400
            or plan_artifact.mode != 0o600
            or audit_artifact.mode != 0o600
            or receipt_artifact.mode != 0o600
        ):
            raise ContinuityError("P2A_PRIVATE_INPUT_MODE")
        checkpoint_paths = _require_sequence(row["p2a_checkpoints"], 3, "P2A_CHECKPOINT_COUNT")
        checkpoint_artifacts: list[Artifact] = []
        checkpoints: list[dict[str, Any]] = []
        for sequence, path_value in enumerate(checkpoint_paths, start=1):
            checkpoint_path = _resolve_input(spec_path, path_value, "P2A_CHECKPOINT_PATH")
            if (
                re.fullmatch(
                    rf"{sequence:04d}-attempt-0001-(pending|running|terminal)\.json",
                    checkpoint_path.name,
                )
                is None
            ):
                raise ContinuityError("P2A_CHECKPOINT_FILENAME")
            artifact, checkpoint = _json_artifact(
                checkpoint_path,
                f"{root}/p2a/checkpoints/{checkpoint_path.name}",
                "P2A_CHECKPOINT",
            )
            if not isinstance(checkpoint, dict):
                raise ContinuityError("P2A_CHECKPOINT_NOT_OBJECT")
            checkpoint_artifacts.append(artifact)
            checkpoints.append(checkpoint)
        if any(artifact.mode != 0o600 for artifact in checkpoint_artifacts):
            raise ContinuityError("P2A_PRIVATE_INPUT_MODE")
        _validate_p2a_parent(
            work_id,
            source,
            plan,
            audit,
            audit_artifact.payload,
            receipt,
            receipt_artifact.payload,
            checkpoints,
        )
        artifacts.extend(
            [source, plan_artifact, audit_artifact, receipt_artifact, *checkpoint_artifacts]
        )
        manifest_row = {
            "alias": expected_alias,
            "glb": source.descriptor(),
            "p2a": {
                "audit_record": audit_artifact.descriptor(),
                "checkpoint_chain": [item.descriptor() for item in checkpoint_artifacts],
                "execution_plan": plan_artifact.descriptor(),
                "source_receipt": receipt_artifact.descriptor(),
                "work_id": work_id,
            },
        }
        manifest_rows.append(manifest_row)
        contexts[expected_alias] = {
            "source_sha256": _sha256(source.payload),
            "p2a_execution_plan_sha256": plan_artifact.semantic_sha256,
            "p2a_terminal_checkpoint_sha256": checkpoint_artifacts[-1].semantic_sha256,
            "p2a_work_id": work_id,
        }
    return manifest_rows, artifacts, contexts


def _validate_p2a_parent(
    work_id: str,
    source: Artifact,
    plan: Any,
    audit: Any,
    audit_payload: bytes,
    receipt: Any,
    receipt_payload: bytes,
    checkpoints: Sequence[Mapping[str, Any]],
) -> None:
    if not isinstance(plan, dict) or not isinstance(plan.get("stages"), list):
        raise ContinuityError("P2A_PLAN_CONTRACT")
    stages = [
        stage
        for stage in plan["stages"]
        if isinstance(stage, dict) and stage.get("work_id") == work_id
    ]
    if len(stages) != 1:
        raise ContinuityError("P2A_PLAN_WORK_ID_LINK")
    source_sha = _sha256(source.payload)
    stage_identity = stages[0].get("identity")
    if isinstance(stage_identity, dict) and stage_identity.get("source_sha256") != source_sha:
        raise ContinuityError("P2A_PLAN_SOURCE_LINK")
    if not isinstance(audit, dict) or audit.get("work_id") != work_id:
        raise ContinuityError("P2A_AUDIT_WORK_ID_LINK")
    audit_body = audit.get("audit")
    if not isinstance(audit_body, dict) or audit_body.get("source_sha256") != source_sha:
        raise ContinuityError("P2A_AUDIT_SOURCE_LINK")
    if (
        not isinstance(receipt, dict)
        or receipt.get("source_sha256") != source_sha
        or receipt.get("source_size_bytes") != len(source.payload)
    ):
        raise ContinuityError("P2A_RECEIPT_SOURCE_LINK")
    plan_hash = _p2a_plan_hash(plan)
    previous: str | None = None
    for expected_state, checkpoint in zip(
        ("PENDING", "RUNNING", "TERMINAL"), checkpoints, strict=True
    ):
        if (
            checkpoint.get("work_id") != work_id
            or checkpoint.get("state") != expected_state
            or checkpoint.get("execution_plan_sha256") != plan_hash
            or checkpoint.get("previous_checkpoint_sha256") != previous
        ):
            raise ContinuityError("P2A_CHECKPOINT_CHAIN")
        previous = _p2a_checkpoint_hash(checkpoint)
    terminal_hashes = checkpoints[-1].get("artifact_hashes")
    if (
        not isinstance(terminal_hashes, dict)
        or terminal_hashes.get("audit_record") != _sha256(audit_payload)
        or terminal_hashes.get("source_receipt") != _sha256(receipt_payload)
    ):
        raise ContinuityError("P2A_TERMINAL_ARTIFACT_LINK")


def _execution_artifacts(
    spec_path: Path,
    rows: Any,
    parents: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[Artifact]]:
    executions = _require_sequence(rows, 4, "EXECUTION_COUNT")
    manifest_rows: list[dict[str, Any]] = []
    artifacts: list[Artifact] = []
    expected_fields = {
        "max_candidate_pairs",
        "parent_alias",
        "profile_id",
        "slot",
        "v1_authority_claims",
        "v1_checkpoints",
        "v1_execution_plan",
        "v1_result",
        "v1_work_id",
    }
    seen_work_ids: set[str] = set()
    for row, expected in zip(executions, SLOT_ROWS, strict=True):
        slot, _slot_id, comparison_slot, alias, profile, limit = expected
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise ContinuityError("EXECUTION_FIELDS")
        if (
            row["slot"] != slot
            or row["parent_alias"] != alias
            or row["profile_id"] != profile
            or row["max_candidate_pairs"] != limit
        ):
            raise ContinuityError("EXECUTION_SLOT_MAPPING")
        work_id = _require_sha256(row["v1_work_id"], "V1_WORK_ID")
        if work_id in seen_work_ids:
            raise ContinuityError("V1_WORK_ID_DUPLICATE")
        seen_work_ids.add(work_id)
        root = f"executions/{slot}/v1"
        plan_artifact, plan = _json_artifact(
            _resolve_input(spec_path, row["v1_execution_plan"], "V1_PLAN_PATH"),
            f"{root}/execution-plan.json",
            "P2C_CANONICAL",
        )
        result_path = _resolve_input(spec_path, row["v1_result"], "V1_RESULT_PATH")
        if re.fullmatch(r"attempt-[0-9]{4}-[0-9a-f]{16}\.json", result_path.name) is None:
            raise ContinuityError("V1_RESULT_FILENAME")
        result_artifact, result = _json_artifact(
            result_path,
            f"{root}/attempt-results/{result_path.name}",
            "P2C_CANONICAL",
        )
        if plan_artifact.mode != 0o600 or result_artifact.mode != 0o600:
            raise ContinuityError("V1_PRIVATE_INPUT_MODE")
        checkpoint_artifacts: list[Artifact] = []
        checkpoints: list[dict[str, Any]] = []
        for sequence, path_value in enumerate(
            _require_sequence(row["v1_checkpoints"], 3, "V1_CHECKPOINT_COUNT"), start=1
        ):
            checkpoint_path = _resolve_input(spec_path, path_value, "V1_CHECKPOINT_PATH")
            if (
                re.fullmatch(
                    rf"{sequence:04d}-(pending|running|terminal)\.json", checkpoint_path.name
                )
                is None
            ):
                raise ContinuityError("V1_CHECKPOINT_FILENAME")
            artifact, checkpoint = _json_artifact(
                checkpoint_path,
                f"{root}/checkpoints/{checkpoint_path.name}",
                "P2C_CANONICAL",
            )
            if not isinstance(checkpoint, dict):
                raise ContinuityError("V1_CHECKPOINT_NOT_OBJECT")
            checkpoint_artifacts.append(artifact)
            checkpoints.append(checkpoint)
        if any(artifact.mode != 0o600 for artifact in checkpoint_artifacts):
            raise ContinuityError("V1_PRIVATE_INPUT_MODE")
        claim_rows = row["v1_authority_claims"]
        if not isinstance(claim_rows, list) or not claim_rows:
            raise ContinuityError("V1_CLAIM_COUNT")
        claim_artifacts: list[Artifact] = []
        claims: list[dict[str, Any]] = []
        for sequence, path_value in enumerate(claim_rows, start=1):
            claim_path = _resolve_input(spec_path, path_value, "V1_CLAIM_PATH")
            if (
                re.fullmatch(rf"{sequence:04d}-attempt-{sequence:04d}-claim\.json", claim_path.name)
                is None
            ):
                raise ContinuityError("V1_CLAIM_FILENAME")
            artifact, claim = _json_artifact(
                claim_path,
                f"{root}/authority-claims/{claim_path.name}",
                "P2C_CANONICAL",
            )
            if not isinstance(claim, dict):
                raise ContinuityError("V1_CLAIM_NOT_OBJECT")
            if artifact.mode != 0o400:
                raise ContinuityError("V1_CLAIM_SOURCE_MODE")
            claim_artifacts.append(artifact)
            claims.append(claim)
        _validate_v1_execution(
            work_id,
            parents[alias],
            limit,
            plan,
            result,
            result_artifact.payload,
            checkpoints,
            claims,
            result_path.name,
        )
        artifacts.extend([plan_artifact, result_artifact, *checkpoint_artifacts, *claim_artifacts])
        manifest_rows.append(
            {
                "comparison_slot": comparison_slot,
                "max_candidate_pairs": limit,
                "parent_alias": alias,
                "profile_id": profile,
                "slot": slot,
                "v1": {
                    "authority_claim_chain": [item.descriptor() for item in claim_artifacts],
                    "checkpoint_chain": [item.descriptor() for item in checkpoint_artifacts],
                    "execution_plan": plan_artifact.descriptor(),
                    "result": result_artifact.descriptor(),
                    "work_id": work_id,
                },
            }
        )
    artifact_by_path = {artifact.bundle_path: artifact for artifact in artifacts}
    root_rows = []
    for row in sorted(manifest_rows, key=lambda item: item["v1"]["work_id"]):
        v1 = row["v1"]
        root_rows.append(
            {
                "plan_sha256": _sha256(
                    artifact_by_path[v1["execution_plan"]["bundle_path"]].payload
                ),
                "result_sha256": _sha256(artifact_by_path[v1["result"]["bundle_path"]].payload),
                "terminal_sha256": _sha256(
                    artifact_by_path[v1["checkpoint_chain"][-1]["bundle_path"]].payload
                ),
            }
        )
    if _sha256(_canonical_bytes(root_rows, newline=True)) != V1_ROOT:
        raise ContinuityError("V1_TERMINAL_EVIDENCE_ROOT")
    return manifest_rows, artifacts


def _validate_v1_execution(
    work_id: str,
    parent: Mapping[str, Any],
    limit: int,
    plan: Any,
    result: Any,
    result_payload: bytes,
    checkpoints: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    result_filename: str,
) -> None:
    if (
        not isinstance(plan, dict)
        or plan.get("work_id") != work_id
        or plan.get("work_id")
        != _p2c_hash({name: value for name, value in plan.items() if name != "work_id"})
        or plan.get("schema") != "MVX-P2C-EXECUTION-PLAN"
        or plan.get("schema_version") != "0.1.0"
        or plan.get("algorithm_id") != "mvx-p2c-exact-binary64-triangle-contact"
        or plan.get("algorithm_version") != "0.2.0"
        or plan.get("code_sha256") != V1_RUNNER_SHA256
        or plan.get("authority_policy") != "REQUIRE_EXTERNAL_ANCHOR"
        or not isinstance(plan.get("external_anchor_public_key_hex"), str)
        or SHA256.fullmatch(plan["external_anchor_public_key_hex"]) is None
    ):
        raise ContinuityError("V1_PLAN_WORK_ID_LINK")
    if plan.get("source_sha256") != parent["source_sha256"]:
        raise ContinuityError("V1_PLAN_SOURCE_LINK")
    limits = plan.get("limits")
    if not isinstance(limits, dict) or limits.get("max_candidate_pairs") != limit:
        raise ContinuityError("V1_PLAN_PROFILE_LINK")
    binding = plan.get("input_binding")
    if (
        not isinstance(binding, dict)
        or binding.get("p2a_work_id") != parent["p2a_work_id"]
        or binding.get("execution_plan_sha256") != parent["p2a_execution_plan_sha256"]
        or binding.get("p2a_terminal_checkpoint_sha256") != parent["p2a_terminal_checkpoint_sha256"]
        or binding.get("materializer_id") != "mvx-p2c-p2a-canonical-scene-materializer"
        or binding.get("materializer_version") != "0.1.0"
        or binding.get("mode") != "P2A_BOUND"
    ):
        raise ContinuityError("V1_PLAN_PARENT_LINK")
    plan_hash = _p2c_hash(plan)
    if (
        not isinstance(result, dict)
        or result_payload != _canonical_bytes(result, newline=True)
        or result.get("work_id") != work_id
        or result.get("schema") != "MVX-P2C-EXACT-TRIANGLE-CONTACT"
        or result.get("schema_version") != "0.2.0"
        or result.get("algorithm_id") != "mvx-p2c-exact-binary64-triangle-contact"
        or result.get("algorithm_version") != "0.2.0"
        or result.get("source_sha256") != parent["source_sha256"]
        or result.get("plan_sha256") != plan_hash
    ):
        raise ContinuityError("V1_RESULT_LINK")
    previous: str | None = None
    expected_states = ("PENDING", "RUNNING", "TERMINAL")
    for expected_state, checkpoint in zip(expected_states, checkpoints, strict=True):
        if (
            checkpoint.get("work_id") != work_id
            or checkpoint.get("state") != expected_state
            or checkpoint.get("plan_sha256") != plan_hash
            or checkpoint.get("previous_checkpoint_sha256") != previous
        ):
            raise ContinuityError("V1_CHECKPOINT_CHAIN")
        previous = _p2c_hash(checkpoint)
    terminal = checkpoints[-1]
    if (
        terminal.get("result_sha256") != _sha256(result_payload)
        or terminal.get("result_filename") != result_filename
        or result_filename != f"attempt-0001-{_sha256(result_payload)[:16]}.json"
    ):
        raise ContinuityError("V1_TERMINAL_RESULT_LINK")
    previous_claim: str | None = None
    for claim in claims:
        if (
            claim.get("work_id") != work_id
            or claim.get("schema") != "MVX-P2C-ATTEMPT-AUTHORITY-CLAIM"
            or claim.get("schema_version") != "0.1.0"
            or claim.get("trust_model") != "LOCAL_SINGLE_WRITER_IMMUTABLE_CLAIM_DIRECTORY"
            or not isinstance(claim.get("public_key_hex"), str)
            or SHA256.fullmatch(claim["public_key_hex"]) is None
            or claim.get("plan_sha256") != plan_hash
            or claim.get("previous_claim_sha256") != previous_claim
        ):
            raise ContinuityError("V1_CLAIM_CHAIN")
        previous_claim = _p2c_hash(claim)
    if terminal.get("claim_sha256") != previous_claim:
        raise ContinuityError("V1_TERMINAL_CLAIM_LINK")
    terminal_claim = claims[-1]
    authorization = result.get("authorization")
    expected_authorization_fields = {
        "attempt",
        "claim_sha256",
        "signature_algorithm",
        "signature_hex",
        "trust_model",
    }
    if (
        not isinstance(authorization, dict)
        or set(authorization) != expected_authorization_fields
        or authorization.get("attempt") != terminal_claim.get("attempt")
        or authorization.get("claim_sha256") != previous_claim
        or authorization.get("signature_algorithm") != "ED25519"
        or authorization.get("trust_model") != "LOCAL_SINGLE_WRITER_IMMUTABLE_CLAIM_DIRECTORY"
        or not isinstance(authorization.get("signature_hex"), str)
        or HEX_SIGNATURE.fullmatch(authorization["signature_hex"]) is None
    ):
        raise ContinuityError("V1_RESULT_AUTHORIZATION")
    unsigned = {name: value for name, value in result.items() if name != "authorization"}
    authorization_message = _canonical_bytes(
        {
            "attempt": terminal_claim["attempt"],
            "claim_sha256": previous_claim,
            "result": unsigned,
            "signature_domain": "MVX-P2C-RESULT-AUTHORIZATION-ED25519-1",
        },
        newline=True,
    )
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(terminal_claim["public_key_hex"])).verify(
            bytes.fromhex(authorization["signature_hex"]), authorization_message
        )
    except (InvalidSignature, ValueError) as error:
        raise ContinuityError("V1_RESULT_AUTHORIZATION") from error


def _validate_disposition_and_preregistration(bindings: Mapping[str, Any]) -> None:
    disposition = bindings.get("v1_disposition")
    preregistration = bindings.get("preregistration")
    if not isinstance(disposition, dict) or not isinstance(preregistration, dict):
        raise ContinuityError("CAMPAIGN_BINDING_NOT_JSON")
    authority = disposition.get("authority")
    disposition_value = disposition.get("disposition")
    private_evidence = disposition.get("private_evidence")
    if (
        not isinstance(authority, dict)
        or authority.get("campaign_disposition") != "UNANCHORED_DIAGNOSTIC"
        or not isinstance(disposition_value, dict)
        or disposition_value.get("reuse_for_v2") != "FORBIDDEN"
        or disposition_value.get("solid_certification_count") != 0
        or not isinstance(private_evidence, dict)
        or private_evidence.get("terminal_evidence_root_sha256") != V1_ROOT
    ):
        raise ContinuityError("V1_DISPOSITION_CONTRACT")
    campaign = preregistration.get("campaign")
    scope = preregistration.get("private_parent_scope")
    versions = preregistration.get("version_domains")
    preexecution = preregistration.get("preexecution_freeze")
    if (
        not isinstance(campaign, dict)
        or campaign.get("campaign_id") != CAMPAIGN_ID
        or campaign.get("campaign_version") != CAMPAIGN_VERSION
        or campaign.get("status") != "FROZEN_BEFORE_EXECUTION"
        or not isinstance(scope, dict)
        or scope.get("unique_p2a_parent_count") != 3
        or scope.get("execution_count") != 4
        or scope.get("v1_terminal_evidence_root_sha256") != V1_ROOT
        or not isinstance(versions, dict)
        or versions.get("algorithm_version") != "0.3.0"
        or versions.get("result_schema_version") != "0.3.0"
        or versions.get("materializer_version") != "0.2.0"
        or not isinstance(preexecution, dict)
        or preexecution.get("public_github_commit_required_before_plan_creation") is not True
        or preexecution.get("private_drive_copy_is_not_publication") is not True
    ):
        raise ContinuityError("PREREGISTRATION_CONTRACT")


def _signer_public_key(manifest: Any) -> str:
    expected_fields = {
        "assurances",
        "challenge_hex",
        "challenge_signature_hex",
        "created_at",
        "public_key_ed25519_hex",
        "purpose",
        "schema",
        "schema_version",
        "signature_algorithm",
        "signer_id",
        "trust_model",
    }
    assurances = {
        "continuity_only": True,
        "drive_origin_proof": False,
        "encryption": False,
        "independent": False,
        "owner_controlled": True,
        "worm": False,
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        raise ContinuityError("SIGNER_MANIFEST_CONTRACT")
    public = _require_sha256(manifest.get("public_key_ed25519_hex"), "SIGNER_PUBLIC_KEY")
    if public == COMPROMISED_V2_SIGNER_PUBLIC_KEY:
        raise ContinuityError("SIGNER_PUBLIC_KEY_COMPROMISED")
    signature = manifest.get("challenge_signature_hex")
    challenge = manifest.get("challenge_hex")
    created_at = manifest.get("created_at")
    if (
        not isinstance(signature, str)
        or HEX_SIGNATURE.fullmatch(signature) is None
        or not isinstance(challenge, str)
        or SHA256.fullmatch(challenge) is None
        or manifest.get("schema") != "MVX-P2C-OWNER-PERSISTENT-SIGNER-MANIFEST"
        or manifest.get("schema_version") != "0.1.0"
        or manifest.get("signature_algorithm") != "ED25519"
        or manifest.get("trust_model") != "OWNER_CONTROLLED_PERSISTENT_CONTINUITY_ONLY"
        or manifest.get("purpose") != "P2C_RESTART_CONTINUITY_ONLY_NEVER_SOLID_VALIDITY"
        or manifest.get("assurances") != assurances
        or manifest.get("signer_id") != f"mvx-p2c-owner-{public[:16]}"
        or not isinstance(created_at, str)
        or not created_at.endswith("Z")
    ):
        raise ContinuityError("SIGNER_MANIFEST_SIGNATURE")
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError as error:
        raise ContinuityError("SIGNER_MANIFEST_SIGNATURE") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContinuityError("SIGNER_MANIFEST_SIGNATURE")
    core = {name: value for name, value in manifest.items() if name != "challenge_signature_hex"}
    message = _canonical_bytes(
        {
            "manifest": core,
            "signature_domain": "MVX-P2C-OWNER-PERSISTENT-SIGNER-MANIFEST-ED25519-1",
        }
    )
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(
            bytes.fromhex(signature), message
        )
    except (InvalidSignature, ValueError) as error:
        raise ContinuityError("SIGNER_MANIFEST_SIGNATURE") from error
    return public


def _privacy_walk(value: Any, *, key: str | None = None) -> None:
    if key is not None and key.lower() in FORBIDDEN_MANIFEST_KEYS:
        raise ContinuityError("MANIFEST_FORBIDDEN_IDENTITY_FIELD")
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise ContinuityError("MANIFEST_NON_STRING_KEY")
            _privacy_walk(child, key=child_key)
        return
    if isinstance(value, list):
        for child in value:
            _privacy_walk(child)
        return
    if isinstance(value, str):
        lowered = value.lower()
        if (
            value.startswith(("/", "\\\\"))
            or WINDOWS_ABSOLUTE.match(value) is not None
            or lowered.startswith(("http://", "https://", "file://"))
        ):
            raise ContinuityError("MANIFEST_FORBIDDEN_LOCATION")


def _private_key(path: Path, expected_public: str) -> Ed25519PrivateKey:
    raw = _safe_read(path, limit=64, private_modes={0o400})
    if len(raw) != 32:
        raise ContinuityError("PRIVATE_KEY_LENGTH")
    try:
        key = Ed25519PrivateKey.from_private_bytes(raw)
        public = (
            key.public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
        )
    except ValueError as error:
        raise ContinuityError("PRIVATE_KEY_INVALID") from error
    if public != expected_public:
        raise ContinuityError("PRIVATE_KEY_MANIFEST_MISMATCH")
    return key


def _signature_payload(
    domain: str,
    value: Mapping[str, Any],
    signer_manifest_sha: str,
    context: Mapping[str, Any],
) -> bytes:
    return _canonical_bytes(
        {
            "context": dict(context),
            "domain": domain,
            "manifest_sha256": _p2c_hash(value),
            "signer_manifest_raw_bytes_sha256": signer_manifest_sha,
        },
        newline=True,
    )


def _authentication(
    domain: str,
    core: Mapping[str, Any],
    signer_manifest_sha: str,
    public_key: str,
    signing_key: Path,
    context: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    payload = _signature_payload(domain, core, signer_manifest_sha, context)
    signature = _private_key(signing_key, public_key).sign(payload).hex()
    return (
        {
            "context": dict(context),
            "domain": domain,
            "manifest_sha256": _p2c_hash(core),
            "payload_raw_bytes_sha256": _sha256(payload),
            "public_key_ed25519_hex": public_key,
            "signature_algorithm": "ED25519",
            "signature_hex": signature,
            "signer_manifest_raw_bytes_sha256": signer_manifest_sha,
        },
        payload,
    )


def _member_directories(artifacts: Sequence[Artifact]) -> list[str]:
    directories = {
        "bindings",
        "code",
        "executions",
        "parents",
    }
    for artifact in artifacts:
        path = PurePosixPath(artifact.bundle_path)
        for parent in path.parents:
            if parent.as_posix() != ".":
                directories.add(parent.as_posix())
    for slot, *_ in SLOT_ROWS:
        root = f"executions/{slot}/v1"
        directories.update(
            {
                f"{root}/attempt-results",
                f"{root}/authority-claims",
                f"{root}/authority-secrets",
                f"{root}/checkpoints",
                f"{root}/staging",
            }
        )
    return sorted(directories, key=lambda item: (item.count("/"), item))


def _tar_bytes(manifest: Mapping[str, Any], payload: bytes, artifacts: Sequence[Artifact]) -> bytes:
    by_name = {artifact.bundle_path: artifact for artifact in artifacts}
    if len(by_name) != len(artifacts):
        raise ContinuityError("BUNDLE_MEMBER_DUPLICATE")
    manifest_bytes = _canonical_bytes(manifest, newline=True)
    generated = [
        Artifact("manifest.json", manifest_bytes, 0o600, "JSON"),
        Artifact("manifest-signing-payload.json", payload, 0o600, "JSON"),
    ]
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for directory in _member_directories([*artifacts, *generated]):
            info = tarfile.TarInfo(f"{directory}/")
            info.type = tarfile.DIRTYPE
            info.mode = 0o700
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            archive.addfile(info)
        for artifact in sorted([*artifacts, *generated], key=lambda item: item.bundle_path):
            info = tarfile.TarInfo(artifact.bundle_path)
            info.size = len(artifact.payload)
            info.mode = artifact.mode
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            archive.addfile(info, io.BytesIO(artifact.payload))
    result = stream.getvalue()
    if len(result) > MAX_BUNDLE_BYTES:
        raise ContinuityError("BUNDLE_SIZE_LIMIT")
    return result


def build_bundle(
    spec_path: Path,
    repository: Path,
    output: Path,
    *,
    signing_key: Path,
    private_root: Path = PRIVATE_ROOT,
) -> dict[str, Any]:
    """Build one deterministic, write-once pre-plan private bundle."""

    spec = _private_spec(spec_path)
    if set(spec) != {"code", "executions", "parents", "schema", "schema_version"}:
        raise ContinuityError("SPEC_FIELDS")
    if spec["schema"] != INPUT_SCHEMA or spec["schema_version"] != SCHEMA_VERSION:
        raise ContinuityError("SPEC_SCHEMA")
    try:
        repository = repository.resolve(strict=True)
    except OSError as error:
        raise ContinuityError("REPOSITORY_UNAVAILABLE") from error
    manifest_code, code_artifacts, binding_values = _code_artifacts(spec, repository)
    _validate_disposition_and_preregistration(binding_values)
    parent_rows, parent_artifacts, parent_contexts = _parent_artifacts(spec_path, spec["parents"])
    execution_rows, execution_artifacts = _execution_artifacts(
        spec_path, spec["executions"], parent_contexts
    )
    signer_descriptor = manifest_code["bindings"]["signer_manifest"]
    signer_manifest = binding_values["signer_manifest"]
    public_key = _signer_public_key(signer_manifest)
    core = {
        "campaign_id": CAMPAIGN_ID,
        "code": manifest_code,
        "executions": execution_rows,
        "gate_credit": "NONE",
        "geometry_execution_count": 0,
        "parents": parent_rows,
        "predecessor_disposition": "UNANCHORED_DIAGNOSTIC",
        "predecessor_reuse": "FORBIDDEN",
        "schema": PREFREEZE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "solid_status_V_count": 0,
        "status": "INPUTS_FROZEN_BEFORE_V2_PLAN_CREATION",
        "v1_terminal_evidence_root_sha256": V1_ROOT,
        "v2_work_ids_present": False,
    }
    authentication, signing_payload = _authentication(
        PREFREEZE_SIGNATURE_DOMAIN,
        core,
        signer_descriptor["raw_bytes_sha256"],
        public_key,
        signing_key,
        {"freeze_scope": "PREFREEZE_INPUTS_CODE_RUNTIME"},
    )
    manifest = {**core, "authentication": authentication}
    _validate_prefreeze_manifest(manifest)
    bundle = _tar_bytes(
        manifest,
        signing_payload,
        [*code_artifacts, *parent_artifacts, *execution_artifacts],
    )
    _publish_validated_bundle(output, bundle, private_root, repository)
    return {"action": "BUNDLE_CREATED"}


def _validate_prefreeze_manifest(manifest: Mapping[str, Any]) -> None:
    _privacy_walk(manifest)
    if (
        manifest.get("schema") != PREFREEZE_SCHEMA
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        raise ContinuityError("PREFREEZE_SCHEMA")
    if manifest.get("v2_work_ids_present") is not False:
        raise ContinuityError("PREFREEZE_V2_WORK_ID")
    parents = manifest.get("parents")
    executions = manifest.get("executions")
    if (
        not isinstance(parents, list)
        or [row.get("alias") for row in parents if isinstance(row, dict)] != list(PARENT_ALIASES)
        or not isinstance(executions, list)
        or [row.get("slot") for row in executions if isinstance(row, dict)]
        != [row[0] for row in SLOT_ROWS]
    ):
        raise ContinuityError("PREFREEZE_SCOPE")
    authentication = manifest.get("authentication")
    if not isinstance(authentication, dict):
        raise ContinuityError("PREFREEZE_AUTHENTICATION")
    core = {name: value for name, value in manifest.items() if name != "authentication"}
    if (
        authentication.get("domain") != PREFREEZE_SIGNATURE_DOMAIN
        or authentication.get("context") != {"freeze_scope": "PREFREEZE_INPUTS_CODE_RUNTIME"}
        or authentication.get("manifest_sha256") != _p2c_hash(core)
    ):
        raise ContinuityError("PREFREEZE_AUTHENTICATION")


def _read_bundle(path: Path) -> tuple[dict[str, bytes], dict[str, int]]:
    payload = _safe_read(path, limit=MAX_BUNDLE_BYTES, private_modes={0o600})
    files: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            for member in archive:
                raw_name = member.name.removesuffix("/")
                name = _safe_relative(raw_name, "BUNDLE_MEMBER_PATH")
                if name in modes:
                    raise ContinuityError("BUNDLE_MEMBER_DUPLICATE")
                if member.uid != 0 or member.gid != 0 or member.mtime != 0:
                    raise ContinuityError("BUNDLE_MEMBER_METADATA")
                mode = stat.S_IMODE(member.mode)
                if member.isdir():
                    if mode != 0o700:
                        raise ContinuityError("BUNDLE_DIRECTORY_MODE")
                    modes[name] = mode
                    continue
                if not member.isfile() or mode not in {0o400, 0o600}:
                    raise ContinuityError("BUNDLE_MEMBER_TYPE_OR_MODE")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ContinuityError("BUNDLE_MEMBER_READ")
                files[name] = extracted.read(MAX_INPUT_BYTES + 1)
                if len(files[name]) > MAX_INPUT_BYTES:
                    raise ContinuityError("BUNDLE_MEMBER_SIZE_LIMIT")
                modes[name] = mode
    except (tarfile.TarError, OSError) as error:
        raise ContinuityError("BUNDLE_INVALID_TAR") from error
    return files, modes


def _descriptor_paths(value: Any) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    if isinstance(value, dict):
        if "bundle_path" in value:
            path = _safe_relative(value["bundle_path"], "DESCRIPTOR_BUNDLE_PATH")
            if path in result:
                raise ContinuityError("DESCRIPTOR_DUPLICATE")
            result[path] = value
        for child in value.values():
            child_paths = _descriptor_paths(child)
            overlap = set(result) & set(child_paths)
            if overlap:
                raise ContinuityError("DESCRIPTOR_DUPLICATE")
            result.update(child_paths)
    elif isinstance(value, list):
        for child in value:
            child_paths = _descriptor_paths(child)
            overlap = set(result) & set(child_paths)
            if overlap:
                raise ContinuityError("DESCRIPTOR_DUPLICATE")
            result.update(child_paths)
    return result


def _verify_descriptor(path: str, descriptor: Mapping[str, Any], payload: bytes, mode: int) -> None:
    if (
        descriptor.get("bundle_path") != path
        or descriptor.get("raw_bytes_sha256") != _sha256(payload)
        or descriptor.get("size_bytes") != len(payload)
        or descriptor.get("mode") != format(mode, "04o")
    ):
        raise ContinuityError("DESCRIPTOR_RAW_BINDING")
    if descriptor.get("content_kind") == "JSON":
        value = _decode_json(payload)
        if descriptor.get("canonical_json_sha256") != _sha256(_canonical_bytes(value)):
            raise ContinuityError("DESCRIPTOR_JSON_BINDING")
        algorithm = descriptor.get("typed_canonical_algorithm")
        if algorithm == "MVX_P2A_EXECUTION_PLAN_JCS_1":
            semantic = _p2a_plan_hash(value)
        elif algorithm == "MVX_CHECKPOINT_STABLE_WITHOUT_VOLATILE_JCS_1":
            if not isinstance(value, dict):
                raise ContinuityError("DESCRIPTOR_TYPED_BINDING")
            semantic = _p2a_checkpoint_hash(value)
        elif algorithm == "MVX_P2C_NEWLINE_CANONICAL_JSON_1":
            semantic = _p2c_hash(value)
        elif algorithm is None:
            return
        else:
            raise ContinuityError("DESCRIPTOR_TYPED_ALGORITHM")
        if descriptor.get("typed_canonical_sha256") != semantic:
            raise ContinuityError("DESCRIPTOR_TYPED_BINDING")


def _verify_authentication(
    manifest: Mapping[str, Any], payload: bytes, signer_manifest_payload: bytes
) -> None:
    authentication = manifest.get("authentication")
    if not isinstance(authentication, dict):
        raise ContinuityError("AUTHENTICATION_FIELDS")
    core = {name: value for name, value in manifest.items() if name != "authentication"}
    context = authentication.get("context")
    if not isinstance(context, dict):
        raise ContinuityError("AUTHENTICATION_CONTEXT")
    expected_payload = _signature_payload(
        authentication.get("domain"), core, _sha256(signer_manifest_payload), context
    )
    public = _require_sha256(authentication.get("public_key_ed25519_hex"), "AUTH_PUBLIC_KEY")
    if (
        payload != expected_payload
        or authentication.get("payload_raw_bytes_sha256") != _sha256(payload)
        or authentication.get("manifest_sha256") != _p2c_hash(core)
        or authentication.get("signer_manifest_raw_bytes_sha256")
        != _sha256(signer_manifest_payload)
    ):
        raise ContinuityError("AUTHENTICATION_BINDING")
    signature = authentication.get("signature_hex")
    if not isinstance(signature, str) or HEX_SIGNATURE.fullmatch(signature) is None:
        raise ContinuityError("AUTHENTICATION_SIGNATURE")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(
            bytes.fromhex(signature), payload
        )
    except (InvalidSignature, ValueError) as error:
        raise ContinuityError("AUTHENTICATION_SIGNATURE") from error


def _artifact_json(files: Mapping[str, bytes], descriptor: Mapping[str, Any]) -> dict[str, Any]:
    path = _safe_relative(descriptor.get("bundle_path"), "DESCRIPTOR_BUNDLE_PATH")
    value = _decode_json(files[path])
    if not isinstance(value, dict):
        raise ContinuityError("BUNDLE_JSON_NOT_OBJECT")
    return value


def _verify_bundle_links(manifest: Mapping[str, Any], files: Mapping[str, bytes]) -> None:
    parent_contexts: dict[str, dict[str, str]] = {}
    for row in manifest["parents"]:
        source_descriptor = row["glb"]
        p2a = row["p2a"]
        source_path = source_descriptor["bundle_path"]
        source = Artifact(
            source_path,
            files[source_path],
            int(source_descriptor["mode"], 8),
            "GLB",
        )
        plan = _artifact_json(files, p2a["execution_plan"])
        audit = _artifact_json(files, p2a["audit_record"])
        receipt = _artifact_json(files, p2a["source_receipt"])
        checkpoints = [_artifact_json(files, descriptor) for descriptor in p2a["checkpoint_chain"]]
        audit_payload = files[p2a["audit_record"]["bundle_path"]]
        receipt_payload = files[p2a["source_receipt"]["bundle_path"]]
        _validate_p2a_parent(
            p2a["work_id"],
            source,
            plan,
            audit,
            audit_payload,
            receipt,
            receipt_payload,
            checkpoints,
        )
        parent_contexts[row["alias"]] = {
            "p2a_execution_plan_sha256": p2a["execution_plan"]["typed_canonical_sha256"],
            "p2a_terminal_checkpoint_sha256": p2a["checkpoint_chain"][-1]["typed_canonical_sha256"],
            "p2a_work_id": p2a["work_id"],
            "source_sha256": source_descriptor["raw_bytes_sha256"],
        }
    root_rows: list[tuple[str, dict[str, str]]] = []
    for row, expected in zip(manifest["executions"], SLOT_ROWS, strict=True):
        slot, _slot_id, comparison, alias, profile, limit = expected
        if (
            row["slot"] != slot
            or row["comparison_slot"] != comparison
            or row["parent_alias"] != alias
            or row["profile_id"] != profile
            or row["max_candidate_pairs"] != limit
        ):
            raise ContinuityError("BUNDLE_EXECUTION_MAPPING")
        v1 = row["v1"]
        plan = _artifact_json(files, v1["execution_plan"])
        result = _artifact_json(files, v1["result"])
        checkpoints = [_artifact_json(files, descriptor) for descriptor in v1["checkpoint_chain"]]
        claims = [_artifact_json(files, descriptor) for descriptor in v1["authority_claim_chain"]]
        result_payload = files[v1["result"]["bundle_path"]]
        _validate_v1_execution(
            v1["work_id"],
            parent_contexts[alias],
            limit,
            plan,
            result,
            result_payload,
            checkpoints,
            claims,
            PurePosixPath(v1["result"]["bundle_path"]).name,
        )
        root_rows.append(
            (
                v1["work_id"],
                {
                    "plan_sha256": _sha256(files[v1["execution_plan"]["bundle_path"]]),
                    "result_sha256": _sha256(files[v1["result"]["bundle_path"]]),
                    "terminal_sha256": _sha256(files[v1["checkpoint_chain"][-1]["bundle_path"]]),
                },
            )
        )
    ordered_rows = [row for _, row in sorted(root_rows, key=lambda item: item[0])]
    reproduced_root = _sha256(_canonical_bytes(ordered_rows, newline=True))
    if (
        reproduced_root != V1_ROOT
        or manifest.get("v1_terminal_evidence_root_sha256") != reproduced_root
    ):
        raise ContinuityError("V1_TERMINAL_EVIDENCE_ROOT")


def _verify_embedded_code_bindings(manifest: Mapping[str, Any], files: Mapping[str, bytes]) -> None:
    archive_path = manifest["code"]["code_archive"]["bundle_path"]
    archive_payload = files[archive_path]
    expected = {
        f"source/{descriptor['repository_path']}": files[descriptor["bundle_path"]]
        for descriptor in manifest["code"]["bindings"].values()
    }
    observed: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_payload), mode="r:") as archive:
            for member in archive:
                name = member.name.removesuffix("/")
                _safe_relative(name, "CODE_ARCHIVE_MEMBER_PATH")
                parts = PurePosixPath(name).parts
                if ".git" in parts or (
                    len(parts) > 1 and parts[0] == "source" and parts[1] == "tmp"
                ):
                    raise ContinuityError("CODE_ARCHIVE_PRIVATE_TREE_MEMBER")
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    raise ContinuityError("CODE_ARCHIVE_UNSAFE_MEMBER")
                if name not in expected or not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                if extracted is None or name in observed:
                    raise ContinuityError("CODE_ARCHIVE_BINDING_DUPLICATE")
                observed[name] = extracted.read(MAX_INPUT_BYTES + 1)
    except (tarfile.TarError, OSError) as error:
        raise ContinuityError("CODE_ARCHIVE_INVALID") from error
    if observed != expected:
        raise ContinuityError("CODE_ARCHIVE_BINDING_MISMATCH")


def _verify_preexecution_bindings(code: Mapping[str, Any], files: Mapping[str, bytes]) -> None:
    bindings = code.get("bindings")
    freeze = code.get("preexecution_bindings")
    if not isinstance(bindings, dict) or not isinstance(freeze, dict):
        raise ContinuityError("PREEXECUTION_BINDING_FIELDS")
    expected_tests = [
        {
            "binding": name,
            "raw_bytes_sha256": bindings[name]["raw_bytes_sha256"],
        }
        for name in TEST_BINDING_NAMES
    ]
    runtime = freeze.get("runtime")
    if (
        freeze.get("runner_sha256") != bindings["runner"]["raw_bytes_sha256"]
        or freeze.get("signer_sha256") != bindings["signer"]["raw_bytes_sha256"]
        or freeze.get("projector_sha256") != bindings["projector"]["raw_bytes_sha256"]
        or freeze.get("continuity_sha256") != bindings["continuity"]["raw_bytes_sha256"]
        or freeze.get("preregistration_sha256") != bindings["preregistration"]["raw_bytes_sha256"]
        or freeze.get("projection_contexts_sha256")
        != bindings["projection_contexts"]["raw_bytes_sha256"]
        or freeze.get("test_suite") != expected_tests
        or freeze.get("tests_sha256") != _p2c_hash(expected_tests)
        or not isinstance(runtime, dict)
        or runtime.get("runtime_lock_raw_bytes_sha256")
        != bindings["runtime_lock"]["raw_bytes_sha256"]
        or freeze.get("runtime_sha256") != _p2c_hash(runtime)
    ):
        raise ContinuityError("PREEXECUTION_BINDING_MISMATCH")
    challenge = _decode_json(files[bindings["signer_challenge"]["bundle_path"]])
    signer_manifest = _decode_json(files[bindings["signer_manifest"]["bundle_path"]])
    _validate_signer_challenge(
        challenge,
        signer_manifest,
        freeze,
        _require_sha1(code.get("challenge_code_commit_sha1"), "CHALLENGE_CODE_COMMIT"),
        _require_sha1(code.get("challenge_git_tree_sha1"), "CHALLENGE_CODE_TREE"),
    )


def validate_bundle(path: Path, *, repository: Path | None = None) -> dict[str, Any]:
    """Validate bytes, privacy, modes, typed hashes, signature, and code binding."""

    files, modes = _read_bundle(path)
    if "manifest.json" not in files or "manifest-signing-payload.json" not in files:
        raise ContinuityError("BUNDLE_CONTROL_FILES")
    manifest = _decode_json(files["manifest.json"])
    if not isinstance(manifest, dict) or files["manifest.json"] != _canonical_bytes(
        manifest, newline=True
    ):
        raise ContinuityError("MANIFEST_NOT_CANONICAL")
    _validate_prefreeze_manifest(manifest)
    descriptors = _descriptor_paths(manifest)
    expected_files = set(descriptors) | {"manifest.json", "manifest-signing-payload.json"}
    if set(files) != expected_files:
        raise ContinuityError("BUNDLE_FILE_SET")
    expected_directories = set(
        _member_directories(
            [
                Artifact(path, b"", int(descriptor["mode"], 8), "CONTROL")
                for path, descriptor in descriptors.items()
            ]
            + [
                Artifact("manifest.json", b"", 0o600, "CONTROL"),
                Artifact("manifest-signing-payload.json", b"", 0o600, "CONTROL"),
            ]
        )
    )
    observed_directories = {name for name, mode in modes.items() if mode == 0o700}
    if observed_directories != expected_directories:
        raise ContinuityError("BUNDLE_DIRECTORY_SET")
    for member_path, descriptor in descriptors.items():
        _verify_descriptor(member_path, descriptor, files[member_path], modes[member_path])
    signer_path = manifest["code"]["bindings"]["signer_manifest"]["bundle_path"]
    public = _signer_public_key(_decode_json(files[signer_path]))
    if public != manifest["authentication"]["public_key_ed25519_hex"]:
        raise ContinuityError("AUTHENTICATION_SIGNER_LINK")
    _verify_authentication(manifest, files["manifest-signing-payload.json"], files[signer_path])
    required_empty = {
        f"executions/{slot}/v1/{name}"
        for slot, *_ in SLOT_ROWS
        for name in ("authority-secrets", "staging")
    }
    if not required_empty.issubset(modes):
        raise ContinuityError("BUNDLE_REQUIRED_DIRECTORIES")
    for row in manifest["executions"]:
        for claim in row["v1"]["authority_claim_chain"]:
            if modes[claim["bundle_path"]] != 0o400:
                raise ContinuityError("BUNDLE_CLAIM_MODE")
    _verify_bundle_links(manifest, files)
    _verify_embedded_code_bindings(manifest, files)
    _verify_preexecution_bindings(manifest["code"], files)
    if repository is not None:
        archive = files[manifest["code"]["code_archive"]["bundle_path"]]
        if _git_line_from_archive(repository, archive) != manifest["code"]["code_commit_sha1"]:
            raise ContinuityError("CODE_ARCHIVE_COMMIT_MISMATCH")
        tree = _git_line(
            repository, "rev-parse", f"{manifest['code']['code_commit_sha1']}^{{tree}}"
        )
        if tree != manifest["code"]["git_tree_sha1"]:
            raise ContinuityError("CODE_TREE_MISMATCH")
        parent = _git_line(repository, "rev-parse", f"{manifest['code']['code_commit_sha1']}^")
        parent_tree = _git_line(repository, "rev-parse", f"{parent}^{{tree}}")
        if (
            parent != manifest["code"]["challenge_code_commit_sha1"]
            or parent_tree != manifest["code"]["challenge_git_tree_sha1"]
        ):
            raise ContinuityError("SIGNER_CHALLENGE_GIT_PARENT")
    return {"action": "BUNDLE_VALID"}


def restore_test(
    bundle: Path,
    destination: Path,
    *,
    repository: Path | None = None,
    private_root: Path = PRIVATE_ROOT,
) -> dict[str, Any]:
    """Extract into a new directory and verify every restored byte and mode."""

    validate_bundle(bundle, repository=repository)
    _make_private_parents(destination.parent, private_root)
    if destination.exists() or destination.is_symlink():
        raise ContinuityError("RESTORE_DESTINATION_EXISTS")
    try:
        destination.mkdir(mode=0o700)
    except OSError as error:
        raise ContinuityError("RESTORE_DESTINATION_FAILED") from error
    files, modes = _read_bundle(bundle)
    directory_names = sorted(
        (name for name, mode in modes.items() if mode == 0o700),
        key=lambda item: (item.count("/"), item),
    )
    try:
        for name in directory_names:
            target = destination / PurePosixPath(name)
            target.mkdir(mode=0o700)
        for name in sorted(files):
            target = destination / PurePosixPath(name)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(target, flags, modes[name])
            os.fchmod(descriptor, modes[name])
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(files[name])
                stream.flush()
                os.fsync(stream.fileno())
    except OSError as error:
        raise ContinuityError("RESTORE_WRITE_FAILED") from error
    for name, payload in files.items():
        target = destination / PurePosixPath(name)
        if _safe_read(target) != payload or stat.S_IMODE(target.stat().st_mode) != modes[name]:
            raise ContinuityError("RESTORE_BYTE_OR_MODE_MISMATCH")
    return {"action": "RESTORE_VALID"}


def _bundle_json(files: Mapping[str, bytes], path: str) -> dict[str, Any]:
    value = _decode_json(files[path])
    if not isinstance(value, dict):
        raise ContinuityError("BUNDLE_JSON_NOT_OBJECT")
    return value


def freeze_continuity(
    bundle: Path,
    v2_plans: Mapping[str, Path],
    output_manifest: Path,
    output_authentication: Path,
    *,
    signing_key: Path,
    private_root: Path = PRIVATE_ROOT,
) -> dict[str, Any]:
    """Freeze after confirmed public publication and plans, before any child."""

    validate_bundle(bundle)
    files, _ = _read_bundle(bundle)
    prefreeze = _bundle_json(files, "manifest.json")
    prereg_path = prefreeze["code"]["bindings"]["preregistration"]["bundle_path"]
    preregistration = _bundle_json(files, prereg_path)
    signer_path = prefreeze["code"]["bindings"]["signer_manifest"]["bundle_path"]
    signer_payload = files[signer_path]
    public = _signer_public_key(_decode_json(signer_payload))
    if set(v2_plans) != {row[0] for row in SLOT_ROWS}:
        raise ContinuityError("V2_PLAN_SLOT_SET")

    parent_by_alias = {
        row["alias"]: {
            "audit_record_sha256": row["p2a"]["audit_record"]["raw_bytes_sha256"],
            "p2a_execution_plan_file_sha256": row["p2a"]["execution_plan"]["raw_bytes_sha256"],
            "p2a_execution_plan_sha256": row["p2a"]["execution_plan"]["typed_canonical_sha256"],
            "p2a_terminal_checkpoint_sha256": row["p2a"]["checkpoint_chain"][-1][
                "typed_canonical_sha256"
            ],
            "p2a_work_id": row["p2a"]["work_id"],
            "source_sha256": row["glb"]["raw_bytes_sha256"],
            "source_size_bytes": row["glb"]["size_bytes"],
        }
        for row in prefreeze["parents"]
    }
    v1_by_slot = {row["slot"]: row for row in prefreeze["executions"]}
    slots: list[dict[str, Any]] = []
    for slot, slot_id, comparison, alias, profile, limit in SLOT_ROWS:
        v1_row = v1_by_slot[slot]
        v1_plan = _bundle_json(files, v1_row["v1"]["execution_plan"]["bundle_path"])
        v2_payload = _safe_read(v2_plans[slot], private_modes={0o600})
        v2_plan = _decode_json(v2_payload)
        if not isinstance(v2_plan, dict):
            raise ContinuityError("V2_PLAN_NOT_OBJECT")
        parent = parent_by_alias[alias]
        _validate_v2_plan(
            v2_plan,
            parent,
            limit,
            public,
            preregistration,
            prefreeze["code"]["preexecution_bindings"],
        )
        continuity_parent = {
            name: parent[name]
            for name in (
                "p2a_execution_plan_sha256",
                "p2a_terminal_checkpoint_sha256",
                "p2a_work_id",
                "source_sha256",
            )
        }
        v1_binding = {
            "execution_plan_sha256": _p2c_hash(v1_plan),
            **continuity_parent,
            "work_id": v1_plan["work_id"],
        }
        v2_binding = {
            "execution_plan_sha256": _p2c_hash(v2_plan),
            **continuity_parent,
            "work_id": v2_plan["work_id"],
        }
        slots.append(
            {
                "comparison_slot": comparison,
                "max_candidate_pairs": limit,
                "private_parent_alias": f"PARENT_{alias}",
                "profile_id": profile,
                "slot_id": slot_id,
                "v1": v1_binding,
                "v2": v2_binding,
            }
        )
    manifest = {
        "campaign_id": CAMPAIGN_ID,
        "persistent_signer_public_key_ed25519_hex": public,
        "preregistration_value_sha256": _p2c_hash(preregistration),
        "schema": CONTINUITY_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "slots": slots,
        "status": "FROZEN_BEFORE_FIRST_V2_CHILD",
        "v1_terminal_evidence_root_sha256": V1_ROOT,
    }
    _validate_final_continuity(manifest, preregistration, public)
    authentication, payload = _authentication(
        CONTINUITY_SIGNATURE_DOMAIN,
        manifest,
        _sha256(signer_payload),
        public,
        signing_key,
        {
            "prefreeze_bundle_raw_bytes_sha256": _sha256(
                _safe_read(bundle, limit=MAX_BUNDLE_BYTES, private_modes={0o600})
            ),
            "prefreeze_manifest_sha256": _p2c_hash(prefreeze),
        },
    )
    detached = {
        **authentication,
        "schema": SIGNATURE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "signed_manifest_schema": CONTINUITY_SCHEMA,
    }
    _write_new_private(output_manifest, _canonical_bytes(manifest, newline=True), private_root)
    _write_new_private(
        output_authentication,
        _canonical_bytes(
            {"authentication": detached, "payload": _decode_json(payload)}, newline=True
        ),
        private_root,
    )
    validate_frozen_continuity(
        output_manifest,
        output_authentication,
        signer_manifest_payload=signer_payload,
        preregistration=preregistration,
        prefreeze_bundle_raw_bytes_sha256=_sha256(
            _safe_read(bundle, limit=MAX_BUNDLE_BYTES, private_modes={0o600})
        ),
        prefreeze_manifest_sha256=_p2c_hash(prefreeze),
    )
    return {"action": "CONTINUITY_FROZEN"}


def _validate_v2_plan(
    plan: Mapping[str, Any],
    parent: Mapping[str, Any],
    limit: int,
    public_key: str,
    preregistration: Mapping[str, Any],
    preexecution: Mapping[str, Any],
) -> None:
    expected_plan_fields = {
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
    expected_binding_fields = {
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
    versions = preregistration.get("version_domains")
    common_limits = preregistration.get("limits_common")
    runtime = preexecution.get("runtime")
    if (
        not isinstance(versions, dict)
        or not isinstance(common_limits, dict)
        or not isinstance(runtime, dict)
    ):
        raise ContinuityError("V2_PREREGISTRATION_BINDING")
    expected_limits = {
        "max_candidate_pairs": limit,
        "max_coordinate_bits": common_limits.get("max_coordinate_bits"),
        "max_runtime_seconds": common_limits.get("max_runtime_seconds"),
        "max_triangles": common_limits.get("max_triangles"),
        "max_vertices": common_limits.get("max_vertices"),
    }
    base = {name: value for name, value in plan.items() if name != "work_id"}
    binding = plan.get("input_binding")
    if (
        set(plan) != expected_plan_fields
        or plan.get("schema") != "MVX-P2C-EXECUTION-PLAN"
        or plan.get("schema_version") != "0.1.0"
        or plan.get("algorithm_id") != versions.get("algorithm_id")
        or plan.get("algorithm_version") != "0.3.0"
        or plan.get("authority_policy") != "REQUIRE_EXTERNAL_ANCHOR"
        or plan.get("code_sha256") != preexecution.get("runner_sha256")
        or plan.get("environment") != runtime.get("runner_environment")
        or plan.get("work_id") != _p2c_hash(base)
        or plan.get("source_sha256") != parent["source_sha256"]
        or plan.get("source_size_bytes") != parent["source_size_bytes"]
        or plan.get("max_input_bytes") != common_limits.get("max_input_bytes")
        or plan.get("external_anchor_public_key_hex") != public_key
        or plan.get("limits") != expected_limits
        or not isinstance(binding, dict)
        or set(binding) != expected_binding_fields
        or binding.get("audit_record_sha256") != parent["audit_record_sha256"]
        or binding.get("execution_plan_file_sha256") != parent["p2a_execution_plan_file_sha256"]
        or binding.get("p2a_work_id") != parent["p2a_work_id"]
        or binding.get("execution_plan_sha256") != parent["p2a_execution_plan_sha256"]
        or binding.get("p2a_terminal_checkpoint_sha256") != parent["p2a_terminal_checkpoint_sha256"]
        or binding.get("materializer_id") != versions.get("materializer_id")
        or binding.get("materializer_version") != "0.2.0"
        or binding.get("mode") != "P2A_BOUND"
    ):
        raise ContinuityError("V2_PLAN_PARENT_OR_IDENTITY_LINK")
    _require_sha256(binding.get("materializer_code_sha256"), "V2_MATERIALIZER_CODE")
    _require_sha256(binding.get("mesh_sha256"), "V2_MESH_SHA256")


def _validate_final_continuity(
    manifest: Mapping[str, Any],
    preregistration: Mapping[str, Any],
    persistent_signer_public_key: str,
) -> None:
    expected_top = {
        "campaign_id",
        "persistent_signer_public_key_ed25519_hex",
        "preregistration_value_sha256",
        "schema",
        "schema_version",
        "slots",
        "status",
        "v1_terminal_evidence_root_sha256",
    }
    if set(manifest) != expected_top:
        raise ContinuityError("FINAL_CONTINUITY_FIELDS")
    expected_public_key = _require_sha256(
        persistent_signer_public_key, "FINAL_CONTINUITY_SIGNER_PUBLIC_KEY"
    )
    manifest_public_key = _require_sha256(
        manifest.get("persistent_signer_public_key_ed25519_hex"),
        "FINAL_CONTINUITY_SIGNER_PUBLIC_KEY",
    )
    if (
        manifest.get("schema") != CONTINUITY_SCHEMA
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("campaign_id") != CAMPAIGN_ID
        or manifest.get("status") != "FROZEN_BEFORE_FIRST_V2_CHILD"
        or manifest_public_key != expected_public_key
        or manifest.get("v1_terminal_evidence_root_sha256") != V1_ROOT
        or manifest.get("preregistration_value_sha256") != _p2c_hash(preregistration)
    ):
        raise ContinuityError("FINAL_CONTINUITY_IDENTITY")
    slots = manifest.get("slots")
    if not isinstance(slots, list) or len(slots) != 4:
        raise ContinuityError("FINAL_CONTINUITY_SLOTS")
    binding_fields = {
        "execution_plan_sha256",
        "p2a_execution_plan_sha256",
        "p2a_terminal_checkpoint_sha256",
        "p2a_work_id",
        "source_sha256",
        "work_id",
    }
    v1_ids: set[str] = set()
    v2_ids: set[str] = set()
    aliases: dict[str, tuple[str, ...]] = {}
    for row, expected in zip(slots, SLOT_ROWS, strict=True):
        slot, slot_id, comparison, alias, profile, limit = expected
        del slot
        if set(row) != {
            "comparison_slot",
            "max_candidate_pairs",
            "private_parent_alias",
            "profile_id",
            "slot_id",
            "v1",
            "v2",
        }:
            raise ContinuityError("FINAL_CONTINUITY_SLOT_FIELDS")
        if (
            row["slot_id"] != slot_id
            or row["comparison_slot"] != comparison
            or row["private_parent_alias"] != f"PARENT_{alias}"
            or row["profile_id"] != profile
            or row["max_candidate_pairs"] != limit
        ):
            raise ContinuityError("FINAL_CONTINUITY_SLOT_MAPPING")
        for campaign in ("v1", "v2"):
            binding = row[campaign]
            if not isinstance(binding, dict) or set(binding) != binding_fields:
                raise ContinuityError("FINAL_CONTINUITY_BINDING_FIELDS")
            for value in binding.values():
                _require_sha256(value, "FINAL_CONTINUITY_SHA256")
        for name in binding_fields - {"execution_plan_sha256", "work_id"}:
            if row["v1"][name] != row["v2"][name]:
                raise ContinuityError("FINAL_CONTINUITY_PARENT_REUSE")
        if row["v1"]["work_id"] == row["v2"]["work_id"]:
            raise ContinuityError("FINAL_CONTINUITY_V1_REUSE")
        v1_ids.add(row["v1"]["work_id"])
        v2_ids.add(row["v2"]["work_id"])
        parent = row["v2"]
        identity = tuple(
            parent[name]
            for name in (
                "source_sha256",
                "p2a_execution_plan_sha256",
                "p2a_terminal_checkpoint_sha256",
                "p2a_work_id",
            )
        )
        previous = aliases.setdefault(alias, identity)
        if previous != identity:
            raise ContinuityError("FINAL_CONTINUITY_ALIAS_COLLISION")
    if len(v1_ids) != 4 or len(v2_ids) != 4 or len(set(aliases.values())) != 3:
        raise ContinuityError("FINAL_CONTINUITY_CARDINALITY")


def validate_frozen_continuity(
    manifest_path: Path,
    authentication_path: Path,
    *,
    signer_manifest_payload: bytes,
    preregistration: Mapping[str, Any],
    prefreeze_bundle_raw_bytes_sha256: str,
    prefreeze_manifest_sha256: str,
) -> dict[str, Any]:
    manifest_payload = _safe_read(manifest_path, private_modes={0o600})
    manifest = _decode_json(manifest_payload)
    if not isinstance(manifest, dict) or manifest_payload != _canonical_bytes(
        manifest, newline=True
    ):
        raise ContinuityError("FINAL_CONTINUITY_NOT_CANONICAL")
    public = _signer_public_key(_decode_json(signer_manifest_payload))
    _validate_final_continuity(manifest, preregistration, public)
    authentication_payload = _safe_read(authentication_path, private_modes={0o600})
    document = _decode_json(authentication_payload)
    if not isinstance(document, dict) or set(document) != {"authentication", "payload"}:
        raise ContinuityError("DETACHED_AUTHENTICATION_FIELDS")
    authentication = document["authentication"]
    if not isinstance(authentication, dict):
        raise ContinuityError("DETACHED_AUTHENTICATION_FIELDS")
    expected_context = {
        "prefreeze_bundle_raw_bytes_sha256": prefreeze_bundle_raw_bytes_sha256,
        "prefreeze_manifest_sha256": prefreeze_manifest_sha256,
    }
    expected_payload = _signature_payload(
        CONTINUITY_SIGNATURE_DOMAIN,
        manifest,
        _sha256(signer_manifest_payload),
        expected_context,
    )
    if _canonical_bytes(document["payload"], newline=True) != expected_payload:
        raise ContinuityError("DETACHED_AUTHENTICATION_PAYLOAD")
    if (
        authentication.get("schema") != SIGNATURE_SCHEMA
        or authentication.get("schema_version") != SCHEMA_VERSION
        or authentication.get("signed_manifest_schema") != CONTINUITY_SCHEMA
        or authentication.get("domain") != CONTINUITY_SIGNATURE_DOMAIN
        or authentication.get("context") != expected_context
        or authentication.get("manifest_sha256") != _p2c_hash(manifest)
        or authentication.get("payload_raw_bytes_sha256") != _sha256(expected_payload)
        or authentication.get("signer_manifest_raw_bytes_sha256")
        != _sha256(signer_manifest_payload)
    ):
        raise ContinuityError("DETACHED_AUTHENTICATION_BINDING")
    if authentication.get("public_key_ed25519_hex") != public:
        raise ContinuityError("DETACHED_AUTHENTICATION_SIGNER")
    signature = authentication.get("signature_hex")
    if not isinstance(signature, str) or HEX_SIGNATURE.fullmatch(signature) is None:
        raise ContinuityError("DETACHED_AUTHENTICATION_SIGNATURE")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(
            bytes.fromhex(signature), expected_payload
        )
    except (InvalidSignature, ValueError) as error:
        raise ContinuityError("DETACHED_AUTHENTICATION_SIGNATURE") from error
    return {"action": "CONTINUITY_VALID"}


def validate_continuity_from_bundle(
    bundle: Path, manifest: Path, authentication: Path
) -> dict[str, Any]:
    """Validate a detached final freeze using only the immutable pre-plan bundle."""

    validate_bundle(bundle)
    files, _ = _read_bundle(bundle)
    prefreeze = _bundle_json(files, "manifest.json")
    prereg_path = prefreeze["code"]["bindings"]["preregistration"]["bundle_path"]
    signer_path = prefreeze["code"]["bindings"]["signer_manifest"]["bundle_path"]
    return validate_frozen_continuity(
        manifest,
        authentication,
        signer_manifest_payload=files[signer_path],
        preregistration=_bundle_json(files, prereg_path),
        prefreeze_bundle_raw_bytes_sha256=_sha256(
            _safe_read(bundle, limit=MAX_BUNDLE_BYTES, private_modes={0o600})
        ),
        prefreeze_manifest_sha256=_p2c_hash(prefreeze),
    )


def _parse_plan_arguments(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ContinuityError("V2_PLAN_ARGUMENT")
        slot, path = value.split("=", 1)
        if slot in result or slot not in {row[0] for row in SLOT_ROWS} or not path:
            raise ContinuityError("V2_PLAN_ARGUMENT")
        result[slot] = Path(path)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--spec", type=Path, required=True)
    build.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--signing-key", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--repository", type=Path)
    restore = commands.add_parser("restore-test")
    restore.add_argument("--bundle", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    restore.add_argument("--repository", type=Path)
    freeze = commands.add_parser("freeze-continuity")
    freeze.add_argument("--bundle", type=Path, required=True)
    freeze.add_argument("--v2-plan", action="append", required=True)
    freeze.add_argument("--output-manifest", type=Path, required=True)
    freeze.add_argument("--output-authentication", type=Path, required=True)
    freeze.add_argument("--signing-key", type=Path, required=True)
    validate_continuity = commands.add_parser("validate-continuity")
    validate_continuity.add_argument("--bundle", type=Path, required=True)
    validate_continuity.add_argument("--manifest", type=Path, required=True)
    validate_continuity.add_argument("--authentication", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "build":
            result = build_bundle(
                arguments.spec,
                arguments.repository,
                arguments.output,
                signing_key=arguments.signing_key,
            )
        elif arguments.command == "validate":
            result = validate_bundle(arguments.bundle, repository=arguments.repository)
        elif arguments.command == "restore-test":
            result = restore_test(
                arguments.bundle,
                arguments.destination,
                repository=arguments.repository,
            )
        elif arguments.command == "freeze-continuity":
            result = freeze_continuity(
                arguments.bundle,
                _parse_plan_arguments(arguments.v2_plan),
                arguments.output_manifest,
                arguments.output_authentication,
                signing_key=arguments.signing_key,
            )
        elif arguments.command == "validate-continuity":
            result = validate_continuity_from_bundle(
                arguments.bundle, arguments.manifest, arguments.authentication
            )
        else:  # pragma: no cover - argparse closes this branch.
            raise ContinuityError("UNKNOWN_COMMAND")
    except ContinuityError as error:
        print(json.dumps({"action": "ERROR", "code": error.code}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
