# E2 checkpoint — SALOME protocol contract only

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Date: 2026-08-12
Operational phase: E2 protocol-only work in parallel with E1
Lot branch: `engine-p0-salome-protocol`
Base commit: `cdddaa47ba54742652819d798e1c6f9c0bd9ce6e`
Published source commit: `aec106f79e277b3cd3c6dabafe1107280f039aa9`
Declared profile: `e2-salome-protocol-contract`

## Disposition

The versioned control contract, strict JSON transport helpers, and explicitly
named `FakeSalomeAgent` pass their local contract tests. This demonstrates the
software boundary only. It does not demonstrate a SALOME 9.16 runtime,
headless SHAPER/GEOM/SMESH execution, MED/MEDCoupling behavior, group or field
fidelity, a greater-than-2-GiB transfer, differential comparison, startup cost,
or bridge overhead. Every such real-runtime claim remains `NOT_RUN`.

The first published source checkpoint intentionally preceded durable digest
reconciliation. GitHub Actions therefore executed the new tests but failed the
two Python jobs and report job on the single stale `spec` tree digest in
`checkpoint.json`. Native, hygiene, and REUSE jobs passed. These failures are
retained below as executed `FAIL` evidence; they are not replaced by the later
local correction.

The corrective durable-state commit and its hosted checks are not yet
published or executed. Consequently this checkpoint is not approved for
integration into `engine`, and the real E2 SALOME sub-gate remains `NOT_RUN`.

## Contract artifacts

| Artifact | SHA-256 at published source `aec106f` | Scope |
|---|---|---|
| Protocol schema 0.1 | `8c20efe80430168151cb197bd27f45d86515f7ee05451a910ff92e32fe249963` | Closed Draft 2020-12 control messages for six operations. |
| ADR-019 | `7581e07695e567690df5ff61784acdfae33d8b3eb8a160cd68721da0fc82fda7` | Contract decision and evidence boundary. |
| Strict transport helpers | `c06b3f4187e0ad855cd5e25e90e79e864a5f9ca04804e7c32135fffdcdacb19e` | Bounded deterministic transport, explicitly not RFC 8785 or IR canonicalization. |
| Fake agent | `3e4ba847a3df3fcd5dcc1b405d2ebd82519d86e75458aa22bec5b8c791d01320` | Contract lifecycle only; `simulation=true`, backend unavailable, SALOME `NOT_RUN`. |
| Contract tests | `85065138701cb4d1da1adf02cd7fabe6b9973d7747ad4896204542a7856446b8` | Positive and negative schema, JSON, lifecycle, and truth tests. |

`encode_control_json` is only a stable bounded transport encoding. It is not
RFC 8785, is not the canonical Morphoia IR encoding, and must not be signed or
used as a content identity. URI syntax validation is not authorization to read
a resource; a real agent still needs an allow-listed resolver and byte-level
size/hash validation.

## Published hosted execution on `aec106f`

| Workflow/job | Result | Exact observation |
|---|---|---|
| Engine run `31585426276` | FAIL | Overall workflow failed. |
| Python 3.12 job `94078032322` | FAIL | All 69 tests ran; 68 passed and only `test_committed_checkpoint_passes_fail_closed_validator` failed because the recorded `spec` tree digest was stale. |
| Python 3.13 job `94078032333` | FAIL | Same 69-test execution and same single stale-digest failure. |
| Native job `94078032366` | PASS | Native GCC/C++20 workflow completed successfully. |
| Hygiene job `94078032264` | PASS | Secret signature and whitespace controls completed successfully. |
| REUSE job `94078032129` | PASS | Repository license metadata completed successfully. |
| Report run `31585425822`, job `94078030193` | FAIL | Report workflow reached the 69-test suite and failed on the same single stale `spec` digest. |

No hosted failure indicates a protocol assertion failure. This classification
does not turn the overall workflows into `PASS`; the three affected jobs and
both workflows remain recorded as `FAIL`.

## Local execution before durable reconciliation

| Command | Result | Boundary |
|---|---|---|
| `python -m unittest tests.test_salome_protocol tests.test_schemas -v` with hash-locked `jsonschema` 4.25.1 | PASS | 23/23 protocol and schema tests passed on Python 3.12.13. |
| `python -m unittest discover -s tests -v` before digest correction | FAIL | 69 tests ran; 68 passed, with only the expected stale committed checkpoint digest failure. |
| Ruff 0.16.1 on protocol and schema tests | PASS | Targeted lint passed. |
| Hash-locked REUSE 6.2.0 | PASS | All then-present repository files resolved. |
| `bash scripts/scan-secrets.sh` | PASS | Bounded signature scan only; not a complete PII/security audit. |
| Tracked and untracked `git diff --check` equivalents | PASS | No whitespace defects. |

Final post-reconciliation command counts and artifact hashes are recorded by
the durable checkpoint once the complete validation set passes.

## Local execution after durable reconciliation

| Command | Result | Boundary |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<hash-locked-jsonschema>:src python -m unittest discover -s tests -v` | PASS | 82/82 tests passed on Python 3.12.13, including 19 protocol tests and 12 E2 evidence tests. |
| `PATH=<hash-locked-report-tools>:$PATH PYTHONPATH=<hash-locked-jsonschema>:src make check` | PASS | Both generated reports and the same 82-test suite passed; immutable baseline PDFs remained excluded from generated-report policy. |
| `python scripts/extract_engine_requirements.py --check` | PASS | Frozen 320-requirement extraction, schemas, tracking, and retained layout remained reproducible. |
| `python scripts/validate_engine_checkpoint.py` | PASS | Current E2 branch/upstream, output hashes, and `cpp`, `spec`, and `docs/engine` tree digests matched. |
| `python scripts/generate_engine_sbom.py --check` | PASS | Closed E0 CycloneDX bytes remained deterministic and unchanged. |
| `python scripts/generate_engine_e2_sbom.py --check` | PASS | Separate 14-artifact E2 manifest and deterministic CycloneDX inventory matched. |
| Ruff 0.16.1 on changed Python files | PASS | No lint finding. |
| Hash-locked REUSE 6.2.0 | PASS | License metadata resolved for 175/175 current repository files. |
| `bash scripts/scan-secrets.sh` | PASS | Bounded signature scan passed; this is not a complete PII/security audit. |
| Tracked/untracked whitespace checks | PASS | No whitespace defect. |

These local results correct the durable-state defect but do not rewrite the
hosted history. The corrective hosted jobs remain `NOT_RUN` until the new
checkpoint is published.

## Evidence and supply-chain separation

The closed E0 manifest and E0 SBOM remain immutable:

| Closed E0 artifact | SHA-256 | Status |
|---|---|---|
| `artifacts/manifest.json` | `df017341a5bdbb43dacd8a39bcb0cc5037c2fc885e60cb568392f7c93f8a312d` | PASS — byte-identical |
| `artifacts/sbom/engine-e0-source-native.cdx.json` | `30db23e7e3fc1edacce0627386152d0246f909adf0ffbefc7b441926b583414b` | PASS — byte-identical |

E2 uses a separate fail-closed artifact manifest and CycloneDX inventory with
an exact source graph, provenance text, notes, source digests, test mapping,
lock, license, and path allowlist. Evidence JSON rejects duplicate keys. The
writer confines output through a non-symlink directory descriptor and rejects
path aliases, symlink parents, hard-link collisions, and target changes. The E2
SBOM records the published source as an implementation base rather than
claiming every later evidence file belongs to that commit. It records
vulnerability analysis as `NOT_RUN`, dependency locks as excluded/not shipped,
execution scope as `contract-only`, and the SALOME runtime as `NOT_RUN`.

## Profile truth table

| Profile/control | Status | Reason |
|---|---|---|
| E2 JSON/schema contract | PASS | Six operations, strict bounded JSON, immutable artifact references, and negative mutations executed locally. |
| Explicit fake lifecycle | PASS | Dispatch and idempotency executed; every response remains visibly fake and makes no artifact/runtime claim. |
| Published hosted checkpoint | FAIL | Engine and report workflows failed on the stale durable `spec` digest; corrective hosted execution is pending. |
| Corrective hosted checkpoint | NOT_RUN | The durable correction has not yet been published. |
| SALOME 9.16 `ProbeCapabilities` | NOT_RUN | Runtime absent. Fake capability shape is not detected-runtime evidence. |
| SHAPER/GEOM/SMESH/MED/MEDCoupling | NOT_RUN | No real SALOME runtime or domain library execution. |
| Greater-than-2-GiB transfer | NOT_RUN | A 3 GiB integer appears only in a small schema vector; no payload was created or transferred. |
| Differential fidelity and ParaVis | NOT_RUN | No real oracle execution. |
| Bridge startup/overhead | NOT_RUN | No real bridge process. |
| Vulnerability analysis | NOT_RUN | The CycloneDX inventory is not a vulnerability scan. |
| G1/P0 SALOME criterion | NOT_RUN | Contract evidence cannot satisfy the real SALOME criteria. |

## Next idempotent action

Publish the reconciled E2 durable-state commit to
`engine-p0-salome-protocol`, verify new Python 3.12/3.13, native, hygiene,
REUSE, and report jobs, and integrate PR #6 into `engine` only if every required
hosted check passes. Never promote the fake agent to real SALOME evidence.
