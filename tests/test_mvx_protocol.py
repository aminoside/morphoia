from __future__ import annotations

import json
import unittest

from morphoia.mvx.hmac_rank import ENCODING_ID as HMAC_RANK_ENCODING_ID
from morphoia.mvx.protocol import (
    G0_PATH,
    NORMATIVE_PATHS,
    PROJECT_ROOT,
    SEAL_PATH,
    load_yaml,
    verify_protocol,
)
from morphoia.mvx.split import (
    ALGORITHM_ID as SPLIT_ALGORITHM_ID,
)
from morphoia.mvx.split import (
    ALGORITHM_VERSION as SPLIT_ALGORITHM_VERSION,
)
from morphoia.mvx.split import _hmac_hex, assign_grouped_split, build_split_manifest


class MvxProtocolTests(unittest.TestCase):
    def test_all_normative_files_exist(self) -> None:
        missing = [path for path in NORMATIVE_PATHS if not (PROJECT_ROOT / path).is_file()]
        self.assertEqual(missing, [])

    def test_metric_ids_are_unique_and_cover_primary_endpoints(self) -> None:
        protocol = load_yaml("docs/mvx/validation/p0/protocol.yaml")
        dictionary = load_yaml("docs/mvx/validation/p0/metrics.yaml")
        ids = [item["id"] for item in dictionary["metrics"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(protocol["endpoint_hierarchy"]["primary"]) <= set(ids))

    def test_error_codes_are_unique(self) -> None:
        taxonomy = load_yaml("docs/mvx/validation/p0/error-codes.yaml")
        codes = [item["code"] for item in taxonomy["codes"]]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(code.startswith("MVX-") for code in codes))

    def test_split_is_deterministic_and_input_order_independent(self) -> None:
        salt = json.loads(
            (PROJECT_ROOT / "docs/mvx/validation/p0/split-test-vectors.json").read_text(
                encoding="utf-8"
            )
        )["salt_hex"]
        records = []
        for index in range(30):
            records.append(
                {
                    "lineage_id": f"L{index:03d}",
                    "leakage_group_id": f"G{index // 2:03d}",
                    "selection_stratum": "objaverse" if index % 3 else "cad",
                    "dataset": "A" if index % 2 else "B",
                    "topology_status": ("V", "O", "N")[index % 3],
                    "complexity_quantile": index % 10,
                    "category": f"C{index % 5}",
                    "creator_group": f"CREATOR-{index // 2:03d}",
                    "source_uid": f"SOURCE-{index // 2:03d}",
                    "eligibility": "ELIGIBLE",
                }
            )
        first = assign_grouped_split(records, salt_hex=salt)
        second = assign_grouped_split(reversed(records), salt_hex=salt)
        self.assertEqual(first, second)
        for index in range(0, 30, 2):
            self.assertEqual(first[f"L{index:03d}"], first[f"L{index + 1:03d}"])

    def test_frozen_split_vector(self) -> None:
        vector_path = (
            PROJECT_ROOT / "docs" / "mvx" / "validation" / "p0" / "split-test-vectors.json"
        )
        vector = json.loads(vector_path.read_text(encoding="utf-8"))
        self.assertEqual(vector["algorithm_id"], SPLIT_ALGORITHM_ID)
        self.assertEqual(vector["algorithm_version"], SPLIT_ALGORITHM_VERSION)
        self.assertEqual(vector["hmac_message_encoding"], HMAC_RANK_ENCODING_ID)
        salt = bytes.fromhex(vector["salt_hex"])
        actual_rank_vectors = {
            item["name"]: _hmac_hex(salt, item["domain"], *item["parts"])
            for item in vector["hmac_rank_vectors"]
        }
        self.assertEqual(
            actual_rank_vectors,
            {item["name"]: item["expected_hex"] for item in vector["hmac_rank_vectors"]},
        )
        actual = assign_grouped_split(vector["records"], salt_hex=vector["salt_hex"])
        self.assertEqual(actual, vector["expected_assignments"])

    def test_split_preserves_oversized_group(self) -> None:
        salt = json.loads(
            (PROJECT_ROOT / "docs/mvx/validation/p0/split-test-vectors.json").read_text(
                encoding="utf-8"
            )
        )["salt_hex"]
        records = []
        for index, group in enumerate(("BIG", "BIG", "BIG", "A", "B", "C")):
            records.append(
                {
                    "lineage_id": f"L{index}",
                    "leakage_group_id": group,
                    "selection_stratum": "fixture",
                    "dataset": "oracle",
                    "topology_status": "V",
                    "complexity_quantile": 0,
                    "category": "C0",
                    "creator_group": f"CREATOR-{group}",
                    "source_uid": f"SOURCE-{group}",
                    "eligibility": "ELIGIBLE",
                }
            )
        assigned = assign_grouped_split(records, salt_hex=salt)
        self.assertEqual({assigned["L0"], assigned["L1"], assigned["L2"]}.__len__(), 1)

    def test_split_manifest_has_protocol_root_and_schema_shape(self) -> None:
        salt = "22" * 32
        records = [
            {
                "lineage_id": f"L{index}",
                "leakage_group_id": f"G{index}",
                "selection_stratum": "fixture",
                "dataset": "oracle",
                "topology_status": "V",
                "complexity_quantile": 0,
                "category": "C0",
                "creator_group": f"C{index}",
                "source_uid": f"S{index}",
                "eligibility": "ELIGIBLE",
            }
            for index in range(10)
        ]
        manifest = build_split_manifest(records, salt_hex=salt, protocol_root_sha256="a" * 64)
        self.assertEqual(manifest["protocol_root_sha256"], "a" * 64)
        self.assertEqual(sum(manifest["counts"].values()), 10)
        self.assertTrue(all("creator_group" in row for row in manifest["assignments"]))

    def test_production_mode_meets_exact_stratum_quotas_and_forced_ood(self) -> None:
        salt = "33" * 32
        targets = {
            "objaverse": {"total": 6, "development": 3, "calibration": 1, "blind": 2},
            "fixtures_C0_C9": {
                "total": 4,
                "development": 2,
                "calibration": 1,
                "blind": 1,
            },
        }
        records = []
        for stratum, count in (("objaverse", 6), ("fixtures_C0_C9", 4)):
            for index in range(count):
                record = {
                    "lineage_id": f"{stratum}-L{index}",
                    "leakage_group_id": f"{stratum}-G{index}",
                    "selection_stratum": stratum,
                    "dataset": stratum,
                    "topology_status": "V",
                    "complexity_quantile": index,
                    "category": "held-out" if index == 0 else "visible",
                    "creator_group": f"{stratum}-C{index}",
                    "source_uid": f"{stratum}-S{index}",
                    "eligibility": "ELIGIBLE",
                }
                if stratum == "objaverse" and index == 0:
                    record["forced_split"] = "blind"
                    record["blind_scope"] = "OOD"
                records.append(record)
        first = assign_grouped_split(
            records,
            salt_hex=salt,
            exact_targets_by_stratum=targets,
        )
        second = assign_grouped_split(
            reversed(records),
            salt_hex=salt,
            exact_targets_by_stratum=targets,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["objaverse-L0"], "blind")
        for stratum, target in targets.items():
            counts = {
                split: sum(
                    destination == split
                    for lineage, destination in first.items()
                    if lineage.startswith(f"{stratum}-")
                )
                for split in ("development", "calibration", "blind")
            }
            self.assertEqual(counts, {key: target[key] for key in counts})

    def test_production_mode_fails_when_atomic_groups_make_quota_impossible(self) -> None:
        records = []
        for index, group in enumerate(("PAIR", "PAIR", "SINGLE")):
            records.append(
                {
                    "lineage_id": f"L{index}",
                    "leakage_group_id": group,
                    "selection_stratum": "objaverse",
                    "dataset": "objaverse",
                    "topology_status": "V",
                    "complexity_quantile": 0,
                    "category": "chair",
                    "creator_group": f"C-{group}",
                    "source_uid": f"S-{group}",
                    "eligibility": "ELIGIBLE",
                }
            )
        with self.assertRaisesRegex(ValueError, "exact grouped split is infeasible"):
            assign_grouped_split(
                records,
                salt_hex="44" * 32,
                exact_targets_by_stratum={
                    "objaverse": {
                        "total": 3,
                        "development": 1,
                        "calibration": 1,
                        "blind": 1,
                    }
                },
            )

    def test_seal_and_g0_verdict_verify(self) -> None:
        self.assertTrue(SEAL_PATH.is_file())
        self.assertTrue(G0_PATH.is_file())
        verification = verify_protocol(require_seal=True)
        self.assertTrue(verification.ok, [item.evidence for item in verification.failures])
        verdict = json.loads(G0_PATH.read_text(encoding="utf-8"))
        self.assertEqual(verdict["verdict"], "PASS")
        self.assertEqual(verdict["protocol_root_sha256"], verification.root_sha256)


if __name__ == "__main__":
    unittest.main()
