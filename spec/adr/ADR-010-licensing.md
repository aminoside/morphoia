# ADR-010: Permissive original code with no noncommercial clause

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted under audit
- Date: 2026-08-12
- Baseline status: Accepted under audit

## Context

The owner's intended use is open and noncommercial, but an NC restriction would
not meet the Open Source Definition. The existing repository carries an MIT
license, while the owner authorizes new original Engine code under
Apache-2.0 OR MIT and new original documentation under CC BY 4.0.

## Options considered

1. Add a noncommercial license restriction.
2. Use one copyleft license for the entire distribution.
3. Preserve existing rights, dual-license new original Engine code
   Apache-2.0 OR MIT, mark new original documentation CC BY 4.0, and audit every
   component separately.

## Decision

Choose option 3. Governance may describe noncommercial intent but cannot limit
license permissions. Do not relicense pre-existing or third-party material.
Preserve SPDX identifiers, notices, DCO provenance, SBOM, and dependency audit.

## Audit conditions

This ADR remains qualified until `LICENSE-APACHE`, `LICENSE-MIT`, NOTICE,
file-level identifiers, dependency licenses, and release SBOM agree. E0 does not
claim a complete redistribution audit.

## Consequences and risks

The CPU foundation remains permissive and reusable. Mixed licensing requires
careful file boundaries. Inconsistent license files or copied third-party code
could create ambiguity.

## Reversibility and review trigger

Licensing of existing contributions is not retroactively reversible without all
rights holders. Review before importing any strong-copyleft, source-available,
proprietary, codec, font, dataset, or binary component and before every release.
