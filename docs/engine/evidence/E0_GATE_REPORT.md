# E0 gate report — core CPU bootstrap

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Date: 2026-08-12
Operational phase: E0
Lot: `p0-bootstrap`
Branch under test: `engine-p0-bootstrap`
Base parent: `fcee715a2d99517f00aacf7d8ce2797658194f83`
Declared profile: Linux x86-64 core CPU

## Disposition

The local mandatory E0/core-CPU acceptance set is `PASS`. Publication, remote
SHA equality, and hosted GitHub checks are still `NOT_RUN` in this report and
must pass before the lot is integrated into `engine`. This report does not
claim E1, P0/G1, SALOME, GPU, HPC, vulnerability-scan, or MVX conformance.

## Frozen inputs

| Input | SHA-256 | Status |
|---|---|---|
| Technical specification v0.1 | `40cdb3288e7b1a38a557d1459147aed7ac1d5646aaa5d6ab09a287abc9b22263` | PASS |
| Architecture reference v0.2 | `8519bba50ab9a05d469780ec074588034714d83d24ef09404705d292bfa02368` | PASS |
| Official logo archive | `d9957fb70c18f2cdea37b7a036e3ddab6b05492d1a3ea978f5ea9f33313c00c5` | PASS |

The catalogue contains 320 unique requirement IDs: 305 MUST, 10 SHOULD, and
5 MAY. Its compact record digest is
`5e65c204e35ba98453669095ede587b2573d3a6f35d7841d16d26104794131ba`;
the complete immutable catalogue digest is
`b846a2f284ad0510b43ca6fdba8ad4fae7d1b40daf2f77305c8153e6a9de4072`.

## Execution environment

Ubuntu 24.04.3 LTS, Linux x86-64; 8 effective CPU cores; 20 GiB cgroup RAM;
54 GiB free disk at probe; GCC/G++ 13.3.0; Python 3.12.13; CMake 3.20.5 from
the hash-locked E0 validation lock. No SALOME 9.16, supported GPU device/runtime,
container runtime, Slurm, EuroHPC access, OCCT, VTK, ITK, PDAL, MED, Kokkos,
PETSc, or other target domain runtime was observed.

## Commands and observed results

| Command or check | Observed result | Evidence boundary |
|---|---|---|
| `MORPHOIA_BOOTSTRAP_FORCE_FALLBACK=1 ./scripts/bootstrap-engine.sh` (two isolated runs) | PASS | Shared C facade and C++ core executed; exact five-symbol C export allow-list passed. |
| CMake 3.20.5 `--preset ci-gcc`, build, and CTest | PASS | Strict shared build; 2/2 tests executed. |
| CMake install plus external `tests/native/consumer` configure/build/CTest | PASS | Installed package found externally; 1/1 C consumer test executed. |
| `./scripts/run-engine-sanitizers.sh` | PASS | ASan and fail-fast UBSan executed; LeakSanitizer is `NOT_RUN`. |
| `python scripts/extract_engine_requirements.py --check` | PASS | Exact PDF/source fragments, derived fields, schemas, distributions, and tracking invariants validated. |
| `PYTHONPATH=src <hash-locked-python> -m unittest discover -s tests -v` | PASS | 40 tests, including legacy, JSON Schema, requirements, immutable-PDF separation, manifest, committed-checkpoint, native-consumer inventory, and SBOM tests. |
| `PATH=<hash-locked-report-tools>:$PATH PYTHONPATH=src make check` | PASS | Both generated reports rebuilt and validated; immutable Engine baseline PDFs stayed byte-identical and outside the report manifest. |
| `python scripts/generate_engine_sbom.py --check` | PASS | Deterministic CycloneDX 1.5 source/declared-tool inventory; vulnerability analysis `NOT_RUN`. |
| `python scripts/validate_engine_checkpoint.py` | PASS | The committed-form checkpoint paths, hashes, statuses, and tree digests validate fail-closed. |
| Hash-locked REUSE 6.2.0 `lint` | PASS | 159/159 repository files carry resolved copyright and license metadata. |
| `bash scripts/scan-secrets.sh` | PASS | Bounded tracked/untracked text signature scan; not a complete secret or PII assessment. |
| `git diff --check` | PASS | No whitespace errors in the E0 change set. |

The sanitizer run did not execute leak detection because LeakSanitizer is not
reliable under the observed ptrace-constrained environment. No skip, mock,
compile-only result, or older result is promoted to `PASS`.

## Profile truth table

| Profile/control | Status | Reason |
|---|---|---|
| E0 core CPU bootstrap | PASS | Native ABI/runtime, CMake package/consumer, Python/schema, sanitizer, evidence, and license checks executed. |
| Branch protection | NOT_RUN | No repository protection/ruleset was observed; PR plus checks is only a compensating control. |
| Hosted Python 3.13 job | NOT_RUN | The hash set resolves for 3.13; execution awaits hosted CI. |
| Vulnerability analysis | NOT_RUN | No pinned vulnerability scanner was executed. |
| LeakSanitizer | NOT_RUN | Environment limitation; excluded from the sanitizer PASS. |
| SALOME 9.16 | NOT_RUN | Runtime absent. |
| CUDA/HIP/SYCL | NOT_RUN | Matching devices and runtimes absent. |
| Containers/Slurm/EuroHPC | NOT_RUN | Runtimes and external access absent. |
| OCCT/VTK/ITK/PDAL/MED/Kokkos/PETSc | NOT_RUN | Libraries absent. |
| MVX | BLOCKED | No owner-validated MVX specification was supplied; E0 does not require it. |

## Next idempotent action

Publish the exact validated tree to `engine-p0-bootstrap`, verify the remote
commit, run hosted checks, and integrate through a lot-to-`engine` pull request.
Never merge `engine` into the default branch under this authorization.
