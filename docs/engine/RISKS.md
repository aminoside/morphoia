# Risk register

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Last updated: 2026-08-12

Probability and impact are qualitative. A risk is closed only with retained
evidence; absence of a failure is not evidence of compatibility.

| ID | Risk | Probability | Impact | Mitigation and evidence trigger | State |
|---|---|---:|---:|---|---|
| R-001 | Scope expands into a CAD kernel, solver, AI framework, or renderer | Medium | Critical | Enforce anti-scope, require ADR and named user/maintainer for additions | Open |
| R-002 | Silent semantic or geometric loss | Medium | Critical | Mandatory provenance, repair and loss records; invariant and round-trip tests | Open |
| R-003 | Canonical JSON or CAS is nondeterministic | Medium | High | Golden vectors, locale/float tests, two clean replays, hash comparison | Open |
| R-004 | Public C ABI becomes unstable or unsafe | Medium | High | Sized/versioned structures, opaque handles, allocator/lifetime/thread tests | Open |
| R-005 | SALOME dependencies contaminate the core | Medium | Critical | Process boundary, dependency inspection, protocol-only contract, core linkage scan | Open |
| R-006 | Optional backend is claimed from mock or compile-only evidence | Medium | Critical | Five-status evidence model and per-profile compatibility matrix | Mitigated by policy |
| R-007 | LGPL/GPL/proprietary obligations are missed | Medium | Critical | Component-level license audit, dynamic package boundary, SBOM, redistribution hold | Open |
| R-008 | Patient or identifiable data enters Git/logs/artifacts | Low | Critical | Synthetic/licensed fixtures only, data cards, pixel/private-tag review, secret/PII scans | Open |
| R-009 | Malformed input causes traversal, bomb, exhaustion, or code execution | High | Critical | Size/type limits, safe archive handling, sanitizers, fuzzing, no untrusted dumps/plugins | Open |
| R-010 | No branch protection permits unreviewed integration | High | High | Lot branches, PR review, checks, explicit remote SHA verification; record noncompliance | Open |
| R-011 | Local CLI cannot publish the checkpoint | High | High | Use the available authenticated app after the local gate; checkpoint small units; verify remote SHA | Controlled |
| R-012 | Concurrent/user MVX work is overwritten | Medium | Critical | Preserve worktrees and unique commits; no stash/reset/cleanup; deliberate reconciliation only | Controlled |
| R-013 | Resource-heavy work exhausts the 54 GiB disk or 20 GiB RAM cgroup | Medium | High | Enforce 2 GiB/60 min/37.8 GiB preapproval caps and cancellable checkpoints | Controlled |
| R-014 | Missing CMake/domain/GPU/HPC runtimes delays gates | High | High | Keep CPU lot independent; isolate profiles; install only free, pinned dependencies within budget | Open |
| R-015 | MVX is invented before validated specification | Medium | Critical | Opaque SPI only; `mock_mvx` excluded from science; stop at `WAITING_FOR_MVX_SPEC` | Controlled |
| R-016 | Test thresholds are changed after observing outcomes | Medium | High | Preregister thresholds by ADR; preserve raw results; review fixture changes | Open |
| R-017 | Existing prototype semantics conflict with Engine requirements | Medium | High | Gap analysis, explicit migrations, no silent replacement of user-owned content | Open |
| R-018 | Dependency/action supply chain is compromised | Medium | Critical | Pin versions/hashes and Actions SHAs; minimal permissions; SBOM and vulnerability scan | Open |
| R-019 | Reproducibility claim exceeds one observed environment | High | High | Two clean builds; publish exact environment; keep ARM64/other OS as `NOT_RUN` | Open |
| R-020 | Research software is mistaken for a clinical product | Medium | Critical | Prominent research-only limitation; no diagnostic/medical-device claims | Controlled |
| R-021 | Legacy Phase 1/2 guides and documents remain French while the Engine public-language policy requires American English | High | Medium | Preserve their meaning, record the gap, and translate/version them in a bounded documentation lot before claiming full language-policy compliance | Open |

## Escalation triggers

Globally stop publication for a secret leak, identifiable medical data,
exploitable Sev 1/Sev 2 vulnerability in the delivered profile, global normative
contradiction, corrupted evidence, or inability to build the mandatory CPU
path. Other risks block only the affected component/profile.
