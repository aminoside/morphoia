from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morphoia.mvx import protocol as protocol_module
from morphoia.mvx.protocol import (
    EXAMPLE_DIRECTORY,
    EXPECTED_GATE_CRITERIA,
    NORMATIVE_PATHS,
    PROJECT_ROOT,
    SCHEMA_DIRECTORY,
    ProtocolCheck,
    ProtocolVerification,
    _clarification_checks,
    _classification_and_denominator_checks,
    _eligibility_checks,
    _error_taxonomy_checks,
    _metric_checks,
    _release_checks,
    _statistical_checks,
    canonical_json_bytes,
    create_seal,
    load_yaml,
    write_g0_verdict,
)


class MvxProtocolSemanticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protocol = load_yaml("docs/mvx/validation/p0/protocol.yaml")
        self.metrics = load_yaml("docs/mvx/validation/p0/metrics.yaml")
        self.eligibility = load_yaml("docs/mvx/validation/p0/eligibility.yaml")
        self.statistical = load_yaml("docs/mvx/validation/p0/statistical-plan.yaml")
        self.errors = load_yaml("docs/mvx/validation/p0/error-codes.yaml")
        self.release = load_yaml("docs/mvx/validation/p0/release-criteria.yaml")
        self.clarifications = load_yaml("docs/mvx/validation/p0/implementation-clarifications.yaml")

    @staticmethod
    def _closure(checks: list[ProtocolCheck]) -> ProtocolCheck:
        return next(check for check in checks if check.identifier == "ENDPOINT_HIERARCHY_CLOSED")

    def test_endpoint_closure_rejects_metric_missing_from_hierarchy(self) -> None:
        metrics = copy.deepcopy(self.metrics)
        metrics["metrics"].append(
            {
                "id": "unregistered_primary_endpoint",
                "level": "primary",
                "type": "boolean",
            }
        )
        self.assertFalse(self._closure(_metric_checks(self.protocol, metrics)).passed)

    def test_endpoint_closure_rejects_duplicate_endpoint(self) -> None:
        protocol = copy.deepcopy(self.protocol)
        protocol["endpoint_hierarchy"]["primary"].append(
            protocol["endpoint_hierarchy"]["primary"][0]
        )
        self.assertFalse(self._closure(_metric_checks(protocol, self.metrics)).passed)

    def test_endpoint_closure_rejects_unknown_hierarchy_level(self) -> None:
        protocol = copy.deepcopy(self.protocol)
        protocol["endpoint_hierarchy"]["unregistered_level"] = []
        self.assertFalse(self._closure(_metric_checks(protocol, self.metrics)).passed)

    def test_normative_paths_cover_every_schema_and_indexed_example(self) -> None:
        normative = set(NORMATIVE_PATHS)
        expected = {
            path.relative_to(PROJECT_ROOT).as_posix()
            for directory, pattern in (
                (SCHEMA_DIRECTORY, "*.schema.json"),
                (EXAMPLE_DIRECTORY, "*.json"),
            )
            for path in directory.glob(pattern)
            if path.is_file()
        }
        self.assertTrue(expected)
        self.assertTrue(expected <= normative)

    def test_normative_paths_cover_every_local_morphoia_module(self) -> None:
        normative = set(NORMATIVE_PATHS)
        local_sources = {
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in (PROJECT_ROOT / "src" / "morphoia").rglob("*.py")
            if path.is_file()
        }
        self.assertTrue(local_sources)
        self.assertTrue(local_sources <= normative)

    def test_immediate_predecessor_archive_is_hash_linked_and_fail_effective(self) -> None:
        current = protocol_module._predecessor_archive_check()
        self.assertTrue(current.passed, current.evidence)
        with patch.object(protocol_module, "PREDECESSOR_SEAL_SHA256", "0" * 64):
            changed = protocol_module._predecessor_archive_check()
        self.assertFalse(changed.passed)

    def test_outcome_based_exclusion_is_rejected(self) -> None:
        eligibility = copy.deepcopy(self.eligibility)
        eligibility["exclude_before_split_if"].append("reconstruction fidelity is poor")
        firewall = next(
            check
            for check in _eligibility_checks(eligibility)
            if check.identifier == "ELIGIBILITY_OUTCOME_FIREWALL"
        )
        self.assertFalse(firewall.passed)

    def test_duplicate_holm_hypothesis_is_rejected(self) -> None:
        statistical = copy.deepcopy(self.statistical)
        statistical["multiplicity"]["families"]["real_geometry_and_topology"]["hypotheses"].append(
            "core_conformance"
        )
        holm = next(
            check
            for check in _statistical_checks(statistical, self.protocol)
            if check.identifier == "HOLM_PRIMARY_FAMILIES_EXACT"
        )
        self.assertFalse(holm.passed)

    def test_holm_hypothesis_without_executable_null_is_rejected(self) -> None:
        statistical = copy.deepcopy(self.statistical)
        del statistical["multiplicity"]["families"]["real_geometry_and_topology"]["hypotheses"][0][
            "H0"
        ]
        holm = next(
            check
            for check in _statistical_checks(statistical, self.protocol)
            if check.identifier == "HOLM_PRIMARY_FAMILIES_EXACT"
        )
        self.assertFalse(holm.passed)

    def test_population_blocker_cannot_be_folded_into_lineage_critical_failure(self) -> None:
        metrics = copy.deepcopy(self.metrics)
        critical = next(item for item in metrics["metrics"] if item["id"] == "critical_failure")
        critical["definition"] = "Any lineage or population-level release rule failure."
        contract = next(
            check
            for check in _metric_checks(self.protocol, metrics)
            if check.identifier == "METRIC_SCOPE_UNITS_BOUNDS_CLOSED"
        )
        self.assertFalse(contract.passed)

    def test_missing_population_claim_boundary_is_rejected(self) -> None:
        clarifications = copy.deepcopy(self.clarifications)
        clarifications["population_bound"]["decision"] = "Pool all datasets."
        claim = next(
            check
            for check in _clarification_checks(clarifications)
            if check.identifier == "CLARIFICATION_CLAIM_BOUNDARY"
        )
        self.assertFalse(claim.passed)

    def test_denominator_that_drops_failures_is_rejected(self) -> None:
        metrics = copy.deepcopy(self.metrics)
        terminal = next(
            item for item in metrics["metrics"] if item["id"] == "terminal_usable_fraction"
        )
        terminal["definition"] = "Successful complete cases only."
        self.assertFalse(_classification_and_denominator_checks(metrics).passed)

    def test_terminal_precedence_order_mutation_is_rejected(self) -> None:
        errors = copy.deepcopy(self.errors)
        ordered = errors["terminal_precedence"]["ordered_fault_codes"]
        ordered[0], ordered[1] = ordered[1], ordered[0]
        self.assertFalse(_error_taxonomy_checks(errors)[0].passed)

    def test_missing_multi_fault_vector_is_rejected(self) -> None:
        errors = copy.deepcopy(self.errors)
        errors["terminal_precedence"]["multi_fault_vectors"].pop()
        self.assertFalse(_error_taxonomy_checks(errors)[0].passed)

    def test_wrong_multi_fault_primary_code_is_rejected(self) -> None:
        errors = copy.deepcopy(self.errors)
        vector = errors["terminal_precedence"]["multi_fault_vectors"][0]
        vector["expected_primary"] = vector["candidates"][0]
        self.assertFalse(_error_taxonomy_checks(errors)[0].passed)

    def test_terminal_precedence_covers_every_non_payload_code_exactly(self) -> None:
        check = _error_taxonomy_checks(self.errors)[0]
        self.assertTrue(check.passed, check.evidence)
        codes = {item["code"] for item in self.errors["codes"]}
        payload = set(self.errors["payload_state_codes"])
        coverage = {
            vector["expected_primary"]
            for vector in self.errors["terminal_precedence"]["coverage_vectors"]
        }
        self.assertEqual(coverage, codes - payload)

    def test_coordinated_error_code_deletion_still_fails_closed(self) -> None:
        errors = copy.deepcopy(self.errors)
        deleted = "MVX-G003"
        errors["codes"] = [item for item in errors["codes"] if item["code"] != deleted]
        errors["terminal_mapping"]["DECLARED_LIMIT"].remove(deleted)
        precedence = errors["terminal_precedence"]
        precedence["ordered_fault_codes"].remove(deleted)
        precedence["pipeline"][-1]["codes"].remove(deleted)
        precedence["coverage_vectors"] = [
            item for item in precedence["coverage_vectors"] if item["expected_primary"] != deleted
        ]
        precedence["multi_fault_vectors"] = [
            item for item in precedence["multi_fault_vectors"] if deleted not in item["candidates"]
        ]
        self.assertFalse(_error_taxonomy_checks(errors)[0].passed)

    def test_gate_pass_if_count_must_match_gate_specific_catalog(self) -> None:
        release = copy.deepcopy(self.release)
        release["gates"]["G4"]["pass_if"].pop()
        catalog = next(
            check
            for check in _release_checks(release)
            if check.identifier == "GATE_CRITERIA_CATALOG_CLOSED"
        )
        self.assertFalse(catalog.passed)

    def test_create_seal_refuses_to_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            seal_path = Path(temporary) / "seal.json"
            seal_path.write_text("immutable\n", encoding="utf-8")
            with (
                patch.object(protocol_module, "SEAL_PATH", seal_path),
                patch.object(
                    protocol_module,
                    "_semantic_checks",
                    return_value=[ProtocolCheck("SYNTHETIC", True, "passed")],
                ),
                self.assertRaises(FileExistsError),
            ):
                create_seal()
            self.assertEqual(seal_path.read_text(encoding="utf-8"), "immutable\n")

    def test_create_seal_reuses_only_an_identical_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            seal_path = Path(temporary) / "seal.json"
            with (
                patch.object(protocol_module, "SEAL_PATH", seal_path),
                patch.object(
                    protocol_module,
                    "_semantic_checks",
                    return_value=[ProtocolCheck("SYNTHETIC", True, "passed")],
                ),
            ):
                first = create_seal()
                original = seal_path.read_bytes()
                second = create_seal()
            self.assertEqual(first, second)
            self.assertEqual(original, canonical_json_bytes(first) + b"\n")
            self.assertEqual(seal_path.read_bytes(), original)
            self.assertFalse(list(seal_path.parent.glob(f".{seal_path.name}.*.tmp")))

    @staticmethod
    def _passing_g0_verification(root_sha256: str) -> ProtocolVerification:
        return ProtocolVerification(
            checks=(
                ProtocolCheck("NORMATIVE_FILES_PRESENT", True, "passed"),
                ProtocolCheck("SEAL_ROOT", True, "passed"),
                ProtocolCheck("PROTOCOL_FROZEN", True, "passed"),
                ProtocolCheck("CUSTODY_SYNTHETIC_DRY_RUN", True, "passed"),
                ProtocolCheck("METRIC_IDS_UNIQUE", True, "passed"),
            ),
            root_sha256=root_sha256,
        )

    def test_rerun_completes_missing_verdict_and_then_reuses_both_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            seal_path = directory / "seal.json"
            verdict_path = directory / "gates" / "G0-verdict.json"
            with (
                patch.object(protocol_module, "SEAL_PATH", seal_path),
                patch.object(protocol_module, "G0_PATH", verdict_path),
                patch.object(
                    protocol_module,
                    "_semantic_checks",
                    return_value=[ProtocolCheck("SYNTHETIC", True, "passed")],
                ),
            ):
                first_seal = create_seal()
                self.assertFalse(verdict_path.exists())

                reused_seal = create_seal()
                verification = self._passing_g0_verification(
                    first_seal["protocol_root_sha256"]
                )
                first_verdict = write_g0_verdict(verification)
                original_verdict = verdict_path.read_bytes()
                reused_verdict = write_g0_verdict(verification)

            self.assertEqual(reused_seal, first_seal)
            self.assertEqual(reused_verdict, first_verdict)
            self.assertEqual(first_verdict["verdict"], "PASS")
            self.assertEqual(original_verdict, canonical_json_bytes(first_verdict) + b"\n")
            self.assertEqual(verdict_path.read_bytes(), original_verdict)
            self.assertFalse(list(directory.rglob("*.tmp")))

    def test_g0_verdict_refuses_to_replace_a_different_valid_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            seal_path = directory / "seal.json"
            verdict_path = directory / "G0-verdict.json"
            seal_path.write_bytes(b"synthetic immutable seal\n")
            passing = self._passing_g0_verification("a" * 64)
            failing = ProtocolVerification(
                checks=(ProtocolCheck("SYNTHETIC_BLOCKER", False, "expected failure"),),
                root_sha256="a" * 64,
            )
            with (
                patch.object(protocol_module, "SEAL_PATH", seal_path),
                patch.object(protocol_module, "G0_PATH", verdict_path),
            ):
                write_g0_verdict(passing)
                original = verdict_path.read_bytes()
                with self.assertRaises(FileExistsError):
                    write_g0_verdict(failing)
            self.assertEqual(verdict_path.read_bytes(), original)

    def test_publish_failure_leaves_no_partial_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "seal.json"
            with (
                patch.object(protocol_module.os, "link", side_effect=OSError("synthetic crash")),
                self.assertRaisesRegex(OSError, "synthetic crash"),
            ):
                protocol_module._publish_write_once_json(
                    target,
                    {"complete": True},
                    artifact="synthetic seal",
                )
            self.assertFalse(target.exists())
            self.assertFalse(list(target.parent.glob(f".{target.name}.*.tmp")))

    def test_g0_verdict_with_failed_criterion_is_always_fail(self) -> None:
        verification = ProtocolVerification(
            checks=(ProtocolCheck("SYNTHETIC_BLOCKER", False, "expected failure"),),
            root_sha256="a" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            seal_path = directory / "seal.json"
            verdict_path = directory / "G0-verdict.json"
            seal_path.write_text("synthetic seal evidence\n", encoding="utf-8")
            with (
                patch.object(protocol_module, "SEAL_PATH", seal_path),
                patch.object(protocol_module, "G0_PATH", verdict_path),
            ):
                verdict = write_g0_verdict(verification)
        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertEqual(
            tuple(item["id"] for item in verdict["criteria"]),
            EXPECTED_GATE_CRITERIA["G0"],
        )
        self.assertTrue(any(not item["passed"] for item in verdict["criteria"]))
        self.assertTrue(verdict["blockers"])
        self.assertIn("not human double blinding", " ".join(verdict["deviations"]))


if __name__ == "__main__":
    unittest.main()
