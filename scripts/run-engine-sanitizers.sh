#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_dir="$(cd -- "${script_dir}/.." && pwd -P)"
cxx="${CXX:-g++}"
cc="${CC:-gcc}"

for compiler in "${cc}" "${cxx}"; do
  if ! command -v "${compiler}" >/dev/null 2>&1; then
    echo "engine-sanitizers: compiler not found: ${compiler}" >&2
    exit 127
  fi
done

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/morphoia-engine-sanitizers.XXXXXX")"
cleanup() {
  if [[ -n "${work_dir:-}" && -d "${work_dir}" ]]; then
    rm -rf -- "${work_dir}"
  fi
}
trap cleanup EXIT

warnings=(-Wall -Wextra -Wpedantic -Werror)
sanitizers=(
  -fsanitize=address,undefined
  -fno-sanitize-recover=all
  -fno-omit-frame-pointer
)
include_arg=(-I"${repo_dir}/cpp/include")

"${cxx}" -std=c++20 "${warnings[@]}" "${sanitizers[@]}" "${include_arg[@]}" \
  -c "${repo_dir}/cpp/src/engine.cpp" -o "${work_dir}/engine.o"
"${cc}" -std=c11 "${warnings[@]}" "${sanitizers[@]}" "${include_arg[@]}" \
  -c "${repo_dir}/tests/native/abi_c_smoke.c" -o "${work_dir}/abi_c_smoke.o"
"${cxx}" "${sanitizers[@]}" "${work_dir}/engine.o" "${work_dir}/abi_c_smoke.o" \
  -o "${work_dir}/abi_c_smoke"
"${cxx}" -std=c++20 "${warnings[@]}" "${sanitizers[@]}" "${include_arg[@]}" \
  -c "${repo_dir}/tests/native/core_smoke.cpp" -o "${work_dir}/core_smoke.o"
"${cxx}" "${sanitizers[@]}" "${work_dir}/engine.o" "${work_dir}/core_smoke.o" \
  -o "${work_dir}/core_smoke"

# This script exercises AddressSanitizer and UndefinedBehaviorSanitizer only.
# LeakSanitizer is explicitly disabled and must be reported separately.
ASAN_OPTIONS="detect_leaks=0" UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" \
  "${work_dir}/abi_c_smoke"
ASAN_OPTIONS="detect_leaks=0" UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" \
  "${work_dir}/core_smoke"
echo "engine-sanitizers: PASS (ASan+UBSan; LSan NOT_RUN)"
