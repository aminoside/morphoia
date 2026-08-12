# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_engine_e1_public_ir_sbom.py"
MANIFEST = ROOT / "artifacts" / "manifests" / "engine-e1-public-ir.json"
SBOM = ROOT / "artifacts" / "sbom" / "engine-e1-public-ir.cdx.json"
TRACEABILITY = ROOT / "spec" / "evidence" / "e1-public-ir-traceability.json"
TRACEABILITY_SCHEMA = ROOT / "spec" / "evidence" / "e1-public-ir-traceability.schema.json"
MANIFEST_SCHEMA = ROOT / "spec" / "evidence" / "e1-public-ir-artifact-manifest.schema.json"


def load_script(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


public_ir_evidence = load_script("morphoia_e1_public_ir_evidence", GENERATOR)


def read_json(path: Path) -> dict:
    return public_ir_evidence.read_json_bytes(path.read_bytes(), str(path))


def copy_evidence_profile(destination: Path) -> None:
    paths = (
        set(public_ir_evidence.ARTIFACT_SPECS)
        | {public_ir_evidence.MANIFEST_PATH, public_ir_evidence.OUTPUT_PATH}
        | set(public_ir_evidence.LOCK_FILES)
        | set(public_ir_evidence.LICENSE_FILES)
    )
    for relative in sorted(paths):
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class PublicIrEvidenceTests(unittest.TestCase):
    def test_wheel_build_backend_is_exactly_hash_locked(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            project["build-system"]["requires"],
            ["setuptools==83.0.0", "wheel==0.47.0"],
        )
        engine_lock = ROOT / "requirements" / "engine-ci.lock"
        self.assertEqual(
            hashlib.sha256(engine_lock.read_bytes()).hexdigest(),
            "ee1e00b79e51678243beb7dedefb043fa675ed9c4d8c458b2fe576aa7082ade5",
        )
        lock = (ROOT / "requirements" / "wheel-build-e1.lock").read_text(
            encoding="utf-8"
        )
        self.assertIn("packaging==26.3", lock)
        self.assertIn(
            "sha256:d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c",
            lock,
        )
        self.assertIn("setuptools==83.0.0", lock)
        self.assertIn(
            "sha256:29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3",
            lock,
        )
        self.assertIn("wheel==0.47.0", lock)
        self.assertIn(
            "sha256:212281cab4dff978f6cedd499cd893e1f620791ca6ff7107cf270781e587eced",
            lock,
        )

    def test_manifest_and_traceability_match_published_schemas(self) -> None:
        for instance_path, schema_path in (
            (MANIFEST, MANIFEST_SCHEMA),
            (TRACEABILITY, TRACEABILITY_SCHEMA),
        ):
            with self.subTest(instance=instance_path.name):
                schema = read_json(schema_path)
                instance = read_json(instance_path)
                Draft202012Validator.check_schema(schema)
                errors = sorted(
                    Draft202012Validator(
                        schema,
                        format_checker=FormatChecker(),
                    ).iter_errors(instance),
                    key=lambda error: list(error.path),
                )
                self.assertEqual(errors, [])

    def test_committed_outputs_are_deterministic_and_cli_verified(self) -> None:
        manifest_bytes, sbom_bytes = public_ir_evidence.build_outputs(ROOT)
        self.assertEqual(manifest_bytes, MANIFEST.read_bytes())
        self.assertEqual(sbom_bytes, SBOM.read_bytes())
        public_ir_evidence.check_outputs(ROOT, manifest_bytes, sbom_bytes)
        completed = subprocess.run(
            [sys.executable, str(GENERATOR), "--root", str(ROOT), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_manifest_is_the_exact_allowlist_and_self_hash_is_exact(self) -> None:
        manifest = read_json(MANIFEST)
        public_ir_evidence.validate_manifest(ROOT, manifest, verify_self=True)
        expected_paths = set(public_ir_evidence.ARTIFACT_SPECS) | {public_ir_evidence.OUTPUT_PATH}
        self.assertEqual(
            {artifact["path"] for artifact in manifest["artifacts"]},
            expected_paths,
        )
        self_entry = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["id"] == public_ir_evidence.SELF_ARTIFACT_ID
        )
        sbom_bytes = SBOM.read_bytes()
        self.assertEqual(self_entry["size_bytes"], len(sbom_bytes))
        self.assertEqual(self_entry["sha256"], hashlib.sha256(sbom_bytes).hexdigest())

    def test_fixture_tree_is_exactly_79_cc_by_files_with_13_invalid_cases(self) -> None:
        public_ir_evidence.verify_fixture_allowlist(ROOT)
        self.assertEqual(len(public_ir_evidence.EXPECTED_FIXTURE_PATHS), 79)
        invalid_index = read_json(
            ROOT / "tests" / "fixtures" / "engine-ir" / "0.1.0" / "invalid" / "index.json"
        )
        self.assertEqual(len(invalid_index["entries"]), 13)
        aggregate = hashlib.sha256()
        manifest_artifacts = {
            artifact["path"]: artifact for artifact in read_json(MANIFEST)["artifacts"]
        }
        sbom_components = {
            component["name"]: component
            for component in read_json(SBOM)["components"]
            if component["type"] == "file"
        }
        for relative in sorted(public_ir_evidence.EXPECTED_FIXTURE_PATHS):
            with self.subTest(relative=relative):
                content = public_ir_evidence.read_repository_file(ROOT, relative)
                fixture_relative = relative.removeprefix(
                    "tests/fixtures/engine-ir/0.1.0/"
                )
                aggregate.update(fixture_relative.encode("utf-8"))
                aggregate.update(b"\0")
                aggregate.update(hashlib.sha256(content).hexdigest().encode("ascii"))
                aggregate.update(b"\n")
                self.assertEqual(
                    public_ir_evidence.ARTIFACT_SPECS[relative].license_expression,
                    "CC-BY-4.0",
                )
                self.assertEqual(
                    manifest_artifacts[relative]["license_expression"], "CC-BY-4.0"
                )
                self.assertEqual(
                    sbom_components[relative]["licenses"],
                    [{"expression": "CC-BY-4.0"}],
                )
        self.assertEqual(
            aggregate.hexdigest(),
            "9647bf7be7c40dd39ea533b0677fc09d42eabcdee59b8b5adc5cbdc23f1e25af",
        )

    def test_fixture_allowlist_rejects_a_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-fixture-") as directory:
            copy_root = Path(directory) / "copy"
            fixture_source = ROOT / "tests" / "fixtures" / "engine-ir" / "0.1.0"
            fixture_target = copy_root / "tests" / "fixtures" / "engine-ir" / "0.1.0"
            fixture_target.parent.mkdir(parents=True)
            shutil.copytree(fixture_source, fixture_target)
            alias = fixture_target / "unexpected-alias.json"
            alias.symlink_to(fixture_target / "index.json")
            with self.assertRaises(ValueError):
                public_ir_evidence.verify_fixture_allowlist(copy_root.resolve())

    def test_frozen_e1_evidence_has_exact_pinned_digests(self) -> None:
        self.assertEqual(
            set(public_ir_evidence.FROZEN_E1_SPECS),
            set(public_ir_evidence.FROZEN_E1_DIGESTS),
        )
        for relative, expected in public_ir_evidence.FROZEN_E1_DIGESTS.items():
            with self.subTest(relative=relative):
                content = public_ir_evidence.read_repository_file(ROOT, relative)
                self.assertEqual(hashlib.sha256(content).hexdigest(), expected)
        global_tracking = public_ir_evidence.read_repository_file(
            ROOT, "spec/requirements/requirements-tracking.yaml"
        )
        self.assertEqual(
            hashlib.sha256(global_tracking).hexdigest(),
            public_ir_evidence.FROZEN_REQUIREMENTS_TRACKING_DIGEST,
        )
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-tracking-") as directory:
            copy_root = Path(directory) / "copy"
            copy_root.mkdir()
            copy_evidence_profile(copy_root)
            tracking = copy_root / "spec/requirements/requirements-tracking.yaml"
            tracking.write_bytes(tracking.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "global requirements tracking"):
                public_ir_evidence.build_artifact_entries(copy_root.resolve())

    def test_sbom_truthfully_limits_execution_and_security_claims(self) -> None:
        sbom = read_json(SBOM)
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertNotIn("vulnerabilities", sbom)
        properties = {
            item["name"]: item["value"] for item in sbom["metadata"]["component"]["properties"]
        }
        self.assertEqual(properties["morphoia:profile"], public_ir_evidence.PROFILE)
        self.assertEqual(properties["morphoia:mvx-status"], "NOT_RUN")
        self.assertEqual(properties["morphoia:optional-backends-status"], "NOT_RUN")
        self.assertEqual(properties["morphoia:vulnerability-analysis-status"], "NOT_RUN")
        packages = [
            component
            for component in sbom["components"]
            if component["bom-ref"].startswith("pkg:pypi/")
        ]
        self.assertTrue(packages)
        self.assertEqual({component["scope"] for component in packages}, {"excluded"})

    def test_sbom_rejects_an_artifact_snapshot_drift(self) -> None:
        entries = public_ir_evidence.build_artifact_entries(ROOT)
        mutated = copy.deepcopy(entries)
        mutated[0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "changed while building SBOM"):
            public_ir_evidence.build_bom(ROOT, mutated)

    def test_traceability_exact_mapping_rejects_permutation_and_false_pass(self) -> None:
        base = read_json(TRACEABILITY)
        public_ir_evidence.validate_traceability(ROOT, base)
        mutations = {
            "entry order": lambda value: value["entries"].reverse(),
            "claim": lambda value: value["entries"][0].__setitem__(
                "claim", "plausible but unapproved claim"
            ),
            "test mapping": lambda value: value["entries"][0]["test_ids"].append(
                "test_context_manager_closes_deterministically"
            ),
            "evidence mapping": lambda value: value["entries"][0]["evidence"].append(
                "docs/engine/IR_MANIFEST_0_1.md"
            ),
            "status": lambda value: value["entries"][0].__setitem__(
                "status", "PASS" if value["entries"][0]["status"] != "PASS" else "NOT_RUN"
            ),
            "false pass": lambda value: value["entries"][2].__setitem__("status", "PASS"),
            "undefined test": lambda value: value["entries"][0]["test_ids"].append(
                "test_undefined_public_ir_claim"
            ),
            "outside evidence": lambda value: value["entries"][0]["evidence"].append("README.md"),
            "blocking scope": lambda value: value["entries"][0].__setitem__(
                "blocking_scope", "unapproved"
            ),
            "overlong reason": lambda value: value["entries"][0].__setitem__("reason", "x" * 4097),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(base)
                mutation(value)
                with self.assertRaises((TypeError, ValueError)):
                    public_ir_evidence.validate_traceability(ROOT, value)

    def test_traceability_status_boundary_is_exact_and_conservative(self) -> None:
        traceability = read_json(TRACEABILITY)
        self.assertEqual(
            tuple(
                command["id"]
                for command in traceability["execution_environment"]["commands"]
            ),
            public_ir_evidence.EXECUTION_COMMAND_IDS,
        )
        integration = next(
            command
            for command in traceability["execution_environment"]["commands"]
            if command["id"] == "public-ir-integration-postmerge"
        )
        self.assertEqual(
            integration,
            {
                "id": "public-ir-integration-postmerge",
                "command": public_ir_evidence.INTEGRATION_COMMAND,
                "status": "PASS",
                "result": public_ir_evidence.INTEGRATION_RESULT,
            },
        )
        final_head = next(
            command
            for command in traceability["execution_environment"]["commands"]
            if command["id"] == "final-evidence-head-hosted"
        )
        self.assertEqual(
            final_head,
            {
                "id": "final-evidence-head-hosted",
                "command": public_ir_evidence.FINAL_EVIDENCE_HEAD_COMMAND,
                "status": "PASS",
                "result": public_ir_evidence.FINAL_EVIDENCE_HEAD_RESULT,
            },
        )
        for field in ("command", "result", "status"):
            with self.subTest(final_head_field=field):
                mutation = copy.deepcopy(traceability)
                mutated = next(
                    command
                    for command in mutation["execution_environment"]["commands"]
                    if command["id"] == "final-evidence-head-hosted"
                )
                mutated[field] = "NOT_RUN" if field == "status" else "mutated"
                with self.assertRaisesRegex(ValueError, "final evidence-head"):
                    public_ir_evidence.validate_traceability(ROOT, mutation)
        for field in ("command", "result", "status"):
            with self.subTest(field=field):
                mutation = copy.deepcopy(traceability)
                mutated = next(
                    command
                    for command in mutation["execution_environment"]["commands"]
                    if command["id"] == "public-ir-integration-postmerge"
                )
                mutated[field] = "NOT_RUN" if field == "status" else "mutated"
                with self.assertRaisesRegex(ValueError, "integration and post-merge"):
                    public_ir_evidence.validate_traceability(ROOT, mutation)
        adr = (ROOT / "spec/adr/ADR-020-public-engine-ir-v0.1.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("- Status: Accepted\n", adr)
        self.assertIn("9c845f9ea4586a65f25985a4d1f92ebdf407a2f4", adr)
        statuses = {
            entry["requirement_id"]: entry["status"] for entry in traceability["entries"]
        }
        self.assertEqual(list(statuses), list(public_ir_evidence.TRACEABILITY_ORDER))
        self.assertEqual(list(statuses.values()).count("PASS"), 33)
        self.assertEqual(list(statuses.values()).count("NOT_RUN"), 16)
        conservative_not_run = {
            "MOR-IR-003",
            "MOR-IR-005",
            "MOR-IR-006",
            "MOR-IR-011",
            "MOR-API-006",
            "MOR-API-011",
            "MOR-API-012",
            "MOR-API-014",
            "MOR-DEV-010",
            "MOR-DEV-011",
            "MOR-DEV-012",
            "MOR-DEV-014",
            "MOR-CAS-006",
            "MOR-CAS-010",
            "MOR-CAS-012",
            "MOR-QA-013",
        }
        self.assertEqual(
            {requirement for requirement, status in statuses.items() if status == "NOT_RUN"},
            conservative_not_run,
        )

    def test_manifest_rejects_path_hash_license_status_and_graph_mutations(self) -> None:
        base = read_json(MANIFEST)
        mutations = {
            "path": lambda value: value["artifacts"][0].__setitem__("path", "README.md"),
            "order": lambda value: value["artifacts"].reverse(),
            "digest": lambda value: value["artifacts"][0].__setitem__("sha256", "0" * 64),
            "license": lambda value: value["artifacts"][0].__setitem__("license_expression", "MIT"),
            "status": lambda value: value["artifacts"][0].__setitem__(
                "verification_status", "NOT_RUN"
            ),
            "vulnerability": lambda value: value["artifacts"][0].__setitem__(
                "vulnerability_analysis_status", "PASS"
            ),
            "source": lambda value: value["artifacts"][0].__setitem__(
                "source_artifact_id", "missing"
            ),
            "provenance": lambda value: value["artifacts"][0].__setitem__(
                "provenance", "unapproved provenance"
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(base)
                mutation(value)
                with self.assertRaises((TypeError, ValueError)):
                    public_ir_evidence.validate_manifest(ROOT, value, verify_self=True)

    def test_strict_json_rejects_duplicate_nan_float_and_surrogate(self) -> None:
        invalid = {
            "duplicate": b'{"value":1,"value":2}\n',
            "nan": b'{"value":NaN}\n',
            "float": b'{"value":1.5}\n',
            "surrogate": b'{"value":"\\ud800"}\n',
        }
        for label, content in invalid.items():
            with self.subTest(label=label), self.assertRaises((TypeError, ValueError)):
                public_ir_evidence.read_json_bytes(content, label)

    def test_confined_input_rejects_traversal_symlink_and_hardlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-input-") as directory:
            workspace = Path(directory)
            root = (workspace / "root").resolve()
            root.mkdir()
            (root / "regular").write_text("bytes\n", encoding="utf-8")
            (root / "link").symlink_to(root / "regular")
            os.link(root / "regular", root / "alias")
            for relative in ("../regular", "/regular", "link", "regular", "alias"):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    public_ir_evidence.read_repository_file(root, relative)

    def test_atomic_write_handles_absent_existing_and_temp_collision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-output-") as directory:
            root = Path(directory).resolve()
            output = root / "out"
            output.mkdir()
            public_ir_evidence.write_atomic(root, "out/result.json", b"first\n")
            self.assertEqual((output / "result.json").read_bytes(), b"first\n")
            public_ir_evidence.write_atomic(root, "out/result.json", b"second\n")
            self.assertEqual((output / "result.json").read_bytes(), b"second\n")

            fixed_uuid = mock.Mock(hex="0" * 32)
            collision = output / f".collision.json.{fixed_uuid.hex}.tmp"
            collision.write_bytes(b"not ours")
            with (
                mock.patch.object(public_ir_evidence.uuid, "uuid4", return_value=fixed_uuid),
                self.assertRaises(ValueError),
            ):
                public_ir_evidence.write_atomic(root, "out/collision.json", b"must not publish\n")
            self.assertEqual(collision.read_bytes(), b"not ours")
            self.assertFalse((output / "collision.json").exists())

    def test_atomic_write_rejects_absent_target_creation_race(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-race-") as directory:
            root = Path(directory).resolve()
            (root / "out").mkdir()

            def create_target(
                descriptor: int, basename: str, identity: tuple[int, ...] | None
            ) -> None:
                self.assertIsNone(identity)
                target = os.open(
                    basename,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=descriptor,
                )
                os.write(target, b"concurrent\n")
                os.close(target)

            with self.assertRaises(ValueError):
                public_ir_evidence.write_atomic(
                    root,
                    "out/result.json",
                    b"generated\n",
                    before_publish=create_target,
                )
            self.assertEqual((root / "out" / "result.json").read_bytes(), b"concurrent\n")
            self.assertEqual(list((root / "out").glob(".*.tmp")), [])

    def test_atomic_write_rejects_existing_target_inode_swap_and_restores_name(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-swap-") as directory:
            root = Path(directory).resolve()
            output = root / "out"
            output.mkdir()
            target = output / "result.json"
            target.write_bytes(b"original\n")

            def swap_target(
                descriptor: int, basename: str, identity: tuple[int, ...] | None
            ) -> None:
                self.assertIsNotNone(identity)
                os.rename(
                    basename,
                    "preserved-original",
                    src_dir_fd=descriptor,
                    dst_dir_fd=descriptor,
                )
                replacement = os.open(
                    basename,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=descriptor,
                )
                os.write(replacement, b"concurrent\n")
                os.close(replacement)

            with self.assertRaises(ValueError):
                public_ir_evidence.write_atomic(
                    root,
                    "out/result.json",
                    b"generated\n",
                    before_publish=swap_target,
                )
            self.assertEqual(target.read_bytes(), b"concurrent\n")
            self.assertEqual((output / "preserved-original").read_bytes(), b"original\n")
            self.assertEqual(list(output.glob(".*.tmp")), [])

    def test_atomic_write_rejects_existing_target_in_place_mutation_and_restores_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-mutate-") as directory:
            root = Path(directory).resolve()
            output = root / "out"
            output.mkdir()
            target = output / "result.json"
            target.write_bytes(b"original\n")

            def mutate_target(
                descriptor: int, basename: str, identity: tuple[int, ...] | None
            ) -> None:
                self.assertIsNotNone(identity)
                file_descriptor = os.open(
                    basename,
                    os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                os.write(file_descriptor, b"concurrent mutation\n")
                os.close(file_descriptor)

            with self.assertRaises(ValueError):
                public_ir_evidence.write_atomic(
                    root,
                    "out/result.json",
                    b"generated\n",
                    before_publish=mutate_target,
                )
            self.assertEqual(target.read_bytes(), b"concurrent mutation\n")
            self.assertEqual(list(output.glob(".*.tmp")), [])

    def test_atomic_exchange_restores_a_mutation_after_final_revalidation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-exchange-") as directory:
            root = Path(directory).resolve()
            output = root / "out"
            output.mkdir()
            target = output / "result.json"
            target.write_bytes(b"original\n")

            def mutate_after_revalidation(
                descriptor: int, basename: str, identity: tuple[int, ...] | None
            ) -> None:
                self.assertIsNotNone(identity)
                file_descriptor = os.open(
                    basename,
                    os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                os.write(file_descriptor, b"late concurrent mutation\n")
                os.close(file_descriptor)

            with self.assertRaises(ValueError):
                public_ir_evidence.write_atomic(
                    root,
                    "out/result.json",
                    b"generated\n",
                    before_exchange=mutate_after_revalidation,
                )
            self.assertEqual(target.read_bytes(), b"late concurrent mutation\n")
            self.assertEqual(list(output.glob(".*.tmp")), [])

    def test_atomic_write_rejects_parent_target_symlink_and_hardlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-alias-") as directory:
            workspace = Path(directory).resolve()
            root = workspace / "root"
            outside = workspace / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "linked-parent").symlink_to(outside)
            with self.assertRaises(ValueError):
                public_ir_evidence.write_atomic(
                    root.resolve(), "linked-parent/result.json", b"escape\n"
                )
            self.assertFalse((outside / "result.json").exists())

            output = root / "out"
            output.mkdir()
            outside_file = outside / "source"
            outside_file.write_bytes(b"preserve\n")
            os.link(outside_file, output / "hardlink")
            with self.assertRaises(ValueError):
                public_ir_evidence.write_atomic(root.resolve(), "out/hardlink", b"replace\n")
            self.assertEqual(outside_file.read_bytes(), b"preserve\n")

            (output / "symlink").symlink_to(outside_file)
            with self.assertRaises(ValueError):
                public_ir_evidence.write_atomic(root.resolve(), "out/symlink", b"replace\n")
            self.assertEqual(outside_file.read_bytes(), b"preserve\n")

    def test_atomic_write_cleans_temp_when_publication_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-cleanup-") as directory:
            root = Path(directory).resolve()
            output = root / "out"
            output.mkdir()
            with (
                mock.patch.object(
                    public_ir_evidence,
                    "_renameat2",
                    side_effect=OSError("injected publication failure"),
                ),
                self.assertRaises(OSError),
            ):
                public_ir_evidence.write_atomic(root, "out/result.json", b"generated\n")
            self.assertFalse((output / "result.json").exists())
            self.assertEqual(list(output.glob(".*.tmp")), [])

    def test_mutated_input_copy_is_not_accepted_as_the_committed_profile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-public-ir-copy-") as directory:
            copy_root = Path(directory) / "copy"
            copy_root.mkdir()
            copy_evidence_profile(copy_root)
            relative = next(iter(public_ir_evidence.ARTIFACT_SPECS))
            path = copy_root / relative
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                public_ir_evidence.check_outputs(
                    copy_root.resolve(), MANIFEST.read_bytes(), SBOM.read_bytes()
                )


if __name__ == "__main__":
    unittest.main()
