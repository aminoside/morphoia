"""Crash-safe publication of the private and released G1 freeze bundles."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable, Mapping
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .custody import (
    canonical_json_bytes,
    sha256_hex,
    validate_custody_precommit,
    validate_precommit_publication_receipt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIRECTORY = PROJECT_ROOT / "schemas" / "mvx" / "0.2.1"
BUNDLE_ALGORITHM_ID = "MVX-G1-BUNDLE-SHA256-1"
RECEIPT_ALGORITHM_ID = "MVX-G1-TWO-PHASE-COMMIT-1"


class FreezeArtifactError(RuntimeError):
    """Raised when a freeze transaction cannot be safely resumed or committed."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: Any) -> bytes:
    """Deterministic JSON bytes for artifacts that may contain finite floats."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _jsonl_bytes(records: Any) -> bytes:
    return b"".join(_json_bytes(record) for record in records)


def _validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIRECTORY / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_frozen_output_schemas(frozen: Any) -> None:
    """Validate every materialized freeze artifact before filesystem publication."""

    objects = (
        ("selection-manifest.schema.json", frozen.selection_manifest),
        ("split.schema.json", frozen.private_split),
        ("custody-public.schema.json", frozen.custody_public),
        ("custody-visible.schema.json", frozen.custody_visible),
        ("milestone-manifest.schema.json", frozen.milestone_manifest),
    )
    for schema_name, value in objects:
        try:
            _validator(schema_name).validate(value)
        except Exception as error:
            raise FreezeArtifactError(f"{schema_name} validation failed: {error}") from error
    record_validator = _validator("frozen-record.schema.json")
    for collection_name, records in (
        ("selected_records", frozen.selected_records),
        ("reserve_records", frozen.reserve_records),
    ):
        for index, record in enumerate(records):
            try:
                record_validator.validate(record)
            except Exception as error:
                raise FreezeArtifactError(
                    f"{collection_name}[{index}] schema validation failed: {error}"
                ) from error


def _manifest(
    *,
    bundle_kind: str,
    freeze_id: str,
    protocol_root_sha256: str,
    precommit_sha256: str,
    files: Mapping[str, bytes],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "algorithm_id": BUNDLE_ALGORITHM_ID,
        "bundle_kind": bundle_kind,
        "freeze_id": freeze_id,
        "protocol_root_sha256": protocol_root_sha256,
        "precommit_sha256": precommit_sha256,
        "files": {
            name: {"sha256": _sha256_bytes(payload), "size_bytes": len(payload)}
            for name, payload in sorted(files.items())
        },
        "state": "PREPARED",
    }


def build_freeze_bundle_payloads(
    frozen: Any,
    precommit: Mapping[str, Any],
    publication_receipt: Mapping[str, Any],
) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, Any], dict[str, Any]]:
    """Return schema-validated, byte-exact private and release bundle payloads."""

    validated_precommit = validate_custody_precommit(precommit)
    try:
        _validator("precommit-publication-receipt.schema.json").validate(publication_receipt)
        validated_publication_receipt = validate_precommit_publication_receipt(
            publication_receipt,
            precommit=validated_precommit,
        )
    except Exception as error:
        raise FreezeArtifactError(
            f"precommit publication receipt production validation failed: {error}"
        ) from error
    validate_frozen_output_schemas(frozen)
    precommit_hash = sha256_hex(validated_precommit)
    publication_receipt_hash = sha256_hex(validated_publication_receipt)
    freeze_id = validated_precommit["freeze_id"]
    protocol_root = validated_precommit["protocol_root_sha256"]
    if frozen.selection_manifest.get("freeze_id") != freeze_id:
        raise FreezeArtifactError("frozen cohort and custody precommit freeze IDs differ")
    if frozen.selection_manifest.get("precommit_sha256") != precommit_hash:
        raise FreezeArtifactError("frozen cohort and custody precommit hashes differ")
    if (
        frozen.selection_manifest.get("publication_receipt_sha256")
        != publication_receipt_hash
    ):
        raise FreezeArtifactError("frozen cohort and publication receipt hashes differ")

    private_files = {
        "selection-manifest.json": _json_bytes(frozen.selection_manifest),
        "private-split.json": _json_bytes(frozen.private_split),
        "selected-records.jsonl": _jsonl_bytes(frozen.selected_records),
        "reserve-records.jsonl": _jsonl_bytes(frozen.reserve_records),
    }
    release_files = {
        "custody-precommit.json": _json_bytes(validated_precommit),
        "precommit-publication-receipt.json": _json_bytes(
            validated_publication_receipt
        ),
        "custody-public.json": _json_bytes(frozen.custody_public),
        "custody-visible.json": _json_bytes(frozen.custody_visible),
        "milestone-manifest.json": _json_bytes(frozen.milestone_manifest),
    }
    private_manifest = _manifest(
        bundle_kind="PRIVATE",
        freeze_id=freeze_id,
        protocol_root_sha256=protocol_root,
        precommit_sha256=precommit_hash,
        files=private_files,
    )
    release_manifest = _manifest(
        bundle_kind="RELEASE",
        freeze_id=freeze_id,
        protocol_root_sha256=protocol_root,
        precommit_sha256=precommit_hash,
        files=release_files,
    )
    _validator("freeze-bundle-manifest.schema.json").validate(private_manifest)
    _validator("freeze-bundle-manifest.schema.json").validate(release_manifest)
    return private_files, release_files, private_manifest, release_manifest


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_atomic_idempotent(path: Path, payload: bytes, *, mode: int) -> str:
    if path.exists() or path.is_symlink():
        try:
            metadata = path.lstat()
        except OSError as error:
            raise FreezeArtifactError(f"cannot inspect existing artifact {path}: {error}") from error
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise FreezeArtifactError(f"existing artifact is not a regular file: {path}")
        if path.read_bytes() != payload:
            raise FreezeArtifactError(f"existing artifact conflicts with expected bytes: {path}")
        return "EXISTING"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    temporary = Path(temporary_name)
    os.fchmod(descriptor, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise FreezeArtifactError(f"concurrent artifact conflicts at {path}") from None
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return "WRITTEN"


def write_public_json_once(path: Path, value: Mapping[str, Any]) -> str:
    """Atomically publish one no-float canonical public artifact at most once."""

    path.parent.mkdir(parents=True, exist_ok=True)
    return _write_atomic_idempotent(
        path,
        canonical_json_bytes(value) + b"\n",
        mode=0o644,
    )


def _expected_directory_files(files: Mapping[str, bytes]) -> set[str]:
    return {*files, "bundle-manifest.json"}


def _verify_bundle_directory(
    directory: Path,
    *,
    files: Mapping[str, bytes],
    manifest_bytes: bytes,
    allow_receipt: bool = False,
) -> None:
    if not directory.is_dir() or directory.is_symlink():
        raise FreezeArtifactError(f"bundle target is not a regular directory: {directory}")
    expected = _expected_directory_files(files)
    entries = list(directory.iterdir())
    actual = {path.name for path in entries}
    allowed_extra = (
        {"freeze-receipt.json"}
        if allow_receipt and "freeze-receipt.json" in actual
        else set()
    )
    if actual != expected | allowed_extra:
        raise FreezeArtifactError(
            f"bundle file set conflicts at {directory}: missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )
    for path in entries:
        try:
            metadata = path.lstat()
        except OSError as error:
            raise FreezeArtifactError(f"cannot inspect bundle entry {path}: {error}") from error
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise FreezeArtifactError(f"bundle entry is not a regular file: {path}")
    for name, payload in files.items():
        if (directory / name).read_bytes() != payload:
            raise FreezeArtifactError(f"bundle artifact hash/bytes mismatch: {directory / name}")
    if (directory / "bundle-manifest.json").read_bytes() != manifest_bytes:
        raise FreezeArtifactError(f"bundle manifest mismatch: {directory}")


def _publish_bundle(
    target: Path,
    *,
    files: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    mode: int,
    fault_hook: Callable[[str], None] | None,
) -> str:
    manifest_bytes = _json_bytes(manifest)
    allow_receipt = manifest.get("bundle_kind") == "RELEASE"
    if target.exists() or target.is_symlink():
        _verify_bundle_directory(
            target,
            files=files,
            manifest_bytes=manifest_bytes,
            allow_receipt=allow_receipt,
        )
        return "EXISTING"

    stage = target.with_name(f".{target.name}.staging-{manifest['freeze_id']}")
    if stage.exists() and (not stage.is_dir() or stage.is_symlink()):
        raise FreezeArtifactError(f"staging target is not a regular directory: {stage}")
    stage.mkdir(mode=mode, parents=False, exist_ok=True)
    os.chmod(stage, mode)
    for name, payload in sorted(files.items()):
        _write_atomic_idempotent(stage / name, payload, mode=0o600)
        if fault_hook is not None:
            fault_hook(f"after:{target.name}:{name}")
    _write_atomic_idempotent(stage / "bundle-manifest.json", manifest_bytes, mode=0o600)
    if fault_hook is not None:
        fault_hook(f"after:{target.name}:bundle-manifest.json")
    _verify_bundle_directory(
        stage,
        files=files,
        manifest_bytes=manifest_bytes,
        allow_receipt=allow_receipt,
    )
    _fsync_directory(stage)
    try:
        os.rename(stage, target)
    except FileExistsError:
        _verify_bundle_directory(
            target,
            files=files,
            manifest_bytes=manifest_bytes,
            allow_receipt=allow_receipt,
        )
    _fsync_directory(target.parent)
    return "PUBLISHED"


@contextmanager
def _transaction_locks(paths: list[Path]):
    with ExitStack() as stack:
        handles = []
        for path in sorted(set(paths), key=lambda item: str(item.resolve())):
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = stack.enter_context(path.open("a+b"))
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise FreezeArtifactError(f"another freeze writer holds {path}") from error
            handles.append(handle)
        yield handles


def commit_freeze_transaction(
    *,
    frozen: Any,
    precommit: Mapping[str, Any],
    publication_receipt: Mapping[str, Any],
    private_directory: Path,
    release_directory: Path,
    fault_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Publish both bundles with a resumable two-phase commit and final receipt."""

    private_target = private_directory.resolve()
    release_target = release_directory.resolve()
    if private_target == release_target:
        raise FreezeArtifactError("private and release directories must differ")
    if private_target.is_relative_to(release_target) or release_target.is_relative_to(
        private_target
    ):
        raise FreezeArtifactError("private and release directories may not contain one another")
    if not private_target.parent.is_dir() or not release_target.parent.is_dir():
        raise FreezeArtifactError("both bundle parent directories must already exist")

    private_files, release_files, private_manifest, release_manifest = (
        build_freeze_bundle_payloads(frozen, precommit, publication_receipt)
    )
    freeze_id = str(private_manifest["freeze_id"])
    receipt = {
        "schema_version": "0.1.0",
        "algorithm_id": RECEIPT_ALGORITHM_ID,
        "freeze_id": freeze_id,
        "protocol_root_sha256": private_manifest["protocol_root_sha256"],
        "precommit_sha256": private_manifest["precommit_sha256"],
        "publication_receipt_sha256": frozen.selection_manifest[
            "publication_receipt_sha256"
        ],
        "private_bundle_manifest_sha256": _sha256_bytes(_json_bytes(private_manifest)),
        "release_bundle_manifest_sha256": _sha256_bytes(_json_bytes(release_manifest)),
        "state": "COMMITTED",
    }
    _validator("freeze-receipt.schema.json").validate(receipt)
    receipt_bytes = _json_bytes(receipt)
    locks = [
        private_target.parent / f".{freeze_id}.lock",
        release_target.parent / f".{freeze_id}.lock",
    ]
    with _transaction_locks(locks):
        private_state = _publish_bundle(
            private_target,
            files=private_files,
            manifest=private_manifest,
            mode=0o700,
            fault_hook=fault_hook,
        )
        if fault_hook is not None:
            fault_hook("after:private-publish")
        release_state = _publish_bundle(
            release_target,
            files=release_files,
            manifest=release_manifest,
            mode=0o750,
            fault_hook=fault_hook,
        )
        if fault_hook is not None:
            fault_hook("after:release-publish")
        receipt_state = _write_atomic_idempotent(
            release_target / "freeze-receipt.json", receipt_bytes, mode=0o600
        )
        if fault_hook is not None:
            fault_hook("after:freeze-receipt.json")

    status = (
        "ALREADY_COMMITTED"
        if private_state == release_state == receipt_state == "EXISTING"
        else "COMMITTED"
    )
    return {"status": status, **receipt}


__all__ = [
    "BUNDLE_ALGORITHM_ID",
    "RECEIPT_ALGORITHM_ID",
    "FreezeArtifactError",
    "build_freeze_bundle_payloads",
    "commit_freeze_transaction",
    "validate_frozen_output_schemas",
    "write_public_json_once",
]
