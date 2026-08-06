from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "mvx_p2c_exact_intersections.py"
SPEC = importlib.util.spec_from_file_location("mvx_p2c_exact_intersections", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
p2c = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p2c
SPEC.loader.exec_module(p2c)

BACKUP_TEST_SCRIPT = Path(__file__).resolve().parent / "test_mvx_backup_guard.py"
BACKUP_SPEC = importlib.util.spec_from_file_location(
    "mvx_backup_guard_fixture_for_p2c", BACKUP_TEST_SCRIPT
)
assert BACKUP_SPEC is not None and BACKUP_SPEC.loader is not None
backup_fixture = importlib.util.module_from_spec(BACKUP_SPEC)
BACKUP_SPEC.loader.exec_module(backup_fixture)


def mesh(vertices: list[list[float]], triangles: list[list[int]]) -> dict[str, object]:
    return {
        "schema": p2c.MESH_SCHEMA,
        "schema_version": p2c.MESH_SCHEMA_VERSION,
        "triangles": triangles,
        "vertices": vertices,
    }


def tetrahedron(
    vertices: list[list[float]], offset: int = 0
) -> tuple[list[list[float]], list[list[int]]]:
    return vertices, [
        [offset + 0, offset + 2, offset + 1],
        [offset + 0, offset + 1, offset + 3],
        [offset + 1, offset + 2, offset + 3],
        [offset + 2, offset + 0, offset + 3],
    ]


def cube() -> tuple[list[list[float]], list[list[int]]]:
    vertices = [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ]
    triangles = [
        [0, 2, 1],
        [0, 3, 2],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [1, 2, 6],
        [1, 6, 5],
        [2, 3, 7],
        [2, 7, 6],
        [3, 0, 4],
        [3, 4, 7],
    ]
    return vertices, triangles


def external_anchor_key() -> tuple[object, str]:
    # Unit-test stand-in for a key that production keeps outside the P2c worker.
    private_key = p2c.Ed25519PrivateKey.generate()
    public_key_hex = (
        private_key.public_key()
        .public_bytes(
            p2c.serialization.Encoding.Raw,
            p2c.serialization.PublicFormat.Raw,
        )
        .hex()
    )
    return private_key, public_key_hex


def signed_external_anchor(payload: dict[str, object], private_key: object) -> dict[str, object]:
    signature = private_key.sign(p2c._external_anchor_message(payload)).hex()
    return {
        **payload,
        "signature_algorithm": "ED25519",
        "signature_hex": signature,
    }


def signed_anchor_readback_receipt(
    payload: dict[str, object], private_key: object
) -> dict[str, object]:
    signature = private_key.sign(p2c._anchor_readback_message(payload)).hex()
    return {
        **payload,
        "signature_algorithm": "ED25519",
        "signature_hex": signature,
    }


def materialise_drive_triplet(root: Path, drive_evidence: dict[str, object]) -> dict[str, object]:
    checkpoint_bytes, checkpoint, completed_bytes, completed, latest = backup_fixture._fixture()
    drive_evidence_bytes = p2c._canonical_bytes(drive_evidence)
    evidence_file_id = "p2c-drive-evidence-id"
    checkpoint["drive"]["files"].append(
        {
            "bytes": len(drive_evidence_bytes),
            "download_verified": True,
            "drive_file_id": evidence_file_id,
            "name": "morphoia-p2c-drive-evidence.json",
            "sha256": p2c._sha256_bytes(drive_evidence_bytes),
        }
    )
    completed["artifact_set"].append(
        {
            "drive_file_id": evidence_file_id,
            "sha256": p2c._sha256_bytes(drive_evidence_bytes),
        }
    )
    checkpoint_bytes = backup_fixture._document(checkpoint)
    checkpoint_registry = completed["checkpoint_registry"]
    checkpoint_registry["bytes"] = len(checkpoint_bytes)
    checkpoint_registry["sha256"] = p2c._sha256_bytes(checkpoint_bytes)
    latest["checkpoint_registry"] = json.loads(json.dumps(checkpoint_registry))
    completed_bytes = backup_fixture._document(completed)
    latest["terminal_marker"]["bytes"] = len(completed_bytes)
    latest["terminal_marker"]["sha256"] = p2c._sha256_bytes(completed_bytes)
    latest_bytes = backup_fixture._document(latest)

    checkpoint_path = root / "drive-checkpoint.json"
    completed_path = root / "drive-completed.json"
    latest_path = root / "drive-latest.json"
    checkpoint_path.write_bytes(checkpoint_bytes)
    completed_path.write_bytes(completed_bytes)
    latest_path.write_bytes(latest_bytes)
    materialised = {
        "artifact-id": backup_fixture._document({"checkpoint_id": "cp-origin"}),
        "latest-evidence-id": b"latest evidence\n",
        "revision-evidence-id": b"revision evidence\n",
        evidence_file_id: drive_evidence_bytes,
    }
    artifact_map: dict[str, str] = {}
    for file_id, payload in materialised.items():
        path = root / f"drive-artifact-{file_id}.bin"
        path.write_bytes(payload)
        artifact_map[file_id] = str(path)
    artifact_map_path = root / "drive-artifact-map.json"
    artifact_map_path.write_bytes(p2c._canonical_bytes(artifact_map))
    return {
        "artifact_map": artifact_map_path,
        "checkpoint": checkpoint_path,
        "completed": completed_path,
        "completed_drive_id": "completed-drive-id",
        "latest": latest_path,
        "latest_drive_id": "latest-drive-id",
    }


class ExactPredicateTests(unittest.TestCase):
    def test_disjoint_triangles_are_exhaustively_free_candidate(self) -> None:
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [3.0, 0.0, 0.0],
                [4.0, 0.0, 0.0],
                [3.0, 1.0, 0.0],
            ],
            [[0, 1, 2], [3, 4, 5]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.FREE)
        self.assertEqual(result["broadphase"]["active_pair_comparisons"], 0)
        self.assertIsNone(result["contact"])

    def test_coplanar_overlap_is_exact_polygon_contact(self) -> None:
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.5, 0.5, 0.0],
                [2.0, 0.5, 0.0],
                [0.5, 2.0, 0.0],
            ],
            [[0, 1, 2], [3, 4, 5]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["kind"], "POLYGON")
        self.assertEqual(result["contact"]["dimension"], 2)
        self.assertEqual(result["contact"]["shared_topological_vertices"], [])

    def test_coplanar_shared_edge_only_is_allowed(self) -> None:
        document = mesh(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
            [[0, 1, 2], [1, 3, 2]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.FREE)
        self.assertEqual(result["broadphase"]["allowed_topological_adjacencies"], 1)

    def test_shared_vertex_only_is_allowed(self) -> None:
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [-1.0, 0.0, 1.0],
                [0.0, -1.0, 1.0],
            ],
            [[0, 1, 2], [0, 3, 4]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.FREE)
        self.assertEqual(result["broadphase"]["allowed_topological_adjacencies"], 1)

    def test_geometrically_equal_but_unwelded_vertices_are_contact(self) -> None:
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
                [-1.0, 0.0, 1.0],
                [0.0, -1.0, 1.0],
            ],
            [[0, 1, 2], [3, 4, 5]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["kind"], "POINT")
        self.assertEqual(result["contact"]["shared_topological_vertices"], [])

    def test_shared_edge_with_overlap_beyond_edge_is_rejected(self) -> None:
        document = mesh(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.5, 0.5, 0.0]],
            [[0, 1, 2], [0, 1, 3]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["kind"], "POLYGON")
        self.assertEqual(result["contact"]["shared_topological_vertices"], [0, 1])

    def test_shared_vertex_with_overlap_beyond_vertex_is_rejected(self) -> None:
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            [[0, 1, 2], [0, 3, 4]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["shared_topological_vertices"], [0])
        self.assertEqual(result["contact"]["dimension"], 2)

    def test_noncoplanar_edge_face_intersection_is_exact_segment(self) -> None:
        document = mesh(
            [
                [-1.0, -1.0, 0.0],
                [1.0, -1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, -1.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
            ],
            [[0, 1, 2], [3, 4, 5]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["kind"], "SEGMENT")

    def test_distinct_tetrahedra_with_vertex_face_tangency_are_rejected(self) -> None:
        lower_vertices, lower_faces = tetrahedron(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, -2.0]]
        )
        upper_vertices, upper_faces = tetrahedron(
            [[0.5, 0.5, 0.0], [0.4, 0.4, 1.0], [0.6, 0.4, 1.0], [0.5, 0.6, 1.0]],
            4,
        )
        document = mesh(lower_vertices + upper_vertices, lower_faces + upper_faces)

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["kind"], "POINT")
        self.assertEqual(result["contact"]["shared_topological_vertices"], [])

    def test_two_intersecting_tetrahedra_are_rejected(self) -> None:
        first_vertices, first_faces = tetrahedron(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 2.0]]
        )
        second_vertices, second_faces = tetrahedron(
            [[0.5, 0.5, -1.0], [1.5, 0.5, 1.0], [0.5, 1.5, 1.0], [-0.5, 0.5, 1.0]],
            4,
        )

        result = p2c.analyze_mesh(
            mesh(first_vertices + second_vertices, first_faces + second_faces)
        )

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertIn(result["contact"]["kind"], {"POINT", "SEGMENT", "POLYGON"})

    def test_cube_with_separate_triangle_piercing_face_is_rejected(self) -> None:
        vertices, triangles = cube()
        vertices.extend([[0.5, 0.5, 0.5], [0.5, 0.5, 1.5], [0.75, 0.5, 1.5]])
        triangles.append([8, 9, 10])

        result = p2c.analyze_mesh(mesh(vertices, triangles))

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["shared_topological_vertices"], [])

    def test_cube_vertex_pushed_through_opposite_face_is_rejected(self) -> None:
        vertices, triangles = cube()
        vertices[6] = [0.75, 0.5, -0.5]

        result = p2c.analyze_mesh(mesh(vertices, triangles))

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["kind"], "SEGMENT")
        self.assertEqual(result["contact"]["shared_topological_vertices"], [])

    def test_closed_cube_alone_only_has_allowed_topological_contacts(self) -> None:
        vertices, triangles = cube()

        result = p2c.analyze_mesh(mesh(vertices, triangles))

        self.assertEqual(result["status"], p2c.FREE)
        self.assertGreater(result["broadphase"]["allowed_topological_adjacencies"], 0)

    def test_extreme_scale_is_not_rounded_by_epsilon(self) -> None:
        scale = 1e-200
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [scale, 0.0, 0.0],
                [0.0, scale, 0.0],
                [2 * scale, 0.0, 0.0],
                [3 * scale, 0.0, 0.0],
                [2 * scale, scale, 0.0],
            ],
            [[0, 1, 2], [3, 4, 5]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.FREE)

    def test_large_offset_preserves_binary64_topology(self) -> None:
        origin = 1e16
        document = mesh(
            [
                [origin, origin, origin],
                [origin + 4.0, origin, origin],
                [origin, origin + 4.0, origin],
                [origin + 4.0, origin + 4.0, origin],
            ],
            [[0, 1, 2], [1, 3, 2]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.FREE)
        self.assertEqual(result["broadphase"]["allowed_topological_adjacencies"], 1)

    def test_degenerate_float64_triangle_returns_error(self) -> None:
        document = mesh(
            [[1e16, 0.0, 0.0], [1e16 + 1.0, 0.0, 0.0], [1e16, 1.0, 0.0]],
            [[0, 1, 2]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.ERROR)
        self.assertEqual(result["error_code"], "INVALID_MESH")
        self.assertEqual(result["diagnostic"], "CANONICAL_MESH_CONTRACT_REJECTED")

    def test_duplicate_face_is_overlap_not_allowed_adjacency(self) -> None:
        document = mesh(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[0, 1, 2], [2, 1, 0]],
        )

        result = p2c.analyze_mesh(document)

        self.assertEqual(result["status"], p2c.CONTACT)
        self.assertEqual(result["contact"]["kind"], "POLYGON")
        self.assertEqual(result["contact"]["shared_topological_vertices"], [0, 1, 2])

    def test_candidate_pair_budget_is_declared(self) -> None:
        vertices, triangles = cube()

        result = p2c.analyze_mesh(
            mesh(vertices, triangles),
            p2c.Limits(max_candidate_pairs=1),
        )

        self.assertEqual(result["status"], p2c.RESOURCE_LIMIT)
        self.assertEqual(result["error_code"], "MAX_CANDIDATE_PAIRS")
        self.assertEqual(result["broadphase"]["active_pair_comparisons"], 2)

    def test_four_thousand_x_active_y_disjoint_triangles_are_bounded_before_yz(self) -> None:
        vertices: list[list[float]] = []
        triangles: list[list[int]] = []
        for index in range(4_000):
            base = len(vertices)
            y = float(index * 3)
            vertices.extend([[0.0, y, 0.0], [1.0, y, 0.0], [0.0, y + 1.0, 0.0]])
            triangles.append([base, base + 1, base + 2])

        result = p2c.analyze_mesh(
            mesh(vertices, triangles),
            p2c.Limits(max_candidate_pairs=5_000),
        )

        self.assertEqual(result["status"], p2c.RESOURCE_LIMIT)
        self.assertEqual(result["error_code"], "MAX_CANDIDATE_PAIRS")
        self.assertEqual(result["broadphase"]["active_pair_comparisons"], 5_001)
        self.assertEqual(result["broadphase"]["bbox_candidate_pairs"], 0)
        self.assertEqual(result["broadphase"]["exact_pairs_examined"], 0)

    def test_minimal_fake_free_result_fails_closed_contract(self) -> None:
        with self.assertRaisesRegex(p2c.P2cError, "unknown or missing"):
            p2c._validate_analysis_contract(
                {"status": p2c.FREE},
                p2c.Limits().as_dict(),
            )


class CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        p2c._ensure_private_root()
        self.temporary = tempfile.TemporaryDirectory(dir=p2c.PRIVATE_ROOT)
        self.root = Path(self.temporary.name)
        self.source = self.root / "mesh.json"
        self.output = self.root / "output"
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [2.0, 0.0, 0.0],
                [3.0, 0.0, 0.0],
                [2.0, 1.0, 0.0],
            ],
            [[0, 1, 2], [3, 4, 5]],
        )
        self.source.write_bytes(p2c._canonical_bytes(document))

    def _terminal_artifacts(self, work_id: str) -> tuple[Path, Path, dict[str, object]]:
        run_directory = self.output / "runs" / work_id
        terminal_path = max((run_directory / "checkpoints").iterdir())
        terminal = json.loads(terminal_path.read_bytes())
        result_path = run_directory / "attempt-results" / terminal["result_filename"]
        return terminal_path, result_path, terminal

    def _write_external_anchor(
        self, work_id: str, private_key: object, name: str = "anchor.json"
    ) -> tuple[Path, Path]:
        run_directory, chain, plan = p2c._load_terminal_run(self.output, work_id)
        drive_evidence = p2c.build_drive_evidence_document(run_directory, chain, plan)
        drive = materialise_drive_triplet(self.root, drive_evidence)
        payload = p2c.build_external_anchor_payload(
            run_directory,
            chain,
            plan,
            drive_checkpoint=drive["checkpoint"],
            drive_completed=drive["completed"],
            drive_latest=drive["latest"],
            drive_artifact_map=drive["artifact_map"],
            completed_drive_id=drive["completed_drive_id"],
            latest_drive_id=drive["latest_drive_id"],
            signed_anchor_drive_file_id="signed-anchor-drive-id",
            signed_anchor_parent_id="signed-anchor-parent-id",
        )
        anchor = signed_external_anchor(payload, private_key)
        path = self.root / name
        path.write_bytes(p2c._canonical_bytes(anchor))
        readback_payload = p2c.build_anchor_readback_payload(path)
        readback = signed_anchor_readback_receipt(readback_payload, private_key)
        readback_path = self.root / f"{name}.readback.json"
        readback_path.write_bytes(p2c._canonical_bytes(readback))
        return path, readback_path

    def _replace_source_with_contact_mesh(self) -> None:
        document = mesh(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.5, 0.5, 0.0],
                [2.0, 0.5, 0.0],
                [0.5, 2.0, 0.0],
            ],
            [[0, 1, 2], [3, 4, 5]],
        )
        self.source.write_bytes(p2c._canonical_bytes(document))

    @staticmethod
    def _forge_contact_as_contract_complete_free(result: dict[str, object]) -> None:
        result["contact"] = None
        result["diagnostic"] = "ALL_CONSERVATIVE_BROADPHASE_PAIRS_EXHAUSTED"
        result["error_code"] = None
        result["status"] = p2c.FREE

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_second_identical_run_is_hash_verified_skip(self) -> None:
        private_key, public_key_hex = external_anchor_key()
        first = p2c.run_checkpointed(
            self.source,
            self.output,
            external_anchor_public_key_hex=public_key_hex,
        )
        second = p2c.run_checkpointed(
            self.source,
            self.output,
            external_anchor_public_key_hex=public_key_hex,
        )
        anchor_path, readback_path = self._write_external_anchor(first["work_id"], private_key)
        third = p2c.run_checkpointed(
            self.source,
            self.output,
            external_anchor=anchor_path,
            external_anchor_readback_receipt=readback_path,
            external_anchor_public_key_hex=public_key_hex,
        )

        self.assertEqual(first["action"], "COMPLETED_UNANCHORED")
        self.assertEqual(second["action"], "READY_FOR_BACKUP")
        self.assertEqual(third["action"], "SKIP_ANCHORED")
        self.assertEqual(first["work_id"], second["work_id"])
        self.assertEqual(first["terminal_checkpoint_sha256"], third["terminal_checkpoint_sha256"])
        self.assertEqual(third["result"]["status"], p2c.FREE)

    def test_anchor_template_and_validation_cli_bind_complete_terminal_evidence(self) -> None:
        private_key, public_key_hex = external_anchor_key()
        completed = p2c.run_checkpointed(
            self.source,
            self.output,
            external_anchor_public_key_hex=public_key_hex,
        )
        run_directory, chain, plan = p2c._load_terminal_run(self.output, completed["work_id"])
        drive_evidence = p2c.build_drive_evidence_document(run_directory, chain, plan)
        drive = materialise_drive_triplet(self.root, drive_evidence)
        template_output = io.StringIO()
        with contextlib.redirect_stdout(template_output):
            return_code = p2c.main(
                [
                    "anchor-template",
                    "--output-root",
                    str(self.output),
                    "--work-id",
                    completed["work_id"],
                    "--drive-checkpoint",
                    str(drive["checkpoint"]),
                    "--drive-completed",
                    str(drive["completed"]),
                    "--drive-latest",
                    str(drive["latest"]),
                    "--drive-artifact-map",
                    str(drive["artifact_map"]),
                    "--completed-drive-id",
                    str(drive["completed_drive_id"]),
                    "--latest-drive-id",
                    str(drive["latest_drive_id"]),
                    "--signed-anchor-drive-file-id",
                    "signed-anchor-drive-id-cli",
                    "--signed-anchor-parent-id",
                    "signed-anchor-parent-id-cli",
                ]
            )
        self.assertEqual(return_code, 0)
        payload_bytes = template_output.getvalue().encode()
        payload = json.loads(payload_bytes)
        self.assertEqual(set(payload), p2c.EXTERNAL_ANCHOR_UNSIGNED_FIELDS)
        self.assertEqual(payload_bytes, p2c._canonical_bytes(payload))
        anchor = signed_external_anchor(payload, private_key)
        anchor_path = self.root / "cli-anchor.json"
        anchor_path.write_bytes(p2c._canonical_bytes(anchor))
        readback_payload = p2c.build_anchor_readback_payload(anchor_path)
        readback = signed_anchor_readback_receipt(readback_payload, private_key)
        readback_path = self.root / "cli-anchor-readback.json"
        readback_path.write_bytes(p2c._canonical_bytes(readback))

        validation_output = io.StringIO()
        with contextlib.redirect_stdout(validation_output):
            validation_code = p2c.main(
                [
                    "validate-anchor",
                    "--output-root",
                    str(self.output),
                    "--anchor",
                    str(anchor_path),
                    "--anchor-readback-receipt",
                    str(readback_path),
                ]
            )
        validation = json.loads(validation_output.getvalue())
        self.assertEqual(validation_code, 0)
        self.assertEqual(validation["action"], "ANCHOR_VALID")
        self.assertEqual(validation["work_id"], completed["work_id"])

    def test_anchor_template_rejects_unverified_or_tampered_drive_triplet(self) -> None:
        _, public_key_hex = external_anchor_key()
        completed = p2c.run_checkpointed(
            self.source,
            self.output,
            external_anchor_public_key_hex=public_key_hex,
        )
        run_directory, chain, plan = p2c._load_terminal_run(self.output, completed["work_id"])
        drive_evidence = p2c.build_drive_evidence_document(run_directory, chain, plan)
        drive = materialise_drive_triplet(self.root, drive_evidence)
        latest = json.loads(drive["latest"].read_bytes())
        latest["checkpoint_id"] = "fabricated-local-checkpoint"
        drive["latest"].write_bytes(backup_fixture._document(latest))

        with self.assertRaisesRegex(p2c.P2cError, "failed exact guard"):
            p2c.build_external_anchor_payload(
                run_directory,
                chain,
                plan,
                drive_checkpoint=drive["checkpoint"],
                drive_completed=drive["completed"],
                drive_latest=drive["latest"],
                drive_artifact_map=drive["artifact_map"],
                completed_drive_id=drive["completed_drive_id"],
                latest_drive_id=drive["latest_drive_id"],
                signed_anchor_drive_file_id="signed-anchor-drive-id-tampered",
                signed_anchor_parent_id="signed-anchor-parent-id-tampered",
            )

    def test_tampered_external_anchor_cannot_authorize_skip(self) -> None:
        private_key, public_key_hex = external_anchor_key()
        completed = p2c.run_checkpointed(
            self.source,
            self.output,
            external_anchor_public_key_hex=public_key_hex,
        )
        anchor_path, readback_path = self._write_external_anchor(completed["work_id"], private_key)
        anchor = json.loads(anchor_path.read_bytes())
        anchor["result_sha256"] = "0" * 64
        anchor_path.write_bytes(p2c._canonical_bytes(anchor))

        with self.assertRaisesRegex(p2c.P2cError, "signature is invalid"):
            p2c.run_checkpointed(
                self.source,
                self.output,
                external_anchor=anchor_path,
                external_anchor_readback_receipt=readback_path,
                external_anchor_public_key_hex=public_key_hex,
            )

    def test_anchor_key_omission_or_change_fails_before_new_run_directory(self) -> None:
        private_key, public_key_hex = external_anchor_key()
        completed = p2c.run_checkpointed(
            self.source,
            self.output,
            external_anchor_public_key_hex=public_key_hex,
        )
        anchor_path, readback_path = self._write_external_anchor(completed["work_id"], private_key)
        run_root = self.output / "runs"
        before = {path.name for path in run_root.iterdir()}

        with self.assertRaisesRegex(p2c.P2cError, "must be supplied together"):
            p2c.run_checkpointed(
                self.source,
                self.output,
                external_anchor=anchor_path,
                external_anchor_public_key_hex=public_key_hex,
            )
        with self.assertRaisesRegex(p2c.P2cError, "requires the precommitted"):
            p2c.run_checkpointed(
                self.source,
                self.output,
                external_anchor=anchor_path,
                external_anchor_readback_receipt=readback_path,
            )
        _, wrong_public_key_hex = external_anchor_key()
        with self.assertRaisesRegex(p2c.P2cError, "work ID differs"):
            p2c.run_checkpointed(
                self.source,
                self.output,
                external_anchor=anchor_path,
                external_anchor_readback_receipt=readback_path,
                external_anchor_public_key_hex=wrong_public_key_hex,
            )

        self.assertEqual({path.name for path in run_root.iterdir()}, before)

    def test_contact_to_free_orphan_is_never_recovered_when_terminal_is_removed(self) -> None:
        self._replace_source_with_contact_mesh()
        first = p2c.run_checkpointed(self.source, self.output)
        self.assertEqual(first["result"]["status"], p2c.CONTACT)
        terminal_path, result_path, _ = self._terminal_artifacts(first["work_id"])
        self.assertIn("terminal", terminal_path.name)
        terminal_path.unlink()
        forged = json.loads(result_path.read_bytes())
        self._forge_contact_as_contract_complete_free(forged)
        result_path.write_bytes(p2c._canonical_bytes(forged))

        with self.assertRaisesRegex(p2c.P2cError, "private key is unavailable"):
            p2c.run_checkpointed(self.source, self.output)

    def test_interrupted_running_attempt_is_preserved_before_retry(self) -> None:
        source = p2c._snapshot_regular(self.source, p2c.DEFAULT_MAX_INPUT_BYTES)
        plan = p2c._make_plan(
            source,
            {"mesh_sha256": source.sha256, "mode": "CANONICAL_MESH"},
            p2c.Limits(),
            p2c.DEFAULT_MAX_INPUT_BYTES,
        )
        work_id = plan["work_id"]
        plan_sha = p2c._sha256_value(plan)
        run_directory = self.output / "runs" / work_id
        checkpoints = run_directory / "checkpoints"
        p2c._ensure_private_tree(checkpoints)
        claims = p2c._ensure_private_tree(run_directory / "authority-claims")
        secrets = p2c._ensure_private_tree(run_directory / "authority-secrets")
        p2c._ensure_private_tree(run_directory / "attempt-results")
        p2c._publish_once(run_directory / "execution-plan.json", p2c._canonical_bytes(plan))
        chain: list[dict[str, object]] = []
        p2c._append_checkpoint(
            checkpoints,
            chain,
            state="PENDING",
            attempt=1,
            plan_sha256=plan_sha,
            work_id=work_id,
        )
        _, claim_sha256, _ = p2c._ensure_attempt_claim(
            claims,
            secrets,
            attempt=1,
            plan_sha256=plan_sha,
            work_id=work_id,
        )
        p2c._append_checkpoint(
            checkpoints,
            chain,
            state="RUNNING",
            attempt=1,
            plan_sha256=plan_sha,
            work_id=work_id,
            claim_sha256=claim_sha256,
        )

        resumed = p2c.run_checkpointed(self.source, self.output)
        names = [path.name for path in sorted(checkpoints.iterdir())]

        self.assertEqual(resumed["action"], "COMPLETED_UNANCHORED")
        self.assertEqual(
            names,
            [
                "0001-pending.json",
                "0002-running.json",
                "0003-interrupted.json",
                "0004-running.json",
                "0005-terminal.json",
            ],
        )

    def test_tampered_terminal_result_blocks_skip(self) -> None:
        completed = p2c.run_checkpointed(self.source, self.output)
        _, result_path, _ = self._terminal_artifacts(completed["work_id"])
        payload = json.loads(result_path.read_bytes())
        payload["diagnostic"] = "TAMPERED"
        result_path.write_bytes(p2c._canonical_bytes(payload))

        with self.assertRaisesRegex(p2c.P2cError, "does not bind result"):
            p2c.run_checkpointed(self.source, self.output)

    def test_forged_orphan_result_is_not_sealed_terminal(self) -> None:
        first = p2c.run_checkpointed(self.source, self.output)
        run_directory = self.output / "runs" / first["work_id"]
        checkpoints = run_directory / "checkpoints"
        terminal_path, result_path, _ = self._terminal_artifacts(first["work_id"])
        terminal_path.unlink()
        forged = json.loads(result_path.read_bytes())
        forged["source_sha256"] = "0" * 64
        result_path.write_bytes(p2c._canonical_bytes(forged))

        with self.assertRaisesRegex(p2c.P2cError, "private key is unavailable"):
            p2c.run_checkpointed(self.source, self.output)

        self.assertEqual(len(list(checkpoints.iterdir())), 2)

    def test_minimal_fake_result_with_matching_terminal_hash_cannot_skip(self) -> None:
        completed = p2c.run_checkpointed(self.source, self.output)
        run_directory = self.output / "runs" / completed["work_id"]
        terminal_path, _, terminal = self._terminal_artifacts(completed["work_id"])
        fake_bytes = p2c._canonical_bytes({"status": p2c.FREE})
        fake_sha256 = p2c._sha256_bytes(fake_bytes)
        fake_name = f"attempt-{terminal['attempt']:04d}-{fake_sha256[:16]}.json"
        fake_path = run_directory / "attempt-results" / fake_name
        fake_path.write_bytes(fake_bytes)
        fake_path.chmod(0o600)
        terminal["result_filename"] = fake_name
        terminal["result_sha256"] = fake_sha256
        terminal_path.write_bytes(p2c._canonical_bytes(terminal))

        with self.assertRaisesRegex(p2c.P2cError, "unknown or missing"):
            p2c.run_checkpointed(self.source, self.output)

    def test_contact_to_free_coordinated_result_and_terminal_forgery_cannot_skip(self) -> None:
        self._replace_source_with_contact_mesh()
        completed = p2c.run_checkpointed(self.source, self.output)
        self.assertEqual(completed["result"]["status"], p2c.CONTACT)
        run_directory = self.output / "runs" / completed["work_id"]
        terminal_path, result_path, terminal = self._terminal_artifacts(completed["work_id"])
        forged = json.loads(result_path.read_bytes())
        self._forge_contact_as_contract_complete_free(forged)
        forged_bytes = p2c._canonical_bytes(forged)
        forged_sha256 = p2c._sha256_bytes(forged_bytes)
        forged_name = f"attempt-{terminal['attempt']:04d}-{forged_sha256[:16]}.json"
        forged_path = run_directory / "attempt-results" / forged_name
        forged_path.write_bytes(forged_bytes)
        forged_path.chmod(0o600)
        terminal["result_filename"] = forged_name
        terminal["result_sha256"] = forged_sha256
        terminal_path.write_bytes(p2c._canonical_bytes(terminal))

        with self.assertRaisesRegex(p2c.P2cError, "signature is invalid"):
            p2c.run_checkpointed(self.source, self.output)

    def test_limit_change_creates_distinct_work_identity(self) -> None:
        first = p2c.run_checkpointed(self.source, self.output)
        second = p2c.run_checkpointed(
            self.source,
            self.output,
            p2c.Limits(max_candidate_pairs=99),
        )

        self.assertNotEqual(first["work_id"], second["work_id"])
        self.assertEqual(second["action"], "COMPLETED_UNANCHORED")

    def test_invalid_json_error_is_terminal_and_idempotent(self) -> None:
        self.source.write_text("not-json", encoding="utf-8")

        first = p2c.run_checkpointed(self.source, self.output)
        second = p2c.run_checkpointed(self.source, self.output)

        self.assertEqual(first["result"]["status"], p2c.ERROR)
        self.assertEqual(second["action"], "READY_FOR_BACKUP")

    def test_oversized_input_is_terminal_resource_limit_and_skip(self) -> None:
        first = p2c.run_checkpointed(self.source, self.output, max_input_bytes=10)
        second = p2c.run_checkpointed(self.source, self.output, max_input_bytes=10)

        self.assertEqual(first["result"]["status"], p2c.RESOURCE_LIMIT)
        self.assertEqual(first["result"]["error_code"], "MAX_INPUT_BYTES")
        self.assertEqual(second["action"], "READY_FOR_BACKUP")

    def test_child_no_status_retries_twice_then_terminal_error(self) -> None:
        with mock.patch.object(
            p2c,
            "_run_analysis_child",
            side_effect=p2c.ChildNoStatus("synthetic child crash"),
        ) as child:
            completed = p2c.run_checkpointed(self.source, self.output)

        self.assertEqual(child.call_count, 2)
        self.assertEqual(completed["result"]["status"], p2c.ERROR)
        self.assertEqual(completed["result"]["error_code"], "CHILD_RETRY_EXHAUSTED")
        checkpoint_directory = self.output / "runs" / completed["work_id"] / "checkpoints"
        self.assertEqual(
            [path.name for path in sorted(checkpoint_directory.iterdir())],
            [
                "0001-pending.json",
                "0002-running.json",
                "0003-interrupted.json",
                "0004-running.json",
                "0005-terminal.json",
            ],
        )

    def test_interrupted_secret_left_by_crash_is_verified_consumed_before_retry(self) -> None:
        with (
            mock.patch.object(
                p2c,
                "_run_analysis_child",
                side_effect=p2c.ChildNoStatus("synthetic child crash"),
            ),
            mock.patch.object(
                p2c,
                "_unlink_private_regular",
                side_effect=p2c.P2cError("synthetic unlink crash"),
            ),
            self.assertRaisesRegex(p2c.P2cError, "synthetic unlink crash"),
        ):
            p2c.run_checkpointed(self.source, self.output)

        completed = p2c.run_checkpointed(self.source, self.output)
        secret_directory = self.output / "runs" / completed["work_id"] / "authority-secrets"

        self.assertEqual(completed["action"], "COMPLETED_UNANCHORED")
        self.assertEqual(list(secret_directory.iterdir()), [])

    def test_bad_checkpoint_state_type_is_structured_rejection(self) -> None:
        completed = p2c.run_checkpointed(self.source, self.output)
        checkpoint_directory = self.output / "runs" / completed["work_id"] / "checkpoints"
        pending_path = checkpoint_directory / "0001-pending.json"
        pending = json.loads(pending_path.read_bytes())
        pending["state"] = 7
        pending_path.write_bytes(p2c._canonical_bytes(pending))

        with self.assertRaisesRegex(p2c.P2cError, "invalid type or value"):
            p2c.run_checkpointed(self.source, self.output)

    def test_runtime_identity_binds_integer_digit_policy(self) -> None:
        completed = p2c.run_checkpointed(self.source, self.output)
        plan_path = self.output / "runs" / completed["work_id"] / "execution-plan.json"
        plan = json.loads(plan_path.read_bytes())

        self.assertEqual(
            plan["environment"]["int_max_str_digits"],
            sys.get_int_max_str_digits(),
        )

    def test_external_child_timeout_is_closed_resource_result(self) -> None:
        with mock.patch.object(
            p2c.subprocess,
            "run",
            side_effect=p2c.subprocess.TimeoutExpired("child", 1),
        ):
            result = p2c._run_analysis_child(self.source.read_bytes(), p2c.Limits())

        self.assertEqual(result["status"], p2c.RESOURCE_LIMIT)
        self.assertEqual(result["error_code"], "CHILD_TIMEOUT")

    def test_output_outside_repository_tmp_is_rejected(self) -> None:
        with (
            tempfile.TemporaryDirectory() as outside,
            self.assertRaisesRegex(p2c.P2cError, "must remain"),
        ):
            p2c.run_checkpointed(self.source, Path(outside) / "output")

    def test_symlink_output_parent_is_rejected(self) -> None:
        real = self.root / "real"
        real.mkdir()
        link = self.root / "linked-parent"
        os.symlink(real, link)

        with self.assertRaisesRegex(p2c.P2cError, "symlink or non-directory"):
            p2c.run_checkpointed(self.source, link / "output")

    def test_anchor_cli_loader_rejects_intermediate_output_symlink(self) -> None:
        completed = p2c.run_checkpointed(self.source, self.output)
        linked_output = self.root / "linked-output"
        os.symlink(self.output, linked_output)

        with self.assertRaisesRegex(p2c.P2cError, "unsafe component"):
            p2c._load_terminal_run(linked_output, completed["work_id"])

    def test_symlink_source_is_rejected_by_nofollow_snapshot(self) -> None:
        source_link = self.root / "mesh-link.json"
        os.symlink(self.source, source_link)

        with self.assertRaisesRegex(p2c.P2cError, "regular non-symlink"):
            p2c.run_checkpointed(source_link, self.output)

    def test_symlink_result_is_rejected_before_skip(self) -> None:
        completed = p2c.run_checkpointed(self.source, self.output)
        _, result_path, _ = self._terminal_artifacts(completed["work_id"])
        result_path.unlink()
        os.symlink(self.source, result_path)

        with self.assertRaisesRegex(p2c.P2cError, "attempt result directory"):
            p2c.run_checkpointed(self.source, self.output)

    def test_symlink_checkpoint_directory_is_rejected(self) -> None:
        completed = p2c.run_checkpointed(self.source, self.output)
        checkpoint_directory = self.output / "runs" / completed["work_id"] / "checkpoints"
        for path in checkpoint_directory.iterdir():
            path.unlink()
        checkpoint_directory.rmdir()
        replacement = self.root / "replacement-checkpoints"
        replacement.mkdir()
        os.symlink(replacement, checkpoint_directory)

        with self.assertRaisesRegex(p2c.P2cError, "symlink or non-directory"):
            p2c.run_checkpointed(self.source, self.output)


class P2aBoundTests(unittest.TestCase):
    def setUp(self) -> None:
        p2c._ensure_private_root()
        self.temporary = tempfile.TemporaryDirectory(dir=p2c.PRIVATE_ROOT)
        self.root = Path(self.temporary.name)
        self.output = self.root / "p2c-output"
        self.p2a = p2c._load_p2a_module()
        self.source_glb = self.root / "source.glb"
        payload = self.p2a._build_test_glb(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ],
            [0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3],
        )
        self.source_glb.write_bytes(payload)
        source_base = {
            "drive_file_id": "synthetic-p2c",
            "source_sha256": p2c._sha256_bytes(payload),
            "source_size_bytes": len(payload),
            "source_title": "synthetic-p2c.glb",
            "source_uid": "0123456789abcdef0123456789abcdef",
        }
        source = {
            **source_base,
            "candidate_commitment_sha256": self.p2a._canonical_hash(source_base),
        }
        self.plan, self.p2a_work_id = self.p2a._make_object_plan(
            source,
            {"profile": "synthetic-p2c"},
            "a" * 64,
            "b" * 64,
        )
        audit = self.p2a.audit_glb_bytes(payload)
        self.assertIsNotNone(audit["geometry"])
        audit_record = {
            "audit": audit,
            "candidate_commitment_sha256": source["candidate_commitment_sha256"],
            "code_git_commit_sha1": "c" * 40,
            "code_git_tree_sha1": "d" * 40,
            "schema": "MVX-P2A-PRIVATE-AUDIT-RECORD",
            "schema_version": "0.1.0",
            "work_id": self.p2a_work_id,
        }
        self.audit_record_path = self.root / "audit-record.json"
        audit_bytes = self.p2a._json_document(audit_record)
        self.audit_record_path.write_bytes(audit_bytes)
        self.execution_plan_path = self.root / "execution-plan.json"
        self.execution_plan_path.write_bytes(self.p2a._json_document(self.plan))
        self.p2a_checkpoint_directory = self.root / "p2a-checkpoints"
        self.p2a_checkpoint_directory.mkdir()
        pending = self.p2a.make_stage_checkpoint(
            self.plan,
            self.p2a_work_id,
            state="PENDING",
        )
        running = self.p2a.make_stage_checkpoint(
            self.plan,
            self.p2a_work_id,
            state="RUNNING",
            previous_checkpoint=pending,
        )
        artifact_hashes = {
            "audit_record": p2c._sha256_bytes(audit_bytes),
            "parser_evidence": "1" * 64,
            "resource_evidence": "2" * 64,
            "source_receipt": "3" * 64,
        }
        terminal = self.p2a.make_stage_checkpoint(
            self.plan,
            self.p2a_work_id,
            state="TERMINAL",
            terminal_status=audit["terminal_status"],
            error_code=audit["error_code"],
            artifact_hashes=artifact_hashes,
            previous_checkpoint=running,
        )
        for sequence, checkpoint in enumerate((pending, running, terminal), start=1):
            name = (
                f"{sequence:04d}-attempt-{checkpoint['attempt']:04d}-"
                f"{checkpoint['state'].casefold()}.json"
            )
            self.p2a.write_checkpoint(self.p2a_checkpoint_directory / name, checkpoint)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_real_p2a_terminal_binds_materialized_mesh_and_skips(self) -> None:
        private_key, public_key_hex = external_anchor_key()
        first = p2c.run_checkpointed_p2a(
            self.source_glb,
            self.audit_record_path,
            self.execution_plan_path,
            self.p2a_checkpoint_directory,
            self.output,
            external_anchor_public_key_hex=public_key_hex,
        )
        run_directory, chain, plan = p2c._load_terminal_run(self.output, first["work_id"])
        drive_evidence = p2c.build_drive_evidence_document(run_directory, chain, plan)
        drive = materialise_drive_triplet(self.root, drive_evidence)
        payload = p2c.build_external_anchor_payload(
            run_directory,
            chain,
            plan,
            drive_checkpoint=drive["checkpoint"],
            drive_completed=drive["completed"],
            drive_latest=drive["latest"],
            drive_artifact_map=drive["artifact_map"],
            completed_drive_id=drive["completed_drive_id"],
            latest_drive_id=drive["latest_drive_id"],
            signed_anchor_drive_file_id="signed-anchor-drive-id-p2a",
            signed_anchor_parent_id="signed-anchor-parent-id-p2a",
        )
        anchor = signed_external_anchor(payload, private_key)
        anchor_path = self.root / "p2a-anchor.json"
        anchor_path.write_bytes(p2c._canonical_bytes(anchor))
        readback_payload = p2c.build_anchor_readback_payload(anchor_path)
        readback = signed_anchor_readback_receipt(readback_payload, private_key)
        readback_path = self.root / "p2a-anchor-readback.json"
        readback_path.write_bytes(p2c._canonical_bytes(readback))
        second = p2c.run_checkpointed_p2a(
            self.source_glb,
            self.audit_record_path,
            self.execution_plan_path,
            self.p2a_checkpoint_directory,
            self.output,
            external_anchor=anchor_path,
            external_anchor_readback_receipt=readback_path,
            external_anchor_public_key_hex=public_key_hex,
        )

        self.assertEqual(first["result"]["input_binding"]["mode"], "P2A_BOUND")
        self.assertEqual(
            first["result"]["input_binding"]["p2a_work_id"],
            self.p2a_work_id,
        )
        self.assertEqual(first["result"]["status"], p2c.FREE)
        self.assertEqual(first["result"]["mesh"], {"triangle_count": 4, "vertex_count": 4})
        self.assertEqual(second["action"], "SKIP_ANCHORED")
        plan_path = self.output / "runs" / first["work_id"] / "execution-plan.json"
        p2c_plan = json.loads(plan_path.read_bytes())
        base = {name: value for name, value in p2c_plan.items() if name != "work_id"}
        self.assertEqual(p2c_plan["work_id"], p2c._sha256_value(base))
        self.assertEqual(
            p2c_plan["input_binding"]["mesh_sha256"],
            first["result"]["input_binding"]["mesh_sha256"],
        )

    def test_tampered_p2a_audit_record_is_rejected_before_p2c_run(self) -> None:
        audit_record = json.loads(self.audit_record_path.read_bytes())
        audit_record["audit"]["geometry"]["triangles_materialised"] += 1
        self.audit_record_path.write_bytes(self.p2a._json_document(audit_record))

        with self.assertRaisesRegex(p2c.P2cError, "terminal does not bind"):
            p2c.run_checkpointed_p2a(
                self.source_glb,
                self.audit_record_path,
                self.execution_plan_path,
                self.p2a_checkpoint_directory,
                self.output,
            )

    def test_tampered_p2a_checkpoint_chain_is_rejected_before_materialization(self) -> None:
        running_path = self.p2a_checkpoint_directory / "0002-attempt-0001-running.json"
        running = json.loads(running_path.read_bytes())
        running["previous_checkpoint_sha256"] = "0" * 64
        running_path.write_bytes(self.p2a._json_document(running))

        with self.assertRaisesRegex(p2c.P2cError, "checkpoint chain"):
            p2c.run_checkpointed_p2a(
                self.source_glb,
                self.audit_record_path,
                self.execution_plan_path,
                self.p2a_checkpoint_directory,
                self.output,
            )

    def test_audit_and_terminal_coordinated_forgery_fails_rematerialization(self) -> None:
        audit_record = json.loads(self.audit_record_path.read_bytes())
        audit_record["audit"]["geometry"]["triangles_materialised"] += 1
        forged_audit_bytes = self.p2a._json_document(audit_record)
        self.audit_record_path.write_bytes(forged_audit_bytes)
        terminal_path = self.p2a_checkpoint_directory / "0003-attempt-0001-terminal.json"
        terminal = json.loads(terminal_path.read_bytes())
        terminal["artifact_hashes"]["audit_record"] = p2c._sha256_bytes(forged_audit_bytes)
        terminal_path.write_bytes(self.p2a._json_document(terminal))

        with self.assertRaisesRegex(p2c.P2cError, "rematerialization differs"):
            p2c.run_checkpointed_p2a(
                self.source_glb,
                self.audit_record_path,
                self.execution_plan_path,
                self.p2a_checkpoint_directory,
                self.output,
            )


if __name__ == "__main__":
    unittest.main()
