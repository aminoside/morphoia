# Morphoia Engine execution plan

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Last updated: 2026-08-12
Owner: Dr Olivier Ami
Current operational phase: E1; E2 protocol-only lot integrated
Current lot: `canonical-json-cas-replay`
Work branch: `engine-p0-ir-cas`
Integration branch: `engine`
Canonical remote: `origin` (`https://github.com/aminoside/morphoia.git`)
E1 base commit: `cdddaa47ba54742652819d798e1c6f9c0bd9ce6e`
E1 native source commit: `bbf84cb806d95701daa2887e71d90a819c4a4c83`
E1 corrective evidence commit: `0e1f6cf45b7b4d0721fc9fb94cb9b1582b7e5b41`
Published E2 source checkpoint: `aec106f79e277b3cd3c6dabafe1107280f039aa9`
Corrective E2 source checkpoint: `e3ec245569bff40533b86789e61b1a78c15915f6`
Final E2 evidence checkpoint: `b3dfc084c81d9d64ff4079304a4e97b0cf75b294`
E2 integration commit: `c84dd152a81b80a7e5c39e51f13b811a0f32d05f`
E1 evidence checkpoint: `4db5c7436a8139d227de58d5f5ff7280e8a0f9ea`

## Objective

Deliver a reproducible, auditable, Linux x86-64 CPU vertical slice before MVX,
then complete only the finite independent stabilization slice. After an
owner-validated MVX specification arrives, incorporate it by change control and
execute E8. A pre-MVX release must not be described as G1/P0 complete.

## Sources and precedence

The immutable baselines and their verified identifiers are listed in
`BASELINES.md`. The technical specification v0.1 is normative for requirements,
evidence, gates, and deliverables. The architecture v0.2 explains choices.
Accepted ADRs may refine but not weaken a MUST. An explicitly validated MVX
specification has priority only within MVX.

## Scope and anti-scope

In scope: a modular C++20 core, versioned C ABI, Python/CLI, federated IR,
canonical JSON and CAS, provenance and loss reporting, CPU reference execution,
small redistributable STEP/DICOM/LAS paths, headless derived output, job bundles,
contract-level optional backends, tests, security, licensing, and evidence.

Out of scope for the core: a new CAD kernel, a general multiphysics solver, an
AI framework, a general renderer, proprietary-format fidelity promises, medical
or clinical claims, and any mandatory proprietary dependency. MVX encoding,
reconstruction, thresholds, and scientific claims remain suspended until a
validated specification is received.

## Observed E0 state

- Repository identity: public `Aminoside/morphoia`; default branch `main` at
  `fcee715a2d99517f00aacf7d8ce2797658194f83`.
- `origin` was validated as the canonical fetch/push URL. The remote `engine`
  branch did not exist initially and was created at the verified base.
  `origin/engine-p0-bootstrap` was published and PR #4 merged it into `engine`.
  The merge is `7715a7f7897a3058473732915e372b9835317d17`, with tree
  `1a2c31b55e284edd521616c3fec7a7f017b883eb` and parents
  `fcee715a2d99517f00aacf7d8ce2797658194f83` and
  `66a3526f3ed5dd4263e16fbe333a4da41041f1fb`.
- The authenticated GitHub app identity `aminoside` was observed with
  administrative and push capability. No branch protection/ruleset was found.
  This is a governance gap, so lot-to-`engine` integration must use PR review
  and required checks as a compensating discipline.
- The `gh` executable is absent and a local command-line push is unauthenticated.
  The authenticated app publication path successfully published and verified
  the checkpoint tree. The authoritative integration checkpoint is merge
  `7715a7f7897a3058473732915e372b9835317d17`; the current durable follow-up does
  not attempt to record the SHA of the commit that will contain itself.
- Initial hosted-state audit found no `engine`/`engine-p*` branch, tag, or
  release; one unrelated draft PR #3 (`agent/add-official-brand-assets` to
  `main`) was preserved; the only observed workflow was the existing report
  validator, whose latest default-branch run was green. GitHub Actions,
  artifacts, LFS, and API quota limits were not exposed by the connector and
  remain `NOT_RUN`, so no paid runner or storage assumption is made.
- Session egress is restricted to the declared allowlist. Repository reads and
  writes are available only through the authenticated connector; unrestricted
  public network access was not probed or assumed.
- Existing user worktrees containing unique MVX commits were detected and left
  untouched. They are not E0 inputs and must not be reconciled without a
  separate review.
- Capability probe: Ubuntu 24.04, x86-64, 8 effective CPUs, 20 GiB cgroup RAM,
  54 GiB free disk, GCC 13 with C++20/OpenMP, and Python 3.12. CMake, Ninja,
  pkg-config, GitHub CLI, SALOME, GPU runtimes/devices, container tools, Slurm,
  EuroHPC access, OCCT, VTK, ITK, PDAL, MED, Kokkos, PETSc, and other domain
  libraries were not observed.
- Existing Python baseline: 14 legacy tests and the CLI smoke `PASS`. With the
  hash-locked E0 dependencies, the combined 50-test Python/schema/evidence
  suite also passes on Python 3.12. Native direct and CMake 3.20.5 minimum paths,
  install/consumer, and fail-fast ASan/UBSan smoke pass. LSan remains `NOT_RUN`.
- Hosted runs `31578405786` and `31578405812` executed the first checkpoint and
  exposed the missing-`pdftotext` dependency. The corrective source SHA
  `8b41fa8435e5812b5bd10ae92e35878d9803e0bc` then passed all Engine jobs in run
  `31581879387` (Python 3.12/3.13, source hygiene, native GCC/C++20, and REUSE)
  and the report workflow in run `31581879373`. The correction retains and
  hashes the exact E0 layout extraction so ordinary offline replay needs no
  implicit system package; explicit `--extract-pdf` remains the provenance
  audit. The earlier failures remain historical executed results, not skips.
- PR #4 was merged into `engine` at
  `7715a7f7897a3058473732915e372b9835317d17`. Engine push run `31582827407`
  then passed native job `94069646681`, Python 3.13 job `94069646723`, hygiene
  job `94069646761`, Python 3.12 job `94069646822`, and REUSE job
  `94069646871`.
- The first E2 protocol source checkpoint was published at
  `aec106f79e277b3cd3c6dabafe1107280f039aa9` on
  `engine-p0-salome-protocol`, with draft PR #6 targeting `engine`. Engine run
  `31585426276` was overall `FAIL`: REUSE job `94078032129`, hygiene job
  `94078032264`, and native job `94078032366` passed; Python 3.12 job
  `94078032322` and Python 3.13 job `94078032333` failed. Report run
  `31585425822`, job `94078030193`, also failed. The logs show 69 tests ran,
  68 passed, and the sole failure was the stale checkpoint `spec` tree digest.
  This history remains `FAIL`; it is not reclassified because the protocol
  assertions themselves passed.
- Corrective source `e3ec245569bff40533b86789e61b1a78c15915f6` then passed
  Engine run `31589424865`: Python 3.12 job `94090702646`, hygiene job
  `94090702698`, native job `94090702707`, REUSE job `94090702764`, and Python
  3.13 job `94090702766`. Report run `31589424850`, job `94090702397`, also
  passed. This new execution proves the durable correction; it does not rewrite
  either historical failed workflow.
- Final E2 evidence source `b3dfc084c81d9d64ff4079304a4e97b0cf75b294`
  passed Engine run `31590141763` and report run `31590141769`. PR #6 then
  merged only into `engine` at `c84dd152a81b80a7e5c39e51f13b811a0f32d05f`;
  exact-merge-SHA Engine run `31590418194` passed all five jobs. This closes
  only the protocol-contract integration, not the real SALOME sub-gate.

## Milestones

### E0 — audit, capability, and resumable bootstrap (PASS, integrated)

Deliverables:

- immutable baseline copies, verified hashes, and redistribution notes;
- machine-readable catalogue of all 320 requirements and traceability matrix;
- repository/capability audit, resource budget, durable state, ADR-001..017;
- reproducible CPU bootstrap and minimal CI;
- first remote checkpoint on `engine-p0-bootstrap` before long development.

Acceptance:

1. correct repository/branches/remotes verified and user work preserved;
2. all three supplied baselines match expected SHA-256 digests;
3. 320 requirements parse and validate without lost IDs or evidence metadata;
4. state is readable in Markdown and JSON;
5. bootstrap and CPU smoke test pass, or a precise reproducible failure is
   checkpointed without advancing `engine`;
6. secret and sensitive-data checks show no introduced finding.

Executed local gate commands (using temporary environments for hash-locked
Python/CMake tools where shown):

```bash
MORPHOIA_BOOTSTRAP_FORCE_FALLBACK=1 ./scripts/bootstrap-engine.sh  # twice
cmake --preset ci-gcc && cmake --build --preset ci-gcc && ctest --preset ci-gcc
# cmake --install, then external tests/native/consumer configure/build/ctest
./scripts/run-engine-sanitizers.sh
PYTHONPATH=src python3 -m morphoia --help
PYTHONPATH=src <locked-python> -m unittest discover -s tests -v
python3 scripts/extract_engine_requirements.py --check
python3 scripts/validate_engine_checkpoint.py
<hash-locked-python> -m reuse lint
bash scripts/scan-secrets.sh
git diff --check
```

All listed local commands passed; the
compact report is retained in `docs/engine/evidence/E0_GATE_REPORT.md`. The
requirements lock and retained-layout path also passed on hosted Python 3.12
and 3.13 in corrective Engine run `31581879387`; report run `31581879373`
passed. PR #4 then integrated E0 at
`7715a7f7897a3058473732915e372b9835317d17`, and the resulting `engine` push
run `31582827407` passed all five jobs. Source SBOM generation is independent
of the executing Python/compiler patch level. Vulnerability analysis, LSan and
the unavailable optional profiles remain `NOT_RUN`. Branch-protection and
R-021 language-policy controls remain `FAIL` without changing E0 core-CPU PASS.

### E1 — core foundations and P0

Implement the modular build, C++20 core, C11 ABI, Python binding/CLI, IR/CAS,
units, frames, tolerances, provenance, loss register, diagnostics, capability
negotiation, and reproducible manifests. Validate two clean builds, ABI
lifetimes, 20 canonical IR graphs, CLI/Python behavior, deterministic hashes,
and absence of forbidden core dependencies.

Entry: E0 CPU bootstrap is green and integrated into `engine`.
Exit: all mandatory E1/core-cpu checks `PASS`; optional profiles remain
explicitly `NOT_RUN` or `BLOCKED`.

Current bounded lot: implement canonical JSON, SHA-256 CAS storage, immutable
URI/size/hash references, and deterministic replay manifests, with invalid
input, collision/integrity, idempotence, and golden-vector tests. Do not add
format adapters, GPU work, or MVX semantics to this lot.

The internal native sub-lot now has a constrained canonical JSON Profile 1,
incremental SHA-256, and an atomic Linux/POSIX CAS implementation under
ADR-018. This does not yet satisfy MOR-IR-002 on the public IR path: the legacy
Python `canonical_json` and `semantic_hash` functions preserve a pre-Engine,
non-JCS identity domain and are explicitly non-authoritative. The complete IR
schema, deterministic replay manifests, 20 graph corpus, green hosted results,
and integration evidence remain required before this bounded lot or E1 can
close.

The first hosted execution of source commit
`bbf84cb806d95701daa2887e71d90a819c4a4c83` is retained as a failed source
attempt. Engine run `31586603633` passed native job `94081774268`, hygiene job
`94081774344`, and REUSE job `94081774196`, but Python 3.12 job `94081774242`
and Python 3.13 job `94081774246` failed because the E1 tree was replayed
through closed-E0 source globs and stale E0 checkpoint digests. Report run
`31586603592`, job `94081774083`, reproduced the same evidence failures.
Those executed failures remain in the durable history.

Correction uses separate evidence profiles. The E0 generator, manifest, and
SBOM stay byte-exact and are validated by frozen hashes. A new fail-closed E1
manifest and CycloneDX profile own evolving E1 native source, exact license
mapping, and the bounded evidence report. The current validation commands are:

```bash
python3 scripts/validate_engine_e0_evidence.py
python3 scripts/generate_engine_e1_sbom.py --check
python3 scripts/generate_engine_e2_sbom.py --check
python3 scripts/validate_engine_checkpoint.py
PYTHONPATH=src <locked-python> -m unittest discover -s tests -v
```

The historical E0 regeneration command remains only in the closed E0 gate
report; it is not a valid current-tree check. On corrective evidence commit
`0e1f6cf45b7b4d0721fc9fb94cb9b1582b7e5b41`, Engine run `31589901243`
passed native job `94092209890`, REUSE job `94092209947`, Python 3.13 job
`94092210022`, hygiene job `94092210038`, and Python 3.12 job `94092210136`.
Report run `31589901212`, job `94092209098`, also passed. This proves the
corrective hosted profile only; public IR, 20-graph replay, greater-than-2-GiB
execution, future CAS capabilities, vulnerability analysis, and integration
remain `NOT_RUN`.

After semantically merging integrated E2 history, the combined local worktree
passed 94/94 Python tests, 5/5 native CTests, direct bootstrap, ASan/UBSan,
installation and the external C consumer, report replay, and REUSE 191/191.
The published two-parent reconciliation `5a96abfc` retained the exact local
tree `bc7714b1`. PR Engine run `31593255255` passed all five jobs and report run
`31593255344`, job `94102764289`, passed; branch-push Engine run `31593250364`
also passed all five jobs. This closes combined hosted reconciliation, not E1
integration or any unfinished public IR, real SALOME, large-transfer, GPU/HPC,
or vulnerability criterion.

### E2 — SALOME P0 spike (parallel after minimal protocol)

Implement protocol and a clearly named fake contract agent. Execute real SALOME
9.16 headless tests only in a verified isolated runtime. Current environment has
no SALOME, so real `ProbeCapabilities`, SHAPER/GEOM, SMESH/MED, MEDCoupling, and
>2 GiB transfer results are `NOT_RUN`; mocks cannot change that status.
Only the versioned JSON/URI/hash protocol, capability schema, explicitly named
fake agent, and contract tests may proceed in parallel with the current E1 lot.

Bounded protocol checkpoint results:

- protocol 0.1 defines six closed operations (`ProbeCapabilities`, `Submit`,
  `Observe`, `Cancel`, `Publish`, and `Health`) with URI/size/SHA-256 artifact
  references and bounded structured diagnostics;
- the strict loader/encoder rejects duplicate keys, non-finite values, unsafe
  integers, invalid UTF-8, lone surrogates, oversized messages, and non-object
  roots; its deterministic encoding is explicitly not RFC 8785 or canonical IR;
- `FakeSalomeAgent` is unambiguously simulated and cannot claim a real backend
  or publish a real SALOME artifact;
- a separate E2 artifact manifest, traceability profile, and CycloneDX inventory
  preserve the closed E0 manifest and E0 SBOM bytes exactly. The E2 generator
  is standard-library-only and bounded to explicit files, exact provenance and
  source edges, pinned published-source digests, exact requirement/test links,
  one hashed lock, and declared licenses. Strict evidence JSON and confined
  descriptor-relative output reject duplicate keys, symlink/alias escapes, and
  collisions; vulnerability analysis remains `NOT_RUN`;
- the first published hosted checkpoint remains `FAIL` because of its stale
  durable digest; corrective source `e3ec245` passed hosted Python 3.12/3.13,
  native, hygiene, REUSE, and report execution;
- real SALOME 9.16, SHAPER/GEOM, SMESH/MED, MEDCoupling, fidelity comparison,
  startup/overhead, and a real greater-than-2-GiB transfer remain `NOT_RUN`.

Acceptance for this contract-only lot is local protocol/schema/evidence tests,
deterministic manifest/SBOM validation, E0 evidence immutability, license and
secret controls, a green full locked suite, and then green required hosted
checks. Passing the lot never upgrades the real E2 SALOME sub-gate.

### E3 — vertical imports and fidelity

Implement and test STEP/AP242, synthetic DICOM authority graph, LAS/LAZ/COPC,
optional MED, and headless VTK paths by declared profile. Every conversion emits
provenance, repair, and loss information. Core-cpu release requires real small
redistributable fixtures, not format-name stubs.

### E4 — compute and AI interchange

Run one real CPU kernel and instrumented DLPack/PyTorch CPU exchange. Build
minimal Device/Buffer/Queue/Event/Fence capability contracts. CUDA, HIP, and
SYCL may be compiled or specified when possible but remain `NOT_RUN` until run
on matching hardware. Include allocation, copy, synchronization, and transfer
costs in every benchmark.

### E5 — optional SALOME/HPC industrialization

After a real positive SALOME spike, add the isolated bridge and differential
suite. Independently implement immutable local job bundles, local replay, Slurm
generation, and static packaging recipes. No EuroHPC platform may be called
validated from syntax inspection or local replay.

### E6 — functional pre-MVX technical pre-release

Freeze and execute the exact E6 checklist from the owner's instruction. Produce
a clone-to-demo path, SBOM, threat model, compliance matrix, checksums, evidence,
limitations, and an automated CPU end-to-end demonstration. Default candidate:
`engine-v0.0.1-alpha.1`. This milestone is operational and does not assert G1.

### E7 — MVX-ready contracts without MVX invention

Implement the versioned MVX SPI, opaque MIME/capability negotiation, generic
manifests and metrics, failure taxonomy, generic object-to-opaque-to-
reconstruction harness, and 10-30 synthetic-object contract corpus. Any test
adapter must be named `mock_mvx` or `null_mvx` and excluded from scientific
benchmarks and acceptance.

### E9-INDEPENDENT — finite post-E6 stabilization

Execute exactly the slice frozen in `E9_INDEPENDENT.md`. It contains only work
independent of MVX scientific definitions and locally verifiable on the
available CPU environment. Its completion does not satisfy external/GPU/HPC
criteria in G2-G5.

### WAITING_FOR_MVX_SPEC — required handoff state

If E6, E7, and the finite E9 slice finish without a validated MVX specification,
publish the pre-MVX handoff, list suspended decisions, set the machine state to
`WAITING_FOR_MVX_SPEC`, return control, and do not poll.

### E8 — validated MVX integration

On receipt of an explicitly validated specification: baseline and hash it,
create its requirements-to-evidence matrix, assess SPI deltas by ADR, implement
real codec/reconstruction/golden vectors, preregister corpus/metrics/thresholds,
run 30-50 pilot objects, then approximately 1,000 frozen objects only if the
pilot gate passes. Publish stratified metrics, uncertainty, failures, and costs.

## Contractual gates

G1-G5 remain governed by the technical specification. An operational phase can
advance while an optional profile is `BLOCKED` or `NOT_RUN`, but a contractual
gate requiring that profile remains unsatisfied. In particular, G1 cannot pass
without real CPU/CUDA/HIP execution, real SALOME headless evidence, groups and
large-artifact evidence, and the specified MVX micro-corpus.

## Decisions and known deviations

- ADR-001..014 retain the statuses in the architecture baseline; ADR-015 and
  ADR-016 remain proposed. ADR-017 accepts explicit component-version domains.
  ADR-018 accepts the bounded internal canonical JSON Profile 1 and Linux/POSIX
  CAS protocol without claiming completion of the public IR or all CAS MUSTs.
  ADR-019 accepts the bounded SALOME control contract and fake-evidence boundary.
- E2 evidence uses its own closed manifest and SBOM profile. The immutable E0
  manifest/SBOM are not regenerated to absorb later-phase files.
- E1 and E2 each use a separate manifest and SBOM profile and are regenerated
  only within their own scope. The immutable E0 manifest/SBOM stay byte-exact.
- Absence of branch protection is recorded, not treated as compliance.
- Missing build/domain tools are environment facts, not evidence that their
  integrations fail.
- Existing repository content predates this Engine bootstrap. It remains
  user-owned and must be migrated or connected deliberately rather than
  overwritten.

## Restart procedure

1. preserve unknown local changes and unique commits;
2. fetch `origin`, revalidate repository identity and authenticated publisher;
3. inspect `engine`, all `engine-p*` branches, open PRs, tags, and recovery refs;
4. read the durable files named in `AGENTS.md`;
5. verify baseline and manifest hashes;
6. reconcile without destructive reset;
7. execute the implemented bootstrap and smallest smoke test;
8. resume the `next_action` in `checkpoint.json` only if its inputs match.

## Current next action

Publish this bounded hosted-evidence follow-up on `engine-p0-ir-cas`, require
fresh exact-head Engine and report checks, verify that PR #7 has no unresolved
review thread, then integrate PR #7 into `engine` only. Verify the exact merge
SHA and post-merge Engine checks before opening the next public-IR lot. Keep real
SALOME 9.16 and the unfinished public IR criteria `NOT_RUN`; never merge
`engine` into the default branch without separate owner instruction.
