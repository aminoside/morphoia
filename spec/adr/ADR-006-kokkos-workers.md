# ADR-006: Kokkos sources with targeted CPU, CUDA, HIP, and SYCL workers

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Proposed
- Date: 2026-08-12
- Baseline status: Validate in P0

## Context

The same numerical intent should run on an open CPU path and selected GPU
ecosystems without pretending that one binary can cover incompatible runtime
and toolchain stacks.

## Options considered

1. Maintain separate handwritten kernels for every backend.
2. Promise a universal GPU binary.
3. Share appropriate kernel sources with Kokkos and ship targeted workers:
   CPU/OpenMP, CUDA, HIP, and later SYCL Tier 2.

## Decision

Adopt option 3 subject to measured P0 validation. Workers are separate
processes/packages with explicit Device, Buffer, Image, Queue, Event, Fence,
and CapabilitySet contracts. The CPU reference remains mandatory and open.
Backend claims require real execution on matching hardware.

## Evidence required for acceptance

Run the same frozen kernel and inputs on CPU, NVIDIA CUDA, and AMD HIP within
preregistered tolerances, including allocations, copies, synchronization, and
transfer costs. A compile-only or simulated backend is not sufficient. E0 has
only GCC/OpenMP; all GPU results are `NOT_RUN`.

## Consequences and risks

Source reuse can reduce divergence while targeted binaries preserve toolchain
reality. Backend-specific tuning and numerical order can still diverge. Kokkos
may add complexity without benefit for some kernels.

## Reversibility and review trigger

Workers and kernels remain behind stable contracts. Reconsider Kokkos after the
P0 benchmark if maintenance cost, binary size, or end-to-end performance is
worse than a documented alternative on at least two required backends.
