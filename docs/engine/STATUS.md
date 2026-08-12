# Morphoia Engine status

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

As of: 2026-08-12
Phase: E2 — SALOME protocol contract, in parallel with E1 core foundations
Overall state: `IN_PROGRESS`
Branch: `engine-p0-salome-protocol`
E0 integration commit: `7715a7f7897a3058473732915e372b9835317d17`
E0 durable-state parent: `cdddaa47ba54742652819d798e1c6f9c0bd9ce6e`
Published E2 source checkpoint: `aec106f79e277b3cd3c6dabafe1107280f039aa9`

## Results

| Area | Status | Evidence or limitation |
|---|---|---|
| Repository identity | PASS | Public `Aminoside/morphoia`; default `main`; canonical remote `origin` verified during E0. |
| User work preservation | PASS | Pre-existing worktrees with unique MVX commits were observed and left untouched. |
| Bootstrap lot branch | PASS | `origin/engine-p0-bootstrap` was published and integrated through PR #4; source commit `66a3526f3ed5dd4263e16fbe333a4da41041f1fb` is the second parent of the merge. |
| E0 integration | PASS | PR #4 merged into `engine` at `7715a7f7897a3058473732915e372b9835317d17`, tree `1a2c31b55e284edd521616c3fec7a7f017b883eb`, with parents `fcee715a2d99517f00aacf7d8ce2797658194f83` and `66a3526f3ed5dd4263e16fbe333a4da41041f1fb`; no merge to the default branch occurred. |
| Branch protection | FAIL | Protection/ruleset inspection executed and found none; PR plus checks is the compensating workflow, not proof of protection. |
| Authenticated publication | PASS | The authenticated app published the checkpoint and exact remote tree; `gh` remains absent and local CLI push remains unauthenticated. |
| Hosted corrective checks | PASS | On corrective source SHA `8b41fa8435e5812b5bd10ae92e35878d9803e0bc`, Engine run `31581879387` passed Python 3.12, Python 3.13, source hygiene, native GCC/C++20, and REUSE; report run `31581879373` passed. Earlier runs `31578405786` and `31578405812` remain recorded as the failures that exposed the implicit `pdftotext` dependency. |
| Hosted integration checks | PASS | Engine push run `31582827407` passed on merge SHA `7715a7f7897a3058473732915e372b9835317d17`: native `94069646681`, Python 3.13 `94069646723`, hygiene `94069646761`, Python 3.12 `94069646822`, and REUSE `94069646871`. |
| Published E2 hosted checkpoint | FAIL | Engine run `31585426276` and report run `31585425822` failed on source `aec106f`; all 69 tests ran and 68 passed, with the sole failure being the stale checkpoint `spec` digest. Native, hygiene, and REUSE jobs passed. |
| E2 protocol contract | PASS | Nineteen local tests execute the versioned six-operation JSON/URI/hash contract, strict bounded transport, and explicitly named `FakeSalomeAgent`; this is contract evidence only. |
| E2 evidence profile | PASS | A separate 14-artifact manifest and deterministic CycloneDX 1.5 SBOM preserve the closed E0 manifest/SBOM byte-for-byte and fail closed on path, symlink/alias, hash, size, license, exact graph/provenance, source digest, exact test mapping, duplicate-key schema, lock, and truth-status mutations. Vulnerability analysis remains `NOT_RUN`. |
| Corrective E2 hosted checkpoint | NOT_RUN | The durable digest/evidence correction has not yet been published or executed by GitHub Actions. |
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
The retained gate report is `evidence/E0_GATE_REPORT.md`. E0 is `PASS` and
integrated into `engine`: PR #4 produced merge
`7715a7f7897a3058473732915e372b9835317d17`, followed by green Engine push run
`31582827407`. This operational E0 gate does not claim G1/P0 completion.
Branch protection and the R-021 public-language control remain `FAIL`; optional
runtimes remain `NOT_RUN`.

## E2 protocol-only checkpoint

The bounded protocol source at `aec106f` defines `ProbeCapabilities`, `Submit`,
`Observe`, `Cancel`, `Publish`, and `Health`, carrying only bounded JSON and
URI/size/SHA-256 metadata across the process boundary. `encode_control_json`
is deterministic control transport only: it is not RFC 8785, not Morphoia IR
canonicalization, and not suitable for signatures or content identity.

Local protocol, schema, evidence, manifest, SBOM, E0-immutability, and mutation
tests pass after durable reconciliation. The first hosted source checkpoint
remains `FAIL`, because its Python 3.12, Python 3.13, and report jobs each found
the same stale `spec` tree digest after otherwise running all 69 tests. The
corrective hosted execution remains `NOT_RUN` until the reconciled commit is
published. The exact run/job record is retained in
`evidence/E2_PROTOCOL_GATE_REPORT.md`.

No SALOME 9.16 process was started. The fake always declares
`agent_kind=fake`, `simulation=true`, an unavailable backend, and real SALOME
status `NOT_RUN`. SHAPER/GEOM, SMESH, MED/MEDCoupling, groups/fields, a real
greater-than-2-GiB transfer, differential fidelity, startup, and overhead all
remain `NOT_RUN`; this checkpoint does not satisfy the real SALOME portion of
E2 or G1/P0.

## Next action

Publish the reconciled E2 durable-state commit to
`engine-p0-salome-protocol`, verify Python 3.12/3.13, native, hygiene, REUSE,
and report jobs, and integrate PR #6 into `engine` only after the required
checks pass. Continue E1 independently; real SALOME 9.16 remains `NOT_RUN`.
