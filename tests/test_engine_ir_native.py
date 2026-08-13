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
import time
import unittest
from pathlib import Path
from unittest import mock

from morphoia import _engine_native as native

UNIT_REGISTRY = {
    "1": ((0, 0, 0, 0, 0, 0, 0), 1, 0),
    "m": ((1, 0, 0, 0, 0, 0, 0), 1, 0),
    "mm": ((1, 0, 0, 0, 0, 0, 0), 1, -3),
    "s": ((0, 0, 1, 0, 0, 0, 0), 1, 0),
    "kg": ((0, 1, 0, 0, 0, 0, 0), 1, 0),
    "g": ((0, 1, 0, 0, 0, 0, 0), 1, -3),
    "A": ((0, 0, 0, 1, 0, 0, 0), 1, 0),
    "K": ((0, 0, 0, 0, 1, 0, 0), 1, 0),
    "mol": ((0, 0, 0, 0, 0, 1, 0), 1, 0),
    "cd": ((0, 0, 0, 0, 0, 0, 1), 1, 0),
}


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
                os.fspath(cls.repository / "cpp/src/core/unit_registry.cpp"),
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

    def test_bounded_unit_capability_and_all_literals_are_exact(self) -> None:
        with native.NativeEngine(self.library) as engine:
            capability = engine.query_capability(native.CAPABILITY_ENGINE_IR_CORE_SI)
            self.assertIsNotNone(capability)
            assert capability is not None
            self.assertEqual(capability.capability_name, "engine-ir-core-si-0.1")
            self.assertEqual(capability.format_identifier, "morphoia.engine.ir-inspection")
            self.assertEqual(capability.format_version, "0.1.0")
            self.assertEqual(
                capability.media_type,
                "application/vnd.morphoia.ir-inspection.v0+json",
            )
            for code, (dimensions, coefficient, scale) in UNIT_REGISTRY.items():
                with self.subTest(code=code):
                    result = engine.validate_engine_ir_unit(
                        code,
                        dimensions=dimensions,
                        si_factor_coefficient=coefficient,
                        si_factor_scale=scale,
                    )
                    self.assertTrue(result.recognized)
                    self.assertTrue(result.dimensions_match)
                    self.assertTrue(result.si_factor_match)
                    self.assertTrue(result.qualified)
                    self.assertEqual(result.expected_dimensions, dimensions)
                    self.assertEqual(result.expected_si_factor_coefficient, coefficient)
                    self.assertEqual(result.expected_si_factor_scale, scale)

    def test_unit_wrapper_preserves_unknown_and_mismatch_truth(self) -> None:
        with native.NativeEngine(self.library) as engine:
            unknown = engine.validate_engine_ir_unit(
                "ft",
                dimensions=(1, 0, 0, 0, 0, 0, 0),
                si_factor_coefficient=3048,
                si_factor_scale=-4,
            )
            self.assertFalse(unknown.recognized)
            self.assertFalse(unknown.qualified)
            self.assertEqual(unknown.expected_dimensions, (0, 0, 0, 0, 0, 0, 0))
            mismatch = engine.validate_engine_ir_unit(
                "mm",
                dimensions=(0, 0, 1, 0, 0, 0, 0),
                si_factor_coefficient=1,
                si_factor_scale=-3,
            )
            self.assertTrue(mismatch.recognized)
            self.assertFalse(mismatch.dimensions_match)
            self.assertTrue(mismatch.si_factor_match)
            self.assertFalse(mismatch.qualified)
            self.assertEqual(mismatch.expected_dimensions, (1, 0, 0, 0, 0, 0, 0))
            self.assertEqual(mismatch.expected_si_factor_scale, -3)
            coefficient_mismatch = engine.validate_engine_ir_unit(
                "mm",
                dimensions=(1, 0, 0, 0, 0, 0, 0),
                si_factor_coefficient=2,
                si_factor_scale=-3,
            )
            self.assertTrue(coefficient_mismatch.dimensions_match)
            self.assertFalse(coefficient_mismatch.si_factor_match)
            self.assertFalse(coefficient_mismatch.qualified)
            scale_mismatch = engine.validate_engine_ir_unit(
                "mm",
                dimensions=(1, 0, 0, 0, 0, 0, 0),
                si_factor_coefficient=1,
                si_factor_scale=-2,
            )
            self.assertTrue(scale_mismatch.dimensions_match)
            self.assertFalse(scale_mismatch.si_factor_match)
            self.assertFalse(scale_mismatch.qualified)

    def test_unit_wrapper_rejects_invalid_python_and_native_inputs(self) -> None:
        with native.NativeEngine(self.library) as engine:
            with self.assertRaisesRegex(TypeError, "exactly seven"):
                engine.validate_engine_ir_unit(
                    "m",
                    dimensions=(1, 0),  # type: ignore[arg-type]
                    si_factor_coefficient=1,
                    si_factor_scale=0,
                )
            with self.assertRaisesRegex(ValueError, "fit int32"):
                engine.validate_engine_ir_unit(
                    "m",
                    dimensions=((1 << 31), 0, 0, 0, 0, 0, 0),
                    si_factor_coefficient=1,
                    si_factor_scale=0,
                )
            for code in ("", "x" * 33, "m\x00"):
                with self.subTest(code=code), self.assertRaises(native.NativeEngineError):
                    engine.validate_engine_ir_unit(
                        code,
                        dimensions=(1, 0, 0, 0, 0, 0, 0),
                        si_factor_coefficient=1,
                        si_factor_scale=0,
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

    def test_historical_seven_symbol_library_fails_only_on_unit_validation(self) -> None:
        compiler = shutil.which("g++")
        assert compiler is not None
        historical_map = self.work / "historical-seven-symbols.map"
        historical_map.write_text(
            "MORPHOIA_ENGINE_0.0 {\n"
            "  global:\n"
            "    morphoia_context_create; morphoia_context_destroy;\n"
            "    morphoia_context_get_abi_version; morphoia_context_query_capability;\n"
            "    morphoia_canonical_json_profile1; morphoia_engine_get_version;\n"
            "    morphoia_status_name;\n"
            "  local: *;\n"
            "};\n",
            encoding="utf-8",
        )
        historical = self.work / "libmorphoia_engine_historical.so"
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
                f"-I{self.repository / 'cpp/include'}",
                f"-I{self.repository / 'cpp/src'}",
                os.fspath(self.repository / "cpp/src/engine.cpp"),
                os.fspath(self.repository / "cpp/src/core/canonical_json.cpp"),
                os.fspath(self.repository / "cpp/src/core/sha256.cpp"),
                os.fspath(self.repository / "cpp/src/core/unit_registry.cpp"),
                f"-Wl,--version-script,{historical_map}",
                "-o",
                os.fspath(historical),
            ],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        )
        with native.NativeEngine(historical) as engine:
            self.assertEqual(engine.canonicalize('{"b":2,"a":1}').canonical, b'{"a":1,"b":2}')
            with self.assertRaisesRegex(native.NativeLibraryError, "unit-validation ABI-v1"):
                engine.validate_engine_ir_unit(
                    "m",
                    dimensions=(1, 0, 0, 0, 0, 0, 0),
                    si_factor_coefficient=1,
                    si_factor_scale=0,
                )

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
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive(), "serialized wrapper call deadlocked")
        self.assertEqual(errors, [])
        self.assertEqual(outputs, [b'{"a":1,"z":0}'] * 8)

    def test_close_waits_for_mixed_calls_then_future_calls_fail_stably(self) -> None:
        engine = native.NativeEngine(self.library)
        started = threading.Barrier(9)
        outcomes: list[str] = []
        failures: list[BaseException] = []

        def worker(index: int) -> None:
            try:
                started.wait(timeout=5)
                if index % 3 == 0:
                    engine.canonicalize('{"z":0,"a":1}')
                elif index % 3 == 1:
                    engine.query_capability(native.CAPABILITY_ENGINE_IR_CORE_SI)
                else:
                    engine.validate_engine_ir_unit(
                        "mm",
                        dimensions=(1, 0, 0, 0, 0, 0, 0),
                        si_factor_coefficient=1,
                        si_factor_scale=-3,
                    )
                outcomes.append("completed")
            except native.NativeLibraryError as error:
                if "closed" not in str(error):
                    failures.append(error)
                outcomes.append("closed")

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        started.wait(timeout=5)
        time.sleep(0.001)
        engine.close()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "mixed call/close deadlocked")
        self.assertEqual(failures, [])
        self.assertEqual(len(outcomes), 8)
        self.assertTrue(engine.closed)
        with self.assertRaisesRegex(native.NativeLibraryError, "closed"):
            engine.query_capability(native.CAPABILITY_ENGINE_IR_CORE_SI)

    def test_close_blocks_until_an_inflight_native_call_releases_the_lock(self) -> None:
        engine = native.NativeEngine(self.library)
        entered = threading.Event()
        release = threading.Event()
        call_done = threading.Event()
        close_done = threading.Event()
        failures: list[BaseException] = []
        original = engine._library.morphoia_canonical_json_profile1  # type: ignore[attr-defined]

        def blocking_call(*arguments):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("timed out waiting to release native call")
            return original(*arguments)

        engine._library.morphoia_canonical_json_profile1 = blocking_call  # type: ignore[attr-defined]

        def call() -> None:
            try:
                engine.canonicalize('{"z":0,"a":1}')
            except (OSError, RuntimeError, ValueError) as error:  # pragma: no cover
                failures.append(error)
            finally:
                call_done.set()

        def close() -> None:
            try:
                engine.close()
            except native.NativeLibraryError as error:  # pragma: no cover
                failures.append(error)
            finally:
                close_done.set()

        call_thread = threading.Thread(target=call)
        call_thread.start()
        self.assertTrue(entered.wait(timeout=5), "native call never became active")
        close_thread = threading.Thread(target=close)
        close_thread.start()
        self.assertFalse(close_done.wait(timeout=0.05), "close bypassed an active call")
        release.set()
        call_thread.join(timeout=5)
        close_thread.join(timeout=5)
        self.assertTrue(call_done.is_set())
        self.assertTrue(close_done.is_set())
        self.assertEqual(failures, [])
        self.assertTrue(engine.closed)

    def test_distinct_contexts_execute_in_parallel_without_shared_results(self) -> None:
        barrier = threading.Barrier(4)
        outputs: list[tuple[bytes, bool]] = []
        failures: list[BaseException] = []

        def worker() -> None:
            try:
                with native.NativeEngine(self.library) as engine:
                    barrier.wait(timeout=5)
                    canonical = engine.canonicalize('{"z":0,"a":1}').canonical
                    qualified = engine.validate_engine_ir_unit(
                        "m",
                        dimensions=(1, 0, 0, 0, 0, 0, 0),
                        si_factor_coefficient=1,
                        si_factor_scale=0,
                    ).qualified
                    outputs.append((canonical, qualified))
            except (OSError, RuntimeError, ValueError) as error:  # pragma: no cover
                failures.append(error)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "distinct-context execution deadlocked")
        self.assertEqual(failures, [])
        self.assertEqual(outputs, [(b'{"a":1,"z":0}', True)] * 4)

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
