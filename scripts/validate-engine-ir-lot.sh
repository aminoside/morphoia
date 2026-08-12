#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_dir="$(cd -- "${script_dir}/.." && pwd -P)"
build_dir="${MORPHOIA_ENGINE_IR_BUILD_DIR:-${repo_dir}/build/engine-cpu-debug}"
library="${MORPHOIA_ENGINE_LIBRARY:-${build_dir}/libmorphoia_engine.so}"
python="${PYTHON:-python3}"

if [[ ! -f "${library}" ]]; then
  echo "validate-engine-ir-lot: native library is absent: ${library}" >&2
  exit 2
fi

cd -- "${repo_dir}"
MORPHOIA_ENGINE_LIBRARY="${library}" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  "${python}" scripts/validate_engine_ir_corpus.py --library "${library}"
MORPHOIA_ENGINE_LIBRARY="${library}" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  "${python}" -m unittest \
    tests.test_engine_ir_contract \
    tests.test_engine_ir_migration \
    tests.test_engine_ir_native \
    tests.test_engine_ir_replay \
    tests.test_engine_ir_cli -v

echo "validate-engine-ir-lot: PASS (20 graphs, native/Python agreement, replay)"
