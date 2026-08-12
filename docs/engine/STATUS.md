# Morphoia Engine status

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

As of: 2026-08-12
Phase: E1 — public IR 0.1 and 20-graph replay; E2 protocol-only lot integrated
Overall state: `IN_PROGRESS`
Work branch: `engine-p0-public-ir-replay`
E0 integration commit: `7715a7f7897a3058473732915e372b9835317d17`
E2 integration commit: `c84dd152a81b80a7e5c39e51f13b811a0f32d05f`
E1 native source commit: `bbf84cb806d95701daa2887e71d90a819c4a4c83`
E1 corrective evidence commit: `0e1f6cf45b7b4d0721fc9fb94cb9b1582b7e5b41`
Published E2 source checkpoint: `aec106f79e277b3cd3c6dabafe1107280f039aa9`
Corrective E2 source checkpoint: `e3ec245569bff40533b86789e61b1a78c15915f6`
Final E2 evidence checkpoint: `b3dfc084c81d9d64ff4079304a4e97b0cf75b294`
E1 evidence checkpoint: `4db5c7436a8139d227de58d5f5ff7280e8a0f9ea`
E1/E2 reconciliation commit: `5a96abfcb658e26d8e085a25f98b032002719967`
E1/E2 integration and public-IR base:
`12656708ccc3031670c4b3efd43996e46fa27998`

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
| E1 native source hosted attempt | FAIL | Engine run `31586603633` on `bbf84cb806d95701daa2887e71d90a819c4a4c83` failed overall: native `94081774268`, hygiene `94081774344`, and REUSE `94081774196` passed; Python 3.12 `94081774242` and Python 3.13 `94081774246` failed on stale E0-era evidence replay. Report run `31586603592`, job `94081774083`, reproduced the evidence failure. |
| E1 corrective hosted checks | PASS | On `0e1f6cf45b7b4d0721fc9fb94cb9b1582b7e5b41`, Engine run `31589901243` passed native `94092209890`, REUSE `94092209947`, Python 3.13 `94092210022`, hygiene `94092210038`, and Python 3.12 `94092210136`; report run `31589901212`, job `94092209098`, also passed. |
| E1 final evidence-head Engine checks | PASS | On `4db5c7436a8139d227de58d5f5ff7280e8a0f9ea`, Engine run `31590626838` passed native `94094507250`, Python 3.12 `94094507279`, REUSE `94094507286`, hygiene `94094507324`, and Python 3.13 `94094507349`. |
| E1 final evidence-head report | NOT_RUN | No report workflow run was observed for exact SHA `4db5c743`; the cause is not asserted and no report PASS is claimed. |
| Published E2 hosted checkpoint | FAIL | Engine run `31585426276` and report run `31585425822` failed on source `aec106f`; all 69 tests ran and 68 passed, with the sole failure being the stale checkpoint `spec` digest. Native, hygiene, and REUSE jobs passed. |
| E2 protocol contract | PASS | Nineteen local tests execute the versioned six-operation JSON/URI/hash contract, strict bounded transport, and explicitly named `FakeSalomeAgent`; this is contract evidence only. |
| E2 evidence profile | PASS | A separate 14-artifact manifest and deterministic CycloneDX 1.5 SBOM preserve the closed E0 manifest/SBOM byte-for-byte and fail closed on path, symlink/alias, hash, size, license, exact graph/provenance, source digest, exact test mapping, duplicate-key schema, lock, and truth-status mutations. Vulnerability analysis remains `NOT_RUN`. |
| Corrective E2 hosted checkpoint | PASS | On corrective source `e3ec245`, Engine run `31589424865` passed Python 3.12 job `94090702646`, hygiene job `94090702698`, native job `94090702707`, REUSE job `94090702764`, and Python 3.13 job `94090702766`; report run `31589424850`, job `94090702397`, passed. |
| Final E2 evidence checkpoint | PASS | On `b3dfc084`, Engine run `31590141763` passed REUSE `94092971527`, hygiene `94092971593`, native `94092971600`, Python 3.13 `94092971604`, and Python 3.12 `94092971670`; report run `31590141769`, job `94092971258`, passed. |
| E2 integration | PASS | PR #6 merged only into `engine` at `c84dd152`; exact-SHA push run `31590418194` passed native `94093829070`, Python 3.12 `94093829134`, Python 3.13 `94093829163`, hygiene `94093829169`, and REUSE `94093829190`. The default branch was unchanged. |
| Combined E1/E2 hosted reconciliation | PASS | The true two-parent merge `5a96abfc` has tree `bc7714b1`. PR Engine run `31593255255` passed Python 3.12 `94102764284`, REUSE `94102764304`, native `94102764307`, Python 3.13 `94102764368`, and hygiene `94102764390`; report run `31593255344`, job `94102764289`, passed. The duplicate branch-push Engine run `31593250364` also passed all five jobs. |
| E1/E2 integration into `engine` | PASS | PR #7 merged only into `engine` at `12656708ccc3031670c4b3efd43996e46fa27998`, tree `9c21bc6544ee41c084208412805e93dbd5a85e70`, with parents `c84dd152` and `4eacd006`; the default branch was unchanged. |
| E1/E2 post-merge hosted checks | PASS | Exact-merge Engine run `31593999716` passed native `94105119978`, Python 3.12 `94105119984`, REUSE `94105120004`, hygiene `94105120031`, and Python 3.13 `94105120081`. |
| Public-IR lot isolation and entry smoke | PASS | `engine-p0-public-ir-replay` was created from exact integration merge `12656708`; branch inspection was clean and the direct CPU bootstrap passed. This is entry evidence, not public-IR implementation evidence. |
| Public-IR entry checkpoint local validation | PASS | Frozen E0/E1 evidence, E2 SBOM, checkpoint, 320 requirements, 102/102 Python tests, report replay, native five-test bootstrap, Ruff on new Python, REUSE 194/194, secret scan, and whitespace checks passed. |
| Public-IR entry checkpoint publication | PASS | Checkpoint `a69d35b5` is published on `engine-p0-public-ir-replay`; PR #8 targets only `engine`. Engine run `31596165398` passed native `94112106988`, REUSE `94112107004`, Python 3.12 `94112107035`, hygiene `94112107044`, and Python 3.13 `94112107066`; report run `31596165378`, job `94112106640`, passed. |
| Public Engine IR 0.1 local contract | PASS | Draft 2020-12 schema validation, bounded SPDX syntax, semantic invariants, native Profile 1 canonicalization, required-native Python, CLI, and explicit migration passed on Linux x86-64/CPython 3.12.13. ADR-020 remains `Proposed` until the lot is published and integrated. |
| Public Engine IR 20-graph replay | PASS | Exactly 20 synthetic input/golden/replay graphs passed byte-identical native/Python canonicalization, two-workspace execution, and checkpoint resume; the 79-file corpus contains 13 declared invalid cases and no payload bytes. |
| Public-IR local native/build gate | PASS | The bounded lot passed 60/60 owned tests, exact seven-symbol ABI inspection, direct bootstrap, ASan/UBSan, two fresh CMake 3.20.5 build/install/CTest 7/7 plus consumer 1/1 runs, and an isolated installed-wheel smoke. LSan and reproducible wheel construction remain `NOT_RUN`. |
| Public-IR local evidence profile | PASS | The separate profile records 32 bounded `PASS` and 17 broader `NOT_RUN` requirements, 123 hash-verified artifacts, a 140-component CycloneDX inventory, 22/22 evidence/mutation tests, and REUSE 299/299. Vulnerability analysis remains `NOT_RUN`; the closed E0 tracking overlay is byte-exact. |
| Public-IR first implementation hosted attempt | FAIL | On exact source `5ee8cebc`, report run `31609319695`, job `94156289420`, passed. Push Engine run `31609314553` and PR Engine run `31609319697` passed native, hygiene, REUSE, full Python 3.12/3.13 tests, and the 60-test IR lot, but both Python jobs failed only in the wheel smoke because setuptools was absent from the job environment. The correction uses a separate hash-locked E1 wheel-build profile so the closed Engine test lock and frozen evidence remain unchanged. |
| Public-IR corrective publication and hosted validation | NOT_RUN | Implementation checkpoint `5ee8cebc` is published on PR #8 and its first hosted attempt remains `FAIL`. The separated-lock correction, corrective exact-head Engine/report checks, review, integration, and post-merge checks remain required. |
| Legacy prototype byte preservation | PASS | The five entry hashes in ADR-020 were recomputed and match; those files remain non-authoritative for Engine identity. |
| Initial hosted-state audit | PASS | No Engine branch/tag/release existed; unrelated draft PR #3 was preserved; one existing report workflow with a green default-branch run was observed. |
| GitHub quotas and storage limits | NOT_RUN | Connector did not expose Actions, artifact, LFS, or API quotas; no paid resource is assumed or enabled. |
| Network capability | PASS | Restricted allowlisted egress and authenticated connector access were observed; unrestricted public egress was not probed or claimed. |
| Technical specification baseline | PASS | Expected SHA-256 recorded; 37 pages. Immutable repository copy is handled by the baseline lot. |
| Architecture baseline | PASS | Expected SHA-256 recorded; 39 pages. Immutable repository copy is handled by the baseline lot. |
| Official logo archive | PASS | Supplied archive matches the expected SHA-256. |
| Requirements catalogue integrity | PASS | The exact validator covers 320 requirements; immutable catalogue and fail-closed living tracking are separate. A retained, hash-verified layout derivative supports deterministic replay without an implicit host package. |
| Requirements JSON Schema validation | PASS | Draft 2020-12 schemas and instances passed with hash-locked `jsonschema` 4.25.1 on Python 3.12. |
| E0 unified Python tests | PASS | 50 tests executed with `PYTHONPATH=src` and the hash-locked E0 dependencies. |
| E1 local unified Python tests | PASS | 62 tests executed with the same hash-locked dependency set, including 26 durable-evidence tests for frozen E0 and the separate fail-closed E1 profile. |
| Combined E1/E2 local validation | PASS | The reconciled tree executed 94/94 Python tests, five CTests, direct bootstrap, ASan/UBSan, installed C consumer, report rebuild, requirements replay, both evolving SBOM profiles, and bounded hygiene controls. |
| Existing CLI smoke | PASS | Help/smoke invocation executed successfully. |
| Native direct-compiler bootstrap | PASS | Two clean temporary GCC/G++ 13 shared-library builds passed C ABI/C++ runtime tests and an exact five-symbol export allow-list. |
| CMake/CTest minimum path | PASS | Hash-locked CMake 3.20.5 configured, built and ran two CTests; install plus external C `find_package` consumer also passed. |
| Sanitizers | PASS | Fail-fast ASan and UBSan smoke passed; LSan remains `NOT_RUN` and is not included in this claim. |
| E0 durable evidence/SBOM | PASS | The closed E0 generator, manifest, and CycloneDX output remain byte-exact and are checked as an immutable profile. Vulnerability analysis remains `NOT_RUN`. |
| E1 durable evidence/SBOM correction | PASS | A separate fail-closed three-artifact E1 manifest and CycloneDX native-core profile cover the evolving source; exact truth fields and paths, dirfd-only atomic writes, mutation, license-map, self-hash, path-confinement, E0-freeze, deterministic checks, and hosted corrective workflows pass. Vulnerability analysis remains `NOT_RUN`. |
| License metadata | PASS | Hash-locked REUSE 6.2.0 lint resolves copyright and license metadata for 299/299 files in the public-IR worktree; dependency vulnerability analysis remains `NOT_RUN`. |
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

## Active E1 bounded lot

The native internal core implements a constrained RFC-8785-compatible
canonical JSON profile, incremental SHA-256, deterministic CAS URIs, and atomic
verified Linux/POSIX storage. ADR-018 defines the exact numeric/Unicode domain
and crash-safe publication protocol. Its historical failed and corrective runs
remain recorded above. PR #7 integrated the verified E1 native and E2 protocol
foundations only into `engine` at `12656708`; exact-merge Engine run
`31593999716` passed all five jobs.

The current finite lot is `public-ir-0.1-and-20-graph-replay` on
`engine-p0-public-ir-replay`. ADR-020 proposes the distinct public Engine IR
0.1 identity domain, strict lexical/schema/semantic validation order,
reverse-DNS extensions, and a native C ABI limited to capability query and
canonicalization. Track A delivered schema, contract, migration, exactly 20
input/golden/replay graphs, and 13 invalid cases. Track B delivered the
seven-symbol native ABI, required-native Python binding, CLI, replay,
build/install consumer, sanitizer, and isolated-wheel coverage. Track C
delivered a separate fail-closed traceability/manifest/SBOM profile while
preserving the E0 overlay byte-exact. The bounded local contract and replay
profile is `PASS`; the implementation is published and its first hosted
Python 3.13 attempt remains `FAIL` only at the wheel smoke. Corrective hosted
checks, PR review, integration into `engine`, and post-merge verification
remain `NOT_RUN`, so the lot and E1 remain `IN_PROGRESS`.

The legacy prototype boundary was recomputed at lot entry:

| Path | SHA-256 |
|---|---|
| `schemas/morphoia-ir-0.1.schema.json` | `7bf9b3fbac2189516c30b15d3630ee2ff6bef5edeaae719942ce862b530ddc3e` |
| `src/morphoia/compiler.py` | `54535e93126fff0c1c2bd38df39be65a6d34e42c83dc6913a701584e5f3ed71f` |
| `src/morphoia/runtime.py` | `f6a0683ba80b02ff12b715ba2197f7d22f5b7a8e3f2e913c2db007fc1a69cfbb` |
| `src/morphoia/backends/json_backend.py` | `8336dadd5b9889c8039963c5cbe2d0df0eeffe38896d5a6e8d673b7c298399f3` |
| `schemas/morphoia-loss-register-0.1.schema.json` | `4d1a19eea8b7b64dcf3b559e42ba5833380e9701528e92771ec4ea8deb153329` |

Those bytes remain intentionally unchanged and non-authoritative for Engine
identity. Migration must be explicit and evidence-bearing.

## Integrated E2 protocol-only checkpoint

The bounded protocol source at `aec106f` defines `ProbeCapabilities`, `Submit`,
`Observe`, `Cancel`, `Publish`, and `Health`, carrying only bounded JSON and
URI/size/SHA-256 metadata across the process boundary. `encode_control_json`
is deterministic control transport only: it is not RFC 8785, not Morphoia IR
canonicalization, and not suitable for signatures or content identity.

Local protocol, schema, evidence, manifest, SBOM, E0-immutability, and mutation
tests pass after durable reconciliation. The first hosted source checkpoint
remains `FAIL`, because its Python 3.12, Python 3.13, and report jobs each found
the same stale `spec` tree digest after otherwise running all 69 tests. The
corrective source `e3ec245` then passed all five Engine jobs in run
`31589424865` and report job `94090702397` in run `31589424850`. The historical
failures remain `FAIL`; the exact run/job record is retained in
`evidence/E2_PROTOCOL_GATE_REPORT.md`.

Final evidence head `b3dfc084` then passed Engine run `31590141763` and report
run `31590141769`. PR #6 merged only into `engine` at `c84dd152`; the exact
merge-SHA push run `31590418194` passed all five jobs. This closes integration
of the contract-only lot without promoting any real SALOME capability.

No SALOME 9.16 process was started. The fake always declares
`agent_kind=fake`, `simulation=true`, an unavailable backend, and real SALOME
status `NOT_RUN`. SHAPER/GEOM, SMESH, MED/MEDCoupling, groups/fields, a real
greater-than-2-GiB transfer, differential fidelity, startup, and overhead all
remain `NOT_RUN`; this checkpoint does not satisfy the real SALOME portion of
E2 or G1/P0.

## Next action

Publish the separated-lock correction as one signed checkpoint on
`engine-p0-public-ir-replay`, update draft PR #8, and require exact-head native,
Python 3.12/3.13, hygiene, REUSE, and report workflows. Integrate PR #8 only
into `engine` after every required check and review is green, then verify the
exact merge SHA. Real SALOME 9.16, GPU backends, the real greater-than-2-GiB
transfer, and all MVX-specific criteria remain `NOT_RUN` or `BLOCKED` until
their named tests and prerequisites exist.
