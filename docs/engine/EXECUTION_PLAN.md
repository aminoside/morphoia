# Morphoia Engine execution plan

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Last updated: 2026-08-12
Owner: Dr Olivier Ami
Current operational phase: E0
Current lot: `p0-bootstrap`
Work branch: `engine-p0-bootstrap`
Integration branch: `engine` (created from the verified base after native smoke)
Canonical remote: `origin` (`https://github.com/aminoside/morphoia.git`)
Base commit: `fcee715a2d99517f00aacf7d8ce2797658194f83`

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
  `origin/engine-p0-bootstrap` is published; PR #4 targets `engine` and remains
  unmerged.
- The authenticated GitHub app identity `aminoside` was observed with
  administrative and push capability. No branch protection/ruleset was found.
  This is a governance gap, so lot-to-`engine` integration must use PR review
  and required checks as a compensating discipline.
- The `gh` executable is absent and a local command-line push is unauthenticated.
  The authenticated app publication path successfully published and verified
  the checkpoint tree; commit `95ba898d1dc3a1a35c15343b59f832808d850396`
  is the remote authority before the current corrective commit.
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
- Hosted runs `31578405786` and `31578405812` executed the first checkpoint.
  Native GCC, source hygiene, and REUSE jobs passed. Python 3.12, Python 3.13,
  and report replay failed because the hosted image has no `pdftotext`. This is
  an executed `FAIL`, not a skip. The correction retains and hashes the exact
  E0 layout extraction so ordinary offline replay needs no implicit system
  package; explicit `--extract-pdf` remains the provenance audit.

## Milestones

### E0 — audit, capability, and resumable bootstrap (hosted correction pending)

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
python3 scripts/generate_engine_sbom.py --check
python3 scripts/validate_engine_checkpoint.py
<hash-locked-python> -m reuse lint
bash scripts/scan-secrets.sh
git diff --check
```

All listed local commands passed for the first published checkpoint; the
compact report is retained in `docs/engine/evidence/E0_GATE_REPORT.md`. The
requirements lock was also resolved with Python 3.13 wheel/hash compatibility.
Hosted 3.13 then executed but failed solely at the missing-Poppler regeneration
test; the retained-layout correction must be replayed before its status can
become PASS. Source SBOM generation is independent
of the executing Python/compiler patch level. Vulnerability analysis, LSan and
the unavailable optional profiles remain `NOT_RUN`.

### E1 — core foundations and P0

Implement the modular build, C++20 core, C11 ABI, Python binding/CLI, IR/CAS,
units, frames, tolerances, provenance, loss register, diagnostics, capability
negotiation, and reproducible manifests. Validate two clean builds, ABI
lifetimes, 20 canonical IR graphs, CLI/Python behavior, deterministic hashes,
and absence of forbidden core dependencies.

Entry: E0 CPU bootstrap is green and integrated into `engine`.
Exit: all mandatory E1/core-cpu checks `PASS`; optional profiles remain
explicitly `NOT_RUN` or `BLOCKED`.

### E2 — SALOME P0 spike (parallel after minimal protocol)

Implement protocol and a clearly named fake contract agent. Execute real SALOME
9.16 headless tests only in a verified isolated runtime. Current environment has
no SALOME, so real `ProbeCapabilities`, SHAPER/GEOM, SMESH/MED, MEDCoupling, and
>2 GiB transfer results are `NOT_RUN`; mocks cannot change that status.

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

Validate and publish the deterministic retained-layout correction to
`engine-p0-bootstrap`, verify its remote SHA, rerun all PR #4 checks, and
integrate by PR into `engine` only when green. Start E1 and the protocol-only E2
lot after that integration; never merge `engine` into the default branch
without separate owner instruction.
