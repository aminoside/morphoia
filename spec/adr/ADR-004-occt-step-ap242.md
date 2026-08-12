# ADR-004: OCCT/XDE with STEP/AP242 as the open CAD boundary

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

Morphoia needs an open CAD path that preserves exact B-Rep and assembly
semantics without claiming perfect access to proprietary authoring formats.

## Options considered

1. Implement a CAD kernel and importers.
2. Depend on proprietary native SDKs in the base profile.
3. Reuse OCCT/XDE and define a tested Morphoia STEP/AP242 profile.

## Decision

Use OCCT/XDE directly behind Morphoia contracts. STEP/AP242 is the general open
CAD exchange boundary. Retain original payload, units, placements, names,
colors, topology, tolerances, product structure, and declared authority; record
repairs, conversions, unsupported constructs, and losses. Proprietary SDKs, if
ever supported, are user-installed optional adapters.

## Evidence and constraints

The decision selects a component/boundary, not perfect round-trip fidelity.
OCCT was not observed in E0, so real import/export evidence is `NOT_RUN`.

## Consequences and risks

Morphoia reuses a mature open kernel and avoids vendor lock-in. STEP
implementations vary, AP242 is broad, and exporter-specific behavior can alter
semantics. Corpus-based invariants and differential tests are required rather
than marketing claims.

## Reversibility and review trigger

OCCT is isolated behind an adapter. Review the selected version/profile after a
reproducible fidelity failure on the frozen CAD corpus, a license/security
change, or evidence that another open implementation materially improves the
required invariants.
