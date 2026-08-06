"""Deterministic execution checkpoints for resumable MVX validation work.

The checkpoint layer is deliberately independent from the codec and from the
P0 protocol implementation.  It answers one narrow question after a process or
workspace restart: may a unit of work be skipped, retried, started, or must it
fail closed?

``SKIP`` is possible only for a terminal checkpoint whose declared artifacts
still exist and match their SHA-256 digests.  A partial ordinary job is retried.
Any evidence that a blind or otherwise ``open_once`` job started but did not
finish with verifiable terminal artifacts fails closed and is never rerun
automatically.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .custody import canonical_json_bytes

SCHEMA_VERSION = "0.1.0"
PLAN_SCHEMA = "MVX-EXECUTION-PLAN"
CHECKPOINT_SCHEMA = "MVX-STAGE-CHECKPOINT"
WORK_ID_ALGORITHM = "MVX-WORK-ID-SHA256-JCS-1"
OPEN_ONCE_CLAIM_SUFFIX = ".open-once-running.json"

_SHA256_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")
_SPLITS = frozenset(("none", "development", "calibration", "blind", "reserve"))
_CHECKPOINT_STATES = frozenset(("PENDING", "RUNNING", "PARTIAL", "INTERRUPTED", "TERMINAL"))
_TERMINAL_STATUSES = frozenset(("PASS", "DECLARED_LIMIT", "REJECT", "FAIL"))


class CheckpointValidationError(ValueError):
    """Raised when a plan or checkpoint is internally inconsistent."""


class ResumeAction(StrEnum):
    """Fail-safe action returned by :func:`assess_resume`."""

    RUN = "RUN"
    RETRY = "RETRY"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"
    FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True, slots=True)
class ResumeAssessment:
    action: ResumeAction
    work_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class WorkIdentity:
    """All stable inputs that define one executable unit of work.

    Phase and stage are included in addition to the required protocol, split,
    source, lineage, profile, configuration, code and environment bindings so
    that successive processing stages can never alias the same work ID.
    """

    protocol_root_sha256: str
    split_sha256: str
    source_sha256: str
    lineage_id: str
    profile_sha256: str
    config_sha256: str
    code_sha256: str
    environment_sha256: str
    phase_id: str
    stage_id: str
    split: str = "none"
    open_once: bool = False

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "protocol_root_sha256": self.protocol_root_sha256,
            "split_sha256": self.split_sha256,
            "source_sha256": self.source_sha256,
            "lineage_id": self.lineage_id,
            "profile_sha256": self.profile_sha256,
            "config_sha256": self.config_sha256,
            "code_sha256": self.code_sha256,
            "environment_sha256": self.environment_sha256,
            "phase_id": self.phase_id,
            "stage_id": self.stage_id,
            "split": self.split,
            "open_once": self.open_once,
        }

    @property
    def work_id(self) -> str:
        return derive_work_id(self)


def _require_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CheckpointValidationError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in _HEX_DIGITS for character in value)
    ):
        raise CheckpointValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _require_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise CheckpointValidationError(f"{field} must be a boolean")
    return value


def _identity_from_mapping(value: Mapping[str, Any]) -> WorkIdentity:
    expected = {
        "protocol_root_sha256",
        "split_sha256",
        "source_sha256",
        "lineage_id",
        "profile_sha256",
        "config_sha256",
        "code_sha256",
        "environment_sha256",
        "phase_id",
        "stage_id",
        "split",
        "open_once",
    }
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise CheckpointValidationError(
            f"work identity fields differ; missing={missing}, extra={extra}"
        )
    identity = WorkIdentity(
        protocol_root_sha256=_require_sha256(
            value["protocol_root_sha256"], field="identity.protocol_root_sha256"
        ),
        split_sha256=_require_sha256(value["split_sha256"], field="identity.split_sha256"),
        source_sha256=_require_sha256(value["source_sha256"], field="identity.source_sha256"),
        lineage_id=_require_string(value["lineage_id"], field="identity.lineage_id"),
        profile_sha256=_require_sha256(value["profile_sha256"], field="identity.profile_sha256"),
        config_sha256=_require_sha256(value["config_sha256"], field="identity.config_sha256"),
        code_sha256=_require_sha256(value["code_sha256"], field="identity.code_sha256"),
        environment_sha256=_require_sha256(
            value["environment_sha256"], field="identity.environment_sha256"
        ),
        phase_id=_require_string(value["phase_id"], field="identity.phase_id"),
        stage_id=_require_string(value["stage_id"], field="identity.stage_id"),
        split=_require_string(value["split"], field="identity.split"),
        open_once=_require_bool(value["open_once"], field="identity.open_once"),
    )
    if identity.split not in _SPLITS:
        raise CheckpointValidationError(f"identity.split is unsupported: {identity.split!r}")
    if identity.split == "blind" and not identity.open_once:
        raise CheckpointValidationError("blind work must be open_once")
    return identity


def derive_work_id(identity: WorkIdentity | Mapping[str, Any]) -> str:
    """Return the canonical content-derived identifier for a unit of work."""

    if isinstance(identity, WorkIdentity):
        checked = _identity_from_mapping(identity.as_dict())
    elif isinstance(identity, Mapping):
        checked = _identity_from_mapping(identity)
    else:
        raise CheckpointValidationError("identity must be WorkIdentity or a mapping")
    payload = {
        "algorithm_id": WORK_ID_ALGORITHM,
        "identity": checked.as_dict(),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def make_stage(
    identity: WorkIdentity,
    *,
    required_artifacts: Sequence[str],
    depends_on_work_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Create a validated execution-plan stage."""

    _identity_from_mapping(identity.as_dict())
    artifacts = list(required_artifacts)
    if not artifacts or any(not isinstance(item, str) or not item for item in artifacts):
        raise CheckpointValidationError("required_artifacts must contain non-empty names")
    if len(set(artifacts)) != len(artifacts):
        raise CheckpointValidationError("required_artifacts must be unique")
    dependencies = list(depends_on_work_ids)
    for index, dependency in enumerate(dependencies):
        _require_sha256(dependency, field=f"depends_on_work_ids[{index}]")
    if len(set(dependencies)) != len(dependencies):
        raise CheckpointValidationError("depends_on_work_ids must be unique")
    return {
        "work_id": identity.work_id,
        "identity": identity.as_dict(),
        "required_artifacts": artifacts,
        "depends_on_work_ids": dependencies,
    }


def make_execution_plan(plan_id: str, stages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Create and semantically validate an ordered execution plan."""

    plan = {
        "schema": PLAN_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "work_id_algorithm": WORK_ID_ALGORITHM,
        "plan_id": _require_string(plan_id, field="plan_id"),
        "stages": copy.deepcopy(list(stages)),
    }
    return validate_execution_plan(plan)


def validate_execution_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate work IDs, ordering and dependency topology fail-closed."""

    if not isinstance(plan, Mapping):
        raise CheckpointValidationError("execution plan must be an object")
    document = copy.deepcopy(dict(plan))
    expected = {"schema", "schema_version", "work_id_algorithm", "plan_id", "stages"}
    if set(document) != expected:
        raise CheckpointValidationError("execution plan has missing or unsupported fields")
    if document["schema"] != PLAN_SCHEMA or document["schema_version"] != SCHEMA_VERSION:
        raise CheckpointValidationError("execution plan schema identity is invalid")
    if document["work_id_algorithm"] != WORK_ID_ALGORITHM:
        raise CheckpointValidationError("execution plan work ID algorithm is invalid")
    _require_string(document["plan_id"], field="plan_id")
    stages = document["stages"]
    if not isinstance(stages, list) or not stages:
        raise CheckpointValidationError("execution plan requires at least one stage")

    prior: set[str] = set()
    seen_stage_keys: set[tuple[str, str, str]] = set()
    for index, stage in enumerate(stages):
        if not isinstance(stage, Mapping):
            raise CheckpointValidationError(f"stage {index} must be an object")
        stage_expected = {
            "work_id",
            "identity",
            "required_artifacts",
            "depends_on_work_ids",
        }
        if set(stage) != stage_expected:
            raise CheckpointValidationError(f"stage {index} has missing or unsupported fields")
        identity_raw = stage["identity"]
        if not isinstance(identity_raw, Mapping):
            raise CheckpointValidationError(f"stage {index}.identity must be an object")
        identity = _identity_from_mapping(identity_raw)
        work_id = _require_sha256(stage["work_id"], field=f"stage {index}.work_id")
        if work_id != identity.work_id:
            raise CheckpointValidationError(f"stage {index} work_id does not bind its identity")
        if work_id in prior:
            raise CheckpointValidationError(f"duplicate work_id at stage {index}")

        stage_key = (identity.phase_id, identity.stage_id, identity.lineage_id)
        if stage_key in seen_stage_keys:
            raise CheckpointValidationError(f"duplicate phase/stage/lineage key at stage {index}")
        seen_stage_keys.add(stage_key)

        artifacts = stage["required_artifacts"]
        if (
            not isinstance(artifacts, list)
            or not artifacts
            or any(not isinstance(item, str) or not item for item in artifacts)
            or len(set(artifacts)) != len(artifacts)
        ):
            raise CheckpointValidationError(
                f"stage {index}.required_artifacts must be a non-empty unique string list"
            )
        dependencies = stage["depends_on_work_ids"]
        if not isinstance(dependencies, list) or len(set(dependencies)) != len(dependencies):
            raise CheckpointValidationError(f"stage {index} dependencies are invalid")
        for dependency in dependencies:
            _require_sha256(dependency, field=f"stage {index}.dependency")
            if dependency not in prior:
                raise CheckpointValidationError(
                    f"stage {index} dependency is absent, forward, or cyclic"
                )
        prior.add(work_id)
    return document


def execution_plan_sha256(plan: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(validate_execution_plan(plan))).hexdigest()


def _stage_by_work_id(plan: Mapping[str, Any], work_id: str) -> dict[str, Any]:
    checked = validate_execution_plan(plan)
    for stage in checked["stages"]:
        if stage["work_id"] == work_id:
            return stage
    raise CheckpointValidationError(f"work_id {work_id!r} is absent from execution plan")


def checkpoint_sha256(checkpoint: Mapping[str, Any]) -> str:
    """Hash the stable checkpoint fields, excluding explicitly volatile metadata."""

    document = copy.deepcopy(dict(checkpoint))
    document.pop("volatile", None)
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _open_regular_fd(path: Path, *, field: str) -> tuple[int, os.stat_result]:
    """Open one regular file without following a symbolic link or inode swap."""

    try:
        expected = path.lstat()
    except OSError as error:
        raise CheckpointValidationError(f"cannot inspect {field} {path}: {error}") from error
    if not stat.S_ISREG(expected.st_mode):
        raise CheckpointValidationError(f"{field} is not a regular file: {path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CheckpointValidationError(f"cannot safely open {field} {path}: {error}") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            expected.st_dev,
            expected.st_ino,
        ):
            raise CheckpointValidationError(f"{field} changed while being opened: {path}")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor, expected


def _unchanged_file(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )


def _read_regular_bytes(path: Path, *, field: str) -> bytes:
    descriptor, before = _open_regular_fd(path, field=field)
    with os.fdopen(descriptor, "rb") as stream:
        payload = stream.read()
        after = os.fstat(stream.fileno())
    if not _unchanged_file(before, after):
        raise CheckpointValidationError(f"{field} changed while being read: {path}")
    return payload


def hash_artifact(path: str | os.PathLike[str]) -> str:
    """Hash one regular artifact file without following symbolic links."""

    artifact = Path(path)
    descriptor, before = _open_regular_fd(artifact, field="artifact")
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
    if not _unchanged_file(before, after):
        raise CheckpointValidationError(f"artifact changed while being hashed: {artifact}")
    return digest.hexdigest()


def hash_artifacts(paths: Mapping[str, str | os.PathLike[str]]) -> dict[str, str]:
    if not isinstance(paths, Mapping):
        raise CheckpointValidationError("artifact paths must be an object")
    return {name: hash_artifact(path) for name, path in sorted(paths.items())}


def _validate_hash_map(value: Any, *, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise CheckpointValidationError(f"{field} must be an object")
    checked: dict[str, str] = {}
    for name, digest in value.items():
        _require_string(name, field=f"{field} artifact name")
        checked[name] = _require_sha256(digest, field=f"{field}.{name}")
    return checked


def _terminal_and_complete(checkpoint: Mapping[str, Any], stage: Mapping[str, Any]) -> bool:
    if checkpoint.get("state") != "TERMINAL":
        return False
    declared = checkpoint.get("artifact_hashes")
    if not isinstance(declared, Mapping):
        return False
    return set(stage["required_artifacts"]).issubset(declared)


def validate_stage_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a checkpoint and optionally bind it to its execution plan."""

    if not isinstance(checkpoint, Mapping):
        raise CheckpointValidationError("stage checkpoint must be an object")
    document = copy.deepcopy(dict(checkpoint))
    expected = {
        "schema",
        "schema_version",
        "execution_plan_sha256",
        "work_id",
        "identity",
        "attempt",
        "state",
        "terminal_status",
        "error_code",
        "interruption_reason",
        "artifact_hashes",
        "dependency_checkpoint_hashes",
        "previous_checkpoint_sha256",
        "volatile",
    }
    if set(document) != expected:
        raise CheckpointValidationError("stage checkpoint has missing or unsupported fields")
    if document["schema"] != CHECKPOINT_SCHEMA or document["schema_version"] != SCHEMA_VERSION:
        raise CheckpointValidationError("stage checkpoint schema identity is invalid")
    _require_sha256(document["execution_plan_sha256"], field="execution_plan_sha256")
    work_id = _require_sha256(document["work_id"], field="work_id")
    identity_raw = document["identity"]
    if not isinstance(identity_raw, Mapping):
        raise CheckpointValidationError("checkpoint identity must be an object")
    identity = _identity_from_mapping(identity_raw)
    if work_id != identity.work_id:
        raise CheckpointValidationError("checkpoint work_id does not bind its identity")
    attempt = document["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise CheckpointValidationError("attempt must be a positive integer")
    if identity.open_once and attempt != 1:
        raise CheckpointValidationError("open_once work may only have attempt 1")
    state = document["state"]
    if state not in _CHECKPOINT_STATES:
        raise CheckpointValidationError(f"unsupported checkpoint state: {state!r}")
    terminal_status = document["terminal_status"]
    if state == "TERMINAL":
        if terminal_status not in _TERMINAL_STATUSES:
            raise CheckpointValidationError("terminal checkpoint requires terminal_status")
        _require_string(document["error_code"], field="error_code")
    elif terminal_status is not None:
        raise CheckpointValidationError("non-terminal checkpoint cannot set terminal_status")
    if state in {"PENDING", "RUNNING"} and document["error_code"] is not None:
        raise CheckpointValidationError(f"{state} checkpoint cannot set error_code")
    if state == "INTERRUPTED":
        _require_string(document["interruption_reason"], field="interruption_reason")
    elif document["interruption_reason"] is not None:
        raise CheckpointValidationError("only INTERRUPTED checkpoints set interruption_reason")
    artifacts = _validate_hash_map(document["artifact_hashes"], field="artifact_hashes")
    dependencies = _validate_hash_map(
        document["dependency_checkpoint_hashes"], field="dependency_checkpoint_hashes"
    )
    previous = document["previous_checkpoint_sha256"]
    if previous is not None:
        _require_sha256(previous, field="previous_checkpoint_sha256")
    if not isinstance(document["volatile"], Mapping):
        raise CheckpointValidationError("volatile must be an object")

    if plan is not None:
        checked_plan = validate_execution_plan(plan)
        if document["execution_plan_sha256"] != execution_plan_sha256(checked_plan):
            raise CheckpointValidationError("checkpoint execution plan hash differs")
        stage = _stage_by_work_id(checked_plan, work_id)
        if stage["identity"] != identity.as_dict():
            raise CheckpointValidationError("checkpoint identity differs from execution plan")
        if set(dependencies) != set(stage["depends_on_work_ids"]):
            raise CheckpointValidationError("checkpoint dependency set differs from execution plan")
        if state == "TERMINAL" and not set(stage["required_artifacts"]).issubset(artifacts):
            raise CheckpointValidationError(
                "terminal checkpoint lacks one or more required artifact hashes"
            )
    elif state == "TERMINAL" and not artifacts:
        raise CheckpointValidationError("terminal checkpoint requires artifact hashes")
    return document


def make_stage_checkpoint(
    plan: Mapping[str, Any],
    work_id: str,
    *,
    state: str,
    attempt: int = 1,
    terminal_status: str | None = None,
    error_code: str | None = None,
    interruption_reason: str | None = None,
    artifact_hashes: Mapping[str, str] | None = None,
    dependency_checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
    previous_checkpoint: Mapping[str, Any] | None = None,
    volatile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one immutable stage-state record linked to its phase dependencies."""

    checked_plan = validate_execution_plan(plan)
    stage = _stage_by_work_id(checked_plan, work_id)
    supplied_dependencies = dict(dependency_checkpoints or {})
    expected_dependencies = set(stage["depends_on_work_ids"])
    if set(supplied_dependencies) != expected_dependencies:
        raise CheckpointValidationError("all and only declared dependency checkpoints are required")
    dependency_hashes: dict[str, str] = {}
    for dependency_id, dependency in supplied_dependencies.items():
        checked_dependency = validate_stage_checkpoint(dependency, plan=checked_plan)
        dependency_stage = _stage_by_work_id(checked_plan, dependency_id)
        if checked_dependency["work_id"] != dependency_id or not _terminal_and_complete(
            checked_dependency, dependency_stage
        ):
            raise CheckpointValidationError("dependency checkpoint is not terminal and complete")
        dependency_hashes[dependency_id] = checkpoint_sha256(checked_dependency)

    previous_hash: str | None = None
    if previous_checkpoint is not None:
        checked_previous = validate_stage_checkpoint(previous_checkpoint, plan=checked_plan)
        if checked_previous["work_id"] != work_id:
            raise CheckpointValidationError("previous checkpoint belongs to different work")
        previous_state = checked_previous["state"]
        previous_attempt = checked_previous["attempt"]
        if previous_state == "TERMINAL":
            raise CheckpointValidationError("terminal work cannot transition to another checkpoint")
        if stage["identity"]["open_once"] and previous_state in {"PARTIAL", "INTERRUPTED"}:
            raise CheckpointValidationError("open_once interrupted work cannot be restarted")
        if previous_state == "PENDING":
            allowed = state == "RUNNING" and attempt == previous_attempt
        elif previous_state == "RUNNING":
            allowed = state in {"PARTIAL", "INTERRUPTED", "TERMINAL"} and (
                attempt == previous_attempt
            )
        else:
            allowed = state == "RUNNING" and attempt == previous_attempt + 1
        if not allowed:
            raise CheckpointValidationError(
                f"invalid checkpoint transition {previous_state} -> {state} at attempt {attempt}"
            )
        previous_hash = checkpoint_sha256(checked_previous)

    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "execution_plan_sha256": execution_plan_sha256(checked_plan),
        "work_id": work_id,
        "identity": copy.deepcopy(stage["identity"]),
        "attempt": attempt,
        "state": state,
        "terminal_status": terminal_status,
        "error_code": error_code,
        "interruption_reason": interruption_reason,
        "artifact_hashes": dict(artifact_hashes or {}),
        "dependency_checkpoint_hashes": dependency_hashes,
        "previous_checkpoint_sha256": previous_hash,
        "volatile": copy.deepcopy(dict(volatile or {})),
    }
    return validate_stage_checkpoint(checkpoint, plan=checked_plan)


def open_once_claim_path(claim_directory: str | os.PathLike[str], work_id: str) -> Path:
    """Return the single authoritative claim path for one content-derived work ID."""

    checked_work_id = _require_sha256(work_id, field="work_id")
    return Path(claim_directory) / f"{checked_work_id}{OPEN_ONCE_CLAIM_SUFFIX}"


def _checkpoint_bytes(checkpoint: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            checkpoint,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_checkpoint_bytes(
    target: Path,
    payload: bytes,
    *,
    allow_identical_existing: bool,
    mode: int,
) -> bool:
    """Hard-link fully flushed bytes into place without following a target link."""

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = _read_regular_bytes(target, field="checkpoint target")
    except CheckpointValidationError as error:
        try:
            target.lstat()
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(
                f"checkpoint target is not a stable regular file: {target}"
            ) from error
    else:
        if allow_identical_existing and existing == payload:
            return False
        raise FileExistsError(f"checkpoint target is already consumed: {target}")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError as error:
            try:
                existing = _read_regular_bytes(target, field="checkpoint target")
            except CheckpointValidationError as inspection_error:
                raise FileExistsError(
                    f"checkpoint target was concurrently replaced by a non-regular file: {target}"
                ) from inspection_error
            if allow_identical_existing and existing == payload:
                return False
            raise FileExistsError(
                f"checkpoint target was concurrently consumed: {target}"
            ) from error
        _fsync_directory(target.parent)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _load_open_once_claim(
    plan: Mapping[str, Any],
    work_id: str,
    claim_directory: str | os.PathLike[str] | None,
) -> dict[str, Any] | None:
    if claim_directory is None:
        return None
    path = open_once_claim_path(claim_directory, work_id)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CheckpointValidationError(
            f"cannot inspect open_once claim {path}: {error}"
        ) from error
    if not stat.S_ISREG(metadata.st_mode):
        raise CheckpointValidationError(f"open_once claim is not a regular file: {path}")
    if metadata.st_mode & 0o222:
        raise CheckpointValidationError(f"open_once claim is not immutable: {path}")
    claim = load_checkpoint(path, plan=plan)
    if claim["work_id"] != work_id or claim["state"] != "RUNNING":
        raise CheckpointValidationError("open_once claim is not the RUNNING head for this work")
    if not claim["identity"]["open_once"] or claim["attempt"] != 1:
        raise CheckpointValidationError("open_once claim has an invalid identity or attempt")
    if claim["previous_checkpoint_sha256"] is None:
        raise CheckpointValidationError("open_once claim does not consume a PENDING authorization")
    return claim


def claim_open_once(
    plan: Mapping[str, Any],
    work_id: str,
    *,
    pending_checkpoint_path: str | os.PathLike[str],
    claim_directory: str | os.PathLike[str],
    volatile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Consume one persisted PENDING authorization before opening blind data.

    The returned RUNNING checkpoint is made visible through one immutable,
    per-work-ID hard link and both its bytes and directory entry are fsynced
    before this function returns.  Only the caller that creates the link may
    proceed to source access.  A byte-identical second call fails closed rather
    than replaying open-once work.
    """

    checked_plan = validate_execution_plan(plan)
    stage = _stage_by_work_id(checked_plan, work_id)
    identity = _identity_from_mapping(stage["identity"])
    if not identity.open_once:
        raise CheckpointValidationError("claim_open_once requires open_once work")

    pending = load_checkpoint(pending_checkpoint_path, plan=checked_plan)
    if pending["work_id"] != work_id or pending["state"] != "PENDING":
        raise CheckpointValidationError(
            "open_once claim requires this work's persisted PENDING authorization"
        )
    if pending["attempt"] != 1 or pending["previous_checkpoint_sha256"] is not None:
        raise CheckpointValidationError("open_once PENDING authorization must be initial attempt 1")

    running = copy.deepcopy(pending)
    running.update(
        {
            "state": "RUNNING",
            "previous_checkpoint_sha256": checkpoint_sha256(pending),
            "volatile": copy.deepcopy(dict(volatile or {})),
        }
    )
    checked_running = validate_stage_checkpoint(running, plan=checked_plan)
    claim_path = open_once_claim_path(claim_directory, work_id)
    _publish_checkpoint_bytes(
        claim_path,
        _checkpoint_bytes(checked_running),
        allow_identical_existing=False,
        mode=0o400,
    )
    return checked_running


def _artifacts_match(
    checkpoint: Mapping[str, Any],
    stage: Mapping[str, Any],
    artifact_paths: Mapping[str, str | os.PathLike[str]] | None,
) -> bool:
    if not _terminal_and_complete(checkpoint, stage) or artifact_paths is None:
        return False
    required = stage["required_artifacts"]
    if any(name not in artifact_paths for name in required):
        return False
    declared = checkpoint["artifact_hashes"]
    try:
        return all(hash_artifact(artifact_paths[name]) == declared[name] for name in required)
    except (CheckpointValidationError, OSError):
        return False


def assess_resume(
    plan: Mapping[str, Any],
    work_id: str,
    *,
    checkpoint: Mapping[str, Any] | None = None,
    artifact_paths: Mapping[str, str | os.PathLike[str]] | None = None,
    dependency_checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
    dependency_artifact_paths: Mapping[str, Mapping[str, str | os.PathLike[str]]] | None = None,
    open_once_claim_directory: str | os.PathLike[str] | None = None,
) -> ResumeAssessment:
    """Return the only safe automatic action for a stage after restart.

    A persisted ``RUNNING`` state is treated as interrupted; the function is a
    restart/resume assessor, not a live-worker liveness probe.
    """

    checked_plan = validate_execution_plan(plan)
    stage = _stage_by_work_id(checked_plan, work_id)
    identity = _identity_from_mapping(stage["identity"])
    fail_closed = identity.open_once or identity.split == "blind"
    dependencies = dict(dependency_checkpoints or {})
    dependency_paths = dict(dependency_artifact_paths or {})

    for dependency_id in stage["depends_on_work_ids"]:
        dependency = dependencies.get(dependency_id)
        if dependency is None:
            return ResumeAssessment(
                ResumeAction.BLOCKED, work_id, f"dependency {dependency_id} has no checkpoint"
            )
        try:
            checked_dependency = validate_stage_checkpoint(dependency, plan=checked_plan)
        except CheckpointValidationError as error:
            return ResumeAssessment(
                ResumeAction.FAIL_CLOSED,
                work_id,
                f"dependency {dependency_id} is invalid: {error}",
            )
        dependency_stage = _stage_by_work_id(checked_plan, dependency_id)
        if dependency_stage["identity"]["open_once"]:
            try:
                dependency_claim = _load_open_once_claim(
                    checked_plan,
                    dependency_id,
                    open_once_claim_directory,
                )
            except CheckpointValidationError as error:
                return ResumeAssessment(
                    ResumeAction.FAIL_CLOSED,
                    work_id,
                    f"dependency {dependency_id} open_once claim is invalid: {error}",
                )
            if dependency_claim is None or checked_dependency.get(
                "previous_checkpoint_sha256"
            ) != checkpoint_sha256(dependency_claim):
                return ResumeAssessment(
                    ResumeAction.FAIL_CLOSED,
                    work_id,
                    f"dependency {dependency_id} lacks its authoritative open_once claim chain",
                )
        if not _artifacts_match(
            checked_dependency, dependency_stage, dependency_paths.get(dependency_id)
        ):
            action = (
                ResumeAction.FAIL_CLOSED
                if dependency_stage["identity"]["open_once"]
                else ResumeAction.BLOCKED
            )
            return ResumeAssessment(
                action,
                work_id,
                f"dependency {dependency_id} lacks verifiable terminal artifacts",
            )

    claim: dict[str, Any] | None = None
    if fail_closed:
        try:
            claim = _load_open_once_claim(
                checked_plan,
                work_id,
                open_once_claim_directory,
            )
        except CheckpointValidationError as error:
            return ResumeAssessment(
                ResumeAction.FAIL_CLOSED,
                work_id,
                f"authoritative open_once claim is invalid: {error}",
            )

    if checkpoint is None:
        if fail_closed:
            if claim is not None:
                return ResumeAssessment(
                    ResumeAction.FAIL_CLOSED,
                    work_id,
                    "open_once authorization was already consumed",
                )
            return ResumeAssessment(
                ResumeAction.BLOCKED,
                work_id,
                "open_once work requires a durably persisted PENDING authorization",
            )
        return ResumeAssessment(ResumeAction.RUN, work_id, "no prior execution checkpoint")
    try:
        checked_checkpoint = validate_stage_checkpoint(checkpoint, plan=checked_plan)
    except CheckpointValidationError as error:
        return ResumeAssessment(
            ResumeAction.FAIL_CLOSED, work_id, f"checkpoint is invalid: {error}"
        )
    if checked_checkpoint["work_id"] != work_id:
        return ResumeAssessment(
            ResumeAction.FAIL_CLOSED, work_id, "checkpoint belongs to different work"
        )

    expected_dependency_hashes = {
        dependency_id: checkpoint_sha256(dependencies[dependency_id])
        for dependency_id in stage["depends_on_work_ids"]
    }
    if checked_checkpoint["dependency_checkpoint_hashes"] != expected_dependency_hashes:
        return ResumeAssessment(
            ResumeAction.FAIL_CLOSED, work_id, "checkpoint dependency chain differs"
        )

    state = checked_checkpoint["state"]
    if state == "TERMINAL":
        if fail_closed and (
            claim is None
            or checked_checkpoint["previous_checkpoint_sha256"] != checkpoint_sha256(claim)
        ):
            return ResumeAssessment(
                ResumeAction.FAIL_CLOSED,
                work_id,
                "terminal open_once checkpoint is not linked to its authoritative claim",
            )
        if _artifacts_match(checked_checkpoint, stage, artifact_paths):
            return ResumeAssessment(
                ResumeAction.SKIP, work_id, "terminal checkpoint and artifacts verified"
            )
        action = ResumeAction.FAIL_CLOSED if fail_closed else ResumeAction.RETRY
        return ResumeAssessment(action, work_id, "terminal artifacts missing or changed")
    if state == "PENDING":
        if fail_closed:
            if claim is not None:
                reason = (
                    "stale PENDING authorization: authoritative open_once claim already exists"
                    if claim["previous_checkpoint_sha256"] == checkpoint_sha256(checked_checkpoint)
                    else "PENDING authorization conflicts with the authoritative open_once claim"
                )
                return ResumeAssessment(ResumeAction.FAIL_CLOSED, work_id, reason)
            requirement = (
                "open_once work requires an authoritative claim directory"
                if open_once_claim_directory is None
                else "PENDING authorization verified; claim_open_once must durably publish "
                "RUNNING before source access"
            )
            return ResumeAssessment(ResumeAction.BLOCKED, work_id, requirement)
        return ResumeAssessment(ResumeAction.RUN, work_id, "work was recorded but never started")
    if fail_closed:
        if claim is None:
            return ResumeAssessment(
                ResumeAction.FAIL_CLOSED,
                work_id,
                f"{identity.split}/open_once work reached {state} without a durable claim",
            )
        if state == "RUNNING" and checkpoint_sha256(checked_checkpoint) != checkpoint_sha256(claim):
            return ResumeAssessment(
                ResumeAction.FAIL_CLOSED,
                work_id,
                "RUNNING checkpoint differs from the authoritative open_once claim",
            )
        return ResumeAssessment(
            ResumeAction.FAIL_CLOSED,
            work_id,
            f"{identity.split}/open_once work previously reached {state}",
        )
    return ResumeAssessment(
        ResumeAction.RETRY, work_id, f"ordinary work previously reached {state}"
    )


def write_checkpoint(path: str | os.PathLike[str], checkpoint: Mapping[str, Any]) -> None:
    """Publish an immutable checkpoint file atomically without overwriting.

    A temporary inode is fully flushed before an atomic hard-link publishes the
    final name.  Repeating the same write is idempotent; different bytes at an
    existing path are rejected.
    """

    document = validate_stage_checkpoint(checkpoint)
    _publish_checkpoint_bytes(
        Path(path),
        _checkpoint_bytes(document),
        allow_identical_existing=True,
        mode=0o600,
    )


def load_checkpoint(
    path: str | os.PathLike[str],
    *,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target = Path(path)
    try:
        value = json.loads(_read_regular_bytes(target, field="checkpoint").decode("utf-8"))
    except (CheckpointValidationError, OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckpointValidationError(f"cannot read checkpoint {target}: {error}") from error
    return validate_stage_checkpoint(value, plan=plan)


__all__ = [
    "CHECKPOINT_SCHEMA",
    "OPEN_ONCE_CLAIM_SUFFIX",
    "PLAN_SCHEMA",
    "SCHEMA_VERSION",
    "WORK_ID_ALGORITHM",
    "CheckpointValidationError",
    "ResumeAction",
    "ResumeAssessment",
    "WorkIdentity",
    "assess_resume",
    "checkpoint_sha256",
    "claim_open_once",
    "derive_work_id",
    "execution_plan_sha256",
    "hash_artifact",
    "hash_artifacts",
    "load_checkpoint",
    "make_execution_plan",
    "make_stage",
    "make_stage_checkpoint",
    "open_once_claim_path",
    "validate_execution_plan",
    "validate_stage_checkpoint",
    "write_checkpoint",
]
