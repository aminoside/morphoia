# ADR-008: VTK-first headless rendering

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

The first release needs inspectable, automated previews and scientific output,
not a general-purpose interactive renderer or scene platform.

## Options considered

1. Build a new Vulkan renderer in the core.
2. Make OpenUSD/Hydra or a commercial renderer mandatory.
3. Use VTK/ParaView-compatible headless output first and add Vulkan, ANARI,
   Hydra, or OpenUSD only as justified adapters.

## Decision

Choose option 3. Rendering remains headless and optional to core semantics.
Visual outputs are derived artifacts with provenance, camera/configuration,
color mapping, and hashes; they never replace authoritative geometry or DICOM.

## Evidence and constraints

The baseline accepts this sequencing. VTK was not observed in E0, so no
headless rendering compatibility is yet proven.

## Consequences and risks

The vertical slice can reuse a mature scientific visualization stack and avoid
premature graphics architecture. Headless driver variability and nondeterministic
rasterization may limit byte-identical screenshots, so semantic and image
tolerances must be explicit.

## Reversibility and review trigger

Rendering is behind an adapter. Add or replace a backend only for a named user
need with measured gaps in VTK, an audited license, and a maintained CPU/offline
fallback where required.
