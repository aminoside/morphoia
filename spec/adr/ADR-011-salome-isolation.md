# ADR-011: Isolate SALOME as an optional backend and oracle

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

SALOME provides valuable SHAPER/GEOM, SMESH, MED, workflow, and job capabilities
but includes its own Python/runtime, KERNEL, CORBA, Qt/PyQt, SALOMEDS, and
patched-library ecosystem. Making it the core would constrain headless,
offline, ABI, packaging, and license goals.

## Options considered

1. Fork SALOME or embed its runtime in the core.
2. Omit SALOME entirely.
3. Use SALOME 9.16 as an isolated optional CAE backend and differential oracle
   from P0.

## Decision

Choose option 3. A versioned JSON/URI/hash protocol connects the core to a
separate SALOME agent. KERNEL, CORBA, Qt/PyQt, SALOMEDS, SALOME Python, and
patched libraries remain inside that runtime. The open CPU core builds and runs
without SALOME.

## Evidence and constraints

This boundary is accepted. Real SALOME behavior is `NOT_RUN` in E0 because the
runtime is absent. A fake agent validates only the protocol contract and must be
named accordingly.

## Consequences and risks

Morphoia can reuse SALOME and compare results without inheriting its runtime.
Startup, serialization, large-artifact transfer, version skew, and packaging
become explicit costs. Differential results do not make SALOME automatic truth.

## Reversibility and review trigger

If a real P0 spike fails structurally after three reasonable approaches,
downgrade SALOME to an external differential oracle by a new ADR. Never solve
the failure by importing SALOME dependencies into the core.
