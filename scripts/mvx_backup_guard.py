#!/usr/bin/env python3
"""Fail-closed verifier for append-only Morphoia Drive checkpoints.

The script never contacts Drive.  After a reset, materialise ``checkpoint.json``,
``COMPLETED.json`` and ``LATEST.json`` plus the optional artifact map, then run
this verifier before treating a stage as complete.  ``SKIP`` is emitted only
when the complete chain revalidates byte-for-byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 16 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
APPEND_ONLY_MODEL = "APPEND_ONLY_VERSIONED_FOLDERS"
LATEST_MODEL = "APPEND_ONLY_VERSIONED_FOLDERS_WITH_MUTABLE_LATEST_POINTER"


class GuardError(RuntimeError):
    """Raised when a checkpoint cannot safely authorize ``SKIP``."""


def _safe_bytes(path: Path, *, limit: int | None = None) -> bytes:
    """Read one owned regular file without following a symlink or racing replacement."""

    try:
        before = path.lstat()
    except OSError as error:
        raise GuardError("MISSING_OR_UNREADABLE_INPUT") from error
    if not stat.S_ISREG(before.st_mode) or path.is_symlink():
        raise GuardError("INPUT_NOT_REGULAR_FILE")
    if before.st_uid != os.getuid():
        raise GuardError("INPUT_NOT_OWNED_BY_WORKER")
    if limit is not None and before.st_size > limit:
        raise GuardError("INPUT_SIZE_LIMIT")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise GuardError("SAFE_OPEN_FAILED") from error
    with os.fdopen(descriptor, "rb") as stream:
        payload = stream.read()
        after = os.fstat(stream.fileno())
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != before.st_size:
        raise GuardError("INPUT_CHANGED_DURING_READ")
    return payload


def _pairs_no_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GuardError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json_bytes(path: Path) -> tuple[bytes, dict[str, Any]]:
    payload = _safe_bytes(path, limit=MAX_JSON_BYTES)
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(GuardError("NONFINITE_JSON")),
        )
    except GuardError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GuardError("INVALID_JSON") from error
    if not isinstance(value, dict):
        raise GuardError("JSON_ROOT_NOT_OBJECT")
    return payload, value


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GuardError(code)
    return value


def _sequence(value: Any, code: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise GuardError(code)
    return value


def _string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise GuardError(code)
    return value


def _sha(value: Any, code: str) -> str:
    text = _string(value, code)
    if SHA256.fullmatch(text) is None:
        raise GuardError(code)
    return text


def _sha1(value: Any, code: str) -> str:
    text = _string(value, code)
    if SHA1.fullmatch(text) is None:
        raise GuardError(code)
    return text


def _positive_size(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GuardError(code)
    return value


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact_contract(checkpoint: Mapping[str, Any]) -> dict[str, tuple[int, str]]:
    drive = _mapping(checkpoint.get("drive"), "CHECKPOINT_DRIVE_INVALID")
    files = _sequence(drive.get("files"), "CHECKPOINT_FILES_INVALID")
    expected: dict[str, tuple[int, str]] = {}
    names: set[str] = set()
    for row in files:
        item = _mapping(row, "CHECKPOINT_FILE_ROW_INVALID")
        file_id = _string(item.get("drive_file_id"), "CHECKPOINT_FILE_ID_INVALID")
        name = _string(item.get("name"), "CHECKPOINT_FILE_NAME_INVALID")
        if file_id in expected or name in names:
            raise GuardError("CHECKPOINT_ARTIFACT_NOT_UNIQUE")
        expected[file_id] = (
            _positive_size(item.get("bytes"), "CHECKPOINT_FILE_SIZE_INVALID"),
            _sha(item.get("sha256"), "CHECKPOINT_FILE_HASH_INVALID"),
        )
        if item.get("download_verified") is not True:
            raise GuardError("CHECKPOINT_ARTIFACT_NOT_VERIFIED")
        names.add(name)

    predecessor = _mapping(checkpoint.get("predecessor_evidence"), "PREDECESSOR_EVIDENCE_INVALID")
    for field in ("exact_latest_snapshot", "revision_evidence"):
        item = _mapping(predecessor.get(field), "PREDECESSOR_EVIDENCE_ITEM_INVALID")
        file_id = _string(item.get("drive_file_id"), "PREDECESSOR_FILE_ID_INVALID")
        if file_id in expected:
            raise GuardError("CHECKPOINT_ARTIFACT_NOT_UNIQUE")
        expected[file_id] = (
            _positive_size(item.get("bytes"), "PREDECESSOR_FILE_SIZE_INVALID"),
            _sha(item.get("sha256"), "PREDECESSOR_FILE_HASH_INVALID"),
        )
        if item.get("download_verified") is not True:
            raise GuardError("PREDECESSOR_EVIDENCE_NOT_VERIFIED")
    return expected


def _artifact_origin_contract(checkpoint: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    """Return the declared payload origin and embedded-payload name→ID mapping."""

    checkpoint_id = _string(checkpoint.get("checkpoint_id"), "CHECKPOINT_ID_INVALID")
    origin = _string(checkpoint.get("artifact_origin_checkpoint_id"), "ARTIFACT_ORIGIN_ID_INVALID")
    policy = _mapping(checkpoint.get("artifact_origin_policy"), "ARTIFACT_ORIGIN_POLICY_INVALID")
    if (
        policy.get("envelope_checkpoint_id") != checkpoint_id
        or policy.get("storage_checkpoint_id") != checkpoint_id
    ):
        raise GuardError("ARTIFACT_ORIGIN_ENVELOPE_MISMATCH")
    raw_names = _sequence(
        policy.get("embedded_origin_is_expected_in"), "ARTIFACT_ORIGIN_NAMES_INVALID"
    )
    if not raw_names:
        raise GuardError("ARTIFACT_ORIGIN_NAMES_INVALID")
    names: list[str] = []
    for value in raw_names:
        name = _string(value, "ARTIFACT_ORIGIN_NAME_INVALID")
        if name in names:
            raise GuardError("ARTIFACT_ORIGIN_NAME_NOT_UNIQUE")
        names.append(name)
    rule = _string(policy.get("validation_rule"), "ARTIFACT_ORIGIN_RULE_INVALID")
    if "MUST equal artifact_origin_checkpoint_id" not in rule:
        raise GuardError("ARTIFACT_ORIGIN_RULE_INVALID")

    files = _sequence(
        _mapping(checkpoint.get("drive"), "CHECKPOINT_DRIVE_INVALID").get("files"),
        "CHECKPOINT_FILES_INVALID",
    )
    by_name: dict[str, str] = {}
    for row in files:
        item = _mapping(row, "CHECKPOINT_FILE_ROW_INVALID")
        name = _string(item.get("name"), "CHECKPOINT_FILE_NAME_INVALID")
        file_id = _string(item.get("drive_file_id"), "CHECKPOINT_FILE_ID_INVALID")
        if name in by_name:
            raise GuardError("CHECKPOINT_ARTIFACT_NOT_UNIQUE")
        by_name[name] = file_id
    if any(name not in by_name for name in names):
        raise GuardError("ARTIFACT_ORIGIN_PAYLOAD_NOT_COMMITTED")
    return origin, {name: by_name[name] for name in names}


def verify_chain(
    *,
    checkpoint_bytes: bytes,
    checkpoint: Mapping[str, Any],
    completed_bytes: bytes,
    completed: Mapping[str, Any],
    latest: Mapping[str, Any],
    completed_drive_id: str | None = None,
) -> dict[str, Any]:
    """Validate the three-document checkpoint chain and return a safe summary."""

    checkpoint_id = _string(checkpoint.get("checkpoint_id"), "CHECKPOINT_ID_INVALID")
    if checkpoint.get("schema") != "MORPHOIA-MVX-DRIVE-CHECKPOINT":
        raise GuardError("CHECKPOINT_SCHEMA_INVALID")
    if checkpoint.get("state") != "ARTIFACTS_VERIFIED":
        raise GuardError("CHECKPOINT_STATE_INVALID")
    if checkpoint.get("publication_model") != APPEND_ONLY_MODEL:
        raise GuardError("CHECKPOINT_NOT_APPEND_ONLY")
    if completed.get("schema") != "MORPHOIA-MVX-DRIVE-CHECKPOINT-COMPLETED":
        raise GuardError("COMPLETED_SCHEMA_INVALID")
    if completed.get("state") != "COMPLETED":
        raise GuardError("COMPLETED_STATE_INVALID")
    if completed.get("publication_model") != APPEND_ONLY_MODEL:
        raise GuardError("COMPLETED_NOT_APPEND_ONLY")
    if completed.get("checkpoint_id") != checkpoint_id:
        raise GuardError("COMPLETED_CHECKPOINT_ID_MISMATCH")
    if latest.get("schema") != "MORPHOIA-MVX-DRIVE-LATEST":
        raise GuardError("LATEST_SCHEMA_INVALID")
    if latest.get("state") != "COMPLETED" or latest.get("checkpoint_id") != checkpoint_id:
        raise GuardError("LATEST_NOT_CURRENT_COMPLETED_CHECKPOINT")
    if latest.get("publication_model") != LATEST_MODEL:
        raise GuardError("LATEST_MODEL_INVALID")

    predecessor = _string(
        checkpoint.get("predecessor_checkpoint_id"), "PREDECESSOR_CHECKPOINT_ID_INVALID"
    )
    if completed.get("predecessor_checkpoint_id") != predecessor:
        raise GuardError("COMPLETED_PREDECESSOR_MISMATCH")
    if latest.get("predecessor_checkpoint_id") != predecessor:
        raise GuardError("LATEST_PREDECESSOR_MISMATCH")

    artifact_origin, _ = _artifact_origin_contract(checkpoint)
    if completed.get("artifact_origin_checkpoint_id") != artifact_origin:
        raise GuardError("COMPLETED_ARTIFACT_ORIGIN_MISMATCH")
    if latest.get("artifact_origin_checkpoint_id") != artifact_origin:
        raise GuardError("LATEST_ARTIFACT_ORIGIN_MISMATCH")
    for document, code in (
        (completed, "COMPLETED_ARTIFACT_ORIGIN_POLICY_INVALID"),
        (latest, "LATEST_ARTIFACT_ORIGIN_POLICY_INVALID"),
    ):
        policy_text = _string(document.get("artifact_origin_policy"), code)
        if "artifact_origin_checkpoint_id" not in policy_text:
            raise GuardError(code)

    checkpoint_hash = _digest(checkpoint_bytes)
    completed_hash = _digest(completed_bytes)
    checkpoint_size = len(checkpoint_bytes)
    completed_size = len(completed_bytes)
    completed_registry = _mapping(
        completed.get("checkpoint_registry"), "COMPLETED_REGISTRY_INVALID"
    )
    latest_registry = _mapping(latest.get("checkpoint_registry"), "LATEST_REGISTRY_INVALID")
    latest_terminal = _mapping(latest.get("terminal_marker"), "LATEST_TERMINAL_INVALID")
    registry_id = _string(completed_registry.get("drive_file_id"), "CHECKPOINT_DRIVE_ID_INVALID")
    if (
        _sha(completed_registry.get("sha256"), "COMPLETED_CHECKPOINT_HASH_INVALID")
        != checkpoint_hash
        or _positive_size(completed_registry.get("bytes"), "COMPLETED_CHECKPOINT_SIZE_INVALID")
        != checkpoint_size
        or completed_registry.get("download_verified") is not True
    ):
        raise GuardError("COMPLETED_CHECKPOINT_BYTES_MISMATCH")
    if (
        latest_registry.get("drive_file_id") != registry_id
        or latest_registry.get("sha256") != checkpoint_hash
        or latest_registry.get("bytes") != checkpoint_size
        or latest_registry.get("download_verified") is not True
    ):
        raise GuardError("LATEST_CHECKPOINT_BYTES_MISMATCH")
    if (
        latest_terminal.get("sha256") != completed_hash
        or latest_terminal.get("bytes") != completed_size
        or latest_terminal.get("download_verified") is not True
    ):
        raise GuardError("LATEST_COMPLETED_BYTES_MISMATCH")
    if (
        completed_drive_id is not None
        and latest_terminal.get("drive_file_id") != completed_drive_id
    ):
        raise GuardError("LATEST_COMPLETED_DRIVE_ID_MISMATCH")

    checkpoint_drive = _mapping(checkpoint.get("drive"), "CHECKPOINT_DRIVE_INVALID")
    checkpoint_registry_folder = checkpoint_drive.get("registry_folder_id")
    if (
        completed.get("registry_folder_id") != checkpoint_registry_folder
        or latest.get("registry_folder_id") != checkpoint_registry_folder
    ):
        raise GuardError("REGISTRY_FOLDER_MISMATCH")

    expected_artifacts = _artifact_contract(checkpoint)
    completed_rows = _sequence(completed.get("artifact_set"), "COMPLETED_ARTIFACT_SET_INVALID")
    completed_artifacts: dict[str, str] = {}
    for row in completed_rows:
        item = _mapping(row, "COMPLETED_ARTIFACT_ROW_INVALID")
        file_id = _string(item.get("drive_file_id"), "COMPLETED_ARTIFACT_ID_INVALID")
        if file_id in completed_artifacts:
            raise GuardError("COMPLETED_ARTIFACT_NOT_UNIQUE")
        completed_artifacts[file_id] = _sha(item.get("sha256"), "COMPLETED_ARTIFACT_HASH_INVALID")
    if {key: value[1] for key, value in expected_artifacts.items()} != completed_artifacts:
        raise GuardError("COMPLETED_ARTIFACT_SET_MISMATCH")

    checkpoint_git = _mapping(checkpoint.get("git"), "CHECKPOINT_GIT_INVALID")
    latest_git = _mapping(latest.get("git"), "LATEST_GIT_INVALID")
    commit = _sha1(checkpoint_git.get("commit_sha"), "CHECKPOINT_COMMIT_INVALID")
    tree = _sha1(checkpoint_git.get("tree_sha"), "CHECKPOINT_TREE_INVALID")
    if completed.get("git_commit_sha") != commit or completed.get("git_tree_sha") != tree:
        raise GuardError("COMPLETED_GIT_MISMATCH")
    if latest_git.get("commit_sha") != commit or latest_git.get("tree_sha") != tree:
        raise GuardError("LATEST_GIT_MISMATCH")

    protocol = _mapping(checkpoint.get("protocol"), "CHECKPOINT_PROTOCOL_INVALID")
    protocol_root = _sha(protocol.get("root_sha256"), "PROTOCOL_ROOT_INVALID")
    if completed.get("protocol_root_sha256") != protocol_root:
        raise GuardError("COMPLETED_PROTOCOL_MISMATCH")
    latest_protocol = _mapping(latest.get("protocol"), "LATEST_PROTOCOL_INVALID")
    if latest_protocol.get("root_sha256") != protocol_root:
        raise GuardError("LATEST_PROTOCOL_MISMATCH")

    p2a = _mapping(checkpoint.get("p2a"), "CHECKPOINT_P2A_INVALID")
    scope = _sha(p2a.get("scope_commitment_sha256"), "P2A_SCOPE_INVALID")
    public_summary = _sha(p2a.get("public_summary_sha256"), "P2A_SUMMARY_INVALID")
    if (
        completed.get("p2a_scope_commitment_sha256") != scope
        or completed.get("p2a_public_summary_sha256") != public_summary
    ):
        raise GuardError("COMPLETED_P2A_MISMATCH")
    latest_p2a = _mapping(latest.get("p2a"), "LATEST_P2A_INVALID")
    if (
        latest_p2a.get("scope_commitment_sha256") != scope
        or latest_p2a.get("public_summary_sha256") != public_summary
        or latest_p2a.get("second_invocation_action") != "SKIP"
    ):
        raise GuardError("LATEST_P2A_MISMATCH")

    return {
        "action": "SKIP",
        "artifact_count": len(expected_artifacts),
        "artifact_origin_checkpoint_id": artifact_origin,
        "checkpoint_id": checkpoint_id,
        "checkpoint_sha256": checkpoint_hash,
        "completed_sha256": completed_hash,
        "git_commit_sha": commit,
        "protocol_root_sha256": protocol_root,
        "scope_commitment_sha256": scope,
    }


def _artifact_map(path: Path) -> dict[str, Path]:
    _, value = _json_bytes(path)
    result: dict[str, Path] = {}
    for file_id, raw_path in value.items():
        if not isinstance(file_id, str) or not file_id:
            raise GuardError("ARTIFACT_MAP_ID_INVALID")
        if not isinstance(raw_path, str) or not raw_path:
            raise GuardError("ARTIFACT_MAP_PATH_INVALID")
        result[file_id] = Path(raw_path)
    return result


def verify_materialised_artifacts(
    checkpoint: Mapping[str, Any], materialised: Mapping[str, Path]
) -> None:
    expected = _artifact_contract(checkpoint)
    if set(materialised) != set(expected):
        raise GuardError("ARTIFACT_MAP_SET_MISMATCH")
    for file_id, path in materialised.items():
        payload = _safe_bytes(path)
        expected_size, expected_hash = expected[file_id]
        if len(payload) != expected_size or _digest(payload) != expected_hash:
            raise GuardError("MATERIALISED_ARTIFACT_MISMATCH")

    origin, embedded = _artifact_origin_contract(checkpoint)
    for file_id in embedded.values():
        _, payload = _json_bytes(materialised[file_id])
        if payload.get("checkpoint_id") != origin:
            raise GuardError("MATERIALISED_ARTIFACT_ORIGIN_MISMATCH")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--completed", required=True, type=Path)
    parser.add_argument("--latest", required=True, type=Path)
    parser.add_argument("--completed-drive-id")
    parser.add_argument("--artifact-map", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checkpoint_bytes, checkpoint = _json_bytes(args.checkpoint)
        completed_bytes, completed = _json_bytes(args.completed)
        _, latest = _json_bytes(args.latest)
        result = verify_chain(
            checkpoint_bytes=checkpoint_bytes,
            checkpoint=checkpoint,
            completed_bytes=completed_bytes,
            completed=completed,
            latest=latest,
            completed_drive_id=args.completed_drive_id,
        )
        if args.artifact_map is not None:
            verify_materialised_artifacts(checkpoint, _artifact_map(args.artifact_map))
            result["materialised_artifacts_verified"] = result["artifact_count"]
    except GuardError as error:
        print(
            json.dumps(
                {"action": "BLOCKED", "error_code": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
