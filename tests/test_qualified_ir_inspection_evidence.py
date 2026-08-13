# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import errno
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_engine_qualified_ir_inspection_evidence.py"


def load_generator() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "morphoia_qualified_ir_evidence", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


generator = load_generator()


def write_bytes(root: Path, relative: str, content: bytes) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def strict_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


class QualifiedIrInspectionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.maximum = 0

    def make_profile_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="morphoia-qualified-evidence-")
        root = Path(temporary.name).resolve()
        for relative in generator.ARTIFACT_SPECS:
            write_bytes(root, relative, (ROOT / relative).read_bytes())
        index = strict_object(ROOT / "tests/fixtures/engine-ir/0.1.0/index.json")
        entries = index["entries"]
        assert isinstance(entries, list)
        for entry in entries:
            assert isinstance(entry, dict)
            relative = f"tests/fixtures/engine-ir/0.1.0/{entry['input']}"
            write_bytes(root, relative, (ROOT / relative).read_bytes())
        for relative in (generator.MANIFEST_PATH, generator.SBOM_PATH):
            if (ROOT / relative).exists():
                write_bytes(root, relative, (ROOT / relative).read_bytes())
        return temporary, root

    def test_committed_profile_matches_generator(self) -> None:
        manifest, sbom = generator.generate(ROOT)
        self.assertEqual((ROOT / generator.MANIFEST_PATH).read_bytes(), manifest)
        self.assertEqual((ROOT / generator.SBOM_PATH).read_bytes(), sbom)
        self.assertEqual(generator.main(["--root", os.fspath(ROOT), "--check"]), 0)

        manifest_schema = strict_object(ROOT / generator.MANIFEST_SCHEMA_PATH)
        report_vectors_schema = strict_object(ROOT / generator.REPORT_VECTORS_SCHEMA_PATH)
        trace_schema = strict_object(ROOT / generator.TRACEABILITY_SCHEMA_PATH)
        Draft202012Validator.check_schema(manifest_schema)
        Draft202012Validator.check_schema(report_vectors_schema)
        Draft202012Validator.check_schema(trace_schema)
        Draft202012Validator(manifest_schema).validate(
            strict_object(ROOT / generator.MANIFEST_PATH)
        )
        Draft202012Validator(trace_schema).validate(
            strict_object(ROOT / generator.TRACEABILITY_PATH)
        )
        Draft202012Validator(report_vectors_schema).validate(
            strict_object(ROOT / generator.REPORT_VECTORS_PATH)
        )

    def test_manifest_traceability_and_sbom_fail_closed(self) -> None:
        temporary, root = self.make_profile_copy()
        self.addCleanup(temporary.cleanup)
        expected_manifest, expected_sbom = generator.generate(root)
        manifest = generator.strict_json(expected_manifest, "prospective manifest")
        sbom = generator.strict_json(expected_sbom, "prospective SBOM")
        artifacts = manifest["artifacts"]
        components = sbom["components"]
        self.assertEqual(len(generator.ARTIFACT_SPECS), 54)
        self.assertEqual(len(artifacts), 55)
        self.assertEqual(len(artifacts), len(generator.ARTIFACT_SPECS) + 1)
        declared_packages = generator._parse_locks(
            {
                relative: (ROOT / relative).read_bytes()
                for relative in generator.LOCK_PATHS
            }
        )
        self.assertEqual(
            len(components), len(generator.ARTIFACT_SPECS) + len(declared_packages)
        )
        self.assertEqual(len(components), 63)
        self.assertNotIn("vulnerabilities", sbom)
        self.assertTrue(
            all(
                item["vulnerability_analysis_status"] == "NOT_RUN"
                for item in artifacts
            )
        )
        for component in components:
            properties = {
                item["name"]: item["value"] for item in component["properties"]
            }
            self.assertEqual(
                properties["morphoia:vulnerability-analysis-status"], "NOT_RUN"
            )
            self.assertEqual(
                properties["morphoia:dependency-license-review-status"], "NOT_RUN"
            )
        root_properties = {
            item["name"]: item["value"]
            for item in sbom["metadata"]["component"]["properties"]
        }
        self.assertEqual(
            root_properties["morphoia:vulnerability-analysis-status"], "NOT_RUN"
        )
        self.assertEqual(
            root_properties["morphoia:dependency-license-review-status"], "NOT_RUN"
        )

        trace = generator.strict_json(
            (root / generator.TRACEABILITY_PATH).read_bytes(),
            generator.TRACEABILITY_PATH,
        )
        commands = {item["id"]: item for item in trace["execution_environment"]["commands"]}
        full_regression = commands["full-python-regression"]
        self.assertEqual(full_regression["status"], "PASS")
        self.assertEqual(
            full_regression["result"],
            "The final full Python regression passed 206/206 tests in 84.942 "
            "seconds on CPython 3.12.13.",
        )
        requirements = {item["requirement_id"]: item for item in trace["entries"]}
        self.assertEqual(
            set(requirements), {"MOR-IR-006", "MOR-API-006", "MOR-QA-017"}
        )
        for requirement in requirements.values():
            self.assertEqual(requirement["status"], "NOT_RUN")
            self.assertIn("full-regression", requirement["reason"])
            self.assertIn("hosted", requirement["reason"])
            self.assertIn("review", requirement["reason"])
            self.assertIn("integration", requirement["reason"])
            self.assertNotIn("final full regression", requirement["reason"])
            self.assertNotIn("full-regression", requirement["blocking_scope"])

        mutations = {
            "unit tuple": (
                "cpp/src/core/unit_registry.cpp",
                lambda data: data.replace(b'{"mm", Dimensions{1, 0, 0, 0, 0, 0, 0}, 1, -3}', b'{"mm", Dimensions{1, 0, 0, 0, 0, 0, 0}, 10, -4}'),
            ),
            "ninth export": (
                "cmake/morphoia_engine.map",
                lambda data: data.replace(b"  local:\n", b"    morphoia_unqualified_extra;\n  local:\n"),
            ),
            "nineteenth graph": (
                "tests/fixtures/engine-ir/0.1.0/index.json",
                lambda data: generator.deterministic_json(
                    {
                        **generator.strict_json(data, "index"),
                        "entries": generator.strict_json(data, "index")["entries"][:-1],
                    }
                ),
            ),
            "freeze count": (
                "spec/evidence/e1-public-ir-freeze.json",
                lambda data: generator.deterministic_json(
                    {
                        **generator.strict_json(data, "freeze"),
                        "git_snapshot": {
                            **generator.strict_json(data, "freeze")["git_snapshot"],
                            "entry_count": 308,
                        },
                    }
                ),
            ),
            "trace status": (
                generator.TRACEABILITY_PATH,
                lambda data: data.replace(
                    b'"id": "hosted-python-3-13",\n        "command"',
                    b'"id": "hosted-python-3-13-mutated",\n        "command"',
                ),
            ),
            "report vector": (
                generator.REPORT_VECTORS_PATH,
                lambda data: data.replace(
                    b'"report_size_bytes": 3751',
                    b'"report_size_bytes": 3752',
                    1,
                ),
            ),
            "evidence schema identifier": (
                generator.REPORT_VECTORS_SCHEMA_PATH,
                lambda data: data.replace(
                    b"qualified-ir-inspection-0.1-report-vectors-1.0.schema.json",
                    b"qualified-ir-inspection-0.1-report-vectors-9.9.schema.json",
                    1,
                ),
            ),
        }
        for label, (relative, mutate) in mutations.items():
            with self.subTest(label=label):
                path = root / relative
                original = path.read_bytes()
                changed = mutate(original)
                self.assertNotEqual(changed, original)
                path.write_bytes(changed)
                with self.assertRaises(generator.EvidenceError):
                    generator.generate(root)
                path.write_bytes(original)

        write_bytes(root, generator.MANIFEST_PATH, expected_manifest + b" ")
        with self.assertRaises(generator.EvidenceError):
            generator.check_output(root, generator.MANIFEST_PATH, expected_manifest)
        write_bytes(root, generator.SBOM_PATH, expected_sbom + b" ")
        with self.assertRaises(generator.EvidenceError):
            generator.check_output(root, generator.SBOM_PATH, expected_sbom)

    def test_inventory_unit_exports_reports_and_freeze_are_exact(self) -> None:
        contents = generator.validate_profile(ROOT)
        self.assertEqual(set(contents), set(generator.ARTIFACT_SPECS))
        self.assertEqual(len(generator.EXPECTED_UNITS), 10)
        self.assertEqual(len(generator.EXPECTED_EXPORTS), 8)
        index = generator.read_repository_json(
            ROOT, "tests/fixtures/engine-ir/0.1.0/index.json"
        )
        self.assertEqual(len(index["entries"]), 20)
        freeze = generator.read_repository_json(
            ROOT, "spec/evidence/e1-public-ir-freeze.json"
        )
        self.assertEqual(freeze["git_snapshot"]["entry_count"], 309)
        self.assertEqual(freeze["counts"]["historical_evidence_tests"], 22)
        vectors = generator.read_repository_json(ROOT, generator.REPORT_VECTORS_PATH)
        self.assertEqual(vectors["pass_count"], 2)
        self.assertTrue(vectors["passes_identical"])
        self.assertEqual(len(vectors["vectors"]), 20)
        self.assertFalse((ROOT / "tests/test_e1_public_ir_evidence.py").exists())

        report = (ROOT / generator.REPORT_PATH).read_text(encoding="utf-8")
        for literal in ("`1`", "`m`", "`mm`", "`s`", "`kg`", "`g`", "`A`", "`K`", "`mol`", "`cd`"):
            self.assertIn(literal, report)
        self.assertIn("No UCUM specification text", report)
        self.assertIn("general UCUM", report)

    def test_path_aliases_duplicate_json_and_atomic_publication_fail_closed(self) -> None:
        malformed = (
            b'{"a":1,"a":2}',
            b'{"a":1.5}',
            b'{"a":NaN}',
            b'{"a":9007199254740992}',
            b'{"a":"\\ud800"}',
        )
        for content in malformed:
            with self.subTest(content=content), self.assertRaises(
                (generator.EvidenceError, generator.DuplicateKeyError)
            ):
                generator.strict_json(content, "mutation")

        for alias in ("symlink", "hardlink"):
            with self.subTest(alias=alias):
                temporary, root = self.make_profile_copy()
                try:
                    trace = root / generator.TRACEABILITY_PATH
                    original = trace.read_bytes()
                    trace.unlink()
                    target = root / "trace-target.json"
                    target.write_bytes(original)
                    if alias == "symlink":
                        trace.symlink_to(target)
                    else:
                        os.link(target, trace)
                    with self.assertRaises(generator.EvidenceError):
                        generator.generate(root)
                finally:
                    temporary.cleanup()

        temporary, root = self.make_profile_copy()
        self.addCleanup(temporary.cleanup)
        target_relative = "artifacts/manifests/atomic-test.json"
        content = b'{"status":"PASS"}\n'
        generator.atomic_write(root, target_relative, content)
        self.assertEqual((root / target_relative).read_bytes(), content)
        self.assertEqual((root / target_relative).stat().st_mode & 0o777, 0o644)
        generator.atomic_write(root, target_relative, content)
        self.assertEqual((root / target_relative).read_bytes(), content)
        self.assertEqual((root / target_relative).stat().st_mode & 0o777, 0o644)
        self.assertEqual(
            list((root / "artifacts/manifests").glob(".atomic-test.json.tmp-*")),
            [],
        )

        target = root / target_relative
        target.unlink()
        alias_target = root / "alias-target.json"
        alias_target.write_bytes(b"preserve")
        target.symlink_to(alias_target)
        with self.assertRaises(generator.EvidenceError):
            generator.atomic_write(root, target_relative, content)
        self.assertEqual(alias_target.read_bytes(), b"preserve")
        target.unlink()

        target.write_bytes(b"old")
        original_rename = generator._renameat2
        invoked = False

        def mutate_before_exchange(
            old_directory: int,
            old_name: str,
            new_directory: int,
            new_name: str,
            flags: int,
        ) -> None:
            nonlocal invoked
            if flags == generator.RENAME_EXCHANGE and not invoked:
                invoked = True
                target.write_bytes(b"raced")
            original_rename(old_directory, old_name, new_directory, new_name, flags)

        with mock.patch.object(generator, "_renameat2", mutate_before_exchange), self.assertRaises(
            generator.EvidenceError
        ):
            generator.atomic_write(root, target_relative, content)
        self.assertEqual(target.read_bytes(), b"raced")

        target.write_bytes(b"old-after-exchange")
        mutated_after_exchange = False

        def mutate_after_exchange(
            old_directory: int,
            old_name: str,
            new_directory: int,
            new_name: str,
            flags: int,
        ) -> None:
            nonlocal mutated_after_exchange
            original_rename(old_directory, old_name, new_directory, new_name, flags)
            if flags == generator.RENAME_EXCHANGE and not mutated_after_exchange:
                mutated_after_exchange = True
                target.write_bytes(b"corrupt-new-output")

        with mock.patch.object(
            generator, "_renameat2", mutate_after_exchange
        ), self.assertRaises(generator.EvidenceError):
            generator.atomic_write(root, target_relative, content)
        self.assertEqual(target.read_bytes(), b"old-after-exchange")

        target.unlink()
        collision = False

        def collide_noreplace(
            old_directory: int,
            old_name: str,
            new_directory: int,
            new_name: str,
            flags: int,
        ) -> None:
            nonlocal collision
            if flags == generator.RENAME_NOREPLACE and not collision:
                collision = True
                target.write_bytes(b"competitor")
                raise OSError(errno.EEXIST, os.strerror(errno.EEXIST))
            original_rename(old_directory, old_name, new_directory, new_name, flags)

        with mock.patch.object(generator, "_renameat2", collide_noreplace), self.assertRaises(
            generator.EvidenceError
        ):
            generator.atomic_write(root, target_relative, content)
        self.assertEqual(target.read_bytes(), b"competitor")


if __name__ == "__main__":
    unittest.main()
