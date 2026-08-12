# ADR-012: Keep MEDCoupling in a separate dynamic LGPL package

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted under audit
- Date: 2026-08-12
- Baseline status: Accepted under audit

## Context

MED meshes, groups, fields, supports, Gauss points, and time steps are valuable
outside a full SALOME session. MEDCoupling/MEDLoader can provide direct access,
but its LGPL and transitive MED-file obligations must not be blurred into the
base core.

## Options considered

1. Copy or statically absorb MED code into the core.
2. Access MED only through full SALOME.
3. Provide an optional `morphoia-io-med` package with dynamic linkage and clear
   LGPL/source/notice compliance.

## Decision

Choose option 3, subject to a component-level license and redistribution audit.
The base distribution and ABI cannot require MEDCoupling. MED payloads and
semantics cross through versioned Morphoia contracts with explicit groups,
supports, units, components, and time metadata.

## Audit conditions

Resolve exact MEDCoupling, MEDLoader, MED-file, HDF5, and transitive versions,
sources, patches, linkage, notices, replacement/relinking rights, and SBOM.
No such runtime was observed in E0, so functionality is `NOT_RUN`.

## Consequences and risks

Direct MED access avoids launching SALOME for simple interchange while keeping
the base small. Dynamic linkage alone does not discharge LGPL obligations;
container or binary redistribution may require source/notice offers.

## Reversibility and review trigger

The package can be removed without changing the core. Reconsider if audit finds
an incompatible transitive component, or a measured alternative preserves the
required MED semantics with lower compliance and maintenance cost.
