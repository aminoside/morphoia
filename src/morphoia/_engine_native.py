"""Strict ctypes binding for the versioned Morphoia Engine C ABI.

The authoritative Engine IR identity path always uses the native library. This
module deliberately has no pure-Python canonicalization fallback and never
searches the current working directory for a shared object.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Self

ABI_VERSION: Final = 1
CAPABILITY_ENGINE_IR_MANIFEST: Final = "morphoia.engine.ir-manifest"
FORMAT_IDENTIFIER: Final = "morphoia.engine.ir-manifest"
FORMAT_VERSION: Final = "0.1.0"
MEDIA_TYPE: Final = "application/vnd.morphoia.ir-manifest.v0+json"
CANONICAL_PROFILE: Final = "morphoia.canonical-json.profile1"
LIBRARY_ENVIRONMENT_VARIABLE: Final = "MORPHOIA_ENGINE_LIBRARY"

STATUS_OK: Final = 0
STATUS_BUFFER_TOO_SMALL: Final = 7
_LIBRARY_SNAPSHOT_FIELDS: Final = (
    "st_dev",
    "st_ino",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


class NativeLibraryError(RuntimeError):
    """Base error for native library discovery, ABI, or execution failures."""


class NativeLibraryNotFoundError(NativeLibraryError):
    """The required native Engine library could not be resolved."""


class NativeEngineError(NativeLibraryError):
    """A structured error returned by the native Engine ABI."""

    def __init__(
        self,
        status: int,
        status_name: str,
        message: str,
        *,
        context: str = "",
        cause: str = "",
        affected_elements: str = "",
        recommendation: str = "",
    ) -> None:
        super().__init__(f"{status_name}: {message}")
        self.status = status
        self.status_name = status_name
        self.message = message
        self.context = context
        self.cause = cause
        self.affected_elements = affected_elements
        self.recommendation = recommendation


class _StringView(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("size", ctypes.c_size_t)]


class _Diagnostic(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("status", ctypes.c_int32),
        ("severity", ctypes.c_uint32),
        ("message_length", ctypes.c_uint32),
        ("message", ctypes.c_char * 256),
        ("context_length", ctypes.c_uint32),
        ("context", ctypes.c_char * 128),
        ("cause_length", ctypes.c_uint32),
        ("cause", ctypes.c_char * 128),
        ("affected_elements_length", ctypes.c_uint32),
        ("affected_elements", ctypes.c_char * 128),
        ("recommendation_length", ctypes.c_uint32),
        ("recommendation", ctypes.c_char * 128),
    ]


class _VersionInfo(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("engine_abi_version", ctypes.c_uint32),
        ("major", ctypes.c_uint32),
        ("minor", ctypes.c_uint32),
        ("patch", ctypes.c_uint32),
        ("version_string", _StringView),
    ]


class _CapabilityInfo(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("supported", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("capability_name", _StringView),
        ("format_identifier", _StringView),
        ("format_version", _StringView),
        ("media_type", _StringView),
        ("canonical_profile", _StringView),
        ("extension_keys", _StringView),
        ("maximum_input_bytes", ctypes.c_uint64),
        ("maximum_string_bytes", ctypes.c_uint64),
        ("maximum_values", ctypes.c_uint64),
        ("maximum_depth", ctypes.c_uint64),
    ]


class _CanonicalOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint64),
        ("maximum_input_bytes", ctypes.c_uint64),
        ("maximum_string_bytes", ctypes.c_uint64),
        ("maximum_values", ctypes.c_uint64),
        ("maximum_depth", ctypes.c_uint64),
    ]


@dataclass(frozen=True, slots=True)
class CanonicalLimits:
    maximum_input_bytes: int = 1_048_576
    maximum_string_bytes: int = 262_144
    maximum_values: int = 100_000
    maximum_depth: int = 64

    def _as_native(self) -> _CanonicalOptions:
        values = (
            self.maximum_input_bytes,
            self.maximum_string_bytes,
            self.maximum_values,
            self.maximum_depth,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in values
        ):
            raise ValueError("every canonical JSON limit must be a positive integer")
        if any(value > (1 << 64) - 1 for value in values):
            raise ValueError("canonical JSON limits must fit uint64")
        options = _CanonicalOptions()
        options.struct_size = ctypes.sizeof(options)
        options.abi_version = ABI_VERSION
        options.flags = 0
        options.maximum_input_bytes = self.maximum_input_bytes
        options.maximum_string_bytes = self.maximum_string_bytes
        options.maximum_values = self.maximum_values
        options.maximum_depth = self.maximum_depth
        return options


@dataclass(frozen=True, slots=True)
class EngineCapability:
    capability_name: str
    format_identifier: str
    format_version: str
    media_type: str
    canonical_profile: str
    extension_keys: tuple[str, ...]
    maximum_input_bytes: int
    maximum_string_bytes: int
    maximum_values: int
    maximum_depth: int


@dataclass(frozen=True, slots=True)
class CanonicalJsonResult:
    canonical: bytes
    sha256: str


def _initialized(structure: ctypes.Structure) -> ctypes.Structure:
    structure.struct_size = ctypes.sizeof(structure)  # type: ignore[attr-defined]
    structure.abi_version = ABI_VERSION  # type: ignore[attr-defined]
    return structure


def _read_view(view: _StringView) -> bytes:
    if view.size == 0:
        return b""
    if not view.data:
        raise NativeLibraryError("native ABI returned a null view with nonzero size")
    return ctypes.string_at(view.data, view.size)


def _decode_view(view: _StringView) -> str:
    return _read_view(view).decode("utf-8", errors="strict")


def _diagnostic_text(
    diagnostic: _Diagnostic,
    field: str,
    length: int,
    capacity: int,
) -> str:
    bounded = min(max(length, 0), capacity)
    offset = getattr(_Diagnostic, field).offset
    raw = ctypes.string_at(ctypes.addressof(diagnostic) + offset, bounded)
    return raw.decode("utf-8", errors="replace")


def _explicit_library_path(value: str | os.PathLike[str], source: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        raise NativeLibraryNotFoundError(f"{source} must name an absolute library path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise NativeLibraryNotFoundError(f"{source} does not resolve to a file: {path}") from error
    if not resolved.is_file():
        raise NativeLibraryNotFoundError(f"{source} does not resolve to a regular file: {resolved}")
    return os.fspath(resolved)


def resolve_native_library(
    explicit_path: str | os.PathLike[str] | None = None,
) -> str:
    """Resolve only an explicit path, the dedicated environment path, or an install."""

    if explicit_path is not None:
        return _explicit_library_path(explicit_path, "explicit native library path")
    environment_path = os.environ.get(LIBRARY_ENVIRONMENT_VARIABLE)
    if environment_path:
        return _explicit_library_path(environment_path, LIBRARY_ENVIRONMENT_VARIABLE)
    installed = ctypes.util.find_library("morphoia_engine")
    if installed:
        return installed
    raise NativeLibraryNotFoundError(
        "libmorphoia_engine is required; provide an absolute path, set "
        f"{LIBRARY_ENVIRONMENT_VARIABLE}, or install the native library"
    )


class _DlInfo(ctypes.Structure):
    _fields_ = [
        ("filename", ctypes.c_char_p),
        ("base", ctypes.c_void_p),
        ("symbol_name", ctypes.c_char_p),
        ("symbol_address", ctypes.c_void_p),
    ]


def _loaded_library_file(library: ctypes.CDLL, resolved: str) -> Path:
    candidate = Path(resolved)
    if candidate.is_absolute():
        return candidate
    runtime = ctypes.CDLL(None)
    try:
        dladdr = runtime.dladdr
    except AttributeError as error:
        raise NativeLibraryError(
            "cannot resolve an installed native library to hash its loaded bytes"
        ) from error
    dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DlInfo)]
    dladdr.restype = ctypes.c_int
    information = _DlInfo()
    symbol = ctypes.cast(library.morphoia_engine_get_version, ctypes.c_void_p)
    if dladdr(symbol, ctypes.byref(information)) == 0 or not information.filename:
        raise NativeLibraryError("cannot identify the loaded native Engine library file")
    try:
        text = os.fsdecode(information.filename)
    except UnicodeDecodeError as error:
        raise NativeLibraryError("loaded native library path is not valid filesystem text") from error
    return Path(text)


def _hash_loaded_library(path: Path) -> tuple[str, str]:
    try:
        resolved = path.resolve(strict=True)
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError as error:
        raise NativeLibraryError(f"cannot open loaded native library for hashing: {path}") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
            raise NativeLibraryError("loaded native Engine library is not a regular file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        if tuple(getattr(before, field) for field in _LIBRARY_SNAPSHOT_FIELDS) != tuple(
            getattr(after, field) for field in _LIBRARY_SNAPSHOT_FIELDS
        ):
            raise NativeLibraryError("loaded native Engine library changed while hashing")
        return os.fspath(resolved), digest.hexdigest()
    finally:
        os.close(descriptor)


class NativeEngine:
    """Owned native context with deterministic close and serialized calls."""

    def __init__(self, library_path: str | os.PathLike[str] | None = None) -> None:
        resolved = resolve_native_library(library_path)
        try:
            library = ctypes.CDLL(resolved)
        except OSError as error:
            raise NativeLibraryNotFoundError(
                f"could not load native Engine library: {resolved}"
            ) from error
        self._library = library
        self.library_path = resolved
        self._lock = threading.RLock()
        self._context = ctypes.c_void_p()
        try:
            self._configure_functions()
            loaded_file = _loaded_library_file(library, resolved)
            self.library_file, self.library_sha256 = _hash_loaded_library(loaded_file)
            self.version = self._query_version()
            self._create_context()
            self._verify_context_abi()
            self.capability = self.query_capability(CAPABILITY_ENGINE_IR_MANIFEST)
            if self.capability is None:
                raise NativeLibraryError(
                    "native library does not support required capability "
                    f"{CAPABILITY_ENGINE_IR_MANIFEST}"
                )
            self._verify_capability_constants(self.capability)
        except AttributeError as error:
            self.close()
            raise NativeLibraryError(
                "native Engine library does not expose the required ABI-v1 symbols"
            ) from error
        except BaseException:
            self.close()
            raise

    def _configure_functions(self) -> None:
        library = self._library
        library.morphoia_engine_get_version.argtypes = [
            ctypes.POINTER(_VersionInfo),
            ctypes.POINTER(_Diagnostic),
        ]
        library.morphoia_engine_get_version.restype = ctypes.c_int32
        library.morphoia_context_create.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_Diagnostic),
        ]
        library.morphoia_context_create.restype = ctypes.c_int32
        library.morphoia_context_destroy.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_Diagnostic),
        ]
        library.morphoia_context_destroy.restype = ctypes.c_int32
        library.morphoia_context_get_abi_version.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_Diagnostic),
        ]
        library.morphoia_context_get_abi_version.restype = ctypes.c_int32
        library.morphoia_context_query_capability.argtypes = [
            ctypes.c_void_p,
            _StringView,
            ctypes.POINTER(_CapabilityInfo),
            ctypes.POINTER(_Diagnostic),
        ]
        library.morphoia_context_query_capability.restype = ctypes.c_int32
        library.morphoia_canonical_json_profile1.argtypes = [
            ctypes.c_void_p,
            _StringView,
            ctypes.POINTER(_CanonicalOptions),
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(_Diagnostic),
        ]
        library.morphoia_canonical_json_profile1.restype = ctypes.c_int32
        library.morphoia_status_name.argtypes = [ctypes.c_int32]
        library.morphoia_status_name.restype = _StringView

    @staticmethod
    def _diagnostic() -> _Diagnostic:
        return _initialized(_Diagnostic())  # type: ignore[return-value]

    def _raise_status(self, status: int, diagnostic: _Diagnostic) -> None:
        status_name = _decode_view(self._library.morphoia_status_name(status))
        raise NativeEngineError(
            status,
            status_name,
            _diagnostic_text(diagnostic, "message", diagnostic.message_length, 256),
            context=_diagnostic_text(diagnostic, "context", diagnostic.context_length, 128),
            cause=_diagnostic_text(diagnostic, "cause", diagnostic.cause_length, 128),
            affected_elements=_diagnostic_text(
                diagnostic, "affected_elements", diagnostic.affected_elements_length, 128
            ),
            recommendation=_diagnostic_text(
                diagnostic, "recommendation", diagnostic.recommendation_length, 128
            ),
        )

    def _query_version(self) -> str:
        version = _initialized(_VersionInfo())
        diagnostic = self._diagnostic()
        status = self._library.morphoia_engine_get_version(
            ctypes.byref(version), ctypes.byref(diagnostic)
        )
        if status != STATUS_OK:
            self._raise_status(status, diagnostic)
        if version.engine_abi_version != ABI_VERSION:
            raise NativeLibraryError(
                f"native Engine ABI {version.engine_abi_version} is incompatible "
                f"with required ABI {ABI_VERSION}"
            )
        return _decode_view(version.version_string)

    def _create_context(self) -> None:
        diagnostic = self._diagnostic()
        status = self._library.morphoia_context_create(
            None, ctypes.byref(self._context), ctypes.byref(diagnostic)
        )
        if status != STATUS_OK:
            self._raise_status(status, diagnostic)
        if not self._context.value:
            raise NativeLibraryError("native context creation returned a null handle")

    def _verify_context_abi(self) -> None:
        value = ctypes.c_uint32()
        diagnostic = self._diagnostic()
        status = self._library.morphoia_context_get_abi_version(
            self._context, ctypes.byref(value), ctypes.byref(diagnostic)
        )
        if status != STATUS_OK:
            self._raise_status(status, diagnostic)
        if value.value != ABI_VERSION:
            raise NativeLibraryError(
                f"native context ABI {value.value} is incompatible with required ABI {ABI_VERSION}"
            )

    @staticmethod
    def _verify_capability_constants(capability: EngineCapability) -> None:
        expected = (
            (capability.format_identifier, FORMAT_IDENTIFIER, "format identifier"),
            (capability.format_version, FORMAT_VERSION, "format version"),
            (capability.media_type, MEDIA_TYPE, "media type"),
            (capability.canonical_profile, CANONICAL_PROFILE, "canonical profile"),
        )
        for actual, required, label in expected:
            if actual != required:
                raise NativeLibraryError(
                    f"native capability {label} {actual!r} does not match required {required!r}"
                )

    def __enter__(self) -> Self:
        if not self._context.value:
            raise NativeLibraryError("native Engine context is closed")
        return self

    def __exit__(self, _exception_type, _exception, _traceback) -> None:
        self.close()

    @property
    def closed(self) -> bool:
        return not bool(self._context.value)

    def close(self) -> None:
        with self._lock:
            if not self._context.value:
                return
            diagnostic = self._diagnostic()
            status = self._library.morphoia_context_destroy(
                ctypes.byref(self._context), ctypes.byref(diagnostic)
            )
            if status != STATUS_OK:
                self._raise_status(status, diagnostic)

    @staticmethod
    def _input_view(value: bytes) -> tuple[_StringView, ctypes.Array[ctypes.c_char] | None]:
        if not value:
            return _StringView(None, 0), None
        storage = ctypes.create_string_buffer(value, len(value))
        return _StringView(ctypes.cast(storage, ctypes.c_void_p), len(value)), storage

    def query_capability(self, name: str) -> EngineCapability | None:
        if not isinstance(name, str):
            raise TypeError("capability name must be str")
        encoded = name.encode("utf-8", errors="strict")
        view, storage = self._input_view(encoded)
        info = _initialized(_CapabilityInfo())
        diagnostic = self._diagnostic()
        with self._lock:
            if not self._context.value:
                raise NativeLibraryError("native Engine context is closed")
            status = self._library.morphoia_context_query_capability(
                self._context, view, ctypes.byref(info), ctypes.byref(diagnostic)
            )
        del storage
        if status != STATUS_OK:
            self._raise_status(status, diagnostic)
        if not info.supported:
            return None
        extension_text = _decode_view(info.extension_keys)
        return EngineCapability(
            capability_name=_decode_view(info.capability_name),
            format_identifier=_decode_view(info.format_identifier),
            format_version=_decode_view(info.format_version),
            media_type=_decode_view(info.media_type),
            canonical_profile=_decode_view(info.canonical_profile),
            extension_keys=tuple(item for item in extension_text.split(",") if item),
            maximum_input_bytes=info.maximum_input_bytes,
            maximum_string_bytes=info.maximum_string_bytes,
            maximum_values=info.maximum_values,
            maximum_depth=info.maximum_depth,
        )

    def canonicalize(
        self,
        source: bytes | bytearray | memoryview | str,
        *,
        limits: CanonicalLimits | None = None,
    ) -> CanonicalJsonResult:
        if isinstance(source, str):
            raw = source.encode("utf-8", errors="strict")
        elif isinstance(source, (bytes, bytearray, memoryview)):
            raw = bytes(source)
        else:
            raise TypeError("canonical JSON source must be str or bytes-like")
        view, view_storage = self._input_view(raw)
        options = limits._as_native() if limits is not None else None
        options_pointer = ctypes.byref(options) if options is not None else None
        required = ctypes.c_size_t()
        digest = (ctypes.c_uint8 * 32)()
        diagnostic = self._diagnostic()
        with self._lock:
            if not self._context.value:
                raise NativeLibraryError("native Engine context is closed")
            status = self._library.morphoia_canonical_json_profile1(
                self._context,
                view,
                options_pointer,
                None,
                0,
                ctypes.byref(required),
                digest,
                ctypes.byref(diagnostic),
            )
            if status != STATUS_BUFFER_TOO_SMALL:
                self._raise_status(status, diagnostic)
            measured_size = required.value
            measured_digest = bytes(digest)
            output = (ctypes.c_char * measured_size)()
            required_again = ctypes.c_size_t()
            digest_again = (ctypes.c_uint8 * 32)()
            diagnostic = self._diagnostic()
            status = self._library.morphoia_canonical_json_profile1(
                self._context,
                view,
                options_pointer,
                ctypes.cast(output, ctypes.c_void_p),
                measured_size,
                ctypes.byref(required_again),
                digest_again,
                ctypes.byref(diagnostic),
            )
            if status != STATUS_OK:
                self._raise_status(status, diagnostic)
        del view_storage
        if required_again.value != measured_size or bytes(digest_again) != measured_digest:
            raise NativeLibraryError(
                "native two-pass canonicalization result changed between calls"
            )
        return CanonicalJsonResult(bytes(output), measured_digest.hex())


__all__ = [
    "ABI_VERSION",
    "CANONICAL_PROFILE",
    "CAPABILITY_ENGINE_IR_MANIFEST",
    "FORMAT_IDENTIFIER",
    "FORMAT_VERSION",
    "LIBRARY_ENVIRONMENT_VARIABLE",
    "MEDIA_TYPE",
    "CanonicalJsonResult",
    "CanonicalLimits",
    "EngineCapability",
    "NativeEngine",
    "NativeEngineError",
    "NativeLibraryError",
    "NativeLibraryNotFoundError",
    "resolve_native_library",
]
