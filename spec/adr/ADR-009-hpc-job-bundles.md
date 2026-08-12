# ADR-009: Immutable HPC job bundles with local and Slurm execution

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Baseline status: Validate in P0

## Context

Scientific jobs must replay locally and on managed clusters while retaining
inputs, configuration, dependencies, seeds, provenance, checkpoints, and
outputs. Scheduler scripts alone are not a portable semantic record.

## Options considered

1. Encode orchestration directly in each cluster scheduler.
2. Make SALOME YACS/JOBMANAGER authoritative.
3. Define immutable Morphoia job bundles and DAGs, with a local executor and
   generated Slurm/Spack/Apptainer/ADIOS2 integrations.

## Decision

Adopt option 3 subject to P0 replay validation. Bundles are content-addressed,
schema-validated, restartable, and write outputs atomically. MPI and site policy
remain those of the target center. ADIOS2 is introduced only when checkpoint or
parallel-I/O evidence justifies it.

## Evidence required for acceptance

Generate and replay one bundle locally, inspect a generated Slurm bundle, and
verify interruption/restart without duplicate effects. Real Slurm, Apptainer,
and checkpoint execution are required for their own profile claims. E0 observed
none of these external tools.

## Consequences and risks

The semantic job record is portable and auditable. Site modules, filesystem,
MPI, container, and network policy remain environment-specific. Static syntax
checks must not be reported as cluster validation.

## Reversibility and review trigger

Executors are adapters around a versioned bundle. Review formats or tools after
a real center cannot express the required bundle semantics, or measured I/O and
restart behavior fails the declared gate.
