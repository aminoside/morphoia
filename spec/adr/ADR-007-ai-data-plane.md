# ADR-007: DLPack and Arrow C Data/Device for the AI data plane

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Baseline status: Validate in P0

## Context

Morphoia must exchange tensors and structured arrays with PyTorch, ONNX Runtime,
and future runtimes without embedding an AI framework in the core or hiding
copies and synchronization.

## Options considered

1. Link the core directly to one AI framework.
2. Define a proprietary tensor ABI.
3. Use DLPack for tensor ownership/device exchange and Arrow C Data/Device for
   structured/tabular interchange.

## Decision

Adopt option 3 subject to P0 lifetime and transfer validation. Runtimes remain
external. Every exchange records device, dtype, shape/strides, ownership,
deleter lifetime, stream/event synchronization, copy count, and transfer cost.
Zero-copy may be claimed only when instrumented evidence proves it.

## Evidence required for acceptance

Execute a PyTorch CPU reference round-trip and lifetime stress tests, including
producer-first and consumer-first destruction, non-contiguous layouts, error
paths, and explicit copies. Extend per available backend. E0 has not executed
these tests.

## Consequences and risks

Morphoia avoids reproducing framework kernels and supports multiple runtimes.
The highest risks are use-after-free, stream races, device mismatch, and
unreported fallback copies.

## Reversibility and review trigger

Interchange adapters are versioned plugins. Reconsider one protocol if its
upstream lifetime/device semantics cannot represent a mandatory case or if two
real runtimes require incompatible behavior that cannot be negotiated.
