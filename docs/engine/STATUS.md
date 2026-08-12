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
| Bootstrap lot branch | PASS | `origin/engine-p0-bootstrap` exists at the base commit. |
| Integration branch | PASS | `engine` was created from the verified default-branch base only after the native CPU smoke passed; lot integration remains pending PR checks. |
| Branch protection | NOT_RUN | No protection or ruleset was observed; PR plus checks is the compensating workflow, not proof of protection. |
| Authenticated publication | NOT_RUN | The authenticated app path is available and will be used after the local gate; `gh` is absent and local CLI push is unauthenticated. |
| Initial hosted-state audit | PASS | No Engine branch/tag/release existed; unrelated draft PR #3 was preserved; one existing report workflow with a green default-branch run was observed. |
| GitHub quotas and storage limits | NOT_RUN | Connector did not expose Actions, artifact, LFS, or API quotas; no paid resource is assumed or enabled. |
| Network capability | PASS | Restricted allowlisted egress and authenticated connector access were observed; unrestricted public egress was not probed or claimed. |
| Technical specification baseline | PASS | Expected SHA-256 recorded; 37 pages. Immutable repository copy is handled by the baseline lot. |
| Architecture baseline | PASS | Expected SHA-256 recorded; 39 pages. Immutable repository copy is handled by the baseline lot. |
| Official logo archive | PASS | Supplied archive matches the expected SHA-256. |
| Requirements catalogue integrity | PASS | Eight mutation/regeneration tests and the exact validator cover 320 requirements; immutable catalogue and fail-closed living tracking are separate. |
| Requirements JSON Schema validation | PASS | Draft 2020-12 schemas and instances passed with hash-locked `jsonschema` 4.25.1 on Python 3.12. |
| Unified Python tests | PASS | 40 tests executed with `PYTHONPATH=src` and the hash-locked E0 dependencies. |
| Existing CLI smoke | PASS | Help/smoke invocation executed successfully. |
| Native direct-compiler bootstrap | PASS | Two clean temporary GCC/G++ 13 shared-library builds passed C ABI/C++ runtime tests and an exact five-symbol export allow-list. |
| CMake/CTest minimum path | PASS | Hash-locked CMake 3.20.5 configured, built and ran two CTests; install plus external C `find_package` consumer also passed. |
| Sanitizers | PASS | Fail-fast ASan and UBSan smoke passed; LSan remains `NOT_RUN` and is not included in this claim. |
| Durable evidence/SBOM | PASS | Checkpoint/manifest validators and mutation tests pass; deterministic CycloneDX source/declaration inventory is hash-addressed. Vulnerability analysis remains `NOT_RUN`. |
| License metadata | PASS | Hash-locked REUSE 6.2.0 lint resolves copyright and license metadata for 159/159 files; dependency vulnerability analysis remains `NOT_RUN`. |
| Secret signature scan | PASS | Bounded fail-closed scan covered tracked and untracked text; binary baselines were separately hash/type/archive inspected. This is not a full secret/PII audit. |
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
The retained local gate report is `evidence/E0_GATE_REPORT.md`. E0
remains `IN_PROGRESS` only until the checkpoint is published, its remote SHA is
verified and lot-to-`engine` checks pass. Optional runtimes remain `NOT_RUN`.

## Next action

Publish the validated checkpoint on `engine-p0-bootstrap`, verify its remote
SHA and hosted checks, then integrate it to `engine` by PR without merging
`engine` into the default branch. Begin E1 and the protocol-only E2 work once
that integration is green.
