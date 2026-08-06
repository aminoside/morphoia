from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "mvx_p2a_checkpoint.py"
SPEC = importlib.util.spec_from_file_location("mvx_p2a_checkpoint", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
p2a = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p2a
SPEC.loader.exec_module(p2a)

CAMPAIGN_PROFILE = {"profile": "fixed"}
CAMPAIGN_CODE_IDENTITY = ("f" * 64, "1" * 40, "2" * 40)
CAMPAIGN_ENVIRONMENT = "3" * 64


def _synthetic_audit(
    source: dict[str, object], *, topology: str = "O", triangles: int = 3
) -> dict[str, object]:
    return {
        "schema": p2a.AUDIT_SCHEMA,
        "schema_version": "0.1.0",
        "algorithm_id": p2a.AUDIT_ALGORITHM,
        "algorithm_version": p2a.AUDIT_ALGORITHM_VERSION,
        "source_sha256": source["source_sha256"],
        "source_size_bytes": source["source_size_bytes"],
        "external_uri_accessed": False,
        "mvx_operation_accessed": False,
        "complexity_quantile": None,
        "eligibility": "PENDING",
        "split": None,
        "khronos_validation": None,
        "terminal_status": "DECLARED_LIMIT",
        "error_code": {"O": "MVX-G001", "N": "MVX-G002", "U": "MVX-G003"}[topology],
        "format_status": "P2A_DIAGNOSTIC_PROFILE_SCAN_COMPLETE",
        "topology_status": topology,
        "container": {},
        "scene": {},
        "geometry": {"triangles_materialised": triangles},
        "diagnostic": "SYNTHETIC_TEST_EVIDENCE",
    }


def _campaign_result(
    source: dict[str, object], *, topology: str = "O", triangles: int = 3
) -> dict[str, object]:
    _, work_id = p2a._make_object_plan(
        source, CAMPAIGN_PROFILE, CAMPAIGN_CODE_IDENTITY[0], CAMPAIGN_ENVIRONMENT
    )
    return {
        "action": "COMPLETED",
        "work_id": work_id,
        "terminal_checkpoint_sha256": p2a._canonical_hash(
            {"work_id": work_id, "topology": topology, "triangles": triangles}
        ),
        "audit": _synthetic_audit(source, topology=topology, triangles=triangles),
    }


def _campaign_plan(source: dict[str, object]) -> dict[str, object]:
    return {"sources": [source], "profile": CAMPAIGN_PROFILE}


class GlbAuditTests(unittest.TestCase):
    def test_open_triangle_is_positive_open_evidence(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        result = p2a.audit_glb_bytes(payload)

        self.assertEqual(result["terminal_status"], "DECLARED_LIMIT")
        self.assertEqual(result["error_code"], "MVX-G001")
        self.assertEqual(result["topology_status"], "O")
        self.assertEqual(result["geometry"]["boundary_edge_count"], 3)
        self.assertFalse(result["external_uri_accessed"])
        self.assertFalse(result["mvx_operation_accessed"])

    def test_closed_tetrahedron_never_claims_solid_without_verifier(self) -> None:
        payload = p2a._build_test_glb(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ],
            [0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3],
        )
        result = p2a.audit_glb_bytes(payload)

        self.assertEqual(result["topology_status"], "U")
        self.assertEqual(result["error_code"], "MVX-G003")
        self.assertEqual(result["geometry"]["boundary_edge_count"], 0)
        self.assertEqual(result["geometry"]["solid_verifier"], "NOT_AVAILABLE")

    def test_degenerate_face_is_invalid_topology(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
            [0, 1, 2],
        )
        result = p2a.audit_glb_bytes(payload)

        self.assertEqual(result["topology_status"], "N")
        self.assertEqual(result["error_code"], "MVX-G002")
        self.assertEqual(result["geometry"]["degenerate_triangle_count"], 1)

    def test_disconnected_vertex_link_is_non_manifold(self) -> None:
        payload = p2a._build_test_glb(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (-1.0, 0.0, 0.0),
                (0.0, -1.0, 0.0),
            ],
            [0, 1, 2, 0, 3, 4],
        )

        result = p2a.audit_glb_bytes(payload)

        self.assertEqual(result["topology_status"], "N")
        self.assertEqual(result["error_code"], "MVX-G002")
        self.assertEqual(result["geometry"]["non_manifold_vertex_count"], 1)

    def test_invalid_header_is_rejected_without_exception(self) -> None:
        result = p2a.audit_glb_bytes(b"not-a-glb")

        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertEqual(result["format_status"], "P2A_DIAGNOSTIC_REJECTED")
        self.assertEqual(result["error_code"], "MVX-I002")
        self.assertEqual(result["topology_status"], "U")

    def test_required_draco_is_rejected_as_unsupported(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        document, binary, _ = p2a._parse_glb_container(payload)
        document["extensionsUsed"] = ["KHR_draco_mesh_compression"]
        document["extensionsRequired"] = ["KHR_draco_mesh_compression"]
        json_bytes = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
        json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
        rebuilt = (
            p2a.struct.pack("<4sII", p2a.GLB_MAGIC, 2, 12 + 8 + len(json_bytes) + 8 + len(binary))
            + p2a.struct.pack("<II", len(json_bytes), p2a.JSON_CHUNK)
            + json_bytes
            + p2a.struct.pack("<II", len(binary), p2a.BIN_CHUNK)
            + binary
        )

        result = p2a.audit_glb_bytes(rebuilt)
        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertEqual(result["error_code"], "MVX-I004")
        self.assertEqual(result["topology_status"], "U")

    def test_buffer_uri_is_never_resolved(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        document, binary, _ = p2a._parse_glb_container(payload)
        document["buffers"][0]["uri"] = "https://example.invalid/private.bin"
        json_bytes = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
        json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
        rebuilt = (
            p2a.struct.pack("<4sII", p2a.GLB_MAGIC, 2, 12 + 8 + len(json_bytes) + 8 + len(binary))
            + p2a.struct.pack("<II", len(json_bytes), p2a.JSON_CHUNK)
            + json_bytes
            + p2a.struct.pack("<II", len(binary), p2a.BIN_CHUNK)
            + binary
        )

        result = p2a.audit_glb_bytes(rebuilt)
        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertEqual(result["error_code"], "MVX-I008")
        self.assertFalse(result["external_uri_accessed"])

    def test_non_unit_quaternion_is_rejected_not_repaired(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        document, binary, _ = p2a._parse_glb_container(payload)
        document["nodes"][0]["rotation"] = [0.0, 0.0, 0.0, 2.0]
        rebuilt = self._rebuild(document, binary)

        result = p2a.audit_glb_bytes(rebuilt)

        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertEqual(result["topology_status"], "U")

    def test_extreme_finite_invertible_scale_does_not_create_false_degeneracy(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        document, binary, _ = p2a._parse_glb_container(payload)
        document["nodes"][0]["scale"] = [1.0, 1e-300, 1.0]

        result = p2a.audit_glb_bytes(self._rebuild(document, binary))

        self.assertEqual(result["topology_status"], "O")
        self.assertEqual(result["geometry"]["degenerate_triangle_count"], 0)

    def test_invalid_json_types_are_rejected(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        for field, value in (("componentType", []), ("type", {}), ("normalized", "false")):
            document, binary, _ = p2a._parse_glb_container(payload)
            document["accessors"][0][field] = value
            result = p2a.audit_glb_bytes(self._rebuild(document, binary))
            self.assertEqual(result["terminal_status"], "REJECT")

    def test_oversized_json_integer_is_bounded_reject(self) -> None:
        json_bytes = b'{"asset":{"version":"2.0"},"oversized":' + b"1" * 5000 + b"}"
        json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
        payload = (
            p2a.struct.pack("<4sII", p2a.GLB_MAGIC, 2, 12 + 8 + len(json_bytes))
            + p2a.struct.pack("<II", len(json_bytes), p2a.JSON_CHUNK)
            + json_bytes
        )

        result = p2a.audit_glb_bytes(payload)

        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertEqual(result["error_code"], "MVX-I002")

    def test_khronos_validator_rejects_invalid_unreferenced_node(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        document, binary, _ = p2a._parse_glb_container(payload)
        document["nodes"].append({"rotation": [True, 0.0, 0.0, 1.0]})

        result = p2a.audit_glb_bytes(self._rebuild(document, binary))

        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertGreater(result["khronos_validation"]["numErrors"], 0)

    def test_error_severity_and_frozen_precedence_ignore_warnings(self) -> None:
        report = {
            "errorCodeCounts": {"UNKNOWN_ASSET_MAJOR_VERSION": 1},
            "codeCounts": {
                "UNKNOWN_ASSET_MAJOR_VERSION": 1,
                "UNSUPPORTED_EXTENSION": 1,
            },
        }

        self.assertEqual(p2a._khronos_reject_code(report), "MVX-I001")

    def test_unsupported_asset_and_glb_versions_are_i001(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        document, binary, _ = p2a._parse_glb_container(payload)
        document["asset"]["version"] = "1.0"
        document["extensionsUsed"] = ["UNKNOWN_warning_only"]
        asset_result = p2a.audit_glb_bytes(self._rebuild(document, binary))
        header_payload = bytearray(payload)
        p2a.struct.pack_into("<I", header_payload, 4, 1)
        header_result = p2a.audit_glb_bytes(bytes(header_payload))

        self.assertEqual(asset_result["error_code"], "MVX-I001")
        self.assertEqual(header_result["error_code"], "MVX-I001")

    def test_nonfinite_binary_position_is_i006(self) -> None:
        payload = bytearray(
            p2a._build_test_glb(
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                [0, 1, 2],
            )
        )
        _document, _binary, container = p2a._parse_glb_container(bytes(payload))
        binary_offset = 12 + 8 + container["json_chunk_bytes"] + 8
        p2a.struct.pack_into("<f", payload, binary_offset, float("inf"))

        result = p2a.audit_glb_bytes(bytes(payload))

        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertEqual(result["error_code"], "MVX-I006")

    def test_finite_transform_overflow_is_i006(self) -> None:
        payload = p2a._build_test_glb(
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [0, 1, 2],
        )
        document, binary, _ = p2a._parse_glb_container(payload)
        document["nodes"][0]["scale"] = [1e308, 1.0, 1.0]

        result = p2a.audit_glb_bytes(self._rebuild(document, binary))

        self.assertEqual(result["terminal_status"], "REJECT")
        self.assertEqual(result["error_code"], "MVX-I006")

    @staticmethod
    def _rebuild(document: dict[str, object], binary: bytes) -> bytes:
        json_bytes = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
        json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
        total = 12 + 8 + len(json_bytes) + (8 + len(binary) if binary else 0)
        result = (
            p2a.struct.pack("<4sII", p2a.GLB_MAGIC, 2, total)
            + p2a.struct.pack("<II", len(json_bytes), p2a.JSON_CHUNK)
            + json_bytes
        )
        if binary:
            result += p2a.struct.pack("<II", len(binary), p2a.BIN_CHUNK) + binary
        return result


class PilotPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        p2a._ensure_private_directory(p2a.REPOSITORY_ROOT / "tmp")
        self.temporary = tempfile.TemporaryDirectory(dir=p2a.REPOSITORY_ROOT / "tmp")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _snapshot(self, count: int = 15) -> tuple[Path, str, list[dict[str, object]]]:
        rows = []
        for index in range(count):
            uid = f"{index + 1:032x}"
            rows.append(
                {
                    "id": f"drive-{index}",
                    "title": f"object_{uid}.glb",
                    "size": str(1000 + index * 7),
                    "mime_type": "model/gltf-binary",
                    "modified_time": "2026-08-06T00:00:00Z",
                }
            )
        payload = (json.dumps({"files": rows}, sort_keys=True) + "\n").encode()
        path = self.root / "snapshot.json"
        path.write_bytes(payload)
        return path, p2a._sha256_bytes(payload), rows

    def test_plan_is_exact_hmac_prefix_not_size_rank(self) -> None:
        snapshot, digest, rows = self._snapshot()
        output = self.root / "pilot.json"
        result = p2a.make_pilot(
            argparse.Namespace(snapshot=str(snapshot), snapshot_sha256=digest, output=str(output))
        )
        plan = json.loads(output.read_text())

        expected = sorted(
            (
                p2a._pilot_rank(p2a._extract_uid(str(row["title"])), str(row["id"])),
                str(row["id"]),
            )
            for row in rows
        )[: p2a.DEFAULT_SCOPE_COUNT]
        self.assertEqual(
            [(row["hmac_rank_hex"], row["drive_file_id"]) for row in plan["candidates"]],
            expected,
        )
        self.assertEqual(result["candidate_count"], 12)
        self.assertFalse(result["private_identity_published"])

    def test_scope_extension_preserves_prefix_and_object_identity(self) -> None:
        snapshot, digest, _ = self._snapshot(count=16)
        plan_12_path = self.root / "pilot-12.json"
        plan_14_path = self.root / "pilot-14.json"
        p2a.make_pilot(
            argparse.Namespace(
                snapshot=str(snapshot), snapshot_sha256=digest, count=12, output=str(plan_12_path)
            )
        )
        p2a.make_pilot(
            argparse.Namespace(
                snapshot=str(snapshot), snapshot_sha256=digest, count=14, output=str(plan_14_path)
            )
        )
        plan_12 = json.loads(plan_12_path.read_text())
        plan_14 = json.loads(plan_14_path.read_text())

        self.assertEqual(plan_12["candidates"], plan_14["candidates"][:12])
        for candidate in plan_12["candidates"]:
            source = {
                **candidate,
                "source_sha256": "a" * 64,
            }
            commitment = p2a._candidate_commitment_payload(source)
            source["candidate_commitment_sha256"] = p2a._canonical_hash(commitment)
            _, first = p2a._make_object_plan(source, {"profile": "fixed"}, "b" * 64, "c" * 64)
            extended = dict(source)
            extended["ordinal"] += 100
            _, second = p2a._make_object_plan(extended, {"profile": "fixed"}, "b" * 64, "c" * 64)
            self.assertEqual(first, second)

    def test_identical_plan_second_write_is_skip(self) -> None:
        snapshot, digest, _ = self._snapshot()
        output = self.root / "pilot.json"
        arguments = argparse.Namespace(
            snapshot=str(snapshot), snapshot_sha256=digest, output=str(output)
        )

        first = p2a.make_pilot(arguments)
        second = p2a.make_pilot(arguments)

        self.assertEqual(first["action"], "COMPLETED")
        self.assertEqual(second["action"], "SKIP")
        self.assertEqual(first["pilot_plan_sha256"], second["pilot_plan_sha256"])

    def test_duplicate_uid_cannot_count_twice(self) -> None:
        snapshot, _, rows = self._snapshot(count=14)
        rows.append({**rows[0], "id": "duplicate-drive"})
        payload = (json.dumps({"files": rows}, sort_keys=True) + "\n").encode()
        snapshot.write_bytes(payload)
        output = self.root / "pilot.json"
        p2a.make_pilot(
            argparse.Namespace(
                snapshot=str(snapshot),
                snapshot_sha256=p2a._sha256_bytes(payload),
                output=str(output),
            )
        )
        plan = json.loads(output.read_text())

        self.assertEqual(len({row["source_uid"] for row in plan["candidates"]}), 12)
        self.assertNotIn(rows[0]["title"], {row["source_title"] for row in plan["candidates"]})


class FilesystemAndCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        p2a._ensure_private_directory(p2a.REPOSITORY_ROOT / "tmp")
        self.temporary = tempfile.TemporaryDirectory(dir=p2a.REPOSITORY_ROOT / "tmp")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_source_symlink_is_rejected(self) -> None:
        target = self.root / "target.glb"
        target.write_bytes(b"bytes")
        link = self.root / "link.glb"
        link.symlink_to(target)

        with self.assertRaisesRegex(p2a.P2aError, "regular non-symlink"):
            p2a._read_regular_bytes(link, label="test")

    def test_object_bundle_is_atomic_and_hash_bound(self) -> None:
        run = self.root / "run"
        p2a._ensure_private_directory(run)
        artifacts = run / "artifacts"
        payloads = {name: p2a._json_document({"name": name}) for name in p2a.OBJECT_ARTIFACT_FILES}

        p2a._publish_object_bundle(run, artifacts, payloads, 1)

        self.assertTrue(p2a._validate_object_bundle(artifacts))
        self.assertEqual({path.name for path in artifacts.iterdir()}, p2a.OBJECT_BUNDLE_FILES)

    def test_partial_staging_is_quarantined_not_deleted(self) -> None:
        run = self.root / "run"
        p2a._ensure_private_directory(run)
        staging = run / "attempt-0001-artifacts.staging"
        p2a._ensure_private_directory(staging)
        (staging / "partial.json").write_text("{}")

        p2a._recover_staging(run, run / "artifacts")

        quarantined = list((run / "quarantine").iterdir())
        self.assertEqual(len(quarantined), 1)
        self.assertTrue((quarantined[0] / "partial.json").exists())

    def test_public_campaign_summary_contains_no_private_tokens(self) -> None:
        secret_uid = "a" * 32
        secret_drive = "private-drive-id"
        secret_source_hash = "b" * 64
        source = {
            "ordinal": 0,
            "drive_file_id": secret_drive,
            "source_uid": secret_uid,
            "source_title": f"secret_{secret_uid}.glb",
            "source_size_bytes": 100,
            "source_sha256": secret_source_hash,
            "candidate_commitment_sha256": "c" * 64,
            "cache_locator": f"sha256/bb/{secret_source_hash}.glb",
        }
        plan = _campaign_plan(source)
        result = _campaign_result(source)

        _, payloads = p2a._campaign_payloads(
            [result], plan, CAMPAIGN_CODE_IDENTITY, CAMPAIGN_ENVIRONMENT
        )
        public = payloads["public-summary.json"].decode()

        for token in (secret_uid, secret_drive, secret_source_hash, result["work_id"]):
            self.assertNotIn(token, public)

    def test_work_identity_does_not_depend_on_campaign_scope(self) -> None:
        source = {
            "source_sha256": "a" * 64,
            "source_uid": "b" * 32,
            "candidate_commitment_sha256": "c" * 64,
        }
        profile = {"profile": "fixed"}

        first, work_a = p2a._make_object_plan(source, profile, "d" * 64, "e" * 64)
        second, work_b = p2a._make_object_plan(source, profile, "d" * 64, "e" * 64)

        self.assertEqual(first, second)
        self.assertEqual(work_a, work_b)

    def test_child_timeout_is_a_bounded_mvx_resource_limit(self) -> None:
        source = {"source_sha256": "a" * 64, "source_size_bytes": 100}
        with mock.patch.object(
            p2a.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(("child",), 1),
        ):
            audit, evidence = p2a._run_child(self.root / "source.glb", source)

        self.assertEqual(audit["terminal_status"], "DECLARED_LIMIT")
        self.assertEqual(audit["error_code"], "MVX-R002")
        self.assertEqual(evidence["child_exit"], "TIMEOUT")

    def test_child_nonzero_is_no_status_and_never_terminalised(self) -> None:
        source = {"source_sha256": "a" * 64, "source_size_bytes": 100}
        completed = subprocess.CompletedProcess(("child",), -11, b"", b"segfault")
        with (
            mock.patch.object(p2a.subprocess, "run", return_value=completed),
            self.assertRaises(p2a.ChildNoStatus) as context,
        ):
            p2a._run_child(self.root / "source.glb", source)

        self.assertEqual(context.exception.error_code, "MVX-X002")

    def test_partial_campaign_staging_is_quarantined_then_rebuilt(self) -> None:
        source = {
            "ordinal": 0,
            "drive_file_id": "private-drive-id",
            "source_uid": "a" * 32,
            "source_title": f"secret_{'a' * 32}.glb",
            "source_size_bytes": 100,
            "source_sha256": "b" * 64,
            "candidate_commitment_sha256": "c" * 64,
            "cache_locator": f"sha256/bb/{'b' * 64}.glb",
        }
        result = _campaign_result(source)
        scope, payloads = p2a._campaign_payloads(
            [result], _campaign_plan(source), CAMPAIGN_CODE_IDENTITY, CAMPAIGN_ENVIRONMENT
        )
        campaign_root = self.root / "campaigns"
        p2a._ensure_private_directory(campaign_root)
        staging = campaign_root / f"{scope}.staging"
        p2a._ensure_private_directory(staging)
        (staging / "partial.json").write_text("{}")

        first = p2a._publish_campaign(campaign_root, scope, payloads)
        second = p2a._publish_campaign(campaign_root, scope, payloads)

        self.assertEqual(first, "COMPLETED")
        self.assertEqual(second, "SKIP")
        self.assertTrue(p2a._validate_campaign_bundle(campaign_root / scope))
        quarantined = list((campaign_root / "quarantine").iterdir())
        self.assertEqual(len(quarantined), 1)
        self.assertTrue((quarantined[0] / "partial.json").exists())

    def test_campaign_marker_corruption_is_fail_closed(self) -> None:
        source = {
            "ordinal": 0,
            "drive_file_id": "private-drive-id",
            "source_uid": "a" * 32,
            "source_title": "private.glb",
            "source_size_bytes": 100,
            "source_sha256": "b" * 64,
            "candidate_commitment_sha256": "c" * 64,
            "cache_locator": f"sha256/bb/{'b' * 64}.glb",
        }
        result = _campaign_result(source, topology="U", triangles=4)
        scope, payloads = p2a._campaign_payloads(
            [result], _campaign_plan(source), CAMPAIGN_CODE_IDENTITY, CAMPAIGN_ENVIRONMENT
        )
        campaign_root = self.root / "campaigns"
        p2a._ensure_private_directory(campaign_root)
        p2a._publish_campaign(campaign_root, scope, payloads)
        marker = campaign_root / scope / "COMPLETED.json"
        marker.chmod(0o600)
        marker.write_text("{}")

        with self.assertRaises(p2a.P2aError):
            p2a._validate_campaign_bundle(campaign_root / scope)

    def test_checkpoint_chain_replays_exact_transition_rules(self) -> None:
        source = {
            "source_sha256": "a" * 64,
            "source_uid": "b" * 32,
            "candidate_commitment_sha256": "c" * 64,
        }
        plan, work_id = p2a._make_object_plan(source, {"profile": "fixed"}, "d" * 64, "e" * 64)
        checkpoint_directory = self.root / "checkpoints"
        p2a._ensure_private_directory(checkpoint_directory)
        pending = p2a.make_stage_checkpoint(plan, work_id, state="PENDING")
        p2a._write_numbered_checkpoint(checkpoint_directory, 1, pending)
        forged_running = dict(pending)
        forged_running.update(
            {
                "attempt": 99,
                "state": "RUNNING",
                "previous_checkpoint_sha256": p2a.checkpoint_sha256(pending),
            }
        )
        p2a._write_numbered_checkpoint(checkpoint_directory, 2, forged_running)

        with self.assertRaisesRegex(p2a.P2aError, "invalid persisted checkpoint transition"):
            p2a._load_checkpoint_chain(checkpoint_directory, plan, work_id)

    def test_public_aggregate_cannot_carry_a_private_uid(self) -> None:
        secret_uid = "a" * 32
        source = {
            "ordinal": 0,
            "drive_file_id": "private-drive-id",
            "source_uid": secret_uid,
            "source_title": f"secret_{secret_uid}.glb",
            "source_size_bytes": 100,
            "source_sha256": "b" * 64,
            "candidate_commitment_sha256": "c" * 64,
            "cache_locator": f"sha256/bb/{'b' * 64}.glb",
        }
        result = _campaign_result(source)
        _scope, payloads = p2a._campaign_payloads(
            [result], _campaign_plan(source), CAMPAIGN_CODE_IDENTITY, CAMPAIGN_ENVIRONMENT
        )
        public = json.loads(payloads["public-summary.json"])
        public["aggregate_materialised_triangles"] = secret_uid
        public_payload = p2a._json_document(public)
        completed = json.loads(payloads["COMPLETED.json"])
        completed["public_summary_sha256"] = p2a._sha256_bytes(public_payload)
        directory = self.root / "campaign"
        p2a._ensure_private_directory(directory)
        (directory / "private-manifest.json").write_bytes(payloads["private-manifest.json"])
        (directory / "public-summary.json").write_bytes(public_payload)
        (directory / "COMPLETED.json").write_bytes(p2a._json_document(completed))

        with self.assertRaises(p2a.P2aError):
            p2a._validate_campaign_bundle(directory)

    def test_terminal_checkpoint_must_match_bound_audit_status(self) -> None:
        source = {
            "ordinal": 0,
            "drive_file_id": "private-drive-id",
            "source_uid": "a" * 32,
            "source_title": "private.glb",
            "source_size_bytes": 100,
            "source_sha256": "b" * 64,
            "candidate_commitment_sha256": "c" * 64,
            "cache_locator": f"sha256/bb/{'b' * 64}.glb",
        }
        plan, work_id = p2a._make_object_plan(source, {"profile": "fixed"}, "d" * 64, "e" * 64)
        audit = _synthetic_audit(source)
        payloads = p2a._artifact_payloads(
            source,
            audit,
            {"child_exit": "ZERO", "stderr_sha256": p2a._sha256_bytes(b"")},
            work_id=work_id,
            code_commit="1" * 40,
            code_tree="2" * 40,
        )
        run = self.root / "terminal-mismatch"
        p2a._ensure_private_directory(run)
        artifacts = run / "artifacts"
        p2a._publish_object_bundle(run, artifacts, payloads, 1)
        pending = p2a.make_stage_checkpoint(plan, work_id, state="PENDING")
        running = p2a.make_stage_checkpoint(
            plan, work_id, state="RUNNING", previous_checkpoint=pending
        )
        artifact_hashes = {
            name: p2a.hash_artifact(path)
            for name, path in p2a._object_artifact_paths(artifacts).items()
        }
        forged_terminal = p2a.make_stage_checkpoint(
            plan,
            work_id,
            state="TERMINAL",
            terminal_status="PASS",
            error_code="MVX-OK",
            artifact_hashes=artifact_hashes,
            previous_checkpoint=running,
        )

        with self.assertRaisesRegex(p2a.P2aError, "disagrees"):
            p2a._validated_object_audit(artifacts, source, work_id, terminal=forged_terminal)

    def test_child_no_status_is_persisted_and_retry_is_bounded(self) -> None:
        source = {
            "source_sha256": "a" * 64,
            "source_uid": "b" * 32,
            "candidate_commitment_sha256": "c" * 64,
        }
        plan, work_id = p2a._make_object_plan(source, {"profile": "fixed"}, "d" * 64, "e" * 64)
        checkpoint_directory = self.root / "crash-checkpoints"
        p2a._ensure_private_directory(checkpoint_directory)
        pending = p2a.make_stage_checkpoint(plan, work_id, state="PENDING")
        running_1 = p2a.make_stage_checkpoint(
            plan, work_id, state="RUNNING", previous_checkpoint=pending
        )
        interrupted_1 = p2a.make_stage_checkpoint(
            plan,
            work_id,
            state="INTERRUPTED",
            error_code="MVX-X002",
            interruption_reason="CHILD_NO_STATUS",
            previous_checkpoint=running_1,
        )
        for sequence, checkpoint in enumerate((pending, running_1, interrupted_1), 1):
            p2a._write_numbered_checkpoint(checkpoint_directory, sequence, checkpoint)
        chain = p2a._load_checkpoint_chain(checkpoint_directory, plan, work_id)
        running_2, next_sequence = p2a._ensure_running(
            plan,
            work_id,
            checkpoint_directory,
            chain,
            artifacts_ready=False,
        )
        self.assertEqual(running_2["attempt"], 2)
        interrupted_2 = p2a.make_stage_checkpoint(
            plan,
            work_id,
            state="INTERRUPTED",
            attempt=2,
            error_code="MVX-X002",
            interruption_reason="CHILD_NO_STATUS",
            previous_checkpoint=running_2,
        )
        p2a._write_numbered_checkpoint(checkpoint_directory, next_sequence, interrupted_2)
        chain = p2a._load_checkpoint_chain(checkpoint_directory, plan, work_id)

        with self.assertRaises(p2a.ChildNoStatus):
            p2a._ensure_running(
                plan,
                work_id,
                checkpoint_directory,
                chain,
                artifacts_ready=False,
            )


if __name__ == "__main__":
    unittest.main()
