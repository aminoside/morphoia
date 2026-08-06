#!/usr/bin/env python3
"""Materialise the private MVX P1a Objaverse census with restart guards.

The frozen P0 implementation deliberately has no dependency on a particular
Google Drive export shape.  This operational adapter binds the private Drive
snapshot and the historic CSV manifest to a content-derived ``work_id``, joins
the two inventories by unique Objaverse UID, and publishes a terminal bundle.

Only ``public-summary.json`` is safe to copy into Git.  Every other generated
artifact contains Drive IDs, source paths, Objaverse UIDs, or row-level
metadata and belongs in the private checkpoint store.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import morphoia.mvx.checkpoint as checkpoint_module
import morphoia.mvx.corpus.registry as corpus_registry_module
import morphoia.mvx.custody as custody_module
import morphoia.mvx.protocol as protocol_module
from morphoia.mvx.checkpoint import (
    ResumeAction,
    WorkIdentity,
    assess_resume,
    checkpoint_sha256,
    hash_artifact,
    load_checkpoint,
    make_execution_plan,
    make_stage,
    make_stage_checkpoint,
    write_checkpoint,
)
from morphoia.mvx.corpus import (
    FileRecord,
    build_object_candidates,
    detect_objaverse_duplicates,
    reconcile_inventories,
    render_jsonl,
)
from morphoia.mvx.custody import canonical_json_bytes
from morphoia.mvx.protocol import protocol_root, verify_protocol

SCRIPT_VERSION = "0.2.0"
SNAPSHOT_ID = "MORPHOIA-OBJAVERSE-2026-08-06-A"
PLAN_ALGORITHM = "MVX-P1A-OBJAVERSE-CENSUS-2"
NO_SPLIT_DOMAIN = {"state": "NO_SPLIT_BEFORE_G1", "version": "1"}
ARTIFACT_FILES = {
    "live_records": "private-live-records.jsonl",
    "reconciliation": "private-reconciliation.jsonl",
    "candidates": "private-candidates.jsonl",
    "duplicate_groups": "private-duplicate-groups.jsonl",
    "public_summary": "public-summary.json",
}
CHECKPOINT_NAME = re.compile(
    r"^(?P<sequence>[0-9]{4})-attempt-(?P<attempt>[0-9]{4})-"
    r"(?P<state>pending|running|partial|interrupted|terminal)\.json$"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class CensusError(RuntimeError):
    """Raised when a private census cannot be resumed without ambiguity."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_document(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _json_document(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_private_directory(directory: Path) -> None:
    """Create or validate a private, non-symlink directory."""

    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            metadata = directory.lstat()
        else:
            _fsync_directory(directory.parent)
            metadata = directory.lstat()
    except OSError as error:
        raise CensusError(f"cannot inspect private directory {directory}: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode) or directory.is_symlink():
        raise CensusError(f"private output component is not a real directory: {directory}")
    if metadata.st_uid != os.getuid():
        raise CensusError(f"private output directory is not owned by this worker: {directory}")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        os.chmod(directory, 0o700, follow_symlinks=False)


def _private_output_root(value: str) -> Path:
    """Resolve output lexically inside the repository's ignored private tree."""

    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    candidate = Path(os.path.abspath(candidate))
    private_root = Path(os.path.abspath(REPOSITORY_ROOT / "tmp"))
    if candidate != private_root and private_root not in candidate.parents:
        raise CensusError("output root must remain inside the repository's ignored tmp directory")

    _ensure_private_directory(private_root)
    current = private_root
    for part in candidate.relative_to(private_root).parts:
        current = current / part
        _ensure_private_directory(current)
    return candidate


@contextmanager
def _exclusive_work_lock(base_directory: Path, work_id: str) -> Iterable[None]:
    """Hold a process-scoped exclusive lock for one content-derived work ID."""

    lock_path = base_directory / f"{work_id}.active.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise CensusError(f"cannot open exclusive work lock: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise CensusError("exclusive work lock is not a worker-owned regular file")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise CensusError("the same work_id is already running in another process") from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _read_regular_bytes(path: Path, *, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise CensusError(f"cannot inspect {label}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise CensusError(f"{label} must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CensusError(f"cannot safely open {label}: {error}") from error
    with os.fdopen(descriptor, "rb") as stream:
        payload = stream.read()
        after = os.fstat(stream.fileno())
    if (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise CensusError(f"{label} changed while being read")
    return payload


def _publish_bytes_once(path: Path, payload: bytes, *, mode: int = 0o600) -> str:
    """Publish flushed bytes without overwriting a conflicting prior artifact."""

    _ensure_private_directory(path.parent)
    try:
        existing = _read_regular_bytes(path, label=f"existing artifact {path.name}")
    except CensusError:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise
    else:
        if existing == payload:
            return "ALREADY_PRESENT"
        raise CensusError(f"conflicting immutable artifact: {path}")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            existing = _read_regular_bytes(path, label=f"concurrent artifact {path.name}")
            if existing == payload:
                return "ALREADY_PRESENT"
            raise CensusError(f"concurrent artifact conflict: {path}") from error
        _fsync_directory(path.parent)
        return "WRITTEN"
    finally:
        temporary.unlink(missing_ok=True)


def _require_digest(actual: str, expected: str, *, label: str) -> None:
    if actual != expected:
        raise CensusError(f"{label} SHA-256 differs from its frozen commitment")


def _load_live_records(snapshot_payload: bytes) -> tuple[FileRecord, ...]:
    try:
        value = json.loads(snapshot_payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CensusError(f"live snapshot is not valid UTF-8 JSON: {error}") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"files"}
        or not isinstance(value["files"], list)
    ):
        raise CensusError("live snapshot must contain exactly one files array")

    records: list[FileRecord] = []
    required = {"id", "title", "size", "mime_type", "modified_time"}
    for index, row in enumerate(value["files"]):
        if not isinstance(row, dict) or not required.issubset(row):
            raise CensusError(f"live snapshot row {index} lacks required Drive metadata")
        mapped = dict(row)
        mapped["name"] = row["title"]
        mapped["dataset"] = "objaverse"
        records.append(FileRecord.from_mapping(mapped, origin="live-drive-snapshot"))
    return tuple(sorted(records, key=lambda record: record.sort_key))


def _objaverse_manifest_records(manifest_payload: bytes) -> tuple[FileRecord, ...]:
    try:
        text = manifest_payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CensusError(f"historic manifest is not valid UTF-8 CSV: {error}") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise CensusError("historic manifest has no CSV header")
    records: list[FileRecord] = []
    for row_number, row in enumerate(reader, 2):
        try:
            records.append(FileRecord.from_mapping(row, origin="historic-drive-manifest"))
        except (TypeError, ValueError) as error:
            raise CensusError(f"historic manifest row {row_number}: {error}") from error
    return tuple(
        record for record in records if (record.dataset or "").casefold().startswith("objaverse")
    )


def _unique_uid_index(records: Sequence[FileRecord]) -> tuple[dict[str, int], set[str]]:
    positions: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        if record.objaverse_uid:
            positions[record.objaverse_uid].append(index)
    unique = {uid: indexes[0] for uid, indexes in positions.items() if len(indexes) == 1}
    ambiguous = {uid for uid, indexes in positions.items() if len(indexes) > 1}
    return unique, ambiguous


def _changed_fields(manifest: FileRecord, live: FileRecord) -> tuple[str, ...]:
    changed: list[str] = []
    if manifest.normalised_path_key != live.normalised_path_key:
        changed.append("path")
    if (
        manifest.size_bytes is not None
        and live.size_bytes is not None
        and manifest.size_bytes != live.size_bytes
    ):
        changed.append("size_bytes")
    if (
        manifest.checksum
        and live.checksum
        and manifest.checksum_algorithm == live.checksum_algorithm
        and manifest.checksum != live.checksum
    ):
        changed.append("checksum")
    if manifest.mime_type and live.mime_type and manifest.mime_type != live.mime_type:
        changed.append("mime_type")
    if (
        manifest.modified_time
        and live.modified_time
        and manifest.modified_time != live.modified_time
    ):
        changed.append("modified_time")
    return tuple(changed)


def reconcile_by_uid_then_generic(
    manifest: Sequence[FileRecord], live: Sequence[FileRecord]
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Reconcile unique Objaverse UIDs first and preserve ambiguity explicitly."""

    manifest_index, manifest_ambiguous = _unique_uid_index(manifest)
    live_index, live_ambiguous = _unique_uid_index(live)
    ambiguous = manifest_ambiguous | live_ambiguous
    shared = sorted((set(manifest_index) & set(live_index)) - ambiguous)
    used_manifest = {manifest_index[uid] for uid in shared}
    used_live = {live_index[uid] for uid in shared}

    entries: list[dict[str, Any]] = []
    for uid in shared:
        old = manifest[manifest_index[uid]]
        current = live[live_index[uid]]
        changes = _changed_fields(old, current)
        entries.append(
            {
                "changed_fields": list(changes),
                "live": current.to_dict(),
                "manifest": old.to_dict(),
                "match_method": "objaverse_uid",
                "status": "CHANGED" if changes else "UNCHANGED",
            }
        )

    remaining_manifest = [row for index, row in enumerate(manifest) if index not in used_manifest]
    remaining_live = [row for index, row in enumerate(live) if index not in used_live]
    fallback = reconcile_inventories(remaining_manifest, remaining_live)
    entries.extend(entry.to_dict() for entry in fallback.entries)
    issues = tuple(
        sorted([*(f"ambiguous_objaverse_uid:{uid}" for uid in ambiguous), *fallback.issues])
    )
    ordered = tuple(
        row
        for _, row in sorted(
            ((_canonical_document(row), row) for row in entries), key=lambda item: item[0]
        )
    )
    return ordered, issues


def _closure_sha256(paths: Iterable[Path]) -> str:
    rows = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        rows.append(
            {
                "path": path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": hash_artifact(path),
            }
        )
    return _sha256_bytes(canonical_json_bytes(rows))


def _git_output(*arguments: str) -> str:
    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise CensusError(f"cannot bind execution to Git: {' '.join(arguments)}") from error
    return result.stdout.strip()


def _runtime_code_identity() -> tuple[str, str, str]:
    """Bind all Python runtime sources to a clean immutable Git commit/tree."""

    expected_package_root = (REPOSITORY_ROOT / "src/morphoia").resolve()
    for module in (
        checkpoint_module,
        corpus_registry_module,
        custody_module,
        protocol_module,
    ):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise CensusError("runtime module lacks a filesystem identity")
        resolved = Path(module_file).resolve()
        if resolved != expected_package_root and expected_package_root not in resolved.parents:
            raise CensusError("runtime module was imported outside the committed checkout")
    if Path(protocol_module.PROJECT_ROOT).resolve() != REPOSITORY_ROOT.resolve():
        raise CensusError("runtime protocol root differs from the runner checkout")

    script_path = Path(__file__).resolve()
    paths = (
        script_path,
        REPOSITORY_ROOT / "pyproject.toml",
        REPOSITORY_ROOT / "uv.lock",
        *sorted((REPOSITORY_ROOT / "src/morphoia").rglob("*.py")),
    )
    relative = [path.relative_to(REPOSITORY_ROOT).as_posix() for path in paths]
    _git_output("ls-files", "--error-unmatch", "--", *relative)
    dirty = subprocess.run(
        ("git", "diff", "--quiet", "HEAD", "--", *relative),
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    if dirty.returncode not in {0, 1}:
        raise CensusError("cannot verify the runtime source closure against Git HEAD")
    if dirty.returncode == 1:
        raise CensusError("runtime source closure must be committed before execution")
    commit_sha1 = _git_output("rev-parse", "HEAD")
    tree_sha1 = _git_output("rev-parse", "HEAD^{tree}")
    payload = {
        "git_commit_sha1": commit_sha1,
        "git_tree_sha1": tree_sha1,
        "source_closure_sha256": _closure_sha256(paths),
    }
    return _sha256_bytes(canonical_json_bytes(payload)), commit_sha1, tree_sha1


def _environment_sha256() -> str:
    payload = {
        "implementation": platform.python_implementation(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pyproject_sha256": hash_artifact(REPOSITORY_ROOT / "pyproject.toml"),
        "uv_lock_sha256": hash_artifact(REPOSITORY_ROOT / "uv.lock"),
    }
    return _sha256_bytes(canonical_json_bytes(payload))


def _make_plan(
    *,
    snapshot_sha256: str,
    manifest_sha256: str,
    source_sha256: str,
) -> tuple[dict[str, Any], str, str, str, str]:
    protocol_verification = verify_protocol(require_seal=True)
    if not protocol_verification.ok:
        raise CensusError("frozen P0 protocol or G0 seal no longer verifies")
    if protocol_verification.root_sha256 != protocol_root():
        raise CensusError("protocol verifier and protocol root disagree")

    code_sha256, commit_sha1, tree_sha1 = _runtime_code_identity()
    profile = {
        "algorithm": PLAN_ALGORITHM,
        "phase": "P1a",
        "scope": "OBJAVERSE_SOURCE_METADATA_ONLY",
        "snapshot_id": SNAPSHOT_ID,
    }
    config = {
        "manifest_sha256": manifest_sha256,
        "script_version": SCRIPT_VERSION,
        "snapshot_sha256": snapshot_sha256,
        "uid_join": "UNIQUE_BOTH_SIDES_THEN_GENERIC_RECONCILIATION",
    }
    identity = WorkIdentity(
        protocol_root_sha256=protocol_root(),
        split_sha256=_sha256_bytes(canonical_json_bytes(NO_SPLIT_DOMAIN)),
        source_sha256=source_sha256,
        lineage_id=SNAPSHOT_ID,
        profile_sha256=_sha256_bytes(canonical_json_bytes(profile)),
        config_sha256=_sha256_bytes(canonical_json_bytes(config)),
        code_sha256=code_sha256,
        environment_sha256=_environment_sha256(),
        phase_id="P1a",
        stage_id="OBJAVERSE_CENSUS_RECONCILIATION",
        split="none",
        open_once=False,
    )
    stage = make_stage(identity, required_artifacts=tuple(ARTIFACT_FILES))
    return (
        make_execution_plan(f"MVX-P1A-{source_sha256[:16]}", [stage]),
        identity.work_id,
        code_sha256,
        commit_sha1,
        tree_sha1,
    )


def _summary(
    *,
    work_id: str,
    code_git_commit_sha1: str,
    code_git_tree_sha1: str,
    source_sha256: str,
    snapshot_sha256: str,
    snapshot_bytes: int,
    manifest_sha256: str,
    manifest_bytes: int,
    live: Sequence[FileRecord],
    manifest: Sequence[FileRecord],
    reconciliation: Sequence[Mapping[str, Any]],
    issues: Sequence[str],
    private_commitments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    candidates = build_object_candidates(live)
    duplicates = detect_objaverse_duplicates(candidates.candidates)
    statuses = Counter(str(row["status"]) for row in reconciliation)
    methods = Counter(str(row["match_method"] or "none") for row in reconciliation)
    changed_fields = Counter(
        field for row in reconciliation for field in row.get("changed_fields", [])
    )
    matched_manifest = [
        row["manifest"]
        for row in reconciliation
        if row.get("match_method") == "objaverse_uid" and row.get("manifest")
    ]
    # Metadata keys remain private; only their completeness counts are public.
    provenance_complete = sum(
        isinstance(row.get("metadata"), dict)
        and all(
            str(row["metadata"].get(key, "")).strip()
            for key in ("source_url", "license", "citation")
        )
        for row in matched_manifest
    )
    historic_labels = {
        str(row["metadata"].get("label", "")).strip()
        for row in matched_manifest
        if isinstance(row.get("metadata"), dict) and str(row["metadata"].get("label", "")).strip()
    }
    uid_rows = [record.objaverse_uid for record in live if record.objaverse_uid]
    return {
        "schema": "MVX-P1A-CENSUS-SUMMARY",
        "schema_version": "0.1.0",
        "algorithm": PLAN_ALGORITHM,
        "script_version": SCRIPT_VERSION,
        "snapshot_id": SNAPSHOT_ID,
        "work_id": work_id,
        "code_git_commit_sha1": code_git_commit_sha1,
        "code_git_tree_sha1": code_git_tree_sha1,
        "protocol_root_sha256": protocol_root(),
        "source_commitment_sha256": source_sha256,
        "inputs": {
            "live_snapshot": {"bytes": snapshot_bytes, "sha256": snapshot_sha256},
            "historic_manifest": {"bytes": manifest_bytes, "sha256": manifest_sha256},
        },
        "live": {
            "file_rows": len(live),
            "glb_rows": len(candidates.direct_candidates),
            "excluded_test_rows": len(candidates.excluded_files),
            "ignored_rows": len(candidates.ignored_files),
            "uid_rows": len(uid_rows),
            "unique_uids": len(set(uid_rows)),
            "direct_candidates": len(candidates.direct_candidates),
            "ready_for_lineage": sum(item.ready_for_lineage for item in candidates.candidates),
        },
        "historic_manifest_objaverse_rows": len(manifest),
        "reconciliation": {
            "statuses": dict(sorted(statuses.items())),
            "match_methods": dict(sorted(methods.items())),
            "changed_fields": dict(sorted(changed_fields.items())),
            "issue_count": len(issues),
        },
        "duplicate_groups": dict(sorted(Counter(group.field for group in duplicates).items())),
        "provenance": {
            "uid_matched_rows_with_generic_source_licence_and_citation": provenance_complete,
            "uid_matched_historic_label_count": len(historic_labels),
            "per_uid_author_provenance_available": False,
        },
        "category_reproducibility": {
            "reproducible_from_committed_raw_snapshot": False,
            "historic_uid_matched_labels_reproducible": len(historic_labels),
            "gate_effect": "CATEGORY_ASSIGNMENT_REMAINS_PENDING_UNTIL_ENRICHED_LOCAL_METADATA",
        },
        "privacy": {
            "drive_ids_published": False,
            "objaverse_uids_published": False,
            "source_paths_published": False,
            "row_level_metadata_published": False,
        },
        "private_artifact_commitments": dict(sorted(private_commitments.items())),
        "mvx_outcome_accessed": False,
        "cohort_selected": False,
        "split_created": False,
        "gate_effect": "P1A_METADATA_CHECKPOINT_ONLY_G1_REMAINS_BLOCKED",
    }


def _private_payloads(
    live: Sequence[FileRecord],
    reconciliation: Sequence[Mapping[str, Any]],
    issues: Sequence[str],
) -> dict[str, bytes]:
    candidates = build_object_candidates(live)
    duplicates = detect_objaverse_duplicates(candidates.candidates)
    reconciliation_rows = [*reconciliation, {"private_issues": list(issues)}]
    return {
        "live_records": render_jsonl(live).encode("utf-8"),
        "reconciliation": render_jsonl(reconciliation_rows).encode("utf-8"),
        "candidates": render_jsonl(candidates.candidates).encode("utf-8"),
        "duplicate_groups": render_jsonl(duplicates).encode("utf-8"),
    }


def _validate_artifact_directory(artifact_directory: Path) -> bool:
    try:
        metadata = artifact_directory.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or artifact_directory.is_symlink():
        raise CensusError("artifact bundle is not a real directory")
    actual = {entry.name for entry in artifact_directory.iterdir()}
    expected = set(ARTIFACT_FILES.values())
    if actual != expected:
        raise CensusError(
            f"artifact bundle is partial or contains extras: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    for entry in artifact_directory.iterdir():
        item = entry.lstat()
        if not stat.S_ISREG(item.st_mode) or entry.is_symlink():
            raise CensusError(f"artifact bundle entry is not a regular file: {entry.name}")
    return True


def _validate_run_layout(run_directory: Path) -> None:
    """Reject every hidden, orphaned, symlinked, or unexpected run entry."""

    _ensure_private_directory(run_directory)
    allowed = {"execution-plan.json", "checkpoints", "artifacts"}
    entries = {entry.name: entry for entry in run_directory.iterdir()}
    unexpected = sorted(set(entries) - allowed)
    if unexpected:
        raise CensusError(f"run directory contains interrupted or unknown entries: {unexpected}")
    plan = entries.get("execution-plan.json")
    if plan is not None:
        metadata = plan.lstat()
        if not stat.S_ISREG(metadata.st_mode) or plan.is_symlink():
            raise CensusError("execution plan entry is not a regular file")
    checkpoints = entries.get("checkpoints")
    if checkpoints is not None:
        metadata = checkpoints.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or checkpoints.is_symlink():
            raise CensusError("checkpoint entry is not a real directory")
    artifacts = entries.get("artifacts")
    if artifacts is not None:
        _validate_artifact_directory(artifacts)


def _checkpoint_paths(checkpoint_directory: Path) -> list[Path]:
    try:
        metadata = checkpoint_directory.lstat()
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(metadata.st_mode) or checkpoint_directory.is_symlink():
        raise CensusError("checkpoint path is not a real directory")
    paths = sorted(checkpoint_directory.iterdir(), key=lambda path: path.name)
    for sequence, path in enumerate(paths, 1):
        match = CHECKPOINT_NAME.fullmatch(path.name)
        metadata = path.lstat()
        if (
            match is None
            or int(match.group("sequence")) != sequence
            or not stat.S_ISREG(metadata.st_mode)
            or path.is_symlink()
        ):
            raise CensusError("checkpoint directory contains a hidden, orphaned, or invalid entry")
    return paths


def _load_checkpoint_chain(
    checkpoint_directory: Path, plan: Mapping[str, Any], work_id: str
) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    for path in _checkpoint_paths(checkpoint_directory):
        match = CHECKPOINT_NAME.fullmatch(path.name)
        assert match is not None
        checkpoint = load_checkpoint(path, plan=plan)
        if checkpoint["work_id"] != work_id:
            raise CensusError("checkpoint directory mixes distinct work IDs")
        expected_previous = checkpoint_sha256(chain[-1]) if chain else None
        if checkpoint["previous_checkpoint_sha256"] != expected_previous:
            raise CensusError("checkpoint chain is missing, reordered, or forked")
        if checkpoint["attempt"] != int(match.group("attempt")) or checkpoint[
            "state"
        ].casefold() != match.group("state"):
            raise CensusError("checkpoint filename does not bind its state and attempt")
        chain.append(checkpoint)
    return chain


def _write_numbered_checkpoint(
    checkpoint_directory: Path,
    sequence: int,
    checkpoint: Mapping[str, Any],
) -> None:
    name = (
        f"{sequence:04d}-attempt-{checkpoint['attempt']:04d}-"
        f"{str(checkpoint['state']).casefold()}.json"
    )
    write_checkpoint(checkpoint_directory / name, checkpoint)


def _ensure_running(
    *,
    plan: Mapping[str, Any],
    work_id: str,
    checkpoint_directory: Path,
    chain: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    sequence = len(chain) + 1
    if not chain:
        pending = make_stage_checkpoint(plan, work_id, state="PENDING")
        _write_numbered_checkpoint(checkpoint_directory, sequence, pending)
        chain.append(pending)
        sequence += 1

    previous = chain[-1]
    if previous["state"] == "TERMINAL":
        return previous, sequence
    if previous["state"] == "RUNNING":
        partial = make_stage_checkpoint(
            plan,
            work_id,
            state="PARTIAL",
            attempt=previous["attempt"],
            error_code="RESTART_DETECTED",
            previous_checkpoint=previous,
        )
        _write_numbered_checkpoint(checkpoint_directory, sequence, partial)
        chain.append(partial)
        previous = partial
        sequence += 1

    if previous["state"] == "PENDING":
        attempt = previous["attempt"]
    elif previous["state"] in {"PARTIAL", "INTERRUPTED"}:
        attempt = previous["attempt"] + 1
    else:
        raise CensusError(f"cannot resume checkpoint state {previous['state']}")
    running = make_stage_checkpoint(
        plan,
        work_id,
        state="RUNNING",
        attempt=attempt,
        previous_checkpoint=previous,
    )
    _write_numbered_checkpoint(checkpoint_directory, sequence, running)
    return running, sequence + 1


def _artifact_paths(artifact_directory: Path) -> dict[str, Path]:
    return {name: artifact_directory / filename for name, filename in ARTIFACT_FILES.items()}


def _publish_artifact_bundle(
    *,
    run_directory: Path,
    artifact_directory: Path,
    payloads: Mapping[str, bytes],
    attempt: int,
) -> None:
    """Publish the complete artifact directory by one rename, never file-by-file."""

    if _validate_artifact_directory(artifact_directory):
        for name, path in _artifact_paths(artifact_directory).items():
            if _read_regular_bytes(path, label=f"existing {name}") != payloads[name]:
                raise CensusError("existing complete artifact bundle conflicts with recomputation")
        return

    staging = run_directory / f"attempt-{attempt:04d}-artifacts.staging"
    try:
        os.mkdir(staging, 0o700)
        _fsync_directory(run_directory)
    except FileExistsError as error:
        raise CensusError(
            "an interrupted artifact staging directory requires quarantine"
        ) from error
    for name, path in _artifact_paths(staging).items():
        _publish_bytes_once(path, payloads[name])
    _validate_artifact_directory(staging)
    try:
        os.rename(staging, artifact_directory)
    except OSError as error:
        raise CensusError("cannot atomically publish the complete artifact bundle") from error
    _fsync_directory(run_directory)


def _terminal_resume_action(
    plan: Mapping[str, Any],
    work_id: str,
    terminal: Mapping[str, Any],
    artifact_directory: Path,
) -> ResumeAction:
    assessment = assess_resume(
        plan,
        work_id,
        checkpoint=terminal,
        artifact_paths=_artifact_paths(artifact_directory),
    )
    if assessment.action is not ResumeAction.SKIP:
        raise CensusError(f"terminal checkpoint is not safely resumable: {assessment.reason}")
    return assessment.action


def _execute_locked(
    *,
    snapshot_payload: bytes,
    manifest_payload: bytes,
    snapshot_sha256: str,
    manifest_sha256: str,
    source_sha256: str,
    plan: Mapping[str, Any],
    work_id: str,
    code_identity: tuple[str, str, str],
    base_directory: Path,
) -> dict[str, Any]:
    run_directory = base_directory / work_id
    plan_path = run_directory / "execution-plan.json"
    checkpoint_directory = run_directory / "checkpoints"
    artifact_directory = run_directory / "artifacts"
    _validate_run_layout(run_directory)
    _publish_bytes_once(plan_path, _json_document(plan))
    _ensure_private_directory(checkpoint_directory)
    chain = _load_checkpoint_chain(checkpoint_directory, plan, work_id)
    if chain and chain[-1]["state"] == "TERMINAL":
        action = _terminal_resume_action(plan, work_id, chain[-1], artifact_directory)
        summary = json.loads(
            _read_regular_bytes(
                artifact_directory / ARTIFACT_FILES["public_summary"],
                label="public summary",
            )
        )
        return {
            "action": action.value,
            "artifact_bundle": f"PRIVATE_CHECKPOINT_STORE/{work_id}/artifacts",
            "checkpoint_sha256": checkpoint_sha256(chain[-1]),
            "summary": summary,
            "work_id": work_id,
        }

    running, next_sequence = _ensure_running(
        plan=plan,
        work_id=work_id,
        checkpoint_directory=checkpoint_directory,
        chain=chain,
    )
    # Derivations consume the exact byte strings bound into source_sha256.
    # Neither input path is reopened after its secure committed read.
    live = _load_live_records(snapshot_payload)
    manifest = _objaverse_manifest_records(manifest_payload)
    reconciliation, issues = reconcile_by_uid_then_generic(manifest, live)
    payloads = _private_payloads(live, reconciliation, issues)
    private_commitments = {
        ARTIFACT_FILES[name]: {"bytes": len(payload), "sha256": _sha256_bytes(payload)}
        for name, payload in payloads.items()
    }
    _, commit_sha1, tree_sha1 = code_identity
    summary = _summary(
        work_id=work_id,
        code_git_commit_sha1=commit_sha1,
        code_git_tree_sha1=tree_sha1,
        source_sha256=source_sha256,
        snapshot_sha256=snapshot_sha256,
        snapshot_bytes=len(snapshot_payload),
        manifest_sha256=manifest_sha256,
        manifest_bytes=len(manifest_payload),
        live=live,
        manifest=manifest,
        reconciliation=reconciliation,
        issues=issues,
        private_commitments=private_commitments,
    )
    payloads["public_summary"] = _json_document(summary)

    _publish_artifact_bundle(
        run_directory=run_directory,
        artifact_directory=artifact_directory,
        payloads=payloads,
        attempt=running["attempt"],
    )
    if _runtime_code_identity() != code_identity:
        raise CensusError("runtime code or Git identity changed before terminal publication")
    artifact_hashes = {
        name: hash_artifact(path) for name, path in _artifact_paths(artifact_directory).items()
    }
    terminal = make_stage_checkpoint(
        plan,
        work_id,
        state="TERMINAL",
        attempt=running["attempt"],
        terminal_status="PASS",
        error_code="P1A_METADATA_ONLY_PASS_G1_BLOCKED",
        artifact_hashes=artifact_hashes,
        previous_checkpoint=running,
    )
    _write_numbered_checkpoint(checkpoint_directory, next_sequence, terminal)
    action = _terminal_resume_action(plan, work_id, terminal, artifact_directory)
    return {
        "action": "COMPLETED",
        "resume_verification": action.value,
        "artifact_bundle": f"PRIVATE_CHECKPOINT_STORE/{work_id}/artifacts",
        "checkpoint_sha256": checkpoint_sha256(terminal),
        "summary": summary,
        "work_id": work_id,
    }


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    snapshot_path = Path(os.path.abspath(arguments.live_snapshot))
    manifest_path = Path(os.path.abspath(arguments.manifest))
    snapshot_payload = _read_regular_bytes(snapshot_path, label="live snapshot")
    manifest_payload = _read_regular_bytes(manifest_path, label="historic manifest")
    snapshot_sha256 = _sha256_bytes(snapshot_payload)
    manifest_sha256 = _sha256_bytes(manifest_payload)
    _require_digest(snapshot_sha256, arguments.snapshot_sha256, label="live snapshot")
    _require_digest(manifest_sha256, arguments.manifest_sha256, label="historic manifest")
    source_sha256 = _sha256_bytes(
        canonical_json_bytes(
            {
                "algorithm": PLAN_ALGORITHM,
                "historic_manifest_sha256": manifest_sha256,
                "live_snapshot_sha256": snapshot_sha256,
            }
        )
    )
    plan, work_id, code_sha256, commit_sha1, tree_sha1 = _make_plan(
        snapshot_sha256=snapshot_sha256,
        manifest_sha256=manifest_sha256,
        source_sha256=source_sha256,
    )
    code_identity = (code_sha256, commit_sha1, tree_sha1)
    base_directory = _private_output_root(arguments.output_root)
    with _exclusive_work_lock(base_directory, work_id):
        return _execute_locked(
            snapshot_payload=snapshot_payload,
            manifest_payload=manifest_payload,
            snapshot_sha256=snapshot_sha256,
            manifest_sha256=manifest_sha256,
            source_sha256=source_sha256,
            plan=plan,
            work_id=work_id,
            code_identity=code_identity,
            base_directory=base_directory,
        )


def self_test() -> None:
    uid_a = "a" * 32
    uid_b = "b" * 32
    manifest = (
        FileRecord(
            f"old/{uid_a}.glb",
            dataset="objaverse",
            objaverse_uid=uid_a,
            size_bytes=4,
        ),
    )
    live = (
        FileRecord(
            f"{uid_a}.glb",
            origin="live",
            dataset="objaverse",
            objaverse_uid=uid_a,
            size_bytes=4,
        ),
        FileRecord(
            f"{uid_b}.glb",
            origin="live",
            file_id="first",
            dataset="objaverse",
            objaverse_uid=uid_b,
        ),
        FileRecord(
            f"{uid_b}.glb",
            origin="live",
            file_id="second",
            dataset="objaverse",
            objaverse_uid=uid_b,
        ),
    )
    rows, issues = reconcile_by_uid_then_generic(manifest, live)
    methods = Counter(str(row["match_method"] or "none") for row in rows)
    statuses = Counter(str(row["status"]) for row in rows)
    assert methods["objaverse_uid"] == 1
    assert statuses["NEW_IN_LIVE"] == 2
    assert len([issue for issue in issues if issue.startswith("ambiguous_objaverse_uid:")]) == 1
    assert build_object_candidates(live).file_row_count == 3
    print("self-test: PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--live-snapshot")
    parser.add_argument("--manifest")
    parser.add_argument("--snapshot-sha256")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--output-root", default="tmp/runs/p1a")
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test()
        return 0
    required = ("live_snapshot", "manifest", "snapshot_sha256", "manifest_sha256")
    missing = [name for name in required if not getattr(arguments, name)]
    if missing:
        parser.error(f"missing required arguments: {', '.join(missing)}")
    try:
        result = run(arguments)
    except (CensusError, OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "error_code": (
                        "P1A_CENSUS_GUARD_REJECTED"
                        if isinstance(error, CensusError)
                        else "P1A_CENSUS_UNEXPECTED_ERROR"
                    ),
                    "diagnostic_sha256": _sha256_bytes(str(error).encode("utf-8")),
                    "message": "Private diagnostic details withheld from standard output.",
                },
                indent=2,
            )
        )
        return 1
    summary = result.pop("summary")
    print(
        json.dumps(
            {
                **result,
                "status": "PASS",
                "public_counts": {
                    "live": summary["live"],
                    "reconciliation": summary["reconciliation"],
                    "duplicate_groups": summary["duplicate_groups"],
                    "gate_effect": summary["gate_effect"],
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
