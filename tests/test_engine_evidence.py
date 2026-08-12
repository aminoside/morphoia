# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
from contextlib import redirect_stderr
import fnmatch
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from types import ModuleType
from typing import Any
import unittest

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs" / "engine" / "checkpoint.json"
MANIFEST = ROOT / "artifacts" / "manifest.json"
SBOM = ROOT / "artifacts" / "sbom" / "engine-e0-source-native.cdx.json"
E1_MANIFEST = ROOT / "artifacts" / "e1" / "manifest.json"
E1_SBOM = ROOT / "artifacts" / "sbom" / "engine-e1-native-core.cdx.json"
CHECKPOINT_SCRIPT = ROOT / "scripts" / "validate_engine_checkpoint.py"
SBOM_SCRIPT = ROOT / "scripts" / "generate_engine_sbom.py"
E1_SBOM_SCRIPT = ROOT / "scripts" / "generate_engine_e1_sbom.py"
E0_EVIDENCE_SCRIPT = ROOT / "scripts" / "validate_engine_e0_evidence.py"
E1_EVIDENCE_SCRIPT = ROOT / "scripts" / "validate_engine_e1_native_evidence.py"


def load_script(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


checkpoint_module = load_script("morphoia_checkpoint_validator", CHECKPOINT_SCRIPT)
sbom_module = load_script("morphoia_sbom_generator", SBOM_SCRIPT)
e1_sbom_module = load_script("morphoia_e1_sbom_generator", E1_SBOM_SCRIPT)
e0_evidence_module = load_script("morphoia_e0_evidence_validator", E0_EVIDENCE_SCRIPT)


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
    def test_frozen_e0_evidence_is_byte_exact_and_self_consistent(self) -> None:
        self.assertEqual(e0_evidence_module.validate(ROOT), [])
        for relative, expected in e0_evidence_module.FROZEN_FILES.items():
            with self.subTest(relative=relative):
                self.assertEqual(
                    e0_evidence_module.sha256_file(ROOT / relative),
                    expected,
                )
        completed = subprocess.run(
            [sys.executable, str(E0_EVIDENCE_SCRIPT), "--root", str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_frozen_e0_validator_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-frozen-e0-") as directory:
            root = Path(directory)
            for relative in e0_evidence_module.FROZEN_FILES:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            self.assertEqual(e0_evidence_module.validate(root), [])
            generator = root / "scripts" / "generate_engine_sbom.py"
            generator.write_bytes(generator.read_bytes() + b"\n")
            self.assertTrue(e0_evidence_module.validate(root))

    def test_e0_artifact_manifest_remains_explicit_and_hash_exact(self) -> None:
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

    def test_e1_manifest_matches_published_json_schema(self) -> None:
        schema = read_json(ROOT / "spec" / "evidence" / "artifact-manifest.schema.json")
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                read_json(E1_MANIFEST)
            ),
            key=lambda error: list(error.path),
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            {item["id"] for item in read_json(E1_MANIFEST)["artifacts"]},
            set(e1_sbom_module.EXPECTED_ARTIFACTS),
        )

    def test_e1_sbom_is_frozen_and_matches_manifest_digest(self) -> None:
        committed = E1_SBOM.read_text(encoding="utf-8")
        manifest = read_json(E1_MANIFEST)
        entry = next(
            item
            for item in manifest["artifacts"]
            if item["id"] == e1_sbom_module.SELF_ARTIFACT_ID
        )
        self.assertEqual(hashlib.sha256(committed.encode("utf-8")).hexdigest(), entry["sha256"])
        self.assertEqual(len(committed.encode("utf-8")), entry["size_bytes"])
        completed = subprocess.run(
            [sys.executable, str(E1_EVIDENCE_SCRIPT), "--root", str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_e0_and_e1_sboms_declare_distinct_honest_scopes(self) -> None:
        e0 = read_json(SBOM)
        e1 = read_json(E1_SBOM)
        for sbom in (e0, e1):
            self.assertEqual(sbom["bomFormat"], "CycloneDX")
            self.assertEqual(sbom["specVersion"], "1.5")
            self.assertNotIn("vulnerabilities", sbom)
            root_component = sbom["metadata"]["component"]
            properties = {
                item["name"]: item["value"] for item in root_component["properties"]
            }
            self.assertEqual(
                properties["morphoia:vulnerability-analysis-status"], "NOT_RUN"
            )
            self.assertEqual(root_component["licenses"], [{"expression": "Apache-2.0 OR MIT"}])
        e0_properties = {
            item["name"]: item["value"]
            for item in e0["metadata"]["component"]["properties"]
        }
        e1_properties = {
            item["name"]: item["value"]
            for item in e1["metadata"]["component"]["properties"]
        }
        self.assertEqual(e0_properties["morphoia:profile"], "e0-source-native")
        self.assertEqual(e1_properties["morphoia:profile"], "e1-native-core")

    def test_locked_packages_are_not_claimed_shipped(self) -> None:
        sbom = read_json(E1_SBOM)
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        components = sbom["components"]
        system = [
            component
            for component in components
            if component["bom-ref"].startswith("urn:morphoia:system-tool:")
        ]
        self.assertEqual(system, [])

        expected_packages = e1_sbom_module.parse_locks(ROOT)
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
        selected = set(e1_sbom_module.collect_source_files(ROOT))
        self.assertIn("tests/native/consumer/CMakeLists.txt", selected)
        self.assertIn("tests/native/consumer/main.c", selected)
        self.assertIn("tests/native/incompatible_consumer/CMakeLists.txt", selected)
        self.assertIn("scripts/generate_engine_e1_sbom.py", selected)
        self.assertIn("scripts/validate_engine_e0_evidence.py", selected)
        self.assertIn("tests/test_engine_evidence.py", selected)

    def test_e1_source_component_licenses_match_reuse_annotations(self) -> None:
        reuse = tomllib.loads((ROOT / "REUSE.toml").read_text(encoding="utf-8"))
        annotations = reuse["annotations"]
        sbom_components = {
            item["name"]: item
            for item in read_json(E1_SBOM)["components"]
            if item["bom-ref"].startswith("urn:morphoia:e1-native-source:")
        }
        for relative in sorted(sbom_components):
            with self.subTest(relative=relative):
                declared = {
                    annotation["SPDX-License-Identifier"]
                    for annotation in annotations
                    if any(
                        fnmatch.fnmatchcase(relative, pattern)
                        for pattern in (
                            annotation["path"]
                            if isinstance(annotation["path"], list)
                            else [annotation["path"]]
                        )
                    )
                }
                self.assertEqual(declared, {e1_sbom_module.source_license_expression(relative)})
                self.assertEqual(
                    sbom_components[relative]["licenses"],
                    [{"expression": next(iter(declared))}],
                )
        self.assertEqual(
            sbom_components["src/morphoia/compiler.py"]["licenses"],
            [{"expression": "MIT"}],
        )

    def test_e1_source_license_map_fails_closed_when_missing_or_conflicting(self) -> None:
        original = e1_sbom_module.SOURCE_LICENSE_RULES
        try:
            e1_sbom_module.SOURCE_LICENSE_RULES = tuple(
                item for item in original if item[0] != "src/morphoia/compiler.py"
            )
            with self.assertRaises(ValueError):
                e1_sbom_module.source_license_expression("src/morphoia/compiler.py")
            e1_sbom_module.SOURCE_LICENSE_RULES = (
                *original,
                ("src/**", "Apache-2.0 OR MIT"),
            )
            with self.assertRaises(ValueError):
                e1_sbom_module.source_license_expression("src/morphoia/compiler.py")
        finally:
            e1_sbom_module.SOURCE_LICENSE_RULES = original

    def test_e1_manifest_rejects_stale_artifact_hash(self) -> None:
        manifest = read_json(E1_MANIFEST)
        manifest["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            e1_sbom_module.validate_manifest_value(ROOT, manifest)

    def test_e1_manifest_static_truth_fields_are_exact(self) -> None:
        base = read_json(E1_MANIFEST)
        mutations = {
            "swapped provenance": lambda value: value["artifacts"][0].__setitem__(
                "provenance", value["artifacts"][1]["provenance"]
            ),
            "invented edge": lambda value: value["artifacts"][0].__setitem__(
                "source_artifact_id", "adr-018-canonical-json-posix-cas"
            ),
            "verification downgrade": lambda value: value["artifacts"][0].__setitem__(
                "verification_status", "NOT_RUN"
            ),
            "false vulnerability pass": lambda value: value["artifacts"][2].__setitem__(
                "vulnerability_analysis_status", "PASS"
            ),
            "removed vulnerability truth": lambda value: value["artifacts"][2].pop(
                "vulnerability_analysis_status"
            ),
            "changed limitation note": lambda value: value["artifacts"][2].__setitem__(
                "note", "No vulnerabilities found"
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                manifest = copy.deepcopy(base)
                mutation(manifest)
                with self.assertRaises(ValueError):
                    e1_sbom_module.validate_manifest_value(ROOT, manifest)

    def test_e1_manifest_exact_allowlist_and_numeric_domain_fail_closed(self) -> None:
        base = read_json(E1_MANIFEST)
        mutations = {
            "unknown manifest field": lambda value: value.__setitem__("unexpected", True),
            "missing manifest field": lambda value: value.pop("project"),
            "unknown artifact field": lambda value: value["artifacts"][0].__setitem__(
                "unexpected", True
            ),
            "missing artifact field": lambda value: value["artifacts"][0].pop("kind"),
            "unsafe size": lambda value: value["artifacts"][0].__setitem__(
                "size_bytes", e1_sbom_module.SAFE_INTEGER_MAX + 1
            ),
            "boolean size": lambda value: value["artifacts"][0].__setitem__(
                "size_bytes", True
            ),
            "invalid status": lambda value: value["artifacts"][0].__setitem__(
                "verification_status", "SKIPPED"
            ),
            "invalid calendar date": lambda value: value.__setitem__(
                "generated_at", "2026-02-31"
            ),
            "lone surrogate": lambda value: value["artifacts"][0].__setitem__(
                "note", "\ud800"
            ),
            "unlisted artifact": lambda value: value["artifacts"].append(
                {
                    **copy.deepcopy(value["artifacts"][0]),
                    "id": "unexpected-artifact",
                    "path": "NOTICE",
                }
            ),
            "duplicate id": lambda value: value["artifacts"][1].__setitem__(
                "id", value["artifacts"][0]["id"]
            ),
            "duplicate path": lambda value: value["artifacts"][1].__setitem__(
                "path", value["artifacts"][0]["path"]
            ),
            "changed order": lambda value: value["artifacts"].reverse(),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                manifest = copy.deepcopy(base)
                mutation(manifest)
                with self.assertRaises(ValueError):
                    parsed = e1_sbom_module.parse_manifest_text(
                        json.dumps(manifest, ensure_ascii=True)
                    )
                    e1_sbom_module.validate_manifest_value(ROOT, parsed)

    def test_e1_manifest_rejects_duplicate_keys_and_non_json_constants(self) -> None:
        values = (
            '{"schema_version":"1.0.0","schema_version":"1.0.0"}',
            '{"schema_version":NaN}',
            '{"schema_version":Infinity}',
        )
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    e1_sbom_module.parse_manifest_text(value)

    def test_e1_manifest_self_hash_is_required_by_cli(self) -> None:
        manifest = read_json(E1_MANIFEST)
        entry = next(
            item
            for item in manifest["artifacts"]
            if item["id"] == e1_sbom_module.SELF_ARTIFACT_ID
        )
        entry["sha256"] = "0" * 64
        original = e1_sbom_module.read_manifest
        e1_sbom_module.read_manifest = lambda root, path: manifest
        try:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = e1_sbom_module.main(["--root", str(ROOT), "--check"])
            self.assertEqual(result, 1)
            self.assertIn("self-artifact hash or size differs", stderr.getvalue())
        finally:
            e1_sbom_module.read_manifest = original

    def test_e1_manifest_requires_exact_path_and_rejects_aliases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-manifest-alias-", dir=ROOT) as directory:
            alias = Path(directory) / "manifest.json"
            os.link(E1_MANIFEST, alias)
            with self.assertRaisesRegex(ValueError, "exactly"):
                e1_sbom_module.read_manifest(ROOT, alias)

        with tempfile.TemporaryDirectory(prefix="morphoia-manifest-root-") as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()
            external = root / "external"
            external.mkdir()
            (external / "manifest.json").write_bytes(E1_MANIFEST.read_bytes())
            (root / "artifacts" / "e1").symlink_to(external, target_is_directory=True)
            expected = root / e1_sbom_module.MANIFEST_RELATIVE
            with self.assertRaises(ValueError):
                e1_sbom_module.read_manifest(root, expected)

    def test_e1_atomic_output_uses_confined_dirfd_and_rejects_input_alias(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-sbom-write-") as directory:
            root = Path(directory)
            output = root / e1_sbom_module.OUTPUT_RELATIVE
            output.parent.mkdir(parents=True)
            e1_sbom_module.write_atomic(
                root, e1_sbom_module.OUTPUT_RELATIVE, b"verified\n", []
            )
            self.assertEqual(
                e1_sbom_module.read_output_exact(
                    root, e1_sbom_module.OUTPUT_RELATIVE, []
                ),
                b"verified\n",
            )
            self.assertEqual(list(output.parent.glob(f".{output.name}.*.tmp")), [])

            source = root / "input.txt"
            source.write_bytes(b"input\n")
            output.unlink()
            os.link(source, output)
            with self.assertRaisesRegex(ValueError, "aliases input"):
                e1_sbom_module.write_atomic(
                    root,
                    e1_sbom_module.OUTPUT_RELATIVE,
                    b"replacement\n",
                    ["input.txt"],
                )
            self.assertEqual(source.read_bytes(), b"input\n")

            output.unlink()
            output.write_bytes(b"previous\n")

            def swap_output_to_input() -> None:
                output.unlink()
                os.link(source, output)

            with self.assertRaisesRegex(ValueError, "unsafe|changed"):
                e1_sbom_module.write_atomic(
                    root,
                    e1_sbom_module.OUTPUT_RELATIVE,
                    b"replacement\n",
                    ["input.txt"],
                    before_replace=swap_output_to_input,
                )
            self.assertEqual(source.read_bytes(), b"input\n")
            self.assertEqual(list(output.parent.glob(f".{output.name}.*.tmp")), [])

    def test_e1_atomic_output_rejects_parent_symlink_and_alternate_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-sbom-parent-") as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()
            external = root / "external"
            external.mkdir()
            (root / "artifacts" / "sbom").symlink_to(external, target_is_directory=True)
            with self.assertRaises(OSError):
                e1_sbom_module.write_atomic(
                    root, e1_sbom_module.OUTPUT_RELATIVE, b"blocked\n", []
                )
            self.assertEqual(list(external.iterdir()), [])
        with self.assertRaisesRegex(ValueError, "exactly"):
            e1_sbom_module.exact_repository_argument(
                ROOT,
                ROOT / "artifacts" / "sbom" / "alternate.cdx.json",
                e1_sbom_module.OUTPUT_RELATIVE,
            )

    def test_e1_paths_reject_final_and_intermediate_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-sbom-path-", dir=ROOT) as directory:
            base = Path(directory)
            final_link = base / "final-link"
            final_link.symlink_to(ROOT / "NOTICE")
            with self.assertRaises(ValueError):
                e1_sbom_module.safe_root_file(ROOT, final_link.relative_to(ROOT).as_posix())

            intermediate = base / "intermediate"
            intermediate.symlink_to(ROOT / "docs", target_is_directory=True)
            relative = (intermediate / "engine" / "STATUS.md").relative_to(ROOT).as_posix()
            with self.assertRaises(ValueError):
                e1_sbom_module.safe_root_file(ROOT, relative)

    def test_lock_parser_rejects_package_without_its_own_hash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-lock-parser-") as directory:
            root = Path(directory)
            lock = root / e1_sbom_module.LOCK_FILES[0]
            lock.parent.mkdir(parents=True)
            lock.write_text(
                "first==1.0 \\\n"
                "second==2.0 \\\n"
                "    --hash=sha256:" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                e1_sbom_module.parse_locks(root)

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
            original = e1_sbom_module.LOCK_FILES
            e1_sbom_module.LOCK_FILES = (
                "requirements/first.lock",
                "requirements/second.lock",
            )
            try:
                with self.assertRaisesRegex(ValueError, "no SHA-256 digest at end"):
                    e1_sbom_module.parse_locks(root)
            finally:
                e1_sbom_module.LOCK_FILES = original


if __name__ == "__main__":
    unittest.main()
