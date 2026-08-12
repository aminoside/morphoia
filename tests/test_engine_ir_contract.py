# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from morphoia.engine_ir_contract import (
    CANONICAL_PROFILE,
    MANIFEST_FORMAT,
    MANIFEST_MEDIA_TYPE,
    MANIFEST_SCHEMA_ID,
    MANIFEST_VERSION,
    MAX_INPUT_BYTES,
    MAX_SAFE_INTEGER,
    REPLAY_SCHEMA_ID,
    LexicalError,
    SchemaError,
    SemanticError,
    load_json_strict,
    validate_manifest,
    validate_replay,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas"
CORPUS_ROOT = ROOT / "tests" / "fixtures" / "engine-ir" / "0.1.0"


def load_fixture(relative: str) -> dict:
    return load_json_strict((CORPUS_ROOT / relative).read_bytes())


def base_manifest() -> dict:
    return load_fixture("inputs/graph-01-brep-source.json")


def envelope_digest(value: dict) -> str:
    return value["identity"]["digest"]


class EngineIrLexicalTests(unittest.TestCase):
    def test_loader_accepts_profile_boundaries_without_reclassifying_keys_as_values(self) -> None:
        self.assertEqual(load_json_strict(f'{{"n":{MAX_SAFE_INTEGER}}}')["n"], MAX_SAFE_INTEGER)
        self.assertEqual(load_json_strict(f'{{"n":{-MAX_SAFE_INTEGER}}}')["n"], -MAX_SAFE_INTEGER)
        # Keys are not values in the native parser. A compact object proves the
        # classification without crossing the independent 1 MiB byte limit.
        members = ",".join(f'"{index:x}":0' for index in range(50_000))
        document = "{" + members + "}"
        self.assertLess(len(document.encode()), MAX_INPUT_BYTES)
        loaded = load_json_strict(document)
        self.assertEqual(len(loaded), 50_000)

    def test_loader_accepts_native_depth_boundary_and_rejects_one_more_container(self) -> None:
        # A public document root must be an object; test the same nesting below an object value.
        accepted_object = '{"v":' + "[" * 63 + "null" + "]" * 63 + "}"
        rejected_object = '{"v":' + "[" * 64 + "null" + "]" * 64 + "}"
        self.assertIn("v", load_json_strict(accepted_object))
        with self.assertRaisesRegex(LexicalError, "nesting"):
            load_json_strict(rejected_object)

    def test_loader_rejects_profile1_lexical_mutations_before_schema(self) -> None:
        invalid = (
            b'{"x":1,"x":2}',
            b'{"x":1,"\\u0078":2}',
            b'{"x":1.0}',
            b'{"x":1e2}',
            b'{"x":9007199254740992}',
            b'{"x":NaN}',
            b'{"x":"\\ud800"}',
            b'\xff{"x":1}',
            b"[]",
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(LexicalError):
                load_json_strict(raw)
        with self.assertRaisesRegex(LexicalError, "exceeds"):
            load_json_strict(b" " * (MAX_INPUT_BYTES + 1))


class EngineIrSchemaTests(unittest.TestCase):
    def test_schema_identifiers_constants_and_integer_domain_are_frozen(self) -> None:
        manifest = load_json_strict(
            (SCHEMA_ROOT / "morphoia-engine-ir-manifest-0.1.0.schema.json").read_bytes()
        )
        replay = load_json_strict(
            (SCHEMA_ROOT / "morphoia-engine-ir-replay-0.1.0.schema.json").read_bytes()
        )
        for schema in (manifest, replay):
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(manifest["$id"], MANIFEST_SCHEMA_ID)
        self.assertEqual(replay["$id"], REPLAY_SCHEMA_ID)
        self.assertEqual(manifest["properties"]["format"]["const"], MANIFEST_FORMAT)
        self.assertEqual(manifest["properties"]["format_version"]["const"], MANIFEST_VERSION)
        self.assertEqual(manifest["properties"]["media_type"]["const"], MANIFEST_MEDIA_TYPE)
        self.assertEqual(
            manifest["properties"]["canonical_profile"]["const"], CANONICAL_PROFILE
        )
        for schema in (manifest, replay):
            stack = [schema]
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    self.assertNotEqual(item.get("type"), "number")
                    stack.extend(item.values())
                elif isinstance(item, list):
                    stack.extend(item)

    def test_closed_schema_rejects_unknown_core_inline_payload_and_unsafe_integer(self) -> None:
        cases: list[tuple[str, callable]] = [
            ("unknown envelope", lambda value: value.__setitem__("unexpected", True)),
            (
                "inline payload",
                lambda value: value["content"]["representations"][0]["payload"].__setitem__(
                    "data", "AAAA"
                ),
            ),
            (
                "unsafe integer",
                lambda value: value["content"].__setitem__("revision", MAX_SAFE_INTEGER + 1),
            ),
            (
                "MVX invention",
                lambda value: value["content"]["representations"][0].__setitem__("kind", "mvx"),
            ),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                value = base_manifest()
                mutate(value)
                with self.assertRaises((LexicalError, SchemaError)):
                    validate_manifest(value, identity_digest=envelope_digest(value))

    def test_extension_namespace_preserves_internal_core_homonyms(self) -> None:
        value = base_manifest()
        extension_value = {
            "content": {"units": ["extension-owned"], "security": "extension-owned"},
            "losses": [],
        }
        value["content"]["extensions"] = {"org.example.feature": extension_value}
        validate_manifest(value, identity_digest=envelope_digest(value))
        round_trip = load_json_strict(json.dumps(value, separators=(",", ":")))
        validate_manifest(round_trip, identity_digest=envelope_digest(round_trip))
        self.assertEqual(round_trip["content"]["extensions"]["org.example.feature"], extension_value)

    def test_spdx_expression_and_invalid_signature_evidence_rules(self) -> None:
        value = base_manifest()
        value["content"]["source"]["license_expression"] = "Apache-2.0 OR MIT"
        validate_manifest(value, identity_digest=envelope_digest(value))
        value["content"]["security"]["signature"] = {
            "status": "invalid",
            "algorithm": None,
            "value": None,
        }
        with self.assertRaises(SchemaError):
            validate_manifest(value, identity_digest=envelope_digest(value))
        value = base_manifest()
        value["content"]["source"]["license_expression"] = "THIS IS NOT SPDX"
        with self.assertRaisesRegex(SemanticError, "SPDX"):
            validate_manifest(value, identity_digest=envelope_digest(value))
        value["content"]["source"]["license_expression"] = (
            "Apache-2.0 OR (MIT AND LicenseRef-Synthetic-Fixture)"
        )
        validate_manifest(value, identity_digest=envelope_digest(value))
        value["content"]["source"]["license_expression"] = (
            "GPL-2.0-or-later WITH LLVM-exception"
        )
        validate_manifest(value, identity_digest=envelope_digest(value))
        invalid_expressions = (
            "(MIT OR Apache-2.0) WITH LLVM-exception",
            "MIT WITH LicenseRef-CustomException",
            "LicenseRef- WITH Exception",
            "MIT\rOR\rApache-2.0",
            "MIT\fOR\fApache-2.0",
        )
        for expression in invalid_expressions:
            with self.subTest(expression=expression):
                value = base_manifest()
                value["content"]["source"]["license_expression"] = expression
                with self.assertRaisesRegex(SemanticError, "SPDX"):
                    validate_manifest(value, identity_digest=envelope_digest(value))


class EngineIrSemanticTests(unittest.TestCase):
    def assertSemanticMutation(self, mutate: callable, message: str | None = None) -> None:
        value = base_manifest()
        mutate(value)
        context = self.assertRaisesRegex(SemanticError, message) if message else self.assertRaises(
            SemanticError
        )
        with context:
            validate_manifest(value, identity_digest=envelope_digest(value))

    def test_identity_is_only_verified_against_native_result(self) -> None:
        value = base_manifest()
        digest = value["identity"]["digest"]
        with self.assertRaisesRegex(SemanticError, "requires a native"):
            validate_manifest(value)
        validate_manifest(value, identity_digest=digest)
        with self.assertRaisesRegex(SemanticError, "native content identity"):
            validate_manifest(value, identity_digest="f" * 64)

    def test_digest_uri_ids_and_references_are_consistent(self) -> None:
        self.assertSemanticMutation(
            lambda value: value["content"]["representations"][0]["payload"].__setitem__(
                "uri", "morphoia-cas://sha256/" + "f" * 64
            ),
            "CAS URI",
        )
        self.assertSemanticMutation(
            lambda value: value["content"]["frames"][0].__setitem__(
                "unit_id", "018f0000-0000-7000-8000-00000000ffff"
            ),
            "unknown frame unit",
        )
        self.assertSemanticMutation(
            lambda value: value["content"]["representations"][0].__setitem__(
                "id", value["content"]["units"][0]["id"]
            ),
            "duplicate declared",
        )
        self.assertSemanticMutation(
            lambda value: value["content"]["product"]["names"][0].__setitem__(
                "subject_id", "018f0000-0000-7000-8000-00000000ffff"
            ),
            "unknown product subject",
        )

    def test_dimensions_transforms_and_timestamps_are_explicit(self) -> None:
        self.assertSemanticMutation(
            lambda value: value["content"]["frames"][0]["origin"].pop(),
            "frame vector dimensions",
        )
        self.assertSemanticMutation(
            lambda value: value["content"]["frames"][0].__setitem__("axes", [0] * 9),
            "signed basis",
        )
        self.assertSemanticMutation(
            lambda value: value["content"]["frames"][0].__setitem__(
                "axes", [-1, 0, 0, 0, 1, 0, 0, 0, 1]
            ),
            "handedness",
        )
        self.assertSemanticMutation(
            lambda value: value["content"]["units"][0]["si_factor"].__setitem__(
                "coefficient", 0
            ),
            "SI factor",
        )
        transformed = load_fixture("inputs/graph-04-transform.json")
        transformed["content"]["transforms"][0]["matrix"].pop()
        with self.assertRaisesRegex(SemanticError, "matrix size"):
            validate_manifest(transformed, identity_digest=envelope_digest(transformed))
        transformed = load_fixture("inputs/graph-04-transform.json")
        transformed["content"]["transforms"][0]["matrix"][-1]["coefficient"] = 2
        with self.assertRaisesRegex(SemanticError, "affine homogeneous"):
            validate_manifest(transformed, identity_digest=envelope_digest(transformed))
        transformed = load_fixture("inputs/graph-04-transform.json")
        for item in transformed["content"]["transforms"][0]["matrix"]:
            item["coefficient"] = 0
        transformed["content"]["transforms"][0]["matrix"][-1]["coefficient"] = 1
        with self.assertRaisesRegex(SemanticError, "singular"):
            validate_manifest(transformed, identity_digest=envelope_digest(transformed))
        transformed = load_fixture("inputs/graph-04-transform.json")
        duplicate = copy.deepcopy(transformed["content"]["transforms"][0])
        duplicate["id"] = "018f0000-0000-7000-8000-00000000ff01"
        transformed["content"]["transforms"].append(duplicate)
        with self.assertRaisesRegex(SemanticError, "duplicate transform"):
            validate_manifest(transformed, identity_digest=envelope_digest(transformed))
        self.assertSemanticMutation(
            lambda value: value["content"]["source"].__setitem__(
                "created_at", "2026-08-12T13:00:00+01:00"
            ),
            "UTC Z",
        )
        self.assertSemanticMutation(
            lambda value: value["content"]["provenance"][0].__setitem__(
                "ended_at", "2026-08-12T11:59:59Z"
            ),
            "end precedes start",
        )

    def test_authority_derivation_ai_and_provenance_invariants(self) -> None:
        derived = load_fixture("inputs/graph-05-derived-mesh.json")
        derived["content"]["representations"][1]["authority"] = "source"
        with self.assertRaisesRegex(SemanticError, "claims source authority"):
            validate_manifest(derived, identity_digest=envelope_digest(derived))
        ai = load_fixture("inputs/graph-09-ai-candidate.json")
        ai["content"]["representations"][1]["authority"] = "derived"
        with self.assertRaisesRegex(SemanticError, "revisable candidate"):
            validate_manifest(ai, identity_digest=envelope_digest(ai))
        broken = load_fixture("inputs/graph-05-derived-mesh.json")
        broken["content"]["provenance"][1]["inputs"] = []
        with self.assertRaisesRegex(SemanticError, "exactly match input producers"):
            validate_manifest(broken, identity_digest=envelope_digest(broken))
        duplicate_producer = load_fixture("inputs/graph-05-derived-mesh.json")
        duplicate_producer["content"]["provenance"][0]["outputs"].append(
            duplicate_producer["content"]["representations"][1]["id"]
        )
        with self.assertRaisesRegex(SemanticError, "multiple provenance producers"):
            validate_manifest(
                duplicate_producer,
                identity_digest=envelope_digest(duplicate_producer),
            )

    def test_provenance_inputs_define_exact_acyclic_time_ordered_parents(self) -> None:
        self_consuming = base_manifest()
        self_consuming["content"]["provenance"][0]["inputs"].append(
            self_consuming["content"]["representations"][0]["id"]
        )
        with self.assertRaisesRegex(SemanticError, "consumes its own output"):
            validate_manifest(
                self_consuming,
                identity_digest=envelope_digest(self_consuming),
            )

        missing_parent = load_fixture("inputs/graph-05-derived-mesh.json")
        missing_parent["content"]["provenance"][1]["parents"] = []
        with self.assertRaisesRegex(SemanticError, "exactly match input producers"):
            validate_manifest(missing_parent, identity_digest=envelope_digest(missing_parent))

        descendant_cycle = load_fixture("inputs/graph-05-derived-mesh.json")
        descendant_cycle["content"]["provenance"][0]["inputs"].append(
            descendant_cycle["content"]["representations"][1]["id"]
        )
        descendant_cycle["content"]["provenance"][0]["parents"].append(
            descendant_cycle["content"]["provenance"][1]["id"]
        )
        with self.assertRaisesRegex(SemanticError, "cycle detected"):
            validate_manifest(
                descendant_cycle,
                identity_digest=envelope_digest(descendant_cycle),
            )

        time_reversal = load_fixture("inputs/graph-05-derived-mesh.json")
        time_reversal["content"]["provenance"][1]["started_at"] = "2026-08-12T11:00:00Z"
        time_reversal["content"]["provenance"][1]["ended_at"] = "2026-08-12T11:00:01Z"
        with self.assertRaisesRegex(SemanticError, "before its producer ends"):
            validate_manifest(time_reversal, identity_digest=envelope_digest(time_reversal))

    def test_verified_signature_self_claim_is_rejected_without_crypto_result(self) -> None:
        value = base_manifest()
        value["content"]["security"]["signature"] = {
            "status": "verified",
            "algorithm": "example-signature",
            "value": "not-cryptographically-verified",
        }
        with self.assertRaisesRegex(SemanticError, "external cryptographic"):
            validate_manifest(value, identity_digest=envelope_digest(value))
        value = base_manifest()
        value["content"]["security"]["trust_level"] = "verified"
        with self.assertRaisesRegex(SemanticError, "external trust-policy"):
            validate_manifest(value, identity_digest=envelope_digest(value))

    def test_linear_revision_and_nonnegative_tolerance_are_explicit(self) -> None:
        revision = load_fixture("inputs/graph-20-revision-parent.json")
        revision["content"]["parents"][0]["logical_id"] = (
            "018f0000-0000-7000-8000-00000000ff02"
        )
        with self.assertRaisesRegex(SemanticError, "different logical identity"):
            validate_manifest(revision, identity_digest=envelope_digest(revision))
        revision = load_fixture("inputs/graph-20-revision-parent.json")
        revision["content"]["parents"].append(copy.deepcopy(revision["content"]["parents"][0]))
        revision["content"]["parents"][1]["content_sha256"] = "f" * 64
        with self.assertRaisesRegex(SemanticError, "exactly one linear parent"):
            validate_manifest(revision, identity_digest=envelope_digest(revision))
        revision = load_fixture("inputs/graph-20-revision-parent.json")
        revision["content"]["parents"][0]["content_sha256"] = revision["identity"][
            "digest"
        ]
        with self.assertRaisesRegex(SemanticError, "current content identity"):
            validate_manifest(revision, identity_digest=envelope_digest(revision))
        revision = base_manifest()
        revision["content"]["parents"] = [
            {
                "logical_id": revision["content"]["logical_id"],
                "revision": 1,
                "content_sha256": "f" * 64,
            }
        ]
        with self.assertRaisesRegex(SemanticError, "revision 1"):
            validate_manifest(revision, identity_digest=envelope_digest(revision))

        tolerance = load_fixture("inputs/graph-14-tolerance.json")
        tolerance["content"]["tolerances"][0]["amount"]["coefficient"] = -1
        with self.assertRaisesRegex(SemanticError, "negative tolerance"):
            validate_manifest(tolerance, identity_digest=envelope_digest(tolerance))

    def test_provenance_and_product_cycles_are_rejected(self) -> None:
        provenance = load_fixture("inputs/graph-05-derived-mesh.json")
        first, second = provenance["content"]["provenance"]
        first["parents"] = [second["id"]]
        with self.assertRaisesRegex(SemanticError, "exactly match input producers"):
            validate_manifest(provenance, identity_digest=envelope_digest(provenance))
        assembly = load_fixture("inputs/graph-11-assembly.json")
        first_assembly, second_assembly = assembly["content"]["product"]["assemblies"]
        first_assembly["parent_id"] = second_assembly["id"]
        with self.assertRaisesRegex(SemanticError, "cycle detected in assembly"):
            validate_manifest(assembly, identity_digest=envelope_digest(assembly))

    def test_replay_contract_is_closed_ordered_and_hash_consistent(self) -> None:
        replay = load_fixture("replays/graph-01-brep-source.replay.json")
        validate_replay(replay)
        replay["operations"][1]["operation"] = "canonicalize-content"
        with self.assertRaises(SchemaError):
            validate_replay(replay)
        replay = load_fixture("replays/graph-01-brep-source.replay.json")
        replay["manifest"]["uri"] = "morphoia-cas://sha256/" + "f" * 64
        with self.assertRaisesRegex(SemanticError, "CAS URI"):
            validate_replay(replay)


class EngineIrCorpusTests(unittest.TestCase):
    def test_exactly_twenty_synthetic_inputs_have_indexed_hashes_and_lf_free_goldens(self) -> None:
        index = load_fixture("index.json")
        self.assertEqual(index["format"], "morphoia.engine.ir-corpus")
        self.assertEqual(index["format_version"], "0.1.0")
        self.assertEqual(len(index["entries"]), 20)
        self.assertEqual(len({item["id"] for item in index["entries"]}), 20)
        self.assertEqual(len(list((CORPUS_ROOT / "inputs").glob("*.json"))), 20)
        self.assertEqual(len(list((CORPUS_ROOT / "goldens").glob("*.content.cjson"))), 20)
        self.assertEqual(len(list((CORPUS_ROOT / "replays").glob("*.replay.json"))), 20)
        for entry in index["entries"]:
            with self.subTest(entry=entry["id"]):
                input_path = CORPUS_ROOT / entry["input"]
                golden_path = CORPUS_ROOT / entry["golden"]
                replay_path = CORPUS_ROOT / entry["replay"]
                raw = input_path.read_bytes()
                golden = golden_path.read_bytes()
                replay_raw = replay_path.read_bytes()
                self.assertFalse(golden.endswith(b"\n"))
                self.assertNotIn(b"\r", golden)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["input_sha256"])
                self.assertEqual(hashlib.sha256(golden).hexdigest(), entry["content_sha256"])
                self.assertEqual(hashlib.sha256(replay_raw).hexdigest(), entry["replay_sha256"])
                manifest = load_json_strict(raw)
                validate_manifest(manifest, identity_digest=entry["content_sha256"])
                self.assertEqual(manifest["identity"]["digest"], entry["content_sha256"])
                replay = load_json_strict(replay_raw)
                validate_replay(replay)
                self.assertEqual(replay["expected_content_identity"], entry["content_sha256"])

    def test_committed_invalid_fixtures_are_rejected_by_declared_stage(self) -> None:
        index = load_fixture("invalid/index.json")
        self.assertEqual(len(index["entries"]), 13)
        stages = {"lexical", "schema", "semantic"}
        self.assertEqual({entry["stage"] for entry in index["entries"]}, stages)
        for entry in index["entries"]:
            raw = (CORPUS_ROOT / entry["path"]).read_bytes()
            error_type = {
                "lexical": LexicalError,
                "schema": SchemaError,
                "semantic": SemanticError,
            }[entry["stage"]]
            with self.subTest(entry=entry["id"]), self.assertRaises(error_type):
                document = load_json_strict(raw)
                validate_manifest(document, identity_digest=envelope_digest(document))


if __name__ == "__main__":
    unittest.main()
