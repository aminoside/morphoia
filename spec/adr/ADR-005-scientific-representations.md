# ADR-005: Reuse VTK, ITK, and PDAL for scientific representations

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

Scientific 3D workflows include meshes and fields, medical voxels and DICOM,
and georeferenced point clouds. One replacement container or library would lose
domain semantics.

## Options considered

1. Implement all readers, data structures, and filters in the core.
2. Convert everything to a triangle mesh or generic tensor.
3. Use mature domain libraries behind Morphoia contracts while preserving each
   authoritative representation.

## Decision

Prefer direct, optional adapters around VTK for mesh/field/headless output, ITK
plus a qualified DICOM stack for medical images, and PDAL for LAS/LAZ/COPC.
DICOM remains authoritative, including UIDs, Frame of Reference, per-frame
metadata, and relationships. CRS, precision, attributes, units, supports, and
time semantics remain explicit for points and fields.

## Evidence and constraints

This architectural acceptance does not validate a concrete library version.
None of VTK, ITK, or PDAL was observed during E0; runtime evidence is `NOT_RUN`.

## Consequences and risks

Adapters leverage mature ecosystems and keep the core focused. Transitive
codecs, version skew, conversions, and medical metadata handling create license,
security, and fidelity risks. Every fixture needs provenance, checksum, license,
classification, and a data card.

## Reversibility and review trigger

Each adapter is replaceable. Re-evaluate a library when a supported format or
invariant cannot be met, an exploitable dependency remains unresolved, or its
license/redistribution terms become incompatible with the delivered profile.
