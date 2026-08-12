# Morphoia Engine agent guide

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

This file governs work in this repository. More specific `AGENTS.md` files may
add constraints for their subtree but may not weaken this guide.

## Mission and authority

Build Morphoia Engine as an open, headless interoperability, orchestration,
provenance, and evidence layer. Work only on `engine` or a bounded
`engine-p<phase>-<slug>` branch. Never push to or merge into the default branch
without a separate, explicit instruction from Dr Olivier Ami.

The current source-of-truth order is:

1. the owner's latest explicit instruction;
2. an owner-validated MVX specification, within its domain;
3. `docs/engine/baselines/Morphoia_Engine_Cahier_des_charges_technique_v0.1.pdf`;
4. `docs/engine/baselines/Morphoia_Engine_Architecture_Reference_v0.2.pdf`;
5. accepted records in `spec/adr/`;
6. `docs/engine/EXECUTION_PLAN.md`.

Never invent MVX behavior. Never lower a MUST, hide a loss, or report an
unexecuted backend as compatible.

## Required startup sequence

Before editing:

1. inspect the Git root, branch, upstream, remotes, status, untracked files,
   worktrees, and recent commits;
2. preserve all pre-existing or user-owned work; do not stash, move, delete,
   reset, or commit it silently;
3. read this file, `.agent/PLANS.md`, `docs/engine/EXECUTION_PLAN.md`,
   `docs/engine/STATUS.md`, `docs/engine/checkpoint.json`, and applicable ADRs;
4. verify baseline hashes against `docs/engine/BASELINES.md`;
5. run the smallest documented smoke test;
6. resume the `next_action` in `docs/engine/checkpoint.json` if it remains
   applicable.

The canonical integration branch is `refs/heads/engine`. The bootstrap work
branch is `refs/heads/engine-p0-bootstrap`. The canonical remote currently
recorded by E0 is `origin`; revalidate it every session rather than assuming it.

## Architecture invariants

- Native implementation: C++20. Public native boundary: versioned C11 ABI
  with opaque handles, sized/versioned structures, explicit allocation, and
  structured diagnostics.
- Reference user API: Python 3.13 while remaining compatible with Python 3.12.
- Data model: versioned Morphoia IR, canonical JSON for control metadata, and
  SHA-256 CAS references for payloads. Large payloads never travel inside
  control JSON.
- Preserve B-Rep, meshes, points, voxels, fields, tensors, and future MVX as
  distinct representations with units, frames, tolerances, authority,
  provenance, repairs, losses, and derivation links.
- DICOM remains authoritative for medical imaging. Only synthetic or clearly
  licensed public fixtures are allowed.
- SALOME 9.16 is an optional, isolated backend and differential oracle. No
  KERNEL, CORBA, Qt/PyQt, SALOMEDS, SALOME Python, or patched SALOME library may
  become a core dependency.
- STEP, XAO, MED, URI, size, and SHA-256 cross process boundaries. Native
  pointers and CORBA objects do not.
- The open-source CPU path is mandatory. CUDA, HIP, SYCL, MED, SALOME, and HPC
  claims are profile-specific and require execution on the named environment.
- Morphoia is research software, not a medical device, diagnostic system, or
  clinical product.

## Evidence language

Use only `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, or `NOT_APPLICABLE`.
Compilation-only, simulation, mocks, skips, and dry runs are not `PASS`.
Every compatibility statement must name hardware, OS, versions, command,
configuration, result, and evidence artifact. A mock SALOME or `mock_mvx`
adapter validates only its software contract.

## Development and Git discipline

- Prefer small, atomic, test-backed changes. Long or risky work belongs on a
  remote lot branch.
- Before each commit and push inspect status, full and staged diffs, file
  sizes, formatting, tests, secret scan, and `git diff --check`.
- Stage explicit paths only. Use Conventional Commits and cite requirement IDs.
- Fetch before pushing; never force-push, rewrite published history, use
  `--all`, use `--mirror`, or move/delete a published tag.
- Update execution state and evidence in the same atomic unit as the work.
- Do not commit build trees, caches, raw datasets, patient data, container
  images, mass logs, or regenerable large outputs.
- Do not install or activate paid services. Respect
  `docs/engine/RESOURCE_BUDGET.yaml` before any resource-intensive operation.

## Definition of done

A task is done only after code is integrated through the applicable review
path, required tests actually pass, documentation and limitations are current,
evidence is hash-addressed, licensing and security are checked, and its
requirement-to-test-to-evidence link exists. `BLOCKED` and `NOT_RUN` are never
done.
