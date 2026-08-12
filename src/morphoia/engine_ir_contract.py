"""Strict schema and semantic validation for public Morphoia Engine IR 0.1.

This module deliberately does not implement canonical JSON or content hashing.
An authoritative identity requires the native Profile 1 implementation exposed
by the Morphoia Engine C ABI.  The helpers here validate already decoded
objects, or decode lexical input before JSON Schema and semantic validation.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker

MANIFEST_FORMAT = "morphoia.engine.ir-manifest"
MANIFEST_VERSION = "0.1.0"
MANIFEST_MEDIA_TYPE = "application/vnd.morphoia.ir-manifest.v0+json"
MANIFEST_SCHEMA_ID = "https://morphoia.org/schemas/engine/ir-manifest/0.1.0"
REPLAY_FORMAT = "morphoia.engine.ir-replay"
REPLAY_SCHEMA_ID = "https://morphoia.org/schemas/engine/ir-replay/0.1.0"
CANONICAL_PROFILE = "morphoia.canonical-json.profile1"

MAX_INPUT_BYTES = 1_048_576
MAX_STRING_BYTES = 262_144
MAX_VALUES = 100_000
MAX_DEPTH = 64
MAX_SAFE_INTEGER = 9_007_199_254_740_991

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UUIDV7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CAS_URI = re.compile(r"^morphoia-cas://sha256/([0-9a-f]{64})$")
_SPDX_LICENSE_REF = re.compile(
    r"(?:DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+"
)
_SPDX_LIST_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*(?:\+)?")


class ContractError(ValueError):
    """Base class for deterministic Engine IR contract rejection."""


class LexicalError(ContractError):
    """The JSON byte/string input is outside Canonical JSON Profile 1."""


class SchemaError(ContractError):
    """The decoded object does not match the closed Draft 2020-12 schema."""


class SemanticError(ContractError):
    """The object graph violates a cross-reference or authority invariant."""


def _reject_float(value: str) -> NoReturn:
    raise LexicalError(f"fractional or exponent JSON number is forbidden: {value}")


def _reject_constant(value: str) -> NoReturn:
    raise LexicalError(f"non-finite JSON number is forbidden: {value}")


def _parse_integer(value: str) -> int:
    parsed = int(value)
    if not -MAX_SAFE_INTEGER <= parsed <= MAX_SAFE_INTEGER:
        raise LexicalError("integer outside Canonical JSON Profile 1 range")
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LexicalError(f"duplicate decoded JSON object key: {key}")
        result[key] = value
    return result


def _check_profile_value(value: Any, *, path: str, depth: int, counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > MAX_VALUES:
        raise LexicalError(f"JSON value count exceeds {MAX_VALUES}")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise LexicalError(f"integer outside Canonical JSON Profile 1 range at {path}")
        return
    if isinstance(value, float):
        raise LexicalError(f"fractional JSON number is forbidden at {path}")
    if isinstance(value, str):
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise LexicalError(f"invalid Unicode scalar value at {path}") from exc
        if len(encoded) > MAX_STRING_BYTES:
            raise LexicalError(f"decoded string exceeds {MAX_STRING_BYTES} bytes at {path}")
        return
    if isinstance(value, Mapping):
        if depth + 1 > MAX_DEPTH:
            raise LexicalError(f"JSON nesting exceeds {MAX_DEPTH} at {path}")
        for key, item in value.items():
            if not isinstance(key, str):
                raise LexicalError(f"JSON object key is not a string at {path}")
            try:
                encoded_key = key.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise LexicalError(f"invalid Unicode scalar value at {path}.<key>") from exc
            if len(encoded_key) > MAX_STRING_BYTES:
                raise LexicalError(
                    f"decoded string exceeds {MAX_STRING_BYTES} bytes at {path}.<key>"
                )
            _check_profile_value(item, path=f"{path}.{key}", depth=depth + 1, counter=counter)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if depth + 1 > MAX_DEPTH:
            raise LexicalError(f"JSON nesting exceeds {MAX_DEPTH} at {path}")
        for index, item in enumerate(value):
            _check_profile_value(
                item,
                path=f"{path}[{index}]",
                depth=depth + 1,
                counter=counter,
            )
        return
    raise LexicalError(f"unsupported JSON value type at {path}: {type(value).__name__}")


def load_json_strict(document: str | bytes) -> dict[str, Any]:
    """Decode one bounded Profile 1 JSON object without repairing input.

    Duplicate decoded keys, malformed UTF-8, floats, exponents, non-finite
    numbers, unsafe integers, lone surrogates, excessive depth, excessive value
    count, and non-object roots are rejected before schema validation.
    """

    if isinstance(document, bytes):
        if len(document) > MAX_INPUT_BYTES:
            raise LexicalError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes")
        try:
            text = document.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise LexicalError("JSON input must be shortest-form valid UTF-8") from exc
    elif isinstance(document, str):
        try:
            encoded = document.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise LexicalError("JSON input contains an invalid Unicode scalar value") from exc
        if len(encoded) > MAX_INPUT_BYTES:
            raise LexicalError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes")
        text = document
    else:
        raise TypeError("document must be str or bytes")

    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_int=_parse_integer,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except LexicalError:
        raise
    except json.JSONDecodeError as exc:
        raise LexicalError(f"invalid JSON at line {exc.lineno} column {exc.colno}") from exc
    except RecursionError as exc:
        raise LexicalError("JSON nesting exceeds the decoder limit") from exc
    if not isinstance(value, dict):
        raise LexicalError("Engine IR JSON root must be an object")
    _check_profile_value(value, path="$", depth=0, counter=[0])
    return value


def _schema_candidates(filename: str) -> tuple[Path, ...]:
    source_tree = Path(__file__).resolve().parents[2] / "schemas" / filename
    installed = Path(sys.prefix) / "share" / "morphoia" / "schemas" / filename
    return source_tree, installed


def _resolve_schema(filename: str, explicit: Path | None) -> Path:
    candidates = (explicit,) if explicit is not None else _schema_candidates(filename)
    for candidate in candidates:
        assert candidate is not None
        if candidate.is_file():
            return candidate
    rendered = ", ".join(str(item) for item in candidates)
    raise SchemaError(f"Engine IR schema is unavailable: {rendered}")


@lru_cache(maxsize=8)
def _load_schema(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SchemaError(f"cannot read Engine IR schema: {path}") from exc
    try:
        schema = load_json_strict(raw)
    except ContractError as exc:
        raise SchemaError(f"Engine IR schema is not strict JSON: {path}") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise SchemaError(f"Engine IR schema is not valid Draft 2020-12: {path}") from exc
    return schema


def _json_path(parts: Sequence[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result


def _validate_schema(document: Mapping[str, Any], filename: str, explicit: Path | None) -> None:
    path = _resolve_schema(filename, explicit)
    validator = Draft202012Validator(
        _load_schema(str(path.resolve())),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: ([str(item) for item in error.absolute_path], error.message),
    )
    if errors:
        first = errors[0]
        raise SchemaError(f"schema rejection at {_json_path(first.absolute_path)}: {first.message}")


def _ensure_uuid(value: str, *, path: str) -> None:
    if not _UUIDV7.fullmatch(value):
        raise SemanticError(f"invalid lowercase UUIDv7 at {path}")


def _ensure_digest(value: str, *, path: str) -> None:
    if not _SHA256.fullmatch(value):
        raise SemanticError(f"invalid lowercase SHA-256 at {path}")


def _require_external_identity(identity_digest: str | None) -> str:
    if identity_digest is None:
        raise SemanticError(
            "authoritative manifest validation requires a native Profile 1 content digest"
        )
    _ensure_digest(identity_digest, path="identity_digest")
    return identity_digest


def _validate_binary_reference(reference: Mapping[str, Any], *, path: str) -> None:
    digest = reference["sha256"]
    match = _CAS_URI.fullmatch(reference["uri"])
    if match is None or match.group(1) != digest:
        raise SemanticError(f"CAS URI and SHA-256 differ at {path}")


def _validate_spdx_syntax(expression: str, *, path: str) -> None:
    """Validate bounded SPDX 2.3 Annex D syntax without a registry lookup."""

    tokens: list[tuple[str, str]] = []
    offset = 0
    while offset < len(expression):
        while offset < len(expression) and expression[offset] in " \t":
            offset += 1
        if offset == len(expression):
            break
        character = expression[offset]
        if character == "(":
            tokens.append(("left-parenthesis", character))
            offset += 1
            continue
        if character == ")":
            tokens.append(("right-parenthesis", character))
            offset += 1
            continue
        reference = _SPDX_LICENSE_REF.match(expression, offset)
        if reference is not None:
            tokens.append(("license-reference", reference.group(0)))
            offset = reference.end()
            continue
        identifier = _SPDX_LIST_IDENTIFIER.match(expression, offset)
        if identifier is None:
            raise SemanticError(f"invalid SPDX expression syntax at {path}")
        value = identifier.group(0)
        if value in {"AND", "OR", "WITH"}:
            tokens.append((value, value))
        elif value.startswith(("LicenseRef-", "DocumentRef-", "AdditionRef-")):
            # Do not allow malformed reserved references to fall back to a
            # generic license-list identifier.
            raise SemanticError(f"invalid SPDX reference syntax at {path}")
        else:
            tokens.append(("list-identifier", value))
        offset = identifier.end()
    if not tokens:
        raise SemanticError(f"empty SPDX expression at {path}")

    position = 0

    def parse_primary() -> bool:
        """Parse one primary and report whether it is an ungrouped simple expression."""

        nonlocal position
        if position >= len(tokens):
            raise SemanticError(f"incomplete SPDX expression at {path}")
        kind, _value = tokens[position]
        if kind == "left-parenthesis":
            position += 1
            parse_or()
            if position >= len(tokens) or tokens[position][0] != "right-parenthesis":
                raise SemanticError(f"unbalanced SPDX expression at {path}")
            position += 1
            return False
        if kind not in {"list-identifier", "license-reference"}:
            raise SemanticError(f"invalid SPDX expression operand at {path}")
        position += 1
        return True

    def parse_with() -> None:
        nonlocal position
        simple = parse_primary()
        if position < len(tokens) and tokens[position][0] == "WITH":
            if not simple:
                raise SemanticError(
                    f"SPDX WITH left operand must be a simple expression at {path}"
                )
            position += 1
            if position >= len(tokens) or tokens[position][0] != "list-identifier":
                raise SemanticError(f"invalid SPDX exception at {path}")
            if tokens[position][1].endswith("+"):
                raise SemanticError(f"invalid SPDX exception at {path}")
            position += 1

    def parse_and() -> None:
        nonlocal position
        parse_with()
        while position < len(tokens) and tokens[position][0] == "AND":
            position += 1
            parse_with()

    def parse_or() -> None:
        nonlocal position
        parse_and()
        while position < len(tokens) and tokens[position][0] == "OR":
            position += 1
            parse_and()

    parse_or()
    if position != len(tokens):
        raise SemanticError(f"unexpected token in SPDX expression at {path}")


def _exact_fraction(value: Mapping[str, int]) -> Fraction:
    coefficient = value["coefficient"]
    scale = value["scale"]
    if scale >= 0:
        return Fraction(coefficient * (10**scale), 1)
    return Fraction(coefficient, 10 ** (-scale))


def _determinant(matrix: Sequence[int | Fraction], dimension: int) -> int | Fraction:
    if dimension == 2:
        return matrix[0] * matrix[3] - matrix[1] * matrix[2]
    return (
        matrix[0] * (matrix[4] * matrix[8] - matrix[5] * matrix[7])
        - matrix[1] * (matrix[3] * matrix[8] - matrix[5] * matrix[6])
        + matrix[2] * (matrix[3] * matrix[7] - matrix[4] * matrix[6])
    )


def _assert_unique_ids(groups: Sequence[tuple[str, Sequence[Mapping[str, Any]]]]) -> set[str]:
    declared: set[str] = set()
    for group_name, values in groups:
        for index, value in enumerate(values):
            identity = value["id"]
            _ensure_uuid(identity, path=f"$.content.{group_name}[{index}].id")
            if identity in declared:
                raise SemanticError(f"duplicate declared logical identifier: {identity}")
            declared.add(identity)
    return declared


def _assert_acyclic(parent_map: Mapping[str, Sequence[str]], *, label: str) -> None:
    indegree = {node: len(parents) for node, parents in parent_map.items()}
    children: dict[str, list[str]] = {node: [] for node in parent_map}
    for child, parents in parent_map.items():
        for parent in parents:
            children[parent].append(child)
    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node = ready.pop()
        visited += 1
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited != len(parent_map):
        unresolved = min(node for node, degree in indegree.items() if degree > 0)
        raise SemanticError(f"cycle detected in {label} DAG at {unresolved}")


def _parse_timestamp(value: str, *, path: str) -> datetime:
    if not value.endswith("Z"):
        raise SemanticError(f"date-time must use UTC Z at {path}")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise SemanticError(f"invalid date-time at {path}") from exc


def _semantic_manifest(document: Mapping[str, Any], identity_digest: str | None) -> None:
    content = document["content"]
    root_id = content["logical_id"]
    _ensure_uuid(root_id, path="$.content.logical_id")
    envelope_digest = document["identity"]["digest"]
    _ensure_digest(envelope_digest, path="$.identity.digest")
    native_identity = _require_external_identity(identity_digest)
    if native_identity != envelope_digest:
        raise SemanticError("native content identity does not match $.identity.digest")
    _parse_timestamp(content["source"]["created_at"], path="$.content.source.created_at")
    _validate_spdx_syntax(
        content["source"]["license_expression"],
        path="$.content.source.license_expression",
    )

    revision = content["revision"]
    parents = content["parents"]
    if revision == 1 and parents:
        raise SemanticError("revision 1 must not declare a parent revision")
    if revision > 1:
        if len(parents) != 1:
            raise SemanticError("Engine IR 0.1 uses exactly one linear parent revision")
        parent = parents[0]
        if parent["logical_id"] != root_id:
            raise SemanticError("parent revision belongs to a different logical identity")
        if parent["revision"] != revision - 1:
            raise SemanticError("parent revision must immediately precede the current revision")
        if parent["content_sha256"] == envelope_digest:
            raise SemanticError("parent revision cannot reuse the current content identity")

    product = content["product"]
    groups = (
        ("units", content["units"]),
        ("frames", content["frames"]),
        ("transforms", content["transforms"]),
        ("product.assemblies", product["assemblies"]),
        ("product.instances", product["instances"]),
        ("representations", content["representations"]),
        ("provenance", content["provenance"]),
        ("tolerances", content["tolerances"]),
        ("fidelity_events", content["fidelity_events"]),
        ("repairs", content["repairs"]),
        ("losses", content["losses"]),
    )
    declared = _assert_unique_ids(groups)
    if root_id in declared:
        raise SemanticError("root logical identifier collides with a declared child identifier")

    unit_ids = {item["id"] for item in content["units"]}
    frame_by_id = {item["id"]: item for item in content["frames"]}
    transform_ids = {item["id"] for item in content["transforms"]}
    for index, frame in enumerate(content["frames"]):
        dimension = frame["dimension"]
        if len(frame["origin"]) != dimension or len(frame["axes"]) != dimension * dimension:
            raise SemanticError(f"frame vector dimensions disagree at $.content.frames[{index}]")
        if frame["unit_id"] not in unit_ids:
            raise SemanticError(f"unknown frame unit at $.content.frames[{index}].unit_id")
        axes = frame["axes"]
        rows = [axes[row * dimension : (row + 1) * dimension] for row in range(dimension)]
        if any(sum(component * component for component in row) != 1 for row in rows):
            raise SemanticError(f"frame axes are not a signed basis at $.content.frames[{index}]")
        if any(
            sum(rows[left][column] * rows[right][column] for column in range(dimension)) != 0
            for left in range(dimension)
            for right in range(left + 1, dimension)
        ):
            raise SemanticError(f"frame axes are not orthogonal at $.content.frames[{index}]")
        determinant = _determinant(axes, dimension)
        expected_sign = 1 if frame["handedness"] == "right" else -1
        if determinant != expected_sign:
            raise SemanticError(f"frame handedness disagrees with axes at $.content.frames[{index}]")

    for index, unit in enumerate(content["units"]):
        if unit["si_factor"]["coefficient"] <= 0:
            raise SemanticError(f"SI factor must be positive at $.content.units[{index}]")

    transform_pairs: set[tuple[str, str]] = set()
    for index, transform in enumerate(content["transforms"]):
        source = frame_by_id.get(transform["from_frame"])
        target = frame_by_id.get(transform["to_frame"])
        if source is None or target is None:
            raise SemanticError(f"unknown transform frame at $.content.transforms[{index}]")
        if source["id"] == target["id"]:
            raise SemanticError(f"self transform is forbidden at $.content.transforms[{index}]")
        if source["dimension"] != target["dimension"]:
            raise SemanticError(f"transform frame dimensions differ at $.content.transforms[{index}]")
        expected = (source["dimension"] + 1) ** 2
        if len(transform["matrix"]) != expected:
            raise SemanticError(f"transform matrix size is not {expected} at $.content.transforms[{index}]")
        pair = (source["id"], target["id"])
        if pair in transform_pairs:
            raise SemanticError(f"duplicate transform frame pair at $.content.transforms[{index}]")
        transform_pairs.add(pair)
        side = source["dimension"] + 1
        values = [_exact_fraction(item) for item in transform["matrix"]]
        if transform["matrix_order"] == "row-major":
            matrix = [values[row * side : (row + 1) * side] for row in range(side)]
        else:
            matrix = [
                [values[column * side + row] for column in range(side)]
                for row in range(side)
            ]
        if matrix[-1][:-1] != [Fraction(0)] * source["dimension"] or matrix[-1][-1] != 1:
            raise SemanticError(f"transform is not an affine homogeneous matrix at $.content.transforms[{index}]")
        linear = [item for row in matrix[:-1] for item in row[:-1]]
        if _determinant(linear, source["dimension"]) == 0:
            raise SemanticError(f"transform spatial matrix is singular at $.content.transforms[{index}]")

    for path, reference in [("$.content.source.artifact", content["source"]["artifact"])]:
        _validate_binary_reference(reference, path=path)

    assembly_ids = {item["id"] for item in product["assemblies"]}
    assembly_parents: dict[str, list[str]] = {identity: [] for identity in assembly_ids}
    for index, assembly in enumerate(product["assemblies"]):
        parent = assembly.get("parent_id")
        if parent is not None:
            if parent not in assembly_ids:
                raise SemanticError(f"unknown assembly parent at $.content.product.assemblies[{index}]")
            assembly_parents[assembly["id"]].append(parent)
    _assert_acyclic(assembly_parents, label="assembly")

    instance_ids = {item["id"] for item in product["instances"]}
    instance_parents: dict[str, list[str]] = {identity: [] for identity in instance_ids}
    for index, instance in enumerate(product["instances"]):
        if instance["assembly_id"] not in assembly_ids:
            raise SemanticError(f"unknown instance assembly at $.content.product.instances[{index}]")
        parent = instance.get("parent_instance_id")
        if parent is not None:
            if parent not in instance_ids:
                raise SemanticError(f"unknown instance parent at $.content.product.instances[{index}]")
            instance_parents[instance["id"]].append(parent)
        transform = instance.get("transform_id")
        if transform is not None and transform not in transform_ids:
            raise SemanticError(f"unknown instance transform at $.content.product.instances[{index}]")
    _assert_acyclic(instance_parents, label="instance")

    representation_by_id = {item["id"]: item for item in content["representations"]}
    representation_ids = set(representation_by_id)
    derivation_parents: dict[str, list[str]] = {}
    for index, representation in enumerate(content["representations"]):
        path = f"$.content.representations[{index}]"
        if representation["unit_id"] not in unit_ids or representation["frame_id"] not in frame_by_id:
            raise SemanticError(f"unknown unit or frame at {path}")
        _validate_binary_reference(representation["payload"], path=f"{path}.payload")
        parents = representation["derived_from"]
        for parent in parents:
            if parent not in representation_ids:
                raise SemanticError(f"unknown representation parent at {path}.derived_from")
        if parents and representation["authority"] == "source":
            raise SemanticError(f"derived representation claims source authority at {path}")
        if not parents and representation["authority"] != "source":
            raise SemanticError(f"root representation lacks source authority at {path}")
        if representation["ai_output"] and (
            representation["authority"] != "candidate" or not parents
        ):
            raise SemanticError(f"AI output is not a revisable candidate branch at {path}")
        derivation_parents[representation["id"]] = list(parents)
    _assert_acyclic(derivation_parents, label="representation derivation")

    provenance_ids = {item["id"] for item in content["provenance"]}
    provenance_parents: dict[str, list[str]] = {}
    output_owner: dict[str, str] = {}
    event_times: dict[str, tuple[datetime, datetime]] = {}
    for index, event in enumerate(content["provenance"]):
        path = f"$.content.provenance[{index}]"
        for parent in event["parents"]:
            if parent not in provenance_ids:
                raise SemanticError(f"unknown provenance parent at {path}.parents")
        provenance_parents[event["id"]] = list(event["parents"])
        for item in event["inputs"]:
            if item not in representation_ids:
                raise SemanticError(f"unknown provenance input at {path}.inputs")
        for item in event["outputs"]:
            if item not in representation_ids:
                raise SemanticError(f"unknown provenance output at {path}.outputs")
            if item in output_owner:
                raise SemanticError(f"representation has multiple provenance producers: {item}")
            output_owner[item] = event["id"]
        started = _parse_timestamp(event["started_at"], path=f"{path}.started_at")
        ended = _parse_timestamp(event["ended_at"], path=f"{path}.ended_at")
        if ended < started:
            raise SemanticError(f"provenance end precedes start at {path}")
        event_times[event["id"]] = (started, ended)
    if set(output_owner) != representation_ids:
        missing = sorted(representation_ids - set(output_owner))
        raise SemanticError(f"representation lacks exactly one provenance producer: {missing[0]}")

    causal_parents: dict[str, list[str]] = {}
    for index, event in enumerate(content["provenance"]):
        path = f"$.content.provenance[{index}]"
        immediate = sorted({output_owner[item] for item in event["inputs"]})
        if event["id"] in immediate:
            raise SemanticError(f"provenance event consumes its own output at {path}.inputs")
        if sorted(event["parents"]) != immediate:
            raise SemanticError(
                f"provenance parents must exactly match input producers at {path}.parents"
            )
        causal_parents[event["id"]] = immediate
    _assert_acyclic(causal_parents, label="provenance")
    for index, event in enumerate(content["provenance"]):
        path = f"$.content.provenance[{index}]"
        consumer_started = event_times[event["id"]][0]
        for parent_id in causal_parents[event["id"]]:
            if event_times[parent_id][1] > consumer_started:
                raise SemanticError(f"provenance consumer starts before its producer ends at {path}")

    if content["security"]["signature"]["status"] == "verified":
        raise SemanticError(
            "verified signature requires an external cryptographic verification result"
        )
    if content["security"]["trust_level"] == "verified":
        raise SemanticError(
            "verified trust level requires an external trust-policy verification result"
        )

    event_by_output = {
        output: event
        for event in content["provenance"]
        for output in event["outputs"]
    }
    for representation in content["representations"]:
        if not set(representation["derived_from"]).issubset(event_by_output[representation["id"]]["inputs"]):
            raise SemanticError(
                f"provenance inputs omit derivation parents for {representation['id']}"
            )

    valid_subjects = representation_ids | assembly_ids | instance_ids
    for field in ("names", "colors", "layers", "properties"):
        for index, record in enumerate(product[field]):
            if record["subject_id"] not in valid_subjects:
                raise SemanticError(f"unknown product subject at $.content.product.{field}[{index}]")
    for field in ("tolerances", "fidelity_events", "repairs", "losses"):
        for index, record in enumerate(content[field]):
            if record["subject_id"] not in valid_subjects:
                raise SemanticError(f"unknown subject at $.content.{field}[{index}]")
            if field == "tolerances" and record["unit_id"] not in unit_ids:
                raise SemanticError(f"unknown tolerance unit at $.content.tolerances[{index}]")
            if field == "tolerances" and record["amount"]["coefficient"] < 0:
                raise SemanticError(f"negative tolerance amount at $.content.tolerances[{index}]")


def validate_manifest(
    document: Mapping[str, Any],
    *,
    identity_digest: str | None = None,
    schema_path: Path | None = None,
) -> Mapping[str, Any]:
    """Validate an Engine IR manifest after lexical decoding.

    ``identity_digest`` must be the digest produced by the native Profile 1
    canonicalizer over ``document["content"]``. It is mandatory because a
    structurally valid envelope must never self-attest its own digest. This
    function never computes an authoritative digest itself.
    """

    if not isinstance(document, Mapping):
        raise SchemaError("Engine IR manifest must be a JSON object")
    _check_profile_value(document, path="$", depth=0, counter=[0])
    _validate_schema(
        document,
        "morphoia-engine-ir-manifest-0.1.0.schema.json",
        schema_path,
    )
    _semantic_manifest(document, identity_digest)
    return document


def validate_replay(
    document: Mapping[str, Any],
    *,
    schema_path: Path | None = None,
) -> Mapping[str, Any]:
    """Validate the closed replay recipe without resolving its CAS reference."""

    if not isinstance(document, Mapping):
        raise SchemaError("Engine IR replay manifest must be a JSON object")
    _check_profile_value(document, path="$", depth=0, counter=[0])
    _validate_schema(
        document,
        "morphoia-engine-ir-replay-0.1.0.schema.json",
        schema_path,
    )
    _validate_binary_reference(document["manifest"], path="$.manifest")
    _ensure_digest(document["expected_content_identity"], path="$.expected_content_identity")
    return document


__all__ = [
    "CANONICAL_PROFILE",
    "MANIFEST_FORMAT",
    "MANIFEST_MEDIA_TYPE",
    "MANIFEST_SCHEMA_ID",
    "MANIFEST_VERSION",
    "MAX_DEPTH",
    "MAX_INPUT_BYTES",
    "MAX_SAFE_INTEGER",
    "MAX_STRING_BYTES",
    "MAX_VALUES",
    "REPLAY_FORMAT",
    "REPLAY_SCHEMA_ID",
    "ContractError",
    "LexicalError",
    "SchemaError",
    "SemanticError",
    "load_json_strict",
    "validate_manifest",
    "validate_replay",
]
