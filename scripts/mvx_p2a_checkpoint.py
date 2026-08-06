#!/usr/bin/env python3
"""Restart-safe, source-only GLB diagnostic for MVX P2a.

This runner deliberately lives outside ``src/morphoia`` because the complete
package source closure is part of the frozen P0 root.  It performs no MVX
encoding, decoding, reconstruction, selection, split assignment, repair, URI
resolution, or network access.

The public output contains aggregate commitments only.  Pilot membership,
Drive identifiers, Objaverse UIDs, source hashes, paths, and per-object values
remain in the ignored private checkpoint tree.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import platform
import re
import resource
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = (REPOSITORY_ROOT / "src").resolve()
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import morphoia.mvx.checkpoint as checkpoint_module
import morphoia.mvx.hmac_rank as hmac_rank_module
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
from morphoia.mvx.custody import canonical_json_bytes
from morphoia.mvx.hmac_rank import hmac_sha256_rank
from morphoia.mvx.protocol import protocol_root, verify_protocol

SCRIPT_VERSION = "0.2.0"
PILOT_SCHEMA = "MVX-P2A-DIAGNOSTIC-PILOT"
PILOT_SCHEMA_VERSION = "0.2.0"
PILOT_ALGORITHM = "MVX-P2A-DIAGNOSTIC-PREFIX-HMAC-2"
PILOT_ALGORITHM_VERSION = "2.0.0"
PILOT_DOMAIN = "p2a-diagnostic-prefix"
DEFAULT_SCOPE_COUNT = 12
AUDIT_SCHEMA = "MVX-P2A-GLB-SOURCE-AUDIT"
AUDIT_ALGORITHM = "MVX-P2A-GLB-STDLIB-AUDIT-1"
AUDIT_ALGORITHM_VERSION = "1.0.0"
NO_SPLIT_DOMAIN = {"state": "PRE_G1_NO_SPLIT", "version": "1"}
BOOTSTRAP_SEED_HEX = "713b129c8347d84b37685cca9ef0734e6599ca90691b852eacb561f4bef148f0"
P0_ROOT = "a600436d8a51ee3c26a6070ead19829cc3568a257493a5c639c35e5a35b8a9e7"
UID_PATTERN = re.compile(r"(?<![0-9a-f])([0-9a-f]{32,64})(?![0-9a-f])", re.IGNORECASE)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHECKPOINT_NAME = re.compile(
    r"^(?P<sequence>[0-9]{4})-attempt-(?P<attempt>[0-9]{4})-"
    r"(?P<state>pending|running|partial|interrupted|terminal)\.json$"
)
OBJECT_ARTIFACT_FILES = {
    "source_receipt": "source-receipt.json",
    "audit_record": "audit-record.json",
    "parser_evidence": "parser-evidence.json",
    "resource_evidence": "resource-evidence.json",
}
OBJECT_BUNDLE_META = frozenset(("bundle-manifest.json", "READY.json"))
OBJECT_BUNDLE_FILES = frozenset((*OBJECT_ARTIFACT_FILES.values(), *OBJECT_BUNDLE_META))
CAMPAIGN_FILES = frozenset(("private-manifest.json", "public-summary.json", "COMPLETED.json"))
VALIDATOR_ROOT = REPOSITORY_ROOT / "scripts/p2a-runtime"
VALIDATOR_WRAPPER = VALIDATOR_ROOT / "validate-glb.js"
VALIDATOR_PACKAGE_JSON = VALIDATOR_ROOT / "package.json"
VALIDATOR_PACKAGE_LOCK = VALIDATOR_ROOT / "package-lock.json"
VALIDATOR_INSTALL_ROOT = VALIDATOR_ROOT / "node_modules/gltf-validator"
VALIDATOR_VERSION = "2.0.0-dev.3.10"

GLB_MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_ACCESSOR_COUNT = 50_000_000
MAX_TRIANGLES = 20_000_000
MAX_SCENE_NODES = 500_000
MAX_VERTEX_INSTANCES = 60_000_000
CHILD_TIMEOUT_SECONDS = 300
CHILD_ADDRESS_SPACE_BYTES = 2 * 1024 * 1024 * 1024
CHILD_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_CHILD_NO_STATUS_ATTEMPTS = 2

SUPPORTED_REQUIRED_EXTENSIONS = frozenset(("KHR_mesh_quantization",))
DECLARED_LIMIT_EXTENSIONS = frozenset(
    (
        "EXT_mesh_gpu_instancing",
        "EXT_meshopt_compression",
        "KHR_draco_mesh_compression",
        "KHR_materials_variants",
    )
)


class P2aError(RuntimeError):
    """Raised when execution cannot continue without ambiguity."""

    error_code = "MVX-X001"


class ChildNoStatus(P2aError):
    """Raised by the supervisor when the isolated worker emitted no valid status."""

    error_code = "MVX-X002"


class GlbInvalid(ValueError):
    """Raised when GLB bytes violate a structural or geometry invariant."""

    def __init__(self, message: str, *, error_code: str = "MVX-I002") -> None:
        super().__init__(message)
        self.error_code = error_code


class GlbDeclaredLimit(ValueError):
    """Raised when a valid source needs an unsupported, explicitly bounded feature."""

    def __init__(self, message: str, *, error_code: str = "MVX-G003") -> None:
        super().__init__(message)
        self.error_code = error_code


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_hash(value: Any) -> str:
    return _sha256_bytes(canonical_json_bytes(value))


def _json_document(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_private_directory(directory: Path) -> None:
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
        raise P2aError(f"cannot inspect private directory: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode) or directory.is_symlink():
        raise P2aError("private output component is not a real directory")
    if metadata.st_uid != os.getuid():
        raise P2aError("private output directory is not owned by this worker")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        os.chmod(directory, 0o700, follow_symlinks=False)


def _private_path(value: str, *, create_directory: bool = False) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    candidate = Path(os.path.abspath(candidate))
    private_root = Path(os.path.abspath(REPOSITORY_ROOT / "tmp"))
    if candidate != private_root and private_root not in candidate.parents:
        raise P2aError("private paths must remain inside the repository's ignored tmp directory")
    _ensure_private_directory(private_root)
    directory = candidate if create_directory else candidate.parent
    current = private_root
    for part in directory.relative_to(private_root).parts:
        current = current / part
        _ensure_private_directory(current)
    return candidate


def _read_regular_bytes(path: Path, *, label: str, maximum: int | None = None) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise P2aError(f"cannot inspect {label}: {error}") from error
    if not stat.S_ISREG(before.st_mode) or path.is_symlink():
        raise P2aError(f"{label} must be a regular non-symlink file")
    if maximum is not None and before.st_size > maximum:
        raise P2aError(f"{label} exceeds its declared byte limit")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise P2aError(f"cannot safely open {label}: {error}") from error
    with os.fdopen(descriptor, "rb") as stream:
        payload = stream.read()
        after = os.fstat(stream.fileno())
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise P2aError(f"{label} changed while being read")
    return payload


def _publish_bytes_once(path: Path, payload: bytes, *, mode: int = 0o600) -> str:
    _ensure_private_directory(path.parent)
    try:
        existing = _read_regular_bytes(path, label="existing immutable artifact")
    except P2aError:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise
    else:
        if existing == payload:
            return "ALREADY_PRESENT"
        raise P2aError("conflicting immutable artifact")

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
            existing = _read_regular_bytes(path, label="concurrent immutable artifact")
            if existing == payload:
                return "ALREADY_PRESENT"
            raise P2aError("concurrent immutable artifact conflict") from error
        _fsync_directory(path.parent)
        return "WRITTEN"
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive_lock(lock_directory: Path, work_id: str) -> Iterable[None]:
    _ensure_private_directory(lock_directory)
    lock_path = lock_directory / f"{work_id}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise P2aError("work lock is not a worker-owned regular file")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise P2aError("the same work_id is already active") from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _verified_protocol_root() -> str:
    verification = verify_protocol(require_seal=True)
    if not verification.ok or verification.root_sha256 != protocol_root():
        raise P2aError("frozen P0 protocol or G0 seal no longer verifies")
    if verification.root_sha256 != P0_ROOT:
        raise P2aError("runner is bound to a different frozen P0 root")
    split_spec = _read_regular_bytes(
        REPOSITORY_ROOT / "docs/mvx/validation/p0/split-spec.yaml",
        label="frozen split specification",
    ).decode("utf-8")
    if f"bootstrap_seed_hex: {BOOTSTRAP_SEED_HEX}" not in split_spec:
        raise P2aError("public bootstrap seed differs from the frozen protocol")
    return verification.root_sha256


def _load_json_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise P2aError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise P2aError(f"{label} must be a JSON object")
    return value


def _extract_uid(title: str) -> str | None:
    matches = {match.casefold() for match in UID_PATTERN.findall(title)}
    return next(iter(matches)) if len(matches) == 1 else None


def _pilot_rank(uid: str, file_id: str) -> str:
    rank = hmac_sha256_rank(
        bytes.fromhex(BOOTSTRAP_SEED_HEX),
        algorithm_id=PILOT_ALGORITHM,
        algorithm_version=PILOT_ALGORITHM_VERSION,
        domain=PILOT_DOMAIN,
        parts=(uid, file_id),
    )
    return rank.hex()


def _validate_pilot_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(value)
    expected = {
        "schema",
        "schema_version",
        "algorithm_id",
        "algorithm_version",
        "protocol_root_sha256",
        "p1a_snapshot_sha256",
        "selection_domain",
        "selection_seed_sha256",
        "pilot_kind",
        "candidate_count",
        "candidates",
        "constraints",
    }
    if set(document) != expected:
        raise P2aError("pilot plan fields differ from the closed contract")
    if document["schema"] != PILOT_SCHEMA or document["schema_version"] != PILOT_SCHEMA_VERSION:
        raise P2aError("pilot plan schema identity is invalid")
    if document["algorithm_id"] != PILOT_ALGORITHM:
        raise P2aError("pilot plan algorithm is invalid")
    if document["algorithm_version"] != PILOT_ALGORITHM_VERSION:
        raise P2aError("pilot plan algorithm version is invalid")
    if document["protocol_root_sha256"] != P0_ROOT:
        raise P2aError("pilot plan protocol root is invalid")
    if document["selection_domain"] != PILOT_DOMAIN:
        raise P2aError("pilot selection domain is invalid")
    if document["selection_seed_sha256"] != _sha256_bytes(bytes.fromhex(BOOTSTRAP_SEED_HEX)):
        raise P2aError("pilot plan seed commitment is invalid")
    if document["pilot_kind"] != "ENGINEERING_P2A_SOURCE_ONLY_NONSTATISTICAL":
        raise P2aError("pilot kind is invalid")
    candidates = document["candidates"]
    candidate_count = document["candidate_count"]
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count < 1
        or not isinstance(candidates, list)
    ):
        raise P2aError("pilot candidate count is invalid")
    if len(candidates) != candidate_count:
        raise P2aError("pilot candidate array length is invalid")
    seen_uids: set[str] = set()
    seen_ids: set[str] = set()
    for index, row in enumerate(candidates):
        if not isinstance(row, dict) or set(row) != {
            "ordinal",
            "drive_file_id",
            "source_uid",
            "source_title",
            "source_size_bytes",
            "source_mime_type",
            "source_modified_time",
            "cache_name",
            "hmac_rank_hex",
        }:
            raise P2aError("pilot candidate fields are invalid")
        if row["ordinal"] != index:
            raise P2aError("pilot candidate ordinals are not contiguous")
        uid = row["source_uid"]
        file_id = row["drive_file_id"]
        if not isinstance(uid, str) or not UID_PATTERN.fullmatch(uid):
            raise P2aError("pilot candidate UID is invalid")
        if not isinstance(file_id, str) or not file_id:
            raise P2aError("pilot candidate Drive ID is invalid")
        if uid in seen_uids or file_id in seen_ids:
            raise P2aError("pilot candidates are not independent unique files")
        seen_uids.add(uid)
        seen_ids.add(file_id)
        if row["hmac_rank_hex"] != _pilot_rank(uid, file_id):
            raise P2aError("pilot candidate rank is invalid")
        if row["cache_name"] != f"source-{index:04d}.glb":
            raise P2aError("pilot cache name is invalid")
        if (
            isinstance(row["source_size_bytes"], bool)
            or not isinstance(row["source_size_bytes"], int)
            or row["source_size_bytes"] <= 0
        ):
            raise P2aError("pilot source size is invalid")
    if candidates != sorted(candidates, key=lambda row: row["hmac_rank_hex"]):
        raise P2aError("pilot candidates are not in HMAC rank order")
    constraints = document["constraints"]
    if constraints != {
        "cohort_selected": False,
        "complexity_quantile_frozen": False,
        "eligibility": "PENDING",
        "mvx_outcome_accessed": False,
        "split": None,
    }:
        raise P2aError("pilot constraints are invalid")
    return document


def make_pilot(arguments: argparse.Namespace) -> dict[str, Any]:
    _verified_protocol_root()
    snapshot_path = Path(os.path.abspath(arguments.snapshot))
    snapshot_payload = _read_regular_bytes(snapshot_path, label="P1a snapshot")
    snapshot_sha256 = _sha256_bytes(snapshot_payload)
    if snapshot_sha256 != arguments.snapshot_sha256:
        raise P2aError("P1a snapshot differs from its frozen commitment")
    snapshot = _load_json_bytes(snapshot_payload, label="P1a snapshot")
    if set(snapshot) != {"files"} or not isinstance(snapshot["files"], list):
        raise P2aError("P1a snapshot must contain exactly one files array")

    by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    required = {"id", "title", "size", "mime_type", "modified_time"}
    for row_number, raw in enumerate(snapshot["files"]):
        if not isinstance(raw, dict) or not required.issubset(raw):
            raise P2aError(f"P1a snapshot row {row_number} lacks required metadata")
        title = str(raw["title"])
        if not title.casefold().endswith(".glb"):
            continue
        uid = _extract_uid(title)
        if uid is None:
            continue
        try:
            size = int(str(raw["size"]))
        except ValueError as error:
            raise P2aError(f"P1a snapshot row {row_number} has invalid size") from error
        candidate = {
            "drive_file_id": str(raw["id"]),
            "source_uid": uid,
            "source_title": title,
            "source_size_bytes": size,
            "source_mime_type": str(raw["mime_type"]),
            "source_modified_time": str(raw["modified_time"]),
        }
        by_uid[uid].append(candidate)

    count = getattr(arguments, "count", DEFAULT_SCOPE_COUNT)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise P2aError("pilot scope count must be a positive integer")
    unique = [rows[0] for rows in by_uid.values() if len(rows) == 1]
    for row in unique:
        row["hmac_rank_hex"] = _pilot_rank(row["source_uid"], row["drive_file_id"])
    unique.sort(key=lambda row: row["hmac_rank_hex"])
    if len(unique) < count:
        raise P2aError("P1a snapshot has fewer unique Objaverse candidates than requested")
    selected = []
    for ordinal, row in enumerate(unique[:count]):
        selected.append({"ordinal": ordinal, "cache_name": f"source-{ordinal:04d}.glb", **row})
    plan = _validate_pilot_plan(
        {
            "schema": PILOT_SCHEMA,
            "schema_version": PILOT_SCHEMA_VERSION,
            "algorithm_id": PILOT_ALGORITHM,
            "algorithm_version": PILOT_ALGORITHM_VERSION,
            "protocol_root_sha256": P0_ROOT,
            "p1a_snapshot_sha256": snapshot_sha256,
            "selection_domain": PILOT_DOMAIN,
            "selection_seed_sha256": _sha256_bytes(bytes.fromhex(BOOTSTRAP_SEED_HEX)),
            "pilot_kind": "ENGINEERING_P2A_SOURCE_ONLY_NONSTATISTICAL",
            "candidate_count": count,
            "candidates": selected,
            "constraints": {
                "cohort_selected": False,
                "complexity_quantile_frozen": False,
                "eligibility": "PENDING",
                "mvx_outcome_accessed": False,
                "split": None,
            },
        }
    )
    output = _private_path(arguments.output)
    action = _publish_bytes_once(output, _json_document(plan))
    return {
        "action": "COMPLETED" if action == "WRITTEN" else "SKIP",
        "candidate_count": count,
        "pilot_plan_sha256": _canonical_hash(plan),
        "private_identity_published": False,
    }


def _cache_path(cache_root: Path, source_sha256: str) -> Path:
    if not SHA256_PATTERN.fullmatch(source_sha256):
        raise P2aError("source SHA-256 is invalid")
    return cache_root / "sha256" / source_sha256[:2] / f"{source_sha256}.glb"


def _candidate_commitment_payload(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: source[key]
        for key in (
            "drive_file_id",
            "source_uid",
            "source_title",
            "source_size_bytes",
            "source_sha256",
        )
    }


def _validate_audit_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(value)
    expected = {
        "schema",
        "schema_version",
        "algorithm_id",
        "algorithm_version",
        "protocol_root_sha256",
        "pilot_plan_sha256",
        "source_count",
        "sources",
        "profile",
        "constraints",
    }
    if set(document) != expected:
        raise P2aError("audit plan fields differ from the closed contract")
    if document["schema"] != "MVX-P2A-SOURCE-AUDIT-PLAN":
        raise P2aError("audit plan schema identity is invalid")
    if document["schema_version"] != "0.1.0":
        raise P2aError("audit plan schema version is invalid")
    if document["algorithm_id"] != AUDIT_ALGORITHM:
        raise P2aError("audit plan algorithm is invalid")
    if document["algorithm_version"] != AUDIT_ALGORITHM_VERSION:
        raise P2aError("audit plan algorithm version is invalid")
    if document["protocol_root_sha256"] != P0_ROOT:
        raise P2aError("audit plan protocol root is invalid")
    if not SHA256_PATTERN.fullmatch(str(document["pilot_plan_sha256"])):
        raise P2aError("audit plan pilot commitment is invalid")
    sources = document["sources"]
    source_count = document["source_count"]
    if (
        isinstance(source_count, bool)
        or not isinstance(source_count, int)
        or source_count < 1
        or not isinstance(sources, list)
    ):
        raise P2aError("audit plan source count is invalid")
    if len(sources) != source_count:
        raise P2aError("audit plan source array length is invalid")
    seen_hashes: set[str] = set()
    seen_uids: set[str] = set()
    for ordinal, receipt in enumerate(sources):
        expected_fields = {
            "ordinal",
            "drive_file_id",
            "source_uid",
            "source_title",
            "source_size_bytes",
            "source_sha256",
            "candidate_commitment_sha256",
            "cache_locator",
        }
        if not isinstance(receipt, dict) or set(receipt) != expected_fields:
            raise P2aError("source receipt fields are invalid")
        if receipt["ordinal"] != ordinal:
            raise P2aError("source receipt ordinals are not contiguous")
        source_hash = receipt["source_sha256"]
        uid = receipt["source_uid"]
        if not isinstance(source_hash, str) or not SHA256_PATTERN.fullmatch(source_hash):
            raise P2aError("source receipt SHA-256 is invalid")
        if not isinstance(uid, str) or not UID_PATTERN.fullmatch(uid):
            raise P2aError("source receipt UID is invalid")
        if source_hash in seen_hashes or uid in seen_uids:
            raise P2aError("pilot receipts contain a repeated source or lineage")
        seen_hashes.add(source_hash)
        seen_uids.add(uid)
        if receipt["cache_locator"] != f"sha256/{source_hash[:2]}/{source_hash}.glb":
            raise P2aError("source cache locator is not content-addressed")
        candidate_payload = _candidate_commitment_payload(receipt)
        if receipt["candidate_commitment_sha256"] != _canonical_hash(candidate_payload):
            raise P2aError("source candidate commitment is invalid")
    expected_profile = {
        "accessor_sparse": "DECLARED_LIMIT",
        "audit_algorithm": AUDIT_ALGORITHM,
        "external_uri_resolution": "FORBIDDEN",
        "gltf_validator": f"KhronosGroup/glTF-Validator@{VALIDATOR_VERSION}",
        "max_accessor_count": MAX_ACCESSOR_COUNT,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_triangles": MAX_TRIANGLES,
        "max_child_no_status_attempts": MAX_CHILD_NO_STATUS_ATTEMPTS,
        "mesh_vertex_merge": "EXACT_BINARY64_NORMALISE_NEGATIVE_ZERO",
        "mvx_operations": "FORBIDDEN",
        "scene_policy": "DEFAULT_ELSE_SOLE_SCENE_ELSE_DECLARED_LIMIT",
        "solid_verifier": "NOT_AVAILABLE_NEVER_EMIT_V",
        "supported_required_extensions": sorted(SUPPORTED_REQUIRED_EXTENSIONS),
        "unsupported_required_extensions": "DECLARED_LIMIT_U",
    }
    if document["profile"] != expected_profile:
        raise P2aError("audit profile differs from the frozen pilot profile")
    if document["constraints"] != {
        "cohort_selected": False,
        "complexity_quantile": None,
        "eligibility": "PENDING",
        "mvx_outcome_accessed": False,
        "split": None,
    }:
        raise P2aError("audit plan constraints are invalid")
    return document


def seal_sources(arguments: argparse.Namespace) -> dict[str, Any]:
    _verified_protocol_root()
    pilot_payload = _read_regular_bytes(
        Path(os.path.abspath(arguments.pilot_plan)), label="private pilot plan"
    )
    pilot = _validate_pilot_plan(_load_json_bytes(pilot_payload, label="private pilot plan"))
    if _canonical_hash(pilot) != arguments.pilot_plan_sha256:
        raise P2aError("private pilot plan differs from its commitment")
    incoming = _private_path(arguments.incoming, create_directory=True)
    cache_root = _private_path(arguments.cache_root, create_directory=True)

    receipts: list[dict[str, Any]] = []
    for candidate in pilot["candidates"]:
        source_path = incoming / candidate["cache_name"]
        payload = _read_regular_bytes(
            source_path,
            label=f"incoming pilot source {candidate['ordinal']}",
            maximum=MAX_SOURCE_BYTES,
        )
        if len(payload) != candidate["source_size_bytes"]:
            raise P2aError("incoming source size differs from the P1a snapshot")
        source_sha256 = _sha256_bytes(payload)
        cache_path = _cache_path(cache_root, source_sha256)
        _publish_bytes_once(cache_path, payload, mode=0o400)
        cached = _read_regular_bytes(cache_path, label="content-addressed source cache")
        if cached != payload:
            raise P2aError("content-addressed cache differs after publication")
        candidate_payload = _candidate_commitment_payload(
            {
                **candidate,
                "source_size_bytes": len(payload),
                "source_sha256": source_sha256,
            }
        )
        receipts.append(
            {
                "ordinal": candidate["ordinal"],
                **candidate_payload,
                "candidate_commitment_sha256": _canonical_hash(candidate_payload),
                "cache_locator": f"sha256/{source_sha256[:2]}/{source_sha256}.glb",
            }
        )

    profile = {
        "accessor_sparse": "DECLARED_LIMIT",
        "audit_algorithm": AUDIT_ALGORITHM,
        "external_uri_resolution": "FORBIDDEN",
        "gltf_validator": f"KhronosGroup/glTF-Validator@{VALIDATOR_VERSION}",
        "max_accessor_count": MAX_ACCESSOR_COUNT,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_triangles": MAX_TRIANGLES,
        "max_child_no_status_attempts": MAX_CHILD_NO_STATUS_ATTEMPTS,
        "mesh_vertex_merge": "EXACT_BINARY64_NORMALISE_NEGATIVE_ZERO",
        "mvx_operations": "FORBIDDEN",
        "scene_policy": "DEFAULT_ELSE_SOLE_SCENE_ELSE_DECLARED_LIMIT",
        "solid_verifier": "NOT_AVAILABLE_NEVER_EMIT_V",
        "supported_required_extensions": sorted(SUPPORTED_REQUIRED_EXTENSIONS),
        "unsupported_required_extensions": "DECLARED_LIMIT_U",
    }
    plan = _validate_audit_plan(
        {
            "schema": "MVX-P2A-SOURCE-AUDIT-PLAN",
            "schema_version": "0.1.0",
            "algorithm_id": AUDIT_ALGORITHM,
            "algorithm_version": AUDIT_ALGORITHM_VERSION,
            "protocol_root_sha256": P0_ROOT,
            "pilot_plan_sha256": _canonical_hash(pilot),
            "source_count": len(receipts),
            "sources": receipts,
            "profile": profile,
            "constraints": {
                "cohort_selected": False,
                "complexity_quantile": None,
                "eligibility": "PENDING",
                "mvx_outcome_accessed": False,
                "split": None,
            },
        }
    )
    output = _private_path(arguments.output)
    action = _publish_bytes_once(output, _json_document(plan))
    return {
        "action": "COMPLETED" if action == "WRITTEN" else "SKIP",
        "source_count": len(receipts),
        "audit_plan_sha256": _canonical_hash(plan),
        "source_set_commitment_sha256": _canonical_hash(
            [
                {
                    "candidate_commitment_sha256": row["candidate_commitment_sha256"],
                    "source_sha256": row["source_sha256"],
                }
                for row in receipts
            ]
        ),
        "private_identity_published": False,
    }


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
        raise P2aError("cannot bind P2a execution to Git") from error
    return result.stdout.strip()


def _closure_sha256(paths: Iterable[Path]) -> str:
    rows = [
        {
            "path": path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": hash_artifact(path),
        }
        for path in sorted(paths, key=lambda item: item.as_posix())
    ]
    return _canonical_hash(rows)


def _runtime_code_identity() -> tuple[str, str, str]:
    expected_package_root = (REPOSITORY_ROOT / "src/morphoia").resolve()
    for module in (checkpoint_module, hmac_rank_module, protocol_module):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise P2aError("runtime module lacks a filesystem identity")
        resolved = Path(module_file).resolve()
        if expected_package_root not in resolved.parents:
            raise P2aError("runtime module was imported outside the committed checkout")
    if Path(protocol_module.PROJECT_ROOT).resolve() != REPOSITORY_ROOT.resolve():
        raise P2aError("runtime protocol root differs from the runner checkout")

    script_path = Path(__file__).resolve()
    paths = (
        script_path,
        VALIDATOR_WRAPPER,
        VALIDATOR_PACKAGE_JSON,
        VALIDATOR_PACKAGE_LOCK,
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
        raise P2aError("cannot verify the P2a code closure against Git HEAD")
    if dirty.returncode == 1:
        raise P2aError("P2a code closure must be committed before source audit")
    commit = _git_output("rev-parse", "HEAD")
    tree = _git_output("rev-parse", "HEAD^{tree}")
    closure = _closure_sha256(paths)
    code_sha256 = _canonical_hash(
        {
            "algorithm": "MVX-P2A-CODE-CLOSURE-1",
            "source_closure_sha256": closure,
        }
    )
    return code_sha256, commit, tree


def _environment_sha256() -> str:
    executable = Path(sys.executable).resolve()
    node_name = shutil.which("node")
    if not node_name:
        raise P2aError("locked P2a environment lacks Node.js")
    node = Path(node_name).resolve()
    validator_files = tuple(
        sorted(path for path in VALIDATOR_INSTALL_ROOT.rglob("*") if path.is_file())
    )
    if not validator_files:
        raise P2aError("locked Khronos validator is not installed; run npm ci")
    installed_package = _load_json_bytes(
        _read_regular_bytes(
            VALIDATOR_INSTALL_ROOT / "package.json", label="installed Khronos validator package"
        ),
        label="installed Khronos validator package",
    )
    if installed_package.get("version") != VALIDATOR_VERSION:
        raise P2aError("installed Khronos validator version differs from the lock")
    payload = {
        "algorithm": "MVX-P2A-STDLIB-KHRONOS-ENVIRONMENT-2",
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_cache_tag": sys.implementation.cache_tag,
        "platform": platform.platform(),
        "executable_sha256": hash_artifact(executable),
        "node_executable_sha256": hash_artifact(node),
        "khronos_validator_version": VALIDATOR_VERSION,
        "khronos_validator_install_sha256": _closure_sha256(validator_files),
        "khronos_validator_lock_sha256": hash_artifact(VALIDATOR_PACKAGE_LOCK),
        "pyproject_sha256": hash_artifact(REPOSITORY_ROOT / "pyproject.toml"),
        "uv_lock_sha256": hash_artifact(REPOSITORY_ROOT / "uv.lock"),
        "third_party_geometry_libraries": [],
    }
    return _canonical_hash(payload)


def _make_object_plan(
    source: Mapping[str, Any], profile: Mapping[str, Any], code_sha256: str, environment: str
) -> tuple[dict[str, Any], str]:
    identity = WorkIdentity(
        protocol_root_sha256=P0_ROOT,
        split_sha256=_canonical_hash(NO_SPLIT_DOMAIN),
        source_sha256=str(source["source_sha256"]),
        lineage_id=f"objaverse:{source['source_uid']}",
        profile_sha256=_canonical_hash(profile),
        config_sha256=_canonical_hash(
            {
                "algorithm": AUDIT_ALGORITHM,
                "algorithm_version": AUDIT_ALGORITHM_VERSION,
                "candidate_commitment_sha256": source["candidate_commitment_sha256"],
                "script_version": SCRIPT_VERSION,
            }
        ),
        code_sha256=code_sha256,
        environment_sha256=environment,
        phase_id="P2a",
        stage_id="GLB_SOURCE_AUDIT",
        split="none",
        open_once=False,
    )
    stage = make_stage(identity, required_artifacts=tuple(OBJECT_ARTIFACT_FILES))
    return make_execution_plan(f"MVX-P2A-{identity.work_id[:16]}", [stage]), identity.work_id


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GlbInvalid("JSON object contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise GlbInvalid(f"JSON contains unsupported numeric constant {value}", error_code="MVX-I006")


def _parse_glb_container(payload: bytes) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    if len(payload) < 20:
        raise GlbInvalid("GLB is shorter than its mandatory header and JSON chunk")
    magic, version, total_length = struct.unpack_from("<4sII", payload, 0)
    if magic != GLB_MAGIC:
        raise GlbInvalid("GLB magic is invalid")
    if version != 2:
        raise GlbInvalid("only GLB version 2 is supported", error_code="MVX-I001")
    if total_length != len(payload):
        raise GlbInvalid("GLB declared length differs from exact source bytes")

    chunks: list[tuple[int, bytes]] = []
    offset = 12
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise GlbInvalid("GLB chunk header is truncated")
        length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        end = offset + length
        if length % 4 != 0 or end > len(payload):
            raise GlbInvalid("GLB chunk length is unaligned or out of bounds")
        chunks.append((chunk_type, payload[offset:end]))
        offset = end
    if offset != len(payload) or not chunks or chunks[0][0] != JSON_CHUNK:
        raise GlbInvalid("GLB must begin with exactly one JSON chunk")
    if sum(chunk_type == JSON_CHUNK for chunk_type, _ in chunks) != 1:
        raise GlbInvalid("GLB contains more than one JSON chunk")
    if sum(chunk_type == BIN_CHUNK for chunk_type, _ in chunks) > 1:
        raise GlbInvalid("GLB contains more than one BIN chunk")
    unknown = sorted(
        {f"0x{chunk_type:08x}" for chunk_type, _ in chunks[1:] if chunk_type != BIN_CHUNK}
    )
    if unknown:
        raise GlbDeclaredLimit("GLB contains an unsupported chunk type")

    json_chunk = chunks[0][1]
    if len(json_chunk) > MAX_JSON_BYTES:
        raise GlbDeclaredLimit("GLB JSON chunk exceeds the pilot resource bound")
    try:
        text = json_chunk.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
        first = len(text) - len(text.lstrip(" \t\r\n"))
        document, end = decoder.raw_decode(text, first)
        if any(character != " " for character in text[end:]):
            raise GlbInvalid("GLB JSON chunk padding must contain spaces only")
    except GlbInvalid:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise GlbInvalid("GLB JSON chunk is not strict UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise GlbInvalid("GLB JSON root must be an object")
    binary = next((chunk for chunk_type, chunk in chunks if chunk_type == BIN_CHUNK), b"")
    evidence = {
        "glb_version": version,
        "declared_length": total_length,
        "chunk_count": len(chunks),
        "json_chunk_bytes": len(json_chunk),
        "bin_chunk_bytes": len(binary),
        "unknown_chunk_types": unknown,
    }
    return document, binary, evidence


def _require_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise GlbInvalid(f"{field} must be an array")
    return value


def _require_index(value: Any, *, field: str, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < upper:
        raise GlbInvalid(f"{field} index is out of bounds")
    return value


def _require_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GlbInvalid(f"{field} must be a JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise GlbInvalid(f"{field} is non-finite", error_code="MVX-I006")
    return result


COMPONENTS: dict[int, tuple[str, int, bool]] = {
    5120: ("b", 1, True),
    5121: ("B", 1, False),
    5122: ("h", 2, True),
    5123: ("H", 2, False),
    5125: ("I", 4, False),
    5126: ("f", 4, True),
}
TYPE_WIDTH = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


def _normalise_component(value: float, component_type: int, normalised: bool) -> float:
    if component_type == 5126 or not normalised:
        return float(value)
    if component_type == 5120:
        return max(float(value) / 127.0, -1.0)
    if component_type == 5122:
        return max(float(value) / 32767.0, -1.0)
    if component_type == 5121:
        return float(value) / 255.0
    if component_type == 5123:
        return float(value) / 65535.0
    if component_type == 5125:
        return float(value) / 4294967295.0
    raise GlbInvalid("unsupported normalised accessor component type")


def _decode_accessor(
    document: Mapping[str, Any], binary: bytes, accessor_index: int
) -> tuple[list[Any], dict[str, Any]]:
    accessors = _require_list(document.get("accessors", []), field="accessors")
    views = _require_list(document.get("bufferViews", []), field="bufferViews")
    index = _require_index(accessor_index, field="accessor", upper=len(accessors))
    accessor = accessors[index]
    if not isinstance(accessor, dict):
        raise GlbInvalid("accessor must be an object")
    if "sparse" in accessor:
        raise GlbDeclaredLimit("sparse accessors are outside the pilot profile")
    if "bufferView" not in accessor:
        raise GlbDeclaredLimit("accessors without a bufferView are outside the pilot profile")
    view_index = _require_index(accessor["bufferView"], field="bufferView", upper=len(views))
    view = views[view_index]
    if not isinstance(view, dict):
        raise GlbInvalid("bufferView must be an object")
    buffer_index = view.get("buffer", 0)
    if isinstance(buffer_index, bool) or not isinstance(buffer_index, int):
        raise GlbInvalid("bufferView.buffer must be an integer")
    if buffer_index != 0:
        raise GlbDeclaredLimit("only the embedded GLB BIN buffer is supported")

    component_type = accessor.get("componentType")
    accessor_type = accessor.get("type")
    count = accessor.get("count")
    if isinstance(component_type, bool) or not isinstance(component_type, int):
        raise GlbInvalid("accessor.componentType must be an integer")
    if not isinstance(accessor_type, str):
        raise GlbInvalid("accessor.type must be a string")
    if component_type not in COMPONENTS or accessor_type not in TYPE_WIDTH:
        raise GlbInvalid("accessor componentType or type is unsupported")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 0 <= count <= MAX_ACCESSOR_COUNT
    ):
        raise GlbDeclaredLimit("accessor count exceeds the pilot bound")
    fmt, component_size, _ = COMPONENTS[component_type]
    width = TYPE_WIDTH[accessor_type]
    element_size = component_size * width
    stride = view.get("byteStride", element_size)
    if isinstance(stride, bool) or not isinstance(stride, int):
        raise GlbInvalid("bufferView byteStride is invalid")
    if stride < element_size or stride % component_size != 0 or stride > 252:
        raise GlbInvalid("bufferView byteStride violates glTF bounds")
    view_offset = view.get("byteOffset", 0)
    view_length = view.get("byteLength")
    accessor_offset = accessor.get("byteOffset", 0)
    for name, value in (
        ("bufferView.byteOffset", view_offset),
        ("bufferView.byteLength", view_length),
        ("accessor.byteOffset", accessor_offset),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise GlbInvalid(f"{name} is invalid")
    if (view_offset + accessor_offset) % component_size:
        raise GlbInvalid(
            "accessor byte offset is not aligned to its component size",
            error_code="MVX-I007",
        )
    buffers = _require_list(document.get("buffers", []), field="buffers")
    if not buffers or not isinstance(buffers[0], dict):
        raise GlbInvalid("embedded buffer declaration is missing")
    declared_buffer_length = buffers[0].get("byteLength")
    if (
        isinstance(declared_buffer_length, bool)
        or not isinstance(declared_buffer_length, int)
        or declared_buffer_length < 0
    ):
        raise GlbInvalid("embedded buffer byteLength is invalid")
    view_end = view_offset + view_length
    if view_end > declared_buffer_length or view_end > len(binary):
        raise GlbInvalid("bufferView exceeds the embedded BIN chunk")
    required_end = view_offset + accessor_offset
    if count:
        required_end += (count - 1) * stride + element_size
    if required_end > view_end:
        raise GlbInvalid("accessor exceeds its bufferView")

    unpacker = struct.Struct("<" + fmt * width)
    values: list[Any] = []
    normalised = accessor.get("normalized", False)
    if not isinstance(normalised, bool):
        raise GlbInvalid("accessor.normalized must be a boolean")
    if component_type == 5126 and normalised:
        raise GlbInvalid("floating-point accessors cannot be normalized")
    for position in range(count):
        offset = view_offset + accessor_offset + position * stride
        raw = unpacker.unpack_from(binary, offset)
        decoded = tuple(_normalise_component(value, component_type, normalised) for value in raw)
        if any(not math.isfinite(value) for value in decoded):
            raise GlbInvalid("accessor contains a non-finite value")
        values.append(decoded[0] if width == 1 else decoded)
    return values, {
        "accessor_index": index,
        "component_type": component_type,
        "count": count,
        "normalised": normalised,
        "type": accessor_type,
    }


Matrix = tuple[tuple[float, float, float, float], ...]


def _identity_matrix() -> Matrix:
    return (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def _matrix_multiply(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        tuple(sum(left[row][k] * right[k][column] for k in range(4)) for column in range(4))
        for row in range(4)
    )


def _node_matrix(node: Mapping[str, Any]) -> Matrix:
    if "matrix" in node:
        if any(key in node for key in ("translation", "rotation", "scale")):
            raise GlbInvalid("node cannot combine matrix and TRS transforms")
        values = node["matrix"]
        if not isinstance(values, list) or len(values) != 16:
            raise GlbInvalid("node matrix must contain sixteen numbers")
        matrix = tuple(
            tuple(
                _require_number(values[column * 4 + row], field="node.matrix element")
                for column in range(4)
            )
            for row in range(4)
        )
        return matrix

    translation = node.get("translation", [0.0, 0.0, 0.0])
    rotation = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    scale = node.get("scale", [1.0, 1.0, 1.0])
    if not isinstance(translation, list) or len(translation) != 3:
        raise GlbInvalid("node translation must contain three numbers")
    if not isinstance(rotation, list) or len(rotation) != 4:
        raise GlbInvalid("node rotation must contain four numbers")
    if not isinstance(scale, list) or len(scale) != 3:
        raise GlbInvalid("node scale must contain three numbers")
    tx, ty, tz = (_require_number(value, field="node.translation element") for value in translation)
    x, y, z, w = (_require_number(value, field="node.rotation element") for value in rotation)
    sx, sy, sz = (_require_number(value, field="node.scale element") for value in scale)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if not math.isclose(norm, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise GlbInvalid("node rotation quaternion is not unit length")
    rotation_matrix: Matrix = (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0.0),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0.0),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    scale_matrix: Matrix = (
        (sx, 0.0, 0.0, 0.0),
        (0.0, sy, 0.0, 0.0),
        (0.0, 0.0, sz, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    translation_matrix: Matrix = (
        (1.0, 0.0, 0.0, tx),
        (0.0, 1.0, 0.0, ty),
        (0.0, 0.0, 1.0, tz),
        (0.0, 0.0, 0.0, 1.0),
    )
    return _matrix_multiply(translation_matrix, _matrix_multiply(rotation_matrix, scale_matrix))


def _transform_position(matrix: Matrix, position: Sequence[float]) -> tuple[float, float, float]:
    if len(position) != 3:
        raise GlbInvalid("POSITION accessor must contain VEC3 values")
    x, y, z = (float(value) for value in position)
    result = tuple(
        matrix[row][0] * x + matrix[row][1] * y + matrix[row][2] * z + matrix[row][3]
        for row in range(3)
    )
    if any(not math.isfinite(value) for value in result):
        raise GlbInvalid("transformed POSITION is non-finite", error_code="MVX-I006")
    return tuple(0.0 if value == 0.0 else value for value in result)


def _linear_determinant(matrix: Matrix) -> float:
    a, b, c = matrix[0][:3]
    d, e, f = matrix[1][:3]
    g, h, i = matrix[2][:3]
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if not math.isfinite(determinant):
        raise GlbInvalid("node transform determinant is non-finite", error_code="MVX-I006")
    return determinant


def _triangles_from_indices(indices: Sequence[int], mode: int) -> list[tuple[int, int, int]]:
    if mode == 4:
        if len(indices) % 3:
            raise GlbInvalid("TRIANGLES index count is not divisible by three")
        return [tuple(indices[offset : offset + 3]) for offset in range(0, len(indices), 3)]
    if mode == 5:
        triangles = []
        for offset in range(max(0, len(indices) - 2)):
            a, b, c = indices[offset : offset + 3]
            triangles.append((b, a, c) if offset % 2 else (a, b, c))
        return triangles
    if mode == 6:
        return (
            [
                (indices[0], indices[offset], indices[offset + 1])
                for offset in range(1, len(indices) - 1)
            ]
            if indices
            else []
        )
    return []


def _materialise_scene(
    document: Mapping[str, Any], binary: bytes
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], dict[str, Any]]:
    asset = document.get("asset")
    if not isinstance(asset, dict) or asset.get("version") != "2.0":
        raise GlbInvalid("glTF asset.version must be exactly 2.0", error_code="MVX-I001")
    if "minVersion" in asset and asset["minVersion"] != "2.0":
        raise GlbInvalid("glTF asset.minVersion is unsupported", error_code="MVX-I001")
    used_extensions = document.get("extensionsUsed", [])
    required_extensions = document.get("extensionsRequired", [])
    for name, value in (
        ("extensionsUsed", used_extensions),
        ("extensionsRequired", required_extensions),
    ):
        if (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item for item in value)
            or len(value) != len(set(value))
        ):
            raise GlbInvalid(f"{name} must be a unique non-empty string array")
    if not set(required_extensions).issubset(used_extensions):
        raise GlbInvalid("extensionsRequired must be included in extensionsUsed")
    unsupported = sorted(set(required_extensions) - SUPPORTED_REQUIRED_EXTENSIONS)
    if unsupported:
        raise GlbInvalid(
            "GLB requires an extension outside the pilot profile", error_code="MVX-I004"
        )

    buffers = _require_list(document.get("buffers", []), field="buffers")
    if len(buffers) != 1 or not isinstance(buffers[0], dict):
        raise GlbDeclaredLimit("pilot supports exactly one embedded GLB buffer")
    if "uri" in buffers[0]:
        raise GlbInvalid("buffer URI resolution is forbidden", error_code="MVX-I008")
    byte_length = buffers[0].get("byteLength")
    if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 0:
        raise GlbInvalid("embedded buffer byteLength is invalid")
    if byte_length > len(binary) or len(binary) - byte_length > 3:
        raise GlbInvalid("embedded BIN chunk length differs from buffer.byteLength")

    scenes = _require_list(document.get("scenes", []), field="scenes")
    nodes = _require_list(document.get("nodes", []), field="nodes")
    meshes = _require_list(document.get("meshes", []), field="meshes")
    views = _require_list(document.get("bufferViews", []), field="bufferViews")
    for view in views:
        if not isinstance(view, dict):
            raise GlbInvalid("bufferView must be an object")
        extensions = view.get("extensions", {})
        if not isinstance(extensions, dict):
            raise GlbInvalid("bufferView extensions must be an object")
        if "EXT_meshopt_compression" in extensions:
            raise GlbInvalid(
                "bufferView uses unsupported meshopt compression", error_code="MVX-I004"
            )
    if len(nodes) > MAX_SCENE_NODES:
        raise GlbDeclaredLimit("node count exceeds the diagnostic bound", error_code="MVX-R003")

    parent_count = [0] * len(nodes)
    validated_children: list[list[int]] = []
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise GlbInvalid("node must be an object")
        node_extensions = node.get("extensions", {})
        if not isinstance(node_extensions, dict):
            raise GlbInvalid("node extensions must be an object")
        if "EXT_mesh_gpu_instancing" in node_extensions:
            raise GlbInvalid("node uses unsupported GPU instancing", error_code="MVX-I004")
        children = node.get("children", [])
        if not isinstance(children, list) or len(children) != len(set(map(str, children))):
            raise GlbInvalid("node.children must be an array of unique indices")
        checked_children = [
            _require_index(child, field="node child", upper=len(nodes)) for child in children
        ]
        if len(checked_children) != len(set(checked_children)):
            raise GlbInvalid("node.children contains a repeated index")
        for child in checked_children:
            parent_count[child] += 1
            if parent_count[child] > 1:
                raise GlbInvalid("node graph is not a disjoint strict tree")
        validated_children.append(checked_children)

    colours = [0] * len(nodes)

    def validate_tree(node_index: int) -> None:
        if colours[node_index] == 1:
            raise GlbInvalid("node graph contains a cycle")
        if colours[node_index] == 2:
            return
        colours[node_index] = 1
        for child in validated_children[node_index]:
            validate_tree(child)
        colours[node_index] = 2

    for node_index in range(len(nodes)):
        validate_tree(node_index)
    if "scene" in document:
        scene_index = _require_index(document["scene"], field="scene", upper=len(scenes))
    elif len(scenes) == 1:
        scene_index = 0
    else:
        raise GlbDeclaredLimit("GLB has no unambiguous default scene")
    scene = scenes[scene_index]
    if not isinstance(scene, dict):
        raise GlbInvalid("scene must be an object")
    roots = scene.get("nodes", [])
    if not isinstance(roots, list) or len(roots) != len(set(map(str, roots))):
        raise GlbInvalid("scene.nodes must be an array")
    checked_roots = [_require_index(root, field="scene root", upper=len(nodes)) for root in roots]
    if len(checked_roots) != len(set(checked_roots)):
        raise GlbInvalid("scene.nodes contains a repeated root")
    if any(parent_count[root] for root in checked_roots):
        raise GlbInvalid("scene root is also referenced as a child")

    instances: list[tuple[int, Matrix]] = []

    def visit(node_index: int, parent: Matrix, stack: frozenset[int]) -> None:
        checked_index = _require_index(node_index, field="node", upper=len(nodes))
        if checked_index in stack:
            raise GlbInvalid("node graph contains a cycle")
        node = nodes[checked_index]
        if not isinstance(node, dict):
            raise GlbInvalid("node must be an object")
        if "skin" in node:
            raise GlbDeclaredLimit("skinned geometry is outside the pilot profile")
        transform = _matrix_multiply(parent, _node_matrix(node))
        if "mesh" in node:
            mesh_index = _require_index(node["mesh"], field="mesh", upper=len(meshes))
            instances.append((mesh_index, transform))
        children = validated_children[checked_index]
        next_stack = stack | {checked_index}
        for child in children:
            visit(child, transform, next_stack)

    for root in checked_roots:
        visit(root, _identity_matrix(), frozenset())
    if len(instances) > MAX_SCENE_NODES:
        raise GlbDeclaredLimit(
            "mesh instance count exceeds the diagnostic bound", error_code="MVX-R003"
        )

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    primitive_count = 0
    ignored_non_triangle_primitives = 0
    decoded_accessors: set[int] = set()
    for mesh_index, transform in instances:
        mesh = meshes[mesh_index]
        if not isinstance(mesh, dict):
            raise GlbInvalid("mesh must be an object")
        if "weights" in mesh:
            raise GlbDeclaredLimit("morph weights are outside the pilot profile")
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list):
            raise GlbInvalid("mesh.primitives must be an array")
        for primitive in primitives:
            primitive_count += 1
            if not isinstance(primitive, dict):
                raise GlbInvalid("mesh primitive must be an object")
            if "targets" in primitive:
                raise GlbDeclaredLimit("morph targets are outside the pilot profile")
            extensions = primitive.get("extensions", {})
            if not isinstance(extensions, dict):
                raise GlbInvalid("primitive extensions must be an object")
            if set(extensions) & DECLARED_LIMIT_EXTENSIONS:
                raise GlbInvalid(
                    "primitive uses an unsupported geometry extension", error_code="MVX-I004"
                )
            mode = primitive.get("mode", 4)
            if isinstance(mode, bool) or not isinstance(mode, int) or mode not in range(7):
                raise GlbInvalid("primitive mode is invalid")
            if mode not in {4, 5, 6}:
                raise GlbDeclaredLimit(
                    "selected scene contains a non-triangle primitive", error_code="MVX-G003"
                )
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict) or "POSITION" not in attributes:
                raise GlbInvalid("triangle primitive lacks a POSITION accessor")
            position_index = attributes["POSITION"]
            positions, position_meta = _decode_accessor(document, binary, position_index)
            decoded_accessors.add(position_meta["accessor_index"])
            if position_meta["type"] != "VEC3":
                raise GlbInvalid("POSITION accessor is not VEC3")
            position_component = position_meta["component_type"]
            if position_component != 5126 and not (
                "KHR_mesh_quantization" in required_extensions
                and position_component in {5120, 5121, 5122, 5123}
            ):
                raise GlbInvalid("POSITION component type is invalid", error_code="MVX-I003")
            transformed = [_transform_position(transform, item) for item in positions]
            if len(vertices) + len(transformed) > MAX_VERTEX_INSTANCES:
                raise GlbDeclaredLimit(
                    "vertex instance count exceeds the diagnostic bound", error_code="MVX-R003"
                )
            base = len(vertices)
            vertices.extend(transformed)
            if "indices" in primitive:
                raw_indices, index_meta = _decode_accessor(document, binary, primitive["indices"])
                decoded_accessors.add(index_meta["accessor_index"])
                if index_meta["type"] != "SCALAR" or index_meta["component_type"] not in {
                    5121,
                    5123,
                    5125,
                }:
                    raise GlbInvalid("index accessor must use an unsigned SCALAR type")
                if index_meta["normalised"]:
                    raise GlbInvalid("index accessor cannot be normalized")
                indices = []
                for value in raw_indices:
                    integer = int(value)
                    if float(integer) != float(value) or not 0 <= integer < len(transformed):
                        raise GlbInvalid("primitive index is out of POSITION bounds")
                    indices.append(integer)
            else:
                indices = list(range(len(transformed)))
            local_faces = _triangles_from_indices(indices, mode)
            if _linear_determinant(transform) < 0.0:
                local_faces = [(face[0], face[2], face[1]) for face in local_faces]
            if len(faces) + len(local_faces) > MAX_TRIANGLES:
                raise GlbDeclaredLimit("materialised triangle count exceeds the pilot bound")
            faces.extend(tuple(base + index for index in face) for face in local_faces)

    evidence = {
        "scene_index": scene_index,
        "scene_root_count": len(roots),
        "node_instance_count": len(instances),
        "primitive_count": primitive_count,
        "ignored_non_triangle_primitives": ignored_non_triangle_primitives,
        "decoded_accessor_count": len(decoded_accessors),
        "required_extensions": sorted(required_extensions),
    }
    return vertices, faces, evidence


def _cross_squared(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    third: tuple[float, float, float],
) -> float:
    ux, uy, uz = (second[index] - first[index] for index in range(3))
    vx, vy, vz = (third[index] - first[index] for index in range(3))
    if any(not math.isfinite(value) for value in (ux, uy, uz, vx, vy, vz)):
        raise GlbInvalid("triangle coordinate difference is non-finite", error_code="MVX-I006")
    scale = max(abs(value) for value in (ux, uy, uz, vx, vy, vz))
    if scale == 0.0:
        return 0.0
    ux, uy, uz, vx, vy, vz = (value / scale for value in (ux, uy, uz, vx, vy, vz))
    cx, cy, cz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    return max(abs(cx), abs(cy), abs(cz))


def _topology_evidence(
    vertices: Sequence[tuple[float, float, float]], faces: Sequence[tuple[int, int, int]]
) -> tuple[str, dict[str, Any]]:
    exact_vertex: dict[tuple[float, float, float], int] = {}
    canonical_vertices: list[tuple[float, float, float]] = []
    remap: list[int] = []
    for vertex in vertices:
        normalised = tuple(0.0 if value == 0.0 else value for value in vertex)
        if normalised not in exact_vertex:
            exact_vertex[normalised] = len(canonical_vertices)
            canonical_vertices.append(normalised)
        remap.append(exact_vertex[normalised])

    canonical_faces = [tuple(remap[index] for index in face) for face in faces]
    degenerate = 0
    duplicate = 0
    seen_faces: set[tuple[int, int, int]] = set()
    edges: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for original, face in zip(faces, canonical_faces, strict=True):
        if (
            len(set(face)) < 3
            or _cross_squared(vertices[original[0]], vertices[original[1]], vertices[original[2]])
            == 0.0
        ):
            degenerate += 1
        unordered_face = tuple(sorted(face))
        if unordered_face in seen_faces:
            duplicate += 1
        seen_faces.add(unordered_face)
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edges[(min(start, end), max(start, end))].append((start, end))

    boundary = sum(len(incidence) == 1 for incidence in edges.values())
    non_manifold = sum(len(incidence) > 2 for incidence in edges.values())
    orientation_conflicts = sum(
        len(incidence) == 2 and incidence[0] == incidence[1] for incidence in edges.values()
    )

    vertex_links: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for face in canonical_faces:
        if len(set(face)) != 3:
            continue
        a, b, c = face
        vertex_links[a].append((b, c))
        vertex_links[b].append((c, a))
        vertex_links[c].append((a, b))
    non_manifold_vertices = 0
    for link_edges in vertex_links.values():
        adjacency: dict[int, set[int]] = defaultdict(set)
        for start, end in link_edges:
            adjacency[start].add(end)
            adjacency[end].add(start)
        if not adjacency:
            non_manifold_vertices += 1
            continue
        pending = [next(iter(adjacency))]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency[current] - visited)
        degrees = [len(adjacency[node]) for node in adjacency]
        degree_one = sum(degree == 1 for degree in degrees)
        link_is_cycle = all(degree == 2 for degree in degrees)
        link_is_path = degree_one == 2 and all(degree in {1, 2} for degree in degrees)
        if len(visited) != len(adjacency) or not (link_is_cycle or link_is_path):
            non_manifold_vertices += 1

    parent = list(range(len(canonical_faces)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(first: int, second: int) -> None:
        a, b = find(first), find(second)
        if a != b:
            parent[b] = a

    face_edges: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(canonical_faces):
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            face_edges[(min(start, end), max(start, end))].append(face_index)
    for incident_faces in face_edges.values():
        for other in incident_faces[1:]:
            union(incident_faces[0], other)
    components = len({find(index) for index in range(len(canonical_faces))}) if faces else 0

    if degenerate or duplicate or non_manifold or non_manifold_vertices or orientation_conflicts:
        status = "N"
        reason = "POSITIVE_NON_MANIFOLD_OR_INVALID_EVIDENCE"
    elif boundary:
        status = "O"
        reason = "POSITIVE_BOUNDARY_EDGE_EVIDENCE"
    else:
        status = "U"
        reason = "CLOSED_EDGE_MANIFOLD_BUT_NO_INDEPENDENT_SOLID_VERIFIER"
    if not faces:
        status = "U"
        reason = "NO_TRIANGULATED_SURFACE"
    xs = [point[0] for point in vertices]
    ys = [point[1] for point in vertices]
    zs = [point[2] for point in vertices]
    bbox = [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)] if vertices else None
    evidence = {
        "input_vertex_instances": len(vertices),
        "exact_unique_vertices": len(canonical_vertices),
        "triangles_materialised": len(faces),
        "edge_connected_components": components,
        "edge_count": len(edges),
        "boundary_edge_count": boundary,
        "non_manifold_edge_count": non_manifold,
        "non_manifold_vertex_count": non_manifold_vertices,
        "orientation_conflict_edge_count": orientation_conflicts,
        "degenerate_triangle_count": degenerate,
        "duplicate_triangle_count": duplicate,
        "bbox": bbox,
        "solid_verifier": "NOT_AVAILABLE",
        "classification_reason": reason,
    }
    return status, evidence


def _khronos_validate_bytes(payload: bytes) -> dict[str, Any]:
    node_name = shutil.which("node")
    if not node_name:
        raise P2aError("locked P2a environment lacks Node.js")
    if not VALIDATOR_WRAPPER.is_file() or not VALIDATOR_INSTALL_ROOT.is_dir():
        raise P2aError("locked Khronos validator runtime is not installed")
    try:
        completed = subprocess.run(
            (node_name, str(VALIDATOR_WRAPPER)),
            input=payload,
            cwd=VALIDATOR_ROOT,
            check=False,
            capture_output=True,
            timeout=min(CHILD_TIMEOUT_SECONDS, 120),
        )
    except subprocess.TimeoutExpired as error:
        raise GlbDeclaredLimit(
            "Khronos validation exceeded its time bound", error_code="MVX-R002"
        ) from error
    if completed.returncode != 0:
        raise ChildNoStatus(
            "Khronos validator exited without a report "
            f"(returncode={completed.returncode}, stderr_sha256={_sha256_bytes(completed.stderr)})"
        )
    if len(completed.stdout) > CHILD_OUTPUT_BYTES or len(completed.stderr) > CHILD_OUTPUT_BYTES:
        raise GlbDeclaredLimit(
            "Khronos validator report exceeded its output bound", error_code="MVX-R003"
        )
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ChildNoStatus("Khronos validator emitted an invalid report") from error
    expected = {
        "validator",
        "version",
        "validatedAt",
        "numErrors",
        "numWarnings",
        "numInfos",
        "numHints",
        "severityCounts",
        "codeCounts",
        "errorCodeCounts",
        "truncated",
    }
    if not isinstance(report, dict) or set(report) != expected:
        raise ChildNoStatus("Khronos validator report fields are invalid")
    if (
        report["validator"] != "KhronosGroup/glTF-Validator"
        or report["version"] != VALIDATOR_VERSION
    ):
        raise ChildNoStatus("Khronos validator identity differs from the locked runtime")
    for field in ("numErrors", "numWarnings", "numInfos", "numHints"):
        value = report[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ChildNoStatus("Khronos validator report count is invalid")
    if not isinstance(report["truncated"], bool):
        raise ChildNoStatus("Khronos validator truncation flag is invalid")
    for field in ("severityCounts", "codeCounts", "errorCodeCounts"):
        counts = report[field]
        if not isinstance(counts, dict) or any(
            not isinstance(key, str)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for key, value in counts.items()
        ):
            raise ChildNoStatus(f"Khronos validator {field} is invalid")
    if sum(report["errorCodeCounts"].values()) != report["numErrors"]:
        raise ChildNoStatus("Khronos validator error-code counts are inconsistent")
    if report["truncated"]:
        raise GlbDeclaredLimit(
            "Khronos validator issue report reached its bound", error_code="MVX-R003"
        )
    return report


def _preflight_source_policy(document: Mapping[str, Any]) -> None:
    asset = document.get("asset")
    if isinstance(asset, dict):
        version = asset.get("version")
        minimum = asset.get("minVersion")
        if isinstance(version, str) and version != "2.0":
            raise GlbInvalid("glTF asset version is unsupported", error_code="MVX-I001")
        if isinstance(minimum, str) and minimum != "2.0":
            raise GlbInvalid("glTF minimum version is unsupported", error_code="MVX-I001")
    for collection_name in ("buffers", "images"):
        collection = document.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if isinstance(item, dict) and "uri" in item:
                raise GlbInvalid(
                    f"{collection_name} URI resolution is forbidden", error_code="MVX-I008"
                )
    required = document.get("extensionsRequired", [])
    if (
        isinstance(required, list)
        and all(isinstance(item, str) for item in required)
        and set(required) - SUPPORTED_REQUIRED_EXTENSIONS
    ):
        raise GlbInvalid(
            "GLB requires an extension outside the diagnostic profile",
            error_code="MVX-I004",
        )


def _khronos_reject_code(report: Mapping[str, Any]) -> str:
    codes = {str(code).upper() for code in report.get("errorCodeCounts", {})}
    candidates: set[str] = set()
    for code in codes:
        if "URI" in code or "PATH" in code:
            candidates.add("MVX-I008")
        elif any(
            token in code
            for token in ("NON_FINITE", "NONFINITE", "INVALID_FLOAT", "INFINITE", "NAN")
        ):
            candidates.add("MVX-I006")
        elif any(
            token in code
            for token in (
                "INDEX",
                "OFFSET",
                "OUT_OF_BOUNDS",
                "OUT_OF_MAX_BOUND",
                "OUT_OF_MIN_BOUND",
                "MAX_MISMATCH",
                "MIN_MISMATCH",
            )
        ):
            candidates.add("MVX-I007")
        elif "EXTENSION" in code:
            candidates.add("MVX-I004")
        elif "RESOURCE" in code or "NOT_FOUND" in code:
            candidates.add("MVX-I005")
        elif any(
            token in code
            for token in (
                "ASSET_MAJOR_VERSION",
                "ASSET_MIN_VERSION",
                "UNSUPPORTED_GLTF_VERSION",
                "GLB_VERSION",
            )
        ):
            candidates.add("MVX-I001")
        else:
            candidates.add("MVX-I002")
    precedence = (
        "MVX-I008",
        "MVX-I002",
        "MVX-I006",
        "MVX-I007",
        "MVX-I003",
        "MVX-I005",
        "MVX-I004",
        "MVX-I001",
    )
    return next((code for code in precedence if code in candidates), "MVX-I002")


def audit_glb_bytes(payload: bytes) -> dict[str, Any]:
    source_sha256 = _sha256_bytes(payload)
    base = {
        "schema": AUDIT_SCHEMA,
        "schema_version": "0.1.0",
        "algorithm_id": AUDIT_ALGORITHM,
        "algorithm_version": AUDIT_ALGORITHM_VERSION,
        "source_sha256": source_sha256,
        "source_size_bytes": len(payload),
        "external_uri_accessed": False,
        "mvx_operation_accessed": False,
        "complexity_quantile": None,
        "eligibility": "PENDING",
        "split": None,
        "khronos_validation": None,
    }
    if len(payload) > MAX_SOURCE_BYTES:
        return {
            **base,
            "terminal_status": "DECLARED_LIMIT",
            "error_code": "MVX-R003",
            "format_status": "P2A_DIAGNOSTIC_RESOURCE_LIMIT",
            "topology_status": "U",
            "container": None,
            "scene": None,
            "geometry": None,
            "diagnostic": "SOURCE_EXCEEDS_PILOT_BYTE_LIMIT",
        }
    try:
        document, binary, container = _parse_glb_container(payload)
        _preflight_source_policy(document)
        validation = _khronos_validate_bytes(payload)
        base["khronos_validation"] = validation
        if validation["numErrors"]:
            raise GlbInvalid(
                "Khronos validator rejected the GLB",
                error_code=_khronos_reject_code(validation),
            )
        vertices, faces, scene = _materialise_scene(document, binary)
        topology, geometry = _topology_evidence(vertices, faces)
    except GlbDeclaredLimit as error:
        return {
            **base,
            "terminal_status": "DECLARED_LIMIT",
            "error_code": error.error_code,
            "format_status": "P2A_DIAGNOSTIC_DECLARED_LIMIT",
            "topology_status": "U",
            "container": locals().get("container"),
            "scene": None,
            "geometry": None,
            "diagnostic": str(error),
        }
    except GlbInvalid as error:
        return {
            **base,
            "terminal_status": "REJECT",
            "error_code": error.error_code,
            "format_status": "P2A_DIAGNOSTIC_REJECTED",
            "topology_status": "U",
            "container": locals().get("container"),
            "scene": None,
            "geometry": None,
            "diagnostic": str(error),
        }
    except MemoryError:
        return {
            **base,
            "terminal_status": "DECLARED_LIMIT",
            "error_code": "MVX-R001",
            "format_status": "P2A_DIAGNOSTIC_RESOURCE_LIMIT",
            "topology_status": "U",
            "container": locals().get("container"),
            "scene": None,
            "geometry": None,
            "diagnostic": "MEMORY_BOUND_REACHED",
        }
    except (OverflowError, RecursionError):
        return {
            **base,
            "terminal_status": "DECLARED_LIMIT",
            "error_code": "MVX-R003",
            "format_status": "P2A_DIAGNOSTIC_RESOURCE_LIMIT",
            "topology_status": "U",
            "container": locals().get("container"),
            "scene": None,
            "geometry": None,
            "diagnostic": "STRUCTURAL_BOUND_REACHED",
        }
    topology_codes = {"O": "MVX-G001", "N": "MVX-G002", "U": "MVX-G003"}
    if topology not in topology_codes:
        raise P2aError("stdlib diagnostic emitted an unsupported topology status")
    return {
        **base,
        "terminal_status": "DECLARED_LIMIT",
        "error_code": topology_codes[topology],
        "format_status": "P2A_DIAGNOSTIC_PROFILE_SCAN_COMPLETE",
        "topology_status": topology,
        "container": container,
        "scene": scene,
        "geometry": geometry,
        "diagnostic": "SOURCE_ONLY_AUDIT_COMPLETE",
    }


def _object_artifact_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / filename for name, filename in OBJECT_ARTIFACT_FILES.items()}


def _validate_object_bundle(directory: Path) -> bool:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or directory.is_symlink():
        raise P2aError("object artifact bundle is not a real directory")
    entries = {entry.name: entry for entry in directory.iterdir()}
    if set(entries) != OBJECT_BUNDLE_FILES:
        raise P2aError("object artifact bundle is partial or contains extras")
    for entry in entries.values():
        item = entry.lstat()
        if not stat.S_ISREG(item.st_mode) or entry.is_symlink():
            raise P2aError("object artifact bundle contains a non-regular entry")
    manifest_payload = _read_regular_bytes(
        entries["bundle-manifest.json"], label="object bundle manifest"
    )
    manifest = _load_json_bytes(manifest_payload, label="object bundle manifest")
    if set(manifest) != {"schema", "schema_version", "files"}:
        raise P2aError("object bundle manifest fields are invalid")
    if manifest["schema"] != "MVX-P2A-OBJECT-BUNDLE" or manifest["schema_version"] != "0.1.0":
        raise P2aError("object bundle manifest identity is invalid")
    if not isinstance(manifest["files"], dict) or set(manifest["files"]) != set(
        OBJECT_ARTIFACT_FILES.values()
    ):
        raise P2aError("object bundle manifest file set is invalid")
    for name, declared in manifest["files"].items():
        if not isinstance(declared, dict) or set(declared) != {"bytes", "sha256"}:
            raise P2aError("object bundle file commitment is invalid")
        payload = _read_regular_bytes(entries[name], label="object bundle artifact")
        if declared != {"bytes": len(payload), "sha256": _sha256_bytes(payload)}:
            raise P2aError("object bundle artifact differs from its commitment")
    ready = _load_json_bytes(
        _read_regular_bytes(entries["READY.json"], label="object READY marker"),
        label="object READY marker",
    )
    if ready != {
        "schema": "MVX-P2A-OBJECT-BUNDLE-READY",
        "schema_version": "0.1.0",
        "bundle_manifest_sha256": _sha256_bytes(manifest_payload),
    }:
        raise P2aError("object READY marker does not bind the bundle manifest")
    return True


def _publish_object_bundle(
    run_directory: Path,
    artifact_directory: Path,
    payloads: Mapping[str, bytes],
    attempt: int,
) -> None:
    if set(payloads) != set(OBJECT_ARTIFACT_FILES):
        raise P2aError("object artifact payload set is incomplete")
    if _validate_object_bundle(artifact_directory):
        for name, path in _object_artifact_paths(artifact_directory).items():
            if _read_regular_bytes(path, label="existing object artifact") != payloads[name]:
                raise P2aError("existing object artifact bundle conflicts with recomputation")
        return
    staging = run_directory / f"attempt-{attempt:04d}-artifacts.staging"
    try:
        os.mkdir(staging, 0o700)
        _fsync_directory(run_directory)
    except FileExistsError as error:
        raise P2aError("artifact staging already exists and must be recovered") from error
    for name, path in _object_artifact_paths(staging).items():
        _publish_bytes_once(path, payloads[name])
    manifest = {
        "schema": "MVX-P2A-OBJECT-BUNDLE",
        "schema_version": "0.1.0",
        "files": {
            filename: {"bytes": len(payloads[name]), "sha256": _sha256_bytes(payloads[name])}
            for name, filename in sorted(OBJECT_ARTIFACT_FILES.items())
        },
    }
    manifest_payload = _json_document(manifest)
    _publish_bytes_once(staging / "bundle-manifest.json", manifest_payload)
    _publish_bytes_once(
        staging / "READY.json",
        _json_document(
            {
                "schema": "MVX-P2A-OBJECT-BUNDLE-READY",
                "schema_version": "0.1.0",
                "bundle_manifest_sha256": _sha256_bytes(manifest_payload),
            }
        ),
    )
    _validate_object_bundle(staging)
    try:
        os.rename(staging, artifact_directory)
    except OSError as error:
        raise P2aError("cannot atomically publish object artifact bundle") from error
    _fsync_directory(run_directory)


def _quarantine_staging(run_directory: Path, staging: Path) -> None:
    quarantine = run_directory / "quarantine"
    _ensure_private_directory(quarantine)
    inventory = []
    for entry in sorted(staging.iterdir(), key=lambda item: item.name):
        metadata = entry.lstat()
        inventory.append(
            {"name": entry.name, "mode": stat.S_IFMT(metadata.st_mode), "bytes": metadata.st_size}
        )
    suffix = _canonical_hash(inventory)[:16]
    target = quarantine / f"{staging.name}.{suffix}"
    if target.exists() or target.is_symlink():
        raise P2aError("staging quarantine target already exists")
    os.rename(staging, target)
    _fsync_directory(quarantine)
    _fsync_directory(run_directory)


def _recover_staging(run_directory: Path, artifact_directory: Path) -> None:
    staging = sorted(
        (entry for entry in run_directory.iterdir() if entry.name.endswith("-artifacts.staging")),
        key=lambda item: item.name,
    )
    if artifact_directory.exists() and staging:
        raise P2aError("complete artifacts and staging coexist")
    ready: list[Path] = []
    partial: list[Path] = []
    for path in staging:
        try:
            complete = _validate_object_bundle(path)
        except P2aError:
            complete = False
        (ready if complete else partial).append(path)
    if len(ready) > 1:
        raise P2aError("multiple complete staging bundles conflict")
    for path in partial:
        _quarantine_staging(run_directory, path)
    if ready:
        os.rename(ready[0], artifact_directory)
        _fsync_directory(run_directory)


def _validate_object_layout(run_directory: Path) -> None:
    _ensure_private_directory(run_directory)
    allowed = {"execution-plan.json", "checkpoints", "artifacts", "quarantine"}
    for entry in run_directory.iterdir():
        if entry.name in allowed or entry.name.endswith("-artifacts.staging"):
            continue
        raise P2aError("object run directory contains an unknown entry")
    for name in ("checkpoints", "quarantine"):
        path = run_directory / name
        if path.exists() or path.is_symlink():
            metadata = path.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
                raise P2aError("object run subdirectory is not a real directory")
    plan = run_directory / "execution-plan.json"
    if plan.exists() or plan.is_symlink():
        metadata = plan.lstat()
        if not stat.S_ISREG(metadata.st_mode) or plan.is_symlink():
            raise P2aError("object execution plan is not a regular file")
    artifacts = run_directory / "artifacts"
    if artifacts.exists() or artifacts.is_symlink():
        _validate_object_bundle(artifacts)


def _checkpoint_paths(directory: Path) -> list[Path]:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(metadata.st_mode) or directory.is_symlink():
        raise P2aError("checkpoint path is not a real directory")
    paths = sorted(directory.iterdir(), key=lambda item: item.name)
    for sequence, path in enumerate(paths, 1):
        match = CHECKPOINT_NAME.fullmatch(path.name)
        item = path.lstat()
        if (
            match is None
            or int(match.group("sequence")) != sequence
            or not stat.S_ISREG(item.st_mode)
            or path.is_symlink()
        ):
            raise P2aError("checkpoint directory contains an invalid or orphaned entry")
    return paths


def _validate_checkpoint_transition(
    previous: Mapping[str, Any] | None, current: Mapping[str, Any]
) -> None:
    state = current["state"]
    attempt = current["attempt"]
    if state != "TERMINAL" and current["artifact_hashes"]:
        raise P2aError("non-terminal checkpoint cannot claim completed artifacts")
    if previous is None:
        if state != "PENDING" or attempt != 1 or current["previous_checkpoint_sha256"] is not None:
            raise P2aError("checkpoint chain must begin with initial PENDING attempt 1")
        return
    if current["previous_checkpoint_sha256"] != checkpoint_sha256(previous):
        raise P2aError("checkpoint chain previous hash is invalid")
    previous_state = previous["state"]
    previous_attempt = previous["attempt"]
    if previous_state == "PENDING":
        allowed = state == "RUNNING" and attempt == previous_attempt
    elif previous_state == "RUNNING":
        allowed = state in {"PARTIAL", "INTERRUPTED", "TERMINAL"} and (attempt == previous_attempt)
    elif previous_state in {"PARTIAL", "INTERRUPTED"}:
        allowed = state == "RUNNING" and attempt == previous_attempt + 1
    else:
        allowed = False
    if not allowed:
        raise P2aError(f"invalid persisted checkpoint transition {previous_state} -> {state}")


def _load_checkpoint_chain(
    directory: Path, plan: Mapping[str, Any], work_id: str
) -> list[dict[str, Any]]:
    chain = []
    for path in _checkpoint_paths(directory):
        match = CHECKPOINT_NAME.fullmatch(path.name)
        assert match is not None
        checkpoint = load_checkpoint(path, plan=plan)
        if checkpoint["work_id"] != work_id:
            raise P2aError("checkpoint directory mixes distinct work IDs")
        _validate_checkpoint_transition(chain[-1] if chain else None, checkpoint)
        if checkpoint["attempt"] != int(match.group("attempt")) or checkpoint[
            "state"
        ].casefold() != match.group("state"):
            raise P2aError("checkpoint filename does not bind its state")
        chain.append(checkpoint)
    return chain


def _write_numbered_checkpoint(
    directory: Path, sequence: int, checkpoint: Mapping[str, Any]
) -> None:
    name = (
        f"{sequence:04d}-attempt-{checkpoint['attempt']:04d}-"
        f"{str(checkpoint['state']).casefold()}.json"
    )
    write_checkpoint(directory / name, checkpoint)


def _ensure_running(
    plan: Mapping[str, Any],
    work_id: str,
    checkpoint_directory: Path,
    chain: list[dict[str, Any]],
    *,
    artifacts_ready: bool,
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
    if previous["state"] == "RUNNING" and artifacts_ready:
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
        if (
            previous["state"] == "INTERRUPTED"
            and previous.get("interruption_reason") == "CHILD_NO_STATUS"
            and previous["attempt"] >= MAX_CHILD_NO_STATUS_ATTEMPTS
        ):
            raise ChildNoStatus("isolated child retry budget is exhausted")
        attempt = previous["attempt"] + 1
    else:
        raise P2aError("checkpoint chain cannot resume its current state")
    running = make_stage_checkpoint(
        plan,
        work_id,
        state="RUNNING",
        attempt=attempt,
        previous_checkpoint=previous,
    )
    _write_numbered_checkpoint(checkpoint_directory, sequence, running)
    return running, sequence + 1


def _child_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (CHILD_TIMEOUT_SECONDS, CHILD_TIMEOUT_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (CHILD_ADDRESS_SPACE_BYTES, CHILD_ADDRESS_SPACE_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_FSIZE, (CHILD_OUTPUT_BYTES, CHILD_OUTPUT_BYTES))


def _declared_child_failure(
    source_sha256: str, source_size: int, code: str, diagnostic: str
) -> dict[str, Any]:
    return {
        "schema": AUDIT_SCHEMA,
        "schema_version": "0.1.0",
        "algorithm_id": AUDIT_ALGORITHM,
        "algorithm_version": AUDIT_ALGORITHM_VERSION,
        "source_sha256": source_sha256,
        "source_size_bytes": source_size,
        "external_uri_accessed": False,
        "mvx_operation_accessed": False,
        "complexity_quantile": None,
        "eligibility": "PENDING",
        "split": None,
        "khronos_validation": None,
        "terminal_status": "DECLARED_LIMIT",
        "error_code": code,
        "format_status": "P2A_DIAGNOSTIC_RESOURCE_LIMIT",
        "topology_status": "U",
        "container": None,
        "scene": None,
        "geometry": None,
        "diagnostic": diagnostic,
    }


def _validate_audit_contract(
    value: Mapping[str, Any], source: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    audit = dict(value)
    expected = {
        "schema",
        "schema_version",
        "algorithm_id",
        "algorithm_version",
        "source_sha256",
        "source_size_bytes",
        "external_uri_accessed",
        "mvx_operation_accessed",
        "complexity_quantile",
        "eligibility",
        "split",
        "khronos_validation",
        "terminal_status",
        "error_code",
        "format_status",
        "topology_status",
        "container",
        "scene",
        "geometry",
        "diagnostic",
    }
    if set(audit) != expected:
        raise P2aError("P2a child audit fields are invalid")
    if (
        audit["schema"] != AUDIT_SCHEMA
        or audit["schema_version"] != "0.1.0"
        or audit["algorithm_id"] != AUDIT_ALGORITHM
        or audit["algorithm_version"] != AUDIT_ALGORITHM_VERSION
    ):
        raise P2aError("P2a child audit identity is invalid")
    if not SHA256_PATTERN.fullmatch(str(audit["source_sha256"])) or (
        isinstance(audit["source_size_bytes"], bool)
        or not isinstance(audit["source_size_bytes"], int)
        or audit["source_size_bytes"] < 0
    ):
        raise P2aError("P2a child source identity is invalid")
    if source is not None and (
        audit["source_sha256"] != source["source_sha256"]
        or audit["source_size_bytes"] != source["source_size_bytes"]
    ):
        raise P2aError("P2a child source identity differs from the sealed receipt")
    if (
        audit["external_uri_accessed"] is not False
        or audit["mvx_operation_accessed"] is not False
        or audit["complexity_quantile"] is not None
        or audit["eligibility"] != "PENDING"
        or audit["split"] is not None
    ):
        raise P2aError("P2a child violated the source-only firewall")
    terminal_codes = {
        "DECLARED_LIMIT": {
            "MVX-R001",
            "MVX-R002",
            "MVX-R003",
            "MVX-R004",
            "MVX-G001",
            "MVX-G002",
            "MVX-G003",
        },
        "REJECT": {
            "MVX-I001",
            "MVX-I002",
            "MVX-I003",
            "MVX-I004",
            "MVX-I005",
            "MVX-I006",
            "MVX-I007",
            "MVX-I008",
        },
    }
    status = audit["terminal_status"]
    if status not in terminal_codes or audit["error_code"] not in terminal_codes[status]:
        raise P2aError("P2a child terminal status and MVX code are inconsistent")
    topology = audit["topology_status"]
    if topology not in {"O", "N", "U"}:
        raise P2aError("stdlib P2a child emitted an invalid topology status")
    geometry = audit["geometry"]
    if geometry is not None:
        if not isinstance(geometry, dict):
            raise P2aError("P2a geometry evidence is invalid")
        triangles = geometry.get("triangles_materialised")
        if isinstance(triangles, bool) or not isinstance(triangles, int) or triangles < 0:
            raise P2aError("P2a triangle count is invalid")
        expected_code = {"O": "MVX-G001", "N": "MVX-G002", "U": "MVX-G003"}[topology]
        if (
            audit["format_status"] != "P2A_DIAGNOSTIC_PROFILE_SCAN_COMPLETE"
            or audit["error_code"] != expected_code
        ):
            raise P2aError("P2a geometry evidence has an inconsistent classification")
    else:
        if topology != "U":
            raise P2aError("P2a audit without geometry must remain topology U")
        if status == "REJECT":
            expected_format = "P2A_DIAGNOSTIC_REJECTED"
        elif str(audit["error_code"]).startswith("MVX-R"):
            expected_format = "P2A_DIAGNOSTIC_RESOURCE_LIMIT"
        else:
            expected_format = "P2A_DIAGNOSTIC_DECLARED_LIMIT"
            if audit["error_code"] != "MVX-G003":
                raise P2aError("P2a geometry limit without evidence must be undetermined")
        if audit["format_status"] != expected_format:
            raise P2aError("P2a audit format status is inconsistent")
    for field in ("container", "scene"):
        if audit[field] is not None and not isinstance(audit[field], dict):
            raise P2aError(f"P2a {field} evidence is invalid")
    if audit["khronos_validation"] is not None and not isinstance(
        audit["khronos_validation"], dict
    ):
        raise P2aError("P2a Khronos evidence is invalid")
    if not isinstance(audit["diagnostic"], str) or not audit["diagnostic"]:
        raise P2aError("P2a audit diagnostic is invalid")
    return audit


def _run_child(
    source_path: Path, source: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": str(SOURCE_ROOT),
        "TZ": "UTC",
    }
    command = (
        sys.executable,
        str(Path(__file__).resolve()),
        "_child-audit",
        "--source",
        str(source_path),
        "--expected-sha256",
        str(source["source_sha256"]),
        "--expected-bytes",
        str(source["source_size_bytes"]),
    )
    try:
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            preexec_fn=_child_limits,
            timeout=CHILD_TIMEOUT_SECONDS + 5,
        )
    except subprocess.TimeoutExpired:
        audit = _declared_child_failure(
            str(source["source_sha256"]),
            int(source["source_size_bytes"]),
            "MVX-R002",
            "ISOLATED_CHILD_TIMEOUT",
        )
        return audit, {"child_exit": "TIMEOUT", "stderr_sha256": None}
    if len(completed.stdout) > CHILD_OUTPUT_BYTES or len(completed.stderr) > CHILD_OUTPUT_BYTES:
        audit = _declared_child_failure(
            str(source["source_sha256"]),
            int(source["source_size_bytes"]),
            "MVX-R003",
            "ISOLATED_CHILD_OUTPUT_LIMIT",
        )
        return audit, {
            "child_exit": "OUTPUT_LIMIT",
            "stderr_sha256": _sha256_bytes(completed.stderr),
        }
    if completed.returncode != 0:
        raise ChildNoStatus(
            "isolated P2a child exited without a valid terminal status "
            f"(returncode={completed.returncode}, stderr_sha256={_sha256_bytes(completed.stderr)})"
        )
    try:
        audit = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ChildNoStatus("P2a child emitted invalid JSON") from error
    if not isinstance(audit, dict):
        raise ChildNoStatus("P2a child audit must be a JSON object")
    try:
        audit = _validate_audit_contract(audit, source)
    except P2aError as error:
        raise ChildNoStatus("P2a child emitted an invalid audit contract") from error
    return audit, {
        "child_exit": "ZERO",
        "stderr_sha256": _sha256_bytes(completed.stderr),
    }


def _artifact_payloads(
    source: Mapping[str, Any],
    audit: Mapping[str, Any],
    child_evidence: Mapping[str, Any],
    *,
    work_id: str,
    code_commit: str,
    code_tree: str,
) -> dict[str, bytes]:
    audit = _validate_audit_contract(audit, source)
    source_receipt = {
        "schema": "MVX-P2A-PRIVATE-SOURCE-RECEIPT",
        "schema_version": "0.1.0",
        **dict(source),
    }
    audit_record = {
        "schema": "MVX-P2A-PRIVATE-AUDIT-RECORD",
        "schema_version": "0.1.0",
        "work_id": work_id,
        "candidate_commitment_sha256": source["candidate_commitment_sha256"],
        "code_git_commit_sha1": code_commit,
        "code_git_tree_sha1": code_tree,
        "audit": audit,
    }
    parser_evidence = {
        "schema": "MVX-P2A-PARSER-EVIDENCE",
        "schema_version": "0.1.0",
        "algorithm_id": AUDIT_ALGORITHM,
        "khronos_validation": audit.get("khronos_validation"),
        "container": audit.get("container"),
        "scene": audit.get("scene"),
        "geometry": audit.get("geometry"),
        "diagnostic": audit.get("diagnostic"),
    }
    resource_evidence = {
        "schema": "MVX-P2A-RESOURCE-EVIDENCE",
        "schema_version": "0.1.0",
        "limits": {
            "address_space_bytes": CHILD_ADDRESS_SPACE_BYTES,
            "max_accessor_count": MAX_ACCESSOR_COUNT,
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_triangles": MAX_TRIANGLES,
            "timeout_seconds": CHILD_TIMEOUT_SECONDS,
        },
        **dict(child_evidence),
    }
    return {
        "source_receipt": _json_document(source_receipt),
        "audit_record": _json_document(audit_record),
        "parser_evidence": _json_document(parser_evidence),
        "resource_evidence": _json_document(resource_evidence),
    }


def _validated_object_audit(
    artifact_directory: Path,
    source: Mapping[str, Any],
    work_id: str,
    terminal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not _validate_object_bundle(artifact_directory):
        raise P2aError("object artifact bundle is not complete")
    source_receipt = _load_json_bytes(
        _read_regular_bytes(
            artifact_directory / OBJECT_ARTIFACT_FILES["source_receipt"],
            label="private source receipt",
        ),
        label="private source receipt",
    )
    expected_source_receipt = {
        "schema": "MVX-P2A-PRIVATE-SOURCE-RECEIPT",
        "schema_version": "0.1.0",
        **dict(source),
    }
    if source_receipt != expected_source_receipt:
        raise P2aError("object source receipt differs from the sealed audit plan")
    audit_record = _load_json_bytes(
        _read_regular_bytes(
            artifact_directory / OBJECT_ARTIFACT_FILES["audit_record"],
            label="private audit record",
        ),
        label="private audit record",
    )
    if set(audit_record) != {
        "schema",
        "schema_version",
        "work_id",
        "candidate_commitment_sha256",
        "code_git_commit_sha1",
        "code_git_tree_sha1",
        "audit",
    }:
        raise P2aError("private audit record fields are invalid")
    if (
        audit_record["schema"] != "MVX-P2A-PRIVATE-AUDIT-RECORD"
        or audit_record["schema_version"] != "0.1.0"
        or audit_record["work_id"] != work_id
        or audit_record["candidate_commitment_sha256"] != source["candidate_commitment_sha256"]
        or not re.fullmatch(r"[0-9a-f]{40}", str(audit_record["code_git_commit_sha1"]))
        or not re.fullmatch(r"[0-9a-f]{40}", str(audit_record["code_git_tree_sha1"]))
        or not isinstance(audit_record["audit"], dict)
    ):
        raise P2aError("private audit record identity is invalid")
    audit = _validate_audit_contract(audit_record["audit"], source)
    if terminal is not None and (
        terminal.get("terminal_status") != audit["terminal_status"]
        or terminal.get("error_code") != audit["error_code"]
    ):
        raise P2aError("terminal checkpoint disagrees with its bound audit record")
    parser = _load_json_bytes(
        _read_regular_bytes(
            artifact_directory / OBJECT_ARTIFACT_FILES["parser_evidence"],
            label="parser evidence",
        ),
        label="parser evidence",
    )
    if parser != {
        "schema": "MVX-P2A-PARSER-EVIDENCE",
        "schema_version": "0.1.0",
        "algorithm_id": AUDIT_ALGORITHM,
        "khronos_validation": audit["khronos_validation"],
        "container": audit["container"],
        "scene": audit["scene"],
        "geometry": audit["geometry"],
        "diagnostic": audit["diagnostic"],
    }:
        raise P2aError("parser evidence differs from the audit record")
    return audit


def _terminal_from_existing_artifacts(
    plan: Mapping[str, Any],
    work_id: str,
    source: Mapping[str, Any],
    checkpoint_directory: Path,
    running: Mapping[str, Any],
    next_sequence: int,
    artifact_directory: Path,
) -> dict[str, Any]:
    audit = _validated_object_audit(artifact_directory, source, work_id)
    terminal_status = audit.get("terminal_status")
    error_code = audit.get("error_code")
    if terminal_status not in {"PASS", "DECLARED_LIMIT", "REJECT", "FAIL"}:
        raise P2aError("existing audit terminal status is invalid")
    if not isinstance(error_code, str) or not error_code:
        raise P2aError("existing audit error code is invalid")
    artifact_hashes = {
        name: hash_artifact(path)
        for name, path in _object_artifact_paths(artifact_directory).items()
    }
    terminal = make_stage_checkpoint(
        plan,
        work_id,
        state="TERMINAL",
        attempt=running["attempt"],
        terminal_status=terminal_status,
        error_code=error_code,
        artifact_hashes=artifact_hashes,
        previous_checkpoint=running,
    )
    _write_numbered_checkpoint(checkpoint_directory, next_sequence, terminal)
    return terminal


def _execute_object(
    source: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    cache_root: Path,
    object_root: Path,
    lock_root: Path,
    code_identity: tuple[str, str, str],
    environment_sha256: str,
) -> dict[str, Any]:
    code_sha256, code_commit, code_tree = code_identity
    plan, work_id = _make_object_plan(source, profile, code_sha256, environment_sha256)
    run_directory = object_root / work_id
    _ensure_private_directory(run_directory)
    with _exclusive_lock(lock_root, work_id):
        _validate_object_layout(run_directory)
        plan_path = run_directory / "execution-plan.json"
        checkpoint_directory = run_directory / "checkpoints"
        artifact_directory = run_directory / "artifacts"
        _publish_bytes_once(plan_path, _json_document(plan))
        _ensure_private_directory(checkpoint_directory)
        _recover_staging(run_directory, artifact_directory)
        chain = _load_checkpoint_chain(checkpoint_directory, plan, work_id)
        if chain and chain[-1]["state"] == "TERMINAL":
            assessment = assess_resume(
                plan,
                work_id,
                checkpoint=chain[-1],
                artifact_paths=_object_artifact_paths(artifact_directory),
            )
            if assessment.action is not ResumeAction.SKIP:
                raise P2aError("terminal P2a object is not safely resumable")
            audit = _validated_object_audit(artifact_directory, source, work_id, terminal=chain[-1])
            return {
                "action": "SKIP",
                "work_id": work_id,
                "terminal_checkpoint_sha256": checkpoint_sha256(chain[-1]),
                "audit": audit,
            }

        artifacts_ready = _validate_object_bundle(artifact_directory)
        running, next_sequence = _ensure_running(
            plan,
            work_id,
            checkpoint_directory,
            chain,
            artifacts_ready=artifacts_ready,
        )
        if artifacts_ready:
            terminal = _terminal_from_existing_artifacts(
                plan,
                work_id,
                source,
                checkpoint_directory,
                running,
                next_sequence,
                artifact_directory,
            )
            audit = _validated_object_audit(artifact_directory, source, work_id, terminal=terminal)
            return {
                "action": "RECOVERED",
                "work_id": work_id,
                "terminal_checkpoint_sha256": checkpoint_sha256(terminal),
                "audit": audit,
            }

        source_path = _cache_path(cache_root, str(source["source_sha256"]))
        try:
            audit, child_evidence = _run_child(source_path, source)
        except ChildNoStatus:
            interrupted = make_stage_checkpoint(
                plan,
                work_id,
                state="INTERRUPTED",
                attempt=running["attempt"],
                error_code="MVX-X002",
                interruption_reason="CHILD_NO_STATUS",
                previous_checkpoint=running,
            )
            _write_numbered_checkpoint(checkpoint_directory, next_sequence, interrupted)
            raise
        payloads = _artifact_payloads(
            source,
            audit,
            child_evidence,
            work_id=work_id,
            code_commit=code_commit,
            code_tree=code_tree,
        )
        _publish_object_bundle(run_directory, artifact_directory, payloads, int(running["attempt"]))
        if _runtime_code_identity() != code_identity:
            raise P2aError("code or Git identity changed before terminal publication")
        terminal = _terminal_from_existing_artifacts(
            plan,
            work_id,
            source,
            checkpoint_directory,
            running,
            next_sequence,
            artifact_directory,
        )
        assessment = assess_resume(
            plan,
            work_id,
            checkpoint=terminal,
            artifact_paths=_object_artifact_paths(artifact_directory),
        )
        if assessment.action is not ResumeAction.SKIP:
            raise P2aError("new P2a object terminal checkpoint does not verify")
        return {
            "action": "COMPLETED",
            "work_id": work_id,
            "terminal_checkpoint_sha256": checkpoint_sha256(terminal),
            "audit": audit,
        }


def _campaign_payloads(
    results: Sequence[Mapping[str, Any]],
    audit_plan: Mapping[str, Any],
    code_identity: tuple[str, str, str],
    environment_sha256: str,
) -> tuple[str, dict[str, bytes]]:
    code_sha256, code_commit, code_tree = code_identity
    sources = audit_plan.get("sources")
    profile = audit_plan.get("profile")
    if (
        not isinstance(sources, list)
        or not isinstance(profile, dict)
        or len(results) != len(sources)
        or not results
    ):
        raise P2aError("campaign results do not match the sealed source scope")
    seen_work_ids: set[str] = set()
    seen_terminal_hashes: set[str] = set()
    for result, source in zip(results, sources, strict=True):
        _, expected_work_id = _make_object_plan(source, profile, code_sha256, environment_sha256)
        work_id = str(result.get("work_id"))
        terminal_hash = str(result.get("terminal_checkpoint_sha256"))
        if work_id != expected_work_id:
            raise P2aError("campaign result work ID differs from its sealed source")
        if work_id in seen_work_ids or terminal_hash in seen_terminal_hashes:
            raise P2aError("campaign repeats a work ID or terminal checkpoint")
        seen_work_ids.add(work_id)
        seen_terminal_hashes.add(terminal_hash)
    terminal_rows = sorted(
        (
            {
                "work_id": result["work_id"],
                "terminal_checkpoint_sha256": result["terminal_checkpoint_sha256"],
            }
            for result in results
        ),
        key=lambda row: row["work_id"],
    )
    scope_commitment = _canonical_hash(terminal_rows)
    audits = [
        _validate_audit_contract(result["audit"], source)
        for result, source in zip(results, sources, strict=True)
    ]
    terminal_counts = Counter(str(audit["terminal_status"]) for audit in audits)
    format_counts = Counter(str(audit["format_status"]) for audit in audits)
    topology_counts = Counter(str(audit["topology_status"]) for audit in audits)
    fully_materialised = [audit for audit in audits if audit.get("geometry") is not None]
    total_triangles = sum(
        int(audit["geometry"]["triangles_materialised"]) for audit in fully_materialised
    )
    aggregate_evidence = {
        "terminal_status_counts": dict(sorted(terminal_counts.items())),
        "format_status_counts": dict(sorted(format_counts.items())),
        "topology_status_counts": dict(sorted(topology_counts.items())),
        "fully_materialised_source_count": len(fully_materialised),
        "aggregate_materialised_triangles": total_triangles,
        "solid_certification_count": topology_counts.get("V", 0),
    }
    private_manifest = {
        "schema": "MVX-P2A-PRIVATE-CAMPAIGN-MANIFEST",
        "schema_version": "0.2.0",
        "campaign_kind": "ENGINEERING_P2A_SOURCE_ONLY_NONSTATISTICAL",
        "protocol_root_sha256": P0_ROOT,
        "scope_commitment_sha256": scope_commitment,
        "audit_plan_sha256": _canonical_hash(audit_plan),
        "code_sha256": code_sha256,
        "environment_sha256": environment_sha256,
        "terminal_objects": terminal_rows,
        "sources": [dict(source) for source in sources],
        "aggregate_evidence": aggregate_evidence,
    }
    public_summary = {
        "schema": "MVX-P2A-DIAGNOSTIC-PILOT-SUMMARY",
        "schema_version": "0.2.0",
        "algorithm_id": AUDIT_ALGORITHM,
        "algorithm_version": AUDIT_ALGORITHM_VERSION,
        "script_version": SCRIPT_VERSION,
        "campaign_kind": "ENGINEERING_P2A_SOURCE_ONLY_NONSTATISTICAL",
        "protocol_root_sha256": P0_ROOT,
        "code_sha256": code_sha256,
        "code_git_commit_sha1": code_commit,
        "code_git_tree_sha1": code_tree,
        "scope_commitment_sha256": scope_commitment,
        "private_manifest_commitment_sha256": _canonical_hash(private_manifest),
        "source_count": len(audits),
        "terminal_status_counts": aggregate_evidence["terminal_status_counts"],
        "format_status_counts": aggregate_evidence["format_status_counts"],
        "topology_status_counts": aggregate_evidence["topology_status_counts"],
        "fully_materialised_source_count": aggregate_evidence["fully_materialised_source_count"],
        "aggregate_materialised_triangles": aggregate_evidence["aggregate_materialised_triangles"],
        "solid_certification_count": aggregate_evidence["solid_certification_count"],
        "solid_verifier": "NOT_AVAILABLE_NEVER_EMIT_V",
        "constraints": {
            "cohort_selected": False,
            "complexity_quantile_frozen": False,
            "eligibility": "PENDING",
            "mvx_outcome_accessed": False,
            "split_created": False,
        },
        "privacy": {
            "drive_ids_published": False,
            "objaverse_uids_published": False,
            "per_object_source_hashes_published": False,
            "source_paths_published": False,
            "work_ids_published": False,
        },
        "gate_effect": "P2A_DIAGNOSTIC_ONLY_G1_REMAINS_BLOCKED",
    }
    private_payload = _json_document(private_manifest)
    public_payload = _json_document(public_summary)
    completed = {
        "schema": "MVX-P2A-CAMPAIGN-COMPLETED",
        "schema_version": "0.2.0",
        "scope_commitment_sha256": scope_commitment,
        "private_manifest_sha256": _sha256_bytes(private_payload),
        "public_summary_sha256": _sha256_bytes(public_payload),
        "object_terminal_count": len(terminal_rows),
    }
    return scope_commitment, {
        "private-manifest.json": private_payload,
        "public-summary.json": public_payload,
        "COMPLETED.json": _json_document(completed),
    }


def _validate_campaign_bundle(directory: Path, payloads: Mapping[str, bytes] | None = None) -> bool:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or directory.is_symlink():
        raise P2aError("campaign bundle is not a real directory")
    entries = {entry.name: entry for entry in directory.iterdir()}
    if set(entries) != CAMPAIGN_FILES:
        raise P2aError("campaign bundle is partial or contains extras")
    for entry in entries.values():
        item = entry.lstat()
        if not stat.S_ISREG(item.st_mode) or entry.is_symlink():
            raise P2aError("campaign bundle contains a non-regular entry")
    current = {
        name: _read_regular_bytes(path, label="campaign artifact") for name, path in entries.items()
    }
    private = _load_json_bytes(current["private-manifest.json"], label="private campaign manifest")
    public = _load_json_bytes(current["public-summary.json"], label="public campaign summary")
    completed = _load_json_bytes(current["COMPLETED.json"], label="campaign marker")
    if (
        set(completed)
        != {
            "schema",
            "schema_version",
            "scope_commitment_sha256",
            "private_manifest_sha256",
            "public_summary_sha256",
            "object_terminal_count",
        }
        or completed.get("schema") != "MVX-P2A-CAMPAIGN-COMPLETED"
        or completed.get("schema_version") != "0.2.0"
    ):
        raise P2aError("campaign terminal marker contract is invalid")
    if completed.get("private_manifest_sha256") != _sha256_bytes(
        current["private-manifest.json"]
    ) or completed.get("public_summary_sha256") != _sha256_bytes(current["public-summary.json"]):
        raise P2aError("campaign terminal marker does not bind its artifacts")
    private_fields = {
        "schema",
        "schema_version",
        "campaign_kind",
        "protocol_root_sha256",
        "scope_commitment_sha256",
        "audit_plan_sha256",
        "code_sha256",
        "environment_sha256",
        "terminal_objects",
        "sources",
        "aggregate_evidence",
    }
    if (
        set(private) != private_fields
        or private.get("schema") != "MVX-P2A-PRIVATE-CAMPAIGN-MANIFEST"
        or private.get("schema_version") != "0.2.0"
    ):
        raise P2aError("private campaign manifest contract is invalid")
    for field in (
        "protocol_root_sha256",
        "scope_commitment_sha256",
        "audit_plan_sha256",
        "code_sha256",
        "environment_sha256",
    ):
        if not SHA256_PATTERN.fullmatch(str(private.get(field))):
            raise P2aError(f"private campaign {field} is invalid")
    if (
        private["protocol_root_sha256"] != P0_ROOT
        or private["campaign_kind"] != "ENGINEERING_P2A_SOURCE_ONLY_NONSTATISTICAL"
    ):
        raise P2aError("private campaign constants are invalid")
    terminal_objects = private.get("terminal_objects")
    sources = private.get("sources")
    if not isinstance(terminal_objects, list) or not isinstance(sources, list):
        raise P2aError("campaign terminal objects or sources are invalid")
    if len(terminal_objects) != len(sources) or len(terminal_objects) < 1:
        raise P2aError("campaign object counts are inconsistent")
    for row in terminal_objects:
        if not isinstance(row, dict) or set(row) != {
            "work_id",
            "terminal_checkpoint_sha256",
        }:
            raise P2aError("campaign terminal row contract is invalid")
        if not SHA256_PATTERN.fullmatch(str(row["work_id"])) or not SHA256_PATTERN.fullmatch(
            str(row["terminal_checkpoint_sha256"])
        ):
            raise P2aError("campaign terminal row commitment is invalid")
    if len({row["work_id"] for row in terminal_objects}) != len(terminal_objects) or len(
        {row["terminal_checkpoint_sha256"] for row in terminal_objects}
    ) != len(terminal_objects):
        raise P2aError("campaign repeats a work ID or terminal checkpoint")
    if terminal_objects != sorted(terminal_objects, key=lambda row: row["work_id"]):
        raise P2aError("campaign terminal rows are not canonical")
    scope = _canonical_hash(terminal_objects)
    if (
        private.get("scope_commitment_sha256") != scope
        or completed.get("scope_commitment_sha256") != scope
    ):
        raise P2aError("campaign scope commitment is inconsistent")
    count = len(terminal_objects)
    if completed.get("object_terminal_count") != count:
        raise P2aError("campaign terminal count is inconsistent")
    public_fields = {
        "schema",
        "schema_version",
        "algorithm_id",
        "algorithm_version",
        "script_version",
        "campaign_kind",
        "protocol_root_sha256",
        "code_sha256",
        "code_git_commit_sha1",
        "code_git_tree_sha1",
        "scope_commitment_sha256",
        "private_manifest_commitment_sha256",
        "source_count",
        "terminal_status_counts",
        "format_status_counts",
        "topology_status_counts",
        "fully_materialised_source_count",
        "aggregate_materialised_triangles",
        "solid_certification_count",
        "solid_verifier",
        "constraints",
        "privacy",
        "gate_effect",
    }
    if (
        set(public) != public_fields
        or public.get("schema") != "MVX-P2A-DIAGNOSTIC-PILOT-SUMMARY"
        or public.get("schema_version") != "0.2.0"
    ):
        raise P2aError("public campaign summary identity is invalid")
    if (
        public.get("algorithm_id") != AUDIT_ALGORITHM
        or public.get("algorithm_version") != AUDIT_ALGORITHM_VERSION
        or public.get("script_version") != SCRIPT_VERSION
        or public.get("campaign_kind") != "ENGINEERING_P2A_SOURCE_ONLY_NONSTATISTICAL"
        or public.get("solid_verifier") != "NOT_AVAILABLE_NEVER_EMIT_V"
        or public.get("protocol_root_sha256") != P0_ROOT
        or not re.fullmatch(r"[0-9a-f]{40}", str(public.get("code_git_commit_sha1")))
        or not re.fullmatch(r"[0-9a-f]{40}", str(public.get("code_git_tree_sha1")))
        or not SHA256_PATTERN.fullmatch(str(public.get("code_sha256")))
        or not SHA256_PATTERN.fullmatch(str(public.get("private_manifest_commitment_sha256")))
    ):
        raise P2aError("public campaign constants are invalid")
    if public.get("scope_commitment_sha256") != scope or public.get("source_count") != count:
        raise P2aError("public campaign scope is inconsistent")
    if public.get("private_manifest_commitment_sha256") != _canonical_hash(private):
        raise P2aError("public campaign summary does not bind the private manifest")
    if public.get("protocol_root_sha256") != private.get("protocol_root_sha256") or public.get(
        "code_sha256"
    ) != private.get("code_sha256"):
        raise P2aError("campaign public/private code identity is inconsistent")
    if public.get("solid_certification_count") != 0:
        raise P2aError("stdlib campaign may not contain a solid certification")
    aggregate = private.get("aggregate_evidence")
    aggregate_fields = {
        "terminal_status_counts",
        "format_status_counts",
        "topology_status_counts",
        "fully_materialised_source_count",
        "aggregate_materialised_triangles",
        "solid_certification_count",
    }
    if not isinstance(aggregate, dict) or set(aggregate) != aggregate_fields:
        raise P2aError("private campaign aggregate evidence is invalid")
    for field in (
        "fully_materialised_source_count",
        "aggregate_materialised_triangles",
        "solid_certification_count",
    ):
        value = aggregate[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise P2aError(f"private campaign {field} is invalid")
        if public.get(field) != value:
            raise P2aError(f"public campaign {field} differs from private evidence")
    if aggregate["fully_materialised_source_count"] > count:
        raise P2aError("campaign materialised source count exceeds its scope")
    if public.get("privacy") != {
        "drive_ids_published": False,
        "objaverse_uids_published": False,
        "per_object_source_hashes_published": False,
        "source_paths_published": False,
        "work_ids_published": False,
    }:
        raise P2aError("public campaign privacy declaration is invalid")
    if (
        public.get("constraints")
        != {
            "cohort_selected": False,
            "complexity_quantile_frozen": False,
            "eligibility": "PENDING",
            "mvx_outcome_accessed": False,
            "split_created": False,
        }
        or public.get("gate_effect") != "P2A_DIAGNOSTIC_ONLY_G1_REMAINS_BLOCKED"
    ):
        raise P2aError("public campaign constraints are invalid")
    for field in ("terminal_status_counts", "format_status_counts", "topology_status_counts"):
        counts = aggregate.get(field)
        if (
            not isinstance(counts, dict)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in counts.values()
            )
            or sum(counts.values()) != count
        ):
            raise P2aError(f"private campaign {field} is inconsistent")
        if public.get(field) != counts:
            raise P2aError(f"public campaign {field} differs from private evidence")
    private_tokens: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise P2aError("campaign source receipt is invalid")
        for value in source.values():
            if isinstance(value, str) and len(value) >= 12:
                private_tokens.add(value)
    for row in terminal_objects:
        private_tokens.update(str(value) for value in row.values())
    public_text = current["public-summary.json"].decode("utf-8")
    if any(token in public_text for token in private_tokens):
        raise P2aError("public campaign summary exposes a private per-object token")
    if payloads is not None and dict(payloads) != current:
        raise P2aError("existing campaign conflicts with deterministic recomputation")
    return True


def _quarantine_campaign_staging(campaign_root: Path, staging: Path, scope_commitment: str) -> Path:
    quarantine = campaign_root / "quarantine"
    _ensure_private_directory(quarantine)
    for sequence in range(1, 10000):
        target = quarantine / f"{scope_commitment}-staging-{sequence:04d}"
        try:
            target.lstat()
        except FileNotFoundError:
            os.rename(staging, target)
            _fsync_directory(quarantine)
            _fsync_directory(campaign_root)
            return target
    raise P2aError("campaign quarantine namespace is exhausted")


def _publish_campaign(
    campaign_root: Path, scope_commitment: str, payloads: Mapping[str, bytes]
) -> str:
    campaign = campaign_root / scope_commitment
    with _exclusive_lock(campaign_root / "locks", scope_commitment):
        if _validate_campaign_bundle(campaign):
            existing_private = _read_regular_bytes(
                campaign / "private-manifest.json", label="existing private campaign manifest"
            )
            if existing_private != payloads["private-manifest.json"]:
                raise P2aError(
                    "existing campaign private identity conflicts with current terminals"
                )
            existing_public = _load_json_bytes(
                _read_regular_bytes(
                    campaign / "public-summary.json", label="existing public campaign summary"
                ),
                label="existing public campaign summary",
            )
            expected_public = _load_json_bytes(
                payloads["public-summary.json"], label="expected public campaign summary"
            )
            for field in ("code_git_commit_sha1", "code_git_tree_sha1"):
                existing_public.pop(field, None)
                expected_public.pop(field, None)
            if existing_public != expected_public:
                raise P2aError(
                    "existing public campaign summary differs from deterministic evidence"
                )
            return "SKIP"
        staging = campaign_root / f"{scope_commitment}.staging"
        try:
            staging.lstat()
        except FileNotFoundError:
            pass
        else:
            try:
                complete_staging = _validate_campaign_bundle(staging)
            except P2aError:
                _quarantine_campaign_staging(campaign_root, staging, scope_commitment)
            else:
                if complete_staging:
                    existing_private = _read_regular_bytes(
                        staging / "private-manifest.json",
                        label="staged private campaign manifest",
                    )
                    if existing_private != payloads["private-manifest.json"]:
                        raise P2aError(
                            "staged campaign private identity conflicts with current terminals"
                        )
                    os.rename(staging, campaign)
                    _fsync_directory(campaign_root)
                    return "RECOVERED"
        os.mkdir(staging, 0o700)
        _fsync_directory(campaign_root)
        for name in ("private-manifest.json", "public-summary.json", "COMPLETED.json"):
            _publish_bytes_once(staging / name, payloads[name])
        _validate_campaign_bundle(staging, payloads)
        os.rename(staging, campaign)
        _fsync_directory(campaign_root)
        return "COMPLETED"


def run_campaign(arguments: argparse.Namespace) -> dict[str, Any]:
    _verified_protocol_root()
    audit_payload = _read_regular_bytes(
        Path(os.path.abspath(arguments.audit_plan)), label="private P2a audit plan"
    )
    audit_plan = _validate_audit_plan(
        _load_json_bytes(audit_payload, label="private P2a audit plan")
    )
    if _canonical_hash(audit_plan) != arguments.audit_plan_sha256:
        raise P2aError("P2a audit plan differs from its commitment")
    cache_root = _private_path(arguments.cache_root, create_directory=True)
    run_root = _private_path(arguments.run_root, create_directory=True)
    lock_root = run_root / "locks"
    object_root = run_root / "objects"
    campaign_root = run_root / "campaigns"
    for directory in (lock_root, object_root, campaign_root):
        _ensure_private_directory(directory)
    code_identity = _runtime_code_identity()
    environment = _environment_sha256()
    results = [
        _execute_object(
            source,
            audit_plan["profile"],
            cache_root=cache_root,
            object_root=object_root,
            lock_root=lock_root,
            code_identity=code_identity,
            environment_sha256=environment,
        )
        for source in audit_plan["sources"]
    ]
    if _runtime_code_identity() != code_identity:
        raise P2aError("code or Git identity changed before campaign publication")
    scope, payloads = _campaign_payloads(results, audit_plan, code_identity, environment)
    campaign_action = _publish_campaign(campaign_root, scope, payloads)
    published_public = _read_regular_bytes(
        campaign_root / scope / "public-summary.json", label="published public campaign summary"
    )
    object_actions = Counter(str(result["action"]) for result in results)
    return {
        "action": "SKIP"
        if campaign_action == "SKIP" and object_actions == {"SKIP": len(results)}
        else "COMPLETED",
        "source_count": len(results),
        "object_actions": dict(sorted(object_actions.items())),
        "campaign_action": campaign_action,
        "scope_commitment_sha256": scope,
        "public_summary_sha256": _sha256_bytes(published_public),
        "public_summary_locator": f"PRIVATE_CHECKPOINT_STORE/campaigns/{scope}/public-summary.json",
        "private_identity_published": False,
        "mvx_outcome_accessed": False,
    }


def child_audit(arguments: argparse.Namespace) -> dict[str, Any]:
    source = Path(os.path.abspath(arguments.source))
    payload = _read_regular_bytes(source, label="child GLB source", maximum=MAX_SOURCE_BYTES)
    if len(payload) != arguments.expected_bytes:
        raise P2aError("child source size differs from its sealed receipt")
    if _sha256_bytes(payload) != arguments.expected_sha256:
        raise P2aError("child source hash differs from its sealed receipt")
    return audit_glb_bytes(payload)


def _build_test_glb(
    positions: Sequence[tuple[float, float, float]], indices: Sequence[int]
) -> bytes:
    if not positions:
        raise ValueError("test GLB requires at least one position")
    position_bytes = b"".join(struct.pack("<fff", *position) for position in positions)
    index_offset = (len(position_bytes) + 3) & ~3
    binary = position_bytes + b"\x00" * (index_offset - len(position_bytes))
    binary += b"".join(struct.pack("<H", index) for index in indices)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes)},
            {
                "buffer": 0,
                "byteOffset": index_offset,
                "byteLength": len(indices) * 2,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(positions),
                "type": "VEC3",
                "min": [min(point[axis] for point in positions) for axis in range(3)],
                "max": [max(point[axis] for point in positions) for axis in range(3)],
            },
            {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    json_bytes = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    return (
        struct.pack("<4sII", GLB_MAGIC, 2, total)
        + struct.pack("<II", len(json_bytes), JSON_CHUNK)
        + json_bytes
        + struct.pack("<II", len(binary), BIN_CHUNK)
        + binary
    )


def self_test() -> dict[str, Any]:
    open_triangle = _build_test_glb([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [0, 1, 2])
    open_result = audit_glb_bytes(open_triangle)
    if open_result["topology_status"] != "O":
        raise P2aError("self-test open surface was not classified O")
    tetra = _build_test_glb(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
        [0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3],
    )
    tetra_result = audit_glb_bytes(tetra)
    if tetra_result["topology_status"] != "U":
        raise P2aError("self-test closed mesh must remain U without a solid verifier")
    invalid = audit_glb_bytes(b"not a glb")
    if invalid["terminal_status"] != "REJECT":
        raise P2aError("self-test invalid GLB was not rejected")
    return {
        "status": "PASS",
        "checks": 3,
        "solid_certification_count": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    pilot = commands.add_parser("make-pilot", help="freeze the private HMAC-ranked pilot")
    pilot.add_argument("--snapshot", required=True)
    pilot.add_argument("--snapshot-sha256", required=True)
    pilot.add_argument("--count", type=int, default=DEFAULT_SCOPE_COUNT)
    pilot.add_argument("--output", required=True)

    seal = commands.add_parser("seal-sources", help="hash and content-address pilot sources")
    seal.add_argument("--pilot-plan", required=True)
    seal.add_argument("--pilot-plan-sha256", required=True)
    seal.add_argument("--incoming", required=True)
    seal.add_argument("--cache-root", required=True)
    seal.add_argument("--output", required=True)

    run = commands.add_parser("run", help="audit every planned source with restart guards")
    run.add_argument("--audit-plan", required=True)
    run.add_argument("--audit-plan-sha256", required=True)
    run.add_argument("--cache-root", required=True)
    run.add_argument("--run-root", required=True)

    child = commands.add_parser("_child-audit")
    child.add_argument("--source", required=True)
    child.add_argument("--expected-sha256", required=True)
    child.add_argument("--expected-bytes", required=True, type=int)

    commands.add_parser("self-test")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "make-pilot":
            result = make_pilot(arguments)
        elif arguments.command == "seal-sources":
            result = seal_sources(arguments)
        elif arguments.command == "run":
            result = run_campaign(arguments)
        elif arguments.command == "_child-audit":
            result = child_audit(arguments)
        else:
            result = self_test()
    except Exception as error:  # noqa: BLE001 - fail closed with path-free diagnostics
        diagnostic = _sha256_bytes(f"{type(error).__name__}:{error}".encode())
        error_code = getattr(error, "error_code", "MVX-X001")
        print(
            json.dumps(
                {
                    "action": "FAIL_CLOSED",
                    "error_code": error_code,
                    "diagnostic_sha256": diagnostic,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
