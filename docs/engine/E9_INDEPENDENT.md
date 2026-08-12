# E9-INDEPENDENT frozen slice

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Frozen at E0: 2026-08-12
Entry condition: E6 pre-MVX technical pre-release published
Maximum scope: the eight lots below; no automatic additions

This finite slice contains stabilization work that does not require MVX codec,
reconstruction semantics, golden vectors, scientific thresholds, GPUs, SALOME,
containers, Slurm, or EuroHPC. It runs after E6, in parallel with E7 where
useful. Finishing it does not satisfy G2-G5.

| Lot | Bounded deliverable | Local acceptance evidence |
|---|---|---|
| E9I-01 | C ABI v1-rc header review: layout/version/size rules, ownership, allocator, diagnostics, thread-safety matrix | GCC 13 compile/link/runtime conformance tests and ABI report |
| E9I-02 | Core failure-injection suite for CAS atomic writes, truncated manifests, stale locks, replay, and targeted recovery | Deterministic CPU tests with operation keys and hashed outputs |
| E9I-03 | Resource-bounded parser/input hardening for canonical JSON, URI/path handling, archives represented by synthetic cases, and extreme declared sizes | Sanitizer-enabled tests and time-bounded fuzz smoke; no real large corpus |
| E9I-04 | Reproducibility exercise from two fresh local source copies with isolated build/cache directories | Environment manifest, commands, binaries/artifact hashes, explained differences |
| E9I-05 | Local job-bundle restart and provenance conformance, including interrupted/replayed work | End-to-end local execution with atomic success marker and no duplicate effects |
| E9I-06 | Static Slurm bundle lint and hostile-parameter tests without claiming Slurm execution | Schema/shell/static checks; Slurm remains `NOT_RUN` |
| E9I-07 | SDK/package consumer test using only the open CPU profile: C consumer, Python wheel/sdist smoke, CLI install/uninstall in isolated environments | Build/install/run evidence and dependency/license inventory |
| E9I-08 | Release-evidence consolidation: SBOM comparison, license/notice completeness, threat-model delta, traceability coverage and handoff drill | Signed-off review report, hashes, recovery rehearsal, zero delivered Sev 1/2 |

## Constraints

- Each lot is one bounded branch or explicitly small atomic change.
- Resource limits remain those in `RESOURCE_BUDGET.yaml`; fuzzing is a short,
  cancellable smoke, not an open-ended campaign.
- Connectors to ParaView, Slicer, FreeCAD, PETSc, MFEM, SALOME, GPU runtimes, or
  actual HPC systems are excluded because their required runtimes were not
  observed in E0. Contract documents may already exist, but they cannot be
  validated as integrations in this slice.
- ARM64 and non-Linux reproducibility are excluded from local validation and
  remain `NOT_RUN` until matching runners are available without new spending.
- Corpus growth, JEPA training, MVX representation choices, and any scientific
  reconstruction claim are excluded.

## Completion and handoff

The slice completes only when all eight local deliverables meet their acceptance
evidence and are integrated into `engine`. Any external-profile result remains
visible as `BLOCKED` or `NOT_RUN`. If E6, E7, and this slice complete before a
validated MVX specification arrives, publish the bounded handoff and set the
project state to `WAITING_FOR_MVX_SPEC` without polling.
