# Morphoia Engine governance

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Morphoia Engine is an open research and engineering project initiated and owned
by Dr Olivier Ami. Governance favors traceable technical evidence, open CPU
portability, and reversible decisions.

## Roles

- **Project owner:** sets mission, normative scope, public positioning, and
  stable-release/merge authority.
- **Maintainers:** review and integrate bounded lots, preserve architecture and
  evidence, triage security and licensing issues, and keep releases
  reproducible. Appointment is explicit; no maintainer other than the owner is
  inferred by this document.
- **Contributors:** propose changes through issues and pull requests, sign off
  commits under `DCO.md`, and provide tests, provenance, and license data.
- **Release reviewer:** verifies the gate report, SBOM, vulnerabilities,
  checksums, and remote SHA. This role may be filled by a maintainer but must be
  recorded for each release.

## Decisions

Normative sources are ordered in `AGENTS.md`. Structural decisions require an
ADR with context, alternatives, evidence, consequences, risks, reversibility,
and a review trigger. An ADR cannot waive corruption, silent loss, personal
data, an exploitable critical vulnerability, or a license obligation.

Technical choices that are reversible, free, legal, and within approved scope
may be made by the active engineering lead. New spending, contracts, data
governance, destructive history changes, default-branch merges, stable
releases, and unresolved normative conflicts require the owner's explicit
decision.

## Branches and review

`engine` is the integration branch. Long or risky work uses
`engine-p<phase>-<slug>`. The default branch is never a work branch. Published
history is not rewritten and tags are not moved.

No branch protection or ruleset was observed during E0. Until independently
verified otherwise, PR review, green checks, atomic commits, and explicit remote
SHA verification are compensating controls. They do not constitute proof of a
protected branch.

## Releases

Technical checkpoints and pre-releases may be made from `engine` after the
declared profile passes its checklist. They must state executed hardware and
profiles, failed/blocked/not-run checks, limitations, SBOM, checksums, and
evidence. A pre-MVX release is not G1. A stable GitHub Release and any merge of
`engine` into the default branch require separate owner approval.

## Conduct and conflicts

Participants follow `CODE_OF_CONDUCT.md`. Material conflicts of interest,
third-party obligations, and affiliations that could imply endorsement must be
disclosed. Morphoia must not imply endorsement by SALOME, EDF, CEA, Open
Cascade, or any other external organization.

## Changes to governance

Governance changes use a reviewed pull request and an ADR when they alter roles,
decision rights, release authority, licensing, or conformance. Current facts and
gaps must not be rewritten retroactively.
