# Decision register

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Last updated: 2026-08-12

This register is an index. Normative rationale, consequences, and review
triggers are recorded in `spec/adr/`. An ADR cannot weaken a MUST in the
technical specification.

| ADR | Decision | Baseline status | Current status |
|---|---|---|---|
| [ADR-001](../../spec/adr/ADR-001-federated-platform.md) | Federated platform, not a monolithic engine | Accepted | Accepted |
| [ADR-002](../../spec/adr/ADR-002-cpp-c-abi-python.md) | C++20 internals, public C ABI, Python user API | Accepted | Accepted |
| [ADR-003](../../spec/adr/ADR-003-canonical-json-cas.md) | Canonical JSON IR plus CAS, no universal binary format | Validate in P0 | Proposed |
| [ADR-004](../../spec/adr/ADR-004-occt-step-ap242.md) | OCCT/XDE and STEP/AP242 open CAD boundary | Accepted | Accepted |
| [ADR-005](../../spec/adr/ADR-005-scientific-representations.md) | VTK, ITK, and PDAL for scientific representations | Accepted | Accepted |
| [ADR-006](../../spec/adr/ADR-006-kokkos-workers.md) | Kokkos CPU/CUDA/HIP workers; SYCL Tier 2 | Validate in P0 | Proposed |
| [ADR-007](../../spec/adr/ADR-007-ai-data-plane.md) | DLPack and Arrow C Data/Device AI data plane | Validate in P0 | Proposed |
| [ADR-008](../../spec/adr/ADR-008-vtk-first-rendering.md) | VTK-first rendering; optional Vulkan/ANARI/Hydra | Accepted | Accepted |
| [ADR-009](../../spec/adr/ADR-009-hpc-job-bundles.md) | HPC through Slurm/Spack/Apptainer/ADIOS2 job bundles | Validate in P0 | Proposed |
| [ADR-010](../../spec/adr/ADR-010-licensing.md) | Apache-2.0 OR MIT for original Engine code; no NC clause | Accepted under audit | Accepted under audit |
| [ADR-011](../../spec/adr/ADR-011-salome-isolation.md) | SALOME is optional backend/oracle, never a core dependency | Accepted | Accepted |
| [ADR-012](../../spec/adr/ADR-012-medcoupling-package.md) | MEDCoupling in a separate dynamic LGPL package | Accepted under audit | Accepted under audit |
| [ADR-013](../../spec/adr/ADR-013-salome-artifact-boundary.md) | STEP/XAO/MED boundary; CORBA internal to SALOME | Accepted | Accepted |
| [ADR-014](../../spec/adr/ADR-014-authoritative-dag.md) | Morphoia/Slurm DAG authoritative; YACS/JOBMANAGER hosts | Accepted | Accepted |
| [ADR-015](../../spec/adr/ADR-015-p0-p1-monorepo.md) | Permissive monorepo for P0-P1 foundation | Proposed by specification | Proposed |
| [ADR-016](../../spec/adr/ADR-016-independent-mvx-gate.md) | MVX gate independent from functional foundation | Proposed by specification | Proposed |
| [ADR-017](../../spec/adr/ADR-017-component-versioning.md) | Separate prototype, Engine, ABI and release versions | N/A | Accepted |
| [ADR-019](../../spec/adr/ADR-019-salome-control-protocol-v0.1.md) | Versioned bounded SALOME control protocol; explicitly fake agent is contract evidence only | N/A | Accepted for E2 contract profile |

## E0 operational decisions

- Use `origin` only because its URL was verified as the canonical repository;
  revalidate on every recovery.
- Work on `engine-p0-bootstrap`; do not advance `engine` before a green native
  CPU smoke test.
- With no observed branch protection, use PR review plus mandatory checks as a
  compensating workflow and retain the governance gap.
- Do not touch the existing worktrees containing unique MVX commits.
- Enforce the unexpanded resource limits in `RESOURCE_BUDGET.yaml`.
- Treat missing tools/runtimes as `NOT_RUN`, not product failure or success.

## E2 protocol operational decisions

- Keep the control plane to bounded deterministic JSON plus URI, byte size, and
  SHA-256 references. The encoder is not RFC 8785, canonical IR, a signing
  format, or a content identifier.
- Name the only test implementation `FakeSalomeAgent` and require every
  response to expose `agent_kind=fake`, `simulation=true`, backend unavailable,
  and real SALOME status `NOT_RUN`.
- Treat the 3 GiB schema vector as metadata-shape evidence only; it is not proof
  that a greater-than-2-GiB payload was created, transferred, or consumed.
- Preserve the closed E0 artifact manifest and E0 SBOM byte-for-byte. Later
  evidence belongs to a profile-specific E2 manifest and CycloneDX inventory,
  generated and checked from exact path, provenance, source-edge, published
  source-digest, requirement/test, lock, and license maps. The published source
  SHA is an implementation base; later evidence components are not attributed
  to that commit.
- Retain hosted Engine run `31585426276` and report run `31585425822` as
  `FAIL`. Their sole stale-digest failure motivates the durable correction but
  is not erased by later local success.
