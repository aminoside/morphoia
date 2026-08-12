# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_engine_e1_native_evidence.py"


def load_script(path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "morphoia_e1_native_evidence_validator", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


validator = load_script(VALIDATOR_PATH)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected an object in {path}")
    return value


def copy_profile(root: Path) -> None:
    relatives = {
        *validator.FROZEN_FILES,
        validator.EXPECTED_ARTIFACTS[validator.ADR_ARTIFACT_ID]["path"],
    }
    for relative in relatives:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)


@contextmanager
def refreshed_pins(root: Path, *relatives: str) -> Iterator[None]:
    updates = {relative: digest(root / relative) for relative in relatives}
    with patch.dict(validator.FROZEN_FILES, updates):
        yield


def update_self_entry(root: Path) -> None:
    sbom = root / validator.SBOM_PATH
    manifest_path = root / validator.MANIFEST_PATH
    manifest = read_json(manifest_path)
    entry = next(
        item
        for item in manifest["artifacts"]
        if item["id"] == validator.SELF_ARTIFACT_ID
    )
    entry["sha256"] = digest(sbom)
    entry["size_bytes"] = sbom.stat().st_size
    write_json(manifest_path, manifest)


class FrozenE1NativeEvidenceTests(unittest.TestCase):
    def test_committed_profile_and_cli_pass(self) -> None:
        self.assertEqual(validator.validate(ROOT), [])
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "--root", str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("byte-exact", completed.stdout)

    def test_every_frozen_file_is_byte_pinned(self) -> None:
        for relative in validator.FROZEN_FILES:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory(
                prefix="morphoia-e1-pin-"
            ) as directory:
                root = Path(directory)
                copy_profile(root)
                path = root / relative
                path.write_bytes(path.read_bytes() + b"\n")
                errors = validator.validate(root)
                self.assertTrue(errors)
                self.assertTrue(
                    any(f"digest differs for {relative}" in error for error in errors),
                    errors,
                )

    def test_duplicate_keys_nan_infinity_and_floats_are_rejected(self) -> None:
        invalid_documents = {
            "duplicate": '{"field":1,"field":1}',
            "nan": '{"field":NaN}',
            "infinity": '{"field":Infinity}',
            "float": '{"field":1.5}',
        }
        with tempfile.TemporaryDirectory(prefix="morphoia-e1-json-") as directory:
            path = Path(directory) / "invalid.json"
            for label, content in invalid_documents.items():
                with self.subTest(label=label):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises((ValueError, json.JSONDecodeError)):
                        validator.read_json_object(path)

    def test_manifest_self_entry_and_report_coherence_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e1-self-") as directory:
            root = Path(directory)
            copy_profile(root)
            manifest_path = root / validator.MANIFEST_PATH
            manifest = read_json(manifest_path)
            self_entry = next(
                item
                for item in manifest["artifacts"]
                if item["id"] == validator.SELF_ARTIFACT_ID
            )
            self_entry["sha256"] = "0" * 64
            write_json(manifest_path, manifest)
            with refreshed_pins(root, validator.MANIFEST_PATH):
                errors = validator.validate(root)
            self.assertTrue(any("digest or size differs" in error for error in errors), errors)

        with tempfile.TemporaryDirectory(prefix="morphoia-e1-report-") as directory:
            root = Path(directory)
            copy_profile(root)
            report = root / validator.REPORT_PATH
            report.write_bytes(report.read_bytes() + b"mutation\n")
            with refreshed_pins(root, validator.REPORT_PATH):
                errors = validator.validate(root)
            self.assertTrue(
                any("report" in error and "differs" in error for error in errors), errors
            )

    def test_profile_and_vulnerability_truth_fail_closed_beyond_hash_pins(self) -> None:
        mutations = {
            "profile": (
                "morphoia:profile",
                "different-profile",
                "profile must remain",
            ),
            "vulnerability": (
                "morphoia:vulnerability-analysis-status",
                "PASS",
                "vulnerability status must remain NOT_RUN",
            ),
        }
        for label, (name, value, message) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="morphoia-e1-truth-"
            ) as directory:
                root = Path(directory)
                copy_profile(root)
                sbom_path = root / validator.SBOM_PATH
                sbom = read_json(sbom_path)
                properties = sbom["metadata"]["component"]["properties"]
                next(item for item in properties if item["name"] == name)["value"] = value
                write_json(sbom_path, sbom)
                update_self_entry(root)
                with refreshed_pins(root, validator.SBOM_PATH, validator.MANIFEST_PATH):
                    errors = validator.validate(root)
                self.assertTrue(any(message in error for error in errors), errors)

        with tempfile.TemporaryDirectory(prefix="morphoia-e1-manifest-truth-") as directory:
            root = Path(directory)
            copy_profile(root)
            manifest_path = root / validator.MANIFEST_PATH
            manifest = read_json(manifest_path)
            self_entry = next(
                item
                for item in manifest["artifacts"]
                if item["id"] == validator.SELF_ARTIFACT_ID
            )
            self_entry["vulnerability_analysis_status"] = "PASS"
            write_json(manifest_path, manifest)
            with refreshed_pins(root, validator.MANIFEST_PATH):
                errors = validator.validate(root)
            self.assertTrue(
                any(
                    "manifest vulnerability status must remain NOT_RUN" in error
                    for error in errors
                ),
                errors,
            )

    def test_sbom_artifact_component_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e1-component-") as directory:
            root = Path(directory)
            copy_profile(root)
            sbom_path = root / validator.SBOM_PATH
            sbom = read_json(sbom_path)
            reference = f"urn:morphoia:artifact:{validator.REPORT_ARTIFACT_ID}"
            component = next(item for item in sbom["components"] if item["bom-ref"] == reference)
            component["hashes"][0]["content"] = "0" * 64
            write_json(sbom_path, sbom)
            update_self_entry(root)
            with refreshed_pins(root, validator.SBOM_PATH, validator.MANIFEST_PATH):
                errors = validator.validate(root)
            self.assertTrue(any("component hash differs" in error for error in errors), errors)

    def test_paths_reject_traversal_symlinks_and_hard_link_aliases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e1-path-") as directory:
            root = Path(directory)
            copy_profile(root)
            for relative in ("../outside", "docs/./engine/report.md", "/absolute"):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    validator.repository_file(root, relative)

        with tempfile.TemporaryDirectory(prefix="morphoia-e1-final-link-") as directory:
            root = Path(directory)
            copy_profile(root)
            report = root / validator.REPORT_PATH
            target = root / "outside-report"
            target.write_bytes(report.read_bytes())
            report.unlink()
            report.symlink_to(target)
            errors = validator.validate(root)
            self.assertTrue(any("symbolic link" in error for error in errors), errors)

        with tempfile.TemporaryDirectory(prefix="morphoia-e1-parent-link-") as directory:
            root = Path(directory)
            copy_profile(root)
            docs = root / "docs"
            relocated = root / "relocated-docs"
            docs.rename(relocated)
            docs.symlink_to(relocated, target_is_directory=True)
            errors = validator.validate(root)
            self.assertTrue(any("symbolic link" in error for error in errors), errors)

        with tempfile.TemporaryDirectory(prefix="morphoia-e1-hard-link-") as directory:
            root = Path(directory)
            copy_profile(root)
            report = root / validator.REPORT_PATH
            alias = root / "report-alias"
            os.link(report, alias)
            errors = validator.validate(root)
            self.assertTrue(any("hard-link alias" in error for error in errors), errors)

    def test_manifest_traversal_is_rejected_after_repinning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e1-manifest-path-") as directory:
            root = Path(directory)
            copy_profile(root)
            manifest_path = root / validator.MANIFEST_PATH
            manifest = copy.deepcopy(read_json(manifest_path))
            manifest["artifacts"][0]["path"] = "../outside-report"
            write_json(manifest_path, manifest)
            with refreshed_pins(root, validator.MANIFEST_PATH):
                errors = validator.validate(root)
            self.assertTrue(any("wrong path" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
