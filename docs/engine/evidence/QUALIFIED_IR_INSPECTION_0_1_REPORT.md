# Qualified Engine IR inspection 0.1 evidence report

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Date: 2026-08-12
Lot: `qualified-ir-inspection-0.1`
Profile: `engine-ir-core-si-0.1`
Source base: `767b88ab7e89b30ed77f5b30c25372d71fa06402`
Status: `NOT_RUN` for release qualification; bounded local sub-gates are
recorded independently

## Scope and truth boundary

This prospective profile inventories the bounded CPU metadata-only unit
qualification and deterministic Engine IR inspection work defined by ADR-021.
Its closed manifest contains exactly 55 artifacts: 54 explicit source,
contract, test, workflow, state, and evidence files plus the separate
CycloneDX SBOM.
It covers exactly ten original Morphoia unit literals, the exact eight-symbol
C ABI export boundary, the reference Python binding, deterministic human and
JSON CLI inspection, the 20 synthetic Engine IR graphs, and the exhaustive
thread-safety contract for API families named by the profile.

The profile does not implement or claim general UCUM parsing, unit
equivalence, offset units, compound expressions, normalization, or conversion.
It does not resolve payload bytes, apply transforms, measure geometry, execute
SALOME, GPU/HPC or greater-than-2-GiB paths, or define MVX behavior. Those
profiles remain `NOT_RUN`; MVX-specific work also remains blocked by the
missing owner-validated specification.

The external reference is the [UCUM Specification version
2.2](https://ucum.org/ucum), under its [official
license](https://ucum.org/license). No UCUM specification text, registry table,
or implementation is copied, adapted, or vendored by this lot.

## Frozen inventory invariants

- Registry literals are exactly `1`, `m`, `mm`, `s`, `kg`, `g`, `A`, `K`,
  `mol`, and `cd`, with the dimension and exact decimal factor tuples frozen in
  ADR-021.
- The Linux export allowlist contains exactly
  `morphoia_canonical_json_profile1`, `morphoia_context_create`,
  `morphoia_context_destroy`, `morphoia_context_get_abi_version`,
  `morphoia_context_query_capability`,
  `morphoia_context_validate_engine_ir_unit`,
  `morphoia_engine_get_version`, and `morphoia_status_name`.
- Exactly 20 licensed synthetic input manifests are inspected twice. The
  report bytes and SHA-256 digest must agree on both traversals; payload bytes
  are absent and are never opened by inspection. Their exact input digests,
  canonical report sizes, and canonical report SHA-256 values are retained in
  `spec/evidence/qualified-ir-inspection-0.1-report-vectors.json` and checked
  by the executing native inspection test. The registry also binds the exact
  direct strict-GCC test library SHA-256 because that digest is deliberately
  included in each inspection report's effective-capability metadata.
- The public-IR predecessor is replayed only from immutable commit
  `767b88ab7e89b30ed77f5b30c25372d71fa06402`. Its bridge verifies 309 Git
  blobs and executes the historical generator plus 22 tests in the pinned
  replay environment.

## Prospective execution record

The machine-readable command record is
`spec/evidence/qualified-ir-inspection-0.1-traceability.json`. At this
checkpoint, the direct compiler fallback, two clean CMake 3.20.5 build/install
paths, immutable predecessor replay, bounded 45-test Python selection, 86-test
public-IR lot plus 20-graph validator, ASan/UBSan, installed-wheel smoke,
strict warnings, evidence mutations, final REUSE/hygiene checks, and the full
Python regression (206/206 tests in 84.942 seconds on CPython 3.12.13) have
local `PASS` results. LeakSanitizer, byte-identical wheel comparison, Python
3.12/3.13 hosted matrices, PR, integration, and exact-merge executions remain
`NOT_RUN` until they actually occur.

Consequently `MOR-IR-006`, `MOR-API-006`, and `MOR-QA-017` remain `NOT_RUN` in
this prospective profile. The full local regression is `PASS`, but the hosted
Python 3.12/3.13 matrices, review, and integration executions required by the
Proposed ADR-021 remain pending. A local sub-gate is not silently promoted
into the complete ADR-021 gate. If later hosted evidence succeeds, a new
evidence checkpoint must update the command records and requirement statuses
without rewriting this execution history.

The accepted public-IR claims inherited from the immutable predecessor are
regression obligations, not new promotions. The global requirements overlay
is deliberately unchanged.

## Reproduction

From the repository root on Linux x86-64:

```bash
python3 scripts/validate_engine_e1_public_ir_frozen.py
MORPHOIA_BOOTSTRAP_FORCE_FALLBACK=1 bash scripts/bootstrap-engine.sh
bash scripts/run-engine-sanitizers.sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/generate_engine_qualified_ir_inspection_evidence.py --check
PYTHONPATH=src python3 -m unittest -v \
  tests.test_qualified_ir_inspection_evidence
python3 -m reuse lint
bash scripts/scan-secrets.sh
git diff --check
```

The deterministic artifact manifest is retained at
`artifacts/manifests/engine-qualified-ir-inspection-0.1.json`; its final entry
hashes the separate CycloneDX 1.5 inventory at
`artifacts/sbom/engine-qualified-ir-inspection-0.1.cdx.json`. The SBOM is an
inventory only: vulnerability analysis remains `NOT_RUN` for every component.
Repository REUSE conformance does not constitute a third-party dependency
license audit; that review also remains `NOT_RUN`.
