# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from morphoia.engine_ir_contract import load_json_strict
from morphoia.engine_ir_migration import MigrationError, build_legacy_migration_content

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "engine-ir" / "0.1.0" / "migration"


def load_metadata() -> dict:
    return load_json_strict((FIXTURE_ROOT / "metadata.json").read_bytes())


class EngineIrMigrationTests(unittest.TestCase):
    def test_explicit_migration_matches_golden_and_preserves_input_bytes(self) -> None:
        source_path = FIXTURE_ROOT / "legacy-input.json"
        raw = source_path.read_bytes()
        before = hashlib.sha256(raw).hexdigest()
        expected = load_json_strict((FIXTURE_ROOT / "expected-content.json").read_bytes())
        result = build_legacy_migration_content(
            raw,
            metadata=load_metadata(),
        )
        self.assertEqual(result, expected)
        self.assertEqual(source_path.read_bytes(), raw)
        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), before)
        self.assertEqual(result["losses"][0]["category"], "identity")
        self.assertEqual(len(result["losses"]), 4)
        self.assertEqual(
            result["provenance"][0]["activity"],
            "explicit-legacy-domain-migration",
        )

    def test_migration_requires_every_metadata_field_and_rejects_unknowns(self) -> None:
        raw = (FIXTURE_ROOT / "legacy-input.json").read_bytes()
        for field in load_metadata():
            with self.subTest(field=field):
                metadata = load_metadata()
                metadata.pop(field)
                with self.assertRaisesRegex(MigrationError, "missing"):
                    build_legacy_migration_content(
                        raw,
                        metadata=metadata,
                    )
        metadata = load_metadata()
        metadata["implicit_repair"] = True
        with self.assertRaisesRegex(MigrationError, "unknown"):
            build_legacy_migration_content(
                raw,
                metadata=metadata,
            )

    def test_migration_rejects_payload_identity_and_legacy_domain_mutations(self) -> None:
        raw = (FIXTURE_ROOT / "legacy-input.json").read_bytes()
        mutations = (
            lambda metadata: metadata["source_artifact"].__setitem__("sha256", "f" * 64),
            lambda metadata: metadata["source_artifact"].__setitem__("size_bytes", 1),
            lambda metadata: metadata["source_artifact"].__setitem__(
                "uri", "morphoia-cas://sha256/" + "f" * 64
            ),
            lambda metadata: metadata["source_artifact"].__setitem__(
                "media_type", "application/json"
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                metadata = load_metadata()
                mutate(metadata)
                with self.assertRaises(MigrationError):
                    build_legacy_migration_content(
                        raw,
                        metadata=metadata,
                    )

        legacy = json.loads(raw)
        legacy["format"] = "morphoia.engine.ir-manifest"
        changed_raw = (json.dumps(legacy, separators=(",", ":")) + "\n").encode()
        metadata = load_metadata()
        digest = hashlib.sha256(changed_raw).hexdigest()
        metadata["source_artifact"].update(
            {
                "sha256": digest,
                "size_bytes": len(changed_raw),
                "uri": f"morphoia-cas://sha256/{digest}",
            }
        )
        with self.assertRaises(MigrationError):
            build_legacy_migration_content(
                changed_raw,
                metadata=metadata,
            )

    def test_migration_returns_only_unsealed_content_without_engine_identity(self) -> None:
        raw = (FIXTURE_ROOT / "legacy-input.json").read_bytes()
        legacy = json.loads(raw)
        content = build_legacy_migration_content(raw, metadata=load_metadata())
        self.assertNotIn("identity", content)
        self.assertNotIn("format", content)
        self.assertIn(legacy["semantic_sha256"], content["losses"][0]["before"])

    def test_migration_does_not_mutate_caller_metadata(self) -> None:
        raw = (FIXTURE_ROOT / "legacy-input.json").read_bytes()
        metadata = load_metadata()
        before = copy.deepcopy(metadata)
        build_legacy_migration_content(
            raw,
            metadata=metadata,
        )
        self.assertEqual(metadata, before)


if __name__ == "__main__":
    unittest.main()
