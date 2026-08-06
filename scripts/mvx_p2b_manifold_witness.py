#!/usr/bin/env python3
"""Restart-safe auxiliary Manifold witness for closed P2a ``U`` meshes.

P2b is deliberately not a solid verifier.  It never changes the primary P2a
classification and never emits ``V``.  It asks one locked third-party runtime
whether an already-canonical P2a mesh is accepted without an observable change.
All object-level outputs stay below the repository's ignored ``tmp`` tree.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import resource
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_ROOT.parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import mvx_p2a_checkpoint as p2a

from morphoia.mvx.checkpoint import (
    ResumeAction,
    WorkIdentity,
    assess_resume,
    checkpoint_sha256,
    hash_artifact,
    make_execution_plan,
    make_stage,
    make_stage_checkpoint,
)

SCRIPT_VERSION = "0.1.0"
ALGORITHM_ID = "MVX-P2B-MANIFOLD-AUXILIARY-WITNESS-1"
ALGORITHM_VERSION = "1.0.0"
RUNTIME_VERSION = "manifold-3d@3.5.1"
RUNTIME_ROOT = SCRIPTS_ROOT / "p2b-runtime"
PACKAGE_JSON = RUNTIME_ROOT / "package.json"
PACKAGE_LOCK = RUNTIME_ROOT / "package-lock.json"
WRAPPER = RUNTIME_ROOT / "manifold-witness.js"
INSTALL_ROOT = RUNTIME_ROOT / "node_modules/manifold-3d"
MANIFOLD_JS = INSTALL_ROOT / "manifold.js"
MANIFOLD_WASM = INSTALL_ROOT / "manifold.wasm"
INSTALLED_PACKAGE_JSON = INSTALL_ROOT / "package.json"
INSTALLED_PACKAGE_JSON_SHA256 = "68a8879b7152ebafed56852af38193006506feadf25903cd67a935229905368d"

MAX_TRIANGLES = 1_000_000
MAX_VERTICES = 3_000_000
CHILD_TIMEOUT_SECONDS = 180
# Node/V8 plus the fixed WASM memory require a large virtual reservation even
# for tiny meshes. Physical use remains constrained by the 1 GiB V8 heap and
# the locked Manifold WASM module; RLIMIT_AS still provides a hard ceiling.
CHILD_ADDRESS_SPACE_BYTES = 12 * 1024 * 1024 * 1024
CHILD_OUTPUT_BYTES = 1024 * 1024
NODE_MAX_OLD_SPACE_MIB = 1024
MAX_CHILD_ATTEMPTS = 2
STATUS_VALUES = frozenset(
    ("MANIFOLD_CORROBORATED", "MANIFOLD_DISCREPANCY", "RESOURCE_LIMIT", "ERROR")
)
PROFILE = {
    "child_address_space_bytes": CHILD_ADDRESS_SPACE_BYTES,
    "child_output_bytes": CHILD_OUTPUT_BYTES,
    "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
    "manifold_operations": ["CONSTRUCT", "STATUS", "GET_MESH"],
    "max_triangles": MAX_TRIANGLES,
    "max_vertices": MAX_VERTICES,
    "merge_vectors": "FORBIDDEN",
    "node_max_old_space_mib": NODE_MAX_OLD_SPACE_MIB,
    "repair": "FORBIDDEN",
    "simplification": "FORBIDDEN",
    "tolerance": 0,
}
ARTIFACT_NAME = "witness_evidence"
ARTIFACT_FILENAME = "witness-evidence.json"
BUNDLE_FILES = frozenset((ARTIFACT_FILENAME, "bundle-manifest.json", "READY.json"))


class P2bError(RuntimeError):
    """Raised when P2b cannot preserve its closed execution contract."""


class P2bInterrupted(P2bError):
    """Raised when the bounded child produced no usable terminal result."""


def _canonical_mesh_sha256(mesh: Mapping[str, Any]) -> str:
    """Hash the canonical mesh as a closed little-endian binary64/u32 stream.

    The frozen custody JCS domain intentionally rejects floats, so geometry is
    never committed through JSON number formatting. Negative zero has already
    been normalised by the canonical materialiser.
    """

    if (
        mesh.get("schema") != "MVX-P2B-CANONICAL-MESH"
        or mesh.get("schema_version") != "0.1.0"
    ):
        raise P2bError("canonical mesh identity is invalid")
    vertices = mesh.get("vertices")
    triangles = mesh.get("triangles")
    if not isinstance(vertices, Sequence) or not isinstance(triangles, Sequence):
        raise P2bError("canonical mesh arrays are invalid")
    payload = bytearray(b"MVX-P2B-MESH\x00\x01")
    payload.extend(struct.pack("<QQ", len(vertices), len(triangles)))
    for vertex in vertices:
        if not isinstance(vertex, Sequence) or len(vertex) != 3:
            raise P2bError("canonical vertex is invalid")
        values = tuple(float(value) for value in vertex)
        if any(
            not math.isfinite(value) or (value == 0.0 and math.copysign(1, value) < 0)
            for value in values
        ):
            raise P2bError("canonical vertex is non-finite or contains negative zero")
        payload.extend(struct.pack("<ddd", *values))
    for triangle in triangles:
        if not isinstance(triangle, Sequence) or len(triangle) != 3:
            raise P2bError("canonical triangle is invalid")
        indices = tuple(int(value) for value in triangle)
        if any(index < 0 or index >= len(vertices) or index > 0xFFFFFFFF for index in indices):
            raise P2bError("canonical triangle index is invalid")
        payload.extend(struct.pack("<III", *indices))
    return p2a._sha256_bytes(bytes(payload))


def _json_document(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _load_object(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = p2a._read_regular_bytes(path, label=label)
    return payload, p2a._load_json_bytes(payload, label=label)


def _expected_p2a_profile() -> dict[str, Any]:
    return {
        "accessor_sparse": "DECLARED_LIMIT",
        "audit_algorithm": p2a.AUDIT_ALGORITHM,
        "external_uri_resolution": "FORBIDDEN",
        "gltf_validator": f"KhronosGroup/glTF-Validator@{p2a.VALIDATOR_VERSION}",
        "max_accessor_count": p2a.MAX_ACCESSOR_COUNT,
        "max_source_bytes": p2a.MAX_SOURCE_BYTES,
        "max_triangles": p2a.MAX_TRIANGLES,
        "max_child_no_status_attempts": p2a.MAX_CHILD_NO_STATUS_ATTEMPTS,
        "mesh_vertex_merge": "EXACT_BINARY64_NORMALISE_NEGATIVE_ZERO",
        "mvx_operations": "FORBIDDEN",
        "scene_policy": "DEFAULT_ELSE_SOLE_SCENE_ELSE_DECLARED_LIMIT",
        "solid_verifier": "NOT_AVAILABLE_NEVER_EMIT_V",
        "supported_required_extensions": sorted(p2a.SUPPORTED_REQUIRED_EXTENSIONS),
        "unsupported_required_extensions": "DECLARED_LIMIT_U",
    }


def _canonical_mesh(
    source_payload: bytes, audit: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
    expected = audit.get("geometry")
    if not isinstance(expected, dict):
        raise P2bError("P2a geometry evidence is absent")

    counts: dict[str, int] = {}
    for field in (
        "input_vertex_instances",
        "exact_unique_vertices",
        "triangles_materialised",
    ):
        value = expected.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise P2bError(f"P2a geometry count {field} is invalid")
        counts[field] = value
    source_sha256 = p2a._sha256_bytes(source_payload)

    def preflight_result(status: str, diagnostic: str) -> tuple[None, str, dict[str, Any]]:
        commitment = p2a._canonical_hash(
            {
                "diagnostic": diagnostic,
                "geometry_counts": counts,
                "schema": "MVX-P2B-UNMATERIALISED-MESH-COMMITMENT",
                "schema_version": "0.1.0",
                "source_sha256": source_sha256,
            }
        )
        return (
            None,
            commitment,
            {
                "canonical_mesh_sha256": commitment,
                "diagnostic": diagnostic,
                "manifold_status": None,
                "output_mesh": None,
                "schema": "MVX-P2B-MANIFOLD-WITNESS-RESULT",
                "schema_version": "0.1.0",
                "status": status,
            },
        )

    if counts["triangles_materialised"] == 0 or counts["exact_unique_vertices"] == 0:
        return preflight_result("ERROR", "EMPTY_CANONICAL_SURFACE_FORBIDDEN")
    if (
        counts["triangles_materialised"] > MAX_TRIANGLES
        or counts["input_vertex_instances"] > MAX_VERTICES
        or counts["exact_unique_vertices"] > MAX_VERTICES
    ):
        return preflight_result("RESOURCE_LIMIT", "P2A_GEOMETRY_COUNT_LIMIT_REACHED")

    try:
        document, binary, _ = p2a._parse_glb_container(source_payload)
        p2a._preflight_source_policy(document)
        vertices, faces, _ = p2a._materialise_scene(document, binary)
        if len(faces) > MAX_TRIANGLES or len(vertices) > MAX_VERTICES:
            return preflight_result("RESOURCE_LIMIT", "PYTHON_MATERIALISATION_LIMIT_REACHED")
        topology, evidence = p2a._topology_evidence(vertices, faces)
    except (p2a.GlbInvalid, p2a.GlbDeclaredLimit) as error:
        raise P2bError("source no longer materialises under its bound P2a algorithm") from error
    if topology != "U":
        raise P2bError("P2b accepts only closed P2a topology U inputs")
    if any(
        evidence.get(field) != expected.get(field)
        for field in (
            "exact_unique_vertices",
            "triangles_materialised",
            "boundary_edge_count",
            "non_manifold_edge_count",
            "non_manifold_vertex_count",
            "orientation_conflict_edge_count",
            "degenerate_triangle_count",
            "duplicate_triangle_count",
        )
    ):
        raise P2bError("canonical materialisation differs from terminal P2a evidence")

    exact_vertices: dict[tuple[float, float, float], int] = {}
    canonical_vertices: list[tuple[float, float, float]] = []
    remap: list[int] = []
    for vertex in vertices:
        normalised = tuple(0.0 if value == 0.0 else value for value in vertex)
        if normalised not in exact_vertices:
            exact_vertices[normalised] = len(canonical_vertices)
            canonical_vertices.append(normalised)
        remap.append(exact_vertices[normalised])
    canonical_faces = [tuple(remap[index] for index in face) for face in faces]
    if len(canonical_faces) > MAX_TRIANGLES or len(canonical_vertices) > MAX_VERTICES:
        return preflight_result("RESOURCE_LIMIT", "CANONICAL_MESH_LIMIT_REACHED")
    if not canonical_faces or not canonical_vertices:
        return preflight_result("ERROR", "EMPTY_CANONICAL_SURFACE_FORBIDDEN")
    mesh = {
        "schema": "MVX-P2B-CANONICAL-MESH",
        "schema_version": "0.1.0",
        "vertices": canonical_vertices,
        "triangles": canonical_faces,
    }
    return mesh, _canonical_mesh_sha256(mesh), None


def _validate_p2a_inputs(
    source_path: Path,
    audit_plan_path: Path,
    execution_plan_path: Path,
    checkpoint_directory: Path,
    artifact_directory: Path,
) -> tuple[bytes, dict[str, Any], str, str]:
    source_payload = p2a._read_regular_bytes(
        source_path, label="P2a source GLB", maximum=p2a.MAX_SOURCE_BYTES
    )
    source_sha256 = p2a._sha256_bytes(source_payload)
    _, raw_audit_plan = _load_object(audit_plan_path, label="P2a source audit plan")
    audit_plan = p2a._validate_audit_plan(raw_audit_plan)
    if audit_plan["profile"] != _expected_p2a_profile():
        raise P2bError("P2a audit plan profile differs from the bound diagnostic profile")
    if not p2a._validate_object_bundle(artifact_directory):
        raise P2bError("P2a object artifact bundle is incomplete")
    _, source_receipt = _load_object(
        artifact_directory / p2a.OBJECT_ARTIFACT_FILES["source_receipt"],
        label="P2a source receipt",
    )
    if (
        source_receipt.get("schema") != "MVX-P2A-PRIVATE-SOURCE-RECEIPT"
        or source_receipt.get("schema_version") != "0.1.0"
    ):
        raise P2bError("P2a source receipt identity is invalid")
    source = {
        key: value
        for key, value in source_receipt.items()
        if key not in {"schema", "schema_version"}
    }
    matches = [row for row in audit_plan["sources"] if row == source]
    if len(matches) != 1:
        raise P2bError("P2a source receipt is absent or repeated in its sealed audit plan")
    if (
        source.get("source_sha256") != source_sha256
        or source.get("source_size_bytes") != len(source_payload)
    ):
        raise P2bError("source bytes differ from the P2a source receipt")

    _, execution_plan = _load_object(execution_plan_path, label="P2a execution plan")
    current_code_identity = p2a._runtime_code_identity()
    current_environment_sha256 = p2a._environment_sha256()
    expected_plan, work_id = p2a._make_object_plan(
        source,
        audit_plan["profile"],
        current_code_identity[0],
        current_environment_sha256,
    )
    if execution_plan != expected_plan:
        raise P2bError(
            "P2a execution plan differs from the exact source, candidate, code, "
            "environment, configuration, profile, protocol, or work identity"
        )
    chain = p2a._load_checkpoint_chain(checkpoint_directory, execution_plan, work_id)
    if not chain or chain[-1]["state"] != "TERMINAL":
        raise P2bError("P2a checkpoint chain lacks its exact terminal element")
    checkpoint_paths = p2a._checkpoint_paths(checkpoint_directory)
    if len(checkpoint_paths) != len(chain):
        raise P2bError("P2a checkpoint chain and persisted files differ")
    terminal = chain[-1]
    assessment = assess_resume(
        execution_plan,
        work_id,
        checkpoint=terminal,
        artifact_paths=p2a._object_artifact_paths(artifact_directory),
    )
    if assessment.action is not ResumeAction.SKIP:
        raise P2bError("P2a terminal artifacts are not exactly resumable")
    audit = p2a._validated_object_audit(
        artifact_directory, source, work_id, terminal=terminal
    )
    if (
        audit["source_sha256"] != source_sha256
        or audit["source_size_bytes"] != len(source_payload)
        or audit["terminal_status"] != "DECLARED_LIMIT"
        or audit["error_code"] != "MVX-G003"
        or audit["topology_status"] != "U"
        or audit["geometry"] is None
    ):
        raise P2bError("P2b requires a fully materialised terminal P2a U audit")
    terminal_payload = p2a._read_regular_bytes(
        checkpoint_paths[-1], label="exact terminal P2a checkpoint"
    )
    return (
        source_payload,
        audit,
        checkpoint_sha256(terminal),
        p2a._sha256_bytes(terminal_payload),
    )


def _node_description(node: Path) -> dict[str, str]:
    try:
        completed = subprocess.run(
            (
                str(node),
                "-p",
                "JSON.stringify({version:process.version,arch:process.arch,platform:process.platform})",
            ),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        value = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise P2bError("cannot identify the locked Node runtime") from error
    if not isinstance(value, dict) or set(value) != {"arch", "platform", "version"}:
        raise P2bError("Node runtime identity is invalid")
    return {key: str(value[key]) for key in sorted(value)}


def _runtime_identity() -> dict[str, Any]:
    node_name = shutil.which("node")
    if not node_name:
        raise P2bError("Node.js is unavailable")
    node = Path(node_name).resolve()
    required = (
        Path(__file__).resolve(),
        PACKAGE_JSON,
        PACKAGE_LOCK,
        WRAPPER,
        MANIFOLD_JS,
        MANIFOLD_WASM,
        INSTALLED_PACKAGE_JSON,
    )
    if any(not path.is_file() or path.is_symlink() for path in required):
        raise P2bError("locked P2b runtime is incomplete; run npm ci in scripts/p2b-runtime")
    installed_package_sha256 = hash_artifact(INSTALLED_PACKAGE_JSON)
    if installed_package_sha256 != INSTALLED_PACKAGE_JSON_SHA256:
        raise P2bError("installed Manifold package metadata differs from the locked package")
    _, installed = _load_object(INSTALLED_PACKAGE_JSON, label="installed manifold package")
    if installed.get("name") != "manifold-3d" or installed.get("version") != "3.5.1":
        raise P2bError("installed Manifold package differs from the lock")
    manifold_js_sha256 = hash_artifact(MANIFOLD_JS)
    manifold_wasm_sha256 = hash_artifact(MANIFOLD_WASM)
    installed_closure_sha256 = p2a._canonical_hash(
        {
            "installed_package_json_sha256": installed_package_sha256,
            "manifold_js_sha256": manifold_js_sha256,
            "manifold_wasm_sha256": manifold_wasm_sha256,
        }
    )
    return {
        "algorithm": "MVX-P2B-MANIFOLD-RUNTIME-IDENTITY-1",
        "architecture": platform.machine(),
        "installed_manifold_closure_sha256": installed_closure_sha256,
        "installed_package_json_sha256": installed_package_sha256,
        "manifold_js_sha256": manifold_js_sha256,
        "manifold_wasm_sha256": manifold_wasm_sha256,
        "node": _node_description(node),
        "node_executable_sha256": hash_artifact(node),
        "package_json_sha256": hash_artifact(PACKAGE_JSON),
        "package_lock_sha256": hash_artifact(PACKAGE_LOCK),
        "profile": PROFILE,
        "runner_sha256": hash_artifact(Path(__file__).resolve()),
        "runtime_version": RUNTIME_VERSION,
        "wrapper_js_sha256": hash_artifact(WRAPPER),
    }


def _make_plan(
    *,
    source_sha256: str,
    canonical_mesh_sha256: str,
    p2a_terminal_checkpoint_sha256: str,
    p2a_terminal_file_sha256: str,
    runtime_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    code_sha256 = p2a._canonical_hash(
        {
            "algorithm": "MVX-P2B-CODE-CLOSURE-1",
            "runner_sha256": runtime_identity["runner_sha256"],
            "wrapper_js_sha256": runtime_identity["wrapper_js_sha256"],
        }
    )
    environment_sha256 = p2a._canonical_hash(runtime_identity)
    identity = WorkIdentity(
        protocol_root_sha256=p2a.P0_ROOT,
        split_sha256=p2a._canonical_hash(p2a.NO_SPLIT_DOMAIN),
        source_sha256=source_sha256,
        lineage_id=f"source-sha256:{source_sha256}",
        profile_sha256=p2a._canonical_hash(PROFILE),
        config_sha256=p2a._canonical_hash(
            {
                "algorithm_id": ALGORITHM_ID,
                "algorithm_version": ALGORITHM_VERSION,
                "canonical_mesh_sha256": canonical_mesh_sha256,
                "p2a_terminal_checkpoint_sha256": p2a_terminal_checkpoint_sha256,
                "p2a_terminal_file_sha256": p2a_terminal_file_sha256,
                "script_version": SCRIPT_VERSION,
            }
        ),
        code_sha256=code_sha256,
        environment_sha256=environment_sha256,
        phase_id="P2b",
        stage_id="MANIFOLD_AUXILIARY_WITNESS",
        split="none",
        open_once=False,
    )
    stage = make_stage(identity, required_artifacts=(ARTIFACT_NAME,))
    return make_execution_plan(f"MVX-P2B-{identity.work_id[:16]}", (stage,)), identity.work_id


def _child_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (CHILD_TIMEOUT_SECONDS, CHILD_TIMEOUT_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (CHILD_ADDRESS_SPACE_BYTES, CHILD_ADDRESS_SPACE_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_FSIZE, (CHILD_OUTPUT_BYTES, CHILD_OUTPUT_BYTES))


def _validate_child_result(value: Mapping[str, Any], canonical_mesh_sha256: str) -> dict[str, Any]:
    result = dict(value)
    if set(result) != {
        "canonical_mesh_sha256",
        "diagnostic",
        "manifold_status",
        "output_mesh",
        "schema",
        "schema_version",
        "status",
    }:
        raise P2bInterrupted("Manifold child result fields differ from the closed contract")
    if (
        result["schema"] != "MVX-P2B-MANIFOLD-WITNESS-RESULT"
        or result["schema_version"] != "0.1.0"
        or result["canonical_mesh_sha256"] != canonical_mesh_sha256
        or result["status"] not in STATUS_VALUES
        or not isinstance(result["diagnostic"], str)
        or not result["diagnostic"]
    ):
        raise P2bInterrupted("Manifold child result identity or status is invalid")
    if result["status"] in {"RESOURCE_LIMIT", "ERROR"}:
        if result["manifold_status"] is not None or result["output_mesh"] is not None:
            raise P2bInterrupted("resource-limit result contains unexpected mesh evidence")
        return result
    mesh = result["output_mesh"]
    if not isinstance(mesh, dict) or set(mesh) != {
        "input_topology_sha256",
        "input_triangle_count",
        "input_vertex_count",
        "output_topology_sha256",
        "output_triangle_count",
        "output_vertex_count",
    }:
        raise P2bInterrupted("Manifold child mesh evidence is invalid")
    for field in ("input_triangle_count", "input_vertex_count"):
        if isinstance(mesh[field], bool) or not isinstance(mesh[field], int) or mesh[field] < 0:
            raise P2bInterrupted("Manifold input count is invalid")
    for field in ("output_triangle_count", "output_vertex_count"):
        value = mesh[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise P2bInterrupted("Manifold output count is invalid")
    for field in ("input_topology_sha256", "output_topology_sha256"):
        value = mesh[field]
        if value is not None and not p2a.SHA256_PATTERN.fullmatch(str(value)):
            raise P2bInterrupted("Manifold topology commitment is invalid")
    if result["manifold_status"] is not None and not isinstance(result["manifold_status"], str):
        raise P2bInterrupted("Manifold status must be a string or null")
    input_hash = mesh["input_topology_sha256"]
    if not isinstance(input_hash, str) or not p2a.SHA256_PATTERN.fullmatch(input_hash):
        raise P2bInterrupted("Manifold input topology commitment is required")
    unchanged = (
        mesh["output_topology_sha256"] == input_hash
        and mesh["output_triangle_count"] == mesh["input_triangle_count"]
        and mesh["output_vertex_count"] == mesh["input_vertex_count"]
    )
    if result["status"] == "MANIFOLD_CORROBORATED" and (
        result["manifold_status"] != "NoError" or not unchanged
    ):
        raise P2bInterrupted("Manifold corroboration lacks exact unchanged NoError evidence")
    if result["status"] == "MANIFOLD_DISCREPANCY" and (
        result["manifold_status"] in {None, "NoError"} and unchanged
    ):
        raise P2bInterrupted("Manifold discrepancy lacks a rejection or observable change")
    return result


def _run_child(mesh: Mapping[str, Any], canonical_mesh_sha256: str) -> dict[str, Any]:
    node_name = shutil.which("node")
    if not node_name:
        raise P2bInterrupted("Node.js disappeared after runtime sealing")
    child_input = {
        "canonical_mesh_sha256": canonical_mesh_sha256,
        "profile": PROFILE,
        "schema": "MVX-P2B-MANIFOLD-WITNESS-INPUT",
        "schema_version": "0.1.0",
        "triangles": mesh["triangles"],
        "vertices": mesh["vertices"],
    }
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TZ": "UTC",
    }
    io_root = p2a._private_path(
        str(REPOSITORY_ROOT / "tmp/p2b-child-io"), create_directory=True
    )
    with tempfile.TemporaryDirectory(prefix="attempt-", dir=io_root) as temporary:
        temporary_root = Path(temporary)
        stdout_path = temporary_root / "stdout.bin"
        stderr_path = temporary_root / "stderr.bin"
        with stdout_path.open("xb", buffering=0) as stdout_stream, stderr_path.open(
            "xb", buffering=0
        ) as stderr_stream:
            os.chmod(stdout_path, 0o600, follow_symlinks=False)
            os.chmod(stderr_path, 0o600, follow_symlinks=False)
            try:
                completed = subprocess.run(
                    (
                        node_name,
                        f"--max-old-space-size={NODE_MAX_OLD_SPACE_MIB}",
                        str(WRAPPER),
                    ),
                    input=_json_document(child_input),
                    cwd=RUNTIME_ROOT,
                    env=environment,
                    check=False,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    preexec_fn=_child_limits,
                    timeout=CHILD_TIMEOUT_SECONDS + 5,
                )
            except subprocess.TimeoutExpired:
                return {
                    "canonical_mesh_sha256": canonical_mesh_sha256,
                    "diagnostic": "BOUNDED_CHILD_TIMEOUT",
                    "manifold_status": None,
                    "output_mesh": None,
                    "schema": "MVX-P2B-MANIFOLD-WITNESS-RESULT",
                    "schema_version": "0.1.0",
                    "status": "RESOURCE_LIMIT",
                }
        stdout_metadata = stdout_path.lstat()
        stderr_metadata = stderr_path.lstat()
        if (
            not stat.S_ISREG(stdout_metadata.st_mode)
            or not stat.S_ISREG(stderr_metadata.st_mode)
            or stdout_path.is_symlink()
            or stderr_path.is_symlink()
        ):
            raise P2bInterrupted("bounded child output is not a pair of regular files")
        if (
            stdout_metadata.st_size >= CHILD_OUTPUT_BYTES
            or stderr_metadata.st_size >= CHILD_OUTPUT_BYTES
        ):
            return {
                "canonical_mesh_sha256": canonical_mesh_sha256,
                "diagnostic": "BOUNDED_CHILD_OUTPUT_LIMIT",
                "manifold_status": None,
                "output_mesh": None,
                "schema": "MVX-P2B-MANIFOLD-WITNESS-RESULT",
                "schema_version": "0.1.0",
                "status": "RESOURCE_LIMIT",
            }
        stdout = p2a._read_regular_bytes(
            stdout_path, label="bounded child stdout", maximum=CHILD_OUTPUT_BYTES
        )
        stderr = p2a._read_regular_bytes(
            stderr_path, label="bounded child stderr", maximum=CHILD_OUTPUT_BYTES
        )
    if completed.returncode != 0:
        raise P2bInterrupted(
            "Manifold child exited without a result "
            f"(returncode={completed.returncode}, stderr_sha256={p2a._sha256_bytes(stderr)})"
        )
    try:
        value = json.loads(stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise P2bInterrupted("Manifold child emitted invalid JSON") from error
    if not isinstance(value, dict):
        raise P2bInterrupted("Manifold child result must be an object")
    return _validate_child_result(value, canonical_mesh_sha256)


def _evidence(
    result: Mapping[str, Any],
    *,
    source_sha256: str,
    canonical_mesh_sha256: str,
    p2a_terminal_checkpoint_sha256: str,
    p2a_terminal_file_sha256: str,
    runtime_identity: Mapping[str, Any],
    work_id: str,
) -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "canonical_mesh_sha256": canonical_mesh_sha256,
        "diagnostic": result["diagnostic"],
        "manifold_status": result["manifold_status"],
        "output_mesh": result["output_mesh"],
        "p2a_primary_topology_status": "U",
        "p2a_terminal_checkpoint_sha256": p2a_terminal_checkpoint_sha256,
        "p2a_terminal_file_sha256": p2a_terminal_file_sha256,
        "primary_status_changed": False,
        "runtime_identity_sha256": p2a._canonical_hash(runtime_identity),
        "schema": "MVX-P2B-MANIFOLD-WITNESS-EVIDENCE",
        "schema_version": "0.1.0",
        "source_sha256": source_sha256,
        "status": result["status"],
        "work_id": work_id,
    }


def _validate_evidence(
    value: Mapping[str, Any], *, work_id: str, expected: Mapping[str, str]
) -> dict[str, Any]:
    evidence = dict(value)
    if set(evidence) != {
        "algorithm_id",
        "algorithm_version",
        "canonical_mesh_sha256",
        "diagnostic",
        "manifold_status",
        "output_mesh",
        "p2a_primary_topology_status",
        "p2a_terminal_checkpoint_sha256",
        "p2a_terminal_file_sha256",
        "primary_status_changed",
        "runtime_identity_sha256",
        "schema",
        "schema_version",
        "source_sha256",
        "status",
        "work_id",
    }:
        raise P2bError("P2b witness evidence fields differ from the contract")
    if (
        evidence["schema"] != "MVX-P2B-MANIFOLD-WITNESS-EVIDENCE"
        or evidence["schema_version"] != "0.1.0"
        or evidence["algorithm_id"] != ALGORITHM_ID
        or evidence["algorithm_version"] != ALGORITHM_VERSION
        or evidence["work_id"] != work_id
        or evidence["status"] not in STATUS_VALUES
        or evidence["p2a_primary_topology_status"] != "U"
        or evidence["primary_status_changed"] is not False
        or any(evidence[key] != value for key, value in expected.items())
    ):
        raise P2bError("P2b witness evidence identity is invalid")
    try:
        _validate_child_result(
            {
                "canonical_mesh_sha256": evidence["canonical_mesh_sha256"],
                "diagnostic": evidence["diagnostic"],
                "manifold_status": evidence["manifold_status"],
                "output_mesh": evidence["output_mesh"],
                "schema": "MVX-P2B-MANIFOLD-WITNESS-RESULT",
                "schema_version": "0.1.0",
                "status": evidence["status"],
            },
            evidence["canonical_mesh_sha256"],
        )
    except P2bInterrupted as error:
        raise P2bError("P2b witness evidence has invalid status semantics") from error
    return evidence


def _validate_bundle(directory: Path, *, work_id: str, expected: Mapping[str, str]) -> bool:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or directory.is_symlink():
        raise P2bError("P2b artifact bundle is not a real directory")
    entries = {entry.name: entry for entry in directory.iterdir()}
    if set(entries) != BUNDLE_FILES:
        raise P2bError("P2b artifact bundle is partial or contains extras")
    for entry in entries.values():
        item = entry.lstat()
        if not stat.S_ISREG(item.st_mode) or entry.is_symlink():
            raise P2bError("P2b artifact bundle contains a non-regular entry")
    evidence_payload = p2a._read_regular_bytes(entries[ARTIFACT_FILENAME], label="P2b evidence")
    _validate_evidence(
        p2a._load_json_bytes(evidence_payload, label="P2b evidence"),
        work_id=work_id,
        expected=expected,
    )
    manifest_payload, manifest = _load_object(
        entries["bundle-manifest.json"], label="P2b bundle manifest"
    )
    if manifest != {
        "files": {
            ARTIFACT_FILENAME: {
                "bytes": len(evidence_payload),
                "sha256": p2a._sha256_bytes(evidence_payload),
            }
        },
        "schema": "MVX-P2B-WITNESS-BUNDLE",
        "schema_version": "0.1.0",
    }:
        raise P2bError("P2b bundle manifest does not bind its evidence")
    _, ready = _load_object(entries["READY.json"], label="P2b READY marker")
    if ready != {
        "bundle_manifest_sha256": p2a._sha256_bytes(manifest_payload),
        "schema": "MVX-P2B-WITNESS-BUNDLE-READY",
        "schema_version": "0.1.0",
    }:
        raise P2bError("P2b READY marker does not bind its bundle")
    return True


def _publish_bundle(
    run_directory: Path,
    artifact_directory: Path,
    evidence: Mapping[str, Any],
    *,
    attempt: int,
    work_id: str,
    expected: Mapping[str, str],
) -> None:
    payload = _json_document(evidence)
    if _validate_bundle(artifact_directory, work_id=work_id, expected=expected):
        existing = p2a._read_regular_bytes(
            artifact_directory / ARTIFACT_FILENAME, label="existing P2b evidence"
        )
        if existing != payload:
            raise P2bError("existing P2b evidence conflicts with recomputation")
        return
    staging = run_directory / f"attempt-{attempt:04d}-artifacts.staging"
    try:
        os.mkdir(staging, 0o700)
        p2a._fsync_directory(run_directory)
    except FileExistsError as error:
        raise P2bError("P2b staging already exists and requires recovery") from error
    p2a._publish_bytes_once(staging / ARTIFACT_FILENAME, payload)
    manifest_payload = _json_document(
        {
            "files": {
                ARTIFACT_FILENAME: {"bytes": len(payload), "sha256": p2a._sha256_bytes(payload)}
            },
            "schema": "MVX-P2B-WITNESS-BUNDLE",
            "schema_version": "0.1.0",
        }
    )
    p2a._publish_bytes_once(staging / "bundle-manifest.json", manifest_payload)
    p2a._publish_bytes_once(
        staging / "READY.json",
        _json_document(
            {
                "bundle_manifest_sha256": p2a._sha256_bytes(manifest_payload),
                "schema": "MVX-P2B-WITNESS-BUNDLE-READY",
                "schema_version": "0.1.0",
            }
        ),
    )
    _validate_bundle(staging, work_id=work_id, expected=expected)
    os.rename(staging, artifact_directory)
    p2a._fsync_directory(run_directory)


def _recover_staging(
    run_directory: Path,
    artifact_directory: Path,
    *,
    work_id: str,
    expected: Mapping[str, str],
) -> None:
    staging = sorted(
        (entry for entry in run_directory.iterdir() if entry.name.endswith("-artifacts.staging")),
        key=lambda item: item.name,
    )
    if artifact_directory.exists() and staging:
        raise P2bError("complete P2b artifacts and staging coexist")
    ready: list[Path] = []
    partial: list[Path] = []
    for path in staging:
        try:
            complete = _validate_bundle(path, work_id=work_id, expected=expected)
        except P2bError:
            complete = False
        (ready if complete else partial).append(path)
    if len(ready) > 1:
        raise P2bError("multiple complete P2b staging bundles conflict")
    quarantine = run_directory / "quarantine"
    p2a._ensure_private_directory(quarantine)
    for index, path in enumerate(partial):
        target = quarantine / f"{path.name}.partial-{index:04d}"
        if target.exists() or target.is_symlink():
            raise P2bError("P2b quarantine target already exists")
        os.rename(path, target)
    if ready:
        os.rename(ready[0], artifact_directory)
    if staging:
        p2a._fsync_directory(run_directory)


def _terminal_from_bundle(
    plan: Mapping[str, Any],
    work_id: str,
    checkpoint_directory: Path,
    running: Mapping[str, Any],
    next_sequence: int,
    artifact_directory: Path,
    *,
    expected: Mapping[str, str],
) -> dict[str, Any]:
    _, evidence = _load_object(
        artifact_directory / ARTIFACT_FILENAME, label="terminal P2b evidence"
    )
    evidence = _validate_evidence(evidence, work_id=work_id, expected=expected)
    mapping = {
        "MANIFOLD_CORROBORATED": ("PASS", "P2B-MANIFOLD-CORROBORATED"),
        "MANIFOLD_DISCREPANCY": ("PASS", "P2B-MANIFOLD-DISCREPANCY"),
        "RESOURCE_LIMIT": ("DECLARED_LIMIT", "P2B-RESOURCE-LIMIT"),
        "ERROR": ("FAIL", "P2B-ERROR"),
    }
    terminal_status, error_code = mapping[evidence["status"]]
    terminal = make_stage_checkpoint(
        plan,
        work_id,
        state="TERMINAL",
        attempt=int(running["attempt"]),
        terminal_status=terminal_status,
        error_code=error_code,
        artifact_hashes={ARTIFACT_NAME: hash_artifact(artifact_directory / ARTIFACT_FILENAME)},
        previous_checkpoint=running,
    )
    p2a._write_numbered_checkpoint(checkpoint_directory, next_sequence, terminal)
    return terminal


def _execute_prevalidated(
    *,
    source_payload: bytes,
    audit: Mapping[str, Any],
    p2a_terminal_checkpoint_sha256: str,
    p2a_terminal_file_sha256: str,
    output_root: Path,
    runtime_identity: Mapping[str, Any],
    child_runner: Callable[[Mapping[str, Any], str], dict[str, Any]] = _run_child,
) -> dict[str, Any]:
    source_sha256 = p2a._sha256_bytes(source_payload)
    mesh, canonical_mesh_sha256, preflight_result = _canonical_mesh(source_payload, audit)
    plan, work_id = _make_plan(
        source_sha256=source_sha256,
        canonical_mesh_sha256=canonical_mesh_sha256,
        p2a_terminal_checkpoint_sha256=p2a_terminal_checkpoint_sha256,
        p2a_terminal_file_sha256=p2a_terminal_file_sha256,
        runtime_identity=runtime_identity,
    )
    root = p2a._private_path(str(output_root), create_directory=True)
    object_root = p2a._private_path(str(root / "objects"), create_directory=True)
    lock_root = p2a._private_path(str(root / "locks"), create_directory=True)
    run_directory = p2a._private_path(
        str(object_root / work_id), create_directory=True
    )
    expected = {
        "canonical_mesh_sha256": canonical_mesh_sha256,
        "p2a_terminal_checkpoint_sha256": p2a_terminal_checkpoint_sha256,
        "p2a_terminal_file_sha256": p2a_terminal_file_sha256,
        "runtime_identity_sha256": p2a._canonical_hash(runtime_identity),
        "source_sha256": source_sha256,
    }
    with p2a._exclusive_lock(lock_root, work_id):
        allowed = {
            "execution-plan.json",
            "checkpoints",
            "artifacts",
            "quarantine",
        }
        if any(
            entry.name not in allowed and not entry.name.endswith("-artifacts.staging")
            for entry in run_directory.iterdir()
        ):
            raise P2bError("P2b run directory contains an unknown entry")
        plan_path = run_directory / "execution-plan.json"
        p2a._publish_bytes_once(plan_path, _json_document(plan))
        checkpoint_directory = p2a._private_path(
            str(run_directory / "checkpoints"), create_directory=True
        )
        artifact_directory = run_directory / "artifacts"
        _recover_staging(
            run_directory,
            artifact_directory,
            work_id=work_id,
            expected=expected,
        )
        chain = p2a._load_checkpoint_chain(checkpoint_directory, plan, work_id)
        artifact_paths = {ARTIFACT_NAME: artifact_directory / ARTIFACT_FILENAME}
        if chain and chain[-1]["state"] == "TERMINAL":
            assessment = assess_resume(
                plan,
                work_id,
                checkpoint=chain[-1],
                artifact_paths=artifact_paths,
            )
            if assessment.action is not ResumeAction.SKIP:
                raise P2bError("terminal P2b work is not safely resumable")
            _, evidence = _load_object(
                artifact_directory / ARTIFACT_FILENAME, label="existing P2b evidence"
            )
            evidence = _validate_evidence(evidence, work_id=work_id, expected=expected)
            return {
                "action": "SKIP",
                "status": evidence["status"],
                "terminal_checkpoint_sha256": checkpoint_sha256(chain[-1]),
                "work_id": work_id,
            }

        artifacts_ready = _validate_bundle(
            artifact_directory, work_id=work_id, expected=expected
        )
        running, next_sequence = p2a._ensure_running(
            plan,
            work_id,
            checkpoint_directory,
            chain,
            artifacts_ready=artifacts_ready,
        )
        if artifacts_ready:
            terminal = _terminal_from_bundle(
                plan,
                work_id,
                checkpoint_directory,
                running,
                next_sequence,
                artifact_directory,
                expected=expected,
            )
            _, evidence = _load_object(
                artifact_directory / ARTIFACT_FILENAME, label="recovered P2b evidence"
            )
            return {
                "action": "RECOVERED",
                "status": evidence["status"],
                "terminal_checkpoint_sha256": checkpoint_sha256(terminal),
                "work_id": work_id,
            }

        attempt = int(running["attempt"])
        if preflight_result is not None:
            result = _validate_child_result(preflight_result, canonical_mesh_sha256)
        elif attempt > MAX_CHILD_ATTEMPTS:
            result = {
                "canonical_mesh_sha256": canonical_mesh_sha256,
                "diagnostic": "RESTART_AFTER_CHILD_RETRY_BUDGET_EXHAUSTED",
                "manifold_status": None,
                "output_mesh": None,
                "schema": "MVX-P2B-MANIFOLD-WITNESS-RESULT",
                "schema_version": "0.1.0",
                "status": "ERROR",
            }
        else:
            try:
                if mesh is None:
                    raise P2bError("materialised mesh is absent without a preflight result")
                result = child_runner(mesh, canonical_mesh_sha256)
                result = _validate_child_result(result, canonical_mesh_sha256)
            except P2bInterrupted:
                if attempt < MAX_CHILD_ATTEMPTS:
                    interrupted = make_stage_checkpoint(
                        plan,
                        work_id,
                        state="INTERRUPTED",
                        attempt=attempt,
                        error_code="P2B-CHILD-NO-STATUS",
                        interruption_reason="CHILD_NO_STATUS",
                        previous_checkpoint=running,
                    )
                    p2a._write_numbered_checkpoint(
                        checkpoint_directory, next_sequence, interrupted
                    )
                    raise
                result = {
                    "canonical_mesh_sha256": canonical_mesh_sha256,
                    "diagnostic": "BOUNDED_CHILD_NO_STATUS_RETRY_EXHAUSTED",
                    "manifold_status": None,
                    "output_mesh": None,
                    "schema": "MVX-P2B-MANIFOLD-WITNESS-RESULT",
                    "schema_version": "0.1.0",
                    "status": "ERROR",
                }
        evidence = _evidence(
            result,
            source_sha256=source_sha256,
            canonical_mesh_sha256=canonical_mesh_sha256,
            p2a_terminal_checkpoint_sha256=p2a_terminal_checkpoint_sha256,
            p2a_terminal_file_sha256=p2a_terminal_file_sha256,
            runtime_identity=runtime_identity,
            work_id=work_id,
        )
        _publish_bundle(
            run_directory,
            artifact_directory,
            evidence,
            attempt=int(running["attempt"]),
            work_id=work_id,
            expected=expected,
        )
        if _runtime_identity() != runtime_identity:
            raise P2bError("P2b runtime changed before terminal publication")
        terminal = _terminal_from_bundle(
            plan,
            work_id,
            checkpoint_directory,
            running,
            next_sequence,
            artifact_directory,
            expected=expected,
        )
        assessment = assess_resume(
            plan, work_id, checkpoint=terminal, artifact_paths=artifact_paths
        )
        if assessment.action is not ResumeAction.SKIP:
            raise P2bError("new P2b terminal checkpoint does not verify")
        return {
            "action": "COMPLETED",
            "status": evidence["status"],
            "terminal_checkpoint_sha256": checkpoint_sha256(terminal),
            "work_id": work_id,
        }


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    p2a._verified_protocol_root()
    source_payload, audit, terminal_hash, terminal_file_hash = _validate_p2a_inputs(
        Path(arguments.source).resolve(),
        Path(arguments.p2a_audit_plan).resolve(),
        Path(arguments.p2a_execution_plan).resolve(),
        Path(arguments.p2a_checkpoint_directory).resolve(),
        Path(arguments.p2a_artifact_directory).resolve(),
    )
    runtime_identity = _runtime_identity()
    return _execute_prevalidated(
        source_payload=source_payload,
        audit=audit,
        p2a_terminal_checkpoint_sha256=terminal_hash,
        p2a_terminal_file_sha256=terminal_file_hash,
        output_root=Path(arguments.output_root),
        runtime_identity=runtime_identity,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    witness = subparsers.add_parser("run", help="run or safely resume one P2b witness")
    witness.add_argument("--source", required=True)
    witness.add_argument("--p2a-audit-plan", required=True)
    witness.add_argument("--p2a-execution-plan", required=True)
    witness.add_argument("--p2a-checkpoint-directory", required=True)
    witness.add_argument("--p2a-artifact-directory", required=True)
    witness.add_argument("--output-root", default="tmp/p2b")
    witness.set_defaults(handler=run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        result = arguments.handler(arguments)
    except (P2bError, p2a.P2aError, ValueError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
