from __future__ import annotations

import inspect
import random
import unittest
from pathlib import Path

import yaml

from morphoia.mvx.selection import (
    ALGORITHM_ID,
    ALGORITHM_VERSION,
    COMPLEXITY_BOOTSTRAP_SEED_HEX,
    DEFAULT_TARGETS,
    DEFAULT_VISIBLE_MILESTONES,
    VISIBLE_MILESTONE_ALGORITHM_ID,
    VISIBLE_MILESTONE_ALGORITHM_VERSION,
    _rank,
    complexity_tie_rank,
    select_cohort,
    select_visible_milestones,
)
from morphoia.mvx.split import (
    ALGORITHM_ID as SPLIT_ALGORITHM_ID,
)
from morphoia.mvx.split import (
    ALGORITHM_VERSION as SPLIT_ALGORITHM_VERSION,
)
from morphoia.mvx.split import _hmac_hex

SEED = "11" * 32
ROOT = Path(__file__).resolve().parents[1]


def records() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    supply = dict(DEFAULT_TARGETS)
    supply["objaverse"] = 650
    for stratum, count in supply.items():
        for index in range(count):
            category = f"category-{index // 5:03d}" if stratum == "objaverse" else stratum
            rows.append(
                {
                    "lineage_id": f"{stratum}:L{index:04d}",
                    "leakage_group_id": f"{stratum}:G{index:04d}",
                    "selection_stratum": stratum,
                    "category": category,
                    "creator_group": f"creator-{stratum}-{index:04d}",
                    "source_uid": f"uid-{stratum}-{index:04d}",
                    "eligibility": "ELIGIBLE",
                }
            )
    return rows


class MvxSelectionTests(unittest.TestCase):
    def test_hmac_algorithms_use_new_versioned_contracts(self) -> None:
        self.assertEqual((ALGORITHM_ID, ALGORITHM_VERSION), ("MVX-COHORT-HMAC-2", "2.0.0"))
        self.assertEqual(
            (VISIBLE_MILESTONE_ALGORITHM_ID, VISIBLE_MILESTONE_ALGORITHM_VERSION),
            ("MVX-VISIBLE-MILESTONES-HMAC-2", "2.0.0"),
        )
        self.assertEqual(
            (SPLIT_ALGORITHM_ID, SPLIT_ALGORITHM_VERSION),
            ("MVX-GROUP-STRATIFIED-HMAC-2", "2.0.0"),
        )

    def test_length_prefixed_hmac_eliminates_separator_tuple_collision(self) -> None:
        key = bytes.fromhex(SEED)
        left = ("alpha\x1fbeta", "gamma")
        right = ("alpha", "beta\x1fgamma")
        self.assertEqual("\x1f".join(left), "\x1f".join(right))
        self.assertNotEqual(_rank(key, "adversarial", *left), _rank(key, "adversarial", *right))
        self.assertNotEqual(
            _hmac_hex(key, "adversarial", *left),
            _hmac_hex(key, "adversarial", *right),
        )

    def test_hmac_domains_are_cryptographically_separate(self) -> None:
        key = bytes.fromhex(SEED)
        self.assertNotEqual(
            _rank(key, "cohort-stratum", "objaverse", "G1"),
            _rank(key, "visible-milestone-stratum", "objaverse", "G1"),
        )

    def test_complexity_tie_break_uses_only_the_fixed_public_seed(self) -> None:
        self.assertEqual(
            COMPLEXITY_BOOTSTRAP_SEED_HEX,
            "713b129c8347d84b37685cca9ef0734e6599ca90691b852eacb561f4bef148f0",
        )
        self.assertEqual(tuple(inspect.signature(complexity_tie_rank).parameters), ("lineage_id",))
        self.assertEqual(complexity_tie_rank("LINEAGE-A"), complexity_tie_rank("LINEAGE-A"))
        self.assertNotEqual(complexity_tie_rank("LINEAGE-A"), complexity_tie_rank("LINEAGE-B"))

        selection_spec = yaml.safe_load(
            (ROOT / "docs/mvx/validation/p0/selection-spec.yaml").read_text(encoding="utf-8")
        )
        split_spec = yaml.safe_load(
            (ROOT / "docs/mvx/validation/p0/split-spec.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(split_spec["bootstrap_seed_hex"], COMPLEXITY_BOOTSTRAP_SEED_HEX)
        tie_break = selection_spec["complexity_quantile"]
        self.assertIn("fixed public", tie_break["tie_break_seed"].lower())
        self.assertIn("never the production selection seed", tie_break["tie_break_seed"])

    def test_exact_targets_ood_and_reserve(self) -> None:
        result = select_cohort(records(), selection_seed_hex=SEED)
        self.assertEqual(result.selected_counts, DEFAULT_TARGETS)
        self.assertEqual(len(result.selected_lineages), 1000)
        self.assertEqual(len(result.reserve_lineages), 50)
        self.assertEqual(len(result.ood_categories), 12)
        self.assertEqual(sum(value == "OOD" for value in result.blind_scope.values()), 60)
        self.assertEqual(set(result.forced_split.values()), {"blind"})

    def test_input_order_is_irrelevant(self) -> None:
        first_rows = records()
        second_rows = list(first_rows)
        random.Random(9).shuffle(second_rows)
        first = select_cohort(first_rows, selection_seed_hex=SEED)
        second = select_cohort(second_rows, selection_seed_hex=SEED)
        self.assertEqual(first, second)

    def test_outcomes_cannot_enter_contract(self) -> None:
        rows = records()
        rows[0]["hd95"] = 999
        rows[1]["terminal_status"] = "FAIL"
        with_outcomes = select_cohort(rows, selection_seed_hex=SEED)
        for row in rows:
            row.pop("hd95", None)
            row.pop("terminal_status", None)
        self.assertEqual(with_outcomes, select_cohort(rows, selection_seed_hex=SEED))

    def test_duplicate_lineage_is_rejected(self) -> None:
        rows = records()
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError, "occurs more than once"):
            select_cohort(rows, selection_seed_hex=SEED)

    def test_cross_stratum_group_is_rejected(self) -> None:
        rows = records()
        rows[0]["leakage_group_id"] = rows[-1]["leakage_group_id"]
        with self.assertRaisesRegex(ValueError, "one registered selection_stratum"):
            select_cohort(rows, selection_seed_hex=SEED)

    def test_creator_or_source_identity_must_be_inside_one_leakage_group(self) -> None:
        rows = records()
        rows[1]["creator_group"] = rows[0]["creator_group"]
        with self.assertRaisesRegex(ValueError, "creator_group values span"):
            select_cohort(rows, selection_seed_hex=SEED)

    def test_exact_target_infeasibility_is_not_silently_relaxed(self) -> None:
        rows = records()
        rows = [row for row in rows if row["selection_stratum"] != "plants"]
        with self.assertRaisesRegex(ValueError, "cannot satisfy exact target"):
            select_cohort(rows, selection_seed_hex=SEED)

    def test_visible_milestones_are_exact_nested_and_ignore_blind(self) -> None:
        rows: list[dict[str, object]] = []
        final_targets = DEFAULT_VISIBLE_MILESTONES["n300"]
        for stratum, count in final_targets.items():
            for index in range(count):
                rows.append(
                    {
                        "lineage_id": f"{stratum}-L{index:03d}",
                        "leakage_group_id": f"{stratum}-G{index:03d}",
                        "selection_stratum": stratum,
                        "split": "development" if index % 2 else "calibration",
                    }
                )
        rows.append(
            {
                "lineage_id": "BLIND-MUST-NOT-APPEAR",
                "leakage_group_id": "BLIND-GROUP",
                "selection_stratum": "objaverse",
                "split": "blind",
            }
        )
        milestones = select_visible_milestones(rows, selection_seed_hex=SEED)
        self.assertEqual(
            {name: len(value) for name, value in milestones.items()},
            {
                "n12": 12,
                "n30": 30,
                "n100": 100,
                "n300": 300,
            },
        )
        self.assertTrue(set(milestones["n12"]) < set(milestones["n30"]))
        self.assertTrue(set(milestones["n30"]) < set(milestones["n100"]))
        self.assertTrue(set(milestones["n100"]) < set(milestones["n300"]))
        self.assertNotIn("BLIND-MUST-NOT-APPEAR", milestones["n300"])

    def test_visible_milestone_atomic_infeasibility_fails(self) -> None:
        rows = [
            {
                "lineage_id": f"L{index}",
                "leakage_group_id": "PAIR" if index < 2 else f"G{index}",
                "selection_stratum": "fixtures_C0_C9",
                "split": "development",
            }
            for index in range(12)
        ]
        compositions = {
            "n12": {"fixtures_C0_C9": 11, "objaverse": 1},
            "n30": {"fixtures_C0_C9": 30},
            "n100": {"fixtures_C0_C9": 100},
            "n300": {"fixtures_C0_C9": 300},
        }
        with self.assertRaisesRegex(ValueError, "cannot satisfy exact target"):
            select_visible_milestones(
                rows,
                selection_seed_hex=SEED,
                compositions=compositions,
            )


if __name__ == "__main__":
    unittest.main()
