#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0 OR MIT

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_dir="$(cd -- "${script_dir}/.." && pwd -P)"
preset="${MORPHOIA_CMAKE_PRESET:-engine-cpu-debug}"

if command -v cmake >/dev/null 2>&1 && [[ "${MORPHOIA_BOOTSTRAP_FORCE_FALLBACK:-0}" != "1" ]]; then
  echo "bootstrap-engine: using CMake preset ${preset}"
  cd -- "${repo_dir}"
  cmake --preset "${preset}"
  cmake --build --preset "${preset}" --parallel
  ctest --preset "${preset}" --output-on-failure
  echo "bootstrap-engine: PASS (CMake)"
  exit 0
fi

cc="${CC:-gcc}"
cxx="${CXX:-g++}"
for compiler in "${cc}" "${cxx}"; do
  if ! command -v "${compiler}" >/dev/null 2>&1; then
    echo "bootstrap-engine: required fallback compiler not found: ${compiler}" >&2
    exit 127
  fi
done

fallback_dir="$(mktemp -d "${TMPDIR:-/tmp}/morphoia-engine-bootstrap.XXXXXX")"
cleanup() {
  if [[ -n "${fallback_dir:-}" && -d "${fallback_dir}" ]]; then
    rm -rf -- "${fallback_dir}"
  fi
}
trap cleanup EXIT

common_warnings=(-Wall -Wextra -Wpedantic -Werror)
include_arg=(-I"${repo_dir}/cpp/include")
internal_include_arg=(-I"${repo_dir}/cpp/src")

echo "bootstrap-engine: using direct compiler fallback"
"${cxx}" -std=c++20 "${common_warnings[@]}" "${include_arg[@]}" \
  -DMORPHOIA_ENGINE_SHARED -DMORPHOIA_ENGINE_EXPORTS -fPIC -fvisibility=hidden \
  -fvisibility-inlines-hidden -shared "${repo_dir}/cpp/src/engine.cpp" \
  -Wl,--version-script,"${repo_dir}/cmake/morphoia_engine.map" \
  -o "${fallback_dir}/libmorphoia_engine.so"

"${cc}" -std=c11 "${common_warnings[@]}" "${include_arg[@]}" \
  -DMORPHOIA_ENGINE_SHARED \
  -c "${repo_dir}/tests/native/abi_c_smoke.c" -o "${fallback_dir}/abi_c_smoke.o"
"${cxx}" "${fallback_dir}/abi_c_smoke.o" -L"${fallback_dir}" -lmorphoia_engine \
  -Wl,-rpath,"${fallback_dir}" \
  -o "${fallback_dir}/abi_c_smoke"

"${cxx}" -std=c++20 "${common_warnings[@]}" "${include_arg[@]}" \
  -DMORPHOIA_ENGINE_SHARED \
  -c "${repo_dir}/tests/native/core_smoke.cpp" -o "${fallback_dir}/core_smoke.o"
"${cxx}" "${fallback_dir}/core_smoke.o" -L"${fallback_dir}" -lmorphoia_engine \
  -Wl,-rpath,"${fallback_dir}" \
  -o "${fallback_dir}/core_smoke"

expected_exports=(
  morphoia_context_create
  morphoia_context_destroy
  morphoia_context_get_abi_version
  morphoia_engine_get_version
  morphoia_status_name
)
mapfile -t actual_exports < <(
  nm -D --defined-only "${fallback_dir}/libmorphoia_engine.so" |
    awk 'NF >= 3 && $2 != "A" {print $3}' |
    sed 's/@.*//' |
    sort
)
if [[ "${actual_exports[*]}" != "${expected_exports[*]}" ]]; then
  echo "bootstrap-engine: exported symbol set mismatch" >&2
  printf 'expected: %s\n' "${expected_exports[*]}" >&2
  printf 'actual:   %s\n' "${actual_exports[*]}" >&2
  exit 1
fi

"${fallback_dir}/abi_c_smoke"
"${fallback_dir}/core_smoke"

"${cxx}" -std=c++20 "${common_warnings[@]}" "${internal_include_arg[@]}" \
  "${repo_dir}/cpp/src/core/sha256.cpp" \
  "${repo_dir}/tests/native/sha256_test.cpp" \
  -o "${fallback_dir}/sha256_test"
"${fallback_dir}/sha256_test"

"${cxx}" -std=c++20 "${common_warnings[@]}" "${internal_include_arg[@]}" \
  -DMORPHOIA_TEST_SOURCE_DIR="\"${repo_dir}\"" \
  "${repo_dir}/cpp/src/core/sha256.cpp" \
  "${repo_dir}/cpp/src/core/canonical_json.cpp" \
  "${repo_dir}/tests/native/canonical_json_test.cpp" \
  -o "${fallback_dir}/canonical_json_test"
"${fallback_dir}/canonical_json_test"

if [[ "$(uname -s)" == "Linux" ]]; then
  "${cxx}" -std=c++20 "${common_warnings[@]}" "${internal_include_arg[@]}" \
    "${repo_dir}/cpp/src/core/sha256.cpp" \
    "${repo_dir}/cpp/src/core/posix_cas.cpp" \
    "${repo_dir}/tests/native/posix_cas_test.cpp" \
    -pthread \
    -o "${fallback_dir}/posix_cas_test"
  "${fallback_dir}/posix_cas_test"
else
  echo "posix_cas_test: NOT_RUN (Linux atomic no-clobber backend only)"
fi
echo "bootstrap-engine: PASS (shared C ABI direct compiler fallback)"
