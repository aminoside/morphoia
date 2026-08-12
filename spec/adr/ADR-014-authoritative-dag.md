# ADR-014: Keep the Morphoia DAG and Slurm bundles authoritative

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

Morphoia needs reproducible orchestration independent of SALOME. YACS and
JOBMANAGER may host useful workflows but would otherwise make SALOME identifiers
and runtime semantics authoritative.

## Options considered

1. Make YACS/JOBMANAGER the canonical scheduler and workflow representation.
2. Implement unrelated orchestration separately for every backend.
3. Keep the versioned Morphoia DAG/job bundle canonical and treat
   YACS/JOBMANAGER as compatibility hosts for demonstrated user cases.

## Decision

Choose option 3. Morphoia owns operation identity, inputs, dependencies,
configuration, seeds, checkpoints, provenance, status, and output hashes. Slurm
bundles are generated views. YACS/JOBMANAGER adapters may translate the DAG but
must report losses and preserve a link to the authoritative bundle.

## Evidence and constraints

This authority boundary is accepted. Neither Slurm nor YACS/JOBMANAGER was
available in E0; runtime compatibility is `NOT_RUN`.

## Consequences and risks

Jobs remain portable and locally replayable. Translation may not preserve every
host feature, so round-trip loss reports are required. The project must resist
adding host-specific semantics to the core DAG without a portable definition.

## Reversibility and review trigger

Host adapters are replaceable. Reconsider the DAG schema after two real user
cases reveal the same missing portable semantic, supported by migration and
backward-compatibility evidence.
