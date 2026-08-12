# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import morphoia.engine_ir as engine_ir_module
from morphoia._engine_native import CanonicalLimits, NativeEngine
from morphoia.engine_ir import (
    ReplayCancelledError,
    ReplayError,
    ReplayTimeoutError,
    migrate_legacy_manifest,
    read_bounded_file,
    replay_manifest,
    resolve_manifest_reference,
    seal_content,
    validate_manifest,
)
from morphoia.engine_ir_contract import SemanticError, load_json_strict
from scripts.validate_engine_ir_corpus import _read_confined, validate_corpus


class EngineIrReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._native_temporary = tempfile.TemporaryDirectory(prefix="morphoia-replay-native-")
        cls.repository = Path(__file__).resolve().parents[1]
        cls.corpus = cls.repository / "tests/fixtures/engine-ir/0.1.0"
        cls.library = Path(cls._native_temporary.name) / "libmorphoia_engine.so"
        compiler = shutil.which("g++")
        if compiler is None:
            raise RuntimeError("g++ is required for mandatory replay tests")
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
        cls._native_temporary.cleanup()

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="morphoia-replay-test-")
        self.root = Path(self._temporary.name)
        os.chmod(self.root, 0o700)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(mode=0o700)
        self.manifest_path = self.root / "manifest.json"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _entry(self, index: int = 0) -> dict:
        corpus_index = load_json_strict((self.corpus / "index.json").read_bytes())
        return corpus_index["entries"][index]

    def _prepared(self, index: int = 0) -> tuple[bytes, bytes, dict]:
        entry = self._entry(index)
        manifest = (self.corpus / entry["input"]).read_bytes()
        replay = (self.corpus / entry["replay"]).read_bytes()
        self.manifest_path.write_bytes(manifest)
        os.chmod(self.manifest_path, 0o600)
        return manifest, replay, entry

    def test_all_twenty_native_content_bytes_and_digests_match_goldens(self) -> None:
        corpus_index = load_json_strict((self.corpus / "index.json").read_bytes())
        self.assertEqual(len(corpus_index["entries"]), 20)
        with NativeEngine(self.library) as engine:
            for entry in corpus_index["entries"]:
                with self.subTest(entry=entry["id"]):
                    manifest = validate_manifest(
                        (self.corpus / entry["input"]).read_bytes(), engine=engine
                    )
                    golden = (self.corpus / entry["golden"]).read_bytes()
                    self.assertEqual(manifest.canonical_content, golden)
                    self.assertEqual(manifest.content_sha256, entry["content_sha256"])

    def test_replay_executes_then_resumes_exact_checkpoint(self) -> None:
        _manifest, replay, entry = self._prepared()
        with NativeEngine(self.library) as engine:
            first = replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
            )
            second = replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
            )
        self.assertFalse(first.resumed)
        self.assertTrue(second.resumed)
        self.assertEqual(first.operation_key, second.operation_key)
        self.assertEqual(first.content_sha256, entry["content_sha256"])
        self.assertEqual(first.manifest_sha256, entry["input_sha256"])
        metadata = first.checkpoint_path.lstat()
        self.assertEqual(metadata.st_nlink, 1)
        self.assertEqual(metadata.st_mode & 0o777, 0o600)

    def test_resolver_rejects_mismatch_before_returning_bytes(self) -> None:
        manifest, replay, _entry = self._prepared()
        recipe = load_json_strict(replay)
        self.assertEqual(resolve_manifest_reference(recipe, self.manifest_path), manifest)
        self.manifest_path.write_bytes(manifest + b" ")
        with self.assertRaisesRegex(ReplayError, "size"):
            resolve_manifest_reference(recipe, self.manifest_path)
        self.manifest_path.write_bytes(b"x" * len(manifest))
        with self.assertRaisesRegex(ReplayError, "SHA-256"):
            resolve_manifest_reference(recipe, self.manifest_path)

    def test_resolver_rejects_symlink_components_final_alias_and_hardlink(self) -> None:
        _manifest, replay, _entry = self._prepared()
        recipe = load_json_strict(replay)
        link = self.root / "manifest-link.json"
        link.symlink_to(self.manifest_path)
        with self.assertRaises(OSError):
            resolve_manifest_reference(recipe, link)

        alias = self.root / "manifest-hardlink.json"
        os.link(self.manifest_path, alias)
        with self.assertRaisesRegex(ReplayError, "metadata"):
            resolve_manifest_reference(recipe, self.manifest_path)

        real_parent = self.root / "real-parent"
        real_parent.mkdir(mode=0o700)
        nested = real_parent / "manifest.json"
        shutil.copyfile(self.manifest_path, nested)
        parent_alias = self.root / "parent-alias"
        parent_alias.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(OSError):
            resolve_manifest_reference(recipe, parent_alias / "manifest.json")

    def test_workspace_permissions_and_checkpoint_aliases_fail_closed(self) -> None:
        _manifest, replay, _entry = self._prepared()
        os.chmod(self.workspace, 0o777)
        with (
            NativeEngine(self.library) as engine,
            self.assertRaisesRegex(ReplayError, "writable"),
        ):
            replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
            )

        os.chmod(self.workspace, 0o700)
        runs = self.workspace / "runs"
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        runs.symlink_to(elsewhere, target_is_directory=True)
        with NativeEngine(self.library) as engine, self.assertRaises(OSError):
            replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
            )

    def test_corrupt_checkpoint_and_concurrent_difference_are_rejected(self) -> None:
        _manifest, replay, _entry = self._prepared()
        with NativeEngine(self.library) as engine:
            first = replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
            )
            first.checkpoint_path.write_bytes(b"{}\n")
            os.chmod(first.checkpoint_path, 0o600)
            with self.assertRaisesRegex(ReplayError, "concurrent replay checkpoint differs"):
                replay_manifest(
                    replay,
                    self.manifest_path,
                    workspace_root=self.workspace,
                    engine=engine,
                )

    def test_checkpoint_symlink_and_hardlink_are_rejected(self) -> None:
        _manifest, replay, _entry = self._prepared()
        with NativeEngine(self.library) as engine:
            first = replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
            )
            bytes_before = first.checkpoint_path.read_bytes()
            first.checkpoint_path.unlink()
            outside = self.root / "outside.json"
            outside.write_bytes(bytes_before)
            os.chmod(outside, 0o600)
            first.checkpoint_path.symlink_to(outside)
            with self.assertRaises(OSError):
                replay_manifest(
                    replay,
                    self.manifest_path,
                    workspace_root=self.workspace,
                    engine=engine,
                )
            first.checkpoint_path.unlink()
            os.link(outside, first.checkpoint_path)
            with self.assertRaisesRegex(ReplayError, "metadata"):
                replay_manifest(
                    replay,
                    self.manifest_path,
                    workspace_root=self.workspace,
                    engine=engine,
                )

    def test_checkpoint_no_clobber_handles_identical_and_different_writers(self) -> None:
        runs = self.workspace / "runs"
        runs.mkdir(mode=0o700)
        descriptor = os.open(runs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            identical_errors: list[BaseException] = []
            identical_barrier = threading.Barrier(2)

            def identical_writer() -> None:
                try:
                    identical_barrier.wait()
                    engine_ir_module._write_checkpoint(  # type: ignore[attr-defined]
                        descriptor, "identical.json", b'{"status":"PASS"}\n'
                    )
                except (OSError, ReplayError) as error:  # pragma: no cover - asserted below
                    identical_errors.append(error)

            identical_threads = [threading.Thread(target=identical_writer) for _ in range(2)]
            for thread in identical_threads:
                thread.start()
            for thread in identical_threads:
                thread.join()
            self.assertEqual(identical_errors, [])
            self.assertEqual((runs / "identical.json").read_bytes(), b'{"status":"PASS"}\n')

            different_errors: list[BaseException] = []
            different_barrier = threading.Barrier(2)

            def different_writer(payload: bytes) -> None:
                try:
                    different_barrier.wait()
                    engine_ir_module._write_checkpoint(  # type: ignore[attr-defined]
                        descriptor, "different.json", payload
                    )
                except (OSError, ReplayError) as error:
                    different_errors.append(error)

            different_threads = [
                threading.Thread(target=different_writer, args=(b'{"writer":1}\n',)),
                threading.Thread(target=different_writer, args=(b'{"writer":2}\n',)),
            ]
            for thread in different_threads:
                thread.start()
            for thread in different_threads:
                thread.join()
            self.assertEqual(len(different_errors), 1)
            self.assertIsInstance(different_errors[0], ReplayError)
            self.assertIn(
                (runs / "different.json").read_bytes(),
                (b'{"writer":1}\n', b'{"writer":2}\n'),
            )
            self.assertEqual(
                sorted(path.name for path in runs.iterdir()),
                ["different.json", "identical.json"],
            )
        finally:
            os.close(descriptor)

    def test_checkpoint_snapshot_rejects_in_place_mutation(self) -> None:
        runs = self.workspace / "runs"
        runs.mkdir(mode=0o700)
        checkpoint = runs / "snapshot.json"
        checkpoint.write_bytes(b"x" * 131_072)
        os.chmod(checkpoint, 0o600)
        initial = checkpoint.stat()
        descriptor = os.open(runs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        real_read = os.read
        mutated = False

        def mutating_read(file_descriptor: int, size: int) -> bytes:
            nonlocal mutated
            chunk = real_read(file_descriptor, size)
            if chunk and not mutated:
                mutated = True
                with checkpoint.open("r+b", buffering=0) as output:
                    output.seek(0)
                    output.write(b"y")
                    os.fsync(output.fileno())
                os.utime(
                    checkpoint,
                    ns=(initial.st_atime_ns, initial.st_mtime_ns),
                )
            return chunk

        try:
            with (
                mock.patch("morphoia.engine_ir.os.read", side_effect=mutating_read),
                self.assertRaisesRegex(ReplayError, "changed during snapshot"),
            ):
                engine_ir_module._read_checkpoint(  # type: ignore[attr-defined]
                    descriptor, checkpoint.name
                )
        finally:
            os.close(descriptor)

    def test_bounded_readers_reject_fifo_without_blocking(self) -> None:
        fifo = self.root / "input.fifo"
        os.mkfifo(fifo, mode=0o600)
        started = time.monotonic()
        with self.assertRaisesRegex(ReplayError, "metadata"):
            read_bounded_file(fifo)
        self.assertLess(time.monotonic() - started, 1.0)

        runs = self.workspace / "runs"
        runs.mkdir(mode=0o700)
        os.mkfifo(runs / "checkpoint.fifo", mode=0o600)
        descriptor = os.open(runs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            started = time.monotonic()
            with self.assertRaisesRegex(ReplayError, "metadata"):
                engine_ir_module._read_checkpoint(  # type: ignore[attr-defined]
                    descriptor, "checkpoint.fifo"
                )
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            os.close(descriptor)

        corpus = self.root / "fifo-corpus"
        corpus.mkdir(mode=0o700)
        os.mkfifo(corpus / "fixture.fifo", mode=0o600)
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "metadata"):
            _read_confined(corpus, "fixture.fifo")
        self.assertLess(time.monotonic() - started, 1.0)

    def test_bounded_file_and_corpus_snapshots_include_ctime(self) -> None:
        source = self.root / "snapshot-source.json"
        source.write_bytes(b"x" * 131_072)
        os.chmod(source, 0o600)
        initial = source.stat()
        real_read = os.read
        mutated = False

        def mutating_read(file_descriptor: int, size: int) -> bytes:
            nonlocal mutated
            chunk = real_read(file_descriptor, size)
            if chunk and not mutated:
                mutated = True
                with source.open("r+b", buffering=0) as output:
                    output.seek(0)
                    output.write(b"y")
                    os.fsync(output.fileno())
                os.utime(source, ns=(initial.st_atime_ns, initial.st_mtime_ns))
            return chunk

        with (
            mock.patch("morphoia.engine_ir.os.read", side_effect=mutating_read),
            self.assertRaisesRegex(ReplayError, "changed during snapshot"),
        ):
            read_bounded_file(source)

        corpus = self.root / "snapshot-corpus"
        corpus.mkdir(mode=0o700)
        fixture = corpus / "fixture.json"
        fixture.write_bytes(b"x" * 131_072)
        os.chmod(fixture, 0o600)
        initial = fixture.stat()
        mutated = False

        def mutating_corpus_read(file_descriptor: int, size: int) -> bytes:
            nonlocal mutated
            chunk = real_read(file_descriptor, size)
            if chunk and not mutated:
                mutated = True
                with fixture.open("r+b", buffering=0) as output:
                    output.seek(0)
                    output.write(b"y")
                    os.fsync(output.fileno())
                os.utime(fixture, ns=(initial.st_atime_ns, initial.st_mtime_ns))
            return chunk

        with (
            mock.patch(
                "scripts.validate_engine_ir_corpus.os.read",
                side_effect=mutating_corpus_read,
            ),
            self.assertRaisesRegex(ValueError, "changed during snapshot"),
        ):
            _read_confined(corpus, "fixture.json")

    def test_operation_key_tracks_python_and_native_implementation(self) -> None:
        _manifest, replay, _entry = self._prepared()
        with NativeEngine(self.library) as engine:
            first = replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
            )
            real_validate = engine_ir_module.validate_manifest

            def changed_validate(*args, **kwargs):
                return real_validate(*args, **kwargs)

            with mock.patch("morphoia.engine_ir.validate_manifest", changed_validate):
                changed = replay_manifest(
                    replay,
                    self.manifest_path,
                    workspace_root=self.workspace,
                    engine=engine,
                )
            original_schema_resolver = engine_ir_module._resolve_schema  # type: ignore[attr-defined]
            original_manifest_schema = original_schema_resolver(
                "morphoia-engine-ir-manifest-0.1.0.schema.json", None
            )
            modified_schema = self.root / "modified-manifest.schema.json"
            modified_schema.write_bytes(original_manifest_schema.read_bytes() + b"\n")

            def schema_resolver(filename: str, explicit: Path | None) -> Path:
                if filename == "morphoia-engine-ir-manifest-0.1.0.schema.json":
                    return modified_schema
                return original_schema_resolver(filename, explicit)

            with mock.patch(
                "morphoia.engine_ir._resolve_schema", side_effect=schema_resolver
            ):
                schema_changed = replay_manifest(
                    replay,
                    self.manifest_path,
                    workspace_root=self.workspace,
                    engine=engine,
                )
            limits_changed = replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=self.workspace,
                engine=engine,
                limits=CanonicalLimits(maximum_input_bytes=1_048_575),
            )
        self.assertNotEqual(first.operation_key, changed.operation_key)
        self.assertFalse(changed.resumed)
        self.assertNotEqual(first.operation_key, schema_changed.operation_key)
        self.assertFalse(schema_changed.resumed)
        self.assertNotEqual(first.operation_key, limits_changed.operation_key)
        self.assertFalse(limits_changed.resumed)

        modified_library = self.root / "libmorphoia_engine-modified.so"
        modified_library.write_bytes(self.library.read_bytes() + b"tracked-build-byte")
        os.chmod(modified_library, 0o700)
        second_workspace = self.root / "second-workspace"
        second_workspace.mkdir(mode=0o700)
        with NativeEngine(modified_library) as engine:
            modified = replay_manifest(
                replay,
                self.manifest_path,
                workspace_root=second_workspace,
                engine=engine,
            )
        self.assertNotEqual(first.operation_key, modified.operation_key)

    def test_timeout_and_cancellation_are_bounded(self) -> None:
        _manifest, replay, _entry = self._prepared()
        invalid = (True, math.nan, math.inf, -1.0, 3600.1, "1")
        with NativeEngine(self.library) as engine:
            for timeout in invalid:
                with self.subTest(timeout=timeout), self.assertRaisesRegex(
                    ValueError, "finite number"
                ):
                    replay_manifest(
                        replay,
                        self.manifest_path,
                        workspace_root=self.workspace,
                        engine=engine,
                        timeout_seconds=timeout,  # type: ignore[arg-type]
                    )
            with self.assertRaises(ReplayTimeoutError):
                replay_manifest(
                    replay,
                    self.manifest_path,
                    workspace_root=self.workspace,
                    engine=engine,
                    timeout_seconds=0,
                )
            cancellation = threading.Event()
            cancellation.set()
            with self.assertRaises(ReplayCancelledError):
                replay_manifest(
                    replay,
                    self.manifest_path,
                    workspace_root=self.workspace,
                    engine=engine,
                    cancellation=cancellation,
                )

    def test_seal_rejects_false_well_formed_digest_and_reseals(self) -> None:
        manifest, _replay, _entry = self._prepared()
        document = load_json_strict(manifest)
        document["identity"]["digest"] = "f" * 64
        forged = json.dumps(document, separators=(",", ":")).encode()
        with NativeEngine(self.library) as engine:
            with self.assertRaisesRegex(SemanticError, "native content identity"):
                validate_manifest(forged, engine=engine)
            sealed = seal_content(document["content"], engine=engine)
        self.assertNotEqual(sealed.content_sha256, "f" * 64)
        self.assertEqual(sealed.document["identity"]["digest"], sealed.content_sha256)

    def test_public_migration_natively_seals_and_keeps_legacy_bytes(self) -> None:
        migration = self.corpus / "migration"
        legacy = (migration / "legacy-input.json").read_bytes()
        before = hashlib.sha256(legacy).hexdigest()
        metadata = load_json_strict((migration / "metadata.json").read_bytes())
        expected_content = load_json_strict((migration / "expected-content.json").read_bytes())
        with NativeEngine(self.library) as engine:
            migrated = migrate_legacy_manifest(legacy, metadata=metadata, engine=engine)
        self.assertEqual(hashlib.sha256(legacy).hexdigest(), before)
        self.assertEqual(migrated.document["content"], expected_content)
        self.assertEqual(migrated.document["identity"]["digest"], migrated.content_sha256)

    def test_corpus_validator_rejects_index_traversal_and_fixture_symlink(self) -> None:
        copied = self.root / "corpus"
        shutil.copytree(self.corpus, copied)
        index_path = copied / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["entries"][0]["input"] = "../outside.json"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsafe corpus index path"):
            validate_corpus(copied, self.library)

        shutil.rmtree(copied)
        shutil.copytree(self.corpus, copied)
        fixture = copied / "inputs/graph-01-brep-source.json"
        target = self.root / "outside.json"
        fixture.rename(target)
        fixture.symlink_to(target)
        with self.assertRaises(OSError):
            validate_corpus(copied, self.library)

        fixture.unlink()
        os.link(target, fixture)
        with self.assertRaisesRegex(ValueError, "metadata"):
            validate_corpus(copied, self.library)

    def test_corpus_validator_rejects_duplicate_index_entries(self) -> None:
        copied = self.root / "duplicate-corpus"
        shutil.copytree(self.corpus, copied)
        index_path = copied / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["entries"] = [copy.deepcopy(index["entries"][0]) for _ in range(20)]
        index_path.write_text(json.dumps(index), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be unique"):
            validate_corpus(copied, self.library)

    def test_corpus_validator_rejects_symlinked_root_ancestor(self) -> None:
        real_parent = self.root / "real-corpus-parent"
        real_parent.mkdir(mode=0o700)
        copied = real_parent / "corpus"
        shutil.copytree(self.corpus, copied)
        parent_alias = self.root / "corpus-parent-alias"
        parent_alias.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(OSError):
            validate_corpus(parent_alias / "corpus", self.library)


if __name__ == "__main__":
    unittest.main()
