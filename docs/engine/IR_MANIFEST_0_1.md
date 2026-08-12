# Morphoia Engine IR manifest 0.1

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

This document describes the bounded public Engine IR identity domain defined by
[ADR-020](../../spec/adr/ADR-020-public-engine-ir-v0.1.md). It is an
interoperability, provenance, and evidence envelope. It is not a universal
geometry format, an in-memory object model, or an MVX specification.

## Frozen identifiers

| Property | Value |
|---|---|
| Manifest schema ID | `https://morphoia.org/schemas/engine/ir-manifest/0.1.0` |
| Replay schema ID | `https://morphoia.org/schemas/engine/ir-replay/0.1.0` |
| Manifest format | `morphoia.engine.ir-manifest` |
| Replay format | `morphoia.engine.ir-replay` |
| Format version | `0.1.0` |
| Manifest media type | `application/vnd.morphoia.ir-manifest.v0+json` |
| Canonical profile | `morphoia.canonical-json.profile1` |
| Content identity | lowercase `SHA-256(Profile1(content))` |
| Logical IDs | lowercase UUIDv7 |
| Local payload URI | `morphoia-cas://sha256/<lowercase-digest>` |

The legacy `morphoia.canonical-construction-graph` schema and Python serializer
remain a byte-preserved, non-authoritative prototype domain. Their historical
semantic hashes are never accepted as Engine content identities.

## Validation and identity

Consumers validate in this exact order:

1. the native bounded Profile 1 parser rejects malformed UTF-8, duplicate
   decoded keys, invalid surrogates, fractions/exponents, unsafe integers, and
   resource-limit violations;
2. Draft 2020-12 validates the closed manifest or replay shape;
3. semantic validation checks identifiers, references, units and frames,
   transforms, authority, provenance and derivation DAGs, timestamps, fidelity,
   repair, loss, security, and payload-reference invariants;
4. the native canonicalizer serializes only the `content` member;
5. SHA-256 of those canonical bytes must equal `identity.digest`.

Python's `load_json_strict`, `validate_manifest`, and `validate_replay` provide
strict decoding and contract checks. They deliberately do not canonicalize or
compute an authoritative identity. The reference Python public path requires
the native C ABI for step 4. Supplying the envelope digest to
`validate_manifest` verifies agreement with an already computed native result;
it is not a digest computation.

The published parser limits for this version are 1 MiB input, 256 KiB per
decoded string or key, 100,000 JSON values, and 64 nested containers. Object
keys are not counted as JSON values, matching the native parser.

## Manifest structure

The envelope contains only the frozen identifiers, a scoped identity object,
and `content`. Envelope metadata does not change content identity.

`content` separates:

- logical identity, revision, and parent content hashes;
- explicit unit declarations, frames, and declared-not-applied transforms;
- original source URI, SPDX license expression, rights holder, source tool,
  date, and immutable payload reference;
- assemblies, instances, names, colors, layers, and bounded properties;
- separately typed `brep`, `mesh`, `points`, `voxels`, `volume`, `field`,
  `scene`, `tensor`, and `opaque` representations;
- provenance events, tolerances, fidelity events, repairs, and losses;
- classification, sensitivity, access policy, signature declaration, and trust
  level;
- optional reverse-DNS extension namespaces.

Revision history is deliberately linear in format 0.1: revision 1 has no
parent, and every later revision has exactly one immediately preceding parent
with the same logical UUID. A future merge-history model requires a new
compatible contract decision; callers cannot encode an ambiguous merge by
adding parent records here.

The `opaque` representation is a typed boundary for bytes whose semantics are
not defined by this contract. It is not proof of MVX support. `mvx` is not an
accepted representation kind because no owner-validated MVX specification has
been received.

Every binary reference includes URI, lowercase SHA-256, byte size, and a
lowercase parameter-free media type. The URI digest and `sha256` must match.
The schema has no inline binary member. A valid CAS hash proves byte identity,
not safety; the consuming adapter must independently validate media, schema,
size, resolver, and resource limits.

## Units, frames, and fidelity limits

Units carry a UCUM-compatible code, an explicit SI dimension vector, and an
exact coefficient/scale factor. The current semantic validator proves that the
factor is positive and that references are consistent. It does not yet contain
a complete UCUM vocabulary able to prove that every code, dimension, and
factor agree. Therefore the broader MOR-IR-006 requirement remains partial and
must not be reported as fully satisfied by this lot.

Frames declare dimension, exact origin, a signed-permutation orthonormal basis,
handedness, matrix order, and unit. Transforms retain source and target frames,
an exact invertible affine homogeneous matrix, order, and
`declared-not-applied`. The homogeneous row is checked after interpreting the
declared storage order, and a source/target frame pair has at most one
transform. No transform, repair, unit conversion, or loss is applied
implicitly.

An AI-derived representation must be a revisable `candidate`, must reference a
parent representation, and can never replace source authority. This is an IR
authority invariant only; it does not execute an AI runtime.

## Provenance, repairs, losses, and signatures

Each representation has exactly one producing provenance event. An event's
`parents` are exactly the immediate producers of its input representations;
self-consumption, descendant consumption, causal cycles, missing/extra parent
edges, and a consumer starting before its producers end are rejected. Events record
activity, tool/version/commit, parameters, parent events, environment, seeds,
UTC RFC 3339 timestamps ending in `Z`, input representations, and output
representations. Event and representation graphs must be acyclic, and declared
derivation parents must appear among provenance inputs.

Fidelity events, repairs, and losses are separate explicit records. Empty
lists mean that no such event was declared; validators do not insert or infer
records. A caller must not interpret absence as proof that an external
conversion was lossless.

Fixtures use `signature.status=unsigned`. A document may structurally carry a
verified/invalid signature declaration, but `validate_manifest` rejects a
self-declared `verified` value unless a future public API supplies an external
cryptographic verification result. No signature algorithm is validated by
this bounded core-CPU lot. The same rule applies to `trust_level=verified`: it
cannot be established by the document that makes the claim.

`source.license_expression` is checked against the bounded SPDX 2.3 Annex D
grammar (list identifiers or nonempty `LicenseRef`, parentheses, `WITH`,
`AND`, and `OR`). `WITH` applies only to an ungrouped simple expression and a
list exception identifier. Expressions are single-line and use only ASCII
space or tab as whitespace. This rejects free-form prose and malformed custom
references but does not claim a complete lookup of the SPDX license and
exception registries; redistribution still requires the separate license
audit recorded by the evidence profile.

## Extensions

The core schema is closed. `extensions` accepts only reverse-DNS top-level keys
such as `org.example.feature`. Values are bounded Profile 1 JSON and may use
any internal key, including names also used by the core; the namespace prevents
those internal names from redefining core fields. Unknown extensions survive
load/validate/serialize round trips byte-semantically. Each extension still
needs its own schema, license, security, and capability review.

## Replay corpus

`tests/fixtures/engine-ir/0.1.0/index.json` freezes exactly 20 small synthetic,
CC BY 4.0 inputs. Each entry records the input, Profile 1 content golden, replay
recipe, and exact SHA-256 values. Golden files have no terminal line feed. The
corpus includes B-Rep, points, voxels, transforms, derived representations,
fields, scenes, tensors, an AI candidate branch, fidelity/loss, assemblies,
instances, unstable topology IDs, tolerances, explicit repair, multiple units
and frames, a provenance chain, an extension with core-homonym internal keys,
and a parent revision.

The replay recipe fixes the five operations `validate-lexical`,
`validate-schema`, `validate-semantic`, `canonicalize-content`, and
`verify-identity` in that order. `determinism.expected_runs` requires at least
two runs. The schema validates a recipe; a PASS claim additionally requires
executing it through the native canonicalizer and comparing the committed
goldens.

The adjacent invalid corpus covers lexical, schema, and semantic rejection.
The migration fixture demonstrates the explicit legacy boundary. The data card
records provenance, classification, license, and limitations.

## Explicit legacy migration

`build_legacy_migration_content` accepts immutable legacy JSON bytes plus a
closed metadata object and returns only an unsealed Engine `content` object. It
verifies the legacy payload hash/size/CAS URI, supports bounded exact legacy
decimal values, maps only model names and IDs, retains the complete legacy JSON
as an opaque source representation, and declares four losses:

- the historical and Engine identity domains differ;
- construction history remains only in the opaque source payload;
- the legacy execution contract is not reinterpreted as Engine runtime
  behavior;
- only selected legacy product metadata becomes structured Engine records.

It never edits the input, computes an Engine identity, or returns a sealed
manifest. The final public migration path must use the native Profile 1 ABI to
canonicalize the returned content, construct the envelope with that native
digest, and validate the complete manifest. A syntactically valid caller
digest is never self-attested.

## Current limitations

- A full UCUM code-to-dimension/factor evaluator is not implemented.
- Cryptographic signature verification is `NOT_RUN`.
- MVX type/codec/reconstruction is `NOT_RUN`; `opaque` is not MVX evidence.
- Payload media validation, remote CAS, garbage collection, resume, and the
  resource-gated greater-than-2-GiB case are outside this lot.
- Schema/semantic validation does not make referenced bytes safe or available.
