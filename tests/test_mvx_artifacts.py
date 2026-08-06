from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_mvx_cohort import freeze, precommit_for, publication_for, synthetic_records

from morphoia.mvx import artifacts as artifacts_module
from morphoia.mvx.artifacts import (
    FreezeArtifactError,
    build_freeze_bundle_payloads,
    commit_freeze_transaction,
    validate_frozen_output_schemas,
)
from morphoia.mvx.cohort import eligible_records_sha256


class MvxFreezeArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = synthetic_records()
        cls.input_hash = eligible_records_sha256(cls.rows)
        cls.precommit = precommit_for(cls.input_hash)
        cls.publication_receipt, _ = publication_for(cls.precommit)
        cls.frozen = freeze(cls.rows)

    def _paths(self, root: Path) -> tuple[Path, Path]:
        private_parent = root / "custodian"
        release_parent = root / "release"
        private_parent.mkdir()
        release_parent.mkdir()
        return private_parent / "bundle", release_parent / "bundle"

    def _commit(
        self,
        *,
        private_directory: Path,
        release_directory: Path,
        fault_hook=None,
    ):
        """Exercise transaction mechanics behind an explicit test-only trust stub."""

        with mock.patch.object(
            artifacts_module,
            "validate_precommit_publication_receipt",
            return_value=self.publication_receipt,
        ) as verifier:
            result = commit_freeze_transaction(
                frozen=self.frozen,
                precommit=self.precommit,
                publication_receipt=self.publication_receipt,
                private_directory=private_directory,
                release_directory=release_directory,
                fault_hook=fault_hook,
            )
        verifier.assert_called_once_with(
            self.publication_receipt,
            precommit=self.precommit,
        )
        return result

    def test_every_frozen_output_validates_before_publication(self) -> None:
        validate_frozen_output_schemas(self.frozen)

    def test_public_artifact_surfaces_have_no_trust_bypass(self) -> None:
        forbidden = {
            "trusted_publishers",
            "trusted_publishers_path",
            "allow_synthetic",
            "allow_synthetic_receipt",
            "verification_clock",
        }
        for surface in (build_freeze_bundle_payloads, commit_freeze_transaction):
            with self.subTest(surface=surface.__name__):
                parameters = set(inspect.signature(surface).parameters)
                self.assertTrue(forbidden.isdisjoint(parameters), parameters & forbidden)

    def test_public_commit_rejects_synthetic_receipt_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private, release = self._paths(Path(temporary))
            with self.assertRaisesRegex(FreezeArtifactError, "production validation"):
                commit_freeze_transaction(
                    frozen=self.frozen,
                    precommit=self.precommit,
                    publication_receipt=self.publication_receipt,
                    private_directory=private,
                    release_directory=release,
                )
            self.assertFalse(private.exists())
            self.assertFalse(release.exists())

    def test_commit_is_idempotent_and_receipt_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private, release = self._paths(Path(temporary))
            first = self._commit(
                private_directory=private,
                release_directory=release,
            )
            second = self._commit(
                private_directory=private,
                release_directory=release,
            )

            self.assertEqual(first["status"], "COMMITTED")
            self.assertEqual(second["status"], "ALREADY_COMMITTED")
            self.assertTrue((private / "bundle-manifest.json").is_file())
            self.assertTrue((release / "bundle-manifest.json").is_file())
            self.assertTrue((release / "freeze-receipt.json").is_file())
            self.assertFalse((private / "freeze-receipt.json").exists())

    def test_interrupted_two_phase_commit_resumes_without_recomputing_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private, release = self._paths(Path(temporary))

            def fail_after_private(point: str) -> None:
                if point == "after:private-publish":
                    raise RuntimeError("synthetic crash")

            with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
                self._commit(
                    private_directory=private,
                    release_directory=release,
                    fault_hook=fail_after_private,
                )
            self.assertTrue(private.is_dir())
            self.assertFalse((release / "freeze-receipt.json").exists())

            resumed = self._commit(
                private_directory=private,
                release_directory=release,
            )
            self.assertEqual(resumed["status"], "COMMITTED")
            self.assertTrue((release / "freeze-receipt.json").is_file())

    def test_corrupt_existing_bundle_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private, release = self._paths(Path(temporary))
            self._commit(
                private_directory=private,
                release_directory=release,
            )
            (private / "selection-manifest.json").write_text("corrupt\n", encoding="utf-8")
            with self.assertRaisesRegex(FreezeArtifactError, "mismatch"):
                self._commit(
                    private_directory=private,
                    release_directory=release,
                )

    def test_hidden_orphan_in_existing_bundle_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private, release = self._paths(Path(temporary))
            self._commit(
                private_directory=private,
                release_directory=release,
            )
            (private / ".orphan").write_text("hidden extra\n", encoding="utf-8")
            with self.assertRaisesRegex(FreezeArtifactError, "extra=.*\\.orphan"):
                self._commit(
                    private_directory=private,
                    release_directory=release,
                )

    def test_expected_bundle_file_cannot_be_a_symlink_even_with_identical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private, release = self._paths(root)
            self._commit(
                private_directory=private,
                release_directory=release,
            )
            expected = private / "selection-manifest.json"
            external_copy = root / "matching-selection-manifest.json"
            external_copy.write_bytes(expected.read_bytes())
            expected.unlink()
            expected.symlink_to(external_copy)

            with self.assertRaisesRegex(FreezeArtifactError, "not a regular file"):
                self._commit(
                    private_directory=private,
                    release_directory=release,
                )

    def test_finite_float_bbox_is_serializable_and_schema_valid(self) -> None:
        rows = synthetic_records()
        rows[0]["bbox"] = [0.0, -1.25, 2.5, 3.0, 4.75, 6.0]
        frozen = freeze(rows)
        validate_frozen_output_schemas(frozen)

    def test_bbox_commitment_is_exact_and_rejects_non_finite_values(self) -> None:
        integer_rows = synthetic_records()
        float_rows = synthetic_records()
        integer_rows[0]["bbox"] = [0, -1, 2, 3, 4, 6]
        float_rows[0]["bbox"] = [0.0, -1.0, 2.0, 3.0, 4.0, 6.0]
        self.assertEqual(
            eligible_records_sha256(integer_rows),
            eligible_records_sha256(float_rows),
        )

        float_rows[0]["bbox"][5] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite"):
            eligible_records_sha256(float_rows)

        collision_rows = synthetic_records()
        collision_rows[0]["bbox"] = [2**53 + 1, 0, 0, 1, 1, 1]
        with self.assertRaisesRegex(ValueError, "exactly representable"):
            eligible_records_sha256(collision_rows)


if __name__ == "__main__":
    unittest.main()
