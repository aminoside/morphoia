# ADR-016: Keep the MVX scientific gate independent from the foundation

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Baseline status: Proposed by the technical specification

## Context

MVX is strategically important but its validated specification has not been
received. Inventing encoding, quantization, model, reconstruction, thresholds,
or GPU assumptions would create false evidence and delay independent Engine
capabilities.

## Options considered

1. Block all work until MVX is specified.
2. Invent a provisional MVX and later migrate it.
3. Deliver the functional CPU foundation independently, prepare only an opaque
   versioned SPI/harness, and run a separate scientific gate after validation.

## Decision

Propose option 3. E6 may release a functional pre-MVX vertical slice without
claiming G1. E7 defines generic contracts and metrics only. A `mock_mvx` or
`null_mvx` adapter tests software plumbing and is excluded from science. E8
starts only after an owner-validated specification is baselined and traced.

## Evidence required for acceptance

The pre-MVX end-to-end CPU path and E7 contract suite must execute without MVX
semantics. The later MVX gate must freeze inputs, corpus, splits, metrics, and
thresholds before final evaluation, first on 30-50 objects and then about 1,000
if the pilot passes.

## Consequences and risks

Foundation progress is honest and a scientific No-Go cannot corrupt it. The SPI
may need change control when the real specification arrives. Public messaging
must distinguish a functional pre-MVX release from contractual G1/P0.

## Reversibility and review trigger

Review immediately when a validated MVX specification arrives. If it makes an
existing core invariant incompatible, produce a conflict analysis and minimum
owner decision rather than silently weakening either source.
