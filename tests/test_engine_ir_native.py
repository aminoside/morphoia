# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

from __future__ import annotations

import contextlib
import ctypes
import gc
import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from morphoia import _engine_native as native


class EngineIrNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="morphoia-native-python-")
        cls.work = Path(cls._temporary.name)
        cls.repository = Path(__file__).resolve().parents[1]
        cls.library = cls.work / "libmorphoia_engine.so"
        compiler = shutil.which("g++")
        if compiler is None:
            raise RuntimeError("g++ is required for the mandatory native Python tests")
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

    def test_explicit_library_negotiates_exact_capability(self) -> None:
        with native.NativeEngine(self.library) as engine:
            self.assertEqual(engine.version, "0.0.1")
            self.assertEqual(engine.capability.capability_name, native.FORMAT_IDENTIFIER)
            self.assertEqual(engine.capability.format_version, native.FORMAT_VERSION)
            self.assertEqual(engine.capability.media_type, native.MEDIA_TYPE)
            self.assertEqual(engine.capability.canonical_profile, native.CANONICAL_PROFILE)
            self.assertEqual(engine.capability.extension_keys, ())

    def test_profile1_two_pass_bytes_and_digest_agree(self) -> None:
        with native.NativeEngine(self.library) as engine:
            result = engine.canonicalize('{"b":2,"a":1}')
        self.assertEqual(result.canonical, b'{"a":1,"b":2}')
        self.assertEqual(result.sha256, hashlib.sha256(result.canonical).hexdigest())
        self.assertEqual(
            result.sha256,
            "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
        )

    def test_context_manager_closes_deterministically(self) -> None:
        engine = native.NativeEngine(self.library)
        with engine:
            self.assertFalse(engine.closed)
        self.assertTrue(engine.closed)
        engine.close()
        with self.assertRaisesRegex(native.NativeLibraryError, "closed"):
            engine.canonicalize("null")

    def test_native_invalid_json_exposes_structured_diagnostic(self) -> None:
        with (
            native.NativeEngine(self.library) as engine,
            self.assertRaises(native.NativeEngineError) as caught,
        ):
            engine.canonicalize('{"a":1,"a":2}')
        error = caught.exception
        self.assertEqual(error.status_name, "MORPHOIA_STATUS_INVALID_JSON")
        self.assertTrue(error.message)
        self.assertTrue(error.context)
        self.assertTrue(error.cause)
        self.assertTrue(error.affected_elements)
        self.assertTrue(error.recommendation)

    def test_native_resource_limits_fail_closed(self) -> None:
        with (
            native.NativeEngine(self.library) as engine,
            self.assertRaises(native.NativeEngineError) as caught,
        ):
            engine.canonicalize(
                '{"a":1}',
                limits=native.CanonicalLimits(
                    maximum_input_bytes=2,
                    maximum_string_bytes=2,
                    maximum_values=2,
                    maximum_depth=2,
                ),
            )
        self.assertEqual(caught.exception.status_name, "MORPHOIA_STATUS_RESOURCE_LIMIT")

    def test_invalid_python_limit_and_input_types_are_rejected(self) -> None:
        with native.NativeEngine(self.library) as engine:
            with self.assertRaisesRegex(ValueError, "positive integer"):
                engine.canonicalize("null", limits=native.CanonicalLimits(maximum_depth=0))
            with self.assertRaisesRegex(TypeError, "str or bytes-like"):
                engine.canonicalize(5)  # type: ignore[arg-type]
            with self.assertRaisesRegex(TypeError, "capability name"):
                engine.query_capability(5)  # type: ignore[arg-type]

    def test_environment_library_path_must_be_absolute(self) -> None:
        with (
            mock.patch.dict(
                os.environ, {native.LIBRARY_ENVIRONMENT_VARIABLE: "relative.so"}
            ),
            self.assertRaisesRegex(native.NativeLibraryNotFoundError, "absolute"),
        ):
            native.resolve_native_library()
        with mock.patch.dict(
            os.environ,
            {native.LIBRARY_ENVIRONMENT_VARIABLE: os.fspath(self.library)},
        ):
            self.assertEqual(native.resolve_native_library(), os.fspath(self.library.resolve()))

    def test_loader_does_not_search_current_working_directory(self) -> None:
        local = self.work / "libmorphoia_engine.so.0"
        local.write_bytes(b"not a shared library")
        with contextlib.chdir(self.work), mock.patch.dict(os.environ, {}, clear=True):
            with (
                mock.patch("ctypes.util.find_library", return_value=None),
                self.assertRaises(native.NativeLibraryNotFoundError),
            ):
                native.resolve_native_library()
            with self.assertRaisesRegex(native.NativeLibraryNotFoundError, "absolute"):
                native.resolve_native_library(local.name)

    def test_missing_library_never_uses_a_python_fallback(self) -> None:
        absent = self.work / "absent" / "libmorphoia_engine.so"
        with self.assertRaises(native.NativeLibraryNotFoundError):
            native.NativeEngine(absent)

    def test_library_missing_required_symbols_is_wrapped(self) -> None:
        libc = Path("/lib/x86_64-linux-gnu/libc.so.6")
        if not libc.is_file():
            self.skipTest("glibc path is unavailable on this Linux profile")
        with self.assertRaisesRegex(native.NativeLibraryError, "ABI-v1 symbols"):
            native.NativeEngine(libc)

    def test_capability_view_survives_gc_pressure(self) -> None:
        with native.NativeEngine(self.library) as engine:
            for index in range(100):
                gc.collect()
                self.assertIsNone(engine.query_capability(f"org.example.unknown.{index}"))
            self.assertIsNotNone(engine.query_capability(native.CAPABILITY_ENGINE_IR_MANIFEST))

    def test_wrapper_serializes_context_lifetime_across_threads(self) -> None:
        errors: list[BaseException] = []
        outputs: list[bytes] = []
        with native.NativeEngine(self.library) as engine:
            def worker() -> None:
                try:
                    outputs.append(engine.canonicalize('{"z":0,"a":1}').canonical)
                except native.NativeLibraryError as error:  # pragma: no cover
                    errors.append(error)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(outputs, [b'{"a":1,"z":0}'] * 8)

    def test_explicit_length_diagnostic_decoder_preserves_utf8_and_nul(self) -> None:
        diagnostic = native._Diagnostic()  # type: ignore[attr-defined]
        raw = "é\x00x".encode()
        address = (
            ctypes.addressof(diagnostic)
            + native._Diagnostic.message.offset  # type: ignore[attr-defined]
        )
        ctypes.memmove(address, raw, len(raw))
        decoded = native._diagnostic_text(  # type: ignore[attr-defined]
            diagnostic, "message", len(raw), 256
        )
        self.assertEqual(decoded, "é\x00x")


if __name__ == "__main__":
    unittest.main()
