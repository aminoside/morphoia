# ADR-021: Bounded qualified Engine IR inspection profile

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Extends: [ADR-002](ADR-002-cpp-c-abi-python.md),
  [ADR-018](ADR-018-canonical-json-profile-posix-cas.md), and
  [ADR-020](ADR-020-public-engine-ir-v0.1.md)

## Context

The integrated Engine IR 0.1 contract carries a unit code, a seven-component
SI dimension vector, and an exact decimal factor. Its existing semantic
validator checks shape and internal references, but it does not prove that a
code, dimension, and factor agree. The public-IR evidence therefore retains
`MOR-IR-006` as `NOT_RUN`. It also retains `MOR-API-006` as `NOT_RUN` because
thread safety has not been documented and executed for every API family in a
declared profile.

The successor lot needs a useful inspection path without claiming general
UCUM parsing, unit equivalence, conversion, payload resolution, geometric
measurement, or transform application. It must preserve the immutable
public-IR evidence history and produce its own requirement-to-test-to-evidence
profile.

The normative requirements directly addressed by this decision are:

- `MOR-IR-006`: unambiguous UCUM-compatible notation with a verifiable factor
  to SI;
- `MOR-API-006`: documented thread safety for every API family in the declared
  profile; and
- `MOR-QA-017`: every in-lot MUST mapped to an executed test, inspection,
  analysis, or demonstration before any promotion.

All three records derive from technical baseline SHA-256
`40cdb3288e7b1a38a557d1459147aed7ac1d5646aaa5d6ab09a287abc9b22263`.
Their immutable catalogue anchors are:

| Requirement | Baseline proof methods | Retained text line(s) | Record SHA-256 |
|---|---|---:|---|
| `MOR-IR-006` | test | 941-942 | `ed6b351b9a4fcfec2f8920ced1e1251c0bfe4033833b9d553df9641c94f9fb45` |
| `MOR-API-006` | test, inspection | 880 | `3860f47125817422c4fa68cea957554485e3dc755c471b3d6675a7afe16dd451` |
| `MOR-QA-017` | test, inspection, analysis, demonstration | 1664-1665 | `b129ef6c6d7c769391f18a6992ecf27cffc67f9134d04c3459426bffb91580a8` |

## Decision

Adopt one closed, CPU metadata-only qualification and inspection profile. Its
frozen identifiers are:

| Property | Value |
|---|---|
| Lot | `qualified-ir-inspection-0.1` |
| Profile and capability | `engine-ir-core-si-0.1` |
| Inspection format | `morphoia.engine.ir-inspection` |
| Inspection format version | `0.1.0` |
| Inspection schema ID | `https://morphoia.org/schemas/engine/ir-inspection/0.1.0` |
| Inspection media type | `application/vnd.morphoia.ir-inspection.v0+json` |
| Related manifest canonical profile | `morphoia.canonical-json.profile1` |
| Transform policy | `declared-not-applied` |
| Unit policy | `exact-literal-validation-no-conversion` |

Capability negotiation for `engine-ir-core-si-0.1` returns the inspection
format, version, media type, and related manifest canonical profile above. An
empty extension-key list announces no profile-specific extension.

### Original Morphoia unit registry

The registry contains exactly ten case-sensitive ASCII literals. Dimension
components are ordered as length, mass, time, electric current, thermodynamic
temperature, amount of substance, and luminous intensity. The factor to SI is
the exact decimal `coefficient * 10^scale`; mass is expressed against the SI
base unit kilogram.

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

Qualification is exact tuple equality. There is no prefix parser, expression
grammar, spelling normalization, factor normalization, or conversion. For
example, `mm` with coefficient 10 and scale -4 is not qualified even though
the numeric factor is equal. A well-formed but unregistered code such as `cm`,
`rad`, `Cel`, `%`, or `m/s` is unsupported by this profile; the result does not
assert that the code is invalid UCUM.

An input code is lexically callable only when it is nonempty, no longer than
32 bytes, shortest-form UTF-8, and contains no NUL. Malformed lexical input is
a technical error. Any other well-formed non-registry code returns a successful
native call with `recognized`, `dimensions_match`, `si_factor_match`, and
`qualified` false and with the expected tuple zeroed.

This is an independently authored Morphoia interoperability registry. The
repository does not copy, redistribute, modify, adapt, or vendor the UCUM
Specification or its tables. Documentation identifies the external reference
as the [UCUM Specification version 2.2](https://ucum.org/ucum) and links to the
[official UCUM license](https://ucum.org/license). General UCUM grammar,
semantic equivalence, offset units, angular units, compound terms, and the
complete code system remain outside this decision.

### Native ABI

Add exactly one symbol to the seven-symbol ABI accepted by ADR-020:

```c
morphoia_status_t morphoia_context_validate_engine_ir_unit(
    const morphoia_context_t* context,
    const morphoia_engine_ir_unit_t* unit,
    morphoia_engine_ir_unit_validation_t* validation,
    morphoia_diagnostic_t* diagnostic);
```

Both unit structures begin with `struct_size` and `abi_version`, use zero-only
flags and reserved fields in ABI v1, and carry the exact fields described in
the profile guide. The operation is all-or-nothing: a pointer, overlap, ABI,
flag, reserved-field, or lexical error leaves the caller's validation prefix
untouched. Input and code bytes are borrowed only for the call; the result and
diagnostic remain caller-owned. The operation does not allocate through the
context allocator.

The exact export allowlist becomes:

1. `morphoia_canonical_json_profile1`;
2. `morphoia_context_create`;
3. `morphoia_context_destroy`;
4. `morphoia_context_get_abi_version`;
5. `morphoia_context_query_capability`;
6. `morphoia_context_validate_engine_ir_unit`;
7. `morphoia_engine_get_version`; and
8. `morphoia_status_name`.

Qualification calls are read-only and may run concurrently on one live
context when every caller-owned output and diagnostic is disjoint and all
shared inputs remain immutable. Destruction is exclusive and must occur only
after all same-context calls complete. The exhaustive profile contract is in
[`THREAD_SAFETY.md`](../../docs/engine/THREAD_SAFETY.md).

### Python, CLI, and inspection

The reference Python surfaces are
`NativeEngine.validate_engine_ir_unit(code, *, dimensions,
si_factor_coefficient, si_factor_scale)` and
`inspect_engine_ir(source, *, profile="engine-ir-core-si-0.1", engine=None) ->
EngineIrInspection`. The native library remains mandatory; when `engine` is
omitted, the high-level call owns and deterministically closes the context it
creates. A supplied engine remains caller-owned. The CLI is:

```text
morphoia inspect MANIFEST --profile engine-ir-core-si-0.1 \
  --library /absolute/path/to/libmorphoia_engine.so [--json]
```

Inspection first runs the existing lexical, Draft 2020-12 schema, semantic,
and content-identity validation chain. It then qualifies every declared unit
and reports deterministic metadata for identity and revision, effective
capabilities, units, frames, declared transforms, tolerances, authority and
derivation, provenance, fidelity events, repairs, losses, payload-reference
metadata, security, limitations, and diagnostics.

Inspection never resolves or opens representation or source payload bytes,
applies a transform, converts a value, modifies the manifest, repairs a record,
or adds an execution timestamp. It is descriptive except for the bounded unit
qualification verdict. Its JSON is deterministic machine output, not a new
Engine IR content identity or a signable envelope.

Canonical report rendering uses explicit native limits of 8 MiB input,
262,144 UTF-8 bytes per decoded string, 500,000 JSON values, and depth 64.
These limits cover the complete bounded manifest 0.1 collection domain plus
the deterministic qualification annotations; exceeding them is a visible
resource error, never truncation.

The report's per-input `status` value is `PASS` only when that manifest's
literal qualification succeeds. It is an application result, not a gate or
requirements-evidence status, and it cannot promote this proposed ADR.

CLI exit codes are frozen as 0 for a completed qualified inspection, 1 for an
input, profile, runtime, contract, or qualification rejection, and 2 for
command-line syntax rejected by the argument parser.

### Diagnostic taxonomy

Inspection diagnostics carry `family`, `code`, `severity`, `path`, `message`,
`affected_elements`, and `recommendation`. `affected_elements` is always an
array. Records are sorted by `(path, code, affected_elements)`; no diagnostic
contains an absolute library or workspace path.

The closed severity vocabulary is `info`, `warning`, and `error`. An `error`
makes the per-input qualification fail; `warning` and `info` do not. A valid,
fully qualified manifest normally has no diagnostics. Normal declarations
belong in their report sections and do not generate a diagnostic by themselves.

| Baseline family | Codes emitted by this profile | Use |
|---|---|---|
| `MOR-UNIT/FRAME` | `MOR-UNIT-UNSUPPORTED`, `MOR-UNIT-DIMENSION`, `MOR-UNIT-SI-FACTOR` | Exact literal unit qualification only |

Manifest lexical/schema/semantic failures and capability incompatibilities
remain structured Python/CLI exceptions in version 0.1; they are not forged
into report diagnostics because no valid inspection report exists yet. The
other baseline families remain reserved and are never emitted by this bounded
metadata profile.

The C unit validator uses existing ABI status codes for technical failures.
An unrecognized well-formed unit is a qualification result, not a new ABI
status. The Python/CLI inspection layer converts that result to
`MOR-UNIT-UNSUPPORTED` without mislabeling it as invalid UCUM.

## Evidence boundary

This ADR freezes a proposed contract; it is not execution evidence. Until the
implementation, negative tests, concurrency tests, two clean builds,
sanitizers, Python 3.12 and 3.13 jobs, license checks, and hosted integration
all complete, the lot and both candidate requirement promotions remain
`NOT_RUN`.

| Requirement | Current lot status | Conditional promotion boundary |
|---|---|---|
| `MOR-IR-006` | `NOT_RUN` | Eligible for bounded-profile `PASS` only after all ten tuples, code/dimension/factor mutations, 20-graph inspection, and cross-surface agreement execute successfully. General UCUM conformance remains `NOT_RUN`. |
| `MOR-API-006` | `NOT_RUN` | Eligible for bounded-profile `PASS` only after the exact native, Python, and CLI inventory in `THREAD_SAFETY.md` is reviewed and its declared same-context/lifetime concurrency tests execute successfully. API families outside this profile remain `NOT_RUN`. |
| `MOR-QA-017` | `NOT_RUN` | Eligible for lot-level `PASS` only when every in-lot MUST has an exact test or inspection and hash-addressed evidence; it cannot promote project-wide traceability. |

The previously accepted public-IR subclaims in `MOR-DEV-002`, `MOR-DEV-003`,
`MOR-API-002` through `MOR-API-005`, `MOR-API-007` through `MOR-API-010`, and
`MOR-IR-001`, `MOR-IR-002`, `MOR-IR-007` through `MOR-IR-009`,
`MOR-IR-012` through `MOR-IR-014`, and `MOR-IR-018` are regression
obligations, not new promotions by this decision.

Inspection exposes fields relevant to `MOR-SCP-003`, `MOR-SCP-004`,
`MOR-ARC-013`, `MOR-IR-003`, `MOR-IR-005`, and `MOR-IO-008`, but does not
execute enough evidence to promote any of them. Their broader results remain
`NOT_RUN`. Payload resolution, geometry measurement, unit conversion,
transform application, SALOME, GPU/HPC, greater-than-2-GiB execution, and MVX
remain outside the lot. A field appearing in an inspection report is never by
itself proof of the corresponding scientific or interoperability behavior.

## Required acceptance evidence

Acceptance requires all of the following to execute and be retained before
this ADR may become Accepted:

- all ten positive unit tuples plus independent code, case, dimension,
  coefficient, and scale mutations through C, Python, and CLI;
- ABI-prefix, exact and partial overlap, reserved-field, invalid UTF-8, NUL,
  and explicit-length mutations through the C ABI, plus the corresponding
  type, range, lexical, and lifetime boundaries exposed by Python; these
  memory-layout mutations are deliberately not misrepresented as CLI inputs;
- deterministic human and JSON inspection of the frozen 20-graph corpus twice,
  with payload bytes absent, transforms still `declared-not-applied`, and no
  manifest mutation;
- exact eight-symbol export inspection and capability-constant agreement;
- concurrent same-context native qualification, distinct-context execution,
  and Python close-versus-call lifetime tests matching `THREAD_SAFETY.md`;
- two clean build/install/consumer executions, fail-fast ASan and UBSan,
  Python 3.12 and 3.13, full regression tests, and hosted branch/PR checks;
- a fail-closed lot manifest, traceability mapping, raw evidence hashes,
  REUSE/SBOM/license checks, and an explicit inspection showing that no UCUM
  table or specification content was vendored or adapted.

Design review, compilation alone, a skipped test, or a mock does not satisfy
any item above.

## Consequences and review triggers

The profile supplies a small verifiable SI tuple boundary without creating a
general unit system or silently converting data. Unsupported codes remain
visible and can be added only through a new profile version, reviewed original
registry change, and new vectors. The inspection report is reproducible and
offline but deliberately cannot prove payload availability or geometry.

Review this decision before expanding the literal registry, accepting unit
expressions or equivalent factors, introducing conversions or offset units,
changing dimension order, resolving payloads, applying transforms, adding a
device/backend diagnostic, changing any frozen identifier or exit code, or
claiming general UCUM conformance. A validated MVX specification receives its
own change control and cannot be inferred from this profile.
