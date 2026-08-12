# Morphoia Engine status

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

As of: 2026-08-12
Phase: E0 — audit, capability, and resumable bootstrap
Overall state: `IN_PROGRESS`
Branch: `engine-p0-bootstrap`
Base: `fcee715a2d99517f00aacf7d8ce2797658194f83`

## Results

| Area | Status | Evidence or limitation |
|---|---|---|
| Repository identity | PASS | Public `Aminoside/morphoia`; default `main`; canonical remote `origin` verified during E0. |
| User work preservation | PASS | Pre-existing worktrees with unique MVX commits were observed and left untouched. |
| Bootstrap lot branch | PASS | `origin/engine-p0-bootstrap` is published; corrective source commit `8b41fa8435e5812b5bd10ae92e35878d9803e0bc` is the latest remotely verified checkpoint. |
| Integration branch | PASS | `engine` was created from the verified default-branch base only after the native CPU smoke passed; PR #4 targets it and remains unmerged. |
| Branch protection | FAIL | Protection/ruleset inspection executed and found none; PR plus checks is the compensating workflow, not proof of protection. |
| Authenticated publication | PASS | The authenticated app published the checkpoint and exact remote tree; `gh` remains absent and local CLI push remains unauthenticated. |
| Hosted corrective checks | PASS | On corrective source SHA `8b41fa8435e5812b5bd10ae92e35878d9803e0bc`, Engine run `31581879387` passed Python 3.12, Python 3.13, source hygiene, native GCC/C++20, and REUSE; report run `31581879373` passed. Earlier runs `31578405786` and `31578405812` remain recorded as the failures that exposed the implicit `pdftotext` dependency. |
| Initial hosted-state audit | PASS | No Engine branch/tag/release existed; unrelated draft PR #3 was preserved; one existing report workflow with a green default-branch run was observed. |
| GitHub quotas and storage limits | NOT_RUN | Connector did not expose Actions, artifact, LFS, or API quotas; no paid resource is assumed or enabled. |
| Network capability | PASS | Restricted allowlisted egress and authenticated connector access were observed; unrestricted public egress was not probed or claimed. |
| Technical specification baseline | PASS | Expected SHA-256 recorded; 37 pages. Immutable repository copy is handled by the baseline lot. |
| Architecture baseline | PASS | Expected SHA-256 recorded; 39 pages. Immutable repository copy is handled by the baseline lot. |
| Official logo archive | PASS | Supplied archive matches the expected SHA-256. |
| Requirements catalogue integrity | PASS | The exact validator covers 320 requirements; immutable catalogue and fail-closed living tracking are separate. A retained, hash-verified layout derivative supports deterministic replay without an implicit host package. |
| Requirements JSON Schema validation | PASS | Draft 2020-12 schemas and instances passed with hash-locked `jsonschema` 4.25.1 on Python 3.12. |
| Unified Python tests | PASS | 50 tests executed with `PYTHONPATH=src` and the hash-locked E0 dependencies. |
| Existing CLI smoke | PASS | Help/smoke invocation executed successfully. |
| Native direct-compiler bootstrap | PASS | Two clean temporary GCC/G++ 13 shared-library builds passed C ABI/C++ runtime tests and an exact five-symbol export allow-list. |
| CMake/CTest minimum path | PASS | Hash-locked CMake 3.20.5 configured, built and ran two CTests; install plus external C `find_package` consumer also passed. |
| Sanitizers | PASS | Fail-fast ASan and UBSan smoke passed; LSan remains `NOT_RUN` and is not included in this claim. |
| Durable evidence/SBOM | PASS | Checkpoint/manifest validators and mutation tests pass; deterministic CycloneDX source/declaration inventory is hash-addressed. Vulnerability analysis remains `NOT_RUN`. |
| License metadata | PASS | Hash-locked REUSE 6.2.0 lint resolves copyright and license metadata for 161/161 files; dependency vulnerability analysis remains `NOT_RUN`. |
| Secret signature scan | PASS | Bounded fail-closed scan covered tracked and untracked text; binary baselines were separately hash/type/archive inspected. This is not a full secret/PII audit. |
| Public language policy | FAIL | Engine code/governance material and contribution guidance are English, but the legacy Phase 1/2 README and developer guides remain French; R-021 records the bounded migration gap. |
| SALOME 9.16 | NOT_RUN | Runtime absent. |
| CUDA/HIP/SYCL execution | NOT_RUN | No compatible GPU/runtime/device observed. |
| Containers/Slurm/EuroHPC | NOT_RUN | Tools and external access absent. |
| OCCT/VTK/ITK/PDAL/MED/Kokkos/PETSc | NOT_RUN | Domain libraries were not observed. |

`IN_PROGRESS` is a project state, not an evidence status. Individual evidence
uses only PASS, FAIL, BLOCKED, NOT_RUN, or NOT_APPLICABLE.

## Environment

Ubuntu 24.04 x86-64; 8 effective CPUs; 20 GiB cgroup RAM; 54 GiB free disk;
GCC 13.3 with C++20 and OpenMP; Python 3.12.13. CMake 3.20.5 was installed
ephemerally from its hash-locked wheel for minimum-version validation. Ninja, pkg-config, GitHub CLI,
SALOME, GPU runtimes/devices, container/HPC tooling, and domain libraries were
not observed by the capability probe.

## Gate E0

The local E0 core-CPU acceptance set is satisfied: repository and work
preservation, baselines, 320-requirement extraction/tracking, two native
bootstraps, CMake 3.20 minimum path, external consumer, unified Python/schema
suite, ASan/UBSan, durable evidence, source SBOM, REUSE and bounded scans pass.
The retained local gate report is `evidence/E0_GATE_REPORT.md`. Corrective
source SHA `8b41fa8435e5812b5bd10ae92e35878d9803e0bc` passed the complete hosted
Engine and report workflows in runs `31581879387` and `31581879373`. E0 remains
`IN_PROGRESS` until this evidence-only follow-up is published, its own remote
SHA and required checks are verified, and PR #4 is integrated into `engine`.
Branch protection and the R-021 public-language control remain `FAIL`; optional
runtimes remain `NOT_RUN`.

## Next action

Publish this evidence-only follow-up on `engine-p0-bootstrap`, verify its remote
SHA and required checks, then integrate PR #4 into `engine` only when that
follow-up is green. Begin E1 and the protocol-only E2 work after integration.
