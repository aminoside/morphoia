# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from morphoia._engine_native import NativeEngine
from morphoia.engine_ir import seal_content
from morphoia.engine_ir_contract import load_json_strict
from morphoia.engine_ir_inspection import (
    INSPECTION_FORMAT,
    INSPECTION_MEDIA_TYPE,
    INSPECTION_PROFILE,
    INSPECTION_SCHEMA_ID,
    InspectionError,
    inspect_engine_ir,
)


class QualifiedEngineIrInspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="morphoia-inspection-")
        cls.work = Path(cls._temporary.name)
        cls.repository = Path(__file__).resolve().parents[1]
        cls.corpus = cls.repository / "tests/fixtures/engine-ir/0.1.0"
        cls.library = cls.work / "libmorphoia_engine.so"
        compiler = shutil.which("g++")
        if compiler is None:
            raise RuntimeError("g++ is required for mandatory inspection tests")
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                "-fPIC",
                "-fvisibility=hidden",
                "-fvisibility-inlines-hidden",
                "-shared",
                "-DMORPHOIA_ENGINE_SHARED",
                "-DMORPHOIA_ENGINE_EXPORTS",
                f"-I{cls.repository / 'cpp/include'}",
                f"-I{cls.repository / 'cpp/src'}",
                os.fspath(cls.repository / "cpp/src/engine.cpp"),
                os.fspath(cls.repository / "cpp/src/core/canonical_json.cpp"),
                os.fspath(cls.repository / "cpp/src/core/sha256.cpp"),
                os.fspath(cls.repository / "cpp/src/core/unit_registry.cpp"),
                f"-Wl,--version-script,{cls.repository / 'cmake/morphoia_engine.map'}",
                "-o",
                os.fspath(cls.library),
            ],
            cwd=cls.repository,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.schema = load_json_strict(
            (
                cls.repository
                / "schemas/morphoia-engine-ir-inspection-0.1.0.schema.json"
            ).read_bytes()
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def _input(self, name: str = "graph-01-brep-source.json") -> bytes:
        return (self.corpus / "inputs" / name).read_bytes()

    def _mutated_manifest(self, mutation) -> bytes:
        source = load_json_strict(self._input())
        content = copy.deepcopy(source["content"])
        mutation(content)
        with NativeEngine(self.library) as engine:
            return seal_content(content, engine=engine).canonical_manifest

    def test_schema_is_draft_2020_12_and_exactly_identified(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(self.schema["$id"], INSPECTION_SCHEMA_ID)

    def test_all_twenty_reports_are_native_canonical_and_repeatable(self) -> None:
        index = load_json_strict((self.corpus / "index.json").read_bytes())
        vectors = load_json_strict(
            (
                self.repository
                / "spec/evidence/qualified-ir-inspection-0.1-report-vectors.json"
            ).read_bytes()
        )
        self.assertEqual(vectors["pass_count"], 2)
        self.assertTrue(vectors["passes_identical"])
        self.assertEqual(
            [item["id"] for item in vectors["vectors"]],
            [item["id"] for item in index["entries"]],
        )
        expected_vectors = {item["id"]: item for item in vectors["vectors"]}
        first: dict[str, tuple[bytes, str]] = {}
        with NativeEngine(self.library) as engine:
            self.assertEqual(vectors["native_library_sha256"], engine.library_sha256)
            for entry in index["entries"]:
                source = (self.corpus / entry["input"]).read_bytes()
                result = inspect_engine_ir(source, engine=engine)
                self.assertTrue(result.qualified, entry["id"])
                self.assertEqual(result.document["format"], INSPECTION_FORMAT)
                self.assertEqual(result.document["media_type"], INSPECTION_MEDIA_TYPE)
                self.assertFalse(
                    result.document["payload_reference_metadata"]["resolution_performed"]
                )
                self.assertEqual(result.canonical_report[-1:], b"}")
                self.assertEqual(
                    result.report_sha256,
                    hashlib.sha256(result.canonical_report).hexdigest(),
                )
                expected = expected_vectors[entry["id"]]
                self.assertEqual(expected["input_sha256"], hashlib.sha256(source).hexdigest())
                self.assertEqual(expected["report_size_bytes"], len(result.canonical_report))
                self.assertEqual(expected["report_sha256"], result.report_sha256)
                Draft202012Validator(self.schema).validate(result.document)
                first[entry["id"]] = (result.canonical_report, result.report_sha256)
            for entry in reversed(index["entries"]):
                result = inspect_engine_ir(
                    (self.corpus / entry["input"]).read_bytes(),
                    engine=engine,
                )
                self.assertEqual(
                    (result.canonical_report, result.report_sha256),
                    first[entry["id"]],
                )

    def test_report_exposes_declared_metadata_without_applying_or_resolving(self) -> None:
        with (
            NativeEngine(self.library) as engine,
            mock.patch(
                "morphoia.engine_ir.resolve_manifest_reference",
                side_effect=AssertionError("payload resolver must not be called"),
            ) as resolver,
            mock.patch(
                "morphoia.engine_ir.read_bounded_file",
                side_effect=AssertionError("payload reader must not be called"),
            ) as reader,
        ):
            result = inspect_engine_ir(self._input(), engine=engine)
        resolver.assert_not_called()
        reader.assert_not_called()
        report = result.document
        self.assertEqual(report["profile"], INSPECTION_PROFILE)
        self.assertEqual(report["transforms"], [])
        self.assertIn("no-transform-application", report["limitations"])
        self.assertIn("no-payload-resolution", report["limitations"])
        reference = report["payload_reference_metadata"]["representations"][0][
            "payload"
        ]
        self.assertTrue(reference["uri"].startswith("morphoia-cas://sha256/"))
        self.assertEqual(reference["sha256"], reference["uri"].rsplit("/", 1)[-1])
        self.assertEqual(report["diagnostics"], [])

    def test_unknown_literal_returns_structured_failure_without_conversion(self) -> None:
        source = self._mutated_manifest(
            lambda content: content["units"][0].update(
                {
                    "ucum_code": "ft",
                    "si_factor": {"coefficient": 3048, "scale": -4},
                }
            )
        )
        with NativeEngine(self.library) as engine:
            result = inspect_engine_ir(source, engine=engine)
        self.assertFalse(result.qualified)
        self.assertEqual(result.document["status"], "FAIL")
        self.assertEqual(
            [item["code"] for item in result.document["diagnostics"]],
            ["MOR-UNIT-UNSUPPORTED"],
        )
        qualification = result.document["units"][0]["qualification"]
        self.assertFalse(qualification["recognized"])
        self.assertEqual(
            qualification["expected_dimension"],
            {
                "length": 0,
                "mass": 0,
                "time": 0,
                "current": 0,
                "temperature": 0,
                "amount": 0,
                "luminous_intensity": 0,
            },
        )

    def test_literal_tuple_mismatches_have_exact_ordered_diagnostics(self) -> None:
        def mutate(content) -> None:
            content["units"][0]["dimension"] = {
                "length": 0,
                "mass": 0,
                "time": 1,
                "current": 0,
                "temperature": 0,
                "amount": 0,
                "luminous_intensity": 0,
            }
            content["units"][0]["si_factor"] = {"coefficient": 1, "scale": 0}

        with NativeEngine(self.library) as engine:
            result = inspect_engine_ir(self._mutated_manifest(mutate), engine=engine)
        self.assertFalse(result.qualified)
        self.assertEqual(
            [item["code"] for item in result.document["diagnostics"]],
            ["MOR-UNIT-DIMENSION", "MOR-UNIT-SI-FACTOR"],
        )

        for name, factor in (
            ("coefficient", {"coefficient": 2, "scale": -3}),
            ("scale", {"coefficient": 1, "scale": -2}),
        ):
            with self.subTest(name=name):
                source = self._mutated_manifest(
                    lambda content, factor=factor: content["units"][0].update(
                        {"si_factor": factor}
                    )
                )
                with NativeEngine(self.library) as engine:
                    independent = inspect_engine_ir(source, engine=engine)
                self.assertFalse(independent.qualified)
                self.assertEqual(
                    [item["code"] for item in independent.document["diagnostics"]],
                    ["MOR-UNIT-SI-FACTOR"],
                )

    def test_profile_selection_is_fail_closed(self) -> None:
        with NativeEngine(self.library) as engine, self.assertRaisesRegex(
            InspectionError,
            "unsupported inspection profile",
        ):
            inspect_engine_ir(self._input(), profile="org.example.profile", engine=engine)

    def test_optional_representation_fields_remain_total(self) -> None:
        def mutate(content) -> None:
            content["representations"][0].pop("topology_identity", None)

        with NativeEngine(self.library) as engine:
            result = inspect_engine_ir(self._mutated_manifest(mutate), engine=engine)
        authority = result.document["authority_and_derivation"][0]
        self.assertIsNone(authority["topology_identity"])
        self.assertEqual(
            authority["ai_output"],
            load_json_strict(self._input())["content"]["representations"][0][
                "ai_output"
            ],
        )

    def test_report_bounds_cover_the_valid_manifest_domain(self) -> None:
        def mutate(content) -> None:
            template = {
                "id": "018f0000-0000-7000-8000-000000000400",
                "subject_id": content["representations"][0]["id"],
                "kind": "linear",
                "amount": {"coefficient": 1, "scale": -3},
                "unit_id": content["units"][0]["id"],
                "source": "declared",
            }
            content["tolerances"] = []
            for index in range(1025):
                item = copy.deepcopy(template)
                item["id"] = f"018f0000-0000-7000-8000-{index + 0x400:012x}"
                content["tolerances"].append(item)

        with NativeEngine(self.library) as engine:
            source = self._mutated_manifest(mutate)
            result = inspect_engine_ir(source, engine=engine)
        self.assertTrue(result.qualified)
        self.assertEqual(len(result.document["tolerances"]), 1025)

    def test_near_one_mebibyte_manifest_has_a_complete_bounded_report(self) -> None:
        def mutate(content) -> None:
            template = {
                "id": "018f0000-0000-7000-8000-000000000700",
                "subject_id": content["representations"][0]["id"],
                "category": "metadata",
                "property": "p",
                "before": "",
                "after": "",
                "severity": "info",
                "decision": "accept",
                "description": "x" * 1920,
            }
            content["losses"] = []
            for index in range(490):
                item = copy.deepcopy(template)
                item["id"] = f"018f0000-0000-7000-8000-{index + 0x700:012x}"
                content["losses"].append(item)

        with NativeEngine(self.library) as engine:
            source = self._mutated_manifest(mutate)
            self.assertLess(len(source), 1_048_576)
            result = inspect_engine_ir(source, engine=engine)
        self.assertTrue(result.qualified)
        self.assertEqual(len(result.document["losses"]), 490)
        self.assertGreater(len(result.canonical_report), 1_048_576)

    def test_duck_typed_fake_engine_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "open NativeEngine"):
            inspect_engine_ir(self._input(), engine=object())  # type: ignore[arg-type]

    def test_exact_capability_is_negotiated_before_manifest_validation(self) -> None:
        with (
            NativeEngine(self.library) as engine,
            mock.patch.object(engine, "query_capability", return_value=None),
            self.assertRaisesRegex(InspectionError, "required inspection contracts"),
        ):
            inspect_engine_ir(b"not JSON", engine=engine)

        with NativeEngine(self.library) as engine:
            manifest = engine.query_capability("morphoia.engine.ir-manifest")
            inspection = engine.query_capability(INSPECTION_PROFILE)
            assert manifest is not None and inspection is not None
            forged = replace(inspection, maximum_values=1)

            def query(name: str):
                return manifest if name == "morphoia.engine.ir-manifest" else forged

            with (
                mock.patch.object(engine, "query_capability", side_effect=query),
                self.assertRaisesRegex(InspectionError, "capability constants mismatch"),
            ):
                inspect_engine_ir(self._input(), engine=engine)

            forged_manifest = replace(manifest, maximum_values=1)

            def query_manifest_limit(name: str):
                return forged_manifest if name == "morphoia.engine.ir-manifest" else inspection

            with (
                mock.patch.object(
                    engine,
                    "query_capability",
                    side_effect=query_manifest_limit,
                ),
                self.assertRaisesRegex(InspectionError, "manifest capability constants"),
            ):
                inspect_engine_ir(self._input(), engine=engine)

    def test_default_engine_resolution_uses_configured_absolute_library(self) -> None:
        previous = os.environ.get("MORPHOIA_ENGINE_LIBRARY")
        os.environ["MORPHOIA_ENGINE_LIBRARY"] = os.fspath(self.library)
        try:
            result = inspect_engine_ir(self._input())
        finally:
            if previous is None:
                os.environ.pop("MORPHOIA_ENGINE_LIBRARY", None)
            else:
                os.environ["MORPHOIA_ENGINE_LIBRARY"] = previous
        self.assertTrue(result.qualified)

    def test_concurrent_inspection_is_deterministic_and_close_is_serialized(self) -> None:
        outputs: list[bytes] = []
        failures: list[BaseException] = []
        barrier = threading.Barrier(8)
        with NativeEngine(self.library) as engine:

            def inspect() -> None:
                try:
                    barrier.wait(timeout=5)
                    outputs.append(inspect_engine_ir(self._input(), engine=engine).canonical_report)
                except (OSError, RuntimeError, ValueError) as error:  # pragma: no cover
                    failures.append(error)

            threads = [threading.Thread(target=inspect) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive(), "concurrent inspection deadlocked")
        self.assertEqual(failures, [])
        self.assertEqual(len(outputs), 8)
        self.assertEqual(len(set(outputs)), 1)


if __name__ == "__main__":
    unittest.main()
