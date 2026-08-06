"""Deterministic P1 corpus inventory and reconciliation primitives.

This module is intentionally a discovery layer.  A :class:`FileRecord` is a
row from a manifest or live inventory.  An :class:`ObjectCandidate` is a
candidate package assembled from one or more rows.  It is *not* a confirmed
object or lineage and must never be used as an independent statistical unit.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

DIRECT_OBJECT_FORMATS: dict[str, str] = {
    ".3ds": "3ds",
    ".3mf": "3mf",
    ".amf": "amf",
    ".blend": "blend",
    ".brep": "brep",
    ".brp": "brep",
    ".dae": "collada",
    ".dcm": "dicom",
    ".dicom": "dicom",
    ".dxf": "dxf",
    ".fbx": "fbx",
    ".fcstd": "freecad",
    ".glb": "glb",
    ".gltf": "gltf",
    ".ifc": "ifc",
    ".iges": "iges",
    ".igs": "iges",
    ".jt": "jt",
    ".mha": "metaimage",
    ".mhd": "metaimage",
    ".nii": "nifti",
    ".nii.gz": "nifti",
    ".nrrd": "nrrd",
    ".obj": "obj",
    ".off": "off",
    ".ply": "ply",
    ".sab": "acis",
    ".sat": "acis",
    ".scad": "openscad",
    ".step": "step",
    ".stl": "stl",
    ".stp": "step",
    ".usd": "usd",
    ".usda": "usd",
    ".usdc": "usd",
    ".usdz": "usd",
    ".vtk": "vtk",
    ".vtp": "vtk",
    ".wrl": "vrml",
    ".x3d": "x3d",
    ".x_b": "parasolid",
    ".x_t": "parasolid",
}

_ARCHIVE_SUFFIXES = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".7z",
    ".rar",
    ".tar",
    ".tgz",
    ".tbz2",
    ".txz",
    ".zip",
)

_TEST_DIRECTORY_NAMES = frozenset(
    {
        "__tests__",
        "demo",
        "demos",
        "example",
        "examples",
        "fixture",
        "fixtures",
        "test_data",
        "testdata",
        "tests",
    }
)

_TEST_STEM_PATTERN = re.compile(
    r"(?:^|[-_. ])(?:demo|dummy|example|fixture|sample|test)(?:$|[-_. 0-9])",
    re.IGNORECASE,
)

_OBJAVERSE_UID_TOKEN = re.compile(r"(?<![0-9a-f])([0-9a-f]{32,64})(?![0-9a-f])", re.IGNORECASE)

_MULTIPART_PATTERNS = (
    (
        "numbered_archive",
        re.compile(r"^(?P<base>.+\.(?:7z|tar|zip))\.(?P<index>\d{3,})$", re.IGNORECASE),
        1,
        False,
    ),
    (
        "zip_part",
        re.compile(r"^(?P<base>.+\.zip)\.part(?P<index>\d+)$", re.IGNORECASE),
        1,
        False,
    ),
    (
        "part_rar",
        re.compile(r"^(?P<base>.+)\.part(?P<index>\d+)\.rar$", re.IGNORECASE),
        1,
        False,
    ),
    (
        "split_zip",
        re.compile(r"^(?P<base>.+)\.z(?P<index>\d{2})$", re.IGNORECASE),
        1,
        True,
    ),
    (
        "split_rar",
        re.compile(r"^(?P<base>.+)\.r(?P<index>\d{2})$", re.IGNORECASE),
        0,
        True,
    ),
)

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "path": (
        "path",
        "relative_path",
        "full_path",
        "file_path",
        "filepath",
        "drive_path",
    ),
    "directory": ("directory", "folder", "folder_path", "parent_path"),
    "name": ("name", "file_name", "filename"),
    "file_id": ("file_id", "drive_id", "google_drive_id", "id"),
    "bytes": ("bytes", "size_bytes", "file_size", "size"),
    "mime_type": ("mime_type", "mimetype", "mimeType"),
    "modified_time": ("modified_time", "modified", "modifiedTime", "mtime"),
    "dataset": ("dataset", "source_dataset", "collection"),
    "source_uid": ("source_uid", "object_uid", "uid"),
    "objaverse_uid": ("objaverse_uid", "objaverse_id"),
    "object_name": ("object_name", "model_name", "asset_name", "title"),
    "sha256": ("sha256", "sha256_checksum", "sha256sum"),
    "md5": ("md5", "md5_checksum", "md5Checksum"),
    "checksum": ("checksum", "content_hash", "hash"),
    "checksum_algorithm": ("checksum_algorithm", "hash_algorithm"),
}

# P1a manifests historically used the short ``sha256``/``bytes``/``format``
# names and a few US-English licence spellings.  P2a and every downstream G1
# artifact have one wire vocabulary.  Aliases are therefore accepted only at
# this import boundary and are never emitted.
CORPUS_REGISTRY_SCHEMA_VERSION = "0.1.0"
_CORPUS_REGISTRY_FIELDS = (
    "schema_version",
    "object_id",
    "lineage_id",
    "leakage_group_id",
    "dataset",
    "source_uid",
    "source_uri",
    "source_path",
    "creator_group",
    "category",
    "selection_stratum",
    "complexity_quantile",
    "source_sha256",
    "source_size_bytes",
    "source_format",
    "format_status",
    "licence",
    "licence_source",
    "licence_spdx",
    "licence_status",
    "provenance_status",
    "eligibility",
    "exclusion_reason",
    "topology_status",
    "split",
    "components",
    "vertices",
    "triangles",
    "bbox",
    "fixture_exception",
)
_CORPUS_REGISTRY_IMPORT_ALIASES: dict[str, tuple[str, ...]] = {
    "selection_stratum": ("stratum",),
    "source_sha256": ("sha256",),
    "source_size_bytes": ("bytes", "size_bytes"),
    "source_format": ("format",),
    "licence": ("license",),
    "licence_source": ("license_source",),
    "licence_spdx": ("license_spdx",),
    "licence_status": ("license_status",),
}


def canonicalise_corpus_registry_record(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Return one outcome-free P1a/P2a record using only canonical field names.

    Legacy aliases are deliberately limited to this import adapter.  Supplying
    conflicting canonical and alias values is an error rather than an implicit
    precedence choice.  Unrelated source metadata and experimental MVX outcome
    fields are not forwarded to cohort selection.
    """

    if not isinstance(mapping, Mapping):
        raise TypeError("corpus registry record must be a mapping")

    canonical: dict[str, Any] = {}
    for field_name in _CORPUS_REGISTRY_FIELDS:
        candidates = (field_name, *_CORPUS_REGISTRY_IMPORT_ALIASES.get(field_name, ()))
        present = [(name, mapping[name]) for name in candidates if name in mapping]
        if not present:
            continue
        first_name, value = present[0]
        conflicting = [name for name, candidate in present[1:] if candidate != value]
        if conflicting:
            names = ", ".join([first_name, *conflicting])
            raise ValueError(f"conflicting corpus registry aliases for {field_name}: {names}")
        canonical[field_name] = copy.deepcopy(value)

    if (
        "schema_version" in canonical
        and canonical["schema_version"] != CORPUS_REGISTRY_SCHEMA_VERSION
    ):
        raise ValueError(
            f"unsupported corpus registry schema_version: {canonical['schema_version']!r}"
        )
    return canonical


def _normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _normalise_path(value: str) -> str:
    text = unicodedata.normalize("NFC", str(value).strip()).replace("\\", "/")
    if not text:
        raise ValueError("file record path must not be empty")
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts:
        raise ValueError("file record path must not be empty")
    return PurePosixPath(*parts).as_posix()


def _normalise_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mapping_value(mapping: Mapping[str, Any], field_name: str) -> Any:
    normalised: dict[str, Any] = {}
    for key, value in mapping.items():
        normalised.setdefault(_normalise_header(str(key)), value)
    for alias in _FIELD_ALIASES[field_name]:
        key = _normalise_header(alias)
        if key in normalised and normalised[key] not in (None, ""):
            return normalised[key]
    return None


def _parse_nonnegative_integer(value: Any, *, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer, not a boolean")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} must be an integer")
        result = int(value)
    else:
        text = str(value).strip().replace(",", "").replace("_", "")
        try:
            result = int(text)
        except ValueError as error:
            raise ValueError(f"{field_name} must be an integer") from error
    if result < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _metadata_string(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, bool, int, float)):
        return _canonical_json(value)
    return "" if value is None else str(value)


def _extension(path: str) -> str:
    lower = PurePosixPath(path).name.casefold()
    for suffix in sorted((*DIRECT_OBJECT_FORMATS, *_ARCHIVE_SUFFIXES), key=len, reverse=True):
        if lower.endswith(suffix):
            return suffix
    return PurePosixPath(lower).suffix


def identify_direct_object_format(path: str | Path) -> str | None:
    """Return the canonical direct-reader format, or ``None`` for sidecars/archives."""

    return DIRECT_OBJECT_FORMATS.get(_extension(str(path)))


def is_test_path(path: str | Path) -> bool:
    """Recognise explicit project test artefacts without excluding dataset ``test/`` splits."""

    normalised = _normalise_path(str(path))
    parts = PurePosixPath(normalised).parts
    if any(part.casefold() in _TEST_DIRECTORY_NAMES for part in parts[:-1]):
        return True
    name = parts[-1]
    stem = name
    while PurePosixPath(stem).suffix:
        stem = PurePosixPath(stem).stem
    return bool(_TEST_STEM_PATTERN.search(stem))


def _infer_dataset(path: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if "objaverse" in path.casefold():
        return "objaverse"
    return None


def _is_objaverse_dataset_name(dataset: str | None) -> bool:
    if not dataset:
        return False
    compact = re.sub(r"[^a-z0-9]", "", dataset.casefold())
    return compact.startswith("objaverse")


def _infer_objaverse_uid(path: str, dataset: str | None, explicit: str | None) -> str | None:
    if explicit:
        return explicit.casefold()
    if not _is_objaverse_dataset_name(dataset):
        return None
    match = _OBJAVERSE_UID_TOKEN.search(PurePosixPath(path).name)
    return match.group(1).casefold() if match else None


def _logical_stem(path: str) -> str:
    name = PurePosixPath(path).name
    suffix = _extension(name)
    return name[: -len(suffix)] if suffix else name


@dataclass(frozen=True)
class FileRecord:
    """One metadata row; explicitly not an object or statistical unit."""

    path: str
    origin: str = "manifest"
    file_id: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None
    mime_type: str | None = None
    modified_time: str | None = None
    dataset: str | None = None
    source_uid: str | None = None
    objaverse_uid: str | None = None
    object_name: str | None = None
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _normalise_path(self.path))
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        for name in (
            "origin",
            "file_id",
            "checksum",
            "checksum_algorithm",
            "mime_type",
            "modified_time",
            "dataset",
            "source_uid",
            "objaverse_uid",
            "object_name",
        ):
            value = getattr(self, name)
            object.__setattr__(self, name, _normalise_optional(value))
        if not self.origin:
            raise ValueError("origin must not be empty")
        if self.checksum:
            object.__setattr__(self, "checksum", self.checksum.casefold())
        if self.checksum_algorithm:
            object.__setattr__(self, "checksum_algorithm", self.checksum_algorithm.casefold())
        if self.objaverse_uid:
            object.__setattr__(self, "objaverse_uid", self.objaverse_uid.casefold())
        canonical_metadata = tuple(sorted((str(key), str(value)) for key, value in self.metadata))
        object.__setattr__(self, "metadata", canonical_metadata)

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name

    @property
    def normalised_path_key(self) -> str:
        return unicodedata.normalize("NFC", self.path).casefold()

    @property
    def sort_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.normalised_path_key,
            self.path,
            self.file_id or "",
            self.checksum_algorithm or "",
            self.checksum or "",
            self.origin or "",
        )

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any], *, origin: str = "manifest") -> FileRecord:
        raw_path = _mapping_value(mapping, "path")
        raw_name = _mapping_value(mapping, "name")
        if raw_path in (None, ""):
            directory = _mapping_value(mapping, "directory")
            if raw_name in (None, ""):
                raise ValueError("manifest row has neither path nor name")
            raw_path = f"{directory}/{raw_name}" if directory not in (None, "") else raw_name

        path = _normalise_path(str(raw_path))
        explicit_dataset = _normalise_optional(_mapping_value(mapping, "dataset"))
        dataset = _infer_dataset(path, explicit_dataset)
        source_uid = _normalise_optional(_mapping_value(mapping, "source_uid"))
        explicit_objaverse_uid = _normalise_optional(_mapping_value(mapping, "objaverse_uid"))
        if explicit_objaverse_uid and not dataset:
            dataset = "objaverse"
        objaverse_uid = _infer_objaverse_uid(
            path,
            dataset,
            explicit_objaverse_uid or (source_uid if _is_objaverse_dataset_name(dataset) else None),
        )

        sha256 = _normalise_optional(_mapping_value(mapping, "sha256"))
        md5 = _normalise_optional(_mapping_value(mapping, "md5"))
        generic_checksum = _normalise_optional(_mapping_value(mapping, "checksum"))
        generic_algorithm = _normalise_optional(_mapping_value(mapping, "checksum_algorithm"))
        if sha256:
            checksum, checksum_algorithm = sha256, "sha256"
        elif md5:
            checksum, checksum_algorithm = md5, "md5"
        else:
            checksum, checksum_algorithm = generic_checksum, generic_algorithm

        recognised_headers = {
            _normalise_header(alias) for aliases in _FIELD_ALIASES.values() for alias in aliases
        }
        metadata = tuple(
            sorted(
                (str(key), _metadata_string(value))
                for key, value in mapping.items()
                if _normalise_header(str(key)) not in recognised_headers
            )
        )
        return cls(
            path=path,
            origin=origin,
            file_id=_normalise_optional(_mapping_value(mapping, "file_id")),
            size_bytes=_parse_nonnegative_integer(
                _mapping_value(mapping, "bytes"), field_name="bytes"
            ),
            checksum=checksum,
            checksum_algorithm=checksum_algorithm,
            mime_type=_normalise_optional(_mapping_value(mapping, "mime_type")),
            modified_time=_normalise_optional(_mapping_value(mapping, "modified_time")),
            dataset=dataset,
            source_uid=source_uid,
            objaverse_uid=objaverse_uid,
            object_name=_normalise_optional(_mapping_value(mapping, "object_name")),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "checksum": self.checksum,
            "checksum_algorithm": self.checksum_algorithm,
            "dataset": self.dataset,
            "file_id": self.file_id,
            "metadata": dict(self.metadata),
            "mime_type": self.mime_type,
            "modified_time": self.modified_time,
            "name": self.name,
            "object_name": self.object_name,
            "objaverse_uid": self.objaverse_uid,
            "origin": self.origin,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "source_uid": self.source_uid,
        }


def parse_manifest(path: str | Path, *, origin: str = "manifest") -> tuple[FileRecord, ...]:
    """Parse CSV or JSONL Drive metadata from a local path.

    The manifest is allowed to be stale.  Parsing it does not make any row part
    of the authoritative live population.
    """

    source = Path(path)
    suffix = source.suffix.casefold()
    mappings: list[Mapping[str, Any]] = []
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError(f"{source} has no CSV header")
            mappings.extend(dict(row) for row in reader)
    elif suffix in {".jsonl", ".ndjson"}:
        for line_number, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{source}:{line_number}: invalid JSON") from error
            if not isinstance(value, dict):
                raise TypeError(f"{source}:{line_number}: JSONL row must be an object")
            mappings.append(value)
    else:
        raise ValueError("manifest must use .csv, .jsonl or .ndjson")

    records: list[FileRecord] = []
    for row_number, mapping in enumerate(mappings, 2 if suffix == ".csv" else 1):
        try:
            records.append(FileRecord.from_mapping(mapping, origin=origin))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{source}: row {row_number}: {error}") from error
    return tuple(sorted(records, key=lambda record: record.sort_key))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_tree(
    root: str | Path,
    *,
    dataset: str | None = None,
    compute_sha256: bool = False,
) -> tuple[FileRecord, ...]:
    """Create a deterministic live inventory without following symlinks."""

    directory = Path(root)
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    records: list[FileRecord] = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        relative = path.relative_to(directory).as_posix()
        checksum = _sha256_file(path) if compute_sha256 else None
        inferred_dataset = _infer_dataset(relative, dataset)
        records.append(
            FileRecord(
                path=relative,
                origin="live",
                size_bytes=stat.st_size,
                checksum=checksum,
                checksum_algorithm="sha256" if checksum else None,
                dataset=inferred_dataset,
                objaverse_uid=_infer_objaverse_uid(relative, inferred_dataset, None),
            )
        )
    return tuple(sorted(records, key=lambda record: record.sort_key))


@dataclass(frozen=True)
class _MultipartPart:
    bundle_key: str
    style: str
    index: int
    expected_start: int
    terminal_required: bool


def _multipart_part(path: str) -> _MultipartPart | None:
    for style, pattern, expected_start, terminal_required in _MULTIPART_PATTERNS:
        match = pattern.match(path)
        if not match:
            continue
        base = match.group("base")
        if style == "part_rar":
            base = f"{base}.rar"
        elif style == "split_zip":
            base = f"{base}.zip"
        elif style == "split_rar":
            base = f"{base}.rar"
        return _MultipartPart(
            _normalise_path(base),
            style,
            int(match.group("index")),
            expected_start,
            terminal_required,
        )
    return None


def _archive_format(path: str) -> str | None:
    lower = path.casefold()
    for suffix in _ARCHIVE_SUFFIXES:
        if lower.endswith(suffix):
            return suffix.removeprefix(".")
    return None


def _coalesced(records: Sequence[FileRecord], attribute: str) -> tuple[str | None, bool]:
    values = {str(getattr(record, attribute)) for record in records if getattr(record, attribute)}
    if not values:
        return None, False
    return min(values, key=str.casefold), len(values) > 1


def _candidate_id(kind: str, package_key: str, records: Sequence[FileRecord]) -> str:
    payload = {
        "file_ids": sorted({record.file_id for record in records if record.file_id}),
        "files": sorted({record.normalised_path_key for record in records}),
        "kind": kind,
        "package_key": package_key.casefold(),
    }
    return f"candidate-{hashlib.sha256(_canonical_json(payload).encode()).hexdigest()}"


@dataclass(frozen=True)
class ObjectCandidate:
    """A physical package candidate awaiting lineage adjudication.

    ``ready_for_lineage`` means the package can enter metadata/geometry
    inspection.  It does not mean that the candidate is an independent object.
    """

    candidate_id: str
    kind: str
    package_key: str
    format: str
    files: tuple[FileRecord, ...]
    logical_name: str
    dataset: str | None = None
    source_uid: str | None = None
    objaverse_uid: str | None = None
    bundle_status: str | None = None
    ready_for_lineage: bool = True
    issues: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.files:
            raise ValueError("an object candidate must reference at least one file row")
        object.__setattr__(self, "files", tuple(sorted(self.files, key=lambda row: row.sort_key)))
        object.__setattr__(self, "issues", tuple(sorted(set(self.issues))))

    @property
    def file_paths(self) -> tuple[str, ...]:
        return tuple(record.path for record in self.files)

    @property
    def normalised_name(self) -> str:
        text = unicodedata.normalize("NFKC", self.logical_name).casefold().replace("_", " ")
        return " ".join(re.findall(r"[\w]+", text, flags=re.UNICODE))

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_status": self.bundle_status,
            "candidate_id": self.candidate_id,
            "dataset": self.dataset,
            "file_paths": list(self.file_paths),
            "format": self.format,
            "issues": list(self.issues),
            "kind": self.kind,
            "logical_name": self.logical_name,
            "objaverse_uid": self.objaverse_uid,
            "package_key": self.package_key,
            "ready_for_lineage": self.ready_for_lineage,
            "source_uid": self.source_uid,
        }


@dataclass(frozen=True)
class CandidateBuildResult:
    candidates: tuple[ObjectCandidate, ...]
    excluded_files: tuple[FileRecord, ...]
    ignored_files: tuple[FileRecord, ...]
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def direct_candidates(self) -> tuple[ObjectCandidate, ...]:
        return tuple(
            candidate for candidate in self.candidates if candidate.kind == "direct_object"
        )

    @property
    def archive_bundles(self) -> tuple[ObjectCandidate, ...]:
        return tuple(
            candidate for candidate in self.candidates if candidate.kind == "archive_bundle"
        )

    @property
    def file_row_count(self) -> int:
        return (
            sum(len(candidate.files) for candidate in self.candidates)
            + len(self.excluded_files)
            + len(self.ignored_files)
        )


def _make_candidate(
    *,
    kind: str,
    package_key: str,
    format_name: str,
    records: Sequence[FileRecord],
    logical_name: str,
    bundle_status: str | None,
    ready_for_lineage: bool,
    initial_issues: Iterable[str] = (),
) -> ObjectCandidate:
    ordered = tuple(sorted(records, key=lambda record: record.sort_key))
    dataset, conflicting_dataset = _coalesced(ordered, "dataset")
    source_uid, conflicting_source_uid = _coalesced(ordered, "source_uid")
    objaverse_uid, conflicting_objaverse_uid = _coalesced(ordered, "objaverse_uid")
    if not objaverse_uid:
        objaverse_uid = _infer_objaverse_uid(package_key, dataset, None)
    issues = list(initial_issues)
    if conflicting_dataset:
        issues.append("conflicting_dataset_metadata")
    if conflicting_source_uid:
        issues.append("conflicting_source_uid_metadata")
    if conflicting_objaverse_uid:
        issues.append("conflicting_objaverse_uid_metadata")
    return ObjectCandidate(
        candidate_id=_candidate_id(kind, package_key, ordered),
        kind=kind,
        package_key=package_key,
        format=format_name,
        files=ordered,
        logical_name=logical_name,
        dataset=dataset,
        source_uid=source_uid,
        objaverse_uid=objaverse_uid,
        bundle_status=bundle_status,
        ready_for_lineage=ready_for_lineage,
        issues=tuple(issues),
    )


def _same_path_physical_groups(records: Sequence[FileRecord]) -> tuple[tuple[FileRecord, ...], ...]:
    """Keep distinct Drive IDs separate even when Drive paths/names collide."""

    file_ids = sorted({record.file_id for record in records if record.file_id})
    if len(file_ids) <= 1:
        return (tuple(records),)
    groups: dict[str, list[FileRecord]] = defaultdict(list)
    for record in records:
        key = f"id:{record.file_id}" if record.file_id else "id:<MISSING>"
        groups[key].append(record)
    return tuple(
        tuple(sorted(groups[key], key=lambda record: record.sort_key)) for key in sorted(groups)
    )


def build_object_candidates(records: Iterable[FileRecord]) -> CandidateBuildResult:
    """Group live file rows into auditable object-package candidates.

    Test artefacts are excluded.  Sidecars and unknown formats are retained as
    ignored rows.  Multipart archives become one non-countable bundle and are
    never interpreted as one object per fragment.
    """

    rows = tuple(sorted(records, key=lambda record: record.sort_key))
    excluded = tuple(record for record in rows if is_test_path(record.path))
    active = tuple(record for record in rows if not is_test_path(record.path))

    fragment_groups: dict[str, list[tuple[FileRecord, _MultipartPart]]] = defaultdict(list)
    for record in active:
        part = _multipart_part(record.path)
        if part:
            fragment_groups[part.bundle_key.casefold()].append((record, part))

    used: set[int] = set()
    candidates: list[ObjectCandidate] = []
    build_issues: list[str] = []

    for folded_key in sorted(fragment_groups):
        grouped = fragment_groups[folded_key]
        parts = [part for _, part in grouped]
        records_in_bundle = [record for record, _ in grouped]
        styles = {part.style for part in parts}
        expected_starts = {part.expected_start for part in parts}
        terminal_required = any(part.terminal_required for part in parts)
        terminal = [record for record in active if record.normalised_path_key == folded_key]
        records_in_bundle.extend(terminal)
        used.update(id(record) for record in records_in_bundle)

        indexes = [part.index for part in parts]
        expected_start = min(expected_starts)
        unique_indexes = sorted(set(indexes))
        contiguous = unique_indexes == list(range(expected_start, max(unique_indexes) + 1))
        issues: list[str] = []
        if len(styles) > 1:
            issues.append("mixed_fragment_styles")
        if len(indexes) != len(unique_indexes):
            issues.append("duplicate_fragment_index")
        if not contiguous:
            status = "GAPPED_SEQUENCE"
            issues.append("missing_fragment_index")
        elif terminal_required and not terminal:
            status = "MISSING_TERMINAL"
            issues.append("missing_terminal_archive")
        elif terminal_required:
            status = "CONTIGUOUS_WITH_TERMINAL"
        else:
            status = "CONTIGUOUS_SEQUENCE"
        package_key = parts[0].bundle_key
        candidates.append(
            _make_candidate(
                kind="archive_bundle",
                package_key=package_key,
                format_name=_archive_format(package_key) or "archive",
                records=records_in_bundle,
                logical_name=_logical_stem(package_key),
                bundle_status=status,
                ready_for_lineage=False,
                initial_issues=issues,
            )
        )

    records_by_path: dict[str, list[FileRecord]] = defaultdict(list)
    for record in active:
        if id(record) not in used:
            records_by_path[record.normalised_path_key].append(record)

    ignored: list[FileRecord] = []
    for path_key in sorted(records_by_path):
        for same_path_records in _same_path_physical_groups(records_by_path[path_key]):
            representative = same_path_records[0]
            format_name = identify_direct_object_format(representative.path)
            archive_format = _archive_format(representative.path)
            duplicate_issue = ("duplicate_file_row",) if len(same_path_records) > 1 else ()
            if format_name:
                explicit_names = sorted(
                    {record.object_name for record in same_path_records if record.object_name},
                    key=str.casefold,
                )
                logical_name = (
                    explicit_names[0] if explicit_names else _logical_stem(representative.path)
                )
                candidates.append(
                    _make_candidate(
                        kind="direct_object",
                        package_key=representative.path,
                        format_name=format_name,
                        records=same_path_records,
                        logical_name=logical_name,
                        bundle_status=None,
                        ready_for_lineage=True,
                        initial_issues=duplicate_issue,
                    )
                )
            elif archive_format:
                candidates.append(
                    _make_candidate(
                        kind="archive_bundle",
                        package_key=representative.path,
                        format_name=archive_format,
                        records=same_path_records,
                        logical_name=_logical_stem(representative.path),
                        bundle_status="SINGLE_ARCHIVE",
                        ready_for_lineage=False,
                        initial_issues=duplicate_issue,
                    )
                )
            else:
                ignored.extend(same_path_records)

    candidates.sort(
        key=lambda candidate: (
            candidate.kind,
            candidate.package_key.casefold(),
            candidate.package_key,
            candidate.candidate_id,
        )
    )
    return CandidateBuildResult(
        candidates=tuple(candidates),
        excluded_files=tuple(sorted(excluded, key=lambda record: record.sort_key)),
        ignored_files=tuple(sorted(ignored, key=lambda record: record.sort_key)),
        issues=tuple(sorted(set(build_issues))),
    )


@dataclass(frozen=True)
class DuplicateGroup:
    field: str
    value: str
    candidate_ids: tuple[str, ...]
    package_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ids": list(self.candidate_ids),
            "field": self.field,
            "package_keys": list(self.package_keys),
            "value": self.value,
        }


def _is_objaverse(candidate: ObjectCandidate) -> bool:
    return _is_objaverse_dataset_name(candidate.dataset)


def detect_objaverse_duplicates(
    candidates: Iterable[ObjectCandidate],
) -> tuple[DuplicateGroup, ...]:
    """Report repeated Objaverse UIDs and normalised names without auto-merging them."""

    unique_candidates = {
        candidate.candidate_id: candidate
        for candidate in candidates
        if candidate.kind == "direct_object" and _is_objaverse(candidate)
    }
    eligible = tuple(
        sorted(unique_candidates.values(), key=lambda candidate: candidate.candidate_id)
    )
    groups: list[DuplicateGroup] = []
    for field_name, value_getter in (
        ("objaverse_uid", lambda candidate: candidate.objaverse_uid),
        ("normalised_name", lambda candidate: candidate.normalised_name or None),
    ):
        by_value: dict[str, list[ObjectCandidate]] = defaultdict(list)
        for candidate in eligible:
            value = value_getter(candidate)
            if value:
                by_value[str(value).casefold()].append(candidate)
        for value in sorted(by_value):
            matching = by_value[value]
            if len(matching) < 2:
                continue
            groups.append(
                DuplicateGroup(
                    field=field_name,
                    value=value,
                    candidate_ids=tuple(sorted(candidate.candidate_id for candidate in matching)),
                    package_keys=tuple(
                        sorted((candidate.package_key for candidate in matching), key=str.casefold)
                    ),
                )
            )
    return tuple(sorted(groups, key=lambda group: (group.field, group.value)))


@dataclass(frozen=True)
class ReconciliationEntry:
    status: str
    match_method: str | None
    manifest_record: FileRecord | None
    live_record: FileRecord | None
    changed_fields: tuple[str, ...] = field(default_factory=tuple)

    @property
    def sort_key(self) -> tuple[str, str, str]:
        record = self.live_record or self.manifest_record
        assert record is not None
        return (record.normalised_path_key, self.status, self.match_method or "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_fields": list(self.changed_fields),
            "live": self.live_record.to_dict() if self.live_record else None,
            "manifest": self.manifest_record.to_dict() if self.manifest_record else None,
            "match_method": self.match_method,
            "status": self.status,
        }


@dataclass(frozen=True)
class ReconciliationResult:
    entries: tuple[ReconciliationEntry, ...]
    authoritative_records: tuple[FileRecord, ...]
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def counts(self) -> dict[str, int]:
        result: dict[str, int] = defaultdict(int)
        for entry in self.entries:
            result[entry.status] += 1
        return dict(sorted(result.items()))

    def build_live_candidates(self) -> CandidateBuildResult:
        """Build candidates only from the live side, never from stale-only rows."""

        return build_object_candidates(self.authoritative_records)


def _unique_index(
    records: Sequence[FileRecord], key_getter: Any
) -> tuple[dict[str, int], set[str]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        value = key_getter(record)
        if value:
            grouped[str(value)].append(index)
    unique = {key: indexes[0] for key, indexes in grouped.items() if len(indexes) == 1}
    ambiguous = {key for key, indexes in grouped.items() if len(indexes) > 1}
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
        and manifest.checksum_algorithm
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


def reconcile_inventories(
    manifest_records: Iterable[FileRecord],
    live_records: Iterable[FileRecord],
    *,
    match_unique_checksum: bool = True,
) -> ReconciliationResult:
    """Reconcile stale metadata with a live inventory, which remains authoritative.

    Matching precedence is unique Drive file ID, unique normalised path, then a
    unique same-algorithm checksum.  Ambiguous keys are reported and never
    guessed.
    """

    manifest = tuple(sorted(manifest_records, key=lambda record: record.sort_key))
    live = tuple(sorted(live_records, key=lambda record: record.sort_key))
    unmatched_manifest = set(range(len(manifest)))
    unmatched_live = set(range(len(live)))
    pairs: list[tuple[int, int, str]] = []
    issues: list[str] = []

    def match_pass(method: str, getter: Any) -> None:
        manifest_subset = [manifest[index] for index in sorted(unmatched_manifest)]
        live_subset = [live[index] for index in sorted(unmatched_live)]
        manifest_positions = sorted(unmatched_manifest)
        live_positions = sorted(unmatched_live)
        manifest_index, manifest_ambiguous = _unique_index(manifest_subset, getter)
        live_index, live_ambiguous = _unique_index(live_subset, getter)
        for value in sorted(manifest_ambiguous | live_ambiguous):
            issues.append(f"ambiguous_{method}:{value}")
        for value in sorted(set(manifest_index) & set(live_index)):
            manifest_position = manifest_positions[manifest_index[value]]
            live_position = live_positions[live_index[value]]
            pairs.append((manifest_position, live_position, method))
            unmatched_manifest.remove(manifest_position)
            unmatched_live.remove(live_position)

    match_pass("file_id", lambda record: record.file_id)
    match_pass("path", lambda record: record.normalised_path_key)
    if match_unique_checksum:
        match_pass(
            "checksum",
            lambda record: (
                f"{record.checksum_algorithm}:{record.checksum}"
                if record.checksum_algorithm and record.checksum
                else None
            ),
        )

    entries: list[ReconciliationEntry] = []
    for manifest_index, live_index, method in pairs:
        old = manifest[manifest_index]
        current = live[live_index]
        changes = _changed_fields(old, current)
        entries.append(
            ReconciliationEntry(
                status="CHANGED" if changes else "UNCHANGED",
                match_method=method,
                manifest_record=old,
                live_record=current,
                changed_fields=changes,
            )
        )
    entries.extend(
        ReconciliationEntry(
            status="MISSING_FROM_LIVE",
            match_method=None,
            manifest_record=manifest[index],
            live_record=None,
        )
        for index in sorted(unmatched_manifest)
    )
    entries.extend(
        ReconciliationEntry(
            status="NEW_IN_LIVE",
            match_method=None,
            manifest_record=None,
            live_record=live[index],
        )
        for index in sorted(unmatched_live)
    )
    return ReconciliationResult(
        entries=tuple(sorted(entries, key=lambda entry: entry.sort_key)),
        authoritative_records=live,
        issues=tuple(sorted(set(issues))),
    )


def _as_mapping(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return {str(key): value for key, value in item.items()}
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if not isinstance(value, dict):
            raise TypeError("to_dict() must return a mapping")
        return value
    raise TypeError(f"cannot serialise {type(item).__name__}")


def _ordered_serialised_rows(items: Iterable[Any]) -> list[tuple[str, dict[str, Any]]]:
    rows = [_as_mapping(item) for item in items]
    serialised = [(_canonical_json(row), row) for row in rows]
    serialised.sort(key=lambda item: item[0])
    return serialised


def render_jsonl(items: Iterable[Any]) -> str:
    """Render canonical, input-order-independent JSON Lines."""

    ordered = _ordered_serialised_rows(items)
    return "".join(f"{canonical}\n" for canonical, _ in ordered)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return _canonical_json(value)
    return str(value)


def render_csv(items: Iterable[Any], *, fieldnames: Sequence[str] | None = None) -> str:
    """Render deterministic UTF-8 CSV with a stable field order."""

    ordered = _ordered_serialised_rows(items)
    rows = [row for _, row in ordered]
    if fieldnames is None:
        headers = sorted({str(key) for row in rows for key in row})
    else:
        headers = [str(field) for field in fieldnames]
        unknown = sorted({str(key) for row in rows for key in row} - set(headers))
        if unknown:
            raise ValueError(f"fieldnames omit fields: {unknown}")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({header: _csv_value(row.get(header)) for header in headers})
    return stream.getvalue()


def write_jsonl(items: Iterable[Any], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_jsonl(items), encoding="utf-8")
    return destination


def write_csv(
    items: Iterable[Any],
    path: str | Path,
    *,
    fieldnames: Sequence[str] | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_csv(items, fieldnames=fieldnames), encoding="utf-8")
    return destination
