"""Fail-closed orchestration for freezing the MVX G1 cohort.

The helpers in :mod:`morphoia.mvx.selection`, :mod:`morphoia.mvx.split` and
:mod:`morphoia.mvx.custody` deliberately have narrow responsibilities.  This
module composes them into one pure operation and checks the cross-artifact
invariants that none of those helpers can establish in isolation.

``freeze_cohort`` performs no filesystem or network I/O and never copies an
experimental outcome into a selection input.  Callers are responsible for
storing the returned private artifacts behind the custody boundary.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import math
import types
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .corpus.registry import canonicalise_corpus_registry_record
from .custody import (
    _validate_precommit_publication_receipt,
    canonical_json_bytes,
    create_custody_release,
    sha256_hex,
    validate_precommit_publication_receipt,
    validate_secret_bytes,
    verify_custody_precommit,
)
from .selection import (
    ALGORITHM_ID as SELECTION_ALGORITHM_ID,
)
from .selection import (
    ALGORITHM_VERSION as SELECTION_ALGORITHM_VERSION,
)
from .selection import (
    DEFAULT_TARGETS,
    VISIBLE_MILESTONE_ALGORITHM_ID,
    VISIBLE_MILESTONE_ALGORITHM_VERSION,
    select_cohort,
    select_visible_milestones,
)
from .split import build_split_manifest

FREEZE_ALGORITHM_ID = "MVX-G1-FREEZE-1"
SELECTION_SCHEMA_VERSION = "0.1.0"
SELECTED_TOTAL = 1_000
OBJAVERSE_OOD_TOTAL = 60
MILESTONE_SIZES = {"n12": 12, "n30": 30, "n100": 100, "n300": 300}
FROZEN_EXACT_TARGETS = {
    "fixtures_C0_C9": {"total": 100, "development": 50, "calibration": 20, "blind": 30},
    "objaverse": {"total": 600, "development": 300, "calibration": 120, "blind": 180},
    "modelnet40": {"total": 100, "development": 50, "calibration": 20, "blind": 30},
    "thingi10k": {"total": 80, "development": 40, "calibration": 16, "blind": 24},
    "google_scanned_objects": {
        "total": 60,
        "development": 30,
        "calibration": 12,
        "blind": 18,
    },
    "human_anatomy": {"total": 50, "development": 25, "calibration": 10, "blind": 15},
    "plants": {"total": 10, "development": 5, "calibration": 2, "blind": 3},
}

_SPLITS = ("development", "calibration", "blind")
_HEX_DIGITS = frozenset("0123456789abcdef")

# This is intentionally an allow-list.  In particular, MVX status, fidelity,
# reconstruction and timing fields supplied by a caller are never forwarded to
# selection or splitting and therefore cannot affect the frozen cohort.
_PRE_OUTCOME_FIELDS = (
    "schema_version",
    "object_id",
    "lineage_id",
    "leakage_group_id",
    "selection_stratum",
    "dataset",
    "category",
    "creator_group",
    "source_uid",
    "eligibility",
    "topology_status",
    "complexity_quantile",
    "source_path",
    "source_uri",
    "source_sha256",
    "source_format",
    "source_size_bytes",
    "format_status",
    "licence",
    "licence_source",
    "licence_spdx",
    "licence_status",
    "provenance_status",
    "components",
    "vertices",
    "triangles",
    "bbox",
    "fixture_exception",
)
_SPLIT_REQUIRED_FIELDS = frozenset(
    {
        "lineage_id",
        "leakage_group_id",
        "selection_stratum",
        "dataset",
        "category",
        "creator_group",
        "source_uid",
        "eligibility",
        "topology_status",
        "complexity_quantile",
        "source_uri",
        "source_sha256",
        "source_size_bytes",
        "source_format",
        "format_status",
        "licence",
        "licence_status",
    }
)
_PRIVATE_REFERENCE_FIELDS = frozenset(
    {
        "source_path",
        "source_uri",
        "source_sha256",
        "source_format",
        "source_size_bytes",
        "format_status",
        "licence",
        "licence_spdx",
        "licence_status",
        "provenance_status",
        "fixture_exception",
        "dataset",
        "category",
        "topology_status",
        "complexity_quantile",
    }
)


class CohortFreezeError(ValueError):
    """Raised when an input or cross-artifact invariant fails closed."""


@dataclass(frozen=True)
class FrozenCohort:
    """Complete in-memory G1 freeze result.

    ``selection_manifest``, ``selected_records``, ``reserve_records`` and
    ``private_split`` are private custody artifacts.  Only ``custody_public``,
    ``custody_visible`` and ``visible_milestones`` may cross the corresponding
    release boundary before blind unlock.
    """

    selection_manifest: Mapping[str, Any]
    selected_records: tuple[Mapping[str, Any], ...]
    reserve_records: tuple[Mapping[str, Any], ...]
    private_split: Mapping[str, Any]
    custody_public: Mapping[str, Any]
    custody_visible: Mapping[str, Any]
    visible_milestones: Mapping[str, tuple[str, ...]]
    milestone_manifest: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return an independent JSON-compatible copy of every artifact."""

        return copy.deepcopy(
            {
                "selection_manifest": dict(self.selection_manifest),
                "selected_records": list(self.selected_records),
                "reserve_records": list(self.reserve_records),
                "private_split": dict(self.private_split),
                "custody_public": dict(self.custody_public),
                "custody_visible": dict(self.custody_visible),
                "visible_milestones": dict(self.visible_milestones),
                "milestone_manifest": dict(self.milestone_manifest),
            }
        )


def _require_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_DIGITS for character in value)
    ):
        raise CohortFreezeError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _require_256_bit_hex(value: Any, *, field: str, secret: bool) -> tuple[str, bytes]:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_DIGITS for character in value)
    ):
        raise CohortFreezeError(f"{field} must encode exactly 256 bits as lowercase hex")
    raw = bytes.fromhex(value)
    if secret:
        periodic = any(raw == raw[:period] * (len(raw) // period) for period in (1, 2, 4, 8, 16))
        printable_ascii = all(0x20 <= byte <= 0x7E for byte in raw)
        if periodic or len(set(raw)) < 16 or printable_ascii:
            raise CohortFreezeError(
                f"{field} appears weak; provide 32 random bytes from a secure secret manager"
            )
    return value, raw


def _normalise_targets(
    exact_targets: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    if not isinstance(exact_targets, Mapping) or set(exact_targets) != set(DEFAULT_TARGETS):
        raise CohortFreezeError(f"exact_targets must define exactly {sorted(DEFAULT_TARGETS)}")
    normalised: dict[str, dict[str, int]] = {}
    aggregate = Counter({split: 0 for split in _SPLITS})
    for stratum in sorted(DEFAULT_TARGETS):
        target = exact_targets[stratum]
        if not isinstance(target, Mapping) or set(target) != {"total", *_SPLITS}:
            raise CohortFreezeError(
                f"exact_targets.{stratum} must define total and all three splits"
            )
        parsed: dict[str, int] = {}
        for name in ("total", *_SPLITS):
            value = target[name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CohortFreezeError(
                    f"exact_targets.{stratum}.{name} must be a non-negative integer"
                )
            parsed[name] = value
        if parsed["total"] != DEFAULT_TARGETS[stratum]:
            raise CohortFreezeError(
                f"exact_targets.{stratum}.total must equal the frozen P0 target "
                f"{DEFAULT_TARGETS[stratum]}"
            )
        if parsed["total"] != sum(parsed[split] for split in _SPLITS):
            raise CohortFreezeError(f"exact_targets.{stratum} does not sum to total")
        for split in _SPLITS:
            aggregate[split] += parsed[split]
        normalised[stratum] = parsed
    if sum(target["total"] for target in normalised.values()) != SELECTED_TOTAL:
        raise CohortFreezeError(f"exact targets must select exactly {SELECTED_TOTAL} lineages")
    if normalised["objaverse"]["blind"] < OBJAVERSE_OOD_TOTAL:
        raise CohortFreezeError("Objaverse blind target cannot contain the 60-lineage OOD set")
    if aggregate != Counter({"development": 500, "calibration": 200, "blind": 300}):
        raise CohortFreezeError("exact targets must preserve the frozen 500/200/300 split")
    if normalised != FROZEN_EXACT_TARGETS:
        raise CohortFreezeError("exact targets must equal every frozen P0 stratum/split quota")
    return normalised


def _safe_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    materialised: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise CohortFreezeError(f"record {index} must be a mapping")
        try:
            canonical = canonicalise_corpus_registry_record(record)
        except (TypeError, ValueError) as error:
            raise CohortFreezeError(f"record {index}: {error}") from error
        safe = {
            field: copy.deepcopy(canonical[field])
            for field in _PRE_OUTCOME_FIELDS
            if field in canonical
        }
        if "bbox" in safe and safe["bbox"] is not None:
            bbox = safe["bbox"]
            if (
                not isinstance(bbox, Sequence)
                or isinstance(bbox, (str, bytes, bytearray))
                or len(bbox) != 6
            ):
                raise CohortFreezeError(
                    f"record {index}.bbox must contain exactly six finite numbers"
                )
            normalised_bbox: list[float] = []
            for coordinate in bbox:
                if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                    raise CohortFreezeError(
                        f"record {index}.bbox must contain exactly six finite numbers"
                    )
                try:
                    number = float(coordinate)
                except OverflowError as error:
                    raise CohortFreezeError(
                        f"record {index}.bbox contains a non-binary64 coordinate"
                    ) from error
                if not math.isfinite(number):
                    raise CohortFreezeError(
                        f"record {index}.bbox must contain only finite numbers"
                    )
                if isinstance(coordinate, int) and int(number) != coordinate:
                    raise CohortFreezeError(
                        f"record {index}.bbox integer is not exactly representable as binary64"
                    )
                normalised_bbox.append(number)
            safe["bbox"] = normalised_bbox
        missing = _SPLIT_REQUIRED_FIELDS - set(safe)
        if missing:
            raise CohortFreezeError(f"record {index} missing fields: {sorted(missing)}")
        materialised.append(safe)
    return materialised


def _validate_g1_records(rows: Sequence[Mapping[str, Any]]) -> None:
    required_strings = (
        "lineage_id",
        "leakage_group_id",
        "selection_stratum",
        "dataset",
        "category",
        "creator_group",
        "source_uid",
        "source_uri",
        "source_format",
        "format_status",
        "licence",
        "licence_status",
    )
    lawful_statuses = {"LAWFUL_INTERNAL_USE", "REDISTRIBUTABLE"}
    for index, row in enumerate(rows):
        for field in required_strings:
            if not isinstance(row.get(field), str) or not str(row[field]).strip():
                raise CohortFreezeError(f"record {index}.{field} must be a non-empty string")
        if not str(row["format_status"]).startswith("P2A_"):
            raise CohortFreezeError(f"record {index}.format_status must be a sealed P2a status")
        if row.get("eligibility") != "ELIGIBLE":
            raise CohortFreezeError(f"record {index} is not ELIGIBLE for the G1 census")
        _require_sha256(row.get("source_sha256"), field=f"record {index}.source_sha256")
        if row.get("topology_status") not in {"V", "O", "N", "U"}:
            raise CohortFreezeError(f"record {index}.topology_status must be V, O, N or U")
        quantile = row.get("complexity_quantile")
        if isinstance(quantile, bool) or not isinstance(quantile, int) or not 0 <= quantile <= 9:
            raise CohortFreezeError(
                f"record {index}.complexity_quantile must be an integer from 0 to 9"
            )
        source_size = row.get("source_size_bytes")
        if isinstance(source_size, bool) or not isinstance(source_size, int) or source_size < 0:
            raise CohortFreezeError(
                f"record {index}.source_size_bytes must be a non-negative integer"
            )

        licence = row.get("licence")
        status = row.get("licence_status")
        if not isinstance(licence, str) or not licence.strip():
            raise CohortFreezeError(f"record {index} requires a recorded licence")

        if row["selection_stratum"] == "fixtures_C0_C9":
            exception = row.get("fixture_exception")
            if not isinstance(exception, Mapping):
                raise CohortFreezeError(f"record {index} requires a structured fixture_exception")
            if exception.get("kind") != "SYNTHETIC_PROTOCOL_FIXTURE":
                raise CohortFreezeError(f"record {index} has an invalid fixture exception kind")
            for field in ("case_id", "generator_id", "generator_version"):
                if not isinstance(exception.get(field), str) or not exception[field].strip():
                    raise CohortFreezeError(
                        f"record {index}.fixture_exception.{field} must be non-empty"
                    )
            if status != "FIXTURE_GENERATED":
                raise CohortFreezeError(
                    f"record {index} fixture licence_status must be FIXTURE_GENERATED"
                )
        else:
            if "fixture_exception" in row:
                raise CohortFreezeError(
                    f"record {index} uses a fixture exception outside fixtures_C0_C9"
                )
            if status not in lawful_statuses:
                raise CohortFreezeError(
                    f"record {index}.licence_status must establish lawful internal use"
                )


def _canonical_record_payload(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def committed_record(row: Mapping[str, Any]) -> dict[str, Any]:
        """Return a no-float commitment payload for one P2a record.

        Custody hashes use the deliberately restricted integer-only JCS domain.
        A source-space bounding box is nevertheless useful in the private P2a
        record, so its finite binary64 values are committed through their exact
        hexadecimal representation instead of being dropped or admitted as
        implementation-dependent JSON numbers.
        """

        committed = copy.deepcopy(dict(row))
        bbox = committed.pop("bbox", None)
        if bbox is not None:
            if (
                not isinstance(bbox, Sequence)
                or isinstance(bbox, (str, bytes, bytearray))
                or len(bbox) != 6
            ):
                raise CohortFreezeError("bbox must contain exactly six finite numbers")
            encoded: list[str] = []
            for value in bbox:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise CohortFreezeError("bbox must contain exactly six finite numbers")
                number = float(value)
                if not math.isfinite(number):
                    raise CohortFreezeError("bbox must contain only finite numbers")
                encoded.append(number.hex())
            committed["bbox_binary64_hex"] = encoded
        return committed

    return {
        "algorithm_id": "MVX-P2A-ELIGIBLE-RECORDS-JCS-BINARY64-1",
        "records": sorted(
            (committed_record(row) for row in rows),
            key=lambda row: (str(row["lineage_id"]), str(row["leakage_group_id"])),
        ),
    }


def eligible_records_sha256(records: Iterable[Mapping[str, Any]]) -> str:
    """Commit the exact, outcome-filtered P2a eligible-record sequence.

    The returned digest is input-order invariant.  It must be sealed by P2a and
    supplied back to :func:`freeze_cohort`; recomputing it after a mutation does
    not constitute independent custody.
    """

    rows = _safe_records(records)
    _validate_g1_records(rows)
    return sha256_hex(_canonical_record_payload(rows))


def _code_constant(value: Any) -> Any:
    if isinstance(value, types.CodeType):
        return _code_object_payload(value)
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, tuple):
        return {"tuple": [_code_constant(item) for item in value]}
    if isinstance(value, frozenset):
        children = [_code_constant(item) for item in value]
        return {"frozenset": sorted(children, key=canonical_json_bytes)}
    if isinstance(value, float):
        return {"float_hex": value.hex()}
    if isinstance(value, (str, int, bool, type(None))):
        return value
    return {"type": type(value).__qualname__, "repr": repr(value)}


def _code_object_payload(code: types.CodeType) -> dict[str, Any]:
    """Return execution-state-independent semantics for one code object."""

    return {
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "bytecode_hex": code.co_code.hex(),
        "constants": [_code_constant(value) for value in code.co_consts],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
    }


def _callable_code_sha256(function: Any) -> str:
    """Hash loaded function semantics without filesystem I/O or quickening state."""

    return sha256_hex(_code_object_payload(function.__code__))


def _code_hashes() -> dict[str, str]:
    return {
        "freeze_cohort_sha256": _callable_code_sha256(freeze_cohort),
        "select_cohort_sha256": _callable_code_sha256(select_cohort),
        "select_visible_milestones_sha256": _callable_code_sha256(select_visible_milestones),
        "build_split_manifest_sha256": _callable_code_sha256(build_split_manifest),
        "create_custody_release_sha256": _callable_code_sha256(create_custody_release),
    }


def _reserve_counts(
    reserve_lineages: Sequence[str], by_lineage: Mapping[str, Mapping[str, Any]]
) -> dict[str, int]:
    counts = Counter(str(by_lineage[lineage]["selection_stratum"]) for lineage in reserve_lineages)
    return {stratum: counts[stratum] for stratum in sorted(DEFAULT_TARGETS)}


def _add_private_references(
    assignment: dict[str, Any], source_record: Mapping[str, Any]
) -> dict[str, Any]:
    enriched = dict(assignment)
    for field in sorted(_PRIVATE_REFERENCE_FIELDS):
        if field in source_record:
            enriched[field] = copy.deepcopy(source_record[field])
    return enriched


def _recursive_scalars(value: Any) -> set[Any]:
    scalars: set[Any] = set()
    if isinstance(value, Mapping):
        for child in value.values():
            scalars.update(_recursive_scalars(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            scalars.update(_recursive_scalars(child))
    elif isinstance(value, (str, int, float, bool, type(None))):
        scalars.add(value)
    return scalars


def _protected_values(private_split: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    identifiers: set[str] = set()
    paths: set[str] = set()
    for row in private_split["assignments"]:
        if row["split"] not in {"blind", "reserve"}:
            continue
        for field, value in row.items():
            if not isinstance(value, str) or not value:
                continue
            if field in {"lineage_id", "leakage_group_id", "source_uid", "creator_group"}:
                identifiers.add(value)
            if "path" in field or field.endswith("_uri"):
                paths.add(value)
    return identifiers, paths


def _assert_redacted(
    private_split: Mapping[str, Any],
    public_manifest: Mapping[str, Any],
    visible_manifest: Mapping[str, Any],
    milestones: Mapping[str, Sequence[str]],
) -> None:
    identifiers, paths = _protected_values(private_split)
    released = {
        "public": public_manifest,
        "visible": visible_manifest,
        "milestones": milestones,
    }
    released_scalars = _recursive_scalars(released)
    leaked_identifiers = sorted(identifiers & released_scalars)
    if leaked_identifiers:
        raise CohortFreezeError(
            f"custody release leaks blind/reserve identifiers: {leaked_identifiers[:3]}"
        )
    released_json = canonical_json_bytes(released).decode("utf-8")
    leaked_paths = sorted(path for path in paths if path in released_json)
    if leaked_paths:
        raise CohortFreezeError(f"custody release leaks blind/reserve paths: {leaked_paths[:3]}")


def _validate_frozen(
    frozen: FrozenCohort,
    *,
    exact_targets: Mapping[str, Mapping[str, int]],
) -> None:
    selection = frozen.selection_manifest
    private_split = frozen.private_split
    public = frozen.custody_public
    visible = frozen.custody_visible
    milestones = frozen.visible_milestones
    milestone_manifest = frozen.milestone_manifest

    for field in (
        "protocol_root_sha256",
        "snapshot_sha256",
        "selection_seed_sha256",
        "precommit_sha256",
        "publication_receipt_sha256",
    ):
        _require_sha256(selection.get(field), field=f"selection_manifest.{field}")
    if not isinstance(selection.get("freeze_id"), str) or not selection["freeze_id"].startswith(
        "mvx-g1-"
    ):
        raise CohortFreezeError("selection manifest freeze_id is invalid")
    for field, value in selection["hashes"].items():
        _require_sha256(value, field=f"selection_manifest.hashes.{field}")
    for field, value in selection["code_hashes"].items():
        _require_sha256(value, field=f"selection_manifest.code_hashes.{field}")
    if selection.get("schema_version") != SELECTION_SCHEMA_VERSION:
        raise CohortFreezeError("selection manifest has an unsupported schema version")
    if selection.get("visibility") != "PRIVATE_CUSTODY_ONLY":
        raise CohortFreezeError("selection manifest must remain private")
    if selection.get("algorithm_id") != SELECTION_ALGORITHM_ID:
        raise CohortFreezeError("selection manifest algorithm differs from the frozen protocol")
    if selection.get("freeze_algorithm_id") != FREEZE_ALGORITHM_ID:
        raise CohortFreezeError("selection manifest freeze algorithm is invalid")

    selected = tuple(selection["selected_lineages"])
    reserve = tuple(selection["reserve_lineages"])
    if len(selected) != SELECTED_TOTAL or len(set(selected)) != SELECTED_TOTAL:
        raise CohortFreezeError("selection manifest must contain 1000 unique selected lineages")
    if len(set(reserve)) != len(reserve) or set(selected) & set(reserve):
        raise CohortFreezeError("selected and reserve lineage lists must be unique and disjoint")
    if sum(selection["selected_counts"].values()) != SELECTED_TOTAL:
        raise CohortFreezeError("selected_counts must sum to 1000")
    if selection["selected_counts"] != {
        stratum: exact_targets[stratum]["total"] for stratum in sorted(exact_targets)
    }:
        raise CohortFreezeError("selected_counts differ from exact targets")
    if sum(selection["reserve_counts"].values()) != len(reserve):
        raise CohortFreezeError("reserve_counts differ from reserve lineage list")
    if selection["hashes"]["selected_lineages_sha256"] != sha256_hex(list(selected)):
        raise CohortFreezeError("selected lineage-list hash is inconsistent")
    if selection["hashes"]["reserve_lineages_sha256"] != sha256_hex(list(reserve)):
        raise CohortFreezeError("reserve lineage-list hash is inconsistent")

    assignments = private_split["assignments"]
    assigned_ids = [str(row["lineage_id"]) for row in assignments]
    if len(assigned_ids) != len(set(assigned_ids)):
        raise CohortFreezeError("private split contains duplicate lineage IDs")
    assigned_by_split = Counter(str(row["split"]) for row in assignments)
    if set(assigned_ids) != set(selected) | set(reserve):
        raise CohortFreezeError("private split and selection manifest lineage sets differ")
    if {row["lineage_id"] for row in assignments if row["split"] == "reserve"} != set(reserve):
        raise CohortFreezeError("private split reserve assignments are inconsistent")
    if any(row["split"] == "reserve" for row in assignments if row["lineage_id"] in selected):
        raise CohortFreezeError("a selected lineage was assigned to reserve")
    if dict(private_split["counts"]) != {
        split: assigned_by_split[split]
        for split in ("development", "calibration", "blind", "reserve")
    }:
        raise CohortFreezeError("private split counts differ from assignment rows")
    if private_split.get("protocol_root_sha256") != selection["protocol_root_sha256"]:
        raise CohortFreezeError("private split and selection protocol roots differ")
    if private_split.get("freeze_id") != selection["freeze_id"]:
        raise CohortFreezeError("private split and selection freeze IDs differ")
    if private_split.get("precommit_sha256") != selection["precommit_sha256"]:
        raise CohortFreezeError("private split and selection precommit hashes differ")
    if (
        private_split.get("publication_receipt_sha256")
        != selection["publication_receipt_sha256"]
    ):
        raise CohortFreezeError("private split and selection publication receipts differ")
    if private_split.get("selection_seed_sha256") != selection["selection_seed_sha256"]:
        raise CohortFreezeError("private split and selection seed commitments differ")
    if private_split.get("snapshot_sha256") != selection["snapshot_sha256"]:
        raise CohortFreezeError("private split and selection snapshot hashes differ")
    if private_split.get("input_records_sha256") != selection["hashes"]["input_records_sha256"]:
        raise CohortFreezeError("private split and selection input hashes differ")
    if private_split.get("code_hashes") != selection["code_hashes"]:
        raise CohortFreezeError("private split and selection code hashes differ")
    actual_reserve_counts = Counter(
        str(row["selection_stratum"]) for row in assignments if row["split"] == "reserve"
    )
    if selection["reserve_counts"] != {
        stratum: actual_reserve_counts[stratum] for stratum in sorted(DEFAULT_TARGETS)
    }:
        raise CohortFreezeError("reserve counts differ across private artifacts")

    selected_rows = [row for row in assignments if row["lineage_id"] in set(selected)]
    actual_by_stratum_split = Counter(
        (str(row["selection_stratum"]), str(row["split"])) for row in selected_rows
    )
    for stratum, target in exact_targets.items():
        for split in _SPLITS:
            if actual_by_stratum_split[(stratum, split)] != target[split]:
                raise CohortFreezeError(f"exact split mismatch for {stratum}.{split}")

    ood_rows = [row for row in assignments if row.get("blind_scope") == "OOD"]
    if len(ood_rows) != OBJAVERSE_OOD_TOTAL:
        raise CohortFreezeError("the private split must contain exactly 60 OOD lineages")
    if selection.get("ood_lineage_count") != len(ood_rows):
        raise CohortFreezeError("selection OOD count differs from the private split")
    if any(row["split"] != "blind" or row["selection_stratum"] != "objaverse" for row in ood_rows):
        raise CohortFreezeError("every OOD lineage must be blind Objaverse")
    ood_categories = set(selection["ood_categories"])
    if {str(row["category"]) for row in ood_rows} != ood_categories:
        raise CohortFreezeError("OOD category identities differ across artifacts")
    if any(
        row["category"] in ood_categories and row.get("blind_scope") != "OOD" for row in assignments
    ):
        raise CohortFreezeError("an OOD category appears outside the OOD blind set")
    for row in assignments:
        expected_scope = "NONE"
        if row["split"] == "blind":
            expected_scope = "IID" if row["selection_stratum"] == "objaverse" else "TRANSFER"
            if row.get("blind_scope") == "OOD":
                expected_scope = "OOD"
        if row.get("blind_scope") != expected_scope:
            raise CohortFreezeError(
                f"invalid blind_scope for lineage {row['lineage_id']!r}: expected {expected_scope}"
            )

    if selection["hashes"]["private_split_sha256"] != sha256_hex(private_split):
        raise CohortFreezeError("private split hash is inconsistent")
    commitment = public.get("private_manifest_commitment_sha256")
    if (
        not isinstance(commitment, str)
        or visible.get("private_manifest_commitment_sha256") != commitment
    ):
        raise CohortFreezeError("custody commitments differ between public and visible views")
    if selection["private_manifest_commitment_sha256"] != commitment:
        raise CohortFreezeError("selection and custody commitments are inconsistent")
    if public.get("counts") != dict(private_split["counts"]):
        raise CohortFreezeError("public custody counts differ from the private split")
    if (
        public.get("protocol_root_sha256") != selection["protocol_root_sha256"]
        or visible.get("protocol_root_sha256") != selection["protocol_root_sha256"]
    ):
        raise CohortFreezeError("custody and selection protocol roots differ")
    for artifact_name, artifact in (("public", public), ("visible", visible)):
        if artifact.get("freeze_id") != selection["freeze_id"]:
            raise CohortFreezeError(f"{artifact_name} custody freeze ID differs")
        if artifact.get("precommit_sha256") != selection["precommit_sha256"]:
            raise CohortFreezeError(f"{artifact_name} custody precommit hash differs")
        if (
            artifact.get("publication_receipt_sha256")
            != selection["publication_receipt_sha256"]
        ):
            raise CohortFreezeError(f"{artifact_name} custody publication receipt differs")
    if public.get("selection_seed_commitment_sha256") != selection["selection_seed_sha256"]:
        raise CohortFreezeError("public selection commitment differs from selection manifest")
    if public.get("split_salt_commitment_sha256") != private_split.get("salt_sha256"):
        raise CohortFreezeError("public split commitment differs from private split")

    visible_rows = visible.get("assignments")
    if not isinstance(visible_rows, list) or any(
        row.get("split") not in {"development", "calibration"} for row in visible_rows
    ):
        raise CohortFreezeError("visible custody contains a blind or reserve assignment")
    expected_visible = {
        row["lineage_id"] for row in assignments if row["split"] in {"development", "calibration"}
    }
    if {row["lineage_id"] for row in visible_rows} != expected_visible:
        raise CohortFreezeError("visible custody is not the exact development/calibration view")

    if set(milestones) != set(MILESTONE_SIZES):
        raise CohortFreezeError("visible milestones must be exactly n12/n30/n100/n300")
    prior: set[str] = set()
    for name in ("n12", "n30", "n100", "n300"):
        lineage_ids = tuple(milestones[name])
        if len(lineage_ids) != MILESTONE_SIZES[name] or len(set(lineage_ids)) != len(lineage_ids):
            raise CohortFreezeError(f"milestone {name} has an invalid size or duplicate")
        if not prior.issubset(lineage_ids) or not set(lineage_ids).issubset(expected_visible):
            raise CohortFreezeError(f"milestone {name} is not a nested visible subset")
        prior = set(lineage_ids)
    if milestone_manifest.get("schema_version") != "0.1.0":
        raise CohortFreezeError("visible milestone manifest schema version is invalid")
    if milestone_manifest.get("visibility") != "DEVELOPMENT_CALIBRATION_ONLY":
        raise CohortFreezeError("visible milestone manifest visibility is invalid")
    if milestone_manifest.get("algorithm_id") != VISIBLE_MILESTONE_ALGORITHM_ID:
        raise CohortFreezeError("visible milestone manifest algorithm is invalid")
    if milestone_manifest.get("algorithm_version") != VISIBLE_MILESTONE_ALGORITHM_VERSION:
        raise CohortFreezeError("visible milestone manifest algorithm version is invalid")
    if milestone_manifest.get("protocol_root_sha256") != selection["protocol_root_sha256"]:
        raise CohortFreezeError("visible milestone manifest protocol root differs")
    if milestone_manifest.get("freeze_id") != selection["freeze_id"]:
        raise CohortFreezeError("visible milestone manifest freeze ID differs")
    if milestone_manifest.get("precommit_sha256") != selection["precommit_sha256"]:
        raise CohortFreezeError("visible milestone manifest precommit hash differs")
    if (
        milestone_manifest.get("publication_receipt_sha256")
        != selection["publication_receipt_sha256"]
    ):
        raise CohortFreezeError("visible milestone publication receipt differs")
    if milestone_manifest.get("selection_seed_sha256") != selection["selection_seed_sha256"]:
        raise CohortFreezeError("visible milestone manifest selection commitment differs")
    if milestone_manifest.get("private_manifest_commitment_sha256") != commitment:
        raise CohortFreezeError("visible milestone manifest custody commitment differs")
    if milestone_manifest.get("milestones") != {
        name: list(lineages) for name, lineages in milestones.items()
    }:
        raise CohortFreezeError("visible milestone manifest payload differs")
    if selection["hashes"]["visible_milestones_sha256"] != sha256_hex(milestone_manifest):
        raise CohortFreezeError("visible milestone hash is inconsistent")

    _assert_redacted(private_split, public, visible, milestones)


def _freeze_cohort_impl(
    records: Iterable[Mapping[str, Any]],
    *,
    protocol_root_sha256: str,
    snapshot_sha256: str,
    expected_input_records_sha256: str,
    selection_seed_hex: str,
    split_secret_hex: str,
    exact_targets: Mapping[str, Mapping[str, int]],
    precommit: Mapping[str, Any],
    publication_receipt: Mapping[str, Any] | None = None,
    trusted_publishers: Mapping[str, Any] | None = None,
    allow_synthetic_receipt: bool = False,
    allow_public_test_secrets: bool = False,
) -> FrozenCohort:
    """Freeze an exact 1,000-lineage cohort, reserve, split and custody release.

    The function is deterministic and input-order invariant.  It accepts only
    pre-outcome source metadata through an explicit allow-list, so additional
    reconstruction scores, terminal states or timings cannot change any output.
    Invalid hashes, secrets, quotas, atomic groups, OOD reservations, custody
    commitments or redaction boundaries raise :class:`CohortFreezeError` (or a
    more specific validation ``ValueError`` from the underlying algorithm).
    """

    protocol_root = _require_sha256(protocol_root_sha256, field="protocol_root_sha256")
    snapshot = _require_sha256(snapshot_sha256, field="snapshot_sha256")
    expected_input_hash = _require_sha256(
        expected_input_records_sha256, field="expected_input_records_sha256"
    )
    seed_hex, seed = _require_256_bit_hex(
        selection_seed_hex, field="selection_seed_hex", secret=True
    )
    split_hex, split_secret = _require_256_bit_hex(
        split_secret_hex, field="split_secret_hex", secret=True
    )
    try:
        seed = validate_secret_bytes(
            seed_hex, allow_public_test_secret=allow_public_test_secrets
        )
        split_secret = validate_secret_bytes(
            split_hex, allow_public_test_secret=allow_public_test_secrets
        )
    except ValueError as error:
        raise CohortFreezeError(f"production secret validation failed: {error}") from error
    if hmac.compare_digest(seed, split_secret):
        raise CohortFreezeError("selection seed and split secret must be independent")
    targets = _normalise_targets(exact_targets)
    configuration_hash = sha256_hex(targets)
    try:
        verified_precommit = verify_custody_precommit(
            precommit,
            protocol_root_sha256=protocol_root,
            snapshot_sha256=snapshot,
            eligible_records_sha256=expected_input_hash,
            configuration_sha256=configuration_hash,
            selection_seed=seed_hex,
            split_salt=split_hex,
            allow_public_test_secrets=allow_public_test_secrets,
        )
    except ValueError as error:
        raise CohortFreezeError(f"custody precommit verification failed: {error}") from error
    precommit_hash = sha256_hex(verified_precommit)
    freeze_id = verified_precommit["freeze_id"]
    try:
        if allow_synthetic_receipt and not allow_public_test_secrets:
            raise ValueError(
                "synthetic receipt mode is restricted to explicit public-test-secret runs"
            )
        if not allow_synthetic_receipt and trusted_publishers is not None:
            raise ValueError(
                "production trusted publisher registry cannot be supplied by the caller"
            )
        if allow_synthetic_receipt:
            verified_receipt = _validate_precommit_publication_receipt(
                publication_receipt,
                precommit=verified_precommit,
                trusted_publishers=trusted_publishers,
                allow_synthetic=True,
            )
        else:
            verified_receipt = validate_precommit_publication_receipt(
                publication_receipt,
                precommit=verified_precommit,
            )
    except ValueError as error:
        raise CohortFreezeError(
            f"precommit publication receipt verification failed: {error}"
        ) from error
    publication_receipt_hash = sha256_hex(verified_receipt)
    safe_rows = _safe_records(records)
    _validate_g1_records(safe_rows)
    actual_input_hash = sha256_hex(_canonical_record_payload(safe_rows))
    if not hmac.compare_digest(actual_input_hash, expected_input_hash):
        raise CohortFreezeError("eligible-record input differs from the sealed P2a commitment")

    result = select_cohort(
        safe_rows,
        selection_seed_hex=seed_hex,
        targets={stratum: target["total"] for stratum, target in targets.items()},
        objaverse_ood_target=OBJAVERSE_OOD_TOTAL,
    )
    if len(result.selected_lineages) != SELECTED_TOTAL:
        raise CohortFreezeError("cohort selection did not return exactly 1000 lineages")
    if set(result.selected_lineages) & set(result.reserve_lineages):
        raise CohortFreezeError("cohort selection returned overlapping selected and reserve sets")

    by_lineage: dict[str, dict[str, Any]] = {}
    for row in safe_rows:
        lineage = str(row["lineage_id"])
        if lineage in by_lineage:
            raise CohortFreezeError(f"lineage {lineage!r} occurs more than once")
        by_lineage[lineage] = row

    split_inputs: list[dict[str, Any]] = []
    for lineage in result.selected_lineages:
        row = copy.deepcopy(by_lineage[lineage])
        forced = result.forced_split.get(lineage)
        row["forced_split"] = forced
        # IID is a candidate scope before assignment.  build_split_manifest
        # rewrites non-blind records to NONE and preserves OOD for forced blind.
        if forced == "blind":
            row["blind_scope"] = "OOD"
        elif row["selection_stratum"] == "objaverse":
            row["blind_scope"] = "IID"
        else:
            row["blind_scope"] = "TRANSFER"
        split_inputs.append(row)

    private_split = build_split_manifest(
        split_inputs,
        salt_hex=split_hex,
        protocol_root_sha256=protocol_root,
        exact_targets_by_stratum=targets,
    )
    selected_assignments: list[dict[str, Any]] = []
    for assignment in private_split["assignments"]:
        selected_assignments.append(
            _add_private_references(dict(assignment), by_lineage[str(assignment["lineage_id"])])
        )
    reserve_assignments: list[dict[str, Any]] = []
    for lineage in result.reserve_lineages:
        row = by_lineage[lineage]
        reserve_assignments.append(
            _add_private_references(
                {
                    "lineage_id": lineage,
                    "leakage_group_id": str(row["leakage_group_id"]),
                    "split": "reserve",
                    "selection_stratum": str(row["selection_stratum"]),
                    "blind_scope": "NONE",
                    "creator_group": str(row["creator_group"]),
                    "source_uid": str(row["source_uid"]),
                },
                row,
            )
        )
    private_split = copy.deepcopy(private_split)
    private_split["snapshot_sha256"] = snapshot
    private_split["input_records_sha256"] = actual_input_hash
    private_split["freeze_id"] = freeze_id
    private_split["precommit_sha256"] = precommit_hash
    private_split["publication_receipt_sha256"] = publication_receipt_hash
    private_split["selection_seed_sha256"] = verified_precommit["selection_seed_sha256"]
    private_split["code_hashes"] = _code_hashes()
    private_split["assignments"] = sorted(
        [*selected_assignments, *reserve_assignments], key=lambda row: str(row["lineage_id"])
    )
    private_split["counts"] = {
        split: sum(row["split"] == split for row in private_split["assignments"])
        for split in ("development", "calibration", "blind", "reserve")
    }

    release = create_custody_release(
        private_split,
        split_hex,
        allow_public_test_secret=allow_public_test_secrets,
    )
    custody_public = release["public_manifest"]
    custody_visible = release["visible_manifest"]
    milestones = select_visible_milestones(
        custody_visible["assignments"], selection_seed_hex=seed_hex
    )

    private_split_hash = sha256_hex(private_split)
    milestone_manifest = {
        "schema_version": "0.1.0",
        "visibility": "DEVELOPMENT_CALIBRATION_ONLY",
        "algorithm_id": VISIBLE_MILESTONE_ALGORITHM_ID,
        "algorithm_version": VISIBLE_MILESTONE_ALGORITHM_VERSION,
        "protocol_root_sha256": protocol_root,
        "freeze_id": freeze_id,
        "precommit_sha256": precommit_hash,
        "publication_receipt_sha256": publication_receipt_hash,
        "selection_seed_sha256": hashlib.sha256(seed).hexdigest(),
        "private_manifest_commitment_sha256": custody_public["private_manifest_commitment_sha256"],
        "milestones": {name: list(values) for name, values in milestones.items()},
    }
    milestones_hash = sha256_hex(milestone_manifest)
    selected_lineages = tuple(sorted(result.selected_lineages))
    reserve_lineages = tuple(sorted(result.reserve_lineages))
    selection_manifest = {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "visibility": "PRIVATE_CUSTODY_ONLY",
        "algorithm_id": SELECTION_ALGORITHM_ID,
        "algorithm_version": SELECTION_ALGORITHM_VERSION,
        "freeze_algorithm_id": FREEZE_ALGORITHM_ID,
        "protocol_root_sha256": protocol_root,
        "snapshot_sha256": snapshot,
        "freeze_id": freeze_id,
        "precommit_sha256": precommit_hash,
        "publication_receipt_sha256": publication_receipt_hash,
        "selection_seed_sha256": hashlib.sha256(seed).hexdigest(),
        "selected_counts": {
            stratum: result.selected_counts[stratum] for stratum in sorted(result.selected_counts)
        },
        "reserve_counts": _reserve_counts(reserve_lineages, by_lineage),
        "selected_lineages": list(selected_lineages),
        "reserve_lineages": list(reserve_lineages),
        "ood_categories": sorted(result.ood_categories),
        "ood_lineage_count": sum(scope == "OOD" for scope in result.blind_scope.values()),
        "private_manifest_commitment_sha256": custody_public["private_manifest_commitment_sha256"],
        "hashes": {
            "input_records_sha256": private_split["input_records_sha256"],
            "selected_lineages_sha256": sha256_hex(list(selected_lineages)),
            "reserve_lineages_sha256": sha256_hex(list(reserve_lineages)),
            "private_split_sha256": private_split_hash,
            "visible_milestones_sha256": milestones_hash,
        },
        "code_hashes": _code_hashes(),
    }

    assignment_by_lineage = {str(row["lineage_id"]): row for row in private_split["assignments"]}
    selected_records = tuple(
        {
            **copy.deepcopy(by_lineage[lineage]),
            "forced_split": result.forced_split.get(lineage),
            "split": assignment_by_lineage[lineage]["split"],
            "blind_scope": assignment_by_lineage[lineage]["blind_scope"],
        }
        for lineage in selected_lineages
    )
    reserve_records = tuple(
        {
            **copy.deepcopy(by_lineage[lineage]),
            "forced_split": None,
            "split": "reserve",
            "blind_scope": "NONE",
        }
        for lineage in reserve_lineages
    )
    frozen = FrozenCohort(
        selection_manifest=selection_manifest,
        selected_records=selected_records,
        reserve_records=reserve_records,
        private_split=private_split,
        custody_public=custody_public,
        custody_visible=custody_visible,
        visible_milestones={name: tuple(values) for name, values in milestones.items()},
        milestone_manifest=milestone_manifest,
    )
    _validate_frozen(frozen, exact_targets=targets)
    return frozen


def freeze_cohort(
    records: Iterable[Mapping[str, Any]],
    *,
    protocol_root_sha256: str,
    snapshot_sha256: str,
    expected_input_records_sha256: str,
    selection_seed_hex: str,
    split_secret_hex: str,
    exact_targets: Mapping[str, Mapping[str, int]],
    precommit: Mapping[str, Any],
    publication_receipt: Mapping[str, Any] | None = None,
) -> FrozenCohort:
    """Production G1 freeze with no caller-controlled trust or test bypass."""

    return _freeze_cohort_impl(
        records,
        protocol_root_sha256=protocol_root_sha256,
        snapshot_sha256=snapshot_sha256,
        expected_input_records_sha256=expected_input_records_sha256,
        selection_seed_hex=selection_seed_hex,
        split_secret_hex=split_secret_hex,
        exact_targets=exact_targets,
        precommit=precommit,
        publication_receipt=publication_receipt,
    )


__all__ = [
    "FREEZE_ALGORITHM_ID",
    "FROZEN_EXACT_TARGETS",
    "CohortFreezeError",
    "FrozenCohort",
    "eligible_records_sha256",
    "freeze_cohort",
]
