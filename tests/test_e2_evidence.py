# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_engine_e2_sbom.py"
MANIFEST = ROOT / "artifacts" / "manifests" / "engine-e2-salome-protocol.json"
SBOM = ROOT / "artifacts" / "sbom" / "engine-e2-salome-protocol.cdx.json"
MANIFEST_SCHEMA = (
    ROOT / "spec" / "evidence" / "e2-salome-protocol-artifact-manifest.schema.json"
)
TRACEABILITY = ROOT / "spec" / "evidence" / "e2-salome-protocol-traceability.json"
TRACEABILITY_SCHEMA = (
    ROOT / "spec" / "evidence" / "e2-salome-protocol-traceability.schema.json"
)
E0_MANIFEST = ROOT / "artifacts" / "manifest.json"
E0_SBOM = ROOT / "artifacts" / "sbom" / "engine-e0-source-native.cdx.json"
E0_MANIFEST_SHA256 = "df017341a5bdbb43dacd8a39bcb0cc5037c2fc885e60cb568392f7c93f8a312d"
E0_SBOM_SHA256 = "30db23e7e3fc1edacce0627386152d0246f909adf0ffbefc7b441926b583414b"


def load_script(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


e2_sbom = load_script("morphoia_e2_sbom_generator", GENERATOR)


def read_json(path: Path) -> dict:
    return e2_sbom.read_json(path)


class E2EvidenceTests(unittest.TestCase):
    def test_closed_e0_manifest_and_sbom_remain_byte_exact(self) -> None:
        self.assertEqual(e2_sbom.sha256_file(E0_MANIFEST), E0_MANIFEST_SHA256)
        self.assertEqual(e2_sbom.sha256_file(E0_SBOM), E0_SBOM_SHA256)

    def test_e2_manifest_and_traceability_match_their_schemas(self) -> None:
        for instance_path, schema_path in (
            (MANIFEST, MANIFEST_SCHEMA),
            (TRACEABILITY, TRACEABILITY_SCHEMA),
        ):
            with self.subTest(instance=instance_path.name):
                schema = read_json(schema_path)
                instance = read_json(instance_path)
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(
                    schema,
                    format_checker=FormatChecker(),
                ).validate(instance)

    def test_e2_manifest_is_exactly_the_bounded_allowlist(self) -> None:
        manifest = read_json(MANIFEST)
        selected = e2_sbom.validate_manifest(ROOT, manifest, verify_self=True)
        paths = {item["path"] for item in manifest["artifacts"]}
        self.assertEqual(paths, set(e2_sbom.ARTIFACT_LICENSES))
        self.assertEqual(paths, set(e2_sbom.ARTIFACT_MEDIA_TYPES))
        self.assertEqual(paths, set(e2_sbom.ARTIFACT_IDS))
        self.assertEqual(paths, set(e2_sbom.ARTIFACT_KINDS))
        self.assertEqual(
            {item["path"] for item in selected},
            set(e2_sbom.ARTIFACT_LICENSES) - {e2_sbom.OUTPUT_PATH},
        )

    def test_e2_traceability_is_fail_closed_and_keeps_real_salome_not_run(self) -> None:
        base = read_json(TRACEABILITY)
        e2_sbom.validate_traceability(ROOT, base)
        mutations = {
            "wrong source commit": lambda value: value.__setitem__(
                "source_commit", "0" * 40
            ),
            "real runtime claim": lambda value: value["entries"][0].__setitem__(
                "real_salome_status", "PASS"
            ),
            "duplicate requirement": lambda value: value["entries"][1].__setitem__(
                "requirement_id", value["entries"][0]["requirement_id"]
            ),
            "evidence outside allowlist": lambda value: value["entries"][0][
                "evidence"
            ].append("README.md"),
            "undefined test": lambda value: value["entries"][0].__setitem__(
                "test_ids", ["test_this_does_not_exist"]
            ),
            "swapped test mapping": lambda value: value["entries"][0].__setitem__(
                "test_ids", list(value["entries"][1]["test_ids"])
            ),
            "swapped evidence mapping": lambda value: value["entries"][0].__setitem__(
                "evidence", list(value["entries"][1]["evidence"])
            ),
            "overlong reason": lambda value: value["entries"][0].__setitem__(
                "reason", "x" * 2049
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(base)
                mutation(value)
                with self.assertRaises((TypeError, ValueError)):
                    e2_sbom.validate_traceability(ROOT, value)

    def test_e2_sbom_is_deterministic_and_self_hash_exact(self) -> None:
        generated = e2_sbom.deterministic_json(e2_sbom.build_bom(ROOT, MANIFEST))
        committed = SBOM.read_text(encoding="utf-8")
        self.assertEqual(generated, committed)
        self_entry = next(
            item
            for item in read_json(MANIFEST)["artifacts"]
            if item["id"] == e2_sbom.SELF_ARTIFACT_ID
        )
        self.assertEqual(
            hashlib.sha256(committed.encode("utf-8")).hexdigest(),
            self_entry["sha256"],
        )
        self.assertEqual(len(committed.encode("utf-8")), self_entry["size_bytes"])
        completed = subprocess.run(
            [sys.executable, str(GENERATOR), "--root", str(ROOT), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_e2_sbom_truthfully_limits_scope_and_security_claims(self) -> None:
        sbom = read_json(SBOM)
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertNotIn("vulnerabilities", sbom)
        properties = {
            item["name"]: item["value"]
            for item in sbom["metadata"]["component"]["properties"]
        }
        self.assertEqual(properties["morphoia:profile"], e2_sbom.PROFILE)
        self.assertEqual(
            properties["morphoia:implementation-base-commit"],
            e2_sbom.SOURCE_COMMIT,
        )
        self.assertNotIn("morphoia:source-commit", properties)
        self.assertEqual(properties["morphoia:execution-scope"], "contract-only")
        self.assertEqual(properties["morphoia:salome-runtime-status"], "NOT_RUN")
        self.assertEqual(properties["morphoia:vulnerability-analysis-status"], "NOT_RUN")
        packages = [
            item for item in sbom["components"] if item["bom-ref"].startswith("pkg:pypi/")
        ]
        self.assertTrue(packages)
        self.assertEqual({item["scope"] for item in packages}, {"excluded"})

    def test_manifest_rejects_path_hash_license_and_graph_mutations(self) -> None:
        base = read_json(MANIFEST)
        mutations = {
            "unlisted path": lambda value: value["artifacts"][0].__setitem__(
                "path", "README.md"
            ),
            "false digest": lambda value: value["artifacts"][0].__setitem__(
                "sha256", "0" * 64
            ),
            "wrong license": lambda value: value["artifacts"][0].__setitem__(
                "license_expression", "MIT"
            ),
            "dangling source": lambda value: value["artifacts"][0].__setitem__(
                "source_artifact_id", "missing"
            ),
            "arbitrary existing source": lambda value: value["artifacts"][1].__setitem__(
                "source_artifact_id", value["artifacts"][2]["id"]
            ),
            "explicit null source": lambda value: value["artifacts"][0].__setitem__(
                "source_artifact_id", None
            ),
            "false vulnerability pass": lambda value: value["artifacts"][0].__setitem__(
                "vulnerability_analysis_status", "PASS"
            ),
            "changed provenance": lambda value: value["artifacts"][0].__setitem__(
                "provenance", "plausible but unapproved provenance"
            ),
            "changed note": lambda value: value["artifacts"][-1].__setitem__(
                "note", "plausible but unapproved note"
            ),
            "explicit null note": lambda value: value["artifacts"][0].__setitem__(
                "note", None
            ),
            "published source digest drift": lambda value: value["artifacts"][1].__setitem__(
                "sha256", value["artifacts"][2]["sha256"]
            ),
            "unknown field": lambda value: value.__setitem__("unexpected", True),
            "unsafe integer": lambda value: value["artifacts"][0].__setitem__(
                "size_bytes", e2_sbom.MAX_SAFE_INTEGER + 1
            ),
            "invalid calendar date": lambda value: value.__setitem__(
                "generated_at", "2026-02-30"
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(base)
                mutation(value)
                with self.assertRaises(ValueError):
                    e2_sbom.validate_manifest(ROOT, value, verify_self=True)

    def test_manifest_rejects_duplicate_keys_and_symlink_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e2-evidence-") as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"profile":"one","profile":"two"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                e2_sbom.read_json(duplicate)

            escaped_surrogate = root / "escaped-surrogate.json"
            escaped_surrogate.write_text('{"value":"\\ud800"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                e2_sbom.read_json(escaped_surrogate)

            unsafe_integer = root / "unsafe-integer.json"
            unsafe_integer.write_text(
                '{"value":9007199254740992}\n', encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                e2_sbom.read_json(unsafe_integer)

            outside = root / "outside"
            outside.write_text("bytes\n", encoding="utf-8")
            link = root / "link"
            link.symlink_to(outside)
            with self.assertRaises(ValueError):
                e2_sbom.safe_root_file(root, "link")

    def test_strict_schema_reader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e2-schema-") as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema",'
                '"type":"object","type":"array"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                read_json(schema)

    def test_atomic_output_rejects_parent_symlink_escape_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e2-output-") as directory:
            workspace = Path(directory)
            root = workspace / "root"
            outside = workspace / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "sbom").symlink_to(outside)
            with self.assertRaises(ValueError):
                e2_sbom.write_atomic(root.resolve(), e2_sbom.OUTPUT_PATH, "escaped\n")
            self.assertFalse((outside / Path(e2_sbom.OUTPUT_PATH).name).exists())

            (root / "artifacts" / "sbom").unlink()
            (root / "artifacts" / "sbom").mkdir()
            input_file = root / "input.json"
            input_file.write_text("input\n", encoding="utf-8")
            output = root / e2_sbom.OUTPUT_PATH
            os.link(input_file, output)
            with self.assertRaises(ValueError):
                e2_sbom.write_atomic(root.resolve(), e2_sbom.OUTPUT_PATH, "collision\n")
            self.assertEqual(input_file.read_text(encoding="utf-8"), "input\n")

    def test_build_rejects_manifest_path_alias_and_parent_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e2-manifest-") as directory:
            workspace = Path(directory)
            root = workspace / "root"
            outside = workspace / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "manifests").symlink_to(outside)
            manifest = outside / Path(e2_sbom.MANIFEST_PATH).name
            manifest.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                e2_sbom.build_bom(root.resolve(), manifest)

        aliased_manifest = MANIFEST.parent / ".." / "manifests" / MANIFEST.name
        with self.assertRaisesRegex(ValueError, "exact in-root profile path"):
            e2_sbom.build_bom(ROOT, aliased_manifest)

    def test_lock_parser_rejects_each_unhashed_declaration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-e2-lock-") as directory:
            root = Path(directory)
            lock = root / e2_sbom.LOCK_FILES[0]
            lock.parent.mkdir(parents=True)
            lock.write_text(
                "first==1.0 \\\n"
                "second==2.0 \\\n"
                "    --hash=sha256:" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "no digest before"):
                e2_sbom.parse_locks(root)


if __name__ == "__main__":
    unittest.main()
