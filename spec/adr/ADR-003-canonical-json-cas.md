# ADR-003: Canonical JSON IR plus SHA-256 CAS

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Baseline status: Validate in P0

## Context

Morphoia must identify, replay, and inspect graphs while retaining large
specialized B-Rep, mesh, point, voxel, field, tensor, and future MVX payloads.
A single universal binary format would either discard semantics or reproduce
many mature formats.

## Options considered

1. Embed every payload in JSON.
2. Define one new universal binary container.
3. Use canonical JSON for versioned control metadata and URI/size/SHA-256
   references to specialized payloads in a CAS.

## Decision

Adopt option 3 subject to P0 validation. Canonicalization must define Unicode,
object ordering, numbers, non-finite values, units, URI normalization, and
schema versioning. Large bytes never enter control JSON. CAS consumers validate
schema, media type, declared size, and operational limits in addition to hash.

## Evidence required for acceptance

Twenty representative IR graphs must validate, canonicalize, hash, and replay
identically across two clean runs. Locale, float, ordering, duplicate-key,
migration, corrupt-blob, and atomic-write cases must pass. E0 has not produced
this evidence.

## Consequences and risks

Metadata remains auditable and diffs stay useful while payload formats retain
authority. Risks include false determinism from underspecified numbers/Unicode,
URI ambiguity, and treating byte integrity as safety.

## Reversibility and review trigger

Schemas and canonicalization are versioned. Reconsider the control encoding if
P0 cannot achieve cross-implementation deterministic hashes or measured JSON
overhead exceeds the documented control-plane budget. Payload formats remain
independent of that change.
