from __future__ import annotations

import copy
import hashlib
import random
import unittest
from unittest import mock

from test_mvx_custody import synthetic_publication_receipt

from morphoia.mvx.cohort import (
    CohortFreezeError,
    _freeze_cohort_impl,
    eligible_records_sha256,
)
from morphoia.mvx.custody import (
    canonical_json_bytes,
    create_custody_precommit,
    sha256_hex,
)
from morphoia.mvx.selection import DEFAULT_TARGETS

PROTOCOL_ROOT = "a" * 64
SNAPSHOT = "b" * 64
SELECTION_SEED = "3a6b4ecb2823191a9db74b71ad660824e0515b37f8e0555ea2bc5732d3cd4856"
SPLIT_SECRET = "00112233445566778899aabbccddeeff102132435465768798a9bacbdcedfe0f"

EXACT_TARGETS = {
    "fixtures_C0_C9": {"total": 100, "development": 50, "calibration": 20, "blind": 30},
    "objaverse": {"total": 600, "development": 300, "calibration": 120, "blind": 180},
    "modelnet40": {"total": 100, "development": 50, "calibration": 20, "blind": 30},
    "thingi10k": {"total": 80, "development": 40, "calibration": 16, "blind": 24},
    "google_scanned_objects": {
        "total": 60,
        "development": 30,
        "calibration": 12,
        "blind": 18,
    },
    "human_anatomy": {"total": 50, "development": 25, "calibration": 10, "blind": 15},
    "plants": {"total": 10, "development": 5, "calibration": 2, "blind": 3},
}


def precommit_for(input_hash: str) -> dict[str, str]:
    return create_custody_precommit(
        protocol_root_sha256=PROTOCOL_ROOT,
        snapshot_sha256=SNAPSHOT,
        eligible_records_sha256=input_hash,
        configuration_sha256=sha256_hex(EXACT_TARGETS),
        selection_seed=SELECTION_SEED,
        split_salt=SPLIT_SECRET,
        allow_public_test_secrets=True,
    )


def publication_for(precommit: dict[str, str]) -> tuple[dict[str, object], dict[str, object]]:
    return synthetic_publication_receipt(precommit)


def synthetic_records() -> list[dict[str, object]]:
    """Return 1,000 target candidates plus 50 Objaverse reserve candidates."""

    rows: list[dict[str, object]] = []
    supply = dict(DEFAULT_TARGETS)
    supply["objaverse"] = 650
    for stratum, count in supply.items():
        for index in range(count):
            category = f"objaverse-category-{index // 5:03d}" if stratum == "objaverse" else stratum
            lineage = f"{stratum}:L{index:04d}"
            row: dict[str, object] = {
                "lineage_id": lineage,
                "leakage_group_id": f"{stratum}:G{index:04d}",
                "selection_stratum": stratum,
                "dataset": stratum,
                "category": category,
                "creator_group": f"creator:{stratum}:{index:04d}",
                "source_uid": f"uid:{stratum}:{index:04d}",
                "eligibility": "ELIGIBLE",
                "topology_status": "V",
                "complexity_quantile": 0,
                "source_path": f"/private/corpus/{lineage}.glb",
                "source_uri": f"drive://private/{lineage}.glb",
                "source_sha256": hashlib.sha256(lineage.encode("utf-8")).hexdigest(),
                "source_size_bytes": 1_024 + index,
                "source_format": "glb",
                "format_status": "P2A_AUDITED_SUPPORTED",
                "licence": "CC-BY-4.0",
                "licence_status": "LAWFUL_INTERNAL_USE",
                "terminal_status": "FAIL",  # Deliberately forbidden outcome input.
                "hd95": 999.0,
            }
            if stratum == "fixtures_C0_C9":
                row["licence"] = "MORPHOIA-SYNTHETIC-FIXTURE"
                row["licence_status"] = "FIXTURE_GENERATED"
                row["fixture_exception"] = {
                    "kind": "SYNTHETIC_PROTOCOL_FIXTURE",
                    "case_id": f"C{index % 10}",
                    "generator_id": "morphoia-analytic-fixtures",
                    "generator_version": "0.1.0",
                }
            rows.append(row)
    if len(rows) != 1050:
        raise AssertionError("synthetic census must contain 1050 records")
    return rows


def freeze(records: list[dict[str, object]] | None = None):
    rows = synthetic_records() if records is None else records
    input_hash = eligible_records_sha256(rows)
    precommit = precommit_for(input_hash)
    publication_receipt, trusted_publishers = publication_for(precommit)
    return _freeze_cohort_impl(
        rows,
        protocol_root_sha256=PROTOCOL_ROOT,
        snapshot_sha256=SNAPSHOT,
        expected_input_records_sha256=input_hash,
        selection_seed_hex=SELECTION_SEED,
        split_secret_hex=SPLIT_SECRET,
        exact_targets=EXACT_TARGETS,
        precommit=precommit,
        publication_receipt=publication_receipt,
        trusted_publishers=trusted_publishers,
        allow_synthetic_receipt=True,
        allow_public_test_secrets=True,
    )


class MvxCohortFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen = freeze()

    def test_exact_selection_reserve_split_ood_and_milestones(self) -> None:
        frozen = self.frozen
        selection = frozen.selection_manifest
        self.assertEqual(len(selection["selected_lineages"]), 1000)
        self.assertEqual(len(selection["reserve_lineages"]), 50)
        self.assertEqual(sum(selection["selected_counts"].values()), 1000)
        self.assertFalse(set(selection["selected_lineages"]) & set(selection["reserve_lineages"]))
        self.assertEqual(selection["ood_lineage_count"], 60)
        self.assertEqual(
            frozen.private_split["counts"],
            {
                "development": 500,
                "calibration": 200,
                "blind": 300,
                "reserve": 50,
            },
        )
        self.assertEqual(
            {name: len(lineages) for name, lineages in frozen.visible_milestones.items()},
            {"n12": 12, "n30": 30, "n100": 100, "n300": 300},
        )
        self.assertLess(
            set(frozen.visible_milestones["n12"]),
            set(frozen.visible_milestones["n30"]),
        )
        self.assertLess(
            set(frozen.visible_milestones["n30"]),
            set(frozen.visible_milestones["n100"]),
        )
        self.assertLess(
            set(frozen.visible_milestones["n100"]),
            set(frozen.visible_milestones["n300"]),
        )

    def test_selected_records_materialise_final_split_and_scope(self) -> None:
        rows = self.frozen.selected_records
        self.assertEqual(len(rows), 1000)
        self.assertTrue(all("forced_split" in row and "blind_scope" in row for row in rows))
        ood = [row for row in rows if row["blind_scope"] == "OOD"]
        self.assertEqual(len(ood), 60)
        self.assertTrue(
            all(row["forced_split"] == "blind" and row["split"] == "blind" for row in ood)
        )
        self.assertNotIn("terminal_status", rows[0])
        self.assertNotIn("hd95", rows[0])
        blind = [row for row in rows if row["split"] == "blind"]
        self.assertTrue(
            all(
                row["blind_scope"] in {"IID", "OOD"}
                if row["selection_stratum"] == "objaverse"
                else row["blind_scope"] == "TRANSFER"
                for row in blind
            )
        )
        self.assertTrue(
            all(
                row["blind_scope"] == "NONE"
                for row in rows
                if row["split"] in {"development", "calibration"}
            )
        )

    def test_public_and_visible_outputs_do_not_leak_blind_or_reserve(self) -> None:
        frozen = self.frozen
        protected_rows = [
            row
            for row in frozen.private_split["assignments"]
            if row["split"] in {"blind", "reserve"}
        ]
        released = canonical_json_bytes(
            {
                "public": frozen.custody_public,
                "visible": frozen.custody_visible,
                "milestones": frozen.visible_milestones,
            }
        ).decode("utf-8")
        for row in protected_rows:
            self.assertNotIn(row["lineage_id"], released)
            self.assertNotIn(row["source_path"], released)
        self.assertNotIn("assignments", frozen.custody_public)
        self.assertEqual(
            {row["split"] for row in frozen.custody_visible["assignments"]},
            {"development", "calibration"},
        )

    def test_commitments_and_hashes_are_cross_artifact_consistent(self) -> None:
        frozen = self.frozen
        commitment = frozen.custody_public["private_manifest_commitment_sha256"]
        self.assertEqual(
            commitment,
            frozen.custody_visible["private_manifest_commitment_sha256"],
        )
        self.assertEqual(
            commitment,
            frozen.selection_manifest["private_manifest_commitment_sha256"],
        )
        for mapping in (
            frozen.selection_manifest["hashes"],
            frozen.selection_manifest["code_hashes"],
        ):
            self.assertTrue(all(len(value) == 64 for value in mapping.values()))

    def test_input_order_and_outcome_fields_are_irrelevant(self) -> None:
        first_rows = synthetic_records()
        clean_rows = copy.deepcopy(first_rows)
        for row in clean_rows:
            row.pop("terminal_status")
            row.pop("hd95")
        random.Random(20260806).shuffle(clean_rows)
        self.assertEqual(freeze(first_rows), freeze(clean_rows))

    def test_sealed_eligible_record_commitment_detects_removal_or_exchange(self) -> None:
        original = synthetic_records()
        commitment = eligible_records_sha256(original)
        removed = copy.deepcopy(original[:-1])
        exchanged = copy.deepcopy(original)
        exchanged[0]["source_uid"] = "uid:unexpected-exchange"
        for changed in (removed, exchanged):
            with (
                self.subTest(size=len(changed)),
                self.assertRaisesRegex(CohortFreezeError, "differs from the sealed P2a commitment"),
            ):
                precommit = precommit_for(commitment)
                publication_receipt, trusted_publishers = publication_for(precommit)
                _freeze_cohort_impl(
                    changed,
                    protocol_root_sha256=PROTOCOL_ROOT,
                    snapshot_sha256=SNAPSHOT,
                    expected_input_records_sha256=commitment,
                    selection_seed_hex=SELECTION_SEED,
                    split_secret_hex=SPLIT_SECRET,
                    exact_targets=EXACT_TARGETS,
                    precommit=precommit,
                    publication_receipt=publication_receipt,
                    trusted_publishers=trusted_publishers,
                    allow_synthetic_receipt=True,
                    allow_public_test_secrets=True,
                )

    def test_freeze_requires_a_matching_preexisting_public_precommit(self) -> None:
        rows = synthetic_records()
        input_hash = eligible_records_sha256(rows)
        good_precommit = precommit_for(input_hash)
        publication_receipt, trusted_publishers = publication_for(good_precommit)
        arguments = {
            "protocol_root_sha256": PROTOCOL_ROOT,
            "snapshot_sha256": SNAPSHOT,
            "expected_input_records_sha256": input_hash,
            "selection_seed_hex": SELECTION_SEED,
            "split_secret_hex": SPLIT_SECRET,
            "exact_targets": EXACT_TARGETS,
            "publication_receipt": publication_receipt,
            "trusted_publishers": trusted_publishers,
            "allow_synthetic_receipt": True,
            "allow_public_test_secrets": True,
        }
        with self.assertRaisesRegex(CohortFreezeError, "precommit verification failed"):
            _freeze_cohort_impl(rows, precommit={}, **arguments)

        changed = copy.deepcopy(good_precommit)
        changed["snapshot_sha256"] = "c" * 64
        with self.assertRaisesRegex(CohortFreezeError, "precommit verification failed"):
            _freeze_cohort_impl(rows, precommit=changed, **arguments)

    def test_every_freeze_artifact_is_linked_to_one_precommit_and_freeze_id(self) -> None:
        frozen = self.frozen
        freeze_ids = {
            frozen.selection_manifest["freeze_id"],
            frozen.private_split["freeze_id"],
            frozen.custody_public["freeze_id"],
            frozen.custody_visible["freeze_id"],
            frozen.milestone_manifest["freeze_id"],
        }
        precommit_hashes = {
            frozen.selection_manifest["precommit_sha256"],
            frozen.private_split["precommit_sha256"],
            frozen.custody_public["precommit_sha256"],
            frozen.custody_visible["precommit_sha256"],
            frozen.milestone_manifest["precommit_sha256"],
        }
        publication_receipt_hashes = {
            frozen.selection_manifest["publication_receipt_sha256"],
            frozen.private_split["publication_receipt_sha256"],
            frozen.custody_public["publication_receipt_sha256"],
            frozen.custody_visible["publication_receipt_sha256"],
            frozen.milestone_manifest["publication_receipt_sha256"],
        }
        self.assertEqual(len(freeze_ids), 1)
        self.assertEqual(len(precommit_hashes), 1)
        self.assertEqual(len(publication_receipt_hashes), 1)

    def test_freeze_requires_production_authorised_signed_publication_receipt(self) -> None:
        rows = synthetic_records()
        input_hash = eligible_records_sha256(rows)
        precommit = precommit_for(input_hash)
        receipt, trusted = publication_for(precommit)
        arguments = {
            "protocol_root_sha256": PROTOCOL_ROOT,
            "snapshot_sha256": SNAPSHOT,
            "expected_input_records_sha256": input_hash,
            "selection_seed_hex": SELECTION_SEED,
            "split_secret_hex": SPLIT_SECRET,
            "exact_targets": EXACT_TARGETS,
            "precommit": precommit,
            "publication_receipt": receipt,
            "trusted_publishers": trusted,
            "allow_public_test_secrets": True,
        }
        with self.assertRaisesRegex(CohortFreezeError, "cannot be supplied"):
            _freeze_cohort_impl(rows, **arguments)

        tampered = copy.deepcopy(receipt)
        tampered["object_version_id"] = "tampered"
        arguments["publication_receipt"] = tampered
        arguments["allow_synthetic_receipt"] = True
        with self.assertRaisesRegex(CohortFreezeError, "object version"):
            _freeze_cohort_impl(rows, **arguments)

    def test_g1_requires_source_audit_licence_and_structured_fixture_exception(self) -> None:
        corruptions = (
            ("source hash", "objaverse", "source_sha256", "invalid", "source_sha256"),
            ("topology", "objaverse", "topology_status", "W", "topology_status"),
            ("quantile", "objaverse", "complexity_quantile", 10, "complexity_quantile"),
            ("format", "objaverse", "format_status", "", "format_status"),
            ("licence", "objaverse", "licence_status", "UNKNOWN", "lawful internal use"),
            ("fixture", "fixtures_C0_C9", "fixture_exception", None, "fixture_exception"),
        )
        for name, stratum, field, value, message in corruptions:
            rows = synthetic_records()
            row = next(record for record in rows if record["selection_stratum"] == stratum)
            if value is None:
                row.pop(field)
            else:
                row[field] = value
            with self.subTest(name=name), self.assertRaisesRegex(CohortFreezeError, message):
                eligible_records_sha256(rows)

    def test_rejects_invalid_hash_weak_secret_and_non_protocol_targets(self) -> None:
        with self.assertRaisesRegex(CohortFreezeError, "protocol_root_sha256"):
            _freeze_cohort_impl(
                synthetic_records(),
                protocol_root_sha256="A" * 64,
                snapshot_sha256=SNAPSHOT,
                expected_input_records_sha256=eligible_records_sha256(synthetic_records()),
                selection_seed_hex=SELECTION_SEED,
                split_secret_hex=SPLIT_SECRET,
                exact_targets=EXACT_TARGETS,
                precommit={},
                allow_synthetic_receipt=True,
                allow_public_test_secrets=True,
            )
        with self.assertRaisesRegex(CohortFreezeError, "appears weak"):
            _freeze_cohort_impl(
                synthetic_records(),
                protocol_root_sha256=PROTOCOL_ROOT,
                snapshot_sha256=SNAPSHOT,
                expected_input_records_sha256=eligible_records_sha256(synthetic_records()),
                selection_seed_hex=SELECTION_SEED,
                split_secret_hex="00" * 32,
                exact_targets=EXACT_TARGETS,
                precommit=precommit_for(eligible_records_sha256(synthetic_records())),
                allow_synthetic_receipt=True,
                allow_public_test_secrets=True,
            )
        changed = copy.deepcopy(EXACT_TARGETS)
        changed["plants"]["development"] = 4
        with self.assertRaisesRegex(CohortFreezeError, "does not sum"):
            _freeze_cohort_impl(
                synthetic_records(),
                protocol_root_sha256=PROTOCOL_ROOT,
                snapshot_sha256=SNAPSHOT,
                expected_input_records_sha256=eligible_records_sha256(synthetic_records()),
                selection_seed_hex=SELECTION_SEED,
                split_secret_hex=SPLIT_SECRET,
                exact_targets=changed,
                precommit=precommit_for(eligible_records_sha256(synthetic_records())),
                allow_synthetic_receipt=True,
                allow_public_test_secrets=True,
            )
        margin_preserving_change = copy.deepcopy(EXACT_TARGETS)
        margin_preserving_change["fixtures_C0_C9"]["development"] -= 1
        margin_preserving_change["fixtures_C0_C9"]["calibration"] += 1
        margin_preserving_change["objaverse"]["development"] += 1
        margin_preserving_change["objaverse"]["calibration"] -= 1
        with self.assertRaisesRegex(CohortFreezeError, "every frozen P0"):
            _freeze_cohort_impl(
                synthetic_records(),
                protocol_root_sha256=PROTOCOL_ROOT,
                snapshot_sha256=SNAPSHOT,
                expected_input_records_sha256=eligible_records_sha256(synthetic_records()),
                selection_seed_hex=SELECTION_SEED,
                split_secret_hex=SPLIT_SECRET,
                exact_targets=margin_preserving_change,
                precommit=precommit_for(eligible_records_sha256(synthetic_records())),
                allow_synthetic_receipt=True,
                allow_public_test_secrets=True,
            )

    def test_fails_closed_if_custody_release_injects_a_blind_identifier(self) -> None:
        import morphoia.mvx.cohort as cohort_module

        original = cohort_module.create_custody_release

        def leaking_release(private_manifest, secret, **kwargs):
            release = original(private_manifest, secret, **kwargs)
            blind = next(row for row in private_manifest["assignments"] if row["split"] == "blind")
            release["public_manifest"]["leaked_identifier"] = blind["lineage_id"]
            return release

        with (
            mock.patch.object(cohort_module, "create_custody_release", leaking_release),
            self.assertRaisesRegex(CohortFreezeError, "leaks blind/reserve"),
        ):
            freeze()

    def test_fails_closed_if_milestone_injects_a_blind_identifier(self) -> None:
        import morphoia.mvx.cohort as cohort_module

        original = cohort_module.select_visible_milestones

        def leaking_milestones(records, *, selection_seed_hex, compositions=None):
            output = original(
                records,
                selection_seed_hex=selection_seed_hex,
                compositions=compositions,
            )
            output["n12"] = (*output["n12"][:-1], "INJECTED-BLIND-ID")
            return output

        with (
            mock.patch.object(cohort_module, "select_visible_milestones", leaking_milestones),
            self.assertRaisesRegex(CohortFreezeError, "code hashes differ|nested visible subset"),
        ):
            freeze()


if __name__ == "__main__":
    unittest.main()
