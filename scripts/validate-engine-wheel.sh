#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

set -Eeuo pipefail

# The smoke is intentionally isolated from caller-controlled Python import roots.
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_dir="$(cd -- "${script_dir}/.." && pwd -P)"
build_python="${MORPHOIA_WHEEL_BUILD_PYTHON:-python3}"
runtime_template="${MORPHOIA_WHEEL_RUNTIME_VENV_TEMPLATE:-}"
library="${MORPHOIA_ENGINE_LIBRARY:-${repo_dir}/build/engine-cpu-debug/libmorphoia_engine.so}"

if [[ ! -f "${library}" ]]; then
  echo "validate-engine-wheel: native library is absent: ${library}" >&2
  exit 2
fi
library="$(cd -- "$(dirname -- "${library}")" && pwd -P)/$(basename -- "${library}")"

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/morphoia-engine-wheel.XXXXXX")"
cleanup() {
  if [[ -n "${work_dir:-}" && -d "${work_dir}" ]]; then
    rm -rf -- "${work_dir}"
  fi
}
trap cleanup EXIT

mkdir -p -- "${work_dir}/wheel" "${work_dir}/pip-cache" "${work_dir}/outside"
build_versions="$(
  "${build_python}" -c \
    'import setuptools, wheel; print(f"setuptools={setuptools.__version__} wheel={wheel.__version__}")'
)"
echo "validate-engine-wheel: observed local build backend ${build_versions}"

PIP_CACHE_DIR="${work_dir}/pip-cache" "${build_python}" -m pip wheel \
  --disable-pip-version-check --no-deps --no-build-isolation \
  --wheel-dir "${work_dir}/wheel" "${repo_dir}"
mapfile -t wheels < <(find "${work_dir}/wheel" -maxdepth 1 -type f -name 'morphoia-*.whl')
if [[ "${#wheels[@]}" -ne 1 ]]; then
  echo "validate-engine-wheel: expected exactly one built wheel" >&2
  exit 1
fi

if [[ -n "${runtime_template}" ]]; then
  if [[ ! -x "${runtime_template}/bin/python" ]]; then
    echo "validate-engine-wheel: runtime venv template is invalid" >&2
    exit 2
  fi
  cp -a -- "${runtime_template}" "${work_dir}/venv"
  echo "validate-engine-wheel: reused caller-supplied runtime venv template"
else
  "${build_python}" -m venv "${work_dir}/venv"
  PIP_CACHE_DIR="${work_dir}/pip-cache" "${work_dir}/venv/bin/python" -m pip install \
    --disable-pip-version-check --require-hashes --only-binary=:all: \
    -r "${repo_dir}/requirements/engine-ci.lock"
fi
PIP_CACHE_DIR="${work_dir}/pip-cache" "${work_dir}/venv/bin/python" -m pip install \
  --disable-pip-version-check --force-reinstall --no-deps "${wheels[0]}"

cp -- "${repo_dir}/tests/fixtures/engine-ir/0.1.0/inputs/graph-01-brep-source.json" \
  "${work_dir}/outside/manifest.json"
cp -- "${repo_dir}/tests/fixtures/engine-ir/0.1.0/replays/graph-01-brep-source.replay.json" \
  "${work_dir}/outside/replay.json"
cp -- "${repo_dir}/tests/fixtures/engine-ir/0.1.0/migration/legacy-input.json" \
  "${work_dir}/outside/legacy-input.json"
cp -- "${repo_dir}/tests/fixtures/engine-ir/0.1.0/migration/metadata.json" \
  "${work_dir}/outside/metadata.json"
chmod 0600 "${work_dir}/outside/"*.json
mkdir -m 0700 -- "${work_dir}/outside/workspace"

(
  cd -- "${work_dir}/outside"
  env -u PYTHONHOME -u PYTHONPATH "${work_dir}/venv/bin/python" - "${work_dir}/venv" <<'PY'
import sys
from pathlib import Path

import morphoia
from morphoia.engine_ir_contract import _resolve_schema
from morphoia.engine_ir_migration import _legacy_schema_path

prefix = Path(sys.argv[1]).resolve()
module = Path(morphoia.__file__).resolve()
if prefix not in module.parents:
    raise SystemExit(f"installed wheel smoke imported outside its venv: {module}")
for filename in (
    "morphoia-engine-ir-manifest-0.1.0.schema.json",
    "morphoia-engine-ir-replay-0.1.0.schema.json",
):
    schema = _resolve_schema(filename, None).resolve()
    if prefix not in schema.parents:
        raise SystemExit(f"installed wheel smoke resolved schema outside its venv: {schema}")
legacy = _legacy_schema_path().resolve()
if prefix not in legacy.parents:
    raise SystemExit(f"installed wheel smoke resolved legacy schema outside its venv: {legacy}")
print("installed_wheel_origin: PASS")
PY
  env -u PYTHONHOME -u PYTHONPATH "${work_dir}/venv/bin/python" -m morphoia \
    engine-ir validate manifest.json \
    --library "${library}" --json
  env -u PYTHONHOME -u PYTHONPATH "${work_dir}/venv/bin/python" -m morphoia \
    engine-ir replay replay.json \
    --manifest manifest.json --workspace workspace --library "${library}" --json
  env -u PYTHONHOME -u PYTHONPATH "${work_dir}/venv/bin/python" - "${library}" <<'PY'
import json
import sys
from pathlib import Path

from morphoia._engine_native import NativeEngine
from morphoia.engine_ir import migrate_legacy_manifest

legacy = Path("legacy-input.json").read_bytes()
metadata = json.loads(Path("metadata.json").read_text(encoding="utf-8"))
with NativeEngine(sys.argv[1]) as engine:
    result = migrate_legacy_manifest(legacy, metadata=metadata, engine=engine)
assert result.document["identity"]["digest"] == result.content_sha256
print("installed_wheel_migration: PASS")
PY
)

echo "validate-engine-wheel: PASS (isolated wheel install; build backend observed, not hash-locked)"
echo "validate-engine-wheel: distribution build reproducibility NOT_RUN"
