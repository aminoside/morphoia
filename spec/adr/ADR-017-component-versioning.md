# ADR-017: Separate Engine, prototype, ABI, and release versions

<!-- SPDX-FileCopyrightText: 2026 Olivier Ami -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Status: Accepted
Date: 2026-08-12
Owners: Morphoia Engine maintainers

## Context

The repository already contains an experimental Python construction-graph
prototype at `0.2.0.dev0`. The new native Engine bootstrap starts at component
version `0.0.1`, its C ABI uses integer version `1`, and the first planned
technical pre-release is `engine-v0.0.1-alpha.1`. Treating these values as one
version would make package, ABI, SBOM, and compatibility evidence ambiguous.

## Options

1. Renumber the pre-existing prototype and every Engine artifact immediately.
2. Use one repository-wide version despite different compatibility domains.
3. Keep explicit component versions and bind them in each release manifest.

The first option causes an unrelated migration before architectural alignment.
The second hides compatibility boundaries. The third preserves history and
makes every claim explicit.

## Decision

Use independent, named version domains until a future packaging ADR unifies
them:

- `prototype_package_version`: existing Python prototype version;
- `engine_component_version`: native Engine semantic version;
- `c_abi_version`: monotonically negotiated integer, independent of SemVer;
- `release_version`: immutable tag/pre-release identifier that records the
  exact component and ABI versions it contains;
- each IR, protocol, plugin SPI, and schema keeps its own declared version.

The E0 native component is `0.0.1` with C ABI `1`. This is a bootstrap version,
not the E6 release claim and not a frozen v1 SDK. SBOMs and manifests must name
the domain instead of exposing an unlabeled `version` field.

## Consequences and risks

Consumers must inspect a release manifest rather than infer ABI compatibility
from a Python package version. Documentation has more fields, but accidental
coupling is avoided. A release is invalid if two files give conflicting values
for the same named domain.

## Reversibility and review trigger

This decision is reversible through a migration that maps all domains and
provides compatibility metadata. Revisit before a unified wheel/SDK is
published, before C ABI v1 is frozen, or if the prototype becomes the reference
Engine Python binding.
