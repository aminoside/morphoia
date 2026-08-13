# Qualified Engine IR inspection 0.1

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

This guide specifies the proposed `engine-ir-core-si-0.1` qualification and
inspection profile. It refines the public Engine IR manifest described in
[`IR_MANIFEST_0_1.md`](IR_MANIFEST_0_1.md) without changing that manifest's
identity domain. The normative design record is
[ADR-021](../../spec/adr/ADR-021-qualified-ir-inspection.md).

No result in this guide is execution evidence. Until the complete lot gate is
run and integrated, qualification and thread-safety claims for `MOR-IR-006`
and `MOR-API-006` remain `NOT_RUN`.

## Profile constants

| Property | Value |
|---|---|
| Lot | `qualified-ir-inspection-0.1` |
| Profile and capability | `engine-ir-core-si-0.1` |
| Input manifest format | `morphoia.engine.ir-manifest` version `0.1.0` |
| Inspection format | `morphoia.engine.ir-inspection` |
| Inspection format version | `0.1.0` |
| Inspection schema ID | `https://morphoia.org/schemas/engine/ir-inspection/0.1.0` |
| Inspection media type | `application/vnd.morphoia.ir-inspection.v0+json` |
| Related canonical profile | `morphoia.canonical-json.profile1` |
| Transform policy | `declared-not-applied` |
| Unit policy | `exact-literal-validation-no-conversion` |

The inspection format has its own version and media type. It is deterministic
machine output, but it is not an Engine IR manifest, a content identity, a
signable envelope, or a replacement for the inspected input.

Report canonicalization uses explicit native bounds: 8 MiB input, 262,144
UTF-8 bytes in any decoded string, 500,000 JSON values, and depth 64. This
covers the complete bounded manifest 0.1 collection domain and its
qualification annotations; the renderer never truncates a report.

## Bounded unit registry

The profile recognizes exactly ten Morphoia-authored literals. Comparisons are
case-sensitive and byte-exact. The dimension order is:

```text
length, mass, time, electric current, thermodynamic temperature,
amount of substance, luminous intensity
```

The SI factor is `coefficient * 10^scale`. The mass component is relative to
kilogram, the SI base unit.

| Literal | Dimension `(L, M, T, I, Theta, N, J)` | Coefficient | Scale |
|---|---:|---:|---:|
| `1` | `(0, 0, 0, 0, 0, 0, 0)` | 1 | 0 |
| `m` | `(1, 0, 0, 0, 0, 0, 0)` | 1 | 0 |
| `mm` | `(1, 0, 0, 0, 0, 0, 0)` | 1 | -3 |
| `s` | `(0, 0, 1, 0, 0, 0, 0)` | 1 | 0 |
| `kg` | `(0, 1, 0, 0, 0, 0, 0)` | 1 | 0 |
| `g` | `(0, 1, 0, 0, 0, 0, 0)` | 1 | -3 |
| `A` | `(0, 0, 0, 1, 0, 0, 0)` | 1 | 0 |
| `K` | `(0, 0, 0, 0, 1, 0, 0)` | 1 | 0 |
| `mol` | `(0, 0, 0, 0, 0, 1, 0)` | 1 | 0 |
| `cd` | `(0, 0, 0, 0, 0, 0, 1)` | 1 | 0 |

A declaration is qualified only when its literal, complete dimension vector,
coefficient, and scale exactly match one row. The profile performs no
conversion or normalization. In particular, `{coefficient: 10, scale: -4}`
does not qualify as the factor for `mm` even though it represents the same
numeric value as `{coefficient: 1, scale: -3}`.

The registry is not a prefix parser or expression grammar. `cm`, `rad`, `Cel`,
`%`, `m/s`, and every other unregistered code are unsupported by this bounded
profile. That verdict does not state that they are invalid UCUM codes.
General expression parsing, semantic equivalence, offset scales, angular
units, compound units, annotations, and conversion remain `NOT_RUN`.

The external interoperability reference is the
[UCUM Specification version 2.2](https://ucum.org/ucum). Its terms are at the
[official UCUM license page](https://ucum.org/license). Morphoia does not copy,
modify, adapt, redistribute, or vendor the UCUM Specification or its tables.
The ten factual literals and tuples above form an independently authored,
closed Morphoia registry for this application profile.

## Native qualification contract

Capability discovery uses `MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI`, whose value
is `engine-ir-core-si-0.1`. The additive ABI function is:

```c
morphoia_status_t morphoia_context_validate_engine_ir_unit(
    const morphoia_context_t* context,
    const morphoia_engine_ir_unit_t* unit,
    morphoia_engine_ir_unit_validation_t* validation,
    morphoia_diagnostic_t* diagnostic);
```

`morphoia_engine_ir_unit_t` contains, in order:

- `uint32_t struct_size` and `uint32_t abi_version`;
- `uint64_t flags`, which must be zero in ABI v1;
- the explicit-length `morphoia_string_view_t code`;
- `int32_t dimensions[7]` in the frozen order above;
- `int64_t si_factor_coefficient` and `int32_t si_factor_scale`; and
- `uint32_t reserved`, which must be zero.

`morphoia_engine_ir_unit_validation_t` contains, in order:

- `uint32_t struct_size` and `uint32_t abi_version`;
- `uint64_t flags`, which must be zero in ABI v1;
- `uint32_t recognized`, `dimensions_match`, `si_factor_match`, and
  `qualified`;
- `int32_t expected_dimensions[7]`;
- `int64_t expected_si_factor_coefficient` and
  `int32_t expected_si_factor_scale`; and
- `uint32_t reserved`, which must be zero.

Callers initialize both structures with their known sizes and negotiated ABI
version. A recognized literal always returns the registry's expected tuple.
A well-formed unregistered code returns `MORPHOIA_STATUS_OK`, all four verdict
fields false, a zero expected tuple, and an empty successful diagnostic.

The code view must be nonempty, at most 32 bytes, shortest-form UTF-8, and free
of embedded NUL bytes. A 32-byte well-formed unknown code is callable; an empty
view, 33 or more bytes, malformed UTF-8, or embedded NUL yields
`MORPHOIA_STATUS_INVALID_ARGUMENT`. Non-ASCII shortest-form UTF-8 is callable
but unrecognized by the ASCII registry.

All ABI-v1 input/output prefixes, code bytes, context storage, and compatible
diagnostic prefix must be mutually disjoint. Technical failures caused by
pointers, overlap, ABI, flags, reserved fields, or lexical input leave the
validation prefix untouched. The implementation does not retain pointers or
allocate through the context allocator. See [`THREAD_SAFETY.md`](THREAD_SAFETY.md)
for lifetime and concurrency rules.

## Python and command line

The proposed reference Python entry points are:

```python
NativeEngine.validate_engine_ir_unit(
    code,
    *,
    dimensions,
    si_factor_coefficient,
    si_factor_scale,
)

inspect_engine_ir(
    source,
    *,
    profile="engine-ir-core-si-0.1",
    engine=None,
) -> EngineIrInspection
```

There is no pure-Python qualification or canonicalization fallback. An
explicit `engine` must be an open `NativeEngine` and remains caller-owned. When
`engine` is omitted, `inspect_engine_ir` owns and deterministically closes the
native context it creates. These signatures remain Proposed and `NOT_RUN`
until implementation and exact API-inventory tests pass.

The proposed CLI is:

```console
morphoia inspect MANIFEST \
  --profile engine-ir-core-si-0.1 \
  --library /absolute/path/to/libmorphoia_engine.so \
  --json
```

Omit `--json` for human-readable output. `--library` names an absolute regular
file, or an already documented installed-library resolution path may be used.
No current-working-directory library fallback is authoritative.

The stable exit-code contract is:

| Code | Meaning |
|---:|---|
| 0 | Inspection completed and every declared unit qualified. |
| 1 | Input, profile, native runtime, contract, or unit qualification was rejected. |
| 2 | Command-line syntax was rejected by the argument parser. |

These surfaces are proposed until their implementation and exact golden tests
are integrated. This document does not claim that the command currently runs.

## Validation and inspection sequence

An inspection executes in this order:

1. safely snapshot the bounded manifest file without following a symlink;
2. query and compare the exact native capability and version constants;
3. run native lexical validation and Profile 1 canonicalization;
4. run Draft 2020-12 schema validation;
5. run the existing Engine IR semantic and content-identity checks;
6. qualify each unit against the closed native registry;
7. construct deterministic descriptive sections and diagnostics; and
8. render human output or deterministic JSON.

The report contains these sections in the listed order:

| Section | Bounded content |
|---|---|
| `identity_and_revision` | Manifest/content hashes, logical ID, revision, and declared parents |
| `effective_capabilities` | Exact profile, format, version, media type, and canonical profile |
| `units` | Declared tuple, expected tuple, and qualification booleans |
| `frames` | Dimension, origin, axes, handedness, matrix order, and unit reference |
| `transforms` | Source/target frames, matrix order, and preserved `declared-not-applied` policy |
| `tolerances` | Declared subject, kind, exact amount, unit, and source |
| `authority_and_derivation` | Representation kind, authority, parents, and AI-candidate declaration |
| `provenance` | Declared DAG event metadata and links |
| `fidelity_events` | Declared property, before/after, metric, threshold, severity, and decision |
| `repairs` | Declared action, before/after, reversibility, and decision |
| `losses` | Declared category, property, before/after, severity, decision, and description |
| `payload_reference_metadata` | URI, SHA-256, byte size, and media type as declarations only |
| `security` | Classification, sensitivity, access policy, signature declaration, and trust level |
| `limitations` | All non-executed and unsupported boundaries for this report |
| `diagnostics` | Stable structured findings sorted as specified below |

Within each collection, records use their manifest order unless the inspection
schema explicitly requires a stable key sort. The renderer adds no wall-clock
timestamp, process ID, workspace path, native-library path, or nondeterministic
environment data.

Inspection must not:

- open, resolve, hash, decode, or validate the referenced source or
  representation payload bytes;
- apply a transform, change a frame, or convert a number;
- insert a repair, loss, fidelity, authority, or provenance record;
- rewrite, reseal, or otherwise mutate the input manifest; or
- infer geometric validity, SALOME compatibility, device support, clinical
  meaning, or MVX semantics.

## Diagnostics

Every diagnostic has this closed shape:

```json
{
  "family": "MOR-UNIT/FRAME",
  "code": "MOR-UNIT-SI-FACTOR",
  "severity": "error",
  "path": "$.content.units[0].si_factor",
  "message": "The declared SI factor does not match the profile tuple.",
  "affected_elements": ["unit-id"],
  "recommendation": "Use the exact profile tuple or select another profile."
}
```

The example is a proposed shape, not evidence of an executed diagnostic.
Diagnostics sort by `path`, then `code`, then the lexicographic
`affected_elements` array. Messages and recommendations are stable US English.
The severity vocabulary is exactly `info`, `warning`, and `error`; an `error`
makes the per-input qualification fail. A fully qualified manifest normally
has no diagnostics. Valid declarations are rendered in their normal sections
and do not produce findings merely because they exist.

| Family | Codes emitted by this profile |
|---|---|
| `MOR-UNIT/FRAME` | `MOR-UNIT-UNSUPPORTED`, `MOR-UNIT-DIMENSION`, `MOR-UNIT-SI-FACTOR` |

Lexical, schema, semantic, runtime, and capability failures occur before a
valid report exists and remain structured Python/CLI exceptions. This profile
does not fabricate report diagnostics for them. `MOR-I/O`, `MOR-GEOM`,
`MOR-CAS`, `MOR-SEC`, `MOR-EXT`, `MOR-DEVICE`, and other `MOR-UNIT/FRAME`
codes are reserved and never emitted by version 0.1.

`MOR-UNIT-UNSUPPORTED` means only that a well-formed code is outside
`engine-ir-core-si-0.1`. It must not say that the code is invalid under the
larger UCUM specification.

## Evidence and truth boundary

The following promotions are conditional, not current results:

| Requirement | Current status | Eligible bounded result only after gate execution |
|---|---|---|
| `MOR-IR-006` | `NOT_RUN` | `PASS` for the exact ten-literal profile after all tuple/mutation and 20-graph cross-surface tests pass; general UCUM stays `NOT_RUN`. |
| `MOR-API-006` | `NOT_RUN` | `PASS` for only the API inventory in `THREAD_SAFETY.md` after documentation inspection and declared concurrency/lifetime tests pass. |
| `MOR-QA-017` | `NOT_RUN` | `PASS` only for this lot when every in-lot MUST links to executed and hash-addressed evidence. |

Existing public-IR results are regression requirements. The inspection does
not newly promote identity/revision completeness, payload resolvability,
authority/provenance completeness, repair/loss measurement, total offline
operation, or tolerance-per-conformance-asset claims. Accordingly,
`MOR-SCP-003`, `MOR-SCP-004`, `MOR-ARC-013`, `MOR-IR-003`, `MOR-IR-005`, and
`MOR-IO-008` retain their broader `NOT_RUN` status in this lot.

Acceptance requires positive and adversarial C/Python/CLI vectors, deterministic
20-graph output twice, proof that absent payload bytes were never opened,
unchanged transform declarations, exact eight-symbol ABI inspection, the
thread tests in `THREAD_SAFETY.md`, two clean builds, ASan/UBSan, Python 3.12
and 3.13, hosted checks, traceability, hashes, REUSE/SBOM/license checks, and a
non-vendorization inspection. Compilation, skipped tests, dry runs, or mocks do
not produce `PASS`.

A report whose application-level `status` is `PASS` says only that one input
qualified against this literal profile. It is not gate evidence and does not
change any requirement status before the complete gate above executes.
