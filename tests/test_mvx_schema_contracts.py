from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "mvx" / "0.2.1"
EXAMPLES = ROOT / "docs" / "mvx" / "validation" / "p0" / "schema-examples"


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / name).read_text(encoding="utf-8")))


def example(name: str) -> dict[str, object]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class MvxSchemaContractTests(unittest.TestCase):
    def test_every_mvx_schema_has_a_valid_example(self) -> None:
        index = example("index.json")
        mapping = {item["schema"]: item["instance"] for item in index["examples"]}
        schemas = {path.name for path in SCHEMAS.glob("*.schema.json")}
        self.assertLessEqual(set(mapping), schemas)
        for schema_name in schemas:
            instance_name = mapping.get(
                schema_name, schema_name.removesuffix(".schema.json") + ".valid.json"
            )
            with self.subTest(schema=schema_name):
                self.assertTrue(
                    (EXAMPLES / instance_name).is_file(),
                    f"missing valid example for {schema_name}",
                )
                validator(schema_name).validate(example(instance_name))

    def test_custody_timestamps_require_explicit_utc_z_shape(self) -> None:
        cases = (
            (
                "protocol-seal.schema.json",
                "protocol-seal.valid.json",
                ("sealed_at",),
            ),
            (
                "precommit-publication-receipt.schema.json",
                "precommit-publication-receipt.valid.json",
                ("published_at",),
            ),
            (
                "trusted-publishers.schema.json",
                "trusted-publishers.valid.json",
                ("publishers", 0, "valid_from"),
            ),
            (
                "trusted-publishers.schema.json",
                "trusted-publishers.valid.json",
                ("publishers", 0, "valid_until"),
            ),
        )
        invalid_values = ("2026-08-06T12:00:00+00:00", "not-a-timestampZ")
        for schema_name, example_name, path in cases:
            for invalid in invalid_values:
                with self.subTest(schema=schema_name, path=path, invalid=invalid):
                    document = example(example_name)
                    target = document
                    for element in path[:-1]:
                        target = target[element]
                    target[path[-1]] = invalid
                    self.assertTrue(list(validator(schema_name).iter_errors(document)))

    def test_hd95_string_is_rejected(self) -> None:
        record = example("metric-record.valid.json")
        record["value"] = "not-a-number"
        self.assertTrue(list(validator("metric-record.schema.json").iter_errors(record)))

    def test_metric_schema_scopes_partition_the_dictionary(self) -> None:
        dictionary = yaml.safe_load(
            (ROOT / "docs" / "mvx" / "validation" / "p0" / "metrics.yaml").read_text(
                encoding="utf-8"
            )
        )
        expected_lineage = {
            item["id"] for item in dictionary["metrics"] if item["scope"] == "LINEAGE"
        }
        expected_aggregate = {
            item["id"] for item in dictionary["metrics"] if item["scope"] == "AGGREGATE"
        }
        lineage_schema = json.loads(
            (SCHEMAS / "metric-record.schema.json").read_text(encoding="utf-8")
        )
        aggregate_schema = json.loads(
            (SCHEMAS / "aggregate-metric-record.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(lineage_schema["properties"]["metric_id"]["enum"]), expected_lineage)
        self.assertEqual(
            set(aggregate_schema["properties"]["metric_id"]["enum"]), expected_aggregate
        )
        self.assertFalse(expected_lineage & expected_aggregate)

    def test_lineage_and_aggregate_metric_ids_cannot_cross_scopes(self) -> None:
        lineage = example("metric-record.valid.json")
        lineage["metric_id"] = "release_critical_blocker_count"
        lineage["value"] = 0
        lineage["unit"] = "count"
        self.assertTrue(list(validator("metric-record.schema.json").iter_errors(lineage)))

        aggregate = example("aggregate-metric-record.valid.json")
        aggregate["metric_id"] = "critical_failure"
        aggregate["value"] = False
        aggregate["unit"] = "boolean"
        self.assertTrue(
            list(validator("aggregate-metric-record.schema.json").iter_errors(aggregate))
        )

    def test_lineage_metric_numeric_bounds_are_enforced(self) -> None:
        schema = validator("metric-record.schema.json")
        record = example("metric-record.valid.json")

        record["value"] = -0.01
        self.assertTrue(list(schema.iter_errors(record)), "negative HD95 must fail")

        record.update(metric_id="occupancy_iou", value=1.001, unit="ratio")
        self.assertTrue(list(schema.iter_errors(record)), "ratio above one must fail")

        record.update(metric_id="relative_volume_error", value=-0.01, unit="relative_error")
        self.assertTrue(list(schema.iter_errors(record)), "negative relative error must fail")
        record["value"] = 1.25
        self.assertFalse(list(schema.iter_errors(record)), "relative error may exceed one")

        record.update(metric_id="package_size_bytes", value=-1, unit="byte")
        self.assertTrue(list(schema.iter_errors(record)), "negative byte count must fail")

        record.update(metric_id="encode_seconds", value=-0.001, unit="second")
        self.assertTrue(list(schema.iter_errors(record)), "negative duration must fail")

    def test_metric_specific_unit_is_mandatory(self) -> None:
        record = example("metric-record.valid.json")
        record["unit"] = "second"
        self.assertTrue(list(validator("metric-record.schema.json").iter_errors(record)))

    def test_aggregate_loader_and_release_bounds_are_enforced(self) -> None:
        schema = validator("aggregate-metric-record.schema.json")
        record = example("aggregate-metric-record.valid.json")

        record.update(
            metric_id="loader_throughput_ratio",
            value=-0.01,
            unit="ratio_to_cost_matched_contiguous_tensor",
        )
        self.assertTrue(list(schema.iter_errors(record)), "negative loader ratio must fail")

        record.update(metric_id="terminal_usable_fraction", value=1.01, unit="ratio")
        self.assertTrue(list(schema.iter_errors(record)), "release ratio above one must fail")

        record.update(metric_id="release_critical_blocker_count", value=-1, unit="count")
        self.assertTrue(list(schema.iter_errors(record)), "negative blocker count must fail")

    def test_all_release_metrics_have_serializable_aggregate_records(self) -> None:
        schema = validator("aggregate-metric-record.schema.json")
        cases = (
            ("terminal_usable_fraction", 0.975, "ratio"),
            ("class_A_fraction_verified_closed", 0.925, "ratio"),
            ("release_critical_blocker_count", 0, "count"),
            ("systematic_stratum_disadvantage", False, "boolean"),
        )
        for metric_id, value, unit in cases:
            with self.subTest(metric=metric_id):
                record = example("aggregate-metric-record.valid.json")
                record.update(metric_id=metric_id, value=value, unit=unit)
                self.assertFalse(list(schema.iter_errors(record)))

    def test_non_evaluable_metric_cannot_retain_a_value(self) -> None:
        record = example("metric-record.valid.json")
        record.update(status="MISSING", reason="worker output absent")
        self.assertTrue(list(validator("metric-record.schema.json").iter_errors(record)))
        record["value"] = None
        self.assertFalse(list(validator("metric-record.schema.json").iter_errors(record)))

    def test_pass_with_error_or_missing_artifact_hash_is_rejected(self) -> None:
        record = example("run-manifest.valid.json")
        record["error_code"] = "MVX-X001"
        record["artifact_hashes"]["reconstruction"] = None
        self.assertTrue(list(validator("run-manifest.schema.json").iter_errors(record)))

    def test_run_manifest_requires_work_and_execution_plan_bindings(self) -> None:
        schema = validator("run-manifest.schema.json")
        for field in ("work_id", "execution_plan_sha256"):
            with self.subTest(field=field):
                record = example("run-manifest.valid.json")
                del record[field]
                self.assertTrue(list(schema.iter_errors(record)))

    def test_terminal_stage_checkpoint_requires_hashed_artifacts(self) -> None:
        record = example("stage-checkpoint.valid.json")
        record["artifact_hashes"] = {}
        self.assertTrue(list(validator("stage-checkpoint.schema.json").iter_errors(record)))

    def test_blind_execution_plan_stage_must_be_open_once(self) -> None:
        record = example("execution-plan.valid.json")
        record["stages"][0]["identity"].update(split="blind", open_once=False)
        self.assertTrue(list(validator("execution-plan.schema.json").iter_errors(record)))

    def test_pass_gate_with_blocker_or_failed_criterion_is_rejected(self) -> None:
        record = example("gate-verdict.valid.json")
        record["blockers"] = ["unresolved"]
        record["criteria"][0]["passed"] = False
        self.assertTrue(list(validator("gate-verdict.schema.json").iter_errors(record)))

    def test_gate_specific_criteria_are_complete_and_exact(self) -> None:
        schema_json = json.loads((SCHEMAS / "gate-verdict.schema.json").read_text(encoding="utf-8"))
        catalog = {
            gate: tuple(definition["enum"])
            for gate, definition in schema_json["$defs"]["gateCriterionIds"].items()
        }
        schema = Draft202012Validator(schema_json)
        self.assertEqual(set(catalog), {f"G{index}" for index in range(8)})
        for gate, identifiers in catalog.items():
            with self.subTest(gate=gate):
                record = example("gate-verdict.valid.json")
                record["gate"] = gate
                record["criteria"] = [
                    {"id": identifier, "passed": True, "evidence": "synthetic evidence"}
                    for identifier in identifiers
                ]
                self.assertFalse(list(schema.iter_errors(record)))

                missing = copy.deepcopy(record)
                missing["criteria"].pop()
                self.assertTrue(list(schema.iter_errors(missing)))

                duplicate = copy.deepcopy(record)
                duplicate["criteria"][-1] = copy.deepcopy(duplicate["criteria"][0])
                duplicate["criteria"][-1]["evidence"] = "different duplicate evidence"
                self.assertTrue(list(schema.iter_errors(duplicate)))

                unknown = copy.deepcopy(record)
                unknown["criteria"][0]["id"] = f"{gate}_UNKNOWN"
                self.assertTrue(list(schema.iter_errors(unknown)))

    def test_gate_verdict_and_criteria_cannot_be_incoherent(self) -> None:
        schema = validator("gate-verdict.schema.json")

        empty = example("gate-verdict.valid.json")
        empty["criteria"] = []
        self.assertTrue(list(schema.iter_errors(empty)))

        fail_all_true = example("gate-verdict.valid.json")
        fail_all_true.update(verdict="FAIL", blockers=["declared blocker"])
        self.assertTrue(list(schema.iter_errors(fail_all_true)))

        fail_without_blocker = example("gate-verdict.valid.json")
        fail_without_blocker["verdict"] = "FAIL"
        fail_without_blocker["criteria"][0]["passed"] = False
        self.assertTrue(list(schema.iter_errors(fail_without_blocker)))

        coherent_fail = copy.deepcopy(fail_without_blocker)
        coherent_fail["blockers"] = ["criterion failed"]
        self.assertFalse(list(schema.iter_errors(coherent_fail)))

        conditional_without_condition = copy.deepcopy(coherent_fail)
        conditional_without_condition["verdict"] = "CONDITIONAL"
        conditional_without_condition["deviations"] = []
        self.assertTrue(list(schema.iter_errors(conditional_without_condition)))

        conditional_with_condition = copy.deepcopy(conditional_without_condition)
        conditional_with_condition["deviations"] = ["owner and due gate recorded"]
        self.assertFalse(list(schema.iter_errors(conditional_with_condition)))

    def test_calibration_freeze_rejects_unknown_or_missing_core_channels(self) -> None:
        schema = validator("calibration-freeze.schema.json")
        baseline = example("calibration-freeze.valid.json")

        unknown = copy.deepcopy(baseline)
        unknown["channels"].append("depth_alias")
        self.assertTrue(list(schema.iter_errors(unknown)))

        missing = copy.deepcopy(baseline)
        missing["channels"].remove("event_kind")
        self.assertTrue(list(schema.iter_errors(missing)))

    def test_calibration_threshold_catalog_is_exact_and_cannot_be_relaxed(self) -> None:
        schema = validator("calibration-freeze.schema.json")
        baseline = example("calibration-freeze.valid.json")
        expected = {
            "hd95_symmetric_p": ("max", 2.0),
            "chamfer_symmetric_rms_p": ("max", 0.75),
            "occupancy_iou": ("min", 0.99),
            "normal_median_deg": ("max", 1.0),
            "normal_p95_deg": ("max", 5.0),
            "relative_volume_error": ("max", 0.02),
            "relative_area_error": ("max", 0.05),
            "topology_exact_ge_8p": ("equal", True),
            "openings_recall_ge_8p": ("min", 0.95),
            "cross_view_agreement_real": ("min", 0.9999),
            "cross_view_agreement_oracle": ("equal", 1.0),
            "cross_view_eligible_coverage": ("min", 0.95),
            "ray_overflow_fraction": ("max", 0.001),
            "topologically_critical_omission_count": ("equal", 0),
        }
        self.assertEqual(set(baseline["thresholds"]), set(expected))

        for metric_id, (direction, p0_value) in expected.items():
            with self.subTest(metric=metric_id):
                threshold = baseline["thresholds"][metric_id]
                self.assertEqual(threshold["direction"], direction)
                self.assertEqual(threshold["p0_value"], p0_value)

                relaxed = copy.deepcopy(baseline)
                if direction == "max":
                    relaxed_value = float(p0_value) + max(abs(float(p0_value)) * 0.01, 0.0001)
                elif direction == "min":
                    relaxed_value = float(p0_value) - 0.0001
                elif isinstance(p0_value, bool):
                    relaxed_value = not p0_value
                else:
                    relaxed_value = float(p0_value) + 1.0
                relaxed["thresholds"][metric_id]["frozen_value"] = relaxed_value
                self.assertTrue(list(schema.iter_errors(relaxed)))

                if direction in {"max", "min"}:
                    stricter = copy.deepcopy(baseline)
                    stricter["thresholds"][metric_id]["frozen_value"] = (
                        float(p0_value) / 2.0
                        if direction == "max"
                        else (float(p0_value) + 1.0) / 2.0
                    )
                    self.assertFalse(list(schema.iter_errors(stricter)))

        missing = copy.deepcopy(baseline)
        del missing["thresholds"]["hd95_symmetric_p"]
        self.assertTrue(list(schema.iter_errors(missing)))

        extra = copy.deepcopy(baseline)
        extra["thresholds"]["unregistered"] = {
            "direction": "max",
            "p0_value": 1.0,
            "frozen_value": 1.0,
        }
        self.assertTrue(list(schema.iter_errors(extra)))

    def test_excluded_record_cannot_receive_a_split(self) -> None:
        record = example("corpus-registry.valid.json")
        record["eligibility"] = "EXCLUDED"
        record["split"] = "blind"
        self.assertTrue(list(validator("corpus-registry.schema.json").iter_errors(record)))


if __name__ == "__main__":
    unittest.main()
