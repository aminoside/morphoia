from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "mvx_p2c_persistent_signer.py"
SPEC = importlib.util.spec_from_file_location("mvx_p2c_persistent_signer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
signer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = signer
SPEC.loader.exec_module(signer)


def _write(path: Path, payload: bytes, mode: int) -> None:
    path.write_bytes(payload)
    path.chmod(mode)


def _private_json(path: Path, value: object) -> None:
    _write(path, signer._canonical_bytes(value), 0o600)


def _private_p2c_json(path: Path, p2c: object, value: object) -> None:
    _write(path, p2c._canonical_bytes(value), 0o600)


class PersistentSignerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.key = self.root / "custodian.ed25519-private"
        self.manifest = self.root / "custodian-public.json"
        self.manifest_document = signer.initialize_signer(
            self.key,
            self.manifest,
            challenge=bytes(range(32)),
            created_at="2026-08-07T00:00:00Z",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _plan_and_anchor(self) -> tuple[Path, Path]:
        p2c = signer._load_p2c()
        source_bytes = b"persistent-signer-test-source"
        source = p2c.FileSnapshot(
            payload=source_bytes,
            sha256=hashlib.sha256(source_bytes).hexdigest(),
            size_bytes=len(source_bytes),
            over_limit=False,
        )
        binding = {"mesh_sha256": source.sha256, "mode": "CANONICAL_MESH"}
        plan = p2c._make_plan(
            source,
            binding,
            p2c.Limits(),
            p2c.DEFAULT_MAX_INPUT_BYTES,
            external_anchor_public_key_hex=self.manifest_document["public_key_ed25519_hex"],
        )
        plan_path = self.root / "execution-plan.json"
        _private_p2c_json(plan_path, p2c, plan)

        evidence_row = {
            "download_verified": True,
            "drive_file_id": "drive-evidence-file",
            "sha256": "1" * 64,
            "size_bytes": 123,
        }
        artifact_set = [evidence_row]
        checkpoint_receipt = {
            "download_verified": True,
            "drive_file_id": "checkpoint-file",
            "sha256": "2" * 64,
            "size_bytes": 456,
        }
        drive_receipt = {
            "artifact_set": artifact_set,
            "artifact_set_sha256": p2c._sha256_value(artifact_set),
            "backup_guard_code_sha256": p2c._sha256_bytes(p2c.BACKUP_GUARD_SCRIPT.read_bytes()),
            "checkpoint": checkpoint_receipt,
            "checkpoint_id": "checkpoint-p2c-v2-test",
            "completed": {
                "download_verified": True,
                "drive_file_id": "completed-file",
                "sha256": "3" * 64,
                "size_bytes": 789,
            },
            "drive_evidence_file_id": "drive-evidence-file",
            "drive_evidence_sha256": "1" * 64,
            "guard_summary_sha256": "4" * 64,
            "latest": {
                "download_verified": True,
                "drive_file_id": "latest-file",
                "sha256": "5" * 64,
                "size_bytes": 321,
            },
            "predecessor_checkpoint_id": "checkpoint-p2c-v1",
            "publication_model": "APPEND_ONLY_CHECKPOINT_COMPLETED_MUTABLE_LATEST",
            "publication_order": ["ARTIFACTS", "CHECKPOINT", "COMPLETED", "LATEST"],
            "schema": "MVX-P2C-VERIFIED-DRIVE-RECEIPT",
            "schema_version": "0.1.0",
            "trust_scope": "P2C_AUXILIARY_REUSE_ONLY_NEVER_SOLID_V",
        }
        unsigned_anchor = {
            "anchor_persistence_policy": (
                "EXTERNAL_SIGNER_MUST_UPLOAD_SIGNED_BYTES_TO_PREALLOCATED_LOCATOR_AND_"
                "VERIFY_READBACK_BEFORE_REUSE"
            ),
            "artifact_manifest_sha256": "6" * 64,
            "authority_claim_chain_sha256": "7" * 64,
            "checkpoint_chain_sha256": "8" * 64,
            "code_sha256": plan["code_sha256"],
            "completed_id": "mvx-p2c-completed:test",
            "completed_sha256": "9" * 64,
            "drive_receipt": drive_receipt,
            "external_anchor_id": "signed-anchor-file-v2",
            "external_anchor_parent_id": "signed-anchor-parent-v2",
            "external_checkpoint_id": drive_receipt["checkpoint_id"],
            "external_checkpoint_sha256": checkpoint_receipt["sha256"],
            "input_binding_sha256": p2c._sha256_value(plan["input_binding"]),
            "plan_sha256": p2c._sha256_value(plan),
            "result_id": "attempt-results/result.json",
            "result_sha256": "a" * 64,
            "runtime_sha256": p2c._sha256_value(plan["environment"]),
            "schema": "MVX-P2C-EXTERNAL-COMPLETION-ANCHOR",
            "schema_version": "0.1.0",
            "source_sha256": plan["source_sha256"],
            "source_size_bytes": plan["source_size_bytes"],
            "terminal_id": "checkpoints/0003-terminal.json",
            "terminal_sha256": "b" * 64,
            "trust_model": p2c.EXTERNAL_ANCHOR_TRUST_MODEL,
            "work_id": plan["work_id"],
        }
        anchor_path = self.root / "unsigned-anchor.json"
        _private_p2c_json(anchor_path, p2c, unsigned_anchor)
        return plan_path, anchor_path

    def _storage_inputs(self) -> tuple[Path, Path, Path, Path]:
        key_bytes = self.key.read_bytes()
        paths: list[Path] = []
        metadata_paths: list[Path] = []
        for slot in ("a", "b"):
            copy_path = self.root / f"copy-{slot}.ed25519-private"
            _write(copy_path, key_bytes, 0o400)
            metadata = {
                "download_verified": True,
                "drive_file_id": f"drive-copy-{slot}",
                "drive_parent_id": f"drive-owner-private-parent-{slot}",
                "owner_only": True,
                "permission_roles": ["owner"],
                "revision_id": f"drive-revision-{slot}",
                "schema": signer.OWNER_COPY_SCHEMA,
                "schema_version": signer.SCHEMA_VERSION,
                "sha256": hashlib.sha256(key_bytes).hexdigest(),
                "shared": False,
                "size_bytes": len(key_bytes),
            }
            metadata_path = self.root / f"copy-{slot}-metadata.json"
            _private_json(metadata_path, metadata)
            paths.append(copy_path)
            metadata_paths.append(metadata_path)
        return paths[0], metadata_paths[0], paths[1], metadata_paths[1]

    def test_init_creates_raw_0400_key_and_self_signed_public_manifest(self) -> None:
        self.assertEqual(len(self.key.read_bytes()), 32)
        self.assertEqual(stat.S_IMODE(self.key.stat().st_mode), 0o400)
        self.assertEqual(stat.S_IMODE(self.manifest.stat().st_mode), 0o644)
        verified = signer.verify_manifest(self.manifest_document)
        self.assertEqual(verified["assurances"], signer.ASSURANCES)
        self.assertFalse(verified["assurances"]["independent"])
        self.assertFalse(verified["assurances"]["worm"])
        self.assertFalse(verified["assurances"]["encryption"])
        self.assertFalse(verified["assurances"]["drive_origin_proof"])

        newline_manifest = self.root / "public-manifest-with-newline.json"
        newline_manifest.write_bytes(self.manifest.read_bytes() + b"\n")
        newline_manifest.chmod(0o644)
        _, parsed = signer._load_manifest(newline_manifest)
        self.assertEqual(parsed, self.manifest_document)

    def test_bind_existing_reuses_key_and_binds_new_challenge(self) -> None:
        rebound = self.root / "rebound-public.json"
        document = signer.bind_existing_signer(
            self.key,
            rebound,
            challenge=b"r" * 32,
            created_at="2026-08-08T00:00:00Z",
        )
        self.assertEqual(
            document["public_key_ed25519_hex"],
            self.manifest_document["public_key_ed25519_hex"],
        )
        self.assertEqual(document["challenge_hex"], (b"r" * 32).hex())
        self.assertEqual(signer.verify_manifest(document), document)
        self.assertEqual(stat.S_IMODE(self.key.stat().st_mode), 0o400)
        with self.assertRaisesRegex(signer.SignerError, "MANIFEST_ALREADY_EXISTS"):
            signer.bind_existing_signer(self.key, rebound, challenge=b"s" * 32)

    def test_cli_never_prints_key_secret_hash_or_signature(self) -> None:
        second_root = self.root / "second"
        second_root.mkdir(mode=0o700)
        key_path = second_root / "key"
        manifest_path = second_root / "manifest.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            return_code = signer.main(
                [
                    "init",
                    "--key",
                    str(key_path),
                    "--manifest",
                    str(manifest_path),
                    "--challenge-hex",
                    "42" * 32,
                    "--created-at",
                    "2026-08-06T12:00:00Z",
                ]
            )
        emitted = output.getvalue()
        raw = key_path.read_bytes()
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(return_code, 0)
        self.assertEqual(json.loads(emitted), {"action": "INITIALIZED"})
        self.assertNotIn(raw.hex(), emitted)
        self.assertNotIn(hashlib.sha256(raw).hexdigest(), emitted)
        self.assertNotIn(manifest["challenge_signature_hex"], emitted)
        self.assertEqual(manifest["challenge_hex"], "42" * 32)
        self.assertEqual(manifest["created_at"], "2026-08-06T12:00:00Z")

    def test_cli_rejects_malformed_explicit_challenge_without_creating_key(self) -> None:
        second_root = self.root / "invalid-challenge"
        second_root.mkdir(mode=0o700)
        key_path = second_root / "key"
        manifest_path = second_root / "manifest.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            return_code = signer.main(
                [
                    "init",
                    "--key",
                    str(key_path),
                    "--manifest",
                    str(manifest_path),
                    "--challenge-hex",
                    "not-a-32-byte-challenge",
                ]
            )
        self.assertEqual(return_code, 2)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"action": "ERROR", "code": "CHALLENGE_HEX_INVALID"},
        )
        self.assertFalse(key_path.exists())
        self.assertFalse(manifest_path.exists())

    def test_manifest_tampering_and_wrong_private_key_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.manifest_document)
        tampered["assurances"]["independent"] = True
        with self.assertRaisesRegex(signer.SignerError, "MANIFEST_CONTRACT"):
            signer.verify_manifest(tampered)

        other_key = self.root / "other-key"
        other_manifest = self.root / "other-manifest.json"
        signer.initialize_signer(other_key, other_manifest)
        with self.assertRaisesRegex(signer.SignerError, "PRIVATE_KEY_MANIFEST_MISMATCH"):
            signer._verify_key_matches_manifest(other_key, self.manifest_document)

    def test_sign_anchor_and_readback_use_runner_contract_and_plan_key(self) -> None:
        plan_path, unsigned_anchor_path = self._plan_and_anchor()
        signed_anchor_path = self.root / "signed-anchor.json"
        signed = signer.sign_anchor(
            self.key,
            self.manifest,
            plan_path,
            unsigned_anchor_path,
            signed_anchor_path,
        )
        self.assertEqual(stat.S_IMODE(signed_anchor_path.stat().st_mode), 0o600)
        self.assertEqual(signed["signature_algorithm"], "ED25519")
        signer.verify_anchor_files(self.manifest, plan_path, signed_anchor_path)

        readback_path = self.root / "signed-readback.json"
        readback = signer.sign_readback(
            self.key,
            self.manifest,
            plan_path,
            signed_anchor_path,
            readback_path,
        )
        self.assertTrue(readback["download_verified"])
        signer.verify_anchor_files(
            self.manifest,
            plan_path,
            signed_anchor_path,
            readback_path,
        )

    def test_anchor_work_id_or_plan_signer_substitution_is_rejected(self) -> None:
        plan_path, unsigned_anchor_path = self._plan_and_anchor()
        anchor = json.loads(unsigned_anchor_path.read_bytes())
        anchor["work_id"] = "0" * 64
        _private_p2c_json(unsigned_anchor_path, signer._load_p2c(), anchor)
        with self.assertRaisesRegex(signer.SignerError, "ANCHOR_PLAN_BINDING"):
            signer.sign_anchor(
                self.key,
                self.manifest,
                plan_path,
                unsigned_anchor_path,
                self.root / "must-not-exist.json",
            )

        other_key = self.root / "substitute-key"
        other_manifest = self.root / "substitute-manifest.json"
        signer.initialize_signer(other_key, other_manifest)
        with self.assertRaisesRegex(signer.SignerError, "PLAN_SIGNER_MISMATCH"):
            signer.sign_anchor(
                other_key,
                other_manifest,
                plan_path,
                unsigned_anchor_path,
                self.root / "must-not-exist-2.json",
            )

    def test_init_preflights_manifest_conflict_before_creating_private_key(self) -> None:
        second_root = self.root / "preflight"
        second_root.mkdir(mode=0o700)
        key_path = second_root / "key"
        manifest_path = second_root / "manifest.json"
        manifest_path.write_bytes(b"occupied")
        with self.assertRaisesRegex(signer.SignerError, "PRIVATE_KEY_ALREADY_EXISTS"):
            signer.initialize_signer(key_path, manifest_path)
        self.assertFalse(key_path.exists())

    def test_storage_receipt_binds_two_distinct_owner_only_exact_key_copies(self) -> None:
        copy_a, metadata_a, copy_b, metadata_b = self._storage_inputs()
        second_metadata = json.loads(metadata_b.read_bytes())
        second_metadata["revision_id"] = json.loads(metadata_a.read_bytes())["revision_id"]
        _private_json(metadata_b, second_metadata)
        receipt_path = self.root / "storage-receipt.json"
        receipt = signer.create_storage_receipt(
            self.key,
            self.manifest,
            copy_a,
            metadata_a,
            copy_b,
            metadata_b,
            receipt_path,
        )
        self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o600)
        self.assertEqual(receipt["trust_model"], signer.TRUST_MODEL)
        self.assertEqual([row["slot"] for row in receipt["copies"]], ["A", "B"])
        self.assertEqual(
            receipt["drive_observation_scope"],
            "CALLER_API_OBSERVED_NOT_CRYPTOGRAPHIC_DRIVE_ORIGIN_PROOF",
        )
        signer.verify_storage_receipt(
            self.manifest,
            receipt_path,
            copy_a,
            metadata_a,
            copy_b,
            metadata_b,
        )

    def test_storage_copy_or_owner_only_metadata_tampering_fails_closed(self) -> None:
        copy_a, metadata_a, copy_b, metadata_b = self._storage_inputs()
        tampered_metadata = json.loads(metadata_b.read_bytes())
        tampered_metadata["shared"] = True
        _private_json(metadata_b, tampered_metadata)
        with self.assertRaisesRegex(signer.SignerError, "STORAGE_METADATA_CONTRACT"):
            signer.create_storage_receipt(
                self.key,
                self.manifest,
                copy_a,
                metadata_a,
                copy_b,
                metadata_b,
                self.root / "must-not-exist.json",
            )

        _write(copy_b, os.urandom(32), 0o400)
        tampered_metadata["shared"] = False
        tampered_metadata["sha256"] = hashlib.sha256(copy_b.read_bytes()).hexdigest()
        _private_json(metadata_b, tampered_metadata)
        with self.assertRaisesRegex(
            signer.SignerError,
            "STORAGE_COPY_CANONICAL_KEY_MISMATCH",
        ):
            signer.create_storage_receipt(
                self.key,
                self.manifest,
                copy_a,
                metadata_a,
                copy_b,
                metadata_b,
                self.root / "must-not-exist-2.json",
            )

    def test_storage_cli_and_verify_cli_emit_only_generic_actions(self) -> None:
        copy_a, metadata_a, copy_b, metadata_b = self._storage_inputs()
        receipt_path = self.root / "storage-cli.json"
        storage_stdout = io.StringIO()
        with contextlib.redirect_stdout(storage_stdout), contextlib.redirect_stderr(io.StringIO()):
            storage_code = signer.main(
                [
                    "storage-receipt",
                    "--key",
                    str(self.key),
                    "--manifest",
                    str(self.manifest),
                    "--copy-a",
                    str(copy_a),
                    "--copy-a-metadata",
                    str(metadata_a),
                    "--copy-b",
                    str(copy_b),
                    "--copy-b-metadata",
                    str(metadata_b),
                    "--output",
                    str(receipt_path),
                ]
            )
        self.assertEqual(storage_code, 0)
        self.assertEqual(
            json.loads(storage_stdout.getvalue()),
            {"action": "STORAGE_RECEIPT_SIGNED"},
        )

        verify_stdout = io.StringIO()
        with contextlib.redirect_stdout(verify_stdout), contextlib.redirect_stderr(io.StringIO()):
            verify_code = signer.main(
                [
                    "verify",
                    "--manifest",
                    str(self.manifest),
                    "--storage-receipt",
                    str(receipt_path),
                    "--copy-a",
                    str(copy_a),
                    "--copy-a-metadata",
                    str(metadata_a),
                    "--copy-b",
                    str(copy_b),
                    "--copy-b-metadata",
                    str(metadata_b),
                ]
            )
        self.assertEqual(verify_code, 0)
        self.assertEqual(json.loads(verify_stdout.getvalue()), {"action": "VERIFIED"})


if __name__ == "__main__":
    unittest.main()
