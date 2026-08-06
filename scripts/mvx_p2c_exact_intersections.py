#!/usr/bin/env python3
"""Exact auxiliary triangle-contact oracle for the MVX P2c experiment.

This module deliberately does *not* certify a solid.  It consumes either a
canonical Float64 triangle mesh or an exactly verified P2a terminal bundle,
then exhaustively checks conservative broad-phase pairs with exact rational
predicates.  Its strongest negative result is therefore
``EXACT_INTERSECTION_FREE_CANDIDATE``.

The checkpoint runner binds source, audit, upstream terminal, materializer,
mesh, limits, runtime and code identities.  Exact predicates run in an
externally bounded child.  Terminal results are immutable and a repeated
invocation returns ``SKIP_ANCHORED`` only after revalidating the complete
contracts, hash chains and caller-supplied external anchor.

Authority model: an attempt-specific Ed25519 public claim is published before
the child starts and its private key is deleted after terminalization.  This
closes partial post-run rewrites of result/checkpoint files in the local
single-writer model.  A local completion is never called ``SKIP``: reuse needs
a canonical anchor signed by a key precommitted in the plan, an exactly guarded
Drive checkpoint→COMPLETED→LATEST triplet, and a separately signed receipt for
the exact anchor bytes read back from their preallocated Drive locator.  The
offline validator checks these complete bindings but relies on the external
signer to attest Drive provenance and readback.  Without that external trust,
no local scheme can detect an actor who can coherently replace all artifacts as
the same operating-system owner; P2c remains an auxiliary candidate verdict,
never a release-grade proof of solid validity.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import heapq
import importlib.util
import json
import math
import os
import re
import resource
import secrets
import signal
import stat
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

SCHEMA = "MVX-P2C-EXACT-TRIANGLE-CONTACT"
SCHEMA_VERSION = "0.2.0"
ALGORITHM_ID = "mvx-p2c-exact-binary64-triangle-contact"
ALGORITHM_VERSION = "0.2.0"
MESH_SCHEMA = "MVX-P2C-CANONICAL-MESH"
MESH_SCHEMA_VERSION = "0.1.0"
MATERIALIZER_ID = "mvx-p2c-p2a-canonical-scene-materializer"
MATERIALIZER_VERSION = "0.1.0"
NUMERIC_MODEL = "IEEE754_BINARY64_EXACT_RATIONAL_LIFT"

FREE = "EXACT_INTERSECTION_FREE_CANDIDATE"
CONTACT = "EXACT_CONTACT_FOUND"
RESOURCE_LIMIT = "RESOURCE_LIMIT"
ERROR = "ERROR"

DEFAULT_MAX_VERTICES = 2_000_000
DEFAULT_MAX_TRIANGLES = 1_000_000
DEFAULT_MAX_CANDIDATE_PAIRS = 2_000_000
DEFAULT_MAX_COORDINATE_BITS = 2_048
DEFAULT_MAX_INPUT_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_RUNTIME_SECONDS = 120
CHILD_ADDRESS_SPACE_BYTES = 4 * 1024 * 1024 * 1024
CHILD_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_ATTEMPTS = 2
AUTHORITY_TRUST_MODEL = "LOCAL_SINGLE_WRITER_IMMUTABLE_CLAIM_DIRECTORY"
REQUIRE_EXTERNAL_ANCHOR = "REQUIRE_EXTERNAL_ANCHOR"
UNANCHORED_DIAGNOSTIC = "UNANCHORED_DIAGNOSTIC"
AUTHORITY_POLICIES = {REQUIRE_EXTERNAL_ANCHOR, UNANCHORED_DIAGNOSTIC}
EXTERNAL_ANCHOR_TRUST_MODEL = (
    "PRECOMMITTED_EXTERNAL_SIGNER_PLUS_DRIVE_TRIPLET_AND_SIGNED_ANCHOR_READBACK"
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = REPOSITORY_ROOT / "tmp"
P2A_SCRIPT = REPOSITORY_ROOT / "scripts" / "mvx_p2a_checkpoint.py"
BACKUP_GUARD_SCRIPT = REPOSITORY_ROOT / "scripts" / "mvx_backup_guard.py"

CHECKPOINT_NAME = re.compile(r"(?P<sequence>[0-9]{4})-(?P<state>[a-z]+)\.json")
CLAIM_NAME = re.compile(r"(?P<sequence>[0-9]{4})-attempt-(?P<attempt>[0-9]{4})-claim\.json")
ATTEMPT_RESULT_NAME = re.compile(r"attempt-(?P<attempt>[0-9]{4})-(?P<digest>[0-9a-f]{16})\.json")
AUTHORITY_SECRET_NAME = re.compile(r"attempt-(?P<attempt>[0-9]{4})\.ed25519-private")
EXTERNAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,511}")

Q = Fraction
Vec2 = tuple[Q, Q]
Vec3 = tuple[Q, Q, Q]
Triangle = tuple[int, int, int]


class P2cError(RuntimeError):
    """A deterministic input, persistence or contract failure."""


class P2cResourceLimit(P2cError):
    """A declared deterministic resource bound was reached."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Limits:
    max_vertices: int = DEFAULT_MAX_VERTICES
    max_triangles: int = DEFAULT_MAX_TRIANGLES
    max_candidate_pairs: int = DEFAULT_MAX_CANDIDATE_PAIRS
    max_coordinate_bits: int = DEFAULT_MAX_COORDINATE_BITS
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS

    def as_dict(self) -> dict[str, int]:
        return {
            "max_candidate_pairs": self.max_candidate_pairs,
            "max_coordinate_bits": self.max_coordinate_bits,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_triangles": self.max_triangles,
            "max_vertices": self.max_vertices,
        }

    def validate(self) -> None:
        for name, value in self.as_dict().items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise P2cError(f"invalid positive integer limit: {name}")


@dataclass(frozen=True)
class Intersection:
    dimension: int
    points: tuple[Vec3, ...]

    @property
    def kind(self) -> str:
        return ("POINT", "SEGMENT", "POLYGON")[self.dimension]


def _canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as error:
        raise P2cError("value is not canonical JSON") from error


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_value(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _fraction_payload(value: Q) -> dict[str, str]:
    return {"denominator": str(value.denominator), "numerator": str(value.numerator)}


def _point_payload(point: Vec3) -> list[dict[str, str]]:
    return [_fraction_payload(value) for value in point]


def _vsub(left: Vec3, right: Vec3) -> Vec3:
    return tuple(a - b for a, b in zip(left, right, strict=True))  # type: ignore[return-value]


def _vadd(left: Vec3, right: Vec3) -> Vec3:
    return tuple(a + b for a, b in zip(left, right, strict=True))  # type: ignore[return-value]


def _vscale(vector: Vec3, scale: Q) -> Vec3:
    return tuple(value * scale for value in vector)  # type: ignore[return-value]


def _dot(left: Vec3, right: Vec3) -> Q:
    return sum((a * b for a, b in zip(left, right, strict=True)), start=Q(0))


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _zero3(vector: Vec3) -> bool:
    return vector == (0, 0, 0)


def _orient2(a: Vec2, b: Vec2, c: Vec2) -> Q:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _project(point: Vec3, dropped_axis: int) -> Vec2:
    return tuple(value for axis, value in enumerate(point) if axis != dropped_axis)  # type: ignore[return-value]


def _projection_axis(normal: Vec3) -> int:
    return max(range(3), key=lambda axis: (abs(normal[axis]), -axis))


def _point_in_triangle_3d(point: Vec3, triangle: tuple[Vec3, Vec3, Vec3], normal: Vec3) -> bool:
    a, b, c = triangle
    return all(
        value >= 0
        for value in (
            _dot(_cross(_vsub(b, a), _vsub(point, a)), normal),
            _dot(_cross(_vsub(c, b), _vsub(point, b)), normal),
            _dot(_cross(_vsub(a, c), _vsub(point, c)), normal),
        )
    )


def _point_in_triangle_2d(point: Vec2, triangle: tuple[Vec2, Vec2, Vec2]) -> bool:
    signs = tuple(
        _orient2(start, end, point)
        for start, end in zip(triangle, triangle[1:] + triangle[:1], strict=True)
    )
    return all(value >= 0 for value in signs) or all(value <= 0 for value in signs)


def _between(value: Q, start: Q, end: Q) -> bool:
    return min(start, end) <= value <= max(start, end)


def _point_on_segment_2d(point: Vec2, start: Vec2, end: Vec2) -> bool:
    return _orient2(start, end, point) == 0 and all(
        _between(value, lower, upper) for value, lower, upper in zip(point, start, end, strict=True)
    )


def _segment_intersections_2d(
    a3: Vec3,
    b3: Vec3,
    c3: Vec3,
    d3: Vec3,
    dropped_axis: int,
) -> tuple[Vec3, ...]:
    a, b, c, d = (_project(point, dropped_axis) for point in (a3, b3, c3, d3))
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    denominator = r[0] * s[1] - r[1] * s[0]
    offset = (c[0] - a[0], c[1] - a[1])
    if denominator != 0:
        t = (offset[0] * s[1] - offset[1] * s[0]) / denominator
        u = (offset[0] * r[1] - offset[1] * r[0]) / denominator
        if 0 <= t <= 1 and 0 <= u <= 1:
            return (_vadd(a3, _vscale(_vsub(b3, a3), t)),)
        return ()
    if offset[0] * r[1] - offset[1] * r[0] != 0:
        return ()
    candidates: set[Vec3] = set()
    for point2, point3, start, end in (
        (a, a3, c, d),
        (b, b3, c, d),
        (c, c3, a, b),
        (d, d3, a, b),
    ):
        if _point_on_segment_2d(point2, start, end):
            candidates.add(point3)
    if len(candidates) <= 1:
        return tuple(candidates)
    axis = max(range(2), key=lambda index: (abs(r[index]), -index))
    ordered = sorted(candidates, key=lambda point: (_project(point, dropped_axis)[axis], point))
    return (ordered[0], ordered[-1])


def _normalise_coplanar_points(points: Iterable[Vec3], dropped_axis: int) -> Intersection | None:
    unique = sorted(set(points), key=lambda point: (_project(point, dropped_axis), point))
    if not unique:
        return None
    if len(unique) == 1:
        return Intersection(0, (unique[0],))
    projected = [(_project(point, dropped_axis), point) for point in unique]
    first = projected[0][0]
    last = projected[-1][0]
    if all(_orient2(first, last, point2) == 0 for point2, _ in projected[1:-1]):
        return Intersection(1, (projected[0][1], projected[-1][1]))

    def build_half(rows: Sequence[tuple[Vec2, Vec3]]) -> list[tuple[Vec2, Vec3]]:
        half: list[tuple[Vec2, Vec3]] = []
        for row in rows:
            while len(half) >= 2 and _orient2(half[-2][0], half[-1][0], row[0]) <= 0:
                half.pop()
            half.append(row)
        return half

    lower = build_half(projected)
    upper = build_half(tuple(reversed(projected)))
    hull = tuple(point3 for _, point3 in lower[:-1] + upper[:-1])
    return Intersection(2, hull)


def _coplanar_intersection(
    first: tuple[Vec3, Vec3, Vec3],
    second: tuple[Vec3, Vec3, Vec3],
    normal: Vec3,
) -> Intersection | None:
    dropped_axis = _projection_axis(normal)
    first2 = tuple(_project(point, dropped_axis) for point in first)
    second2 = tuple(_project(point, dropped_axis) for point in second)
    points: set[Vec3] = set()
    for point3, point2 in zip(first, first2, strict=True):
        if _point_in_triangle_2d(point2, second2):
            points.add(point3)
    for point3, point2 in zip(second, second2, strict=True):
        if _point_in_triangle_2d(point2, first2):
            points.add(point3)
    first_edges = tuple(zip(first, first[1:] + first[:1], strict=True))
    second_edges = tuple(zip(second, second[1:] + second[:1], strict=True))
    for a, b in first_edges:
        for c, d in second_edges:
            points.update(_segment_intersections_2d(a, b, c, d, dropped_axis))
    return _normalise_coplanar_points(points, dropped_axis)


def _edge_plane_points(
    triangle: tuple[Vec3, Vec3, Vec3],
    other: tuple[Vec3, Vec3, Vec3],
    other_normal: Vec3,
) -> set[Vec3]:
    origin = other[0]
    distances = tuple(_dot(other_normal, _vsub(point, origin)) for point in triangle)
    points: set[Vec3] = set()
    for point, distance in zip(triangle, distances, strict=True):
        if distance == 0 and _point_in_triangle_3d(point, other, other_normal):
            points.add(point)
    for index in range(3):
        start = triangle[index]
        end = triangle[(index + 1) % 3]
        start_distance = distances[index]
        end_distance = distances[(index + 1) % 3]
        if start_distance == 0 or end_distance == 0:
            continue
        if (start_distance < 0) == (end_distance < 0):
            continue
        parameter = start_distance / (start_distance - end_distance)
        point = _vadd(start, _vscale(_vsub(end, start), parameter))
        if _point_in_triangle_3d(point, other, other_normal):
            points.add(point)
    return points


def _noncoplanar_intersection(
    first: tuple[Vec3, Vec3, Vec3],
    second: tuple[Vec3, Vec3, Vec3],
    first_normal: Vec3,
    second_normal: Vec3,
) -> Intersection | None:
    direction = _cross(first_normal, second_normal)
    points = _edge_plane_points(first, second, second_normal)
    points.update(_edge_plane_points(second, first, first_normal))
    if not points:
        return None
    if len(points) == 1:
        return Intersection(0, (next(iter(points)),))
    axis = max(range(3), key=lambda index: (abs(direction[index]), -index))
    ordered = sorted(points, key=lambda point: (point[axis], point))
    if ordered[0] == ordered[-1]:
        return Intersection(0, (ordered[0],))
    return Intersection(1, (ordered[0], ordered[-1]))


def _triangle_intersection(
    first: tuple[Vec3, Vec3, Vec3], second: tuple[Vec3, Vec3, Vec3]
) -> Intersection | None:
    first_normal = _cross(_vsub(first[1], first[0]), _vsub(first[2], first[0]))
    second_normal = _cross(_vsub(second[1], second[0]), _vsub(second[2], second[0]))
    if _zero3(first_normal) or _zero3(second_normal):
        raise P2cError("degenerate triangle reached exact predicate")
    line_direction = _cross(first_normal, second_normal)
    if _zero3(line_direction):
        if _dot(first_normal, _vsub(second[0], first[0])) != 0:
            return None
        return _coplanar_intersection(first, second, first_normal)
    return _noncoplanar_intersection(first, second, first_normal, second_normal)


def _coordinate_fraction(value: object, max_bits: int) -> Q:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise P2cError("vertex coordinate is not a JSON number")
    try:
        canonical = float(value)
    except (OverflowError, ValueError) as error:
        raise P2cError("vertex coordinate is outside Float64") from error
    if not math.isfinite(canonical):
        raise P2cError("vertex coordinate is not finite Float64")
    exact = Q.from_float(canonical)
    if max(exact.numerator.bit_length(), exact.denominator.bit_length()) > max_bits:
        raise P2cResourceLimit("MAX_COORDINATE_BITS")
    return exact


def _parse_mesh(
    mesh: Mapping[str, Any], limits: Limits
) -> tuple[tuple[Vec3, ...], tuple[Triangle, ...]]:
    if set(mesh) != {"schema", "schema_version", "triangles", "vertices"}:
        raise P2cError("canonical mesh has unknown or missing fields")
    if mesh["schema"] != MESH_SCHEMA or mesh["schema_version"] != MESH_SCHEMA_VERSION:
        raise P2cError("canonical mesh schema is unsupported")
    raw_vertices = mesh["vertices"]
    raw_triangles = mesh["triangles"]
    if not isinstance(raw_vertices, list) or not isinstance(raw_triangles, list):
        raise P2cError("vertices and triangles must be arrays")
    if len(raw_vertices) > limits.max_vertices:
        raise P2cResourceLimit("MAX_VERTICES")
    if len(raw_triangles) > limits.max_triangles:
        raise P2cResourceLimit("MAX_TRIANGLES")
    vertices: list[Vec3] = []
    for row in raw_vertices:
        if not isinstance(row, list) or len(row) != 3:
            raise P2cError("each vertex must have exactly three coordinates")
        vertices.append(
            tuple(_coordinate_fraction(value, limits.max_coordinate_bits) for value in row)  # type: ignore[arg-type]
        )
    triangles: list[Triangle] = []
    for row in raw_triangles:
        if not isinstance(row, list) or len(row) != 3:
            raise P2cError("each triangle must have exactly three indices")
        if any(isinstance(index, bool) or not isinstance(index, int) for index in row):
            raise P2cError("triangle indices must be integers")
        triangle = tuple(row)
        if len(set(triangle)) != 3:
            raise P2cError("triangle repeats a vertex index")
        if any(index < 0 or index >= len(vertices) for index in triangle):
            raise P2cError("triangle index is out of bounds")
        points = tuple(vertices[index] for index in triangle)
        if _zero3(_cross(_vsub(points[1], points[0]), _vsub(points[2], points[0]))):
            raise P2cError("mesh contains an exact degenerate triangle")
        triangles.append(triangle)  # type: ignore[arg-type]
    return tuple(vertices), tuple(triangles)


def _bbox(points: tuple[Vec3, Vec3, Vec3]) -> tuple[Vec3, Vec3]:
    return (
        tuple(min(point[axis] for point in points) for axis in range(3)),  # type: ignore[arg-type]
        tuple(max(point[axis] for point in points) for axis in range(3)),  # type: ignore[arg-type]
    )


def _bbox_overlap(first: tuple[Vec3, Vec3], second: tuple[Vec3, Vec3]) -> bool:
    return all(
        first[0][axis] <= second[1][axis] and second[0][axis] <= first[1][axis] for axis in range(3)
    )


def _bbox_yz_overlap(first: tuple[Vec3, Vec3], second: tuple[Vec3, Vec3]) -> bool:
    return all(
        first[0][axis] <= second[1][axis] and second[0][axis] <= first[1][axis] for axis in (1, 2)
    )


def _allowed_topological_contact(
    intersection: Intersection,
    first_indices: Triangle,
    second_indices: Triangle,
    vertices: Sequence[Vec3],
) -> bool:
    shared = tuple(sorted(set(first_indices).intersection(second_indices)))
    if len(shared) == 1:
        return intersection.dimension == 0 and intersection.points == (vertices[shared[0]],)
    if len(shared) == 2:
        expected = tuple(sorted((vertices[shared[0]], vertices[shared[1]])))
        return intersection.dimension == 1 and tuple(sorted(intersection.points)) == expected
    return False


def _contact_payload(
    first_index: int,
    second_index: int,
    first: Triangle,
    second: Triangle,
    intersection: Intersection,
) -> dict[str, Any]:
    return {
        "dimension": intersection.dimension,
        "kind": intersection.kind,
        "points": [_point_payload(point) for point in intersection.points],
        "shared_topological_vertices": sorted(set(first).intersection(second)),
        "triangle_pair": [first_index, second_index],
    }


def _broadphase_payload(
    active_comparisons: int,
    bbox_candidates: int,
    exact_pairs: int,
    allowed_adjacencies: int,
) -> dict[str, int]:
    return {
        "active_pair_comparisons": active_comparisons,
        "allowed_topological_adjacencies": allowed_adjacencies,
        "bbox_candidate_pairs": bbox_candidates,
        "exact_pairs_examined": exact_pairs,
    }


def _analysis_result(
    status: str,
    limits: Limits,
    *,
    error_code: str | None,
    diagnostic: str,
    mesh: dict[str, int] | None,
    broadphase: dict[str, int] | None,
    contact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "broadphase": broadphase,
        "contact": contact,
        "diagnostic": diagnostic,
        "error_code": error_code,
        "limits": limits.as_dict(),
        "mesh": mesh,
        "numeric_model": NUMERIC_MODEL,
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": status,
    }
    return _validate_analysis_contract(result, limits.as_dict())


def analyze_mesh(mesh: Mapping[str, Any], limits: Limits | None = None) -> dict[str, Any]:
    selected_limits = limits or Limits()
    active_comparisons = 0
    bbox_candidates = 0
    exact_pairs = 0
    allowed_adjacencies = 0
    mesh_counts: dict[str, int] | None = None
    try:
        selected_limits.validate()
        vertices, triangles = _parse_mesh(mesh, selected_limits)
        mesh_counts = {"triangle_count": len(triangles), "vertex_count": len(vertices)}
        rows = []
        for index, triangle in enumerate(triangles):
            points = tuple(vertices[vertex] for vertex in triangle)
            bounds = _bbox(points)  # type: ignore[arg-type]
            rows.append((bounds[0][0], bounds[1][0], index, bounds, points))
        rows.sort(key=lambda row: (row[0], row[1], row[2]))

        active: dict[int, tuple[Any, ...]] = {}
        expiry_heap: list[tuple[Q, int]] = []
        for current in rows:
            while expiry_heap and expiry_heap[0][0] < current[0]:
                _, expired_index = heapq.heappop(expiry_heap)
                active.pop(expired_index, None)
            for other in active.values():
                active_comparisons += 1
                if active_comparisons > selected_limits.max_candidate_pairs:
                    raise P2cResourceLimit("MAX_CANDIDATE_PAIRS")
                if not _bbox_yz_overlap(other[3], current[3]):
                    continue
                bbox_candidates += 1
                exact_pairs += 1
                intersection = _triangle_intersection(other[4], current[4])
                if intersection is None:
                    continue
                first_index, second_index = sorted((other[2], current[2]))
                first = triangles[first_index]
                second = triangles[second_index]
                if _allowed_topological_contact(intersection, first, second, vertices):
                    allowed_adjacencies += 1
                    continue
                return _analysis_result(
                    CONTACT,
                    selected_limits,
                    error_code="EXACT_DISALLOWED_CONTACT",
                    diagnostic="EXACT_DISALLOWED_CONTACT_WITNESS",
                    mesh=mesh_counts,
                    broadphase=_broadphase_payload(
                        active_comparisons,
                        bbox_candidates,
                        exact_pairs,
                        allowed_adjacencies,
                    ),
                    contact=_contact_payload(
                        first_index, second_index, first, second, intersection
                    ),
                )
            active[current[2]] = current
            heapq.heappush(expiry_heap, (current[1], current[2]))
        return _analysis_result(
            FREE,
            selected_limits,
            error_code=None,
            diagnostic="ALL_CONSERVATIVE_BROADPHASE_PAIRS_EXHAUSTED",
            mesh=mesh_counts,
            broadphase=_broadphase_payload(
                active_comparisons,
                bbox_candidates,
                exact_pairs,
                allowed_adjacencies,
            ),
        )
    except P2cResourceLimit as error:
        return _analysis_result(
            RESOURCE_LIMIT,
            selected_limits,
            error_code=error.code,
            diagnostic="DECLARED_DETERMINISTIC_RESOURCE_BOUND_REACHED",
            mesh=mesh_counts,
            broadphase=_broadphase_payload(
                active_comparisons,
                bbox_candidates,
                exact_pairs,
                allowed_adjacencies,
            ),
        )
    except P2cError:
        return _analysis_result(
            ERROR,
            selected_limits,
            error_code="INVALID_MESH",
            diagnostic="CANONICAL_MESH_CONTRACT_REJECTED",
            mesh=mesh_counts,
            broadphase=None,
        )
    except ArithmeticError:
        return _analysis_result(
            ERROR,
            selected_limits,
            error_code="EXACT_ARITHMETIC_ERROR",
            diagnostic="EXACT_ARITHMETIC_FAILED_CLOSED",
            mesh=mesh_counts,
            broadphase=None,
        )


ANALYSIS_FIELDS = {
    "algorithm_id",
    "algorithm_version",
    "broadphase",
    "contact",
    "diagnostic",
    "error_code",
    "limits",
    "mesh",
    "numeric_model",
    "schema",
    "schema_version",
    "status",
}
RESULT_FIELDS = ANALYSIS_FIELDS | {
    "authorization",
    "input_binding",
    "plan_sha256",
    "source_sha256",
    "source_size_bytes",
    "work_id",
}
EXTERNAL_ANCHOR_UNSIGNED_FIELDS = {
    "artifact_manifest_sha256",
    "anchor_persistence_policy",
    "authority_claim_chain_sha256",
    "checkpoint_chain_sha256",
    "code_sha256",
    "completed_id",
    "completed_sha256",
    "external_anchor_id",
    "external_anchor_parent_id",
    "external_checkpoint_id",
    "external_checkpoint_sha256",
    "drive_receipt",
    "input_binding_sha256",
    "plan_sha256",
    "result_id",
    "result_sha256",
    "runtime_sha256",
    "schema",
    "schema_version",
    "source_sha256",
    "source_size_bytes",
    "terminal_id",
    "terminal_sha256",
    "trust_model",
    "work_id",
}
EXTERNAL_ANCHOR_FIELDS = EXTERNAL_ANCHOR_UNSIGNED_FIELDS | {
    "signature_algorithm",
    "signature_hex",
}
ANCHOR_READBACK_UNSIGNED_FIELDS = {
    "anchor_drive_file_id",
    "anchor_parent_id",
    "anchor_sha256",
    "anchor_size_bytes",
    "download_verified",
    "schema",
    "schema_version",
    "trust_model",
}
ANCHOR_READBACK_FIELDS = ANCHOR_READBACK_UNSIGNED_FIELDS | {
    "signature_algorithm",
    "signature_hex",
}
RESOURCE_CODES = {
    "CHILD_CPU_LIMIT",
    "CHILD_TIMEOUT",
    "MAX_CANDIDATE_PAIRS",
    "MAX_COORDINATE_BITS",
    "MAX_INPUT_BYTES",
    "MAX_TRIANGLES",
    "MAX_VERTICES",
}
ERROR_CODES = {
    "CHILD_RETRY_EXHAUSTED",
    "EXACT_ARITHMETIC_ERROR",
    "INVALID_JSON",
    "INVALID_MESH",
}


@dataclass(frozen=True)
class FileSnapshot:
    payload: bytes | None
    sha256: str
    size_bytes: int
    over_limit: bool


class ChildNoStatus(P2cError):
    """The isolated exact child exited without a valid closed result."""


def _is_nonnegative_integer(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise P2cError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _validate_fraction_payload(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"denominator", "numerator"}:
        raise P2cError("contact rational has invalid fields")
    numerator_text = value["numerator"]
    denominator_text = value["denominator"]
    if (
        not isinstance(numerator_text, str)
        or not isinstance(denominator_text, str)
        or not re.fullmatch(r"0|-?[1-9][0-9]*", numerator_text)
        or not re.fullmatch(r"[1-9][0-9]*", denominator_text)
    ):
        raise P2cError("contact rational is not canonical decimal")
    try:
        numerator = int(numerator_text)
        denominator = int(denominator_text)
    except ValueError as error:
        raise P2cError("contact rational exceeds runtime integer policy") from error
    if math.gcd(numerator, denominator) != 1:
        raise P2cError("contact rational is not reduced")


def _validate_mesh_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {"triangle_count", "vertex_count"}:
        raise P2cError("result mesh counts are invalid")
    if not all(_is_nonnegative_integer(item) for item in value.values()):
        raise P2cError("result mesh counts must be nonnegative integers")
    return value


def _validate_broadphase(value: Any, limits: Mapping[str, int]) -> dict[str, int]:
    expected = {
        "active_pair_comparisons",
        "allowed_topological_adjacencies",
        "bbox_candidate_pairs",
        "exact_pairs_examined",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise P2cError("broadphase evidence fields are invalid")
    if not all(_is_nonnegative_integer(item) for item in value.values()):
        raise P2cError("broadphase evidence must contain nonnegative integers")
    active = value["active_pair_comparisons"]
    bbox = value["bbox_candidate_pairs"]
    exact = value["exact_pairs_examined"]
    allowed = value["allowed_topological_adjacencies"]
    if not allowed <= exact <= bbox <= active:
        raise P2cError("broadphase counters violate monotonic invariants")
    if active > limits["max_candidate_pairs"] + 1:
        raise P2cError("broadphase counter exceeds its fail-fast boundary")
    return value


def _validate_contact(value: Any, mesh_counts: Mapping[str, int]) -> dict[str, Any]:
    expected = {
        "dimension",
        "kind",
        "points",
        "shared_topological_vertices",
        "triangle_pair",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise P2cError("contact witness fields are invalid")
    dimension = value["dimension"]
    kind = value["kind"]
    if isinstance(dimension, bool) or dimension not in {0, 1, 2}:
        raise P2cError("contact dimension is invalid")
    if kind != ("POINT", "SEGMENT", "POLYGON")[dimension]:
        raise P2cError("contact kind differs from its dimension")
    points = value["points"]
    required_count = {0: 1, 1: 2}[dimension] if dimension < 2 else None
    if not isinstance(points, list) or (
        (required_count is not None and len(points) != required_count)
        or (dimension == 2 and len(points) < 3)
    ):
        raise P2cError("contact point count is invalid")
    for point in points:
        if not isinstance(point, list) or len(point) != 3:
            raise P2cError("contact point is not a rational Vec3")
        for coordinate in point:
            _validate_fraction_payload(coordinate)
    pair = value["triangle_pair"]
    if (
        not isinstance(pair, list)
        or len(pair) != 2
        or not all(_is_nonnegative_integer(item) for item in pair)
        or pair != sorted(set(pair))
        or pair[-1] >= mesh_counts["triangle_count"]
    ):
        raise P2cError("contact triangle pair is invalid")
    shared = value["shared_topological_vertices"]
    if (
        not isinstance(shared, list)
        or not all(_is_nonnegative_integer(item) for item in shared)
        or shared != sorted(set(shared))
        or any(item >= mesh_counts["vertex_count"] for item in shared)
        or len(shared) > 3
    ):
        raise P2cError("contact shared-vertex witness is invalid")
    return value


def _validate_analysis_contract(value: Any, expected_limits: Mapping[str, int]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ANALYSIS_FIELDS:
        raise P2cError("analysis result has unknown or missing fields")
    if (
        value["schema"] != SCHEMA
        or value["schema_version"] != SCHEMA_VERSION
        or value["algorithm_id"] != ALGORITHM_ID
        or value["algorithm_version"] != ALGORITHM_VERSION
        or value["numeric_model"] != NUMERIC_MODEL
    ):
        raise P2cError("analysis result identity is invalid")
    if value["limits"] != dict(expected_limits):
        raise P2cError("analysis result limits differ from the execution plan")
    if not isinstance(value["diagnostic"], str) or not value["diagnostic"]:
        raise P2cError("analysis diagnostic is invalid")
    status = value["status"]
    if status not in {FREE, CONTACT, RESOURCE_LIMIT, ERROR}:
        raise P2cError("analysis status is invalid")
    mesh_counts = None if value["mesh"] is None else _validate_mesh_counts(value["mesh"])
    broadphase = (
        None
        if value["broadphase"] is None
        else _validate_broadphase(value["broadphase"], expected_limits)
    )
    if status == FREE:
        if (
            value["error_code"] is not None
            or value["diagnostic"] != "ALL_CONSERVATIVE_BROADPHASE_PAIRS_EXHAUSTED"
            or mesh_counts is None
            or broadphase is None
            or value["contact"] is not None
        ):
            raise P2cError("FREE result contract is inconsistent")
    elif status == CONTACT:
        if (
            value["error_code"] != "EXACT_DISALLOWED_CONTACT"
            or value["diagnostic"] != "EXACT_DISALLOWED_CONTACT_WITNESS"
            or mesh_counts is None
            or broadphase is None
        ):
            raise P2cError("CONTACT result contract is inconsistent")
        if broadphase["exact_pairs_examined"] < 1:
            raise P2cError("CONTACT result lacks an examined exact pair")
        _validate_contact(value["contact"], mesh_counts)
    elif status == RESOURCE_LIMIT:
        if (
            value["error_code"] not in RESOURCE_CODES
            or value["contact"] is not None
            or value["diagnostic"]
            not in {
                "DECLARED_DETERMINISTIC_RESOURCE_BOUND_REACHED",
                "ISOLATED_EXACT_CHILD_CPU_LIMIT",
                "ISOLATED_EXACT_CHILD_TIMEOUT",
                "SOURCE_EXCEEDS_DECLARED_INPUT_BOUND",
            }
        ):
            raise P2cError("RESOURCE_LIMIT result contract is inconsistent")
        if value["error_code"] == "MAX_CANDIDATE_PAIRS" and (
            broadphase is None
            or broadphase["active_pair_comparisons"] != expected_limits["max_candidate_pairs"] + 1
        ):
            raise P2cError("pair-limit result lacks its exact fail-fast counter")
        if value["error_code"] in {"CHILD_CPU_LIMIT", "CHILD_TIMEOUT", "MAX_INPUT_BYTES"} and (
            mesh_counts is not None or broadphase is not None
        ):
            raise P2cError("external resource result must not claim in-child evidence")
    elif (
        value["error_code"] not in ERROR_CODES
        or value["contact"] is not None
        or value["diagnostic"]
        not in {
            "CANONICAL_MESH_CONTRACT_REJECTED",
            "EXACT_ARITHMETIC_FAILED_CLOSED",
            "ISOLATED_CHILD_RETRY_BUDGET_EXHAUSTED",
            "JSON_INPUT_REJECTED",
        }
    ):
        raise P2cError("ERROR result contract is inconsistent")
    elif mesh_counts is not None or broadphase is not None:
        raise P2cError("ERROR result must not claim partial geometry evidence")
    return value


def _private_candidate(path: Path) -> Path:
    candidate = Path(os.path.abspath(path))
    root = Path(os.path.abspath(PRIVATE_ROOT))
    if candidate != root and root not in candidate.parents:
        raise P2cError("P2c output must remain under the repository tmp directory")
    return candidate


def _directory_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


def _ensure_private_root() -> None:
    try:
        os.mkdir(PRIVATE_ROOT, 0o700)
    except FileExistsError:
        pass
    try:
        before = PRIVATE_ROOT.lstat()
        descriptor = os.open(
            PRIVATE_ROOT,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
        )
    except OSError as error:
        raise P2cError("private tmp root is not a safe real directory") from error
    try:
        after = os.fstat(descriptor)
        if not stat.S_ISDIR(before.st_mode) or _directory_identity(before) != _directory_identity(
            after
        ):
            raise P2cError("private tmp root changed during validation")
    finally:
        os.close(descriptor)


def _ensure_private_tree(path: Path) -> Path:
    candidate = _private_candidate(path)
    _ensure_private_root()
    descriptor = os.open(
        PRIVATE_ROOT,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
    )
    try:
        for part in candidate.relative_to(PRIVATE_ROOT).parts:
            try:
                os.mkdir(part, 0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError as error:
                raise P2cError("private output path contains a symlink or non-directory") from error
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise P2cError("private output component is not a directory")
            os.fchmod(child, 0o700)
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)
    return candidate


def _open_real_directory(path: Path) -> int:
    candidate = _private_candidate(path)
    root = PRIVATE_ROOT.resolve()
    try:
        before = root.lstat()
        descriptor = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
        )
    except OSError as error:
        raise P2cError("private directory is unsafe or disappeared") from error
    opened_root = os.fstat(descriptor)
    if not stat.S_ISDIR(before.st_mode) or _directory_identity(before) != _directory_identity(
        opened_root
    ):
        os.close(descriptor)
        raise P2cError("private directory changed during safe open")
    try:
        relative = candidate.relative_to(root)
        for part in relative.parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                os.close(descriptor)
                raise P2cError("private path component is not a directory")
            os.close(descriptor)
            descriptor = child
    except (OSError, ValueError) as error:
        os.close(descriptor)
        raise P2cError("private directory path contains an unsafe component") from error
    return descriptor


def _snapshot_regular(path: Path, maximum_retained_bytes: int) -> FileSnapshot:
    try:
        before = path.lstat()
    except OSError as error:
        raise P2cError("cannot inspect regular input") from error
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise P2cError("input must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise P2cError("cannot safely open regular input") from error
    hasher = hashlib.sha256()
    retained = bytearray() if before.st_size <= maximum_retained_bytes else None
    total = 0
    try:
        opened = os.fstat(descriptor)
        if (
            before.st_dev != opened.st_dev
            or before.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
        ):
            raise P2cError("input changed before safe open completed")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            hasher.update(chunk)
            if retained is not None:
                if total <= maximum_retained_bytes:
                    retained.extend(chunk)
                else:
                    retained = None
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or total != after.st_size:
        raise P2cError("input changed while being read")
    return FileSnapshot(
        bytes(retained) if retained is not None else None,
        hasher.hexdigest(),
        total,
        total > maximum_retained_bytes,
    )


def _safe_regular_bytes(path: Path, maximum: int = CHILD_OUTPUT_BYTES) -> bytes:
    snapshot = _snapshot_regular(path, maximum)
    if snapshot.payload is None:
        raise P2cError("persisted artifact exceeds its byte limit")
    return snapshot.payload


def _publish_once(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    if mode not in {0o400, 0o600}:
        raise P2cError("immutable artifact mode is unsupported")
    target = _private_candidate(path)
    _ensure_private_tree(target.parent)
    staging = _ensure_private_tree(target.parent.parent / "staging")
    parent_fd = _open_real_directory(target.parent)
    staging_fd = _open_real_directory(staging)
    temporary_name = f"{target.parent.name}-{target.name}.{secrets.token_hex(16)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=staging_fd,
        )
        os.fchmod(descriptor, mode)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(
                temporary_name,
                target.name,
                src_dir_fd=staging_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _safe_regular_bytes(target, max(len(payload), 1)) != payload:
                raise P2cError("immutable artifact conflicts with existing bytes")
        else:
            os.fsync(parent_fd)
    except OSError as error:
        raise P2cError("cannot atomically publish immutable artifact") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=staging_fd)
        os.close(staging_fd)
        os.close(parent_fd)


def _unlink_private_regular(path: Path, *, expected_mode: int) -> None:
    target = _private_candidate(path)
    parent_fd = _open_real_directory(target.parent)
    try:
        metadata = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise P2cError("private authority secret is not an immutable regular file")
        os.unlink(target.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError as error:
        raise P2cError("cannot safely remove consumed authority secret") from error
    finally:
        os.close(parent_fd)


@contextlib.contextmanager
def _exclusive_lock(root: Path, work_id: str) -> Iterable[None]:
    directory = _ensure_private_tree(root)
    directory_fd = _open_real_directory(directory)
    try:
        descriptor = os.open(
            f"{work_id}.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise P2cError("lock is not a regular file")
    except OSError as error:
        os.close(directory_fd)
        raise P2cError("cannot safely open work lock") from error
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        os.close(directory_fd)


def _decode_json(payload: bytes, label: str) -> Any:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise P2cError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise P2cError(f"{label} contains unsupported numeric constant {value}")

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise P2cError(f"{label} is invalid JSON") from error


def _load_json(path: Path) -> Any:
    payload = _safe_regular_bytes(path)
    value = _decode_json(payload, "persisted JSON")
    if payload != _canonical_bytes(value):
        raise P2cError("persisted JSON is not canonical")
    return value


def _checkpoint_hash(checkpoint: Mapping[str, Any]) -> str:
    return _sha256_value(checkpoint)


def _checkpoint_paths(directory: Path) -> list[Path]:
    descriptor = _open_real_directory(directory)
    try:
        names = sorted(os.listdir(descriptor))
        paths: list[Path] = []
        for name in names:
            match = CHECKPOINT_NAME.fullmatch(name)
            try:
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except OSError as error:
                raise P2cError("cannot inspect checkpoint entry") from error
            if match is None or not stat.S_ISREG(metadata.st_mode):
                raise P2cError("checkpoint directory contains an invalid entry")
            paths.append(directory / name)
        return paths
    finally:
        os.close(descriptor)


def _validate_checkpoint_document(checkpoint: Any) -> dict[str, Any]:
    expected = {
        "attempt",
        "claim_sha256",
        "plan_sha256",
        "previous_checkpoint_sha256",
        "result_filename",
        "result_sha256",
        "state",
        "work_id",
    }
    if not isinstance(checkpoint, dict) or set(checkpoint) != expected:
        raise P2cError("checkpoint has unknown or missing fields")
    attempt = checkpoint["attempt"]
    state = checkpoint["state"]
    if (
        isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or not 1 <= attempt <= MAX_ATTEMPTS
        or not isinstance(state, str)
        or state not in {"PENDING", "RUNNING", "INTERRUPTED", "TERMINAL"}
    ):
        raise P2cError("checkpoint state or attempt has an invalid type or value")
    _require_sha256(checkpoint["plan_sha256"], "checkpoint plan hash")
    _require_sha256(checkpoint["work_id"], "checkpoint work ID")
    previous = checkpoint["previous_checkpoint_sha256"]
    if previous is not None:
        _require_sha256(previous, "checkpoint previous hash")
    result_sha = checkpoint["result_sha256"]
    claim_sha = checkpoint["claim_sha256"]
    result_filename = checkpoint["result_filename"]
    if state == "PENDING":
        if claim_sha is not None:
            raise P2cError("PENDING checkpoint cannot bind an authority claim")
    else:
        _require_sha256(claim_sha, "checkpoint authority claim hash")
    if state == "TERMINAL":
        _require_sha256(result_sha, "terminal result hash")
        if not isinstance(result_filename, str) or not re.fullmatch(
            r"attempt-[0-9]{4}-[0-9a-f]{16}\.json", result_filename
        ):
            raise P2cError("terminal result filename is invalid")
        expected_filename = f"attempt-{attempt:04d}-{result_sha[:16]}.json"
        if result_filename != expected_filename:
            raise P2cError("terminal result filename does not bind attempt and digest")
    elif result_sha is not None or result_filename is not None:
        raise P2cError("non-terminal checkpoint binds a result")
    return checkpoint


def _load_checkpoint_chain(directory: Path, plan_sha256: str, work_id: str) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    for expected_sequence, path in enumerate(_checkpoint_paths(directory), start=1):
        match = CHECKPOINT_NAME.fullmatch(path.name)
        assert match is not None
        if int(match.group("sequence")) != expected_sequence:
            raise P2cError("checkpoint sequence has a gap")
        checkpoint = _validate_checkpoint_document(_load_json(path))
        if checkpoint["plan_sha256"] != plan_sha256 or checkpoint["work_id"] != work_id:
            raise P2cError("checkpoint identity differs from plan")
        if checkpoint["state"].casefold() != match.group("state"):
            raise P2cError("checkpoint filename does not bind its state")
        expected_previous = _checkpoint_hash(chain[-1]) if chain else None
        if checkpoint["previous_checkpoint_sha256"] != expected_previous:
            raise P2cError("checkpoint hash chain is invalid")
        state = checkpoint["state"]
        attempt = checkpoint["attempt"]
        if not chain and (state != "PENDING" or attempt != 1):
            raise P2cError("checkpoint chain does not begin at PENDING attempt 1")
        if chain:
            previous = chain[-1]
            allowed = (
                (previous["state"] == "PENDING" and state == "RUNNING" and attempt == 1)
                or (
                    previous["state"] == "RUNNING"
                    and state in {"INTERRUPTED", "TERMINAL"}
                    and attempt == previous["attempt"]
                )
                or (
                    previous["state"] == "INTERRUPTED"
                    and state == "RUNNING"
                    and attempt == previous["attempt"] + 1
                )
            )
            if not allowed:
                raise P2cError("checkpoint transition is invalid")
            if state in {"INTERRUPTED", "TERMINAL"} and (
                checkpoint["claim_sha256"] != previous["claim_sha256"]
            ):
                raise P2cError("checkpoint transition changes its authority claim")
            if (
                state == "RUNNING"
                and previous["state"] == "INTERRUPTED"
                and (checkpoint["claim_sha256"] == previous["claim_sha256"])
            ):
                raise P2cError("retry must use a new authority claim")
        chain.append(checkpoint)
    return chain


def _append_checkpoint(
    directory: Path,
    chain: list[dict[str, Any]],
    *,
    state: str,
    attempt: int,
    plan_sha256: str,
    work_id: str,
    claim_sha256: str | None = None,
    result_filename: str | None = None,
    result_sha256: str | None = None,
) -> dict[str, Any]:
    checkpoint = _validate_checkpoint_document(
        {
            "attempt": attempt,
            "claim_sha256": claim_sha256,
            "plan_sha256": plan_sha256,
            "previous_checkpoint_sha256": _checkpoint_hash(chain[-1]) if chain else None,
            "result_filename": result_filename,
            "result_sha256": result_sha256,
            "state": state,
            "work_id": work_id,
        }
    )
    name = f"{len(chain) + 1:04d}-{state.casefold()}.json"
    _publish_once(directory / name, _canonical_bytes(checkpoint))
    chain.append(checkpoint)
    return checkpoint


def _script_sha256() -> str:
    return _sha256_bytes(Path(__file__).read_bytes())


def _runtime_identity() -> dict[str, Any]:
    return {
        "implementation": sys.implementation.name,
        "int_max_str_digits": sys.get_int_max_str_digits(),
        "version": list(sys.version_info[:3]),
    }


def _claim_hash(claim: Mapping[str, Any]) -> str:
    return _sha256_value(claim)


def _claim_paths(directory: Path) -> list[Path]:
    descriptor = _open_real_directory(directory)
    try:
        names = sorted(os.listdir(descriptor))
        paths: list[Path] = []
        for sequence, name in enumerate(names, start=1):
            match = CLAIM_NAME.fullmatch(name)
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (
                match is None
                or int(match.group("sequence")) != sequence
                or not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o400
            ):
                raise P2cError("authority claim directory contains a mutable or invalid entry")
            paths.append(directory / name)
        return paths
    finally:
        os.close(descriptor)


def _validate_claim_document(
    claim: Any,
    *,
    plan_sha256: str,
    work_id: str,
    previous_claim_sha256: str | None,
) -> dict[str, Any]:
    expected = {
        "attempt",
        "plan_sha256",
        "previous_claim_sha256",
        "public_key_hex",
        "schema",
        "schema_version",
        "trust_model",
        "work_id",
    }
    if not isinstance(claim, dict) or set(claim) != expected:
        raise P2cError("authority claim has unknown or missing fields")
    if (
        claim["schema"] != "MVX-P2C-ATTEMPT-AUTHORITY-CLAIM"
        or claim["schema_version"] != "0.1.0"
        or claim["trust_model"] != AUTHORITY_TRUST_MODEL
        or claim["plan_sha256"] != plan_sha256
        or claim["work_id"] != work_id
        or claim["previous_claim_sha256"] != previous_claim_sha256
        or isinstance(claim["attempt"], bool)
        or not isinstance(claim["attempt"], int)
        or not 1 <= claim["attempt"] <= MAX_ATTEMPTS
        or not isinstance(claim["public_key_hex"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", claim["public_key_hex"])
    ):
        raise P2cError("authority claim identity or key is invalid")
    return claim


def _load_claim_chain(directory: Path, plan_sha256: str, work_id: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for sequence, path in enumerate(_claim_paths(directory), start=1):
        match = CLAIM_NAME.fullmatch(path.name)
        assert match is not None
        claim = _validate_claim_document(
            _load_json(path),
            plan_sha256=plan_sha256,
            work_id=work_id,
            previous_claim_sha256=_claim_hash(claims[-1]) if claims else None,
        )
        if claim["attempt"] != sequence or claim["attempt"] != int(match.group("attempt")):
            raise P2cError("authority claim sequence does not bind its attempt")
        claims.append(claim)
    return claims


def _authority_secret_path(secret_directory: Path, attempt: int) -> Path:
    return secret_directory / f"attempt-{attempt:04d}.ed25519-private"


def _authority_secret_exists(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise P2cError("cannot inspect attempt authority private key") from error
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o400:
        raise P2cError("attempt authority private key is mutable or unsafe")
    return True


def _validate_authority_secret_directory(directory: Path) -> list[Path]:
    descriptor = _open_real_directory(directory)
    paths: list[Path] = []
    try:
        for name in sorted(os.listdir(descriptor)):
            match = AUTHORITY_SECRET_NAME.fullmatch(name)
            try:
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except OSError as error:
                raise P2cError("cannot inspect authority secret entry") from error
            if (
                match is None
                or not 1 <= int(match.group("attempt")) <= MAX_ATTEMPTS
                or not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o400
            ):
                raise P2cError("authority secret directory contains an unsafe entry")
            paths.append(directory / name)
    finally:
        os.close(descriptor)
    return paths


def _validate_attempt_result_directory(directory: Path) -> list[Path]:
    descriptor = _open_real_directory(directory)
    paths: list[Path] = []
    try:
        for name in sorted(os.listdir(descriptor)):
            match = ATTEMPT_RESULT_NAME.fullmatch(name)
            try:
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except OSError as error:
                raise P2cError("cannot inspect attempt result entry") from error
            if (
                match is None
                or not 1 <= int(match.group("attempt")) <= MAX_ATTEMPTS
                or not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise P2cError("attempt result directory contains an unsafe entry")
            paths.append(directory / name)
    finally:
        os.close(descriptor)
    return paths


def _load_authority_private_key(path: Path, expected_public_hex: str) -> Ed25519PrivateKey:
    if not _authority_secret_exists(path):
        raise P2cError("attempt authority private key is unavailable")
    raw = _safe_regular_bytes(path, 64)
    if len(raw) != 32:
        raise P2cError("attempt authority private key length is invalid")
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError as error:
        raise P2cError("attempt authority private key is invalid") from error
    public_hex = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        .hex()
    )
    if public_hex != expected_public_hex:
        raise P2cError("attempt private key differs from immutable public claim")
    return private_key


def _ensure_attempt_claim(
    claim_directory: Path,
    secret_directory: Path,
    *,
    attempt: int,
    plan_sha256: str,
    work_id: str,
) -> tuple[dict[str, Any], str, Ed25519PrivateKey]:
    claims = _load_claim_chain(claim_directory, plan_sha256, work_id)
    if attempt <= len(claims):
        claim = claims[attempt - 1]
        private_key = _load_authority_private_key(
            _authority_secret_path(secret_directory, attempt),
            claim["public_key_hex"],
        )
        return claim, _claim_hash(claim), private_key
    if attempt != len(claims) + 1:
        raise P2cError("authority claim attempts are not append-only")
    secret_path = _authority_secret_path(secret_directory, attempt)
    try:
        secret_metadata = secret_path.lstat()
    except FileNotFoundError:
        private_key = Ed25519PrivateKey.generate()
        raw_private = private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        _publish_once(secret_path, raw_private, mode=0o400)
    else:
        if (
            not stat.S_ISREG(secret_metadata.st_mode)
            or stat.S_IMODE(secret_metadata.st_mode) != 0o400
        ):
            raise P2cError("orphan authority secret is mutable or unsafe")
        raw_private = _safe_regular_bytes(secret_path, 64)
        if len(raw_private) != 32:
            raise P2cError("orphan authority secret length is invalid")
        private_key = Ed25519PrivateKey.from_private_bytes(raw_private)
    public_hex = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        .hex()
    )
    claim = _validate_claim_document(
        {
            "attempt": attempt,
            "plan_sha256": plan_sha256,
            "previous_claim_sha256": _claim_hash(claims[-1]) if claims else None,
            "public_key_hex": public_hex,
            "schema": "MVX-P2C-ATTEMPT-AUTHORITY-CLAIM",
            "schema_version": "0.1.0",
            "trust_model": AUTHORITY_TRUST_MODEL,
            "work_id": work_id,
        },
        plan_sha256=plan_sha256,
        work_id=work_id,
        previous_claim_sha256=_claim_hash(claims[-1]) if claims else None,
    )
    name = f"{attempt:04d}-attempt-{attempt:04d}-claim.json"
    _publish_once(claim_directory / name, _canonical_bytes(claim), mode=0o400)
    reloaded = _load_claim_chain(claim_directory, plan_sha256, work_id)
    if reloaded[-1] != claim:
        raise P2cError("published authority claim failed exact reload")
    return claim, _claim_hash(claim), private_key


def _authorization_message(
    unsigned_result: Mapping[str, Any], claim_sha256: str, attempt: int
) -> bytes:
    return _canonical_bytes(
        {
            "attempt": attempt,
            "claim_sha256": claim_sha256,
            "result": dict(unsigned_result),
            "signature_domain": "MVX-P2C-RESULT-AUTHORIZATION-ED25519-1",
        }
    )


def _validate_authorization(value: Any) -> dict[str, Any]:
    expected = {
        "attempt",
        "claim_sha256",
        "signature_algorithm",
        "signature_hex",
        "trust_model",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise P2cError("result authorization has unknown or missing fields")
    if (
        isinstance(value["attempt"], bool)
        or not isinstance(value["attempt"], int)
        or not 1 <= value["attempt"] <= MAX_ATTEMPTS
        or not isinstance(value["claim_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["claim_sha256"])
        or value["signature_algorithm"] != "ED25519"
        or not isinstance(value["signature_hex"], str)
        or not re.fullmatch(r"[0-9a-f]{128}", value["signature_hex"])
        or value["trust_model"] != AUTHORITY_TRUST_MODEL
    ):
        raise P2cError("result authorization identity or signature is invalid")
    return value


def _verify_result_authority(
    result: Mapping[str, Any], claim: Mapping[str, Any], claim_sha256: str
) -> None:
    authorization = _validate_authorization(result["authorization"])
    if (
        authorization["claim_sha256"] != claim_sha256
        or authorization["attempt"] != claim["attempt"]
    ):
        raise P2cError("result authorization differs from terminal authority claim")
    unsigned = {name: value for name, value in result.items() if name != "authorization"}
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(claim["public_key_hex"]))
        public_key.verify(
            bytes.fromhex(authorization["signature_hex"]),
            _authorization_message(unsigned, claim_sha256, claim["attempt"]),
        )
    except (InvalidSignature, ValueError) as error:
        raise P2cError("result authorization signature is invalid") from error


def _validate_input_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("mode") not in {"CANONICAL_MESH", "P2A_BOUND"}:
        raise P2cError("input binding mode is invalid")
    if value["mode"] == "CANONICAL_MESH":
        if set(value) != {"mesh_sha256", "mode"}:
            raise P2cError("canonical mesh binding fields are invalid")
        _require_sha256(value["mesh_sha256"], "canonical mesh hash")
    else:
        expected = {
            "audit_record_sha256",
            "execution_plan_file_sha256",
            "execution_plan_sha256",
            "materializer_code_sha256",
            "materializer_id",
            "materializer_version",
            "mesh_sha256",
            "mode",
            "p2a_terminal_checkpoint_sha256",
            "p2a_work_id",
        }
        if set(value) != expected:
            raise P2cError("P2a input binding fields are invalid")
        for name in expected - {"materializer_id", "materializer_version", "mode"}:
            _require_sha256(value[name], f"P2a binding {name}")
        if (
            value["materializer_id"] != MATERIALIZER_ID
            or value["materializer_version"] != MATERIALIZER_VERSION
        ):
            raise P2cError("P2a materializer identity is invalid")
    return value


def _validate_result_contract(result: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or set(result) != RESULT_FIELDS:
        raise P2cError("result has unknown or missing fields")
    _validate_authorization(result["authorization"])
    analysis = {name: result[name] for name in ANALYSIS_FIELDS}
    _validate_analysis_contract(analysis, plan["limits"])
    binding = _validate_input_binding(result["input_binding"])
    expected = {
        "input_binding": plan["input_binding"],
        "plan_sha256": _sha256_value(plan),
        "source_sha256": plan["source_sha256"],
        "source_size_bytes": plan["source_size_bytes"],
        "work_id": plan["work_id"],
    }
    if binding != plan["input_binding"] or any(
        result[name] != value for name, value in expected.items()
    ):
        raise P2cError("result identity differs from execution plan")
    return result


def _validate_terminal(
    run_directory: Path,
    chain: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
    *,
    allow_live_secret: bool = False,
) -> dict[str, Any]:
    if not chain or chain[-1].get("state") != "TERMINAL":
        raise P2cError("checkpoint chain is not terminal")
    terminal = chain[-1]
    plan_sha256 = _sha256_value(plan)
    claim_directory = run_directory / "authority-claims"
    secret_directory = run_directory / "authority-secrets"
    result_directory = run_directory / "attempt-results"
    claims = _load_claim_chain(claim_directory, plan_sha256, plan["work_id"])
    attempt = terminal["attempt"]
    if len(claims) != attempt:
        raise P2cError("terminal does not bind the exact authority claim chain")
    claim = claims[attempt - 1]
    claim_sha256 = _claim_hash(claim)
    if terminal["claim_sha256"] != claim_sha256:
        raise P2cError("terminal authority claim hash is invalid")
    _validate_attempt_result_directory(result_directory)
    result_path = result_directory / terminal["result_filename"]
    result_bytes = _safe_regular_bytes(result_path)
    if _sha256_bytes(result_bytes) != terminal["result_sha256"]:
        raise P2cError("terminal checkpoint does not bind result bytes")
    result = _decode_json(result_bytes, "terminal result")
    if result_bytes != _canonical_bytes(result):
        raise P2cError("terminal result is not canonical")
    validated = _validate_result_contract(result, plan)
    _verify_result_authority(validated, claim, claim_sha256)
    secret_path = _authority_secret_path(secret_directory, attempt)
    live_secrets = _validate_authority_secret_directory(secret_directory)
    if live_secrets and (not allow_live_secret or live_secrets != [secret_path]):
        raise P2cError("terminal has unconsumed or unrelated authority secrets")
    return validated


def _external_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or EXTERNAL_ID.fullmatch(value) is None:
        raise P2cError(f"{label} is not a canonical external identifier")
    return value


def _anchor_local_evidence(
    run_directory: Path,
    chain: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    result = _validate_terminal(run_directory, chain, plan)
    terminal = chain[-1]
    terminal_id = f"checkpoints/{len(chain):04d}-terminal.json"
    result_id = f"attempt-results/{terminal['result_filename']}"
    claims = _load_claim_chain(
        run_directory / "authority-claims", _sha256_value(plan), plan["work_id"]
    )
    checkpoint_entries = [
        {
            "id": f"checkpoints/{sequence:04d}-{checkpoint['state'].casefold()}.json",
            "sha256": _checkpoint_hash(checkpoint),
        }
        for sequence, checkpoint in enumerate(chain, start=1)
    ]
    claim_entries = [
        {
            "id": f"authority-claims/{attempt:04d}-attempt-{attempt:04d}-claim.json",
            "sha256": _claim_hash(claim),
        }
        for attempt, claim in enumerate(claims, start=1)
    ]
    result_entries = [
        {
            "id": f"attempt-results/{path.name}",
            "sha256": _sha256_bytes(_safe_regular_bytes(path)),
            "size_bytes": len(_safe_regular_bytes(path)),
        }
        for path in _validate_attempt_result_directory(run_directory / "attempt-results")
    ]
    plan_sha256 = _sha256_value(plan)
    result_sha256 = terminal["result_sha256"]
    terminal_sha256 = _checkpoint_hash(terminal)
    core_entries = [
        {
            "id": "execution-plan.json",
            "sha256": plan_sha256,
            "size_bytes": len(_canonical_bytes(plan)),
        },
        *[
            {
                **entry,
                "size_bytes": len(_safe_regular_bytes(run_directory / entry["id"])),
            }
            for entry in checkpoint_entries
        ],
        *[
            {
                **entry,
                "size_bytes": len(_safe_regular_bytes(run_directory / entry["id"])),
            }
            for entry in claim_entries
        ],
        *result_entries,
    ]
    artifact_entries = sorted(
        [
            *core_entries,
        ],
        key=lambda entry: entry["id"],
    )
    artifact_manifest_sha256 = _sha256_value(artifact_entries)
    completed_id = f"mvx-p2c-completed:{plan['work_id']}:{terminal_sha256[:16]}"
    completed_sha256 = _sha256_value(
        {
            "artifact_manifest_sha256": artifact_manifest_sha256,
            "plan_sha256": plan_sha256,
            "result_sha256": result_sha256,
            "terminal_sha256": terminal_sha256,
            "work_id": plan["work_id"],
        }
    )
    return {
        "artifact_manifest_sha256": artifact_manifest_sha256,
        "authority_claim_chain_sha256": _sha256_value(claim_entries),
        "checkpoint_chain_sha256": _sha256_value(checkpoint_entries),
        "code_sha256": plan["code_sha256"],
        "completed_id": completed_id,
        "completed_sha256": completed_sha256,
        "input_binding_sha256": _sha256_value(plan["input_binding"]),
        "plan_sha256": plan_sha256,
        "result_id": result_id,
        "result_sha256": result_sha256,
        "runtime_sha256": _sha256_value(plan["environment"]),
        "source_sha256": plan["source_sha256"],
        "source_size_bytes": plan["source_size_bytes"],
        "terminal_id": terminal_id,
        "terminal_sha256": terminal_sha256,
        "work_id": plan["work_id"],
        "artifact_entries": artifact_entries,
        "result": result,
    }


def _external_anchor_message(unsigned_anchor: Mapping[str, Any]) -> bytes:
    return _canonical_bytes(
        {
            "anchor": dict(unsigned_anchor),
            "signature_domain": "MVX-P2C-EXTERNAL-COMPLETION-ANCHOR-ED25519-1",
        }
    )


def _anchor_readback_message(unsigned_receipt: Mapping[str, Any]) -> bytes:
    return _canonical_bytes(
        {
            "receipt": dict(unsigned_receipt),
            "signature_domain": "MVX-P2C-SIGNED-ANCHOR-READBACK-ED25519-1",
        }
    )


def build_anchor_readback_payload(anchor_path: Path) -> dict[str, Any]:
    """Build the receipt payload only after exact signed-anchor Drive readback."""

    anchor_bytes = _safe_regular_bytes(anchor_path)
    anchor = _decode_json(anchor_bytes, "signed external anchor")
    if anchor_bytes != _canonical_bytes(anchor) or not isinstance(anchor, dict):
        raise P2cError("signed external anchor readback is not canonical")
    if set(anchor) != EXTERNAL_ANCHOR_FIELDS:
        raise P2cError("signed external anchor readback contract is incomplete")
    return {
        "anchor_drive_file_id": anchor["external_anchor_id"],
        "anchor_parent_id": anchor["external_anchor_parent_id"],
        "anchor_sha256": _sha256_bytes(anchor_bytes),
        "anchor_size_bytes": len(anchor_bytes),
        "download_verified": True,
        "schema": "MVX-P2C-SIGNED-ANCHOR-READBACK-RECEIPT",
        "schema_version": "0.1.0",
        "trust_model": EXTERNAL_ANCHOR_TRUST_MODEL,
    }


def _validate_anchor_readback_receipt(
    receipt: Any,
    anchor_bytes: bytes,
    anchor: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    if not isinstance(receipt, dict) or set(receipt) != ANCHOR_READBACK_FIELDS:
        raise P2cError("signed anchor readback receipt has unknown or missing fields")
    unsigned = {
        name: value
        for name, value in receipt.items()
        if name not in {"signature_algorithm", "signature_hex"}
    }
    if (
        receipt["schema"] != "MVX-P2C-SIGNED-ANCHOR-READBACK-RECEIPT"
        or receipt["schema_version"] != "0.1.0"
        or receipt["trust_model"] != EXTERNAL_ANCHOR_TRUST_MODEL
        or receipt["download_verified"] is not True
        or receipt["anchor_drive_file_id"] != anchor["external_anchor_id"]
        or receipt["anchor_parent_id"] != anchor["external_anchor_parent_id"]
        or receipt["anchor_sha256"] != _sha256_bytes(anchor_bytes)
        or receipt["anchor_size_bytes"] != len(anchor_bytes)
    ):
        raise P2cError("signed anchor readback receipt does not bind exact downloaded bytes")
    _external_identifier(receipt["anchor_drive_file_id"], "readback anchor Drive file ID")
    _external_identifier(receipt["anchor_parent_id"], "readback anchor parent ID")
    _require_sha256(receipt["anchor_sha256"], "readback anchor hash")
    if (
        not _is_nonnegative_integer(receipt["anchor_size_bytes"])
        or receipt["signature_algorithm"] != "ED25519"
        or not isinstance(receipt["signature_hex"], str)
        or re.fullmatch(r"[0-9a-f]{128}", receipt["signature_hex"]) is None
    ):
        raise P2cError("signed anchor readback receipt fields are invalid")
    public_key_hex = plan.get("external_anchor_public_key_hex")
    if public_key_hex is None:
        raise P2cError("execution plan has no external readback verifier")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(
            bytes.fromhex(receipt["signature_hex"]),
            _anchor_readback_message(unsigned),
        )
    except (InvalidSignature, ValueError) as error:
        raise P2cError("signed anchor readback receipt signature is invalid") from error


def build_drive_evidence_document(
    run_directory: Path,
    chain: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the exact local evidence document that must be read back from Drive."""

    evidence = _anchor_local_evidence(run_directory, chain, plan)
    return {
        "artifact_entries": evidence["artifact_entries"],
        "local_evidence": {
            name: value
            for name, value in evidence.items()
            if name not in {"artifact_entries", "result"}
        },
        "publication_policy": "CHECKPOINT_THEN_COMPLETED_THEN_LATEST_AFTER_FULL_READBACK",
        "schema": "MVX-P2C-DRIVE-EVIDENCE",
        "schema_version": "0.1.0",
        "trust_scope": "P2C_AUXILIARY_REUSE_ONLY_NEVER_SOLID_V",
    }


def _verified_drive_receipt(
    *,
    drive_checkpoint: Path,
    drive_completed: Path,
    drive_latest: Path,
    drive_artifact_map: Path,
    completed_drive_id: str,
    latest_drive_id: str,
    expected_drive_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    guard = _load_backup_guard_module()
    checkpoint_bytes = _safe_regular_bytes(drive_checkpoint, guard.MAX_JSON_BYTES)
    completed_bytes = _safe_regular_bytes(drive_completed, guard.MAX_JSON_BYTES)
    latest_bytes = _safe_regular_bytes(drive_latest, guard.MAX_JSON_BYTES)
    checkpoint = _decode_json(checkpoint_bytes, "Drive checkpoint")
    completed = _decode_json(completed_bytes, "Drive COMPLETED marker")
    latest = _decode_json(latest_bytes, "Drive LATEST pointer")
    if not all(isinstance(value, dict) for value in (checkpoint, completed, latest)):
        raise P2cError("materialised Drive triplet roots must be objects")
    _external_identifier(completed_drive_id, "Drive COMPLETED file ID")
    _external_identifier(latest_drive_id, "Drive LATEST file ID")
    try:
        guard_summary = guard.verify_chain(
            checkpoint_bytes=checkpoint_bytes,
            checkpoint=checkpoint,
            completed_bytes=completed_bytes,
            completed=completed,
            latest=latest,
            completed_drive_id=completed_drive_id,
        )
        expected_artifacts = guard._artifact_contract(checkpoint)
        artifact_origin, embedded = guard._artifact_origin_contract(checkpoint)
    except Exception as error:
        raise P2cError("materialised Drive checkpoint chain failed exact guard") from error
    map_bytes = _safe_regular_bytes(drive_artifact_map, guard.MAX_JSON_BYTES)
    raw_map = _decode_json(map_bytes, "Drive artifact map")
    if not isinstance(raw_map, dict) or set(raw_map) != set(expected_artifacts):
        raise P2cError("materialised Drive artifact map set is not exact")
    materialised: dict[str, tuple[bytes, Any]] = {}
    for file_id, raw_path in raw_map.items():
        if not isinstance(file_id, str) or not isinstance(raw_path, str) or not raw_path:
            raise P2cError("materialised Drive artifact map row is invalid")
        path = Path(raw_path)
        if not path.is_absolute():
            path = drive_artifact_map.parent / path
        payload = _safe_regular_bytes(path, DEFAULT_MAX_INPUT_BYTES)
        expected_size, expected_sha256 = expected_artifacts[file_id]
        if len(payload) != expected_size or _sha256_bytes(payload) != expected_sha256:
            raise P2cError("materialised Drive artifact differs from checkpoint")
        decoded: Any = None
        with contextlib.suppress(P2cError):
            decoded = _decode_json(payload, "materialised Drive JSON artifact")
        materialised[file_id] = (payload, decoded)
    for file_id in embedded.values():
        decoded = materialised[file_id][1]
        if not isinstance(decoded, dict) or decoded.get("checkpoint_id") != artifact_origin:
            raise P2cError("materialised Drive artifact origin is invalid")
    matching_evidence = [
        (file_id, payload)
        for file_id, (payload, decoded) in materialised.items()
        if decoded == expected_drive_evidence
    ]
    if len(matching_evidence) != 1:
        raise P2cError(
            "Drive artifact set does not contain exactly one exact P2c evidence document"
        )
    checkpoint_registry = completed.get("checkpoint_registry")
    if not isinstance(checkpoint_registry, dict):
        raise P2cError("Drive COMPLETED checkpoint registry is invalid")
    artifact_rows = [
        {
            "download_verified": True,
            "drive_file_id": file_id,
            "sha256": expected_artifacts[file_id][1],
            "size_bytes": expected_artifacts[file_id][0],
        }
        for file_id in sorted(expected_artifacts)
    ]
    checkpoint_id = guard_summary["checkpoint_id"]
    return {
        "artifact_set": artifact_rows,
        "artifact_set_sha256": _sha256_value(artifact_rows),
        "backup_guard_code_sha256": _sha256_bytes(BACKUP_GUARD_SCRIPT.read_bytes()),
        "checkpoint": {
            "download_verified": True,
            "drive_file_id": checkpoint_registry["drive_file_id"],
            "sha256": _sha256_bytes(checkpoint_bytes),
            "size_bytes": len(checkpoint_bytes),
        },
        "checkpoint_id": checkpoint_id,
        "completed": {
            "download_verified": True,
            "drive_file_id": completed_drive_id,
            "sha256": _sha256_bytes(completed_bytes),
            "size_bytes": len(completed_bytes),
        },
        "drive_evidence_file_id": matching_evidence[0][0],
        "drive_evidence_sha256": _sha256_bytes(matching_evidence[0][1]),
        "guard_summary_sha256": _sha256_value(guard_summary),
        "latest": {
            "download_verified": True,
            "drive_file_id": latest_drive_id,
            "sha256": _sha256_bytes(latest_bytes),
            "size_bytes": len(latest_bytes),
        },
        "predecessor_checkpoint_id": checkpoint["predecessor_checkpoint_id"],
        "publication_model": "APPEND_ONLY_CHECKPOINT_COMPLETED_MUTABLE_LATEST",
        "publication_order": ["ARTIFACTS", "CHECKPOINT", "COMPLETED", "LATEST"],
        "schema": "MVX-P2C-VERIFIED-DRIVE-RECEIPT",
        "schema_version": "0.1.0",
        "trust_scope": "P2C_AUXILIARY_REUSE_ONLY_NEVER_SOLID_V",
    }


def build_external_anchor_payload(
    run_directory: Path,
    chain: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
    *,
    drive_checkpoint: Path,
    drive_completed: Path,
    drive_latest: Path,
    drive_artifact_map: Path,
    completed_drive_id: str,
    latest_drive_id: str,
    signed_anchor_drive_file_id: str,
    signed_anchor_parent_id: str,
) -> dict[str, Any]:
    """Build canonical bytes that the precommitted external authority must sign."""

    if plan.get("external_anchor_public_key_hex") is None:
        raise P2cError("execution plan did not precommit an external anchor public key")
    _external_identifier(signed_anchor_drive_file_id, "signed anchor Drive file ID")
    _external_identifier(signed_anchor_parent_id, "signed anchor Drive parent ID")
    evidence = _anchor_local_evidence(run_directory, chain, plan)
    drive_evidence = build_drive_evidence_document(run_directory, chain, plan)
    drive_receipt = _verified_drive_receipt(
        drive_checkpoint=drive_checkpoint,
        drive_completed=drive_completed,
        drive_latest=drive_latest,
        drive_artifact_map=drive_artifact_map,
        completed_drive_id=completed_drive_id,
        latest_drive_id=latest_drive_id,
        expected_drive_evidence=drive_evidence,
    )
    return {
        **{
            name: value
            for name, value in evidence.items()
            if name not in {"artifact_entries", "result"}
        },
        "anchor_persistence_policy": (
            "EXTERNAL_SIGNER_MUST_UPLOAD_SIGNED_BYTES_TO_PREALLOCATED_LOCATOR_AND_VERIFY_"
            "READBACK_BEFORE_REUSE"
        ),
        "drive_receipt": drive_receipt,
        "external_anchor_id": signed_anchor_drive_file_id,
        "external_anchor_parent_id": signed_anchor_parent_id,
        "external_checkpoint_id": drive_receipt["checkpoint_id"],
        "external_checkpoint_sha256": drive_receipt["checkpoint"]["sha256"],
        "schema": "MVX-P2C-EXTERNAL-COMPLETION-ANCHOR",
        "schema_version": "0.1.0",
        "trust_model": EXTERNAL_ANCHOR_TRUST_MODEL,
    }


def _validate_drive_file_receipt(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "download_verified",
        "drive_file_id",
        "sha256",
        "size_bytes",
    }:
        raise P2cError(f"{label} receipt fields are invalid")
    _external_identifier(value["drive_file_id"], f"{label} Drive file ID")
    _require_sha256(value["sha256"], f"{label} hash")
    if value["download_verified"] is not True or not _is_nonnegative_integer(value["size_bytes"]):
        raise P2cError(f"{label} was not fully read back")
    return value


def _validate_drive_receipt(value: Any) -> dict[str, Any]:
    expected = {
        "artifact_set",
        "artifact_set_sha256",
        "backup_guard_code_sha256",
        "checkpoint",
        "checkpoint_id",
        "completed",
        "drive_evidence_file_id",
        "drive_evidence_sha256",
        "guard_summary_sha256",
        "latest",
        "predecessor_checkpoint_id",
        "publication_model",
        "publication_order",
        "schema",
        "schema_version",
        "trust_scope",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise P2cError("verified Drive receipt has unknown or missing fields")
    if (
        value["schema"] != "MVX-P2C-VERIFIED-DRIVE-RECEIPT"
        or value["schema_version"] != "0.1.0"
        or value["trust_scope"] != "P2C_AUXILIARY_REUSE_ONLY_NEVER_SOLID_V"
        or value["publication_model"] != "APPEND_ONLY_CHECKPOINT_COMPLETED_MUTABLE_LATEST"
        or value["publication_order"] != ["ARTIFACTS", "CHECKPOINT", "COMPLETED", "LATEST"]
    ):
        raise P2cError("verified Drive receipt policy or trust scope is invalid")
    _external_identifier(value["checkpoint_id"], "Drive checkpoint ID")
    _external_identifier(value["predecessor_checkpoint_id"], "Drive predecessor checkpoint ID")
    for name in (
        "artifact_set_sha256",
        "backup_guard_code_sha256",
        "drive_evidence_sha256",
        "guard_summary_sha256",
    ):
        _require_sha256(value[name], f"Drive receipt {name}")
    if value["backup_guard_code_sha256"] != _sha256_bytes(BACKUP_GUARD_SCRIPT.read_bytes()):
        raise P2cError("Drive receipt used a different backup guard")
    for name in ("checkpoint", "completed", "latest"):
        _validate_drive_file_receipt(value[name], f"Drive {name}")
    artifact_set = value["artifact_set"]
    if not isinstance(artifact_set, list) or not artifact_set:
        raise P2cError("Drive artifact set is empty or invalid")
    validated_rows = [_validate_drive_file_receipt(row, "Drive artifact") for row in artifact_set]
    artifact_ids = [row["drive_file_id"] for row in validated_rows]
    if artifact_ids != sorted(set(artifact_ids)):
        raise P2cError("Drive artifact set is not uniquely sorted")
    if _sha256_value(validated_rows) != value["artifact_set_sha256"]:
        raise P2cError("Drive artifact set commitment is invalid")
    _external_identifier(value["drive_evidence_file_id"], "Drive evidence file ID")
    evidence_rows = [
        row for row in validated_rows if row["drive_file_id"] == value["drive_evidence_file_id"]
    ]
    if len(evidence_rows) != 1 or (evidence_rows[0]["sha256"] != value["drive_evidence_sha256"]):
        raise P2cError("Drive evidence artifact is absent from the exact artifact set")
    return value


def _validate_external_anchor(
    anchor: Any,
    run_directory: Path,
    chain: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(anchor, dict) or set(anchor) != EXTERNAL_ANCHOR_FIELDS:
        raise P2cError("external anchor has unknown or missing fields")
    unsigned_anchor = {
        name: value
        for name, value in anchor.items()
        if name not in {"signature_algorithm", "signature_hex"}
    }
    if (
        anchor["schema"] != "MVX-P2C-EXTERNAL-COMPLETION-ANCHOR"
        or anchor["schema_version"] != "0.1.0"
        or anchor["trust_model"] != EXTERNAL_ANCHOR_TRUST_MODEL
    ):
        raise P2cError("external anchor schema or trust model is invalid")
    if anchor["anchor_persistence_policy"] != (
        "EXTERNAL_SIGNER_MUST_UPLOAD_SIGNED_BYTES_TO_PREALLOCATED_LOCATOR_AND_VERIFY_"
        "READBACK_BEFORE_REUSE"
    ):
        raise P2cError("external anchor persistence policy is invalid")
    drive_receipt = _validate_drive_receipt(anchor["drive_receipt"])
    if (
        anchor["external_checkpoint_id"] != drive_receipt["checkpoint_id"]
        or anchor["external_checkpoint_sha256"] != drive_receipt["checkpoint"]["sha256"]
    ):
        raise P2cError("external anchor IDs do not bind the verified Drive receipt")
    public_key_hex = plan.get("external_anchor_public_key_hex")
    if public_key_hex is None:
        raise P2cError("execution plan has no precommitted external anchor verifier")
    if (
        anchor["signature_algorithm"] != "ED25519"
        or not isinstance(anchor["signature_hex"], str)
        or re.fullmatch(r"[0-9a-f]{128}", anchor["signature_hex"]) is None
    ):
        raise P2cError("external anchor signature fields are invalid")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(
            bytes.fromhex(anchor["signature_hex"]),
            _external_anchor_message(unsigned_anchor),
        )
    except (InvalidSignature, ValueError) as error:
        raise P2cError("external anchor signature is invalid") from error
    _external_identifier(anchor["external_anchor_id"], "external anchor ID")
    _external_identifier(anchor["external_anchor_parent_id"], "external anchor parent ID")
    _external_identifier(anchor["external_checkpoint_id"], "external checkpoint ID")
    for name in EXTERNAL_ANCHOR_UNSIGNED_FIELDS - {
        "anchor_persistence_policy",
        "completed_id",
        "drive_receipt",
        "external_anchor_id",
        "external_anchor_parent_id",
        "external_checkpoint_id",
        "result_id",
        "schema",
        "schema_version",
        "source_size_bytes",
        "terminal_id",
        "trust_model",
    }:
        _require_sha256(anchor[name], f"external anchor {name}")
    for name in ("completed_id", "result_id", "terminal_id"):
        _external_identifier(anchor[name], f"external anchor {name}")
    if not _is_nonnegative_integer(anchor["source_size_bytes"]):
        raise P2cError("external anchor source size is invalid")
    evidence = _anchor_local_evidence(run_directory, chain, plan)
    expected = {
        name: value
        for name, value in evidence.items()
        if name not in {"artifact_entries", "result"}
    }
    if any(anchor[name] != value for name, value in expected.items()):
        raise P2cError("external anchor differs from the complete local terminal evidence")
    return evidence["result"]


def _validate_external_anchor_files(
    anchor_path: Path,
    readback_receipt_path: Path,
    run_directory: Path,
    chain: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    anchor_bytes = _safe_regular_bytes(anchor_path)
    anchor = _decode_json(anchor_bytes, "external anchor")
    if anchor_bytes != _canonical_bytes(anchor):
        raise P2cError("external anchor is not canonical")
    result = _validate_external_anchor(anchor, run_directory, chain, plan)
    receipt = _load_json(readback_receipt_path)
    _validate_anchor_readback_receipt(receipt, anchor_bytes, anchor, plan)
    return result


def _error_analysis(limits: Limits, code: str, diagnostic: str) -> dict[str, Any]:
    return _analysis_result(
        ERROR,
        limits,
        error_code=code,
        diagnostic=diagnostic,
        mesh=None,
        broadphase=None,
    )


def _resource_analysis(limits: Limits, code: str, diagnostic: str) -> dict[str, Any]:
    return _analysis_result(
        RESOURCE_LIMIT,
        limits,
        error_code=code,
        diagnostic=diagnostic,
        mesh=None,
        broadphase=None,
    )


def _child_limits(seconds: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))
    resource.setrlimit(
        resource.RLIMIT_AS,
        (CHILD_ADDRESS_SPACE_BYTES, CHILD_ADDRESS_SPACE_BYTES),
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _limit_arguments(limits: Limits) -> list[str]:
    return [
        "--max-vertices",
        str(limits.max_vertices),
        "--max-triangles",
        str(limits.max_triangles),
        "--max-candidate-pairs",
        str(limits.max_candidate_pairs),
        "--max-coordinate-bits",
        str(limits.max_coordinate_bits),
        "--max-runtime-seconds",
        str(limits.max_runtime_seconds),
    ]


def _run_analysis_child(mesh_bytes: bytes, limits: Limits) -> dict[str, Any]:
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONHASHSEED": "0",
        "PYTHONINTMAXSTRDIGITS": str(sys.get_int_max_str_digits()),
        "TZ": "UTC",
    }
    command = (
        sys.executable,
        str(Path(__file__).resolve()),
        "_child-analyze",
        *_limit_arguments(limits),
    )
    try:
        completed = subprocess.run(
            command,
            input=mesh_bytes,
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            preexec_fn=lambda: _child_limits(limits.max_runtime_seconds),
            timeout=limits.max_runtime_seconds + 2,
        )
    except subprocess.TimeoutExpired:
        return _resource_analysis(
            limits,
            "CHILD_TIMEOUT",
            "ISOLATED_EXACT_CHILD_TIMEOUT",
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ChildNoStatus("cannot execute isolated exact child") from error
    if len(completed.stdout) > CHILD_OUTPUT_BYTES or len(completed.stderr) > CHILD_OUTPUT_BYTES:
        raise ChildNoStatus("isolated exact child exceeded its output contract")
    if completed.returncode < 0 and -completed.returncode == signal.SIGXCPU:
        return _resource_analysis(
            limits,
            "CHILD_CPU_LIMIT",
            "ISOLATED_EXACT_CHILD_CPU_LIMIT",
        )
    if completed.returncode != 0:
        raise ChildNoStatus("isolated exact child exited without a result")
    result = _decode_json(completed.stdout, "isolated exact child result")
    try:
        return _validate_analysis_contract(result, limits.as_dict())
    except P2cError as error:
        raise ChildNoStatus("isolated exact child result contract is invalid") from error


def _load_p2a_module() -> Any:
    spec = importlib.util.spec_from_file_location("mvx_p2a_checkpoint_for_p2c", P2A_SCRIPT)
    if spec is None or spec.loader is None:
        raise P2cError("cannot load the P2a verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_backup_guard_module() -> Any:
    spec = importlib.util.spec_from_file_location("mvx_backup_guard_for_p2c", BACKUP_GUARD_SCRIPT)
    if spec is None or spec.loader is None:
        raise P2cError("cannot load the Drive backup guard")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _canonicalise_materialised_mesh(
    vertices: Sequence[Sequence[float]], faces: Sequence[Sequence[int]]
) -> bytes:
    canonical_vertices: list[list[float]] = []
    vertex_map: dict[tuple[float, float, float], int] = {}
    remap: list[int] = []
    for raw in vertices:
        vertex = tuple(0.0 if float(value) == 0.0 else float(value) for value in raw)
        if vertex not in vertex_map:
            vertex_map[vertex] = len(canonical_vertices)
            canonical_vertices.append(list(vertex))
        remap.append(vertex_map[vertex])
    canonical_faces = [[remap[int(index)] for index in face] for face in faces]
    return _canonical_bytes(
        {
            "schema": MESH_SCHEMA,
            "schema_version": MESH_SCHEMA_VERSION,
            "triangles": canonical_faces,
            "vertices": canonical_vertices,
        }
    )


def _prepare_p2a_binding(
    source_glb: Path,
    audit_record_path: Path,
    execution_plan_path: Path,
    checkpoint_directory: Path,
    max_input_bytes: int,
) -> tuple[FileSnapshot, bytes, dict[str, Any]]:
    source = _snapshot_regular(source_glb, max_input_bytes)
    if source.payload is None:
        raise P2cError("P2a-bound GLB exceeds the P2c materialization byte limit")
    audit_bytes = _safe_regular_bytes(audit_record_path)
    plan_bytes = _safe_regular_bytes(execution_plan_path)
    audit_record = _decode_json(audit_bytes, "P2a audit record")
    raw_plan = _decode_json(plan_bytes, "P2a execution plan")
    p2a = _load_p2a_module()
    try:
        plan = p2a.checkpoint_module.validate_execution_plan(raw_plan)
    except Exception as error:
        raise P2cError("P2a execution plan failed exact validation") from error
    expected_audit_fields = {
        "audit",
        "candidate_commitment_sha256",
        "code_git_commit_sha1",
        "code_git_tree_sha1",
        "schema",
        "schema_version",
        "work_id",
    }
    if not isinstance(audit_record, dict) or set(audit_record) != expected_audit_fields:
        raise P2cError("P2a audit record fields are invalid")
    p2a_work_id = _require_sha256(audit_record["work_id"], "P2a work ID")
    if (
        audit_record["schema"] != "MVX-P2A-PRIVATE-AUDIT-RECORD"
        or audit_record["schema_version"] != "0.1.0"
        or not re.fullmatch(r"[0-9a-f]{64}", str(audit_record["candidate_commitment_sha256"]))
        or not re.fullmatch(r"[0-9a-f]{40}", str(audit_record["code_git_commit_sha1"]))
        or not re.fullmatch(r"[0-9a-f]{40}", str(audit_record["code_git_tree_sha1"]))
    ):
        raise P2cError("P2a audit record identity is invalid")
    stages = [stage for stage in plan["stages"] if stage["work_id"] == p2a_work_id]
    if len(stages) != 1:
        raise P2cError("P2a execution plan does not bind exactly one audited stage")
    stage = stages[0]
    expected_p2a_config = p2a._canonical_hash(
        {
            "algorithm": p2a.AUDIT_ALGORITHM,
            "algorithm_version": p2a.AUDIT_ALGORITHM_VERSION,
            "candidate_commitment_sha256": audit_record["candidate_commitment_sha256"],
            "script_version": p2a.SCRIPT_VERSION,
        }
    )
    if (
        stage["identity"]["phase_id"] != "P2a"
        or stage["identity"]["stage_id"] != "GLB_SOURCE_AUDIT"
        or stage["identity"]["source_sha256"] != source.sha256
        or stage["identity"]["config_sha256"] != expected_p2a_config
        or "audit_record" not in stage["required_artifacts"]
    ):
        raise P2cError("P2a stage identity is incompatible with P2c")
    try:
        chain = p2a._load_checkpoint_chain(checkpoint_directory, plan, p2a_work_id)
    except Exception as error:
        raise P2cError("P2a checkpoint chain failed exact validation") from error
    if not chain or chain[-1]["state"] != "TERMINAL":
        raise P2cError("P2a checkpoint chain is not terminal")
    terminal = chain[-1]
    if terminal["artifact_hashes"].get("audit_record") != _sha256_bytes(audit_bytes):
        raise P2cError("P2a terminal does not bind the supplied audit record")
    audit = audit_record["audit"]
    try:
        audit = p2a._validate_audit_contract(
            audit,
            {"source_sha256": source.sha256, "source_size_bytes": source.size_bytes},
        )
    except Exception as error:
        raise P2cError("P2a audit contract failed exact validation") from error
    if (
        terminal["terminal_status"] != audit["terminal_status"]
        or terminal["error_code"] != audit["error_code"]
        or audit["geometry"] is None
    ):
        raise P2cError("P2a terminal and geometry audit are inconsistent")
    try:
        document, binary, container = p2a._parse_glb_container(source.payload)
        p2a._preflight_source_policy(document)
        vertices, faces, scene = p2a._materialise_scene(document, binary)
        topology, geometry = p2a._topology_evidence(vertices, faces)
    except Exception as error:
        raise P2cError("P2a canonical rematerialization failed") from error
    if (
        container != audit["container"]
        or scene != audit["scene"]
        or geometry != audit["geometry"]
        or topology != audit["topology_status"]
    ):
        raise P2cError("P2a rematerialization differs from sealed audit evidence")
    mesh_bytes = _canonicalise_materialised_mesh(vertices, faces)
    p2a_plan_sha = p2a.checkpoint_module.execution_plan_sha256(plan)
    if terminal["execution_plan_sha256"] != p2a_plan_sha:
        raise P2cError("P2a terminal plan hash is inconsistent")
    binding = {
        "audit_record_sha256": _sha256_bytes(audit_bytes),
        "execution_plan_file_sha256": _sha256_bytes(plan_bytes),
        "execution_plan_sha256": p2a_plan_sha,
        "materializer_code_sha256": _sha256_value(
            {
                "p2a_script_sha256": _sha256_bytes(P2A_SCRIPT.read_bytes()),
                "p2c_script_sha256": _script_sha256(),
            }
        ),
        "materializer_id": MATERIALIZER_ID,
        "materializer_version": MATERIALIZER_VERSION,
        "mesh_sha256": _sha256_bytes(mesh_bytes),
        "mode": "P2A_BOUND",
        "p2a_terminal_checkpoint_sha256": p2a.checkpoint_sha256(terminal),
        "p2a_work_id": p2a_work_id,
    }
    _validate_input_binding(binding)
    return source, mesh_bytes, binding


def _make_plan(
    source: FileSnapshot,
    binding: Mapping[str, Any],
    limits: Limits,
    max_input_bytes: int,
    authority_policy: str | None = None,
    external_anchor_public_key_hex: str | None = None,
) -> dict[str, Any]:
    selected_authority_policy = authority_policy or (
        REQUIRE_EXTERNAL_ANCHOR
        if external_anchor_public_key_hex is not None
        else UNANCHORED_DIAGNOSTIC
    )
    if selected_authority_policy not in AUTHORITY_POLICIES:
        raise P2cError("authority policy is invalid")
    if external_anchor_public_key_hex is not None and (
        not isinstance(external_anchor_public_key_hex, str)
        or re.fullmatch(r"[0-9a-f]{64}", external_anchor_public_key_hex) is None
    ):
        raise P2cError("external anchor public key is invalid")
    if (selected_authority_policy == REQUIRE_EXTERNAL_ANCHOR) != (
        external_anchor_public_key_hex is not None
    ):
        raise P2cError("authority policy and external anchor verifier are inconsistent")
    base = {
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "authority_policy": selected_authority_policy,
        "code_sha256": _script_sha256(),
        "environment": _runtime_identity(),
        "external_anchor_public_key_hex": external_anchor_public_key_hex,
        "input_binding": dict(binding),
        "limits": limits.as_dict(),
        "max_input_bytes": max_input_bytes,
        "schema": "MVX-P2C-EXECUTION-PLAN",
        "schema_version": "0.1.0",
        "source_sha256": source.sha256,
        "source_size_bytes": source.size_bytes,
    }
    return {**base, "work_id": _sha256_value(base)}


def _unsigned_result_from_analysis(
    analysis: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    _validate_analysis_contract(dict(analysis), plan["limits"])
    result = {
        **dict(analysis),
        "input_binding": plan["input_binding"],
        "plan_sha256": _sha256_value(plan),
        "source_sha256": plan["source_sha256"],
        "source_size_bytes": plan["source_size_bytes"],
        "work_id": plan["work_id"],
    }
    return result


def _result_from_analysis(
    analysis: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    attempt: int,
    claim_sha256: str,
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    unsigned = _unsigned_result_from_analysis(analysis, plan)
    authorization = {
        "attempt": attempt,
        "claim_sha256": claim_sha256,
        "signature_algorithm": "ED25519",
        "signature_hex": private_key.sign(
            _authorization_message(unsigned, claim_sha256, attempt)
        ).hex(),
        "trust_model": AUTHORITY_TRUST_MODEL,
    }
    return _validate_result_contract({**unsigned, "authorization": authorization}, plan)


def _validate_run_layout(run_directory: Path) -> None:
    descriptor = _open_real_directory(run_directory)
    try:
        for name in os.listdir(descriptor):
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if name in {
                "attempt-results",
                "authority-claims",
                "authority-secrets",
                "checkpoints",
                "staging",
            }:
                if not stat.S_ISDIR(metadata.st_mode):
                    raise P2cError("run subdirectory is not a real directory")
            elif name == "execution-plan.json":
                if not stat.S_ISREG(metadata.st_mode):
                    raise P2cError("run artifact is not a regular file")
            else:
                raise P2cError("run directory contains an unknown entry")
    finally:
        os.close(descriptor)


def _terminalize(
    analysis: Mapping[str, Any],
    plan: Mapping[str, Any],
    run_directory: Path,
    checkpoint_directory: Path,
    chain: list[dict[str, Any]],
    attempt: int,
    claim: Mapping[str, Any],
    claim_sha256: str,
    private_key: Ed25519PrivateKey,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if _script_sha256() != plan["code_sha256"] or _runtime_identity() != plan["environment"]:
        raise P2cError("code or runtime identity changed before terminal publication")
    if (
        claim["attempt"] != attempt
        or _claim_hash(claim) != claim_sha256
        or not chain
        or chain[-1]["state"] != "RUNNING"
        or chain[-1]["attempt"] != attempt
        or chain[-1]["claim_sha256"] != claim_sha256
    ):
        raise P2cError("terminalization authority differs from RUNNING claim")
    result = _result_from_analysis(
        analysis,
        plan,
        attempt=attempt,
        claim_sha256=claim_sha256,
        private_key=private_key,
    )
    _verify_result_authority(result, claim, claim_sha256)
    result_bytes = _canonical_bytes(result)
    result_sha256 = _sha256_bytes(result_bytes)
    result_filename = f"attempt-{attempt:04d}-{result_sha256[:16]}.json"
    _publish_once(run_directory / "attempt-results" / result_filename, result_bytes)
    terminal = _append_checkpoint(
        checkpoint_directory,
        chain,
        state="TERMINAL",
        attempt=attempt,
        plan_sha256=_sha256_value(plan),
        work_id=plan["work_id"],
        claim_sha256=claim_sha256,
        result_filename=result_filename,
        result_sha256=result_sha256,
    )
    _validate_terminal(run_directory, chain, plan, allow_live_secret=True)
    _unlink_private_regular(
        _authority_secret_path(run_directory / "authority-secrets", attempt),
        expected_mode=0o400,
    )
    _validate_terminal(run_directory, chain, plan)
    return result, terminal


def _validate_checkpoint_claim_bindings(
    chain: Sequence[Mapping[str, Any]], claims: Sequence[Mapping[str, Any]]
) -> None:
    for checkpoint in chain:
        if checkpoint["state"] == "PENDING":
            continue
        attempt = checkpoint["attempt"]
        if attempt > len(claims) or checkpoint["claim_sha256"] != _claim_hash(claims[attempt - 1]):
            raise P2cError("checkpoint does not bind the immutable authority claim")
    if not chain:
        if claims:
            raise P2cError("authority claim exists before checkpoint chain")
        return
    last = chain[-1]
    bound_attempt = max(
        (checkpoint["attempt"] for checkpoint in chain if checkpoint["state"] != "PENDING"),
        default=0,
    )
    if len(claims) < bound_attempt or len(claims) > bound_attempt + 1:
        raise P2cError("authority claim chain and checkpoint chain diverge")
    if len(claims) == bound_attempt + 1 and not (
        (last["state"] == "PENDING" and bound_attempt == 0)
        or (last["state"] == "INTERRUPTED" and len(claims) == last["attempt"] + 1)
    ):
        raise P2cError("unbound authority claim is not a valid pre-RUNNING claim")


def _consume_verified_terminal_secret(
    run_directory: Path,
    chain: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    result = _validate_terminal(run_directory, chain, plan, allow_live_secret=True)
    terminal = chain[-1]
    secret_path = _authority_secret_path(run_directory / "authority-secrets", terminal["attempt"])
    if _authority_secret_exists(secret_path):
        _unlink_private_regular(secret_path, expected_mode=0o400)
    strict_result = _validate_terminal(run_directory, chain, plan)
    if strict_result != result:
        raise P2cError("terminal result changed while consuming authority secret")
    return strict_result


def _run_prepared(
    source: FileSnapshot,
    mesh_bytes: bytes | None,
    binding: Mapping[str, Any],
    output_root: Path,
    limits: Limits,
    max_input_bytes: int,
    external_anchor: Path | None = None,
    external_anchor_readback_receipt: Path | None = None,
    external_anchor_public_key_hex: str | None = None,
) -> dict[str, Any]:
    output = _ensure_private_tree(output_root)
    plan = _make_plan(
        source,
        binding,
        limits,
        max_input_bytes,
        external_anchor_public_key_hex=external_anchor_public_key_hex,
    )
    work_id = plan["work_id"]
    plan_sha256 = _sha256_value(plan)
    run_directory = _ensure_private_tree(output / "runs" / work_id)
    checkpoint_directory = _ensure_private_tree(run_directory / "checkpoints")
    claim_directory = _ensure_private_tree(run_directory / "authority-claims")
    secret_directory = _ensure_private_tree(run_directory / "authority-secrets")
    _ensure_private_tree(run_directory / "attempt-results")
    with _exclusive_lock(output / "locks", work_id):
        _validate_run_layout(run_directory)
        _validate_authority_secret_directory(secret_directory)
        _validate_attempt_result_directory(run_directory / "attempt-results")
        _publish_once(run_directory / "execution-plan.json", _canonical_bytes(plan))
        if _load_json(run_directory / "execution-plan.json") != plan:
            raise P2cError("persisted execution plan differs")
        chain = _load_checkpoint_chain(checkpoint_directory, plan_sha256, work_id)
        claims = _load_claim_chain(claim_directory, plan_sha256, work_id)
        _validate_checkpoint_claim_bindings(chain, claims)
        if chain and chain[-1]["state"] == "TERMINAL":
            result = _consume_verified_terminal_secret(run_directory, chain, plan)
            if external_anchor is None and external_anchor_readback_receipt is None:
                return {
                    "action": "READY_FOR_BACKUP",
                    "result": result,
                    "terminal_checkpoint_sha256": _checkpoint_hash(chain[-1]),
                    "work_id": work_id,
                }
            if external_anchor is None or external_anchor_readback_receipt is None:
                raise P2cError("anchored reuse requires anchor and signed readback receipt")
            anchored_result = _validate_external_anchor_files(
                external_anchor,
                external_anchor_readback_receipt,
                run_directory,
                chain,
                plan,
            )
            if anchored_result != result:
                raise P2cError("external anchor validation changed terminal result")
            return {
                "action": "SKIP_ANCHORED",
                "result": result,
                "terminal_checkpoint_sha256": _checkpoint_hash(chain[-1]),
                "work_id": work_id,
            }
        if external_anchor is not None or external_anchor_readback_receipt is not None:
            raise P2cError("external anchor cannot authorize a non-terminal local run")

        if not chain:
            _append_checkpoint(
                checkpoint_directory,
                chain,
                state="PENDING",
                attempt=1,
                plan_sha256=plan_sha256,
                work_id=work_id,
            )
        while True:
            previous = chain[-1]
            if previous["state"] == "RUNNING":
                claim, claim_sha256, private_key = _ensure_attempt_claim(
                    claim_directory,
                    secret_directory,
                    attempt=previous["attempt"],
                    plan_sha256=plan_sha256,
                    work_id=work_id,
                )
                if claim_sha256 != previous["claim_sha256"]:
                    raise P2cError("stale RUNNING checkpoint authority claim differs")
                if previous["attempt"] >= MAX_ATTEMPTS:
                    analysis = _error_analysis(
                        limits,
                        "CHILD_RETRY_EXHAUSTED",
                        "ISOLATED_CHILD_RETRY_BUDGET_EXHAUSTED",
                    )
                    result, terminal = _terminalize(
                        analysis,
                        plan,
                        run_directory,
                        checkpoint_directory,
                        chain,
                        previous["attempt"],
                        claim,
                        claim_sha256,
                        private_key,
                    )
                    break
                _append_checkpoint(
                    checkpoint_directory,
                    chain,
                    state="INTERRUPTED",
                    attempt=previous["attempt"],
                    plan_sha256=plan_sha256,
                    work_id=work_id,
                    claim_sha256=claim_sha256,
                )
                _unlink_private_regular(
                    _authority_secret_path(secret_directory, previous["attempt"]),
                    expected_mode=0o400,
                )
                previous = chain[-1]
            if previous["state"] == "PENDING":
                attempt = 1
            elif previous["state"] == "INTERRUPTED":
                interrupted_secret = _authority_secret_path(secret_directory, previous["attempt"])
                if _authority_secret_exists(interrupted_secret):
                    current_claims = _load_claim_chain(claim_directory, plan_sha256, work_id)
                    if previous["attempt"] > len(current_claims):
                        raise P2cError("interrupted checkpoint has no authority claim")
                    interrupted_claim = current_claims[previous["attempt"] - 1]
                    _load_authority_private_key(
                        interrupted_secret, interrupted_claim["public_key_hex"]
                    )
                    _unlink_private_regular(interrupted_secret, expected_mode=0o400)
                attempt = previous["attempt"] + 1
            else:
                raise P2cError("checkpoint chain cannot resume")
            claim, claim_sha256, private_key = _ensure_attempt_claim(
                claim_directory,
                secret_directory,
                attempt=attempt,
                plan_sha256=plan_sha256,
                work_id=work_id,
            )
            _append_checkpoint(
                checkpoint_directory,
                chain,
                state="RUNNING",
                attempt=attempt,
                plan_sha256=plan_sha256,
                work_id=work_id,
                claim_sha256=claim_sha256,
            )
            if source.over_limit:
                analysis = _resource_analysis(
                    limits,
                    "MAX_INPUT_BYTES",
                    "SOURCE_EXCEEDS_DECLARED_INPUT_BOUND",
                )
            elif mesh_bytes is None:
                raise P2cError("retained mesh bytes are missing below the input limit")
            else:
                try:
                    analysis = _run_analysis_child(mesh_bytes, limits)
                except ChildNoStatus:
                    if attempt < MAX_ATTEMPTS:
                        _append_checkpoint(
                            checkpoint_directory,
                            chain,
                            state="INTERRUPTED",
                            attempt=attempt,
                            plan_sha256=plan_sha256,
                            work_id=work_id,
                            claim_sha256=claim_sha256,
                        )
                        _unlink_private_regular(
                            _authority_secret_path(secret_directory, attempt),
                            expected_mode=0o400,
                        )
                        continue
                    analysis = _error_analysis(
                        limits,
                        "CHILD_RETRY_EXHAUSTED",
                        "ISOLATED_CHILD_RETRY_BUDGET_EXHAUSTED",
                    )
            result, terminal = _terminalize(
                analysis,
                plan,
                run_directory,
                checkpoint_directory,
                chain,
                attempt,
                claim,
                claim_sha256,
                private_key,
            )
            break
        return {
            "action": "COMPLETED_UNANCHORED",
            "result": result,
            "terminal_checkpoint_sha256": _checkpoint_hash(terminal),
            "work_id": work_id,
        }


def run_checkpointed(
    mesh_path: Path,
    output_root: Path,
    limits: Limits | None = None,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    external_anchor: Path | None = None,
    external_anchor_readback_receipt: Path | None = None,
    external_anchor_public_key_hex: str | None = None,
) -> dict[str, Any]:
    selected_limits = limits or Limits()
    selected_limits.validate()
    if (
        isinstance(max_input_bytes, bool)
        or not isinstance(max_input_bytes, int)
        or max_input_bytes <= 0
    ):
        raise P2cError("max_input_bytes must be a positive integer")
    source = _snapshot_regular(mesh_path, max_input_bytes)
    binding = {"mesh_sha256": source.sha256, "mode": "CANONICAL_MESH"}
    if (external_anchor is None) != (external_anchor_readback_receipt is None):
        raise P2cError("external anchor and signed readback receipt must be supplied together")
    if external_anchor is not None:
        if external_anchor_public_key_hex is None:
            raise P2cError("external anchor reuse requires the precommitted public key")
        anchor = _load_json(external_anchor)
        candidate = _make_plan(
            source,
            binding,
            selected_limits,
            max_input_bytes,
            external_anchor_public_key_hex=external_anchor_public_key_hex,
        )
        if not isinstance(anchor, dict) or anchor.get("work_id") != candidate["work_id"]:
            raise P2cError("external anchor work ID differs from source, limits, code or key")
    return _run_prepared(
        source,
        source.payload,
        binding,
        output_root,
        selected_limits,
        max_input_bytes,
        external_anchor,
        external_anchor_readback_receipt,
        external_anchor_public_key_hex,
    )


def run_checkpointed_p2a(
    source_glb: Path,
    audit_record: Path,
    execution_plan: Path,
    p2a_checkpoint_directory: Path,
    output_root: Path,
    limits: Limits | None = None,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    external_anchor: Path | None = None,
    external_anchor_readback_receipt: Path | None = None,
    external_anchor_public_key_hex: str | None = None,
) -> dict[str, Any]:
    selected_limits = limits or Limits()
    selected_limits.validate()
    if (
        isinstance(max_input_bytes, bool)
        or not isinstance(max_input_bytes, int)
        or max_input_bytes <= 0
    ):
        raise P2cError("max_input_bytes must be a positive integer")
    source, mesh_bytes, binding = _prepare_p2a_binding(
        source_glb,
        audit_record,
        execution_plan,
        p2a_checkpoint_directory,
        max_input_bytes,
    )
    if (external_anchor is None) != (external_anchor_readback_receipt is None):
        raise P2cError("external anchor and signed readback receipt must be supplied together")
    if external_anchor is not None:
        if external_anchor_public_key_hex is None:
            raise P2cError("external anchor reuse requires the precommitted public key")
        anchor = _load_json(external_anchor)
        candidate = _make_plan(
            source,
            binding,
            selected_limits,
            max_input_bytes,
            external_anchor_public_key_hex=external_anchor_public_key_hex,
        )
        if not isinstance(anchor, dict) or anchor.get("work_id") != candidate["work_id"]:
            raise P2cError("external anchor work ID differs from source, limits, code or key")
    return _run_prepared(
        source,
        mesh_bytes,
        binding,
        output_root,
        selected_limits,
        max_input_bytes,
        external_anchor,
        external_anchor_readback_receipt,
        external_anchor_public_key_hex,
    )


def _validate_persisted_plan(plan: Any, expected_work_id: str) -> dict[str, Any]:
    expected = {
        "algorithm_id",
        "algorithm_version",
        "authority_policy",
        "code_sha256",
        "environment",
        "external_anchor_public_key_hex",
        "input_binding",
        "limits",
        "max_input_bytes",
        "schema",
        "schema_version",
        "source_sha256",
        "source_size_bytes",
        "work_id",
    }
    if not isinstance(plan, dict) or set(plan) != expected:
        raise P2cError("persisted execution plan has unknown or missing fields")
    base = {name: value for name, value in plan.items() if name != "work_id"}
    if (
        plan["schema"] != "MVX-P2C-EXECUTION-PLAN"
        or plan["schema_version"] != "0.1.0"
        or plan["algorithm_id"] != ALGORITHM_ID
        or plan["algorithm_version"] != ALGORITHM_VERSION
        or plan["authority_policy"] not in AUTHORITY_POLICIES
        or plan["work_id"] != expected_work_id
        or _sha256_value(base) != expected_work_id
        or plan["code_sha256"] != _script_sha256()
        or plan["environment"] != _runtime_identity()
    ):
        raise P2cError("persisted execution plan identity is invalid")
    _validate_input_binding(plan["input_binding"])
    public_key_hex = plan["external_anchor_public_key_hex"]
    if public_key_hex is not None and (
        not isinstance(public_key_hex, str) or re.fullmatch(r"[0-9a-f]{64}", public_key_hex) is None
    ):
        raise P2cError("persisted plan external anchor public key is invalid")
    if (plan["authority_policy"] == REQUIRE_EXTERNAL_ANCHOR) != (public_key_hex is not None):
        raise P2cError("persisted plan authority policy and verifier are inconsistent")
    _require_sha256(plan["source_sha256"], "persisted plan source hash")
    if not _is_nonnegative_integer(plan["source_size_bytes"]):
        raise P2cError("persisted plan source size is invalid")
    if (
        isinstance(plan["max_input_bytes"], bool)
        or not isinstance(plan["max_input_bytes"], int)
        or plan["max_input_bytes"] <= 0
    ):
        raise P2cError("persisted plan input byte limit is invalid")
    if not isinstance(plan["limits"], dict):
        raise P2cError("persisted plan limits are invalid")
    try:
        limits = Limits(**plan["limits"])
    except TypeError as error:
        raise P2cError("persisted plan limits have unknown or missing fields") from error
    limits.validate()
    if limits.as_dict() != plan["limits"]:
        raise P2cError("persisted plan limits are not canonical")
    return plan


def _load_terminal_run(
    output_root: Path, work_id: str
) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    _require_sha256(work_id, "work ID")
    output = _private_candidate(output_root)
    run_directory = _private_candidate(output / "runs" / work_id)
    descriptor = _open_real_directory(run_directory)
    os.close(descriptor)
    _validate_run_layout(run_directory)
    _validate_authority_secret_directory(run_directory / "authority-secrets")
    _validate_attempt_result_directory(run_directory / "attempt-results")
    plan = _validate_persisted_plan(_load_json(run_directory / "execution-plan.json"), work_id)
    plan_sha256 = _sha256_value(plan)
    chain = _load_checkpoint_chain(run_directory / "checkpoints", plan_sha256, work_id)
    claims = _load_claim_chain(run_directory / "authority-claims", plan_sha256, work_id)
    _validate_checkpoint_claim_bindings(chain, claims)
    _validate_terminal(run_directory, chain, plan)
    return run_directory, chain, plan


def _add_limits(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-vertices", type=int, default=DEFAULT_MAX_VERTICES)
    parser.add_argument("--max-triangles", type=int, default=DEFAULT_MAX_TRIANGLES)
    parser.add_argument("--max-candidate-pairs", type=int, default=DEFAULT_MAX_CANDIDATE_PAIRS)
    parser.add_argument("--max-coordinate-bits", type=int, default=DEFAULT_MAX_COORDINATE_BITS)
    parser.add_argument("--max-runtime-seconds", type=int, default=DEFAULT_MAX_RUNTIME_SECONDS)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="run or safely resume one canonical mesh audit")
    run.add_argument("--mesh", required=True, type=Path)
    run.add_argument("--output-root", required=True, type=Path)
    run.add_argument("--max-input-bytes", type=int, default=DEFAULT_MAX_INPUT_BYTES)
    run.add_argument("--external-anchor", type=Path)
    run.add_argument("--external-anchor-readback-receipt", type=Path)
    run.add_argument("--external-anchor-public-key-hex")
    _add_limits(run)
    p2a_run = subcommands.add_parser("run-p2a", help="run from an exactly bound P2a terminal")
    p2a_run.add_argument("--source-glb", required=True, type=Path)
    p2a_run.add_argument("--audit-record", required=True, type=Path)
    p2a_run.add_argument("--execution-plan", required=True, type=Path)
    p2a_run.add_argument("--p2a-checkpoint-directory", required=True, type=Path)
    p2a_run.add_argument("--output-root", required=True, type=Path)
    p2a_run.add_argument("--max-input-bytes", type=int, default=DEFAULT_MAX_INPUT_BYTES)
    p2a_run.add_argument("--external-anchor", type=Path)
    p2a_run.add_argument("--external-anchor-readback-receipt", type=Path)
    p2a_run.add_argument("--external-anchor-public-key-hex")
    _add_limits(p2a_run)
    template = subcommands.add_parser(
        "anchor-template",
        help="emit canonical unsigned bytes for the precommitted external signer",
    )
    template.add_argument("--output-root", required=True, type=Path)
    template.add_argument("--work-id", required=True)
    template.add_argument("--drive-checkpoint", required=True, type=Path)
    template.add_argument("--drive-completed", required=True, type=Path)
    template.add_argument("--drive-latest", required=True, type=Path)
    template.add_argument("--drive-artifact-map", required=True, type=Path)
    template.add_argument("--completed-drive-id", required=True)
    template.add_argument("--latest-drive-id", required=True)
    template.add_argument("--signed-anchor-drive-file-id", required=True)
    template.add_argument("--signed-anchor-parent-id", required=True)
    drive_evidence = subcommands.add_parser(
        "drive-evidence",
        help="emit canonical P2c evidence that must be uploaded and read back before anchoring",
    )
    drive_evidence.add_argument("--output-root", required=True, type=Path)
    drive_evidence.add_argument("--work-id", required=True)
    validate_anchor = subcommands.add_parser(
        "validate-anchor", help="validate a canonical external anchor against local evidence"
    )
    validate_anchor.add_argument("--output-root", required=True, type=Path)
    validate_anchor.add_argument("--anchor", required=True, type=Path)
    validate_anchor.add_argument("--anchor-readback-receipt", required=True, type=Path)
    readback = subcommands.add_parser(
        "readback-receipt-template",
        help="emit unsigned receipt payload after exact signed-anchor Drive readback",
    )
    readback.add_argument("--anchor", required=True, type=Path)
    child = subcommands.add_parser("_child-analyze")
    _add_limits(child)
    return parser


def _limits_from_arguments(arguments: argparse.Namespace) -> Limits:
    return Limits(
        max_vertices=arguments.max_vertices,
        max_triangles=arguments.max_triangles,
        max_candidate_pairs=arguments.max_candidate_pairs,
        max_coordinate_bits=arguments.max_coordinate_bits,
        max_runtime_seconds=arguments.max_runtime_seconds,
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "_child-analyze":
        limits = _limits_from_arguments(arguments)
        try:
            decoded = _decode_json(sys.stdin.buffer.read(), "canonical mesh")
            if not isinstance(decoded, dict):
                raise P2cError("canonical mesh is not an object")
            analysis = analyze_mesh(decoded, limits)
        except P2cError:
            analysis = _error_analysis(limits, "INVALID_JSON", "JSON_INPUT_REJECTED")
        sys.stdout.buffer.write(_canonical_bytes(analysis))
        return 0
    try:
        if arguments.command == "run":
            limits = _limits_from_arguments(arguments)
            result = run_checkpointed(
                arguments.mesh,
                arguments.output_root,
                limits,
                max_input_bytes=arguments.max_input_bytes,
                external_anchor=arguments.external_anchor,
                external_anchor_readback_receipt=(arguments.external_anchor_readback_receipt),
                external_anchor_public_key_hex=arguments.external_anchor_public_key_hex,
            )
        elif arguments.command == "run-p2a":
            limits = _limits_from_arguments(arguments)
            result = run_checkpointed_p2a(
                arguments.source_glb,
                arguments.audit_record,
                arguments.execution_plan,
                arguments.p2a_checkpoint_directory,
                arguments.output_root,
                limits,
                max_input_bytes=arguments.max_input_bytes,
                external_anchor=arguments.external_anchor,
                external_anchor_readback_receipt=(arguments.external_anchor_readback_receipt),
                external_anchor_public_key_hex=arguments.external_anchor_public_key_hex,
            )
        elif arguments.command == "anchor-template":
            run_directory, chain, plan = _load_terminal_run(
                arguments.output_root, arguments.work_id
            )
            result = build_external_anchor_payload(
                run_directory,
                chain,
                plan,
                drive_checkpoint=arguments.drive_checkpoint,
                drive_completed=arguments.drive_completed,
                drive_latest=arguments.drive_latest,
                drive_artifact_map=arguments.drive_artifact_map,
                completed_drive_id=arguments.completed_drive_id,
                latest_drive_id=arguments.latest_drive_id,
                signed_anchor_drive_file_id=arguments.signed_anchor_drive_file_id,
                signed_anchor_parent_id=arguments.signed_anchor_parent_id,
            )
        elif arguments.command == "drive-evidence":
            run_directory, chain, plan = _load_terminal_run(
                arguments.output_root, arguments.work_id
            )
            result = build_drive_evidence_document(run_directory, chain, plan)
        elif arguments.command == "validate-anchor":
            anchor = _load_json(arguments.anchor)
            if not isinstance(anchor, dict) or "work_id" not in anchor:
                raise P2cError("external anchor has no work ID")
            run_directory, chain, plan = _load_terminal_run(
                arguments.output_root, anchor["work_id"]
            )
            anchored_result = _validate_external_anchor_files(
                arguments.anchor,
                arguments.anchor_readback_receipt,
                run_directory,
                chain,
                plan,
            )
            result = {
                "action": "ANCHOR_VALID",
                "result_sha256": chain[-1]["result_sha256"],
                "status": anchored_result["status"],
                "terminal_checkpoint_sha256": _checkpoint_hash(chain[-1]),
                "work_id": plan["work_id"],
            }
        elif arguments.command == "readback-receipt-template":
            result = build_anchor_readback_payload(arguments.anchor)
        else:
            raise AssertionError("unreachable command")
    except P2cError as error:
        print(_canonical_bytes({"action": ERROR, "diagnostic": str(error)}).decode(), end="")
        return 2
    print(_canonical_bytes(result).decode(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
