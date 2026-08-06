from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "mvx_p2b_manifold_witness.py"
SPEC = importlib.util.spec_from_file_location("mvx_p2b_manifold_witness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
p2b = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p2b
SPEC.loader.exec_module(p2b)


def _mesh(
    vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]]
) -> dict[str, object]:
    return {
        "schema": "MVX-P2B-CANONICAL-MESH",
        "schema_version": "0.1.0",
        "vertices": vertices,
        "triangles": triangles,
    }


def _run_fixture(
    vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]]
) -> dict[str, object]:
    mesh = _mesh(vertices, triangles)
    return p2b._run_child(mesh, p2b._canonical_mesh_sha256(mesh))


def _tetrahedron() -> tuple[
    list[tuple[float, float, float]], list[tuple[int, int, int]]
]:
    return (
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
        [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)],
    )


def _tetra_glb_and_audit() -> tuple[bytes, dict[str, object]]:
    vertices, triangles = _tetrahedron()
    payload = p2b.p2a._build_test_glb(vertices, [index for face in triangles for index in face])
    document, binary, _ = p2b.p2a._parse_glb_container(payload)
    materialised_vertices, materialised_faces, _ = p2b.p2a._materialise_scene(document, binary)
    topology, geometry = p2b.p2a._topology_evidence(
        materialised_vertices, materialised_faces
    )
    assert topology == "U"
    return payload, {"geometry": geometry}


def _strict_p2a_fixture(root: Path) -> dict[str, Path | dict[str, object] | bytes]:
    vertices, triangles = _tetrahedron()
    payload = p2b.p2a._build_test_glb(vertices, [index for face in triangles for index in face])
    source_sha256 = p2b.p2a._sha256_bytes(payload)
    candidate = {
        "drive_file_id": "synthetic-private-drive-id",
        "source_uid": "a" * 32,
        "source_title": f"synthetic_{'a' * 32}.glb",
        "source_size_bytes": len(payload),
        "source_sha256": source_sha256,
    }
    source = {
        "ordinal": 0,
        **candidate,
        "candidate_commitment_sha256": p2b.p2a._canonical_hash(candidate),
        "cache_locator": f"sha256/{source_sha256[:2]}/{source_sha256}.glb",
    }
    profile = p2b._expected_p2a_profile()
    audit_plan = p2b.p2a._validate_audit_plan(
        {
            "schema": "MVX-P2A-SOURCE-AUDIT-PLAN",
            "schema_version": "0.1.0",
            "algorithm_id": p2b.p2a.AUDIT_ALGORITHM,
            "algorithm_version": p2b.p2a.AUDIT_ALGORITHM_VERSION,
            "protocol_root_sha256": p2b.p2a.P0_ROOT,
            "pilot_plan_sha256": "b" * 64,
            "source_count": 1,
            "sources": [source],
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
    code_identity = p2b.p2a._runtime_code_identity()
    environment_sha256 = p2b.p2a._environment_sha256()
    execution_plan, work_id = p2b.p2a._make_object_plan(
        source, profile, code_identity[0], environment_sha256
    )
    audit = p2b.p2a.audit_glb_bytes(payload)
    assert audit["topology_status"] == "U"
    run_directory = root / "p2a-object"
    p2b.p2a._ensure_private_directory(run_directory)
    artifact_directory = run_directory / "artifacts"
    payloads = p2b.p2a._artifact_payloads(
        source,
        audit,
        {"child_exit": "ZERO", "stderr_sha256": p2b.p2a._sha256_bytes(b"")},
        work_id=work_id,
        code_commit=code_identity[1],
        code_tree=code_identity[2],
    )
    p2b.p2a._publish_object_bundle(run_directory, artifact_directory, payloads, 1)
    execution_plan_path = run_directory / "execution-plan.json"
    p2b.p2a._publish_bytes_once(
        execution_plan_path, p2b.p2a._json_document(execution_plan)
    )
    checkpoint_directory = run_directory / "checkpoints"
    p2b.p2a._ensure_private_directory(checkpoint_directory)
    pending = p2b.make_stage_checkpoint(execution_plan, work_id, state="PENDING")
    running = p2b.make_stage_checkpoint(
        execution_plan, work_id, state="RUNNING", previous_checkpoint=pending
    )
    artifact_hashes = {
        name: p2b.hash_artifact(path)
        for name, path in p2b.p2a._object_artifact_paths(artifact_directory).items()
    }
    terminal = p2b.make_stage_checkpoint(
        execution_plan,
        work_id,
        state="TERMINAL",
        terminal_status="DECLARED_LIMIT",
        error_code="MVX-G003",
        artifact_hashes=artifact_hashes,
        previous_checkpoint=running,
    )
    for sequence, checkpoint in enumerate((pending, running, terminal), 1):
        p2b.p2a._write_numbered_checkpoint(
            checkpoint_directory, sequence, checkpoint
        )
    audit_plan_path = root / "p2a-audit-plan.json"
    source_path = root / "source.glb"
    p2b.p2a._publish_bytes_once(audit_plan_path, p2b.p2a._json_document(audit_plan))
    p2b.p2a._publish_bytes_once(source_path, payload)
    return {
        "artifact_directory": artifact_directory,
        "audit_plan_path": audit_plan_path,
        "audit": audit,
        "checkpoint_directory": checkpoint_directory,
        "execution_plan_path": execution_plan_path,
        "payload": payload,
        "source_path": source_path,
    }


def _synthetic_child_result(canonical_mesh_sha256: str) -> dict[str, object]:
    return {
        "canonical_mesh_sha256": canonical_mesh_sha256,
        "diagnostic": "SYNTHETIC_CORROBORATION_FOR_CHECKPOINT_TEST",
        "manifold_status": "NoError",
        "output_mesh": {
            "input_topology_sha256": "1" * 64,
            "input_triangle_count": 4,
            "input_vertex_count": 4,
            "output_topology_sha256": "1" * 64,
            "output_triangle_count": 4,
            "output_vertex_count": 4,
        },
        "schema": "MVX-P2B-MANIFOLD-WITNESS-RESULT",
        "schema_version": "0.1.0",
        "status": "MANIFOLD_CORROBORATED",
    }


class ManifoldAdversarialFixtureTests(unittest.TestCase):
    def test_tetrahedron_is_auxiliarily_corroborated(self) -> None:
        result = _run_fixture(*_tetrahedron())

        self.assertEqual(result["status"], "MANIFOLD_CORROBORATED")
        self.assertEqual(result["manifold_status"], "NoError")
        self.assertEqual(result["output_mesh"]["input_vertex_count"], 4)
        self.assertEqual(result["output_mesh"]["output_vertex_count"], 4)

    def test_open_triangle_is_a_discrepancy(self) -> None:
        result = _run_fixture(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [(0, 1, 2)],
        )

        self.assertEqual(result["status"], "MANIFOLD_DISCREPANCY")
        self.assertEqual(result["manifold_status"], "NotManifold")

    def test_touching_tetrahedra_expose_silent_vertex_split(self) -> None:
        result = _run_fixture(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                (-1.0, 0.0, 0.0),
                (0.0, -1.0, 0.0),
                (0.0, 0.0, -1.0),
            ],
            [
                (0, 2, 1),
                (0, 1, 3),
                (1, 2, 3),
                (2, 0, 3),
                (0, 4, 5),
                (0, 6, 4),
                (4, 6, 5),
                (5, 6, 0),
            ],
        )

        self.assertEqual(result["status"], "MANIFOLD_DISCREPANCY")
        self.assertEqual(result["manifold_status"], "NoError")
        self.assertEqual(result["output_mesh"]["input_vertex_count"], 7)
        self.assertEqual(result["output_mesh"]["output_vertex_count"], 8)

    def test_self_intersecting_bow_tie_proves_corroboration_is_not_solid_proof(self) -> None:
        vertices = [
            (1.0, 0.0, 0.0),
            (-1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, -1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, -1.0),
        ]
        triangles = [
            (4, 0, 2),
            (4, 2, 1),
            (4, 1, 3),
            (4, 3, 0),
            (5, 2, 0),
            (5, 1, 2),
            (5, 3, 1),
            (5, 0, 3),
        ]
        topology, _ = p2b.p2a._topology_evidence(vertices, triangles)

        result = _run_fixture(vertices, triangles)

        self.assertEqual(topology, "U")
        self.assertEqual(result["status"], "MANIFOLD_CORROBORATED")
        self.assertEqual(result["manifold_status"], "NoError")

    def test_two_intersecting_closed_shells_are_still_only_corroborated(self) -> None:
        first, tetra_faces = _tetrahedron()
        second = [(x + 0.25, y + 0.25, z + 0.25) for x, y, z in first]
        triangles = tetra_faces + [
            tuple(index + 4 for index in face) for face in tetra_faces
        ]
        vertices = first + second
        topology, _ = p2b.p2a._topology_evidence(vertices, triangles)

        result = _run_fixture(vertices, triangles)

        self.assertEqual(topology, "U")
        self.assertEqual(result["status"], "MANIFOLD_CORROBORATED")
        self.assertEqual(result["manifold_status"], "NoError")

    def test_binary64_vertices_colliding_in_float32_are_a_discrepancy(self) -> None:
        result = _run_fixture(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0 + 1e-10, 0.0, 0.0),
                (0.0, 1.0, 0.0),
            ],
            [(0, 1, 3), (0, 3, 2)],
        )

        self.assertEqual(result["status"], "MANIFOLD_DISCREPANCY")
        self.assertIsNone(result["manifold_status"])
        self.assertEqual(
            result["diagnostic"],
            "BINARY64_VERTICES_COLLIDE_AFTER_REQUIRED_FLOAT32_CONVERSION",
        )

    def test_p2a_counts_over_limit_stop_before_rematerialisation(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        limits = {
            "input_vertex_instances": p2b.MAX_VERTICES,
            "exact_unique_vertices": p2b.MAX_VERTICES,
            "triangles_materialised": p2b.MAX_TRIANGLES,
        }
        for field, limit in limits.items():
            with self.subTest(field=field):
                forged = json.loads(json.dumps(audit))
                forged["geometry"][field] = limit + 1
                with mock.patch.object(
                    p2b.p2a,
                    "_materialise_scene",
                    side_effect=AssertionError(
                        "over-limit evidence reached rematerialisation"
                    ),
                ):
                    mesh, _commitment, result = p2b._canonical_mesh(payload, forged)

                self.assertIsNone(mesh)
                self.assertEqual(result["status"], "RESOURCE_LIMIT")
                self.assertEqual(
                    result["diagnostic"], "P2A_GEOMETRY_COUNT_LIMIT_REACHED"
                )

    def test_empty_p2a_mesh_is_terminal_error_not_corroboration(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        audit = json.loads(json.dumps(audit))
        audit["geometry"]["input_vertex_instances"] = 0
        audit["geometry"]["exact_unique_vertices"] = 0
        audit["geometry"]["triangles_materialised"] = 0

        with mock.patch.object(
            p2b.p2a,
            "_materialise_scene",
            side_effect=AssertionError("empty evidence reached rematerialisation"),
        ):
            mesh, _commitment, result = p2b._canonical_mesh(payload, audit)

        self.assertIsNone(mesh)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["diagnostic"], "EMPTY_CANONICAL_SURFACE_FORBIDDEN")

    def test_wrapper_also_rejects_empty_mesh_as_error(self) -> None:
        result = _run_fixture([], [])

        self.assertEqual(result["status"], "ERROR")
        self.assertIsNone(result["manifold_status"])
        self.assertIsNone(result["output_mesh"])

    def test_python_lengths_are_rechecked_before_child_serialisation(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        audit = json.loads(json.dumps(audit))
        audit["geometry"]["input_vertex_instances"] = 2
        audit["geometry"]["exact_unique_vertices"] = 2

        with mock.patch.object(p2b, "MAX_VERTICES", 3):
            mesh, _commitment, result = p2b._canonical_mesh(payload, audit)

        self.assertIsNone(mesh)
        self.assertEqual(result["status"], "RESOURCE_LIMIT")
        self.assertEqual(result["diagnostic"], "PYTHON_MATERIALISATION_LIMIT_REACHED")


class P2bIdentityAndResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime_identity = p2b._runtime_identity()

    def test_work_id_binds_terminal_mesh_runtime_and_profile(self) -> None:
        arguments = {
            "source_sha256": "1" * 64,
            "canonical_mesh_sha256": "2" * 64,
            "p2a_terminal_checkpoint_sha256": "3" * 64,
            "p2a_terminal_file_sha256": "4" * 64,
            "runtime_identity": self.runtime_identity,
        }
        _, baseline = p2b._make_plan(**arguments)

        for field in (
            "source_sha256",
            "canonical_mesh_sha256",
            "p2a_terminal_checkpoint_sha256",
            "p2a_terminal_file_sha256",
        ):
            changed = dict(arguments)
            changed[field] = "f" * 64
            self.assertNotEqual(p2b._make_plan(**changed)[1], baseline)
        changed_runtime = json.loads(json.dumps(self.runtime_identity))
        changed_runtime["node"]["arch"] = "adversarial-test-arch"
        changed = {**arguments, "runtime_identity": changed_runtime}
        self.assertNotEqual(p2b._make_plan(**changed)[1], baseline)

    def test_wrapper_import_bypasses_package_exports(self) -> None:
        wrapper = p2b.WRAPPER.read_text(encoding="utf-8")

        self.assertIn('./node_modules/manifold-3d/manifold.js"', wrapper)
        self.assertNotIn('from "manifold-3d"', wrapper)

    def test_forged_installed_package_exports_fail_closed(self) -> None:
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)
        package = json.loads(p2b.INSTALLED_PACKAGE_JSON.read_text(encoding="utf-8"))
        package["exports"] = {".": "./adversarial-redirect.js"}

        with tempfile.TemporaryDirectory(dir=private_tmp) as temporary:
            forged = Path(temporary) / "package.json"
            forged.write_text(json.dumps(package), encoding="utf-8")
            with mock.patch.object(p2b, "INSTALLED_PACKAGE_JSON", forged), self.assertRaisesRegex(
                p2b.P2bError, "metadata differs"
            ):
                p2b._runtime_identity()

    def test_child_output_uses_bounded_files_not_capture_output(self) -> None:
        mesh = _mesh(*_tetrahedron())
        digest = p2b._canonical_mesh_sha256(mesh)
        expected = _synthetic_child_result(digest)

        def fake_run(*_arguments: object, **keywords: object) -> SimpleNamespace:
            self.assertNotIn("capture_output", keywords)
            self.assertIn("stdout", keywords)
            self.assertIn("stderr", keywords)
            keywords["stdout"].write(json.dumps(expected).encode("utf-8"))
            return SimpleNamespace(returncode=0)

        with mock.patch.object(p2b.subprocess, "run", side_effect=fake_run):
            result = p2b._run_child(mesh, digest)

        self.assertEqual(result["status"], "MANIFOLD_CORROBORATED")

    def test_parent_treats_exact_child_file_cap_as_resource_limit_before_reading(self) -> None:
        mesh = _mesh(*_tetrahedron())
        digest = p2b._canonical_mesh_sha256(mesh)

        def fake_run(*_arguments: object, **keywords: object) -> SimpleNamespace:
            keywords["stdout"].write(b"x" * p2b.CHILD_OUTPUT_BYTES)
            return SimpleNamespace(returncode=0)

        with mock.patch.object(p2b.subprocess, "run", side_effect=fake_run):
            result = p2b._run_child(mesh, digest)

        self.assertEqual(result["status"], "RESOURCE_LIMIT")
        self.assertEqual(result["diagnostic"], "BOUNDED_CHILD_OUTPUT_LIMIT")

    def test_interruption_retries_once_then_exact_terminal_skips(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)
        calls = 0

        def interrupted_then_complete(
            _mesh_value: dict[str, object], canonical_mesh_sha256: str
        ) -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise p2b.P2bInterrupted("synthetic child interruption")
            return _synthetic_child_result(canonical_mesh_sha256)

        with tempfile.TemporaryDirectory(dir=private_tmp) as temporary:
            output = Path(temporary) / "run"
            with self.assertRaises(p2b.P2bInterrupted):
                p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="3" * 64,
                    p2a_terminal_file_sha256="4" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=interrupted_then_complete,
                )
            completed = p2b._execute_prevalidated(
                source_payload=payload,
                audit=audit,
                p2a_terminal_checkpoint_sha256="3" * 64,
                p2a_terminal_file_sha256="4" * 64,
                output_root=output,
                runtime_identity=self.runtime_identity,
                child_runner=interrupted_then_complete,
            )
            skipped = p2b._execute_prevalidated(
                source_payload=payload,
                audit=audit,
                p2a_terminal_checkpoint_sha256="3" * 64,
                p2a_terminal_file_sha256="4" * 64,
                output_root=output,
                runtime_identity=self.runtime_identity,
                child_runner=lambda *_: self.fail("terminal P2b work was rerun"),
            )

        self.assertEqual(calls, 2)
        self.assertEqual(completed["action"], "COMPLETED")
        self.assertEqual(skipped["action"], "SKIP")
        self.assertEqual(
            completed["terminal_checkpoint_sha256"], skipped["terminal_checkpoint_sha256"]
        )

    def test_second_child_no_status_becomes_terminal_error_and_then_skips(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)
        calls = 0

        def always_interrupted(*_arguments: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            raise p2b.P2bInterrupted("synthetic child interruption")

        with tempfile.TemporaryDirectory(dir=private_tmp) as temporary:
            output = Path(temporary) / "run"
            with self.assertRaises(p2b.P2bInterrupted):
                p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="9" * 64,
                    p2a_terminal_file_sha256="a" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=always_interrupted,
                )
            completed = p2b._execute_prevalidated(
                source_payload=payload,
                audit=audit,
                p2a_terminal_checkpoint_sha256="9" * 64,
                p2a_terminal_file_sha256="a" * 64,
                output_root=output,
                runtime_identity=self.runtime_identity,
                child_runner=always_interrupted,
            )
            skipped = p2b._execute_prevalidated(
                source_payload=payload,
                audit=audit,
                p2a_terminal_checkpoint_sha256="9" * 64,
                p2a_terminal_file_sha256="a" * 64,
                output_root=output,
                runtime_identity=self.runtime_identity,
                child_runner=lambda *_: self.fail("terminal ERROR was rerun"),
            )

        self.assertEqual(calls, 2)
        self.assertEqual(completed["action"], "COMPLETED")
        self.assertEqual(completed["status"], "ERROR")
        self.assertEqual(skipped["action"], "SKIP")
        self.assertEqual(skipped["status"], "ERROR")

    def test_restart_after_second_attempt_never_runs_a_third_child(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)
        calls = 0

        def always_interrupted(*_arguments: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            raise p2b.P2bInterrupted("synthetic child interruption")

        with tempfile.TemporaryDirectory(dir=private_tmp) as temporary:
            output = Path(temporary) / "run"
            with self.assertRaises(p2b.P2bInterrupted):
                p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="b" * 64,
                    p2a_terminal_file_sha256="c" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=always_interrupted,
                )
            with mock.patch.object(
                p2b,
                "_publish_bundle",
                side_effect=p2b.P2bError("synthetic crash before ERROR bundle"),
            ), self.assertRaises(p2b.P2bError):
                p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="b" * 64,
                    p2a_terminal_file_sha256="c" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=always_interrupted,
                )
            recovered_as_error = p2b._execute_prevalidated(
                source_payload=payload,
                audit=audit,
                p2a_terminal_checkpoint_sha256="b" * 64,
                p2a_terminal_file_sha256="c" * 64,
                output_root=output,
                runtime_identity=self.runtime_identity,
                child_runner=lambda *_: self.fail("a third child attempt was launched"),
            )

        self.assertEqual(calls, 2)
        self.assertEqual(recovered_as_error["action"], "COMPLETED")
        self.assertEqual(recovered_as_error["status"], "ERROR")

    def test_complete_atomic_bundle_is_recovered_without_child_redo(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)
        original_terminal = p2b._terminal_from_bundle

        with tempfile.TemporaryDirectory(dir=private_tmp) as temporary:
            output = Path(temporary) / "run"
            with mock.patch.object(
                p2b,
                "_terminal_from_bundle",
                side_effect=p2b.P2bError("synthetic stop after atomic bundle"),
            ), self.assertRaises(p2b.P2bError):
                p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="5" * 64,
                    p2a_terminal_file_sha256="6" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=lambda _mesh_value, digest: _synthetic_child_result(digest),
                )
            with mock.patch.object(p2b, "_terminal_from_bundle", wraps=original_terminal):
                recovered = p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="5" * 64,
                    p2a_terminal_file_sha256="6" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=lambda *_: self.fail("complete bundle caused child redo"),
                )

        self.assertEqual(recovered["action"], "RECOVERED")
        self.assertEqual(recovered["status"], "MANIFOLD_CORROBORATED")

    def test_forged_ready_bundle_cannot_claim_corroboration_without_evidence(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=private_tmp) as temporary:
            output = Path(temporary) / "run"
            with mock.patch.object(
                p2b,
                "_terminal_from_bundle",
                side_effect=p2b.P2bError("synthetic stop before terminal"),
            ), self.assertRaises(p2b.P2bError):
                p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="d" * 64,
                    p2a_terminal_file_sha256="e" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=lambda _mesh_value, digest: _synthetic_child_result(digest),
                )
            run_directory = next((output / "objects").iterdir())
            artifact_directory = run_directory / "artifacts"
            evidence_path = artifact_directory / p2b.ARTIFACT_FILENAME
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["manifold_status"] = None
            evidence["output_mesh"] = None
            evidence_payload = p2b._json_document(evidence)
            evidence_path.write_bytes(evidence_payload)
            manifest = {
                "files": {
                    p2b.ARTIFACT_FILENAME: {
                        "bytes": len(evidence_payload),
                        "sha256": p2b.p2a._sha256_bytes(evidence_payload),
                    }
                },
                "schema": "MVX-P2B-WITNESS-BUNDLE",
                "schema_version": "0.1.0",
            }
            manifest_payload = p2b._json_document(manifest)
            (artifact_directory / "bundle-manifest.json").write_bytes(manifest_payload)
            (artifact_directory / "READY.json").write_bytes(
                p2b._json_document(
                    {
                        "bundle_manifest_sha256": p2b.p2a._sha256_bytes(manifest_payload),
                        "schema": "MVX-P2B-WITNESS-BUNDLE-READY",
                        "schema_version": "0.1.0",
                    }
                )
            )

            with self.assertRaisesRegex(p2b.P2bError, "status semantics"):
                p2b._execute_prevalidated(
                    source_payload=payload,
                    audit=audit,
                    p2a_terminal_checkpoint_sha256="d" * 64,
                    p2a_terminal_file_sha256="e" * 64,
                    output_root=output,
                    runtime_identity=self.runtime_identity,
                    child_runner=lambda *_: self.fail("forged READY bundle reached child"),
                )

    def test_private_evidence_contains_no_paths_or_lineage_tokens(self) -> None:
        payload, audit = _tetra_glb_and_audit()
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)
        secrets = ("private-drive-id", "objaverse-secret-uid", "/private/source/path.glb")

        with tempfile.TemporaryDirectory(dir=private_tmp) as temporary:
            output = Path(temporary) / "run"
            result = p2b._execute_prevalidated(
                source_payload=payload,
                audit=audit,
                p2a_terminal_checkpoint_sha256="7" * 64,
                p2a_terminal_file_sha256="8" * 64,
                output_root=output,
                runtime_identity=self.runtime_identity,
                child_runner=lambda _mesh_value, digest: _synthetic_child_result(digest),
            )
            evidence_path = (
                output
                / "objects"
                / result["work_id"]
                / "artifacts"
                / p2b.ARTIFACT_FILENAME
            )
            evidence = evidence_path.read_text(encoding="utf-8")

        for secret in secrets:
            self.assertNotIn(secret, evidence)
        self.assertNotIn(str(output), evidence)
        self.assertIn('"primary_status_changed": false', evidence)


class StrictP2aDependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        private_tmp = p2b.REPOSITORY_ROOT / "tmp"
        private_tmp.mkdir(mode=0o700, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=private_tmp)
        self.root = Path(self.temporary.name)
        self.fixture = _strict_p2a_fixture(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self) -> tuple[bytes, dict[str, object], str, str]:
        return p2b._validate_p2a_inputs(
            self.fixture["source_path"],
            self.fixture["audit_plan_path"],
            self.fixture["execution_plan_path"],
            self.fixture["checkpoint_directory"],
            self.fixture["artifact_directory"],
        )

    def test_exact_plan_chain_terminal_and_artifacts_validate(self) -> None:
        payload, audit, terminal_sha256, terminal_file_sha256 = self.validate()

        self.assertEqual(payload, self.fixture["payload"])
        self.assertEqual(audit["topology_status"], "U")
        self.assertRegex(terminal_sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(terminal_file_sha256, r"^[0-9a-f]{64}$")

    def test_forged_terminal_is_rejected(self) -> None:
        terminal_path = max(self.fixture["checkpoint_directory"].iterdir())
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        terminal["error_code"] = "MVX-G001"
        terminal_path.write_bytes(p2b.p2a._json_document(terminal))

        with self.assertRaises((p2b.P2bError, p2b.p2a.P2aError)):
            self.validate()

    def test_truncated_checkpoint_chain_is_rejected(self) -> None:
        first = min(self.fixture["checkpoint_directory"].iterdir())
        first.unlink()

        with self.assertRaises((p2b.P2bError, p2b.p2a.P2aError)):
            self.validate()

    def test_execution_plan_mismatch_is_rejected(self) -> None:
        path = self.fixture["execution_plan_path"]
        execution_plan = json.loads(path.read_text(encoding="utf-8"))
        execution_plan["plan_id"] = "MVX-P2A-ADVERSARIAL-PLAN"
        path.write_bytes(p2b.p2a._json_document(execution_plan))

        with self.assertRaisesRegex(p2b.P2bError, "execution plan differs"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
