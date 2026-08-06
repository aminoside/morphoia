from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import unittest
from datetime import UTC, datetime
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from morphoia.mvx import custody as custody_module
from morphoia.mvx.cli import configure_mvx_parser
from morphoia.mvx.cohort import freeze_cohort
from morphoia.mvx.custody import (
    G1_BLOCKED_STATE,
    G1_READY_STATE,
    PUBLICATION_RECEIPT_ALGORITHM_ID,
    CustodyValidationError,
    canonical_json_bytes,
    create_custody_precommit,
    create_custody_release,
    sha256_hex,
    synthetic_dry_run,
    validate_custody_precommit,
    validate_precommit_publication_receipt,
    validate_trusted_publishers,
    verify_custody_precommit,
    verify_private_manifest_commitment,
)

SECRET = bytes.fromhex("00112233445566778899aabbccddeeff102132435465768798a9bacbdcedfe0f")
SELECTION_SECRET = bytes.fromhex(
    "3a6b4ecb2823191a9db74b71ad660824e0515b37f8e0555ea2bc5732d3cd4856"
)


def production_publication_fixture(
    precommit: dict[str, str],
    *,
    published_at: str = "2026-08-06T12:01:00Z",
    sequence: int = 7,
    object_locator: str = "https://publisher.invalid/object-lock/precommit",
    object_version_id: str = "worm-v7",
    receipt_registry_sha256: str | None = None,
) -> tuple[dict[str, object], custody_module._ProductionTrustContext]:
    private_key = Ed25519PrivateKey.from_private_bytes(
        hashlib.sha256(b"MVX production publisher unit-test key").digest()
    )
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    registry = validate_trusted_publishers(
        {
            "schema_version": "0.2.0",
            "registry_epoch": 7,
            "publishers": [
                {
                    "publisher_id": "MVX-UNIT-TEST-WORM",
                    "public_key_ed25519_hex": public_key.hex(),
                    "store_kinds": ["OBJECT_LOCK_VERSION"],
                    "production": True,
                    "valid_from": "2026-08-06T12:00:00Z",
                    "valid_until": "2027-08-06T12:00:00Z",
                    "sequence_minimum": 7,
                    "sequence_maximum": 9,
                    "object_locator_pattern": "^https://publisher[.]invalid/object-lock/precommit$",
                    "object_version_id_pattern": "^worm-v[7-9]$",
                }
            ],
            "g1_state": G1_READY_STATE,
        }
    )
    registry_sha256 = hashlib.sha256(b"exact sealed registry bytes\n").hexdigest()
    seal_sha256 = hashlib.sha256(b"exact G0 seal bytes\n").hexdigest()
    context = custody_module._ProductionTrustContext(
        registry=registry,
        registry_sha256=registry_sha256,
        registry_epoch=registry["registry_epoch"],
        g0_seal_sha256=seal_sha256,
        g0_sealed_at=datetime(2026, 8, 6, 12, 0, 0, tzinfo=UTC),
    )
    precommit_sha256 = sha256_hex(precommit)
    core = {
        "schema_version": "0.2.0",
        "algorithm_id": PUBLICATION_RECEIPT_ALGORITHM_ID,
        "publisher_id": "MVX-UNIT-TEST-WORM",
        "store_kind": "OBJECT_LOCK_VERSION",
        "object_locator": object_locator,
        "object_version_id": object_version_id,
        "sequence": sequence,
        "published_at": published_at,
        "trusted_publishers_sha256": (
            registry_sha256
            if receipt_registry_sha256 is None
            else receipt_registry_sha256
        ),
        "registry_epoch": registry["registry_epoch"],
        "g0_seal_sha256": seal_sha256,
        "protocol_root_sha256": precommit["protocol_root_sha256"],
        "snapshot_sha256": precommit["snapshot_sha256"],
        "eligible_records_sha256": precommit["eligible_records_sha256"],
        "freeze_id": precommit["freeze_id"],
        "precommit_sha256": precommit_sha256,
        "published_object_sha256": precommit_sha256,
        "state": "PUBLISHED_IMMUTABLE",
    }
    return (
        {
            **core,
            "signature_ed25519_hex": private_key.sign(canonical_json_bytes(core)).hex(),
        },
        context,
    )


def synthetic_publication_receipt(
    precommit: dict[str, str],
) -> tuple[dict[str, object], dict[str, object]]:
    """Create the non-production signed fixture; never imported by package code."""

    private_key = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(
            "9d61b19deffd5a60ba844af492ec2cc4"
            "4449c5697b326919703bac031cae7f60"
        )
    )
    registry = validate_trusted_publishers(
        {
            "schema_version": "0.2.0",
            "registry_epoch": 1,
            "publishers": [
                {
                    "publisher_id": "MVX-SYNTHETIC-PUBLISHER-ONLY",
                    "public_key_ed25519_hex": (
                        "d75a980182b10ab7d54bfed3c964073a"
                        "0ee172f3daa62325af021a68f707511a"
                    ),
                    "store_kinds": ["SYNTHETIC_TEST_ONLY"],
                    "production": False,
                    "valid_from": "2026-08-06T00:00:00Z",
                    "valid_until": "2099-12-31T23:59:59Z",
                    "sequence_minimum": 1,
                    "sequence_maximum": 9007199254740991,
                    "object_locator_pattern": "^synthetic://immutable/precommit$",
                    "object_version_id_pattern": "^synthetic-sequence-[1-9][0-9]*$",
                }
            ],
            "g1_state": G1_BLOCKED_STATE,
        }
    )
    precommit_hash = sha256_hex(precommit)
    core = {
        "schema_version": "0.2.0",
        "algorithm_id": PUBLICATION_RECEIPT_ALGORITHM_ID,
        "publisher_id": "MVX-SYNTHETIC-PUBLISHER-ONLY",
        "store_kind": "SYNTHETIC_TEST_ONLY",
        "object_locator": "synthetic://immutable/precommit",
        "object_version_id": "synthetic-sequence-1",
        "sequence": 1,
        "published_at": "2026-08-06T00:00:00Z",
        "trusted_publishers_sha256": sha256_hex(canonical_json_bytes(registry) + b"\n"),
        "registry_epoch": registry["registry_epoch"],
        "g0_seal_sha256": "0" * 64,
        "protocol_root_sha256": precommit["protocol_root_sha256"],
        "snapshot_sha256": precommit["snapshot_sha256"],
        "eligible_records_sha256": precommit["eligible_records_sha256"],
        "freeze_id": precommit["freeze_id"],
        "precommit_sha256": precommit_hash,
        "published_object_sha256": precommit_hash,
        "state": "PUBLISHED_IMMUTABLE",
    }
    receipt = {
        **core,
        "signature_ed25519_hex": private_key.sign(canonical_json_bytes(core)).hex(),
    }
    custody_module._validate_precommit_publication_receipt(
        receipt,
        precommit=precommit,
        trusted_publishers=registry,
        allow_synthetic=True,
    )
    return receipt, registry


def public_precommit() -> dict[str, str]:
    return create_custody_precommit(
        protocol_root_sha256="a" * 64,
        snapshot_sha256="b" * 64,
        eligible_records_sha256="c" * 64,
        configuration_sha256="d" * 64,
        selection_seed=SELECTION_SECRET,
        split_salt=SECRET,
        allow_public_test_secrets=True,
    )


def private_manifest() -> dict[str, object]:
    precommit = public_precommit()
    publication_receipt, _ = synthetic_publication_receipt(precommit)
    return {
        "schema_version": "0.1.0",
        "algorithm_id": "MVX-GROUP-STRATIFIED-HMAC-2",
        "algorithm_version": "2.0.0",
        "protocol_root_sha256": "a" * 64,
        "salt_sha256": precommit["split_salt_sha256"],
        "selection_seed_sha256": precommit["selection_seed_sha256"],
        "precommit_sha256": sha256_hex(precommit),
        "publication_receipt_sha256": sha256_hex(publication_receipt),
        "freeze_id": precommit["freeze_id"],
        "assignments": [
            {
                "lineage_id": "VISIBLE-DEV-LINEAGE",
                "leakage_group_id": "VISIBLE-DEV-GROUP",
                "split": "development",
                "selection_stratum": "objaverse",
                "blind_scope": "NONE",
                "creator_group": "CREATOR-DEV-001",
                "source_uid": "SOURCE-DEV-001",
                "source_path": "/corpus/development/object.glb",
                "source_sha256": "c" * 64,
            },
            {
                "lineage_id": "VISIBLE-CAL-LINEAGE",
                "leakage_group_id": "VISIBLE-CAL-GROUP",
                "split": "calibration",
                "selection_stratum": "scan",
                "blind_scope": "NONE",
                "creator_group": "CREATOR-CAL-001",
                "source_uid": "SOURCE-CAL-001",
                "source_path": "/corpus/calibration/object.glb",
                "source_sha256": "d" * 64,
            },
            {
                "lineage_id": "SECRET-BLIND-LINEAGE",
                "leakage_group_id": "SECRET-BLIND-GROUP",
                "split": "blind",
                "blind_scope": "IID",
                "selection_stratum": "objaverse",
                "creator_group": "CREATOR-BLIND-001",
                "source_uid": "SOURCE-BLIND-001",
                "source_path": "/private/holdout/secret-blind-object.glb",
                "source_sha256": "e" * 64,
            },
            {
                "lineage_id": "SECRET-RESERVE-LINEAGE",
                "leakage_group_id": "SECRET-RESERVE-GROUP",
                "split": "reserve",
                "selection_stratum": "objaverse",
                "blind_scope": "NONE",
                "creator_group": "CREATOR-RESERVE-001",
                "source_uid": "SOURCE-RESERVE-001",
                "source_path": "/private/reserve/secret-reserve-object.glb",
                "source_sha256": "f" * 64,
            },
        ],
        "counts": {"development": 1, "calibration": 1, "blind": 1, "reserve": 1},
        "deviations": [],
    }


def fixture_release(manifest, secret=SECRET):
    return create_custody_release(
        manifest,
        secret,
        allow_public_test_secret=True,
    )


def fixture_verify(manifest, secret, commitment):
    return verify_private_manifest_commitment(
        manifest,
        secret,
        commitment,
        allow_public_test_secret=True,
    )


class CustodyTests(unittest.TestCase):
    def test_production_surfaces_expose_no_trust_or_synthetic_injection(self) -> None:
        forbidden = {
            "trusted_publishers",
            "trusted_publishers_path",
            "allow_synthetic",
            "allow_synthetic_receipt",
            "verification_clock",
        }
        for surface in (validate_precommit_publication_receipt, freeze_cohort):
            with self.subTest(surface=surface.__name__):
                parameters = set(inspect.signature(surface).parameters)
                self.assertTrue(forbidden.isdisjoint(parameters), parameters & forbidden)
        self.assertNotIn("_validate_precommit_publication_receipt", custody_module.__all__)
        self.assertNotIn("Ed25519PrivateKey", custody_module.__dict__)

    def test_precommit_is_deterministic_valid_and_binds_both_preimages(self) -> None:
        first = public_precommit()
        second = public_precommit()
        self.assertEqual(first, second)
        self.assertEqual(validate_custody_precommit(first), first)
        self.assertEqual(
            verify_custody_precommit(
                first,
                protocol_root_sha256="a" * 64,
                snapshot_sha256="b" * 64,
                eligible_records_sha256="c" * 64,
                configuration_sha256="d" * 64,
                selection_seed=SELECTION_SECRET,
                split_salt=SECRET,
                allow_public_test_secrets=True,
            ),
            first,
        )
        serialized = canonical_json_bytes(first).decode("utf-8")
        self.assertNotIn(SELECTION_SECRET.hex(), serialized)
        self.assertNotIn(SECRET.hex(), serialized)

    def test_precommit_rejects_mismatch_or_equal_secrets(self) -> None:
        with self.assertRaisesRegex(CustodyValidationError, "mismatch"):
            verify_custody_precommit(
                public_precommit(),
                protocol_root_sha256="a" * 64,
                snapshot_sha256="b" * 64,
                eligible_records_sha256="c" * 64,
                configuration_sha256="d" * 64,
                selection_seed=bytes(reversed(SELECTION_SECRET)),
                split_salt=SECRET,
                allow_public_test_secrets=True,
            )
        with self.assertRaisesRegex(CustodyValidationError, "independent"):
            create_custody_precommit(
                protocol_root_sha256="a" * 64,
                snapshot_sha256="b" * 64,
                eligible_records_sha256="c" * 64,
                configuration_sha256="d" * 64,
                selection_seed=SECRET,
                split_salt=SECRET,
                allow_public_test_secrets=True,
            )

    def test_signed_publication_receipt_binds_precommit_and_rejects_tampering(self) -> None:
        precommit = public_precommit()
        receipt, registry = synthetic_publication_receipt(precommit)
        self.assertEqual(
            custody_module._validate_precommit_publication_receipt(
                receipt,
                precommit=precommit,
                trusted_publishers=registry,
                allow_synthetic=True,
            ),
            receipt,
        )
        with self.assertRaises(TypeError):
            validate_precommit_publication_receipt(
                receipt,
                precommit=precommit,
                trusted_publishers=registry,
            )
        changed = copy.deepcopy(receipt)
        changed["object_version_id"] = "tampered-version"
        with self.assertRaisesRegex(CustodyValidationError, "object version"):
            custody_module._validate_precommit_publication_receipt(
                changed,
                precommit=precommit,
                trusted_publishers=registry,
                allow_synthetic=True,
            )

    def test_production_uses_only_sealed_registry_and_accepts_safe_ready_fixture(self) -> None:
        precommit = public_precommit()
        receipt, context = production_publication_fixture(precommit)
        now = datetime(2026, 8, 6, 12, 2, 0, tzinfo=UTC)
        with (
            mock.patch.object(
                custody_module,
                "_load_production_trust_context",
                return_value=context,
            ) as loader,
            mock.patch.object(custody_module, "_utc_now", return_value=now),
        ):
            self.assertEqual(
                validate_precommit_publication_receipt(receipt, precommit=precommit),
                receipt,
            )
        loader.assert_called_once_with(precommit["protocol_root_sha256"])

        rogue_registry = copy.deepcopy(context.registry)
        rogue_registry["registry_epoch"] += 1
        with self.assertRaises(TypeError):
            validate_precommit_publication_receipt(
                receipt,
                precommit=precommit,
                trusted_publishers=rogue_registry,
            )

    def test_production_receipt_rejects_raw_registry_alias_backdate_future_and_bounds(self) -> None:
        precommit = public_precommit()
        cases = (
            (
                "alternate registry bytes",
                {
                    "receipt_registry_sha256": hashlib.sha256(
                        b"{  alternate whitespace but same JSON  }\n"
                    ).hexdigest()
                },
                "trusted_publishers_sha256",
            ),
            ("backdated", {"published_at": "2026-08-06T11:59:59Z"}, "G0 seal"),
            ("future", {"published_at": "2026-08-06T12:07:01Z"}, "future"),
            ("sequence", {"sequence": 10}, "sequence"),
            (
                "untrusted locator",
                {"object_locator": "https://attacker.invalid/object-lock/precommit"},
                "object locator",
            ),
            ("version", {"object_version_id": "worm-v10"}, "object version"),
        )
        now = datetime(2026, 8, 6, 12, 2, 0, tzinfo=UTC)
        for name, overrides, expected_message in cases:
            with self.subTest(case=name):
                receipt, context = production_publication_fixture(precommit, **overrides)
                with (
                    mock.patch.object(
                        custody_module,
                        "_load_production_trust_context",
                        return_value=context,
                    ),
                    mock.patch.object(custody_module, "_utc_now", return_value=now),
                    self.assertRaisesRegex(CustodyValidationError, expected_message),
                ):
                    validate_precommit_publication_receipt(receipt, precommit=precommit)

    def test_production_receipt_rejects_a_fake_signer_for_a_trusted_identity(self) -> None:
        precommit = public_precommit()
        receipt, context = production_publication_fixture(precommit)
        rogue_key = Ed25519PrivateKey.generate()
        core = {
            key: value
            for key, value in receipt.items()
            if key != "signature_ed25519_hex"
        }
        receipt["signature_ed25519_hex"] = rogue_key.sign(
            canonical_json_bytes(core)
        ).hex()
        with (
            mock.patch.object(
                custody_module,
                "_load_production_trust_context",
                return_value=context,
            ),
            mock.patch.object(
                custody_module,
                "_utc_now",
                return_value=datetime(2026, 8, 6, 12, 2, 0, tzinfo=UTC),
            ),
            self.assertRaisesRegex(CustodyValidationError, "signature verification"),
        ):
            validate_precommit_publication_receipt(receipt, precommit=precommit)

    def test_registry_state_invariants_and_current_normative_block_are_strict(self) -> None:
        _, synthetic = synthetic_publication_receipt(public_precommit())
        self.assertEqual(synthetic["g1_state"], G1_BLOCKED_STATE)

        blocked_with_production = copy.deepcopy(synthetic)
        blocked_with_production["publishers"][0].update(
            production=True,
            store_kinds=["OBJECT_LOCK_VERSION"],
            object_locator_pattern="^https://publisher[.]invalid/precommit$",
        )
        with self.assertRaisesRegex(CustodyValidationError, "synthetic test key"):
            validate_trusted_publishers(blocked_with_production)

        ready_with_synthetic = copy.deepcopy(synthetic)
        ready_with_synthetic["g1_state"] = G1_READY_STATE
        with self.assertRaisesRegex(CustodyValidationError, "READY"):
            validate_trusted_publishers(ready_with_synthetic)

    def test_cli_has_no_trusted_publisher_registry_override(self) -> None:
        parser = argparse.ArgumentParser()
        root_subparsers = parser.add_subparsers(dest="command", required=True)
        configure_mvx_parser(root_subparsers)
        mvx_parser = next(
            action.choices["mvx"]
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        cohort_parser = next(
            action.choices["cohort"]
            for action in mvx_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        freeze_parser = next(
            action.choices["freeze"]
            for action in cohort_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertNotIn("--trusted-publishers", freeze_parser._option_string_actions)

    def test_public_normative_secrets_are_rejected_in_production(self) -> None:
        for public_secret in (
            "713b129c8347d84b37685cca9ef0734e6599ca90691b852eacb561f4bef148f0",
            "5b627e7f79d5ba855bd52402bc7d8a487a970f52d659f5c7ff6f23997c98c10b",
        ):
            with self.subTest(secret=public_secret), self.assertRaisesRegex(
                CustodyValidationError, "public normative"
            ):
                create_custody_precommit(
                    protocol_root_sha256="a" * 64,
                    snapshot_sha256="b" * 64,
                    eligible_records_sha256="c" * 64,
                    configuration_sha256="d" * 64,
                    selection_seed=public_secret,
                    split_salt=hashlib.sha256(public_secret.encode("ascii")).digest(),
                )

    def test_canonical_json_and_hash_are_stable_across_key_order(self) -> None:
        first = {"z": [3, 2, 1], "a": {"é": True, "n": None}}
        second = {"a": {"n": None, "é": True}, "z": [3, 2, 1]}
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        self.assertEqual(sha256_hex(first), sha256_hex(second))
        self.assertNotIn(b" ", canonical_json_bytes(first))

    def test_release_redacts_blind_and_reserve_identifiers_and_paths(self) -> None:
        original = private_manifest()
        untouched = copy.deepcopy(original)
        release = fixture_release(original)
        self.assertEqual(original, untouched)

        public = release["public_manifest"]
        self.assertEqual(
            set(public),
            {
                "schema",
                "schema_version",
                "protocol_root_sha256",
                "algorithm_id",
                "freeze_id",
                "precommit_sha256",
                "publication_receipt_sha256",
                "selection_seed_commitment_sha256",
                "split_salt_commitment_sha256",
                "counts",
                "salt_commitment_sha256",
                "private_manifest_commitment_sha256",
            },
        )
        public_text = canonical_json_bytes(public).decode("utf-8")
        visible_text = canonical_json_bytes(release["visible_manifest"]).decode("utf-8")
        for secret_fragment in (
            "SECRET-BLIND-LINEAGE",
            "SECRET-BLIND-GROUP",
            "/private/holdout/secret-blind-object.glb",
            "SECRET-RESERVE-LINEAGE",
            "/private/reserve/secret-reserve-object.glb",
        ):
            self.assertNotIn(secret_fragment, public_text)
            self.assertNotIn(secret_fragment, visible_text)
        self.assertNotIn("assignments", public)
        self.assertEqual(
            {row["split"] for row in release["visible_manifest"]["assignments"]},
            {"development", "calibration"},
        )
        self.assertEqual(len(release["visible_manifest"]["assignments"]), 2)

    def test_commitments_are_stable_and_bind_private_manifest(self) -> None:
        manifest = private_manifest()
        first = fixture_release(manifest)
        second = fixture_release(copy.deepcopy(manifest), SECRET.hex())
        self.assertEqual(first, second)
        commitment = first["public_manifest"]["private_manifest_commitment_sha256"]
        self.assertTrue(fixture_verify(manifest, SECRET, commitment))

        changed = copy.deepcopy(manifest)
        changed["assignments"][0]["source_path"] = "/changed/object.glb"
        changed_release = fixture_release(changed)
        self.assertNotEqual(
            commitment,
            changed_release["public_manifest"]["private_manifest_commitment_sha256"],
        )
        self.assertFalse(fixture_verify(changed, SECRET, commitment))

    def test_duplicate_lineage_is_rejected(self) -> None:
        manifest = private_manifest()
        duplicate = copy.deepcopy(manifest["assignments"][0])
        duplicate["leakage_group_id"] = "OTHER-GROUP"
        duplicate["split"] = "blind"
        manifest["assignments"].append(duplicate)
        manifest["counts"]["blind"] += 1
        with self.assertRaisesRegex(CustodyValidationError, "duplicate lineage_id"):
            fixture_release(manifest)

    def test_leakage_group_crossing_splits_is_rejected(self) -> None:
        manifest = private_manifest()
        manifest["assignments"][2]["leakage_group_id"] = "VISIBLE-DEV-GROUP"
        with self.assertRaisesRegex(CustodyValidationError, "cross split boundaries"):
            fixture_release(manifest)

    def test_invalid_hash_and_count_mismatch_are_rejected(self) -> None:
        invalid_hash = private_manifest()
        invalid_hash["assignments"][0]["source_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(CustodyValidationError, "source_sha256"):
            fixture_release(invalid_hash)

        wrong_count = private_manifest()
        wrong_count["counts"]["blind"] = 2
        with self.assertRaisesRegex(CustodyValidationError, "does not match"):
            fixture_release(wrong_count)

    def test_weak_or_wrong_length_secret_is_rejected(self) -> None:
        weak_secrets = (
            b"\x00" * 32,
            b"0123456789abcdef0123456789abcdef",
            bytes(range(16)) * 2,
            b"too short",
        )
        for weak in weak_secrets:
            with self.subTest(secret=weak), self.assertRaises(CustodyValidationError):
                fixture_release(private_manifest(), weak)

    def test_synthetic_dry_run_is_deterministic_and_redacted(self) -> None:
        first = synthetic_dry_run()
        second = synthetic_dry_run()
        self.assertEqual(first, second)
        output = json.dumps(first, sort_keys=True)
        self.assertNotIn("SYNTH-BLIND-001", output)
        self.assertNotIn("/synthetic/private/blind.glb", output)
        self.assertEqual(first["public_manifest"]["counts"]["blind"], 1)

    def test_visible_allowlist_drops_unknown_fields_and_rejects_hidden_token_injection(self) -> None:
        manifest = private_manifest()
        manifest["assignments"][0]["untrusted_notes"] = (
            "SECRET-BLIND-LINEAGE /private/holdout/secret-blind-object.glb"
        )
        release = fixture_release(manifest)
        visible_text = canonical_json_bytes(release["visible_manifest"]).decode("utf-8")
        self.assertNotIn("untrusted_notes", visible_text)
        self.assertNotIn("SECRET-BLIND-LINEAGE", visible_text)

        injected = private_manifest()
        injected["assignments"][0]["category"] = "SECRET-BLIND-LINEAGE"
        with self.assertRaisesRegex(CustodyValidationError, "hidden sensitive tokens"):
            fixture_release(injected)


if __name__ == "__main__":
    unittest.main()
