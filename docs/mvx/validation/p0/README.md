# MVX P0.1 - feasibility protocol

This directory is the executable pre-registration package for the Morphoia
MVX feasibility study. It freezes the decisions that could otherwise be tuned
after seeing calibration or blind results.

The current candidate is `1.0.2-p0`. The local `1.0.1-p0` seal was superseded
before publication or experimental use when the post-seal drift guard detected
delayed hardening edits. Its original seal, verdict and cryptographically
linked supersession record remain under `audit/superseded-1.0.1-p0/`.

## Normative files

- `protocol.yaml`: authority, scope, endpoints, missing-data and stopping rules.
- `metrics.yaml`: metric definitions, directions, populations and thresholds.
- `eligibility.yaml`: inclusion, exclusion, topology status and repair policy.
- `split-spec.yaml`: deterministic grouped split algorithm, commit-reveal secret
  policy and targets.
- `selection-spec.yaml`: deterministic selection of the 1,000-unit cohort,
  reserve, nested milestones and Objaverse OOD categories.
- `split-test-vectors.json`: frozen input/output vectors for split conformance.
- `statistical-plan.yaml`: estimands, confidence intervals and multiplicity.
- `error-codes.yaml`: terminal statuses and stable error taxonomy.
- `release-criteria.yaml`: cumulative gates G0-G7 and final decision rules.
- `roles.yaml`: decision, custody, unlock and adjudication responsibilities.
- `implementation-clarifications.yaml`: explicit resolutions of contradictions
  and bit-exact notation required before implementation.
- `seal.json`: SHA-256 manifest generated from all normative files.

No production selection seed or split salt exists at P0. After the complete
P1a+P2a eligible-record root is sealed, an external custodian generates both
preimages and publishes one immutable precommit binding both SHA-256
commitments before either preimage is used. The preimages and full blind
mapping remain inaccessible. Public and development views contain no blind
identity or path.

Every executable stage is declared in an immutable execution plan. Its
content-derived `work_id` binds the protocol, split, source, lineage, profile,
configuration, code, environment, phase and stage. A completed stage is
skipped only when a terminal checkpoint exists and every required artifact
still matches its SHA-256. Ordinary interrupted work is retried with a linked
attempt; interrupted blind/open-once work fails closed and is never replayed
automatically.

G1 publication is a two-bundle transaction. Private and releasable files are
validated and written to sibling staging directories, fsynced and atomically
published. The terminal freeze receipt is written last. Repeating a
byte-identical transaction returns `ALREADY_COMMITTED`; conflicts fail closed.

The external publication step returns a signed receipt binding the exact
precommit, raw-byte publisher-registry hash, registry epoch and G0 seal to an
immutable object version and bounded sequence. Production freeze loads only the
normative `trusted-publishers.json`; there is no caller path override. P0
contains only a non-production test key and its registry state is BLOCKED, so G1
cannot run until a real WORM publisher key and READY state are introduced by a
new sealed protocol version. Offline verification cannot itself prove remote
WORM persistence or a globally monotone history; those remain external custody
evidence and no stronger pre-calculation claim is made at P0.

The JSON schemas in the repository root `schemas/` are also included in the
seal. `gates/G0-verdict.json` is a result of validation and is deliberately not
part of the normative hash, avoiding a circular seal.

## Verify

```bash
morphoia mvx protocol verify
morphoia mvx custody dry-run
python -m unittest tests.test_mvx_protocol -v
```

The production custodian first writes the public precommit, then invokes the
freeze with the same two preimages through distinct inherited file
descriptors. Plaintext secrets must never appear in arguments, logs, Git or the
shared development workspace.

```bash
morphoia mvx custody precommit --snapshot-sha256 SNAPSHOT --eligible-records-sha256 ELIGIBLE --selection-secret-fd FD1 --split-secret-fd FD2 --output custody-precommit.json
morphoia mvx cohort freeze eligible.jsonl --snapshot-sha256 SNAPSHOT --eligible-records-sha256 ELIGIBLE --precommit custody-precommit.json --publication-receipt signed-receipt.json --selection-secret-fd FD1 --split-secret-fd FD2 --private-dir PRIVATE --release-dir RELEASE
```

The protocol may be amended only by a new version. A changed file with an old
seal is a hard failure. Confirmatory results remain tied to the exact protocol
root hash recorded in their run manifest.
