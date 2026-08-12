# ADR-013: Exchange STEP, XAO, and MED artifacts with SALOME

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

In-process geometry objects and CORBA references bind identity and lifetime to a
specific SALOME/OCCT runtime and cannot form a durable, safe interoperability
boundary.

## Options considered

1. Share `TopoDS_Shape`, memory pointers, or CORBA objects across the boundary.
2. Treat SALOME `.hdf` studies as canonical Morphoia state.
3. Exchange open artifacts by URI, size, and SHA-256 using STEP, XAO, and MED;
   retain studies only as opaque external artifacts.

## Decision

Choose option 3. CORBA, when used, remains internal to the SALOME agent. Every
request and result identifies protocol/schema versions, media type, URI, size,
hash, units, dimensions, and provenance. `external_refs.salome` may refer to an
external study but never supplies canonical Morphoia identity.

## Evidence and constraints

The process boundary is accepted. Preservation of groups, fields, dimensions,
and large artifacts requires real E2/E5 execution and is currently `NOT_RUN`.

## Consequences and risks

Artifacts are restartable, auditable, and decoupled from process lifetime.
Serialization can cost time and may expose format limitations. Pool startup and
long-operation overhead must be measured separately; payload bytes never enter
control JSON.

## Reversibility and review trigger

Additional open transport formats may be added through capability negotiation.
Review when a required semantic cannot be represented by STEP/XAO/MED without a
declared loss, but do not replace the boundary with native pointers.
