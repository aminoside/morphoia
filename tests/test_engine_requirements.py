# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_engine_requirements.py"
CATALOGUE = ROOT / "spec" / "requirements" / "requirements.yaml"
TRACKING = ROOT / "spec" / "requirements" / "requirements-tracking.yaml"
PDF_BRANDING_SCRIPT = ROOT / "scripts" / "check_pdf_branding.py"
PDF = (
    ROOT
    / "docs"
    / "engine"
    / "baselines"
    / "Morphoia_Engine_Cahier_des_charges_technique_v0.1.pdf"
)
BASELINES = {
    PDF: "40cdb3288e7b1a38a557d1459147aed7ac1d5646aaa5d6ab09a287abc9b22263",
    ROOT
    / "docs"
    / "engine"
    / "baselines"
    / "Morphoia_Engine_Architecture_Reference_v0.2.pdf": (
        "8519bba50ab9a05d469780ec074588034714d83d24ef09404705d292bfa02368"
    ),
    ROOT / "docs" / "engine" / "baselines" / "morphoia-logo-vectoriel.zip": (
        "d9957fb70c18f2cdea37b7a036e3ddab6b05492d1a3ea978f5ea9f33313c00c5"
    ),
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class EngineRequirementsTests(unittest.TestCase):
    def run_check(
        self,
        catalogue: Path = CATALOGUE,
        tracking: Path = TRACKING,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--check",
                "--output",
                str(catalogue),
                "--tracking-output",
                str(tracking),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_mutation_rejected(
        self,
        mutate_catalogue: Callable[[dict[str, Any]], None] | None = None,
        mutate_tracking: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-requirements-test-") as directory:
            directory_path = Path(directory)
            catalogue_path = directory_path / "requirements.yaml"
            tracking_path = directory_path / "requirements-tracking.yaml"
            catalogue = read_json(CATALOGUE)
            tracking = read_json(TRACKING)
            if mutate_catalogue is not None:
                mutate_catalogue(catalogue)
            if mutate_tracking is not None:
                mutate_tracking(tracking)
            write_json(catalogue_path, catalogue)
            write_json(tracking_path, tracking)
            completed = self.run_check(catalogue_path, tracking_path)
            self.assertNotEqual(completed.returncode, 0, completed.stdout)
            self.assertIn("FAIL:", completed.stderr)

    def test_baseline_digests(self) -> None:
        for path, expected in BASELINES.items():
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_logo_archive_is_bounded_and_confined(self) -> None:
        archive_path = ROOT / "docs" / "engine" / "baselines" / "morphoia-logo-vectoriel.zip"
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            self.assertEqual(len(entries), 11)
            self.assertLess(sum(item.file_size for item in entries), 1024 * 1024)
            for item in entries:
                with self.subTest(entry=item.filename):
                    path = Path(item.filename)
                    self.assertFalse(path.is_absolute())
                    self.assertNotIn("..", path.parts)
                    self.assertEqual(item.flag_bits & 0x1, 0, "encrypted entry")
                    self.assertLess(item.file_size, 256 * 1024)
            self.assertIsNone(archive.testzip())

    def test_immutable_engine_baselines_are_not_treated_as_branded_reports(self) -> None:
        specification = importlib.util.spec_from_file_location(
            "morphoia_pdf_branding", PDF_BRANDING_SCRIPT
        )
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        tracked = set(module.tracked_pdfs())
        declared = {
            entry["path"]
            for entry in read_json(ROOT / "reports.json")["reports"]
        }
        expected_baselines = {
            path.relative_to(ROOT).as_posix()
            for path in BASELINES
            if path.suffix == ".pdf"
        }
        self.assertEqual(set(module.IMMUTABLE_BASELINE_PDFS), expected_baselines)
        self.assertEqual(tracked, declared)
        completed = subprocess.run(
            ["git", "ls-files", "--", "*.pdf"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        all_tracked = {line for line in completed.stdout.splitlines() if line}
        self.assertEqual(all_tracked, declared | expected_baselines)

    def test_catalogue_and_tracking_are_exact(self) -> None:
        completed = self.run_check()
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_immutable_catalogue_is_separate_from_tracking(self) -> None:
        catalogue = read_json(CATALOGUE)
        self.assertEqual(catalogue["schema_version"], "1.1.0")
        self.assertEqual(len(catalogue["requirements"]), 320)
        self.assertTrue(all("tracking" not in item for item in catalogue["requirements"]))
        self.assertEqual(
            catalogue["baseline"]["records_sha256"],
            "5e65c204e35ba98453669095ede587b2573d3a6f35d7841d16d26104794131ba",
        )
        self.assertEqual(
            catalogue["baseline"]["immutable_records_sha256"],
            "b846a2f284ad0510b43ca6fdba8ad4fae7d1b40daf2f77305c8153e6a9de4072",
        )

    def test_tracking_starts_fail_closed(self) -> None:
        tracking = read_json(TRACKING)
        entries = tracking["entries"]
        self.assertEqual(len(entries), 320)
        self.assertTrue(all(item["status"] == "NOT_RUN" for item in entries.values()))
        self.assertTrue(
            all(item["dependency_mapping"] == "UNMAPPED" for item in entries.values())
        )
        self.assertTrue(all(not item["test_ids"] for item in entries.values()))
        self.assertTrue(all(not item["evidence"] for item in entries.values()))

    def test_catalogue_mutations_are_rejected(self) -> None:
        mutations: dict[str, Callable[[dict[str, Any]], None]] = {
            "unknown top-level field": lambda data: data.__setitem__("unexpected", True),
            "schema reference": lambda data: data.__setitem__("$schema", "wrong-schema.json"),
            "baseline hash": lambda data: data["baseline"].__setitem__("records_sha256", "0" * 64),
            "summary": lambda data: data["summary"].__setitem__("total", 319),
            "priority type": lambda data: data["requirements"][0].__setitem__("priority", []),
            "derived phase": lambda data: data["requirements"][0]["phase"].__setitem__("end", 4),
            "derived proof": lambda data: data["requirements"][0]["proof"].__setitem__(
                "methods", ["analysis"]
            ),
            "source coordinate": lambda data: data["requirements"][0]["source"][
                "text_lines"
            ].__setitem__(0, 1),
            "source digest": lambda data: data["requirements"][0]["source"].__setitem__(
                "source_sha256", "0" * 64
            ),
            "quality flag": lambda data: data["requirements"][0].__setitem__(
                "quality_flags", ["modal_priority_mismatch"]
            ),
            "record digest": lambda data: data["requirements"][0].__setitem__(
                "record_sha256", "0" * 64
            ),
            "unknown record field": lambda data: data["requirements"][0].__setitem__(
                "unexpected", True
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                self.assert_mutation_rejected(mutate_catalogue=mutation)

    def test_tracking_mutations_are_rejected(self) -> None:
        requirement_id = "MOR-SCP-001"

        def wrong_component(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["component"] = "core/ir"

        def wrong_gates(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["gate_candidates"] = ["G5"]

        def unknown_field(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["unexpected"] = True

        def pass_without_proof(data: dict[str, Any]) -> None:
            entry = data["entries"][requirement_id]
            entry["status"] = "PASS"
            entry["mapping_status"] = "COMPLETE"
            entry["dependency_mapping"] = "NOT_APPLICABLE"

        def fail_without_proof(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["status"] = "FAIL"

        def blocked_without_blocker(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["status"] = "BLOCKED"

        def not_applicable_without_justification(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["status"] = "NOT_APPLICABLE"

        def remove_entry(data: dict[str, Any]) -> None:
            del data["entries"][requirement_id]

        def invalid_dependency_mapping_type(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["dependency_mapping"] = []

        def invalid_status_type(data: dict[str, Any]) -> None:
            data["entries"][requirement_id]["status"] = {}

        mutations = {
            "family/component mapping": wrong_component,
            "gate candidates": wrong_gates,
            "unknown tracking field": unknown_field,
            "PASS without test and evidence": pass_without_proof,
            "FAIL without test and evidence": fail_without_proof,
            "BLOCKED without dependency and evidence": blocked_without_blocker,
            "NOT_APPLICABLE without justification": not_applicable_without_justification,
            "missing requirement tracking": remove_entry,
            "dependency mapping type": invalid_dependency_mapping_type,
            "status type": invalid_status_type,
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                self.assert_mutation_rejected(mutate_tracking=mutation)

    def test_regeneration_preserves_valid_tracking_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-requirements-regen-") as directory:
            directory_path = Path(directory)
            catalogue_path = directory_path / "requirements.yaml"
            tracking_path = directory_path / "requirements-tracking.yaml"
            shutil.copyfile(CATALOGUE, catalogue_path)
            tracking = copy.deepcopy(read_json(TRACKING))
            entry = tracking["entries"]["MOR-SCP-001"]
            entry.update(
                {
                    "issue": "https://github.com/Aminoside/morphoia/issues/1",
                    "test_ids": ["tests/test_engine_requirements.py::test_example"],
                    "evidence": ["artifact:sha256:0123456789abcdef"],
                    "dependency_mapping": "NOT_APPLICABLE",
                    "status": "PASS",
                    "status_reason": None,
                    "mapping_status": "COMPLETE",
                }
            )
            write_json(tracking_path, tracking)
            before = tracking_path.read_bytes()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--pdf",
                    str(PDF),
                    "--output",
                    str(catalogue_path),
                    "--tracking-output",
                    str(tracking_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(tracking_path.read_bytes(), before)
            self.assertEqual(catalogue_path.read_bytes(), CATALOGUE.read_bytes())
            self.assertIn("preserved existing tracking overlay byte-for-byte", completed.stdout)

    def test_invalid_tracking_blocks_regeneration_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-requirements-regen-fail-") as directory:
            directory_path = Path(directory)
            catalogue_path = directory_path / "requirements.yaml"
            tracking_path = directory_path / "requirements-tracking.yaml"
            shutil.copyfile(CATALOGUE, catalogue_path)
            tracking = read_json(TRACKING)
            tracking["entries"]["MOR-SCP-001"]["status"] = "PASS"
            write_json(tracking_path, tracking)
            before_catalogue = catalogue_path.read_bytes()
            before_tracking = tracking_path.read_bytes()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--pdf",
                    str(PDF),
                    "--output",
                    str(catalogue_path),
                    "--tracking-output",
                    str(tracking_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0, completed.stdout)
            self.assertEqual(catalogue_path.read_bytes(), before_catalogue)
            self.assertEqual(tracking_path.read_bytes(), before_tracking)


if __name__ == "__main__":
    unittest.main()
