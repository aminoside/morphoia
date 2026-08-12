# ADR-015: Use a permissive monorepo for the P0-P1 foundation

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Baseline status: Proposed by the technical specification

## Context

P0-P1 changes span schemas, core ABI, adapters, bindings, CLI, tests,
documentation, and evidence. Early independent repositories would multiply
version coordination before boundaries are proven.

## Options considered

1. Create one repository per component immediately.
2. Keep foundation code, contracts, tests, and documentation in one permissive
   monorepo while packaging optional legal/runtime boundaries separately.
3. Vendor all external dependencies into the repository.

## Decision

Propose option 2 for P0-P1. The repository does not erase component boundaries:
SALOME remains out of process, MED remains a separate optional package, workers
are targeted, and third-party source is not vendored by default. Packages have
explicit dependency direction and can be extracted later with history.

## Evidence required for acceptance

The bootstrap must demonstrate modular builds, optional dependency isolation,
bounded CI, independent package manifests, and no forbidden linkage into the
core. That evidence is incomplete in E0.

## Consequences and risks

Atomic cross-layer changes and traceability are simpler. CI and checkout size
may grow, ownership can blur, and optional packages could accidentally become
mandatory.

## Reversibility and review trigger

Revisit after P1 or earlier when a package requires independent release cadence,
access control, incompatible licensing, or CI/resource isolation. Extraction
must preserve history, issues, provenance, and reproducibility.
