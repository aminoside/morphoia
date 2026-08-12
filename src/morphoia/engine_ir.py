"""Reference Python API for public Morphoia Engine IR 0.1.

Authoritative content identity always flows through the native Profile 1 C ABI.
The pure-Python contract layer performs schema and semantic validation only.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib.metadata
import json
import math
import os
import secrets
import stat
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ._engine_native import (
    CANONICAL_PROFILE,
    FORMAT_IDENTIFIER,
    FORMAT_VERSION,
    MEDIA_TYPE,
    CanonicalLimits,
    NativeEngine,
)
from .engine_ir_contract import (
    REPLAY_FORMAT,
    ContractError,
    _resolve_schema,
    load_json_strict,
)
from .engine_ir_contract import (
    validate_manifest as validate_manifest_contract,
)
from .engine_ir_contract import (
    validate_replay as validate_replay_contract,
)
from .engine_ir_migration import _legacy_schema_path, build_legacy_migration_content

SHA256_ALGORITHM: Final = "sha256"
IDENTITY_SCOPE: Final = "content"
REPLAY_VERSION: Final = "0.1.0"
MAXIMUM_REPLAY_MANIFEST_BYTES: Final = 1_048_576
MAXIMUM_REPLAY_TIMEOUT_SECONDS: Final = 3_600.0
_SNAPSHOT_FIELDS: Final = (
    "st_dev",
    "st_ino",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


class ReplayError(ContractError):
    """A replay reference, workspace, deadline, or checkpoint is invalid."""


class ReplayCancelledError(ReplayError):
    """Replay was explicitly cancelled before completing."""


class ReplayTimeoutError(ReplayError):
    """Replay exceeded its caller-supplied wall-time budget."""


@dataclass(frozen=True, slots=True)
class ValidatedManifest:
    document: Mapping[str, Any]
    canonical_manifest: bytes
    canonical_content: bytes
    manifest_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ReplayResult:
    operation_key: str
    manifest_sha256: str
    content_sha256: str
    canonical_content: bytes
    checkpoint_path: Path
    resumed: bool


def _json_ready(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise TypeError(f"floating-point JSON value is forbidden at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object key must be str at {path}")
            _json_ready(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _json_ready(item, path=f"{path}[{index}]")
        return
    raise TypeError(f"unsupported JSON value {type(value).__name__} at {path}")


def _transport_json(value: Mapping[str, Any]) -> bytes:
    _json_ready(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise TypeError("value cannot be represented as bounded JSON") from error


def _coerce_source(source: bytes | bytearray | memoryview | str) -> bytes:
    if isinstance(source, str):
        return source.encode("utf-8", errors="strict")
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    raise TypeError("Engine IR source must be str or bytes-like")


def seal_content(
    content: Mapping[str, Any],
    *,
    engine: NativeEngine,
    limits: CanonicalLimits | None = None,
) -> ValidatedManifest:
    """Seal content with a native digest, then validate the complete envelope."""

    if not isinstance(content, Mapping):
        raise TypeError("Engine IR content must be a mapping")
    content_result = engine.canonicalize(_transport_json(content), limits=limits)
    normalized_content = load_json_strict(content_result.canonical)
    document: dict[str, Any] = {
        "format": FORMAT_IDENTIFIER,
        "format_version": FORMAT_VERSION,
        "media_type": MEDIA_TYPE,
        "canonical_profile": CANONICAL_PROFILE,
        "identity": {
            "algorithm": SHA256_ALGORITHM,
            "digest": content_result.sha256,
            "scope": IDENTITY_SCOPE,
        },
        "content": normalized_content,
    }
    validate_manifest_contract(document, identity_digest=content_result.sha256)
    manifest_result = engine.canonicalize(_transport_json(document), limits=limits)
    normalized_manifest = load_json_strict(manifest_result.canonical)
    validate_manifest_contract(normalized_manifest, identity_digest=content_result.sha256)
    return ValidatedManifest(
        document=normalized_manifest,
        canonical_manifest=manifest_result.canonical,
        canonical_content=content_result.canonical,
        manifest_sha256=manifest_result.sha256,
        content_sha256=content_result.sha256,
    )


def validate_manifest(
    source: bytes | bytearray | memoryview | str,
    *,
    engine: NativeEngine,
    limits: CanonicalLimits | None = None,
) -> ValidatedManifest:
    """Run native lexical, schema, semantic, and identity validation in order."""

    raw = _coerce_source(source)
    manifest_result = engine.canonicalize(raw, limits=limits)
    document = load_json_strict(manifest_result.canonical)
    content = document.get("content")
    if not isinstance(content, Mapping):
        # The contract layer will produce the stable schema error.
        validate_manifest_contract(document, identity_digest="0" * 64)
        raise TypeError("Engine IR content must be a mapping")  # pragma: no cover
    content_result = engine.canonicalize(_transport_json(content), limits=limits)
    validate_manifest_contract(document, identity_digest=content_result.sha256)
    return ValidatedManifest(
        document=document,
        canonical_manifest=manifest_result.canonical,
        canonical_content=content_result.canonical,
        manifest_sha256=manifest_result.sha256,
        content_sha256=content_result.sha256,
    )


def migrate_legacy_manifest(
    legacy_document: str | bytes,
    *,
    metadata: Mapping[str, Any],
    engine: NativeEngine,
    limits: CanonicalLimits | None = None,
) -> ValidatedManifest:
    """Build migration content, natively seal it, and preserve input bytes exactly."""

    before = (
        legacy_document.encode("utf-8", errors="strict")
        if isinstance(legacy_document, str)
        else legacy_document
    )
    if not isinstance(before, bytes):
        raise TypeError("legacy_document must be str or bytes")
    before_digest = hashlib.sha256(before).digest()
    content = build_legacy_migration_content(legacy_document, metadata=metadata)
    result = seal_content(content, engine=engine, limits=limits)
    if hashlib.sha256(before).digest() != before_digest:
        raise ReplayError("legacy input bytes changed during migration")
    return result


def create_replay_recipe(
    manifest: ValidatedManifest,
    *,
    seed: int = 0,
    expected_runs: int = 2,
) -> Mapping[str, Any]:
    """Create the closed deterministic replay recipe for one canonical manifest."""

    recipe: dict[str, Any] = {
        "format": REPLAY_FORMAT,
        "format_version": REPLAY_VERSION,
        "canonical_profile": CANONICAL_PROFILE,
        "manifest": {
            "uri": f"morphoia-cas://sha256/{manifest.manifest_sha256}",
            "sha256": manifest.manifest_sha256,
            "size_bytes": len(manifest.canonical_manifest),
            "media_type": MEDIA_TYPE,
        },
        "expected_content_identity": manifest.content_sha256,
        "operations": [
            {"sequence": 1, "operation": "validate-lexical"},
            {"sequence": 2, "operation": "validate-schema"},
            {"sequence": 3, "operation": "validate-semantic"},
            {"sequence": 4, "operation": "canonicalize-content"},
            {"sequence": 5, "operation": "verify-identity"},
        ],
        "determinism": {"seed": seed, "expected_runs": expected_runs},
    }
    validate_replay_contract(recipe)
    return recipe


class _Deadline:
    def __init__(
        self,
        timeout_seconds: float | None,
        cancellation: threading.Event | None,
    ) -> None:
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds < 0
            or timeout_seconds > MAXIMUM_REPLAY_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "timeout_seconds must be a finite number from 0 through 3600"
            )
        self._deadline = (
            None if timeout_seconds is None else time.monotonic() + timeout_seconds
        )
        self._cancellation = cancellation

    def check(self) -> None:
        if self._cancellation is not None and self._cancellation.is_set():
            raise ReplayCancelledError("replay cancelled")
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise ReplayTimeoutError("replay timeout expired")


def _open_absolute_directory(path: Path) -> int:
    """Open every absolute directory component without following a symlink."""

    if not path.is_absolute():
        raise ReplayError("workspace root must be absolute")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            if component in ("", ".", ".."):
                raise ReplayError("workspace root has an unsafe path component")
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if (
            metadata.st_uid != os.geteuid()
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise ReplayError(
                "workspace root must be owner-controlled and not group/world writable"
            )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _ensure_private_directory(parent_descriptor: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    except FileExistsError:
        pass
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        dir_fd=parent_descriptor,
    )
    metadata = os.fstat(descriptor)
    if (
        metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        os.close(descriptor)
        raise ReplayError(f"workspace directory {name!r} is not private and owner-controlled")
    return descriptor


def read_bounded_file(path: Path, maximum_bytes: int = MAXIMUM_REPLAY_MANIFEST_BYTES) -> bytes:
    """Snapshot one absolute regular file through no-follow directory handles."""

    if not path.is_absolute() or path.name in ("", ".", ".."):
        raise ReplayError("manifest resolver path must be an absolute regular file")
    parent_descriptor = _open_absolute_directory(path.parent)
    try:
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=parent_descriptor,
        )
    except BaseException:
        os.close(parent_descriptor)
        raise
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_size > maximum_bytes
        ):
            raise ReplayError("manifest resolver rejected unsafe file metadata or size")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum_bytes + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > maximum_bytes:
                raise ReplayError("manifest resolver input exceeds its byte limit")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            tuple(getattr(before, field) for field in _SNAPSHOT_FIELDS)
            != tuple(getattr(after, field) for field in _SNAPSHOT_FIELDS)
        ):
            raise ReplayError("manifest resolver input changed during snapshot")
        return b"".join(chunks)
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)


def resolve_manifest_reference(recipe: Mapping[str, Any], path: Path) -> bytes:
    """Return no bytes until URI, media type, size, and SHA-256 all verify."""

    validate_replay_contract(recipe)
    reference = recipe["manifest"]
    if reference["media_type"] != MEDIA_TYPE:
        raise ReplayError("replay manifest media type is unsupported")
    expected_digest = reference["sha256"]
    if reference["uri"] != f"morphoia-cas://sha256/{expected_digest}":
        raise ReplayError("replay manifest URI and SHA-256 differ")
    data = read_bounded_file(path, MAXIMUM_REPLAY_MANIFEST_BYTES)
    if len(data) != reference["size_bytes"]:
        raise ReplayError("resolved manifest size differs from its reference")
    if hashlib.sha256(data).hexdigest() != expected_digest:
        raise ReplayError("resolved manifest SHA-256 differs from its reference")
    return data


def _checkpoint_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def _read_checkpoint(directory: int, name: str) -> bytes | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=directory,
        )
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ReplayError("replay checkpoint metadata is unsafe")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(
                descriptor, min(65_536, MAXIMUM_REPLAY_MANIFEST_BYTES + 1 - size)
            )
            if not chunk:
                break
            size += len(chunk)
            if size > MAXIMUM_REPLAY_MANIFEST_BYTES:
                raise ReplayError("replay checkpoint exceeds its byte limit")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            tuple(getattr(metadata, field) for field in _SNAPSHOT_FIELDS)
            != tuple(getattr(after, field) for field in _SNAPSHOT_FIELDS)
        ):
            raise ReplayError("replay checkpoint changed during snapshot")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_checkpoint(directory: int, name: str, data: bytes) -> None:
    temporary = (
        f".{name}.{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(8)}.tmp"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory,
    )
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        library = ctypes.CDLL(None, use_errno=True)
        rename_noreplace = library.renameat2
        rename_noreplace.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_noreplace.restype = ctypes.c_int
        result = rename_noreplace(
            directory,
            os.fsencode(temporary),
            directory,
            os.fsencode(name),
            1,  # RENAME_NOREPLACE
        )
        if result != 0:
            saved_error = ctypes.get_errno()
            if saved_error != errno.EEXIST:
                raise OSError(saved_error, os.strerror(saved_error))
            if _read_checkpoint(directory, name) != data:
                raise ReplayError("concurrent replay checkpoint differs from expected bytes")
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.fsync(directory)
        os.close(descriptor)


def _callable_fingerprint(function: Any) -> bytes:
    """Return a path-independent fingerprint of one live Python callable."""

    code = getattr(function, "__code__", None)
    if code is None:
        raise ReplayError("replay implementation callable has no inspectable code")
    payload = {
        "module": getattr(function, "__module__", ""),
        "qualname": getattr(function, "__qualname__", ""),
        "bytecode": code.co_code.hex(),
        "names": list(code.co_names),
        "constants": [
            item
            if item is None or isinstance(item, (str, bool, int, float, bytes))
            else type(item).__name__
            for item in code.co_consts
        ],
    }
    return repr(payload).encode("utf-8", errors="strict")


def _replay_implementation_digest(engine: NativeEngine) -> str:
    """Hash installed source plus live entry points that determine replay behavior."""

    digest = hashlib.sha256()
    digest.update(b"morphoia.engine.ir-replay-implementation.v1\0")
    package = Path(__file__).parent
    for filename in ("_engine_native.py", "engine_ir.py", "engine_ir_contract.py"):
        path = package / filename
        try:
            source = path.read_bytes()
        except OSError as error:
            raise ReplayError(f"cannot fingerprint replay implementation: {filename}") from error
        digest.update(filename.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(len(source)).encode("ascii"))
        digest.update(b"\0")
        digest.update(source)
        digest.update(b"\0")
    schema_paths = (
        _resolve_schema("morphoia-engine-ir-manifest-0.1.0.schema.json", None),
        _resolve_schema("morphoia-engine-ir-replay-0.1.0.schema.json", None),
        _legacy_schema_path(),
    )
    for path in schema_paths:
        try:
            schema = path.read_bytes()
        except OSError as error:
            raise ReplayError(f"cannot fingerprint replay schema: {path.name}") from error
        digest.update(path.name.encode("ascii", errors="strict"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(schema).digest())
        digest.update(b"\0")
    for function in (
        validate_manifest,
        validate_manifest_contract,
        validate_replay_contract,
        load_json_strict,
        resolve_manifest_reference,
    ):
        digest.update(_callable_fingerprint(function))
        digest.update(b"\0")
    try:
        jsonschema_version = importlib.metadata.version("jsonschema")
    except importlib.metadata.PackageNotFoundError as error:
        raise ReplayError("jsonschema distribution version is unavailable") from error
    digest.update(f"jsonschema={jsonschema_version}".encode("ascii", errors="strict"))
    digest.update(b"\0native-library-sha256=")
    digest.update(engine.library_sha256.encode("ascii", errors="strict"))
    return digest.hexdigest()


def replay_manifest(
    recipe_source: bytes | bytearray | memoryview | str,
    manifest_path: Path,
    *,
    workspace_root: Path,
    engine: NativeEngine,
    limits: CanonicalLimits | None = None,
    timeout_seconds: float | None = 30.0,
    cancellation: threading.Event | None = None,
) -> ReplayResult:
    """Replay one small manifest with an immutable reference and resumable marker."""

    deadline = _Deadline(timeout_seconds, cancellation)
    deadline.check()
    recipe_result = engine.canonicalize(_coerce_source(recipe_source), limits=limits)
    recipe = load_json_strict(recipe_result.canonical)
    validate_replay_contract(recipe)
    deadline.check()

    manifest_source = resolve_manifest_reference(recipe, manifest_path)
    manifest = validate_manifest(manifest_source, engine=engine, limits=limits)
    reference = recipe["manifest"]
    if recipe["expected_content_identity"] != manifest.content_sha256:
        raise ReplayError("replay expected content identity does not match manifest content")
    deadline.check()

    stored = manifest_source
    implementation_digest = _replay_implementation_digest(engine)
    effective_limits = limits or CanonicalLimits(
        maximum_input_bytes=engine.capability.maximum_input_bytes,
        maximum_string_bytes=engine.capability.maximum_string_bytes,
        maximum_values=engine.capability.maximum_values,
        maximum_depth=engine.capability.maximum_depth,
    )
    limit_identity = (
        f"input={effective_limits.maximum_input_bytes};"
        f"string={effective_limits.maximum_string_bytes};"
        f"values={effective_limits.maximum_values};"
        f"depth={effective_limits.maximum_depth}"
    ).encode("ascii")
    operation_key = hashlib.sha256(
        b"morphoia.engine.ir-replay\0"
        + engine.version.encode("ascii", errors="strict")
        + b"\0"
        + implementation_digest.encode("ascii")
        + b"\0"
        + limit_identity
        + b"\0"
        + recipe_result.canonical
        + b"\0"
        + stored
    ).hexdigest()
    workspace_descriptor = _open_absolute_directory(workspace_root)
    try:
        runs_descriptor = _ensure_private_directory(workspace_descriptor, "runs")
    finally:
        os.close(workspace_descriptor)
    checkpoint_name = f"{operation_key}.json"
    checkpoint = workspace_root / "runs" / checkpoint_name
    expected_checkpoint: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "PASS",
        "operation_key": operation_key,
        "manifest_sha256": reference["sha256"],
        "content_sha256": manifest.content_sha256,
        "canonical_content_size": len(manifest.canonical_content),
        "expected_runs": recipe["determinism"]["expected_runs"],
        "seed": recipe["determinism"]["seed"],
        "implementation_sha256": implementation_digest,
    }
    expected_bytes = _checkpoint_bytes(expected_checkpoint)
    try:
        checkpoint_bytes = _read_checkpoint(runs_descriptor, checkpoint_name)
        if checkpoint_bytes == expected_bytes:
            deadline.check()
            return ReplayResult(
                operation_key=operation_key,
                manifest_sha256=reference["sha256"],
                content_sha256=manifest.content_sha256,
                canonical_content=manifest.canonical_content,
                checkpoint_path=checkpoint,
                resumed=True,
            )

        baseline = manifest
        for _run in range(recipe["determinism"]["expected_runs"]):
            deadline.check()
            replayed = validate_manifest(stored, engine=engine, limits=limits)
            if (
                replayed.canonical_manifest != baseline.canonical_manifest
                or replayed.canonical_content != baseline.canonical_content
                or replayed.manifest_sha256 != baseline.manifest_sha256
                or replayed.content_sha256 != baseline.content_sha256
            ):
                raise ReplayError("replay was not byte- and identity-deterministic")
        deadline.check()
        _write_checkpoint(runs_descriptor, checkpoint_name, expected_bytes)
        return ReplayResult(
            operation_key=operation_key,
            manifest_sha256=reference["sha256"],
            content_sha256=manifest.content_sha256,
            canonical_content=manifest.canonical_content,
            checkpoint_path=checkpoint,
            resumed=False,
        )
    finally:
        os.close(runs_descriptor)


__all__ = [
    "IDENTITY_SCOPE",
    "MAXIMUM_REPLAY_MANIFEST_BYTES",
    "MAXIMUM_REPLAY_TIMEOUT_SECONDS",
    "REPLAY_VERSION",
    "SHA256_ALGORITHM",
    "ReplayCancelledError",
    "ReplayError",
    "ReplayResult",
    "ReplayTimeoutError",
    "ValidatedManifest",
    "create_replay_recipe",
    "migrate_legacy_manifest",
    "read_bounded_file",
    "replay_manifest",
    "resolve_manifest_reference",
    "seal_content",
    "validate_manifest",
]
