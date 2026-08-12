# ADR-018: Constrained canonical JSON and atomic Linux/POSIX CAS

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted for the bounded E1 internal-core lot
- Date: 2026-08-12
- Extends: [ADR-003](ADR-003-canonical-json-cas.md)

## Context

ADR-003 selected canonical JSON control metadata and SHA-256-addressed external
payloads, but deliberately left the numerical domain, Unicode handling, URI
form, and safe local publication protocol open for P0 validation. Those details
must be explicit before a hash can be treated as reproducible evidence.

The current release profile is Linux x86-64 CPU. The public native boundary
must remain the existing five-symbol C ABI while the internal C++ facilities
are exercised and hardened. This lot does not yet provide the complete IR
schema, 20-graph replay corpus, garbage collection, chunk resume, remote object
storage, or a resource-approved object larger than 2 GiB.

## Options considered

For JSON:

1. Delegate parsing, object ordering, and number formatting to a generic JSON
   library with its default serialization.
2. Implement every RFC 8785 input number using a binary64 parser and shortest
   round-trip formatter in the first internal lot.
3. Publish a versioned RFC 8785-compatible profile with an intentionally
   narrower exact-integer domain, strict Unicode validation, and fail-closed
   behavior for values outside that domain.

For local publication:

1. Write directly to the digest path and overwrite an existing entry.
2. Hard-link a temporary file into the digest path and unlink the temporary
   name afterwards.
3. Stage and synchronize a private file, then atomically rename it without
   replacement using Linux `renameat2(RENAME_NOREPLACE)`.

## Decision

Adopt option 3 in both groups for this bounded lot.

### Morphoia Canonical JSON Profile 1

The accepted input domain is JSON `null`, booleans, Unicode strings, arrays,
objects, and integers from `-9007199254740991` through
`9007199254740991`. Fractions, exponent notation, larger integers, `NaN`, and
infinities are rejected. A future schema that needs an exact decimal outside
this domain must represent its sign, coefficient, and scale explicitly until a
separate numeric profile is accepted.

Inputs must contain shortest-form valid UTF-8. Escaped surrogate pairs are
decoded; lone or malformed surrogates are rejected. Unicode text is not
normalized because RFC 8785 preserves parsed string data. Object keys are
sorted by their UTF-16 code units, strings use the RFC 8785 minimal escapes,
and negative zero serializes as `0`. Duplicate keys are detected after escape
decoding and rejected before an object is created. Depth, input-byte,
decoded-string, and value-count limits are mandatory parser inputs.

This is a constrained input profile whose output is RFC 8785 compatible. It is
not a claim that arbitrary RFC 8785 binary64 numbers are accepted.

### Hashes and binary references

SHA-256 is incremental and is the only public byte identity. Its textual form
is exactly 64 lowercase hexadecimal characters. An internal binary reference
contains the digest, a size in the same exact-integer domain as Profile 1, a
lowercase parameter-free media type, and
`morphoia-cas://sha256/<lowercase-hex>`. URI construction and inverse parsing
must round-trip exactly; no external URI is converted to a local path by this
component.

### Local Linux/POSIX store

The store walks absolute root and source paths component by component using
directory descriptors and `O_NOFOLLOW`; `.` and `..`, empty components,
embedded NULs, and symlinked components are rejected. Managed directories must
be owned by the effective user and have mode 0700.

Writes stream through a mode-0600 `O_CREAT|O_EXCL` temporary file while SHA-256
and size are calculated. Expected-size/digest ingestion verifies transfer
identity before publication. The file and metadata are synchronized, the mode
is changed to 0444, and Linux `renameat2(RENAME_NOREPLACE)` publishes it without
an overwrite or a two-hard-link visibility interval. Directory entries are
synchronized. If the identity already exists, its regular-file type,
ownership, mode, link count, size, and digest are revalidated; conflicting
bytes are an integrity error.

Reads never expose bytes merely because a path name matches a digest. The
published object is copied and hashed into a private, immediately unlinked
snapshot. Only after the complete size and digest match does the caller's sink
receive bytes from that snapshot. This deliberately spends one local copy to
prevent mutations between validation and delivery from exposing unverified
bytes.

The CAS implementation is internal, not installed, and adds no public ABI
symbol. A non-Linux backend must supply an equivalent atomic no-clobber
primitive and its own executed tests before it can claim compatibility.

## Evidence

Native tests cover NIST SHA-256 vectors, incremental boundaries, exact golden
canonical bytes and digest, UTF-16 key ordering, decoded duplicate keys,
malformed UTF-8 and surrogates, unsafe numbers, parser limits, idempotence,
streaming writes, expected transfer identity, atomic concurrent publication,
existing-object poisoning, symlinked path components, hard-linked objects,
read-time mutation, private-snapshot delivery, size bounds, URI inversion, and
temporary-file cleanup.

The local direct-compiler bootstrap, CMake 3.20 clean build with five native
tests, strict conversion-warning build, and ASan/UBSan suite passed on the
2026-08-12 Linux x86-64 capability profile. Hosted checks and integration are
still required by the Definition of Done. The 20-graph IR replay gate and
greater-than-2-GiB execution remain `NOT_RUN`; this ADR does not reclassify
them.

## Consequences and risks

- Deterministic integer metadata and Unicode strings are available without a
  new runtime dependency.
- Floats and exponent notation fail closed, so schemas must state explicit
  decimal representations when needed.
- Verified reads require temporary local storage equal to the object size and
  therefore must be quota-gated by the eventual workspace configuration.
- `renameat2(RENAME_NOREPLACE)` makes the current backend Linux-specific even
  though its directory and file operations otherwise follow POSIX patterns.
- SHA-256 integrity proves byte identity only; media/schema validation and
  hostile-format limits remain mandatory at the consuming adapter.

## Reversibility and review triggers

Canonicalization and URI domains are versioned. Revisit this decision before
accepting JSON floating-point inputs, installing an internal API as public,
adding a non-Linux local backend, implementing remote object storage, or if
measured snapshot cost violates the eventual I/O budget. Replacing the numeric
profile requires frozen cross-implementation golden vectors and a migration;
existing content identities are never silently rewritten.
