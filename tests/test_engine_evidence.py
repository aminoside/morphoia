# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
from typing import Any
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs" / "engine" / "checkpoint.json"
MANIFEST = ROOT / "artifacts" / "manifest.json"
SBOM = ROOT / "artifacts" / "sbom" / "engine-e0-source-native.cdx.json"
CHECKPOINT_SCRIPT = ROOT / "scripts" / "validate_engine_checkpoint.py"
SBOM_SCRIPT = ROOT / "scripts" / "generate_engine_sbom.py"


def load_script(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


checkpoint_module = load_script("morphoia_checkpoint_validator", CHECKPOINT_SCRIPT)
sbom_module = load_script("morphoia_sbom_generator", SBOM_SCRIPT)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_reconciled_checkpoint() -> dict[str, Any]:
    checkpoint = copy.deepcopy(read_json(CHECKPOINT))
    excluded = checkpoint["source_digests"]["excluded"]
    for item in checkpoint["source_digests"]["paths"]:
        item["status"] = "PASS"
        item["sha256"] = checkpoint_module.tree_sha256(ROOT, item["path"], excluded)
    for output in checkpoint["outputs"]:
        if output["status"] == "PASS" and output["uri"].startswith("repo:"):
            output["sha256"] = checkpoint_module.sha256_file(
                ROOT / output["uri"].removeprefix("repo:")
            )
    for dependency in checkpoint["external_dependencies"]:
        if dependency["status"] != "PASS" and not any(
            dependency.get(field) for field in ("reason", "blocking_scope")
        ):
            dependency["reason"] = "External prerequisite has not been executed in E0"
    return checkpoint


class CheckpointEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checkpoint = make_reconciled_checkpoint()

    def test_reconciled_checkpoint_passes_semantic_and_digest_validation(self) -> None:
        self.assertEqual(checkpoint_module.validate_checkpoint(self.checkpoint, ROOT), [])

    def test_committed_checkpoint_passes_fail_closed_validator(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CHECKPOINT_SCRIPT), "--root", str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_checkpoint_mutations_fail_closed(self) -> None:
        mutations = {
            "unknown top-level field": lambda value: value.__setitem__("unexpected", True),
            "overlapping task": lambda value: value["tasks"]["remaining"].append(
                value["tasks"]["completed"][0]
            ),
            "unauthorized branch": lambda value: value["git"].__setitem__("branch", "main"),
            "missing output digest": lambda value: value["outputs"][0].__setitem__(
                "sha256", None
            ),
            "false output digest": lambda value: value["outputs"][0].__setitem__(
                "sha256", "0" * 64
            ),
            "invalid test status": lambda value: value["tests"][0].__setitem__(
                "status", "SKIPPED"
            ),
            "invalid status type": lambda value: value["tests"][0].__setitem__(
                "status", {}
            ),
            "invalid test id type": lambda value: value["tests"][0].__setitem__(
                "id", []
            ),
            "invalid input path type": lambda value: value["inputs"][0].__setitem__(
                "path", []
            ),
            "unsafe input path": lambda value: value["inputs"][0].__setitem__(
                "path", "../outside.pdf"
            ),
            "missing baseline": lambda value: value["inputs"].pop(0),
            "false source digest": lambda value: value["source_digests"]["paths"][0].__setitem__(
                "sha256", "0" * 64
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(self.checkpoint)
                mutation(value)
                self.assertTrue(checkpoint_module.validate_checkpoint(value, ROOT))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-checkpoint-json-") as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":"1.0.0","schema_version":"1.0.0"}\n')
            with self.assertRaises(ValueError):
                checkpoint_module.load_json(path)

    def test_tree_digest_is_stable_and_honors_checkpoint_exclusion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-tree-digest-") as directory:
            root = Path(directory)
            source = root / "docs" / "engine"
            source.mkdir(parents=True)
            (source / "checkpoint.json").write_text("first\n", encoding="utf-8")
            (source / "evidence.txt").write_text("stable\n", encoding="utf-8")
            excluded = ["docs/engine/checkpoint.json"]
            first = checkpoint_module.tree_sha256(root, "docs/engine", excluded)
            (source / "checkpoint.json").write_text("second\n", encoding="utf-8")
            second = checkpoint_module.tree_sha256(root, "docs/engine", excluded)
            self.assertEqual(first, second)
            (source / "evidence.txt").write_text("changed\n", encoding="utf-8")
            self.assertNotEqual(
                second, checkpoint_module.tree_sha256(root, "docs/engine", excluded)
            )


class EngineSbomTests(unittest.TestCase):
    def test_artifact_manifest_is_explicit_and_hash_exact(self) -> None:
        manifest = read_json(MANIFEST)
        self.assertEqual(manifest["manifest_document_license"], "CC-BY-4.0")
        self.assertNotIn("license", manifest)
        identifiers: set[str] = set()
        paths: set[str] = set()
        for artifact in manifest["artifacts"]:
            with self.subTest(artifact=artifact["id"]):
                self.assertNotIn(artifact["id"], identifiers)
                self.assertNotIn(artifact["path"], paths)
                identifiers.add(artifact["id"])
                paths.add(artifact["path"])
                self.assertTrue(artifact["license_expression"])
                path = ROOT / artifact["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, artifact["size_bytes"])
                self.assertEqual(sbom_module.sha256_file(path), artifact["sha256"])
        self.assertIn("requirements-catalog-v0.1", identifiers)
        self.assertIn("requirements-tracking-v1", identifiers)
        self.assertIn(sbom_module.SELF_ARTIFACT_ID, identifiers)

    def test_sbom_is_deterministic_and_matches_manifest_digest(self) -> None:
        generated = sbom_module.canonical_json(sbom_module.build_bom(ROOT, MANIFEST))
        committed = SBOM.read_text(encoding="utf-8")
        self.assertEqual(generated, committed)
        manifest = read_json(MANIFEST)
        entry = next(
            item for item in manifest["artifacts"] if item["id"] == sbom_module.SELF_ARTIFACT_ID
        )
        self.assertEqual(hashlib.sha256(committed.encode("utf-8")).hexdigest(), entry["sha256"])
        completed = subprocess.run(
            [sys.executable, str(SBOM_SCRIPT), "--root", str(ROOT), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_sbom_declares_scope_and_does_not_claim_vulnerability_analysis(self) -> None:
        sbom = read_json(SBOM)
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertNotIn("vulnerabilities", sbom)
        root_component = sbom["metadata"]["component"]
        properties = {item["name"]: item["value"] for item in root_component["properties"]}
        self.assertEqual(properties["morphoia:profile"], "e0-source-native")
        self.assertEqual(properties["morphoia:vulnerability-analysis-status"], "NOT_RUN")
        self.assertEqual(root_component["licenses"], [{"expression": "Apache-2.0 OR MIT"}])

    def test_locked_packages_are_not_claimed_shipped(self) -> None:
        sbom = read_json(SBOM)
        components = sbom["components"]
        system = [
            component
            for component in components
            if component["bom-ref"].startswith("urn:morphoia:system-tool:")
        ]
        self.assertEqual(system, [])

        expected_packages = sbom_module.parse_locks(ROOT)
        self.assertEqual(
            expected_packages[("rpds-py", "2026.6.3")]["hashes"],
            {
                "ecabd69db66de867690f9797f2f8fa27ba501bbc24540cbdbdc649cd15888ba6",
                "acac386b453c2516111b50985d60ce46e7fadb5ea71ae7b25f4c946935bf27cf",
            },
        )
        self.assertIn(("cmake", "3.20.5"), expected_packages)
        package_components = {
            (item["name"], item["version"]): item
            for item in components
            if item["bom-ref"].startswith("pkg:pypi/")
        }
        self.assertEqual(set(package_components), set(expected_packages))
        for component in package_components.values():
            self.assertEqual(component["scope"], "excluded")
            self.assertEqual(
                component["licenses"],
                [{"license": {"name": "NOASSERTION"}}],
            )

    def test_native_source_profile_includes_installed_package_consumer(self) -> None:
        selected = set(sbom_module.collect_source_files(ROOT))
        self.assertIn("tests/native/consumer/CMakeLists.txt", selected)
        self.assertIn("tests/native/consumer/main.c", selected)
        self.assertIn("tests/native/incompatible_consumer/CMakeLists.txt", selected)

    def test_stale_manifest_hash_is_rejected(self) -> None:
        manifest = read_json(MANIFEST)
        manifest["artifacts"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(prefix="morphoia-manifest-") as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                sbom_module.build_bom(ROOT, path)

    def test_manifest_provenance_rejects_self_dangling_and_cycles(self) -> None:
        base = read_json(MANIFEST)
        mutations = {
            "self": lambda values: next(
                item for item in values if item["id"] == "baseline-technical-spec-v0.1-layout"
            ).__setitem__("source_artifact_id", "baseline-technical-spec-v0.1-layout"),
            "dangling": lambda values: next(
                item for item in values if item["id"] == "requirements-catalog-v0.1"
            ).__setitem__("source_artifact_id", "missing-source"),
            "cycle": lambda values: next(
                item for item in values if item["id"] == "baseline-technical-spec-v0.1"
            ).__setitem__("source_artifact_id", "requirements-catalog-v0.1"),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="morphoia-manifest-provenance-"
            ) as directory:
                manifest = copy.deepcopy(base)
                mutation(manifest["artifacts"])
                path = Path(directory) / "manifest.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    sbom_module.build_bom(ROOT, path)

    def test_lock_parser_rejects_package_without_its_own_hash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-lock-parser-") as directory:
            root = Path(directory)
            lock = root / sbom_module.LOCK_FILES[0]
            lock.parent.mkdir(parents=True)
            lock.write_text(
                "first==1.0 \\\n"
                "second==2.0 \\\n"
                "    --hash=sha256:" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                sbom_module.parse_locks(root)

    def test_lock_parser_rejects_unhashed_duplicate_declaration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-lock-duplicate-") as directory:
            root = Path(directory)
            first = root / "requirements" / "first.lock"
            second = root / "requirements" / "second.lock"
            first.parent.mkdir(parents=True)
            first.write_text(
                "same-package==1.0 \\\n"
                "    --hash=sha256:" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            second.write_text("same-package==1.0 \\\n", encoding="utf-8")
            original = sbom_module.LOCK_FILES
            sbom_module.LOCK_FILES = (
                "requirements/first.lock",
                "requirements/second.lock",
            )
            try:
                with self.assertRaisesRegex(ValueError, "no SHA-256 digest at end"):
                    sbom_module.parse_locks(root)
            finally:
                sbom_module.LOCK_FILES = original


if __name__ == "__main__":
    unittest.main()
