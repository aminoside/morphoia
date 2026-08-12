# ADR-019: Freeze the experimental SALOME control protocol 0.1 contract

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted implementation detail under ADR-011 and ADR-013

## Context

ADR-011 isolates SALOME 9.16 from the Morphoia core. ADR-013 limits the process
boundary to control metadata and immutable STEP, XAO, MED, or opaque HDF
artifact references. The technical baseline additionally requires a versioned
contract exposing `ProbeCapabilities`, `Submit`, `Observe`, `Cancel`, `Publish`,
and `Health` (MOR-SAL-015 through MOR-SAL-020).

The E0 capability probe did not find a SALOME runtime. A contract can still be
implemented and tested, but a fake must not be used as evidence of a headless
SALOME agent, detected modules, artifact conversion, large-artifact transport,
or differential fidelity.

## Options considered

1. Delay every protocol decision until a SALOME runtime becomes available.
2. Embed SALOME Python, KERNEL, CORBA, Qt/PyQt, or patched libraries in the
   Morphoia process and expose their native objects.
3. Freeze a narrow experimental JSON Schema 2020-12 contract now, test it with
   an explicitly named fake, and qualify the real runtime separately.

## Decision

Choose option 3 and publish protocol version `0.1.0` as
`morphoia-salome-protocol-0.1.schema.json`.

Every message carries a protocol version, message and request identifiers,
direction, one of the six normative operations, timestamp, and a strictly
typed operation body. Responses carry an explicit status and structured
diagnostics. Job lifecycle responses also carry attempt sequence, environment,
logs, state, and terminality.

Artifact bytes never enter the control document. Each input or output artifact
is represented by an allow-listed URI scheme, lowercase SHA-256 digest, byte
size, media type, and qualified metadata. Unknown fields and conventional
inline-payload fields are rejected; control strings, collections, parameters,
logs, and diagnostics are bounded. JSON decoding rejects duplicate keys,
invalid UTF-8, lone Unicode surrogates, `NaN`, infinity, and integers outside
the exactly interoperable JSON range from `-(2^53-1)` through `2^53-1`.

The helper `encode_control_json` provides a stable bounded transport encoding
for this protocol. It is not RFC 8785, is not Morphoia IR canonicalization, and
must never be used as signable bytes or a content identity.

`FakeSalomeAgent` is the only E2 implementation until a real runtime is
available. It has no SALOME dependency, uses the `fake-contract` execution
profile, returns `simulation=true` and `backend_available=false`, records the
SALOME evidence status as `NOT_RUN`, and never publishes a STEP, XAO, MED, or
HDF artifact. Its in-memory lifecycle exists only to test dispatch and
idempotency.

Protocol `0.1.x` changes may only add backward-compatible clarifications that
remain valid against the same schema. A field removal, changed meaning, or new
required field needs a new protocol minor or major version and an ADR review.

## Evidence and status boundaries

Schema validation and fake lifecycle tests are evidence for the software
contract only. They may support the structural portions of MOR-SAL-015,
MOR-SAL-017, and MOR-SAL-018. They do not establish real capability detection
(MOR-SAL-016), real publication (MOR-SAL-019), real attempt evidence
(MOR-SAL-020), SHAPER/GEOM/SMESH execution, headless runtime behavior, group or
field preservation, MED interoperability, the greater-than-2-GiB transfer
criterion, or bridge performance.

Those real-runtime items and the SALOME sub-gate remain `NOT_RUN`. A schema
vector that declares a large byte size is not a transferred artifact and is
never reported as such.

## Consequences and risks

The core and agent can evolve independently behind a deterministic,
language-neutral boundary, and invalid or oversized control documents fail
closed. The initial schema is deliberately narrower than a future remote gRPC
transport and does not select a service framework.

The principal risk is mistaking contract coverage for backend compatibility.
Public evidence must retain the fake/real distinction, named environment, and
five-status vocabulary. URI syntax validation also does not authorize access;
each runtime still needs an allow-listed resolver, size/hash verification, and
path-traversal controls before consuming bytes.

## Reversibility and review trigger

Review this ADR after the first real SALOME 9.16 `ProbeCapabilities` capture,
after three reasonable protocol-integration failures, or when a required
STEP/XAO/MED semantic cannot be represented without loss. Changes must preserve
ADR-011 isolation and ADR-013 artifact boundaries. Never resolve version skew
by sharing a SALOME pointer, CORBA object, or runtime library with the core.
