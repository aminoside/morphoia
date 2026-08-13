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
from pathlib import Path
from types import ModuleType
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_engine_e1_public_ir_frozen.py"
FREEZE = ROOT / "spec" / "evidence" / "e1-public-ir-freeze.json"
SCHEMA = ROOT / "spec" / "evidence" / "e1-public-ir-freeze.schema.json"


def load_script(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


frozen = load_script("morphoia_e1_public_ir_frozen", VALIDATOR)


class FrozenPublicIrEvidenceTests(unittest.TestCase):
    def test_declaration_matches_published_schema(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        declaration = json.loads(FREEZE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).iter_errors(declaration),
            key=lambda error: list(error.path),
        )
        self.assertEqual(errors, [])

    def test_declaration_and_schema_are_byte_pinned(self) -> None:
        declaration = frozen.load_declaration(ROOT)
        self.assertEqual(declaration["status"], "FROZEN")
        self.assertEqual(
            hashlib.sha256(FREEZE.read_bytes()).hexdigest(),
            frozen.FREEZE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(SCHEMA.read_bytes()).hexdigest(),
            frozen.FREEZE_SCHEMA_SHA256,
        )

    def test_local_git_snapshot_metadata_is_exact(self) -> None:
        result = frozen.validate(ROOT, replay=False)
        self.assertEqual(
            result,
            {
                "commit": "767b88ab7e89b30ed77f5b30c25372d71fa06402",
                "entries": 309,
                "historical_tests": 22,
            },
        )

    def test_cli_replays_historical_generator_and_22_tests(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), "--root", str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("frozen-public-ir: PASS", completed.stdout)
        self.assertIn("22 historical tests", completed.stdout)

    def test_duplicate_keys_non_finite_numbers_and_floats_fail_closed(self) -> None:
        cases = (
            b'{"key":1,"key":2}\n',
            b'{"value":NaN}\n',
            b'{"value":1.5}\n',
        )
        with tempfile.TemporaryDirectory(prefix="morphoia-freeze-json-") as directory:
            root = Path(directory)
            for index, content in enumerate(cases):
                path = root / f"case-{index}.json"
                path.write_bytes(content)
                with self.subTest(index=index), self.assertRaises(
                    frozen.FreezeValidationError
                ):
                    frozen._read_strict_json(
                        root,
                        Path(path.name),
                        hashlib.sha256(content).hexdigest(),
                    )

    def test_symlink_and_hardlink_declarations_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-freeze-links-") as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_bytes(b"{}\n")
            symlink = root / "symlink.json"
            symlink.symlink_to(source.name)
            hardlink = root / "hardlink.json"
            os.link(source, hardlink)
            for path in (symlink, hardlink):
                with self.subTest(path=path.name), self.assertRaises(
                    frozen.FreezeValidationError
                ):
                    frozen._read_confined_file(root, Path(path.name), 1024)

    def test_mutated_declaration_is_rejected_before_git_replay(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-freeze-mutation-") as directory:
            root = Path(directory)
            target = root / "spec" / "evidence"
            target.mkdir(parents=True)
            shutil.copy2(SCHEMA, target / SCHEMA.name)
            declaration = json.loads(FREEZE.read_text(encoding="utf-8"))
            declaration["counts"]["traceability_pass"] = 34
            (target / FREEZE.name).write_text(
                json.dumps(declaration, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                frozen.FreezeValidationError,
                "SHA-256 mismatch",
            ):
                frozen.load_declaration(root)

    def test_commit_topology_mutation_is_rejected(self) -> None:
        declaration = copy.deepcopy(frozen.load_declaration(ROOT))
        declaration["git_snapshot"]["parents"].reverse()
        with self.assertRaisesRegex(
            frozen.FreezeValidationError,
            "topology mismatch",
        ):
            frozen._verify_commit(ROOT, declaration)

    def test_materializer_rejects_an_unlisted_blob(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="morphoia-freeze-archive-"
        ) as directory, self.assertRaisesRegex(
            frozen.FreezeValidationError,
            "blob set differs",
        ):
            frozen._materialize_blobs(
                [{"path": "expected", "mode": "100644", "blob": "0" * 40}],
                {"unexpected": b"content"},
                Path(directory),
            )

    def test_shallow_repository_is_rejected(self) -> None:
        declaration = frozen.load_declaration(ROOT)

        def fake_git(_root: Path, arguments: list[str], *, check: bool = True) -> bytes:
            del check
            if arguments == ["rev-parse", "--is-shallow-repository"]:
                return b"true\n"
            raise AssertionError(arguments)

        with mock.patch.object(
            frozen, "_git", side_effect=fake_git
        ), self.assertRaisesRegex(
            frozen.FreezeValidationError,
            "full Git history",
        ):
            frozen._verify_commit(ROOT, declaration)

    def test_git_invocations_are_offline_and_environment_is_scrubbed(self) -> None:
        arguments = frozen._git_argv(ROOT, ["cat-file", "--batch"])
        self.assertEqual(
            arguments[:7],
            [
                "git",
                "--no-lazy-fetch",
                "--no-replace-objects",
                "--no-optional-locks",
                "-c",
                "protocol.allow=never",
                "-C",
            ],
        )
        with mock.patch.dict(
            os.environ,
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "protocol.allow",
                "GIT_CONFIG_VALUE_0": "always",
                "GIT_CONFIG_PARAMETERS": "'protocol.allow=always'",
                "GIT_OBJECT_DIRECTORY": "/untrusted",
            },
        ):
            environment = frozen._git_environment()
        for key in (
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
            "GIT_CONFIG_PARAMETERS",
            "GIT_OBJECT_DIRECTORY",
        ):
            self.assertNotIn(key, environment)
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")

    def test_replay_runtime_versions_are_exact(self) -> None:
        declaration = copy.deepcopy(frozen.load_declaration(ROOT))
        frozen._verify_runtime(declaration)
        declaration["replay"]["distributions"]["jsonschema"] = "0.0.0"
        with self.assertRaisesRegex(
            frozen.FreezeValidationError,
            "distribution version mismatch",
        ):
            frozen._verify_runtime(declaration)

    def test_snapshot_python_is_deterministic_and_isolated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-freeze-python-") as directory:
            root = Path(directory)
            probe = root / "probe.py"
            probe.write_text(
                "import json, sys\n"
                "print(json.dumps({\n"
                "  'hash': hash('morphoia-frozen-profile'),\n"
                "  'safe_path': sys.flags.safe_path,\n"
                "  'no_user_site': sys.flags.no_user_site,\n"
                "  'dont_write_bytecode': sys.dont_write_bytecode,\n"
                "  'utf8_mode': sys.flags.utf8_mode,\n"
                "}))\n",
                encoding="utf-8",
            )
            first = json.loads(frozen._run_snapshot_command(root, [str(probe)]))
            second = json.loads(frozen._run_snapshot_command(root, [str(probe)]))
        self.assertEqual(first, second)
        self.assertTrue(first["safe_path"])
        self.assertTrue(first["no_user_site"])
        self.assertTrue(first["dont_write_bytecode"])
        self.assertEqual(first["utf8_mode"], 1)

    def test_snapshot_integrity_rejects_an_added_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-freeze-integrity-") as directory:
            root = Path(directory)
            (root / "expected").write_bytes(b"expected")
            (root / "unexpected").write_bytes(b"unexpected")
            with self.assertRaisesRegex(
                frozen.FreezeValidationError,
                "unlisted file",
            ):
                frozen._verify_materialized_snapshot(
                    root,
                    [{"path": "expected", "mode": "100644", "blob": "0" * 40}],
                    {"expected": b"expected"},
                )


if __name__ == "__main__":
    unittest.main()
