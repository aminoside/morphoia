# E0 compliance matrix

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Snapshot: 2026-08-12
Declared profile: E0 audit/bootstrap on Linux x86-64 CPU

The complete 320-item catalogue is machine-readable in
`spec/requirements/requirements.yaml`. This E0 view records gate evidence; it
does not replace per-requirement links and does not assert G1-G5 completion.

| Control | Component/lot | Test or inspection | Evidence | Status |
|---|---|---|---|---|
| Correct public repository and default branch | E0 audit | remote/repository inspection | `STATUS.md` | PASS |
| Canonical remote verified | E0 audit | remote URL and permission inspection | `checkpoint.json` | PASS |
| User changes and worktrees preserved | E0 audit | worktree and ref inspection | `RISKS.md` R-012 | PASS |
| Bootstrap work isolated from default branch | E0 Git | branch/upstream inspection | `engine-p0-bootstrap` | PASS |
| Protected integration branch | Governance | ruleset/protection inspection | inspection executed; no protection observed | FAIL |
| Authenticated checkpoint publication | Publication | app publication and remote tree verification | checkpoint `95ba898d1dc3a1a35c15343b59f832808d850396` and PR #4 published | PASS |
| Hosted corrective checks | Publication | GitHub Actions runs `31578405786`, `31578405812` | first runs exposed missing `pdftotext`; retained-layout correction awaits rerun | FAIL |
| Initial branches/tags/PR/releases/workflows audit | Hosted-state audit | connector inspection | no Engine refs/releases; unrelated PR #3 preserved; existing report workflow observed | PASS |
| GitHub Actions/artifact/LFS/API quotas | Capability | quota inspection | connector did not expose limits; no paid capacity assumed | NOT_RUN |
| Network capability | Capability | environment policy and connector probe | restricted allowlist plus authenticated repository connector | PASS |
| Technical specification bytes | Baselines | SHA-256 plus PDF metadata | `BASELINES.md` | PASS |
| Architecture bytes | Baselines | SHA-256 plus PDF metadata | `BASELINES.md` | PASS |
| Official visual archive bytes | Baselines | SHA-256 | `BASELINES.md` | PASS |
| 320 requirements present and IDs unique | Requirements | Python standard-library structural smoke | 320 unique `MOR-*` IDs | PASS |
| Requirements catalogue conforms to its JSON Schema | Requirements | Draft 2020-12 validator | hash-locked `jsonschema` 4.25.1 on Python 3.12 | PASS |
| Requirement-to-component/test/evidence links complete | Traceability | catalogue/matrix inspection | mapping lot incomplete | NOT_RUN |
| Durable human-readable state | Governance | file inspection | plan, status, decisions, risks | PASS |
| Durable machine-readable state | Governance | fail-closed validators plus mutation tests | checkpoint, manifest and schemas | PASS |
| Resource limits recorded | Capability | probe-to-budget comparison | `RESOURCE_BUDGET.yaml` | PASS |
| Existing Python unit baseline | Existing prototype | targeted modules with `PYTHONPATH=src` | 14 tests executed | PASS |
| Existing CLI smoke | Existing prototype | CLI help/smoke | successful invocation | PASS |
| Native C++20 direct-compiler bootstrap | Engine core | `./scripts/bootstrap-engine.sh` fallback | ABI and core smoke executed with GCC/G++ 13 | PASS |
| Native CMake/CTest bootstrap | Engine core | CMake 3.20.5 configure/build/test | two CTests, install and external C consumer | PASS |
| Unified test discovery | Bootstrap | `PYTHONPATH=src <locked-python> -m unittest discover -s tests -v` | 50 tests | PASS |
| Immutable normative PDFs excluded from report branding | Baselines/reporting | tracked-report manifest test plus full `make check` | two Engine baseline PDFs remain hash-identical and outside generated-report policy | PASS |
| Second clean bootstrap | Reproducibility | two isolated direct GCC/G++ builds/tests | both executions passed | PASS |
| ASan/UBSan smoke | Security | fail-fast sanitizer script | two native executables | PASS |
| LeakSanitizer | Security | leak detection | deliberately disabled; environment limitation retained | NOT_RUN |
| Secret/sensitive-data scan of E0 diff | Security | bounded fail-closed text signature scan plus binary/hash inspection | no supported signature; not a full PII audit | PASS |
| E0 SBOM | Supply chain | deterministic CycloneDX generator/check | source, artifacts and hashed locks inventoried; vulnerability analysis NOT_RUN | PASS |
| Repository license metadata | Supply chain | hash-locked REUSE 6.2.0 lint | 161/161 files resolved; component vulnerability analysis NOT_RUN | PASS |
| Public English language policy | Documentation | repository-language inspection | root README and contribution guide are English; legacy Phase 1/2 guides/documents remain French under R-021 | FAIL |
| SALOME 9.16 headless | Optional SALOME | real runtime probe | runtime absent | NOT_RUN |
| CUDA, HIP, and SYCL execution | Optional compute | real hardware execution | hardware/runtime absent | NOT_RUN |
| Container and Slurm execution | Optional HPC | real runtime execution | tools absent | NOT_RUN |
| EuroHPC execution | Optional HPC | platform job evidence | access absent | NOT_RUN |

## Evidence interpretation

`FAIL` for branch protection means inspection executed and the required
condition was absent; compensating PR discipline is documented separately.
A mock, static generator, compiled object, or alternative backend cannot upgrade
an unavailable optional profile to `PASS`.

## E0 disposition

The local mandatory E0/core-CPU checks pass and the first checkpoint was
published with remote tree equality. Its hosted Python/report checks executed
and failed on an implicit `pdftotext` dependency. The gate stays operationally
open until the retained-layout correction is published and every corrective
check passes. Full per-requirement test/evidence mapping is a living E1+ task
and no G1-G5 contractual gate is claimed.
