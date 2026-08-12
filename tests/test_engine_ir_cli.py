# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class EngineIrCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="morphoia-cli-native-")
        cls.repository = Path(__file__).resolve().parents[1]
        cls.corpus = cls.repository / "tests/fixtures/engine-ir/0.1.0"
        cls.library = Path(cls._temporary.name) / "libmorphoia_engine.so"
        compiler = shutil.which("g++")
        if compiler is None:
            raise RuntimeError("g++ is required for mandatory CLI tests")
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
                f"-Wl,--version-script,{cls.repository / 'cmake/morphoia_engine.map'}",
                "-o",
                os.fspath(cls.library),
            ],
            cwd=cls.repository,
            check=True,
            capture_output=True,
            text=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.fspath(self.repository / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [os.sys.executable, "-m", "morphoia", *arguments],
            cwd=self.repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_validate_json_and_human_output_are_stable(self) -> None:
        source = self.corpus / "inputs/graph-01-brep-source.json"
        result = self._run(
            "engine-ir",
            "validate",
            os.fspath(source),
            "--library",
            os.fspath(self.library),
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "PASS")
        index = json.loads((self.corpus / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["content_sha256"], index["entries"][0]["content_sha256"])
        human = self._run(
            "engine-ir",
            "validate",
            os.fspath(source),
            "--library",
            os.fspath(self.library),
        )
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("PASS Engine IR 0.1.0", human.stdout)

    def test_invalid_manifest_and_missing_native_library_return_one(self) -> None:
        invalid = self.corpus / "invalid/duplicate-key.json"
        result = self._run(
            "engine-ir",
            "validate",
            os.fspath(invalid),
            "--library",
            os.fspath(self.library),
            "--json",
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stderr)
        self.assertEqual(payload["status"], "FAIL")
        self.assertEqual(payload["native_status"], "MORPHOIA_STATUS_INVALID_JSON")

        absent = self._run(
            "engine-ir",
            "validate",
            os.fspath(invalid),
            "--library",
            "/definitely/absent/libmorphoia_engine.so",
            "--json",
        )
        self.assertEqual(absent.returncode, 1)
        self.assertEqual(json.loads(absent.stderr)["error_type"], "NativeLibraryNotFoundError")

        human = self._run(
            "engine-ir",
            "validate",
            os.fspath(invalid),
            "--library",
            os.fspath(self.library),
        )
        self.assertEqual(human.returncode, 1)
        self.assertEqual(human.stdout, "")
        self.assertIn("MORPHOIA_STATUS_INVALID_JSON", human.stderr)

        libc = Path("/lib/x86_64-linux-gnu/libc.so.6")
        if libc.is_file():
            incompatible = self._run(
                "engine-ir",
                "validate",
                os.fspath(invalid),
                "--library",
                os.fspath(libc),
                "--json",
            )
            self.assertEqual(incompatible.returncode, 1)
            self.assertEqual(incompatible.stdout, "")
            incompatible_error = json.loads(incompatible.stderr)
            self.assertEqual(incompatible_error["status"], "FAIL")
            self.assertEqual(incompatible_error["error_type"], "NativeLibraryError")

    def test_validate_and_recipe_inputs_reject_symlink_and_oversize(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-cli-inputs-") as temporary_text:
            root = Path(temporary_text)
            os.chmod(root, 0o700)
            source_alias = root / "source.json"
            source_alias.symlink_to(
                self.corpus / "inputs/graph-01-brep-source.json"
            )
            symlink = self._run(
                "engine-ir",
                "validate",
                os.fspath(source_alias),
                "--library",
                os.fspath(self.library),
                "--json",
            )
            self.assertEqual(symlink.returncode, 1)

            real_parent = root / "real-parent"
            real_parent.mkdir(mode=0o700)
            nested_source = real_parent / "source.json"
            nested_source.write_bytes(
                (self.corpus / "inputs/graph-01-brep-source.json").read_bytes()
            )
            os.chmod(nested_source, 0o600)
            parent_alias = root / "parent-alias"
            parent_alias.symlink_to(real_parent, target_is_directory=True)
            parent_symlink = self._run(
                "engine-ir",
                "validate",
                os.fspath(parent_alias / "source.json"),
                "--library",
                os.fspath(self.library),
                "--json",
            )
            self.assertEqual(parent_symlink.returncode, 1)

            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (1_048_576 + 1))
            os.chmod(oversized, 0o600)
            too_large = self._run(
                "engine-ir",
                "validate",
                os.fspath(oversized),
                "--library",
                os.fspath(self.library),
                "--json",
            )
            self.assertEqual(too_large.returncode, 1)
            self.assertIn("size", json.loads(too_large.stderr)["message"])

            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            recipe_alias = root / "recipe.json"
            recipe_alias.symlink_to(
                self.corpus / "replays/graph-01-brep-source.replay.json"
            )
            recipe = self._run(
                "engine-ir",
                "replay",
                os.fspath(recipe_alias),
                "--manifest",
                os.fspath(self.corpus / "inputs/graph-01-brep-source.json"),
                "--workspace",
                os.fspath(workspace),
                "--library",
                os.fspath(self.library),
                "--json",
            )
            self.assertEqual(recipe.returncode, 1)

    def test_replay_json_reports_execute_then_resume(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-cli-replay-") as temporary_text:
            workspace = Path(temporary_text)
            os.chmod(workspace, 0o700)
            arguments = (
                "engine-ir",
                "replay",
                os.fspath(self.corpus / "replays/graph-01-brep-source.replay.json"),
                "--manifest",
                os.fspath(self.corpus / "inputs/graph-01-brep-source.json"),
                "--workspace",
                os.fspath(workspace),
                "--library",
                os.fspath(self.library),
                "--json",
            )
            first = self._run(*arguments)
            second = self._run(*arguments)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse(json.loads(first.stdout)["resumed"])
        self.assertTrue(json.loads(second.stdout)["resumed"])

    def test_replay_cli_does_not_resolve_manifest_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-cli-symlink-") as temporary_text:
            root = Path(temporary_text)
            os.chmod(root, 0o700)
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            manifest_alias = root / "manifest.json"
            manifest_alias.symlink_to(
                self.corpus / "inputs/graph-01-brep-source.json"
            )
            result = self._run(
                "engine-ir",
                "replay",
                os.fspath(self.corpus / "replays/graph-01-brep-source.replay.json"),
                "--manifest",
                os.fspath(manifest_alias),
                "--workspace",
                os.fspath(workspace),
                "--library",
                os.fspath(self.library),
                "--json",
            )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "FAIL")

    def test_legacy_compile_help_is_explicitly_non_authoritative(self) -> None:
        result = self._run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("non-authoritative legacy prototype", result.stdout)
        self.assertIn("identity domain", result.stdout)


if __name__ == "__main__":
    unittest.main()
