# ADR-001: Use a federated platform, not a monolithic engine

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

CAD kernels, DICOM stacks, mesh/field tools, renderers, solvers, AI runtimes,
and HPC schedulers already exist and evolve independently. Reimplementing them
would expand scope, duplicate mature work, and make fidelity claims harder to
test.

## Options considered

1. Build one monolithic geometry, simulation, rendering, and AI engine.
2. Fork an existing platform such as SALOME and make it the product core.
3. Federate mature components through stable contracts and evidence.

## Decision

Morphoia is an open, headless federation layer for interoperability,
orchestration, provenance, and proof. It preserves multiple authoritative and
derived representations and delegates domain algorithms to qualified adapters
or isolated workers. It is not a new CAD kernel, general solver, AI framework,
or renderer.

## Evidence and constraints

The architecture and technical specification both select this boundary.
E0 has not executed domain adapters; acceptance is architectural, not a claim
that any adapter is already compatible.

## Consequences and risks

The core stays smaller, replaceable, and independently open-source. Integration
contracts, version negotiation, provenance, loss reporting, and differential
tests become first-class work. The principal risk is a lowest-common-denominator
IR; Morphoia mitigates it by retaining specialized payloads and authority rather
than flattening them.

## Reversibility and review trigger

Individual adapters are replaceable. Reconsider the federation boundary only
if two independent real user cases show that a mandatory capability cannot be
expressed without owning a domain kernel, with measured alternatives and an
approved scope change.
