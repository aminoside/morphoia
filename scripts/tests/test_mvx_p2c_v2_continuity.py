from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCRIPT = Path(__file__).resolve().parents[1] / "mvx_p2c_v2_continuity.py"
SPEC = importlib.util.spec_from_file_location("mvx_p2c_v2_continuity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
continuity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = continuity
SPEC.loader.exec_module(continuity)

PROJECTOR_SCRIPT = Path(__file__).resolve().parents[1] / "mvx_p2c_scientific_projection.py"
PROJECTOR_SPEC = importlib.util.spec_from_file_location(
    "mvx_p2c_scientific_projection_continuity_integration", PROJECTOR_SCRIPT
)
assert PROJECTOR_SPEC is not None and PROJECTOR_SPEC.loader is not None
scientific_projection = importlib.util.module_from_spec(PROJECTOR_SPEC)
sys.modules[PROJECTOR_SPEC.name] = scientific_projection
PROJECTOR_SPEC.loader.exec_module(scientific_projection)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: object, *, newline: bool = True) -> bytes:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return payload + (b"\n" if newline else b"")


def _write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


def _write_json(path: Path, value: object, mode: int = 0o600) -> bytes:
    payload = _json_bytes(value)
    _write(path, payload, mode)
    return payload


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.strip()


class ContinuityFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repository = root / "repository"
        self.inputs = root / "inputs"
        self.key_path = root / "owner.ed25519-private"
        self.spec_path = root / "input-spec.json"
        self.repository.mkdir(mode=0o700)
        self.inputs.mkdir(mode=0o700)
        self.owner_key = Ed25519PrivateKey.generate()
        raw_key = self.owner_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        _write(self.key_path, raw_key, 0o400)
        self.public_key = (
            self.owner_key.public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
        )
        self.parents: dict[str, dict[str, object]] = {}
        self.executions: list[dict[str, object]] = []
        self._make_private_evidence()
        self.v1_root = self._v1_root()
        self._make_repository()
        self._make_spec()

    def _make_private_evidence(self) -> None:
        for alias, digit in zip(continuity.PARENT_ALIASES, ("1", "2", "3"), strict=True):
            parent_root = self.inputs / f"parent-{alias}"
            parent_root.mkdir(mode=0o700)
            work_id = digit * 64
            source = f"synthetic-private-glb-{alias}".encode()
            source_path = parent_root / "source.glb"
            _write(source_path, source, 0o400)
            source_sha = _sha(source)
            plan = {
                "plan_id": f"MVX-P2A-{work_id[:16]}",
                "schema": "MVX-EXECUTION-PLAN",
                "schema_version": "0.1.0",
                "stages": [
                    {
                        "identity": {"source_sha256": source_sha},
                        "required_artifacts": ["audit_record"],
                        "work_id": work_id,
                    }
                ],
                "work_id_algorithm": "MVX-WORK-ID-SHA256-JCS-1",
            }
            plan_path = parent_root / "execution-plan.json"
            plan_payload = _write_json(plan_path, plan)
            audit = {
                "audit": {"source_sha256": source_sha},
                "schema": "MVX-P2A-PRIVATE-AUDIT-RECORD",
                "schema_version": "0.1.0",
                "work_id": work_id,
            }
            audit_path = parent_root / "audit-record.json"
            audit_payload = _write_json(audit_path, audit)
            receipt = {
                "schema": "MVX-P2A-PRIVATE-SOURCE-RECEIPT",
                "schema_version": "0.1.0",
                "source_sha256": source_sha,
                "source_size_bytes": len(source),
            }
            receipt_path = parent_root / "source-receipt.json"
            receipt_payload = _write_json(receipt_path, receipt)
            plan_sha = continuity._p2a_plan_hash(plan)
            checkpoints: list[Path] = []
            previous = None
            for sequence, state in enumerate(("PENDING", "RUNNING", "TERMINAL"), start=1):
                checkpoint = {
                    "artifact_hashes": (
                        {
                            "audit_record": _sha(audit_payload),
                            "source_receipt": _sha(receipt_payload),
                        }
                        if state == "TERMINAL"
                        else {}
                    ),
                    "execution_plan_sha256": plan_sha,
                    "previous_checkpoint_sha256": previous,
                    "state": state,
                    "volatile": {"fixture": sequence},
                    "work_id": work_id,
                }
                path = parent_root / (f"{sequence:04d}-attempt-0001-{state.lower()}.json")
                _write_json(path, checkpoint)
                checkpoints.append(path)
                previous = continuity._p2a_checkpoint_hash(checkpoint)
            self.parents[alias] = {
                "audit_path": audit_path,
                "audit_sha": _sha(audit_payload),
                "checkpoints": checkpoints,
                "execution_plan_file_sha": _sha(plan_payload),
                "execution_plan_path": plan_path,
                "execution_plan_sha": plan_sha,
                "receipt_path": receipt_path,
                "source_path": source_path,
                "source_sha": source_sha,
                "source_size": len(source),
                "terminal_sha": previous,
                "work_id": work_id,
            }

        for index, row in enumerate(continuity.SLOT_ROWS, start=1):
            slot, _slot_id, _comparison, alias, profile, limit = row
            parent = self.parents[alias]
            run_root = self.inputs / f"v1-{slot}"
            run_root.mkdir(mode=0o700)
            plan_base = {
                "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
                "algorithm_version": "0.2.0",
                "authority_policy": "REQUIRE_EXTERNAL_ANCHOR",
                "code_sha256": continuity.V1_RUNNER_SHA256,
                "environment": {
                    "implementation": "cpython",
                    "int_max_str_digits": 4300,
                    "version": [3, 11, 0],
                },
                "external_anchor_public_key_hex": "f" * 64,
                "input_binding": {
                    "audit_record_sha256": parent["audit_sha"],
                    "execution_plan_file_sha256": parent["execution_plan_file_sha"],
                    "execution_plan_sha256": parent["execution_plan_sha"],
                    "materializer_code_sha256": "a" * 64,
                    "materializer_id": "mvx-p2c-p2a-canonical-scene-materializer",
                    "materializer_version": "0.1.0",
                    "mesh_sha256": chr(96 + index) * 64,
                    "mode": "P2A_BOUND",
                    "p2a_terminal_checkpoint_sha256": parent["terminal_sha"],
                    "p2a_work_id": parent["work_id"],
                },
                "limits": {
                    "max_candidate_pairs": limit,
                    "max_coordinate_bits": 2048,
                    "max_runtime_seconds": 120,
                    "max_triangles": 1_000_000,
                    "max_vertices": 2_000_000,
                },
                "max_input_bytes": 536_870_912,
                "schema": "MVX-P2C-EXECUTION-PLAN",
                "schema_version": "0.1.0",
                "source_sha256": parent["source_sha"],
                "source_size_bytes": parent["source_size"],
            }
            work_id = continuity._p2c_hash(plan_base)
            plan = {**plan_base, "work_id": work_id}
            plan_path = run_root / "execution-plan.json"
            plan_payload = _write_json(plan_path, plan)
            plan_sha = continuity._p2c_hash(plan)
            attempt_key = Ed25519PrivateKey.generate()
            claim = {
                "attempt": 1,
                "plan_sha256": plan_sha,
                "previous_claim_sha256": None,
                "public_key_hex": (
                    attempt_key.public_key()
                    .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
                    .hex()
                ),
                "schema": "MVX-P2C-ATTEMPT-AUTHORITY-CLAIM",
                "schema_version": "0.1.0",
                "trust_model": "LOCAL_SINGLE_WRITER_IMMUTABLE_CLAIM_DIRECTORY",
                "work_id": work_id,
            }
            claim_path = run_root / "0001-attempt-0001-claim.json"
            _write_json(claim_path, claim, 0o400)
            claim_sha = continuity._p2c_hash(claim)
            unsigned_result = {
                "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
                "algorithm_version": "0.2.0",
                "plan_sha256": plan_sha,
                "schema": "MVX-P2C-EXACT-TRIANGLE-CONTACT",
                "schema_version": "0.2.0",
                "source_sha256": parent["source_sha"],
                "status": "EXACT_INTERSECTION_FREE_CANDIDATE",
                "work_id": work_id,
            }
            message = continuity._canonical_bytes(
                {
                    "attempt": 1,
                    "claim_sha256": claim_sha,
                    "result": unsigned_result,
                    "signature_domain": "MVX-P2C-RESULT-AUTHORIZATION-ED25519-1",
                },
                newline=True,
            )
            result = {
                **unsigned_result,
                "authorization": {
                    "attempt": 1,
                    "claim_sha256": claim_sha,
                    "signature_algorithm": "ED25519",
                    "signature_hex": attempt_key.sign(message).hex(),
                    "trust_model": "LOCAL_SINGLE_WRITER_IMMUTABLE_CLAIM_DIRECTORY",
                },
            }
            result_payload = _json_bytes(result)
            result_filename = f"attempt-0001-{_sha(result_payload)[:16]}.json"
            result_path = run_root / result_filename
            _write(result_path, result_payload)
            checkpoint_paths: list[Path] = []
            previous_checkpoint = None
            for sequence, state in enumerate(("PENDING", "RUNNING", "TERMINAL"), start=1):
                checkpoint = {
                    "attempt": 1,
                    "claim_sha256": claim_sha if state != "PENDING" else None,
                    "plan_sha256": plan_sha,
                    "previous_checkpoint_sha256": previous_checkpoint,
                    "result_filename": result_filename if state == "TERMINAL" else None,
                    "result_sha256": _sha(result_payload) if state == "TERMINAL" else None,
                    "state": state,
                    "work_id": work_id,
                }
                path = run_root / f"{sequence:04d}-{state.lower()}.json"
                _write_json(path, checkpoint)
                checkpoint_paths.append(path)
                previous_checkpoint = continuity._p2c_hash(checkpoint)
            self.executions.append(
                {
                    "authority_claims": [claim_path],
                    "checkpoints": checkpoint_paths,
                    "limit": limit,
                    "parent_alias": alias,
                    "plan_path": plan_path,
                    "plan_sha": _sha(plan_payload),
                    "profile": profile,
                    "result_path": result_path,
                    "result_sha": _sha(result_payload),
                    "slot": slot,
                    "terminal_sha": _sha(checkpoint_paths[-1].read_bytes()),
                    "work_id": work_id,
                }
            )

    def _v1_root(self) -> str:
        rows = [
            {
                "plan_sha256": row["plan_sha"],
                "result_sha256": row["result_sha"],
                "terminal_sha256": row["terminal_sha"],
            }
            for row in sorted(self.executions, key=lambda item: item["work_id"])
        ]
        return _sha(_json_bytes(rows))

    def _signer_manifest(self, challenge_hex: str) -> dict[str, object]:
        core = {
            "assurances": {
                "continuity_only": True,
                "drive_origin_proof": False,
                "encryption": False,
                "independent": False,
                "owner_controlled": True,
                "worm": False,
            },
            "challenge_hex": challenge_hex,
            "created_at": "2026-08-07T00:00:00Z",
            "public_key_ed25519_hex": self.public_key,
            "purpose": "P2C_RESTART_CONTINUITY_ONLY_NEVER_SOLID_VALIDITY",
            "schema": "MVX-P2C-OWNER-PERSISTENT-SIGNER-MANIFEST",
            "schema_version": "0.1.0",
            "signature_algorithm": "ED25519",
            "signer_id": f"mvx-p2c-owner-{self.public_key[:16]}",
            "trust_model": "OWNER_CONTROLLED_PERSISTENT_CONTINUITY_ONLY",
        }
        message = continuity._canonical_bytes(
            {
                "manifest": core,
                "signature_domain": "MVX-P2C-OWNER-PERSISTENT-SIGNER-MANIFEST-ED25519-1",
            }
        )
        return {**core, "challenge_signature_hex": self.owner_key.sign(message).hex()}

    def _make_repository(self) -> None:
        preregistration = {
            "campaign": {
                "campaign_id": continuity.CAMPAIGN_ID,
                "campaign_version": continuity.CAMPAIGN_VERSION,
                "status": "FROZEN_BEFORE_EXECUTION",
            },
            "limits_common": {
                "max_coordinate_bits": 2048,
                "max_input_bytes": 536_870_912,
                "max_runtime_seconds": 120,
                "max_triangles": 1_000_000,
                "max_vertices": 2_000_000,
            },
            "private_parent_scope": {
                "execution_count": 4,
                "unique_p2a_parent_count": 3,
                "v1_terminal_evidence_root_sha256": self.v1_root,
            },
            "preexecution_freeze": {
                "private_drive_copy_is_not_publication": True,
                "public_github_commit_required_before_plan_creation": True,
            },
            "version_domains": {
                "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
                "algorithm_version": "0.3.0",
                "materializer_id": "mvx-p2c-p2a-canonical-scene-materializer",
                "materializer_version": "0.2.0",
                "result_schema_version": "0.3.0",
            },
        }
        disposition = {
            "authority": {"campaign_disposition": "UNANCHORED_DIAGNOSTIC"},
            "disposition": {"reuse_for_v2": "FORBIDDEN", "solid_certification_count": 0},
            "private_evidence": {"terminal_evidence_root_sha256": self.v1_root},
        }
        binding_payloads: dict[str, tuple[str, bytes]] = {
            "preregistration": ("docs/preregistration.json", _json_bytes(preregistration)),
            "projection_contexts": (
                "docs/projection-contexts.json",
                _json_bytes({"fixture": True}),
            ),
            "v1_disposition": ("docs/disposition.json", _json_bytes(disposition)),
            "runner": ("scripts/runner.py", b"RUNNER-V2\n"),
            "runner_test": ("tests/test_runner.py", b"TEST-RUNNER\n"),
            "signer": ("scripts/signer.py", b"SIGNER\n"),
            "signer_test": ("tests/test_signer.py", b"TEST-SIGNER\n"),
            "projector": ("scripts/projector.py", b"PROJECTOR\n"),
            "projector_test": ("tests/test_projector.py", b"TEST-PROJECTOR\n"),
            "continuity": ("scripts/continuity.py", b"CONTINUITY\n"),
            "continuity_test": ("tests/test_continuity.py", b"TEST-CONTINUITY\n"),
            "runtime_lock": ("uv.lock", b"RUNTIME-LOCK\n"),
        }
        self.binding_paths: dict[str, str] = {}
        for name, (relative, payload) in binding_payloads.items():
            _write(self.repository / relative, payload, 0o644)
            self.binding_paths[name] = relative
        _git(self.repository, "init", "-q")
        _git(self.repository, "config", "user.email", "fixture@example.invalid")
        _git(self.repository, "config", "user.name", "Fixture")
        _git(self.repository, "add", ".")
        _git(self.repository, "commit", "-qm", "fixture-code")
        challenge_commit = _git(self.repository, "rev-parse", "HEAD")
        challenge_tree = _git(self.repository, "rev-parse", "HEAD^{tree}")
        tests = [
            {
                "binding": name,
                "raw_bytes_sha256": _sha(binding_payloads[name][1]),
            }
            for name in continuity.TEST_BINDING_NAMES
        ]
        runtime = continuity._runtime_freeze(_sha(binding_payloads["runtime_lock"][1]))
        challenge = {
            "campaign_id": continuity.CAMPAIGN_ID,
            "code_commit_sha1": challenge_commit,
            "git_tree_sha1": challenge_tree,
            "preregistration_sha256": _sha(binding_payloads["preregistration"][1]),
            "runner_sha256": _sha(binding_payloads["runner"][1]),
            "runtime_sha256": continuity._p2c_hash(runtime),
            "schema": "MVX-P2C-V2-PERSISTENT-SIGNER-CHALLENGE",
            "schema_version": continuity.SCHEMA_VERSION,
            "tests_sha256": continuity._p2c_hash(tests),
        }
        challenge_payload = _json_bytes(challenge)
        signer_payload = _json_bytes(
            self._signer_manifest(continuity._p2c_hash(challenge)), newline=False
        )
        challenge_path = "docs/signer-challenge.json"
        manifest_path = "docs/signer-manifest.json"
        _write(self.repository / challenge_path, challenge_payload, 0o644)
        _write(self.repository / manifest_path, signer_payload, 0o644)
        self.binding_paths["signer_challenge"] = challenge_path
        self.binding_paths["signer_manifest"] = manifest_path
        _git(self.repository, "add", ".")
        _git(self.repository, "commit", "-qm", "fixture-signer")
        self.commit = _git(self.repository, "rev-parse", "HEAD")
        self.tree = _git(self.repository, "rev-parse", "HEAD^{tree}")

    def _make_spec(self) -> None:
        parents = []
        for alias in continuity.PARENT_ALIASES:
            parent = self.parents[alias]
            parents.append(
                {
                    "alias": alias,
                    "p2a_audit_record": str(parent["audit_path"]),
                    "p2a_checkpoints": [str(path) for path in parent["checkpoints"]],
                    "p2a_execution_plan": str(parent["execution_plan_path"]),
                    "p2a_source_receipt": str(parent["receipt_path"]),
                    "p2a_work_id": parent["work_id"],
                    "source_glb": str(parent["source_path"]),
                }
            )
        executions = []
        for row in self.executions:
            executions.append(
                {
                    "max_candidate_pairs": row["limit"],
                    "parent_alias": row["parent_alias"],
                    "profile_id": row["profile"],
                    "slot": row["slot"],
                    "v1_authority_claims": [str(path) for path in row["authority_claims"]],
                    "v1_checkpoints": [str(path) for path in row["checkpoints"]],
                    "v1_execution_plan": str(row["plan_path"]),
                    "v1_result": str(row["result_path"]),
                    "v1_work_id": row["work_id"],
                }
            )
        spec = {
            "code": {
                "bindings": self.binding_paths,
                "commit_sha1": self.commit,
                "tree_sha1": self.tree,
            },
            "executions": executions,
            "parents": parents,
            "schema": continuity.INPUT_SCHEMA,
            "schema_version": continuity.SCHEMA_VERSION,
        }
        _write_json(self.spec_path, spec)

    def make_v2_plans(self, bundle: Path) -> dict[str, Path]:
        files, _ = continuity._read_bundle(bundle)
        manifest = continuity._bundle_json(files, "manifest.json")
        preexecution = manifest["code"]["preexecution_bindings"]
        plans: dict[str, Path] = {}
        for slot, _slot_id, _comparison, alias, _profile, limit in continuity.SLOT_ROWS:
            parent = next(row for row in manifest["parents"] if row["alias"] == alias)
            plan_base = {
                "algorithm_id": "mvx-p2c-exact-binary64-triangle-contact",
                "algorithm_version": "0.3.0",
                "authority_policy": "REQUIRE_EXTERNAL_ANCHOR",
                "code_sha256": preexecution["runner_sha256"],
                "environment": preexecution["runtime"]["runner_environment"],
                "external_anchor_public_key_hex": self.public_key,
                "input_binding": {
                    "audit_record_sha256": parent["p2a"]["audit_record"]["raw_bytes_sha256"],
                    "execution_plan_file_sha256": parent["p2a"]["execution_plan"][
                        "raw_bytes_sha256"
                    ],
                    "execution_plan_sha256": parent["p2a"]["execution_plan"][
                        "typed_canonical_sha256"
                    ],
                    "materializer_code_sha256": "d" * 64,
                    "materializer_id": "mvx-p2c-p2a-canonical-scene-materializer",
                    "materializer_version": "0.2.0",
                    "mesh_sha256": ("e" if slot != "04" else "f") * 64,
                    "mode": "P2A_BOUND",
                    "p2a_terminal_checkpoint_sha256": parent["p2a"]["checkpoint_chain"][-1][
                        "typed_canonical_sha256"
                    ],
                    "p2a_work_id": parent["p2a"]["work_id"],
                },
                "limits": {
                    "max_candidate_pairs": limit,
                    "max_coordinate_bits": 2048,
                    "max_runtime_seconds": 120,
                    "max_triangles": 1_000_000,
                    "max_vertices": 2_000_000,
                },
                "max_input_bytes": 536_870_912,
                "schema": "MVX-P2C-EXECUTION-PLAN",
                "schema_version": "0.1.0",
                "source_sha256": parent["glb"]["raw_bytes_sha256"],
                "source_size_bytes": parent["glb"]["size_bytes"],
            }
            plan = {**plan_base, "work_id": continuity._p2c_hash(plan_base)}
            path = self.root / "v2-plans" / slot / "execution-plan.json"
            _write_json(path, plan)
            plans[slot] = path
        return plans


class P2cV2ContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.original_root = continuity.V1_ROOT
        # Create evidence first, then bind the synthetic raw-byte root everywhere.
        self.fixture = ContinuityFixture.__new__(ContinuityFixture)
        self.fixture.root = self.root
        self.fixture.repository = self.root / "repository"
        self.fixture.inputs = self.root / "inputs"
        self.fixture.key_path = self.root / "owner.ed25519-private"
        self.fixture.spec_path = self.root / "input-spec.json"
        self.fixture.repository.mkdir(mode=0o700)
        self.fixture.inputs.mkdir(mode=0o700)
        self.fixture.owner_key = Ed25519PrivateKey.generate()
        raw = self.fixture.owner_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        _write(self.fixture.key_path, raw, 0o400)
        self.fixture.public_key = (
            self.fixture.owner_key.public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
        )
        self.fixture.parents = {}
        self.fixture.executions = []
        self.fixture._make_private_evidence()
        self.fixture.v1_root = self.fixture._v1_root()
        continuity.V1_ROOT = self.fixture.v1_root
        self.fixture._make_repository()
        self.fixture._make_spec()

    def tearDown(self) -> None:
        continuity.V1_ROOT = self.original_root
        self.temporary.cleanup()

    def _build(self, name: str = "bundle.tar") -> Path:
        output = self.root / name
        result = continuity.build_bundle(
            self.fixture.spec_path,
            self.fixture.repository,
            output,
            signing_key=self.fixture.key_path,
            private_root=self.root,
        )
        self.assertEqual(result, {"action": "BUNDLE_CREATED"})
        return output

    def test_bundle_is_deterministic_private_and_cleanly_restorable(self) -> None:
        first = self._build("first.tar")
        second = self._build("second.tar")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)
        self.assertEqual(
            continuity.validate_bundle(first, repository=self.fixture.repository),
            {"action": "BUNDLE_VALID"},
        )
        destination = self.root / "restored"
        self.assertEqual(
            continuity.restore_test(
                first,
                destination,
                repository=self.fixture.repository,
                private_root=self.root,
            ),
            {"action": "RESTORE_VALID"},
        )
        for slot, *_ in continuity.SLOT_ROWS:
            claim = next((destination / f"executions/{slot}/v1/authority-claims").iterdir())
            self.assertEqual(stat.S_IMODE(claim.stat().st_mode), 0o400)
            for empty in ("authority-secrets", "staging"):
                directory = destination / f"executions/{slot}/v1/{empty}"
                self.assertTrue(directory.is_dir())
                self.assertEqual(list(directory.iterdir()), [])
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        files, _ = continuity._read_bundle(first)
        manifest_text = files["manifest.json"].decode()
        self.assertNotIn(str(self.root), manifest_text)
        self.assertNotIn('"source_title"', manifest_text)
        self.assertNotIn('"source_uid"', manifest_text)
        self.assertNotIn('"v2_work_id"', manifest_text)

    def test_rejects_forged_v1_result_signature_before_publication(self) -> None:
        result_path = self.fixture.executions[0]["result_path"]
        result = json.loads(result_path.read_bytes())
        result["authorization"]["signature_hex"] = "0" * 128
        forged_payload = _json_bytes(result)
        row = self.fixture.executions[0]
        parent = self.fixture.parents[row["parent_alias"]]
        checkpoints = [json.loads(path.read_bytes()) for path in row["checkpoints"]]
        forged_name = f"attempt-0001-{_sha(forged_payload)[:16]}.json"
        checkpoints[-1]["result_filename"] = forged_name
        checkpoints[-1]["result_sha256"] = _sha(forged_payload)
        with self.assertRaisesRegex(continuity.ContinuityError, "V1_RESULT_AUTHORIZATION"):
            continuity._validate_v1_execution(
                row["work_id"],
                {
                    "p2a_execution_plan_sha256": parent["execution_plan_sha"],
                    "p2a_terminal_checkpoint_sha256": parent["terminal_sha"],
                    "p2a_work_id": parent["work_id"],
                    "source_sha256": parent["source_sha"],
                },
                row["limit"],
                json.loads(row["plan_path"].read_bytes()),
                result,
                forged_payload,
                checkpoints,
                [json.loads(path.read_bytes()) for path in row["authority_claims"]],
                forged_name,
            )
        _write(result_path, forged_payload)
        output = self.root / "forged.tar"
        with self.assertRaises(continuity.ContinuityError):
            continuity.build_bundle(
                self.fixture.spec_path,
                self.fixture.repository,
                output,
                signing_key=self.fixture.key_path,
                private_root=self.root,
            )
        self.assertFalse(output.exists())

    def test_freeze_emits_exact_projector_shape_and_bundle_bound_signature(self) -> None:
        bundle = self._build()
        plans = self.fixture.make_v2_plans(bundle)
        manifest_path = self.root / "freeze" / "continuity.json"
        authentication_path = self.root / "freeze" / "authentication.json"
        result = continuity.freeze_continuity(
            bundle,
            plans,
            manifest_path,
            authentication_path,
            signing_key=self.fixture.key_path,
            private_root=self.root,
        )
        self.assertEqual(result, {"action": "CONTINUITY_FROZEN"})
        self.assertEqual(
            continuity.validate_continuity_from_bundle(bundle, manifest_path, authentication_path),
            {"action": "CONTINUITY_VALID"},
        )
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(
            set(manifest),
            {
                "campaign_id",
                "persistent_signer_public_key_ed25519_hex",
                "preregistration_value_sha256",
                "schema",
                "schema_version",
                "slots",
                "status",
                "v1_terminal_evidence_root_sha256",
            },
        )
        self.assertEqual(manifest["schema"], continuity.CONTINUITY_SCHEMA)
        self.assertEqual(
            manifest["persistent_signer_public_key_ed25519_hex"], self.fixture.public_key
        )
        self.assertEqual(len(manifest["slots"]), 4)
        preregistration = json.loads(
            (self.fixture.repository / self.fixture.binding_paths["preregistration"]).read_bytes()
        )
        with mock.patch.object(scientific_projection, "V1_ROOT", self.fixture.v1_root):
            self.assertEqual(
                scientific_projection.validate_continuity_manifest(manifest, preregistration),
                manifest,
            )

        mismatched_signer = copy.deepcopy(manifest)
        mismatched_signer["persistent_signer_public_key_ed25519_hex"] = "0" * 64
        with self.assertRaisesRegex(continuity.ContinuityError, "FINAL_CONTINUITY_IDENTITY"):
            continuity._validate_final_continuity(
                mismatched_signer, preregistration, self.fixture.public_key
            )

        compromised_manifest = copy.deepcopy(
            json.loads(
                (
                    self.fixture.repository / self.fixture.binding_paths["signer_manifest"]
                ).read_bytes()
            )
        )
        compromised_manifest["public_key_ed25519_hex"] = continuity.COMPROMISED_V2_SIGNER_PUBLIC_KEY
        compromised_manifest["signer_id"] = (
            f"mvx-p2c-owner-{continuity.COMPROMISED_V2_SIGNER_PUBLIC_KEY[:16]}"
        )
        with self.assertRaisesRegex(continuity.ContinuityError, "SIGNER_PUBLIC_KEY_COMPROMISED"):
            continuity._signer_public_key(compromised_manifest)
        authentication = json.loads(authentication_path.read_bytes())["authentication"]
        self.assertEqual(
            authentication["context"]["prefreeze_bundle_raw_bytes_sha256"],
            _sha(bundle.read_bytes()),
        )
        self.assertIsInstance(authentication["signature_hex"], str)
        self.assertEqual(len(authentication["signature_hex"]), 128)

    def test_cli_validation_output_is_generic(self) -> None:
        bundle = self._build()
        output = io.StringIO()
        error = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = continuity.main(["validate", "--bundle", str(bundle)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), {"action": "BUNDLE_VALID"})
        emitted = output.getvalue() + error.getvalue()
        self.assertNotIn(str(bundle), emitted)
        self.assertNotIn(self.fixture.public_key, emitted)
        self.assertNotIn(self.fixture.key_path.read_bytes().hex(), emitted)

    def test_extra_empty_tar_directory_is_rejected(self) -> None:
        bundle = self._build()
        source = io.BytesIO(bundle.read_bytes())
        target = io.BytesIO()
        with (
            tarfile.open(fileobj=source, mode="r:") as reader,
            tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as writer,
        ):
            for member in reader:
                extracted = reader.extractfile(member) if member.isfile() else None
                writer.addfile(member, extracted)
            extra = tarfile.TarInfo("unexpected-empty/")
            extra.type = tarfile.DIRTYPE
            extra.mode = 0o700
            extra.uid = 0
            extra.gid = 0
            extra.mtime = 0
            writer.addfile(extra)
        tampered = self.root / "tampered.tar"
        _write(tampered, target.getvalue())
        with self.assertRaisesRegex(continuity.ContinuityError, "BUNDLE_DIRECTORY_SET"):
            continuity.validate_bundle(tampered)
