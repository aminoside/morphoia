# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import ast
import copy
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from morphoia.salome_protocol import (
    MAX_CONTROL_MESSAGE_BYTES,
    OPERATIONS,
    PROTOCOL_VERSION,
    FakeSalomeAgent,
    ProtocolError,
    encode_control_json,
    load_control_json,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "morphoia-salome-protocol-0.1.schema.json"
FIXED_TIME = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
FIXED_TIME_TEXT = "2026-08-12T12:00:00Z"


def request(operation: str, body: dict, *, request_id: str | None = None) -> dict:
    request_id = request_id or f"request:{operation}"
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": f"message:{operation}",
        "request_id": request_id,
        "direction": "request",
        "operation": operation,
        "sent_at": FIXED_TIME_TEXT,
        "body": body,
    }


def submit_request(*, request_id: str = "request:Submit") -> dict:
    return request(
        "Submit",
        {
            "operation_name": "geom.import_step",
            "parameters": {
                "preserve_names": True,
                "tolerance": {"value": 1e-7, "unit": "m"},
                "layers": ["geometry", "metadata"],
            },
            "inputs": [
                {
                    "uri": "file:///tmp/morphoia-fixture.step",
                    "sha256": "a" * 64,
                    "size_bytes": 4096,
                    "media_type": "model/step",
                    "role": "source",
                    "units": [{"symbol": "mm", "dimension": "length"}],
                }
            ],
            "budget": {
                "wall_time_seconds": 60,
                "memory_bytes": 1073741824,
                "temp_bytes": 1073741824,
            },
            "expected_outputs": [
                {
                    "role": "geometry-groups",
                    "format": "XAO",
                    "media_type": "application/x-xao",
                }
            ],
            "idempotency_key": "submit-key-001",
        },
        request_id=request_id,
    )


class SalomeProtocolSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def assertValid(self, instance: dict) -> None:
        errors = sorted(self.validator.iter_errors(instance), key=lambda item: list(item.path))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def assertInvalid(self, instance: dict) -> None:
        with self.assertRaises(ValidationError):
            self.validator.validate(instance)

    def test_schema_is_draft_2020_12_and_protocol_version_is_explicit(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(self.schema["properties"]["protocol_version"]["const"], "0.1.0")
        maximum = 2**53 - 1

        def objects(value: object):
            if isinstance(value, dict):
                yield value
                for item in value.values():
                    yield from objects(item)
            elif isinstance(value, list):
                for item in value:
                    yield from objects(item)

        integer_schemas = [
            value for value in objects(self.schema) if value.get("type") == "integer"
        ]
        number_schemas = [
            value for value in objects(self.schema) if value.get("type") == "number"
        ]
        self.assertTrue(integer_schemas)
        for value in (*integer_schemas, *number_schemas):
            self.assertLessEqual(value["maximum"], maximum)
            self.assertGreaterEqual(value.get("minimum", -maximum), -maximum)

    def test_all_six_request_and_fake_response_contracts_validate(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        probe = request(
            "ProbeCapabilities",
            {"client": {"name": "morphoia-core", "version": "0.0.1"}},
        )
        health = request("Health", {})
        submit = submit_request()

        for message in (probe, health, submit):
            self.assertValid(message)
            self.assertValid(agent.handle(message))

        job_id = agent.handle(submit)["body"]["job_id"]
        lifecycle = (
            request("Observe", {"job_id": job_id}),
            request(
                "Cancel",
                {"job_id": job_id, "idempotency_key": "cancel-key-001"},
            ),
            request("Publish", {"job_id": job_id}),
        )
        observed_operations = {"ProbeCapabilities", "Submit", "Health"}
        for message in lifecycle:
            self.assertValid(message)
            response = agent.handle(message)
            self.assertValid(response)
            observed_operations.add(response["operation"])
        self.assertEqual(observed_operations, set(OPERATIONS))

    def test_fake_capabilities_are_truthful_about_not_running_salome(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        response = agent.handle(
            request(
                "ProbeCapabilities",
                {"client": {"name": "contract-test", "version": "1"}},
            )
        )
        self.assertValid(response)
        self.assertEqual(response["agent_kind"], "fake")
        self.assertTrue(response["simulation"])
        self.assertEqual(response["status"], "not_available")
        capabilities = response["body"]
        self.assertEqual(capabilities["agent_kind"], "fake")
        self.assertTrue(capabilities["simulation"])
        self.assertFalse(capabilities["backend_available"])
        self.assertEqual(capabilities["runtime"]["status"], "NOT_RUN")
        self.assertIsNone(capabilities["runtime"]["salome_version"])
        self.assertEqual(
            {item["status"] for item in capabilities["modules"]},
            {"NOT_RUN"},
        )
        self.assertEqual(capabilities["med_formats"], [])
        self.assertEqual(capabilities["oss_meshers"], [])
        self.assertEqual(set(capabilities["supported_operations"]), set(OPERATIONS))

    def test_schema_rejects_a_fake_agent_that_claims_real_capability(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        response = agent.handle(
            request(
                "ProbeCapabilities",
                {"client": {"name": "contract-test", "version": "1"}},
            )
        )
        mutations = (
            lambda value: value.__setitem__("simulation", False),
            lambda value: value.__setitem__("status", "succeeded"),
            lambda value: value["body"].__setitem__("backend_available", True),
            lambda value: value["body"].__setitem__("simulation", False),
            lambda value: value["body"]["runtime"].__setitem__("status", "PASS"),
            lambda value: value["body"]["runtime"].__setitem__(
                "salome_version", "9.16.0"
            ),
            lambda value: value["body"]["runtime"].__setitem__("gui_active", True),
            lambda value: value["body"]["modules"][0].__setitem__("status", "PASS"),
            lambda value: value["body"].__setitem__("med_formats", ["MED-3"]),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(response)
                mutation(changed)
                self.assertInvalid(changed)

    def test_artifact_references_are_hash_size_uri_metadata_only(self) -> None:
        message = submit_request()
        self.assertValid(message)
        mutations = {
            "uppercase digest": lambda value: value["body"]["inputs"][0].__setitem__(
                "sha256", "A" * 64
            ),
            "short digest": lambda value: value["body"]["inputs"][0].__setitem__(
                "sha256", "a" * 63
            ),
            "negative size": lambda value: value["body"]["inputs"][0].__setitem__(
                "size_bytes", -1
            ),
            "unapproved URI scheme": lambda value: value["body"]["inputs"][0].__setitem__(
                "uri", "ftp://example.invalid/input.step"
            ),
            "missing media type": lambda value: value["body"]["inputs"][0].pop(
                "media_type"
            ),
            "inline payload": lambda value: value["body"]["inputs"][0].__setitem__(
                "payload", "not-allowed"
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(message)
                mutation(changed)
                self.assertInvalid(changed)

    def test_control_plane_rejects_inline_payload_fields_and_unbounded_strings(self) -> None:
        base = submit_request()
        mutations = {
            "top-level payload": lambda value: value.__setitem__("payload", "forbidden"),
            "body payload": lambda value: value["body"].__setitem__(
                "payload", "forbidden"
            ),
            "parameter payload": lambda value: value["body"]["parameters"].__setitem__(
                "payload", "forbidden"
            ),
            "nested payload": lambda value: value["body"]["parameters"].__setitem__(
                "options", {"payload": "forbidden"}
            ),
            "large control string": lambda value: value["body"]["parameters"].__setitem__(
                "label", "x" * 4097
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(base)
                mutation(changed)
                self.assertInvalid(changed)

        unsafe_integer = submit_request()
        unsafe_integer["body"]["parameters"]["unsafe_integer"] = 2**53
        self.assertInvalid(unsafe_integer)

    def test_large_artifact_reference_is_not_transfer_evidence(self) -> None:
        message = submit_request()
        message["body"]["inputs"][0]["size_bytes"] = 3 * 1024**3
        self.assertValid(message)
        encoded = encode_control_json(message)
        self.assertLess(len(encoded), 8192)
        self.assertNotIn("payload", encoded)

    def test_request_envelope_is_closed_and_versioned(self) -> None:
        base = request("Health", {})
        mutations = {
            "wrong version": lambda value: value.__setitem__("protocol_version", "0.2.0"),
            "unknown operation": lambda value: value.__setitem__("operation", "Execute"),
            "response field on request": lambda value: value.__setitem__(
                "status", "succeeded"
            ),
            "attempt on request": lambda value: value.__setitem__("attempt", {}),
            "unknown field": lambda value: value.__setitem__("unexpected", True),
            "fake marker on request": lambda value: value.__setitem__(
                "agent_kind", "fake"
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(base)
                mutation(changed)
                self.assertInvalid(changed)

    def test_attempt_state_and_terminality_cannot_contradict_each_other(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        response = agent.handle(submit_request())
        self.assertValid(response)
        self.assertEqual(response["attempt"]["state"], "queued")
        self.assertFalse(response["attempt"]["terminal"])
        changed = copy.deepcopy(response)
        changed["attempt"]["terminal"] = True
        self.assertInvalid(changed)

    def test_submit_and_cancel_are_idempotent_in_the_fake_contract_lifecycle(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        first = agent.handle(submit_request(request_id="request:Submit:first"))
        second = agent.handle(submit_request(request_id="request:Submit:second"))
        self.assertValid(first)
        self.assertValid(second)
        self.assertEqual(first["body"]["job_id"], second["body"]["job_id"])
        self.assertFalse(first["body"]["duplicate"])
        self.assertTrue(second["body"]["duplicate"])

        job_id = first["body"]["job_id"]
        cancel = request(
            "Cancel",
            {"job_id": job_id, "idempotency_key": "cancel-key-001"},
        )
        cancelled = agent.handle(cancel)
        cancelled_again = agent.handle(cancel)
        self.assertValid(cancelled)
        self.assertValid(cancelled_again)
        self.assertEqual(cancelled["body"]["cancellation_effect"], "cancelled")
        self.assertEqual(
            cancelled_again["body"]["cancellation_effect"],
            "already_cancelled",
        )
        self.assertTrue(cancelled_again["body"]["idempotent"])

    def test_fake_publish_never_claims_a_salome_artifact(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        submitted = agent.handle(submit_request())
        response = agent.handle(
            request("Publish", {"job_id": submitted["body"]["job_id"]})
        )
        self.assertValid(response)
        self.assertEqual(response["agent_kind"], "fake")
        self.assertTrue(response["simulation"])
        self.assertEqual(response["status"], "not_available")
        self.assertEqual(response["body"]["artifacts"], [])
        self.assertEqual(response["attempt"]["environment"]["salome_status"], "NOT_RUN")
        self.assertEqual(response["body"]["losses"][0]["id"], "FAKE-NO-SALOME")

    def test_health_requires_headless_truth_fields_for_the_fake(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        response = agent.handle(request("Health", {}))
        self.assertValid(response)
        health = response["body"]
        self.assertFalse(health["runtime_ready"])
        self.assertFalse(health["gui_active"])
        self.assertEqual(health["salome_status"], "NOT_RUN")
        changed = copy.deepcopy(response)
        changed["body"]["gui_active"] = True
        self.assertInvalid(changed)


class SalomeProtocolJsonTests(unittest.TestCase):
    def test_strict_loader_rejects_duplicate_keys_nan_and_non_object_roots(self) -> None:
        invalid_documents = (
            '{"request_id":"one","request_id":"two"}',
            '{"value":NaN}',
            '{"value":Infinity}',
            "[]",
            b'\xff{"value":1}',
        )
        for document in invalid_documents:
            with self.subTest(document=document), self.assertRaises(ProtocolError):
                load_control_json(document)

    def test_strict_loader_and_serializer_enforce_the_control_message_size_limit(self) -> None:
        oversized = '{"value":"' + "x" * MAX_CONTROL_MESSAGE_BYTES + '"}'
        with self.assertRaises(ProtocolError):
            load_control_json(oversized)
        with self.assertRaises(ProtocolError):
            encode_control_json({"value": "x" * MAX_CONTROL_MESSAGE_BYTES})

    def test_control_encoder_is_deterministic_but_not_ir_canonicalization(self) -> None:
        message = request("Health", {"client_time": FIXED_TIME_TEXT})
        encoded = encode_control_json(message)
        self.assertEqual(encoded, encode_control_json(copy.deepcopy(message)))
        self.assertTrue(encoded.endswith("\n"))
        self.assertEqual(load_control_json(encoded), message)
        self.assertNotIn("canonical", encode_control_json.__name__)
        self.assertIn("not RFC 8785", encode_control_json.__doc__ or "")
        with self.assertRaises(ProtocolError):
            encode_control_json({"value": float("nan")})

    def test_loader_and_encoder_reject_lone_unicode_surrogates_recursively(self) -> None:
        documents = (
            r'{"value":"\ud800"}',
            b'{"value":"\\ud800"}',
            '{"value":"' + chr(0xDFFF) + '"}',
            r'{"nested":{"values":["safe","\udfff"]}}',
            r'{"\ud800":"value"}',
        )
        for document in documents:
            with self.subTest(document=ascii(document)), self.assertRaises(ProtocolError):
                load_control_json(document)
        values = (
            {"value": chr(0xD800)},
            {"nested": ["safe", {"value": chr(0xDFFF)}]},
            {chr(0xD800): "value"},
        )
        for value in values:
            with self.subTest(value=ascii(value)), self.assertRaises(ProtocolError):
                encode_control_json(value)

    def test_loader_and_encoder_reject_integers_above_binary64_exact_range(self) -> None:
        maximum = 2**53 - 1
        self.assertEqual(load_control_json(f'{{"value":{maximum}}}')["value"], maximum)
        self.assertIn(str(maximum), encode_control_json({"value": maximum}))
        invalid_values = (2**53, -(2**53))
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                load_control_json(f'{{"value":{value}}}')
            with self.assertRaises(ProtocolError):
                encode_control_json({"value": value})

    def test_fake_agent_rejects_unversioned_non_request_and_unknown_operation(self) -> None:
        agent = FakeSalomeAgent(clock=lambda: FIXED_TIME)
        mutations = (
            {"protocol_version": "0.2.0", "direction": "request", "operation": "Health"},
            {
                "protocol_version": PROTOCOL_VERSION,
                "direction": "response",
                "operation": "Health",
            },
            {
                "protocol_version": PROTOCOL_VERSION,
                "direction": "request",
                "operation": "Execute",
            },
        )
        for fields in mutations:
            value = {
                **request("Health", {}),
                **fields,
            }
            with self.subTest(fields=fields), self.assertRaises(ProtocolError):
                agent.handle(value)

        unsafe_requests = (
            request("Health", {"client_time": chr(0xD800)}),
            request("Health", {"unsafe_integer": 2**53}),
        )
        for value in unsafe_requests:
            with self.subTest(value=ascii(value)), self.assertRaises(ProtocolError):
                agent.handle(value)

    def test_protocol_package_has_no_forbidden_salome_runtime_imports(self) -> None:
        forbidden = {"salome", "kernel", "corba", "salomeds", "qt", "pyqt", "omniorb"}
        imported: set[str] = set()
        for path in sorted((ROOT / "src" / "morphoia" / "salome_protocol").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0].lower() for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".", 1)[0].lower())
        self.assertEqual(imported & forbidden, set())


if __name__ == "__main__":
    unittest.main()
