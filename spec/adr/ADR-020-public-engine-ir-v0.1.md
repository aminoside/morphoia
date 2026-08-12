# ADR-020: Public Morphoia Engine IR manifest 0.1 identity domain

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Extends: [ADR-003](ADR-003-canonical-json-cas.md),
  [ADR-017](ADR-017-component-versioning.md), and
  [ADR-018](ADR-018-canonical-json-profile-posix-cas.md)

## Context

The repository contains a pre-Engine Python prototype IR schema and serializers.
Those bytes predate the Engine baselines and do not implement the constrained
canonical JSON Profile 1 accepted by ADR-018. Reinterpreting or silently
rewriting them would change existing identities and could make historical
prototype output appear authoritative under a contract it never implemented.

ADR-018 provides an internal canonicalizer and local CAS primitive, but it does
not define the public Engine IR envelope, public identity domain, replay
contract, migration boundary, or 20-graph evidence required by E1. A separate,
versioned public contract is therefore required before native, Python, and CLI
surfaces can exchange Engine IR reproducibly.

This decision is deliberately independent of MVX. No validated Morphoia MVX
specification has been received, so this ADR cannot define an MVX encoding,
model, quantization, reconstruction algorithm, metric threshold, or loss
policy.

## Options considered

1. Replace the legacy prototype schema and serializers in place, and treat
   their existing names as the Engine identity domain.
2. Define a public C object model for every IR node and make its in-memory
   representation the cross-language contract.
3. Preserve the legacy prototype byte-for-byte as a non-authoritative domain,
   introduce a distinct versioned Engine manifest and replay contract, and
   expose only canonicalization and capability discovery through the native C
   ABI.

## Decision

Choose option 3 for the bounded public-IR 0.1 lot. The contract constants are:

| Property | Value |
|---|---|
| JSON Schema `$id` | `https://morphoia.org/schemas/engine/ir-manifest/0.1.0` |
| Format identifier | `morphoia.engine.ir-manifest` |
| Format version | `0.1.0` |
| Media type | `application/vnd.morphoia.ir-manifest.v0+json` |
| Canonical profile | `morphoia.canonical-json.profile1` |
| Semantic identity | `SHA-256(canonical_profile_1(content))` |
| Logical identifier | lowercase UUIDv7 |
| Local immutable payload URI | `morphoia-cas://sha256/<digest>` |

The manifest envelope is versioned independently from the legacy prototype,
the C ABI, the Python package, and a future Morphoia release. Its semantic
identity is the lowercase hexadecimal SHA-256 digest of the Profile 1 canonical
bytes of its `content` member. Envelope metadata that is outside `content`
cannot silently alter that identity. A payload reference carries its URI, byte
size, media type, and digest; payload bytes never become a massive JSON value.

Logical identifiers use the lowercase textual UUIDv7 form. They support graph
references and provenance but are not content identities. A CAS URI uses only
the exact lowercase SHA-256 digest form accepted by ADR-018; consumers must
still enforce schema, type, size, resolver, and resource limits before reading
the referenced bytes.

### Validation order

Every accepted document passes three distinct stages in this order:

1. native lexical validation rejects malformed UTF-8, duplicate decoded keys,
   lone surrogates, disallowed numeric forms, and configured resource-limit
   violations before a generic object graph is trusted;
2. JSON Schema Draft 2020-12 validation checks the declared manifest or replay
   shape and rejects unknown structural fields;
3. semantic validation checks version/capability agreement, UUID and reference
   integrity, identity recomputation, units/frames/provenance/loss invariants,
   and derivation consistency applicable to the implemented schema.

A failure at any stage is a structured rejection. Repair, coercion, identifier
replacement, unit conversion, or loss insertion is never implicit.

For this initial contract, revision lineage is linear: revision 1 has no
parent, while every later revision has one parent for the same logical UUID at
the immediately preceding revision. Provenance parents are the exact immediate
producers of event inputs, including causal timestamp ordering. Transforms are
unique per frame pair and must be invertible affine homogeneous matrices after
interpreting their declared storage order. Neither a verified signature nor a
verified trust level may be self-attested by a manifest.
Source license expressions follow the bounded, single-line SPDX 2.3 Annex D
syntax; registry membership and license compatibility remain separate audits.

### Extensions and capability negotiation

The core schema is closed. An explicitly declared extension member may contain
only reverse-DNS keys controlled by its producer, such as
`org.example.feature`. An extension cannot redefine a core field, canonical
profile, identity rule, unit, frame, authority, provenance edge, or loss.
Capability discovery must report the exact format, version, media type,
canonical profile, validation limits, and supported extension keys rather than
assuming compatibility from a package version.

### Native and language boundaries

The C11 ABI gains only sized/versioned capability-query and canonicalization
surfaces with explicit buffers, resource limits, and structured diagnostics.
It does not expose an IR C object model, C++ class, allocator-owned graph, or
implementation pointer. Python and CLI orchestration use the same public JSON
bytes and native canonicalizer; they cannot substitute the legacy serializer
or an unverified pure-Python fallback when claiming Engine identity.

### Legacy prototype boundary

The following files are preserved byte-exact at the entry to this lot and
remain non-authoritative for Engine IR identity:

| Path | SHA-256 |
|---|---|
| `schemas/morphoia-ir-0.1.schema.json` | `7bf9b3fbac2189516c30b15d3630ee2ff6bef5edeaae719942ce862b530ddc3e` |
| `src/morphoia/compiler.py` | `54535e93126fff0c1c2bd38df39be65a6d34e42c83dc6913a701584e5f3ed71f` |
| `src/morphoia/runtime.py` | `f6a0683ba80b02ff12b715ba2197f7d22f5b7a8e3f2e913c2db007fc1a69cfbb` |
| `src/morphoia/backends/json_backend.py` | `8336dadd5b9889c8039963c5cbe2d0df0eeffe38896d5a6e8d673b7c298399f3` |
| `schemas/morphoia-loss-register-0.1.schema.json` | `4d1a19eea8b7b64dcf3b559e42ba5833380e9701528e92771ec4ea8deb153329` |

Migration is explicit input-to-output transformation with provenance and loss
reporting. It cannot overwrite legacy input, inherit its old semantic hash, or
claim losslessness without an executed comparison.

## Bounded implementation and evidence

The public-IR 0.1 lot is limited to the manifest/replay schemas, strict contract
and migration helpers, native capability/canonicalization ABI, reference
Python/CLI surfaces, and a frozen corpus of 20 small redistributable graphs with
canonical golden bytes and digests. Positive, invalid, migration, mutation,
native/Python agreement, deterministic replay, resource-bound, and export
allow-list tests are required.

This ADR remains `Proposed` until those checks execute successfully on the
declared core-CPU environment, durable evidence is generated, hosted checks
pass, and the lot is integrated into `engine`. Design review alone is not
`PASS`. Real SALOME, GPU backends, a greater-than-2-GiB object, remote CAS,
domain-format importers, and MVX remain outside this bounded evidence profile
and retain their existing `NOT_RUN` status.

## Consequences and risks

- Existing prototype consumers keep their exact bytes and names, while new
  Engine consumers receive an unambiguous identity domain.
- Cross-language identity depends on one native bounded canonicalizer instead
  of serializer defaults, at the cost of requiring the native library for an
  authoritative Python result.
- A closed core with reverse-DNS extensions keeps evolution explicit, but an
  extension still requires independent licensing, schema, and security review.
- UUIDv7 ordering is operational metadata only; treating it as byte authority
  would be an implementation defect.
- SHA-256 and a CAS URI establish byte identity, not safety or semantic
  validity. Every adapter remains responsible for content-specific validation.

## Reversibility and review triggers

The contract is versioned and can be superseded without reinterpreting existing
identities. Review this ADR before accepting it, before adding fractional JSON
numbers, before changing which members enter `content`, before installing a C
IR object model, before allowing a new URI resolver or remote CAS, after any
native/Python golden mismatch, or when a validated MVX specification requires a
different opaque representation boundary. Any identity-domain change requires
a new format version, frozen cross-version vectors, and an explicit migration;
published digests are never silently rewritten.
