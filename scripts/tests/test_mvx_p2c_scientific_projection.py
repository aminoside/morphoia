from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCRIPT = Path(__file__).resolve().parents[1] / "mvx_p2c_scientific_projection.py"
SPEC = importlib.util.spec_from_file_location("mvx_p2c_scientific_projection", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
projection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = projection
SPEC.loader.exec_module(projection)

PREREGISTRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/mvx/validation/p2c/preregistration/pilot3-2026-08-06-v2/preregistration.json"
)
CONTEXTS_PATH = PREREGISTRATION_PATH.with_name("projection-contexts.json")


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def fraction(value: int) -> dict[str, str]:
    return {"denominator": "1", "numerator": str(value)}


def common_limits(max_candidate_pairs: int) -> dict[str, int]:
    return {
        "max_candidate_pairs": max_candidate_pairs,
        "max_coordinate_bits": 2048,
        "max_runtime_seconds": 120,
        "max_triangles": 1_000_000,
        "max_vertices": 2_000_000,
    }


def free_scientific(max_candidate_pairs: int) -> dict[str, object]:
    return {
        "numeric_model": projection.NUMERIC_MODEL,
        "limits": common_limits(max_candidate_pairs),
        "mesh": {"triangle_count": 4, "vertex_count": 6},
        "broadphase": {
            "active_pair_comparisons": 27,
            "allowed_topological_adjacencies": 6,
            "bbox_candidate_pairs": 6,
            "exact_pairs_examined": 6,
        },
        "contact": None,
        "diagnostic": "ALL_CONSERVATIVE_BROADPHASE_PAIRS_EXHAUSTED",
        "error_code": None,
        "status": "EXACT_INTERSECTION_FREE_CANDIDATE",
    }


def polygon_scientific(max_candidate_pairs: int) -> dict[str, object]:
    return {
        "numeric_model": projection.NUMERIC_MODEL,
        "limits": common_limits(max_candidate_pairs),
        "mesh": {"triangle_count": 2, "vertex_count": 6},
        "broadphase": {
            "active_pair_comparisons": 1,
            "allowed_topological_adjacencies": 0,
            "bbox_candidate_pairs": 1,
            "exact_pairs_examined": 1,
        },
        "contact": {
            "dimension": 2,
            "kind": "POLYGON",
            "points": [
                [fraction(0), fraction(0), fraction(0)],
                [fraction(1), fraction(0), fraction(0)],
                [fraction(0), fraction(1), fraction(0)],
            ],
            "shared_topological_vertices": [],
            "triangle_pair": [0, 1],
        },
        "diagnostic": "EXACT_DISALLOWED_CONTACT_WITNESS",
        "error_code": "EXACT_DISALLOWED_CONTACT",
        "status": "EXACT_CONTACT_FOUND",
    }


class EvidenceFactory:
    def __init__(self) -> None:
        self.preregistration = projection.load_json(PREREGISTRATION_PATH)
        self.contexts = projection.load_json(CONTEXTS_PATH)
        self.slots = self.preregistration["execution_slots"]
        self.parents = {
            "PARENT_A": {
                "source_sha256": digest("parent-a-source"),
                "p2a_execution_plan_sha256": digest("parent-a-p2a-plan"),
                "p2a_terminal_checkpoint_sha256": digest("parent-a-p2a-terminal"),
                "p2a_work_id": digest("parent-a-p2a-work"),
            },
            "PARENT_B": {
                "source_sha256": digest("parent-b-source"),
                "p2a_execution_plan_sha256": digest("parent-b-p2a-plan"),
                "p2a_terminal_checkpoint_sha256": digest("parent-b-p2a-terminal"),
                "p2a_work_id": digest("parent-b-p2a-work"),
            },
            "PARENT_C": {
                "source_sha256": digest("parent-c-source"),
                "p2a_execution_plan_sha256": digest("parent-c-p2a-plan"),
                "p2a_terminal_checkpoint_sha256": digest("parent-c-p2a-terminal"),
                "p2a_work_id": digest("parent-c-p2a-work"),
            },
        }

    def implementation(self, campaign_key: str) -> dict[str, object]:
        return projection._campaign_implementation(self.preregistration, campaign_key)

    def plan(self, campaign_key: str, slot_index: int) -> dict[str, object]:
        slot = self.slots[slot_index]
        parent = self.parents[slot["private_parent_alias"]]
        implementation = self.implementation(campaign_key)
        binding = {
            "audit_record_sha256": digest(f"{slot_index}-audit"),
            "execution_plan_file_sha256": digest(f"{slot_index}-p2a-plan-file"),
            "execution_plan_sha256": parent["p2a_execution_plan_sha256"],
            "materializer_code_sha256": digest(f"{campaign_key}-materializer-code"),
            "materializer_id": implementation["materializer_id"],
            "materializer_version": implementation["materializer_version"],
            "mesh_sha256": digest(f"{campaign_key}-{slot_index}-mesh"),
            "mode": "P2A_BOUND",
            "p2a_terminal_checkpoint_sha256": parent["p2a_terminal_checkpoint_sha256"],
            "p2a_work_id": parent["p2a_work_id"],
        }
        base = {
            "algorithm_id": implementation["algorithm_id"],
            "algorithm_version": implementation["algorithm_version"],
            "authority_policy": "REQUIRE_EXTERNAL_ANCHOR",
            "code_sha256": (
                projection.V1_RUNNER_SHA256
                if campaign_key == "v1"
                else hashlib.sha256(projection.RUNNER_PATH.read_bytes()).hexdigest()
            ),
            "environment": {
                "implementation": "cpython",
                "int_max_str_digits": 4300,
                "version": [3, 12, 13],
            },
            "external_anchor_public_key_hex": digest("persistent-public-key"),
            "input_binding": binding,
            "limits": common_limits(slot["max_candidate_pairs"]),
            "max_input_bytes": 536_870_912,
            "schema": "MVX-P2C-EXECUTION-PLAN",
            "schema_version": "0.1.0",
            "source_sha256": parent["source_sha256"],
            "source_size_bytes": 12_345 + slot_index,
        }
        return {**base, "work_id": projection.sha256_value(base)}

    def continuity(self, plans: dict[tuple[str, int], dict[str, object]]) -> dict[str, object]:
        rows = []
        for slot_index, slot in enumerate(self.slots):
            parent = self.parents[slot["private_parent_alias"]]
            row: dict[str, object] = {
                "slot_id": slot["slot_id"],
                "comparison_slot": slot["comparison_slot"],
                "private_parent_alias": slot["private_parent_alias"],
                "profile_id": slot["profile_id"],
                "max_candidate_pairs": slot["max_candidate_pairs"],
            }
            for campaign_key in ("v1", "v2"):
                plan = plans.get((campaign_key, slot_index))
                row[campaign_key] = {
                    "execution_plan_sha256": (
                        projection.sha256_value(plan)
                        if plan is not None
                        else digest(f"{campaign_key}-{slot_index}-plan")
                    ),
                    "source_sha256": parent["source_sha256"],
                    "p2a_execution_plan_sha256": parent["p2a_execution_plan_sha256"],
                    "p2a_terminal_checkpoint_sha256": parent["p2a_terminal_checkpoint_sha256"],
                    "p2a_work_id": parent["p2a_work_id"],
                    "work_id": (
                        plan["work_id"]
                        if plan is not None
                        else digest(f"{campaign_key}-{slot_index}-work")
                    ),
                }
            rows.append(row)
        return {
            "schema": projection.CONTINUITY_SCHEMA,
            "schema_version": projection.CONTINUITY_SCHEMA_VERSION,
            "campaign_id": projection.CAMPAIGN_ID,
            "status": "FROZEN_BEFORE_FIRST_V2_CHILD",
            "persistent_signer_public_key_ed25519_hex": digest("persistent-public-key"),
            "preregistration_value_sha256": projection.sha256_value(self.preregistration),
            "v1_terminal_evidence_root_sha256": projection.V1_ROOT,
            "slots": rows,
        }

    def result_evidence(
        self,
        campaign_key: str,
        plan: dict[str, object],
        scientific: dict[str, object],
    ) -> tuple[bytes, dict[str, object], dict[str, object], dict[str, object]]:
        implementation = self.implementation(campaign_key)
        private_key = Ed25519PrivateKey.generate()
        public_key_hex = (
            private_key.public_key()
            .public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
            .hex()
        )
        plan_sha256 = projection.sha256_value(plan)
        claim = {
            "attempt": 1,
            "plan_sha256": plan_sha256,
            "previous_claim_sha256": None,
            "public_key_hex": public_key_hex,
            "schema": "MVX-P2C-ATTEMPT-AUTHORITY-CLAIM",
            "schema_version": "0.1.0",
            "trust_model": projection.AUTHORITY_TRUST_MODEL,
            "work_id": plan["work_id"],
        }
        claim_sha256 = projection.sha256_value(claim)
        unsigned = {
            "algorithm_id": implementation["algorithm_id"],
            "algorithm_version": implementation["algorithm_version"],
            **scientific,
            "input_binding": plan["input_binding"],
            "plan_sha256": plan_sha256,
            "schema": implementation["result_schema"],
            "schema_version": implementation["result_schema_version"],
            "source_sha256": plan["source_sha256"],
            "source_size_bytes": plan["source_size_bytes"],
            "work_id": plan["work_id"],
        }
        message = projection.canonical_bytes(
            {
                "attempt": 1,
                "claim_sha256": claim_sha256,
                "result": unsigned,
                "signature_domain": "MVX-P2C-RESULT-AUTHORIZATION-ED25519-1",
            }
        )
        result = {
            **unsigned,
            "authorization": {
                "attempt": 1,
                "claim_sha256": claim_sha256,
                "signature_algorithm": "ED25519",
                "signature_hex": private_key.sign(message).hex(),
                "trust_model": projection.AUTHORITY_TRUST_MODEL,
            },
        }
        result_bytes = projection.canonical_bytes(result)
        result_sha256 = hashlib.sha256(result_bytes).hexdigest()
        terminal = {
            "attempt": 1,
            "claim_sha256": claim_sha256,
            "plan_sha256": plan_sha256,
            "previous_checkpoint_sha256": digest("running-checkpoint"),
            "result_filename": f"attempt-0001-{result_sha256[:16]}.json",
            "result_sha256": result_sha256,
            "state": "TERMINAL",
            "work_id": plan["work_id"],
        }
        return result_bytes, result, terminal, claim

    def project(
        self,
        campaign_key: str,
        slot_index: int,
        scientific: dict[str, object] | None = None,
        paired_plan: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        plan = self.plan(campaign_key, slot_index)
        plans = {(campaign_key, slot_index): plan}
        other = "v1" if campaign_key == "v2" else "v2"
        if paired_plan is not None:
            plans[(other, slot_index)] = paired_plan
        continuity = self.continuity(plans)
        result_bytes, result, terminal, claim = self.result_evidence(
            campaign_key,
            plan,
            scientific or free_scientific(self.slots[slot_index]["max_candidate_pairs"]),
        )
        projected = projection.project_bound_result(
            campaign_key=campaign_key,
            slot_id=self.slots[slot_index]["slot_id"],
            preregistration=self.preregistration,
            context_set=self.contexts,
            continuity_manifest=continuity,
            execution_plan=plan,
            terminal_checkpoint=terminal,
            authority_claim=claim,
            result_bytes=result_bytes,
            result=result,
        )
        return projected, continuity, plan


class PreregistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = EvidenceFactory()

    def test_frozen_public_documents_validate(self) -> None:
        prereg = projection.validate_preregistration(self.factory.preregistration)
        projection.validate_contexts(self.factory.contexts, prereg)
        self.assertEqual(prereg["campaign"]["status"], "FROZEN_BEFORE_EXECUTION")
        self.assertEqual(prereg["historical_v1"]["algorithm_version"], "0.2.0")

    def test_every_previously_open_critical_clause_is_closed(self) -> None:
        mutations = [
            lambda value: value["private_parent_scope"].__setitem__(
                "v1_terminal_evidence_root_sha256", "0" * 64
            ),
            lambda value: value["private_parent_scope"].__setitem__(
                "private_continuity_manifest_required_before_execution", False
            ),
            lambda value: value["preexecution_freeze"].__setitem__("required", False),
            lambda value: value["preexecution_freeze"].__setitem__(
                "must_precede_first_child_execution", False
            ),
            lambda value: value["preexecution_freeze"].__setitem__(
                "public_github_commit_required_before_plan_creation", False
            ),
            lambda value: value["work_identity"].__setitem__(
                "v1_result_or_checkpoint_reuse", "ALLOWED"
            ),
            lambda value: value["scientific_projection"].__setitem__(
                "projection_visibility", "PUBLIC"
            ),
            lambda value: value["authority"].__setitem__("private_key_in_repository", True),
            lambda value: value["materialization_contract"].__setitem__(
                "vertex_reorder", "ALLOWED"
            ),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(self.factory.preregistration)
                mutation(changed)
                with self.assertRaises(projection.ProjectionError):
                    projection.validate_preregistration(changed)

    def test_continuity_manifest_rejects_parent_or_slot_substitution(self) -> None:
        plans = {("v2", 0): self.factory.plan("v2", 0)}
        manifest = self.factory.continuity(plans)
        projection.validate_continuity_manifest(manifest, self.factory.preregistration)

        changed = copy.deepcopy(manifest)
        changed["slots"][0]["v2"]["source_sha256"] = digest("substituted-parent")
        with self.assertRaisesRegex(projection.ProjectionError, "same sealed P2a parent"):
            projection.validate_continuity_manifest(changed, self.factory.preregistration)

        changed = copy.deepcopy(manifest)
        changed["slots"][0]["comparison_slot"] = "PARENT_C_DEFAULT"
        with self.assertRaisesRegex(projection.ProjectionError, "differs from preregistration"):
            projection.validate_continuity_manifest(changed, self.factory.preregistration)


class ScientificProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = EvidenceFactory()

    def test_runner_polygon_kind_is_valid_and_private_payload_is_exact(self) -> None:
        projected, _, _ = self.factory.project("v2", 0, polygon_scientific(2_000_000))
        projection.validate_projection(projected)
        self.assertEqual(projected["scientific_payload"]["contact"]["kind"], "POLYGON")
        self.assertEqual(projected["campaign"]["campaign_version"], "2.0.0")

    def test_slot_name_cannot_reassign_a_plan_to_another_parent(self) -> None:
        plan = self.factory.plan("v2", 0)
        continuity = self.factory.continuity({("v2", 0): plan})
        result_bytes, result, terminal, claim = self.factory.result_evidence(
            "v2", plan, free_scientific(2_000_000)
        )
        with self.assertRaises(projection.ProjectionError):
            projection.project_bound_result(
                campaign_key="v2",
                slot_id="P2C-V2-03",
                preregistration=self.factory.preregistration,
                context_set=self.factory.contexts,
                continuity_manifest=continuity,
                execution_plan=plan,
                terminal_checkpoint=terminal,
                authority_claim=claim,
                result_bytes=result_bytes,
                result=result,
            )

    def test_result_terminal_and_signature_are_all_required(self) -> None:
        plan = self.factory.plan("v2", 0)
        continuity = self.factory.continuity({("v2", 0): plan})
        _, result, terminal, claim = self.factory.result_evidence(
            "v2", plan, free_scientific(2_000_000)
        )
        tampered = copy.deepcopy(result)
        tampered["authorization"]["signature_hex"] = "0" * 128
        tampered_bytes = projection.canonical_bytes(tampered)
        tampered_sha256 = hashlib.sha256(tampered_bytes).hexdigest()
        terminal["result_sha256"] = tampered_sha256
        terminal["result_filename"] = f"attempt-0001-{tampered_sha256[:16]}.json"
        with self.assertRaisesRegex(projection.ProjectionError, "signature is invalid"):
            projection.project_bound_result(
                campaign_key="v2",
                slot_id="P2C-V2-01",
                preregistration=self.factory.preregistration,
                context_set=self.factory.contexts,
                continuity_manifest=continuity,
                execution_plan=plan,
                terminal_checkpoint=terminal,
                authority_claim=claim,
                result_bytes=tampered_bytes,
                result=tampered,
            )

    def test_real_historical_mode_validates_v1_identity_and_compares_to_v2(self) -> None:
        v1_plan = self.factory.plan("v1", 0)
        v2_plan = self.factory.plan("v2", 0)
        continuity = self.factory.continuity({("v1", 0): v1_plan, ("v2", 0): v2_plan})
        v1_bytes, v1_result, v1_terminal, v1_claim = self.factory.result_evidence(
            "v1", v1_plan, free_scientific(2_000_000)
        )
        v2_bytes, v2_result, v2_terminal, v2_claim = self.factory.result_evidence(
            "v2", v2_plan, polygon_scientific(2_000_000)
        )
        v1 = projection.project_bound_result(
            campaign_key="v1",
            slot_id="P2C-V2-01",
            preregistration=self.factory.preregistration,
            context_set=self.factory.contexts,
            continuity_manifest=continuity,
            execution_plan=v1_plan,
            terminal_checkpoint=v1_terminal,
            authority_claim=v1_claim,
            result_bytes=v1_bytes,
            result=v1_result,
        )
        v2 = projection.project_bound_result(
            campaign_key="v2",
            slot_id="P2C-V2-01",
            preregistration=self.factory.preregistration,
            context_set=self.factory.contexts,
            continuity_manifest=continuity,
            execution_plan=v2_plan,
            terminal_checkpoint=v2_terminal,
            authority_claim=v2_claim,
            result_bytes=v2_bytes,
            result=v2_result,
        )
        comparison = projection.compare_projections(v1, v2)
        self.assertEqual(v1["campaign"]["campaign_version"], "v1")
        self.assertEqual(v1["implementation"]["algorithm_version"], "0.2.0")
        self.assertFalse(comparison["scientific_payload_equal"])
        self.assertIn("$.status", comparison["changed_paths"])

    def test_compare_accepts_two_v2_projections_only_for_repeatability(self) -> None:
        first, _, _ = self.factory.project("v2", 0)
        comparison = projection.compare_projections(first, copy.deepcopy(first))
        self.assertEqual(comparison["comparison_kind"], "V2_REPEATABILITY")
        self.assertTrue(comparison["scientific_payload_equal"])


class PrivateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = EvidenceFactory()
        self.temporary = tempfile.TemporaryDirectory(dir=projection.PRIVATE_ROOT)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, value: object, mode: int = 0o600) -> Path:
        path = self.root / name
        path.write_bytes(projection.canonical_bytes(value))
        path.chmod(mode)
        return path

    def arguments(self, campaign_key: str, output: Path) -> list[str]:
        plan = self.factory.plan(campaign_key, 0)
        continuity = self.factory.continuity({(campaign_key, 0): plan})
        result_bytes, _, terminal, claim = self.factory.result_evidence(
            campaign_key, plan, free_scientific(2_000_000)
        )
        result_path = self.root / f"{campaign_key}-result.json"
        result_path.write_bytes(result_bytes)
        result_path.chmod(0o600)
        command = "project" if campaign_key == "v2" else "project-historical-v1"
        return [
            command,
            "--result",
            str(result_path),
            "--execution-plan",
            str(self.write(f"{campaign_key}-plan.json", plan)),
            "--terminal-checkpoint",
            str(self.write(f"{campaign_key}-terminal.json", terminal)),
            "--authority-claim",
            str(self.write(f"{campaign_key}-claim.json", claim, 0o400)),
            "--continuity-manifest",
            str(self.write(f"{campaign_key}-continuity.json", continuity)),
            "--slot-id",
            "P2C-V2-01",
            "--output",
            str(output),
        ]

    def test_project_cli_emits_only_generic_action_and_publishes_0600_once(self) -> None:
        output = self.root / "projection.json"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = projection.main(self.arguments("v2", output))
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue().strip(), "P2C_PRIVATE_V2_PROJECTION_WRITTEN")
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        private_payload = output.read_text(encoding="utf-8")
        self.assertNotIn(private_payload, stdout.getvalue())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = projection.main(self.arguments("v2", output))
        self.assertEqual(code, 2)
        self.assertEqual(output.read_text(encoding="utf-8"), private_payload)

    def test_output_is_required_and_stdout_sentinel_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            projection._parser().parse_args(["project", "--result", "x"])
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = projection.main(self.arguments("v2", Path("-")))
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")

    def test_historical_cli_is_not_a_mutated_v2_envelope(self) -> None:
        output = self.root / "historical.json"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = projection.main(self.arguments("v1", output))
        self.assertEqual(code, 0)
        historical = json.loads(output.read_bytes())
        self.assertEqual(historical["campaign"]["campaign_version"], "v1")
        self.assertEqual(historical["implementation"]["result_schema_version"], "0.2.0")

    def test_private_reader_uses_open_descriptor_bytes_and_rejects_symlink(self) -> None:
        evidence = self.write("fd-evidence.json", {"value": "bound-to-open-fd"})
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("path reopen")):
            payload, value = projection._read_private_json(evidence)
        self.assertEqual(value, {"value": "bound-to-open-fd"})
        self.assertEqual(payload, projection.canonical_bytes(value))

        link = self.root / "linked-evidence.json"
        link.symlink_to(evidence)
        with self.assertRaisesRegex(projection.ProjectionError, "non-symlink"):
            projection._read_private_json(link)


if __name__ == "__main__":
    unittest.main()
