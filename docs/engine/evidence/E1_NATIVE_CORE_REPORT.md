# E1 native canonical JSON and POSIX CAS evidence

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Date: 2026-08-12
Profile: Linux x86-64, GCC/G++ 13.3.0, C++20, core CPU
Native implementation source commit:
`bbf84cb806d95701daa2887e71d90a819c4a4c83`
Corrective evidence source commit executed by GitHub Actions:
`0e1f6cf45b7b4d0721fc9fb94cb9b1582b7e5b41`
Final evidence source commit executed by GitHub Actions:
`4db5c7436a8139d227de58d5f5ff7280e8a0f9ea`
Combined E1/E2 reconciliation commit executed by GitHub Actions:
`5a96abfcb658e26d8e085a25f98b032002719967`

## Result

The bounded internal native implementation of canonical JSON Profile 1,
incremental SHA-256, and the verified local POSIX CAS passed its native,
sanitizer, strict-warning, and adversarial tests. It adds no installed API and
does not change the five-symbol public C ABI.

The first hosted source attempt is `FAIL`, not `PASS`: later E1 source made the
closed E0 source-glob SBOM replay differ and also made the E0-era checkpoint
tree digests stale. These evidence-design failures did not fail the native job.
The corrective durable-state lot freezes E0 evidence byte for byte and gives E1
a separate manifest and SBOM profile. That correction subsequently passed the
hosted Engine and report workflows without rewriting the first result.

## Hosted source results

| Workflow or job | Status | Observation |
|---|---|---|
| Engine run `31586603633` | FAIL | Overall source run on `bbf84cb`; two Python evidence jobs failed. |
| REUSE job `94081774196` | PASS | License metadata validation executed successfully. |
| Native job `94081774268` | PASS | GCC/C++20 native build, tests, consumer, bootstrap, and sanitizers executed successfully. |
| Hygiene job `94081774344` | PASS | Secret-signature and whitespace checks executed successfully. |
| Python 3.12 job `94081774242` | FAIL | Closed-E0 SBOM regeneration and stale durable source digests disagreed with the E1 tree. |
| Python 3.13 job `94081774246` | FAIL | Same evidence-profile and checkpoint-digest failures as Python 3.12. |
| Report run `31586603592`, job `94081774083` | FAIL | The unified evidence suite reached and reproduced the same failures. |

No failed job is reclassified as skipped or passed.

## Hosted corrective results

| Workflow or job | Status | Observation |
|---|---|---|
| Engine run `31589901243` | PASS | All five jobs passed on corrective evidence source `0e1f6cf`. |
| Native job `94092209890` | PASS | GCC/C++20 native build and executed test path passed. |
| REUSE job `94092209947` | PASS | License metadata validation passed. |
| Python 3.13 job `94092210022` | PASS | Unified Python and phase-scoped evidence validation passed. |
| Hygiene job `94092210038` | PASS | Secret-signature and whitespace checks passed. |
| Python 3.12 job `94092210136` | PASS | Unified Python and phase-scoped evidence validation passed. |
| Report run `31589901212`, job `94092209098` | PASS | Report generation and the unified validation path passed. |

These results close the corrective hosted-check item only. They do not prove
the public IR path, the 20-graph corpus, greater-than-2-GiB execution, future
CAS capabilities, vulnerability analysis, or integration into `engine`.

## Hosted final evidence-head results

| Workflow or job | Status | Observation |
|---|---|---|
| Engine run `31590626838` | PASS | All five jobs passed on final E1 evidence head `4db5c743`. |
| Native job `94094507250` | PASS | GCC/C++20 native build and executed tests passed. |
| Python 3.12 job `94094507279` | PASS | Unified Python and phase-scoped evidence validation passed. |
| REUSE job `94094507286` | PASS | License metadata validation passed. |
| Hygiene job `94094507324` | PASS | Secret-signature and whitespace checks passed. |
| Python 3.13 job `94094507349` | PASS | Unified Python and phase-scoped evidence validation passed. |
| Report workflow | NOT_RUN | No report workflow run was observed for exact SHA `4db5c743`; the cause is not asserted. |

No report result is inferred from the green Engine run. The non-rewriting merge
of `engine` at `c84dd152` into this published E1 history must be reconciled and
then execute both combined workflows before integration.

## Combined local reconciliation

| Check | Status | Executed result |
|---|---|---|
| Unified Python suite | PASS | 94/94 tests passed with hash-locked dependencies. |
| CMake 3.20.5 build and CTest | PASS | 5/5 native tests passed; install and external C consumer passed; incompatible 0.1 consumer was rejected. |
| Direct bootstrap | PASS | ABI/core/SHA-256/canonical JSON/POSIX CAS tests passed. |
| ASan and fail-fast UBSan | PASS | All five native tests passed; LSan remains `NOT_RUN`. |
| Report replay | PASS | Both reports rebuilt and validated; the same 94-test suite passed. |
| REUSE 6.2.0 | PASS | License metadata resolved for 191/191 files. |

This local PASS proves the reconciled worktree. The following exact-head hosted
checks independently executed the published two-parent merge.

## Combined hosted reconciliation

| Workflow or job | Status | Observation |
|---|---|---|
| PR Engine run `31593255255` | PASS | All five required jobs passed on exact head `5a96abfc`. |
| Python 3.12 job `94102764284` | PASS | Unified Python and all three phase-scoped evidence checks passed. |
| REUSE job `94102764304` | PASS | License metadata validation passed. |
| Native job `94102764307` | PASS | GCC/C++20 build, five native tests, installed consumer, bootstrap, and sanitizers passed. |
| Python 3.13 job `94102764368` | PASS | Unified Python and all three phase-scoped evidence checks passed. |
| Hygiene job `94102764390` | PASS | Secret-signature and whitespace checks passed. |
| Report run `31593255344`, job `94102764289` | PASS | Both reports and the unified suite passed. |
| Branch-push Engine run `31593250364` | PASS | The duplicate exact-head push execution also passed all five jobs. |

These results close the combined hosted-reconciliation item. They do not prove
the public IR, 20-graph corpus, greater-than-2-GiB execution, real SALOME,
future CAS capabilities, vulnerability analysis, or integration into `engine`.

## Local executed evidence

| Check | Status | Executed result |
|---|---|---|
| Forced direct-compiler fallback | PASS | Five native tests passed; exact five-symbol export allow-list preserved. |
| Two clean CMake 3.20 release builds | PASS | Five of five CTests passed in each build; native binaries were byte-identical. |
| ASan and fail-fast UBSan | PASS | Five native tests passed under each executed sanitizer configuration. |
| Strict `-Wconversion`, `-Wsign-conversion`, and `-Wshadow` build | PASS | Native sources compiled and tests passed. |
| Install and external C consumer | PASS | Supported consumer built and ran; incompatible future-version consumer was rejected. |
| Adversarial native review | PASS | No remaining native publication blocker after fixes and re-execution. |

The CAS tests include expected size/digest ingestion, directory-descriptor
confinement, symlink/hardlink rejection, no-clobber concurrent publication,
existing-object revalidation, private verified read snapshots, mutation during
delivery, durable directory creation, temporary cleanup, and URI parsing.
Canonical JSON tests include exact golden bytes, UTF-16 key ordering, duplicate
decoded keys, malformed UTF-8, lone surrogates, unsafe integers, and resource
limits.

## Requirement truth for this bounded profile

| Requirement | Status | Scope and limitation |
|---|---|---|
| `MOR-CAS-001` | PASS | Executed internal Linux/POSIX profile publishes only SHA-256 identities. |
| `MOR-CAS-003` | PASS | Size and hash are verified before atomic no-clobber publication. |
| `MOR-CAS-004` | PASS | Bounded streaming read/write tests executed; verified reads use a private disk snapshot rather than whole-object memory. |
| `MOR-CAS-008` | PASS | Corruption is rejected before any bytes reach the consumer sink. |
| `MOR-CAS-002` | NOT_APPLICABLE | Optional BLAKE3 chunking is not implemented; no second public identity exists. |
| `MOR-IR-002` | NOT_RUN | Profile 1 is internal; the installed/public IR path and legacy Python serializer are not authoritative JCS yet. |
| `MOR-IR-005` | NOT_RUN | Internal reference construction and inverse URI parsing pass, but no public IR resolver contract is integrated. |
| `MOR-CAS-005` | NOT_RUN | No resource-approved object larger than 2 GiB was executed. |
| `MOR-CAS-006` | NOT_RUN | Only one local POSIX backend was executed; shared identity with a second backend is unproved. |
| `MOR-CAS-007` | NOT_RUN | Pin-aware garbage collection is not implemented. |
| `MOR-CAS-009` | NOT_RUN | Verified chunk resume and retransmission avoidance are not implemented. |
| `MOR-CAS-010` | NOT_RUN | No external-URI adapter is implemented; internal CAS URIs are never used as arbitrary paths. |
| `MOR-CAS-011` | NOT_RUN | Workspace quota, retention, pinning, and purge policy are not implemented. |
| `MOR-CAS-012` | NOT_RUN | The provenance transform path is not implemented. |

The 20-graph IR corpus, replay manifests, whole E1 gate, integration into
`engine`, and greater-than-2-GiB execution remain `NOT_RUN`.
The bounded lot and E1 therefore remain `IN_PROGRESS`.
