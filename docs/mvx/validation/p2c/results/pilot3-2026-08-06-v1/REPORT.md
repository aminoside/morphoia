# P2c v1 disposition report

Status: `UNANCHORED_DIAGNOSTIC`

Author: Dr Olivier Ami

## Verified

- The historical runner is Git commit
  `63dadbf930be77a7281a564387e9b9cbf6082022` and has SHA-256
  `adb7fe9aef50f4473a5220788004ecebaec9bfd5d81be478b14132f774534f02`.
- Four terminal chains cover three P2a sources. Their local Ed25519 attempt
  signatures validate.
- Two executions returned `EXACT_INTERSECTION_FREE_CANDIDATE`; one default
  execution reached its declared pair limit; the same source under the
  preregistered expanded limit returned `EXACT_CONTACT_FOUND`.
- No signed external completion anchor and no signed anchor-readback receipt
  exist.
- The private Drive payload was previously read back byte-for-byte, but its
  archive does not reproduce the required file modes and empty directories in
  a clean extraction.

## Decided

- The execution plans remain byte-for-byte unchanged with their planned
  `REQUIRE_EXTERNAL_ANCHOR` policy.
- The realized campaign is frozen as `UNANCHORED_DIAGNOSTIC`.
- It receives no gate credit and certifies zero solids.
- P2c v2 must use new work identifiers and must not silently reuse v1 results,
  placeholders, signatures, or checkpoints.

## Known limitations

The v1 P2a-bound materializer merged vertex instances with exactly equal
coordinates. That may turn a geometric contact between topologically distinct
shells into an allowed shared-vertex or shared-edge adjacency. The two negative
contact findings are therefore candidate diagnostics only.

The scientific computation is deterministic for a fixed materialized mesh,
limits, and algorithm. The complete JSON envelopes are intentionally not
byte-identical across fresh executions because each attempt uses a new local
authorization key. Cross-version comparison must exclude work identifiers,
plan hashes, and signatures and compare the canonical scientific projection.

## Next decision

P2c v2 must first preserve original vertex instances, prove its persistent
signer is available, run the same three default profiles plus the declared
expanded profile, compare the scientific projections, and pass a clean
restore/reuse test. A separate independent solid verifier remains required
before any derived `V` status.
