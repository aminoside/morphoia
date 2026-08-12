<!-- SPDX-FileCopyrightText: 2026 Olivier Ami -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Morphoia Engine requirements catalogue

The requirements source is deliberately split into two machine-readable
documents:

- `requirements.yaml` is the immutable transcription of all 320 atomic
  requirements in the French v0.1 technical specification;
- `requirements-tracking.yaml` is the living requirement-to-component,
  work-package, issue, test, evidence, dependency, gate, and status overlay.

Both files use JSON syntax, a strict subset of YAML 1.2. The corresponding
JSON Schema 2020-12 contracts are
`requirements-catalog.schema.json` and
`requirements-tracking.schema.json`.

## Integrity model

The French wording, priority column, phase, proof method, row fragments, and
source coordinates are preserved without editorial correction. Every source
record carries a source hash and an immutable-record hash. Two aggregate
digests have distinct purposes:

- `records_sha256` is the published compact digest over identifier, wording,
  priority, phase, and proof method;
- `immutable_records_sha256` also covers family and ordinal derivations,
  source coordinates and fragments, source hashes, quality flags, and
  per-record hashes.

Ten source rows contain a mismatch between the modal verb in the wording and
the priority column. They remain unmodified and are flagged
`modal_priority_mismatch` pending formal change control. The priority column
remains authoritative.

Family-to-component, work-package, and phase-to-gate assignments are checked
derived mappings. Other tracking values are living project data. Empty test,
evidence, issue, and dependency fields mean not established, never satisfied.
Every execution status starts as `NOT_RUN`.

The validator enforces evidence invariants without a third-party Python
package. In particular, `PASS` and `FAIL` require test and evidence references;
`PASS` also requires complete requirement and dependency mapping; `BLOCKED`
requires a reason, dependency, and blocker evidence; and `NOT_APPLICABLE`
requires a reason and justification evidence.

## Regeneration and validation

Run:

```bash
python3 scripts/extract_engine_requirements.py
python3 scripts/extract_engine_requirements.py --check
```

Regeneration is fail-closed on the PDF, layout extraction, compact records,
and full immutable-record digests. It creates a fail-closed tracking overlay
only when that file is absent. If an overlay already exists, it is validated
and preserved byte-for-byte. An invalid overlay blocks regeneration before the
immutable catalogue is written; live traceability is never silently repaired,
reset, or discarded.

A changed Poppler extraction must be investigated through change control; it
must never silently rewrite either source-of-truth file.
