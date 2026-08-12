# Contributing to MORPHOIA

MORPHOIA is a public research repository led by Olivier Ami. Licensing is
file- and component-specific: legacy prototype code remains MIT; new original
Engine code is Apache-2.0 OR MIT; new original Engine documentation is CC BY
4.0; baselines, fonts, and brand assets retain their recorded terms. Review
`REUSE.toml`, `NOTICE`, and `DEPENDENCIES.md` before contributing or
redistributing content.

## Contribution rules

1. Open an issue describing the need, affected standards, and acceptance criteria.
2. Work on a dedicated branch; do not push directly to the default branch.
3. Preserve bibliographic references and data provenance.
4. Add or update tests for every code change.
5. Report semantic losses, ambiguities, repairs, and proprietary dependencies explicitly.
6. Never include confidential industrial data, patient data, secrets, or credentials.
7. Obtain domain review for normative, geometry, patent, or licensing changes.
8. Add an ADR for every structural architecture decision.
9. Add a component justification before duplicating or replacing an existing solution.
10. Distinguish implemented, specified, experimental, and planned behavior.
11. Sign every commit under the [Developer Certificate of Origin](DCO.md) with `git commit --signoff`; never sign as another person.

## PDF documents and MORPHOIA identity

Every new repository PDF must follow MORPHOIA visual identity version 1.0
and retain `Olivier Ami` as the document author. Contributors remain credited
through their commits and, when appropriate, a contributions section.

New PDFs must:

1. use the official masters in `assets/brand/` without modifying or rasterizing them;
2. use the shared `reporting/morphoia_brand.py` theme;
3. embed Aldrich and Barlow without font substitution;
4. be declared in `reports.json` with their generator and validator;
5. be rebuilt and verified by `make check` before a pull request.

CI rejects any tracked PDF that is undeclared or nonconforming.

Exception: the two immutable normative PDFs explicitly registered under
`docs/engine/baselines/` are hash-addressed evidence inputs, not generated
reports. They are not rebuilt, rebranded, or added to `reports.json`; CI checks
their exact allow-list and digests separately. Every other PDF, including one
placed in that directory, must be in the report manifest or the check fails.

## Authorship

Olivier Ami remains the author and initiator of MORPHOIA. Contributors retain
attribution for their commits and specific contributions.

## Phase 1 and the Phase 2 candidate

Phase 1 forbids prematurely designing a new language. Every representation or
architecture proposal must connect to the feasibility study, existing
standards, and a demonstrated gap.

The Phase 2 textual facade and IR are experimental. No contribution may call
them a stable standard before P1/P2 execution on two independent backends,
public conformance, and measured industrial benefit.
