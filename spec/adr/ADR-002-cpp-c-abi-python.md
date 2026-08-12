# ADR-002: C++20 internals, public C ABI, Python user API

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

- Status: Accepted
- Date: 2026-08-12
- Baseline status: Accepted

## Context

The engine needs native performance and access to C++ scientific libraries,
but consumers require a durable language-neutral boundary and productive
orchestration.

## Options considered

1. Publish the C++ ABI directly.
2. Implement only in Python.
3. Use C++20 internally, a versioned C11 ABI, and Python as the reference user
   API.

## Decision

Use C++20 for native implementation. Expose opaque handles through a C11 ABI
with explicit ABI versioning, sized/versioned structures, explicit allocators,
structured diagnostics, capability negotiation, ownership/lifetime rules, and
documented thread safety. Build the Python 3.13 reference API on that boundary
while maintaining Python 3.12 compatibility.

## Evidence and constraints

This is a baseline architecture decision. E0 native ABI execution remains
`NOT_RUN` until the concurrent core lot is integrated; acceptance is not ABI
stability evidence.

## Consequences and risks

C consumers and bindings avoid C++ name mangling and standard-library ABI
coupling. The wrapper layer adds work and must prevent exceptions, allocator
mismatch, and dangling handles from crossing the boundary. Python must not
silently become a second semantic implementation.

## Reversibility and review trigger

Internal C++ components may change behind the ABI. Review structure layouts,
calling convention, or binding mechanism before the first v1 freeze, after a
sanitizer/lifetime failure, or when a second non-Python binding exposes a
contract defect.
