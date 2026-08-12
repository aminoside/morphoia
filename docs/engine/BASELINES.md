# Immutable baselines

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Verified: 2026-08-12

These files are inputs, not generated outputs. Do not edit, normalize, optimize,
recompress, or replace them in place. A new owner-validated edition receives a
new filename, hash, comparison report, and change-control decision.

| Baseline | Repository path | SHA-256 | Size | Pages | Verification |
|---|---|---|---:|---:|---|
| Technical specification v0.1 | `docs/engine/baselines/Morphoia_Engine_Cahier_des_charges_technique_v0.1.pdf` | `40cdb3288e7b1a38a557d1459147aed7ac1d5646aaa5d6ab09a287abc9b22263` | 257,770 bytes | 37 | PASS |
| Architecture reference v0.2 | `docs/engine/baselines/Morphoia_Engine_Architecture_Reference_v0.2.pdf` | `8519bba50ab9a05d469780ec074588034714d83d24ef09404705d292bfa02368` | 261,922 bytes | 39 | PASS |
| Official vector logo archive | `docs/engine/baselines/morphoia-logo-vectoriel.zip` | `d9957fb70c18f2cdea37b7a036e3ddab6b05492d1a3ea978f5ea9f33313c00c5` | 167,259 bytes | N/A | PASS |

The requirements replay also retains a versioned, non-normative layout-text
derivative at
`spec/requirements/Morphoia_Engine_Cahier_des_charges_technique_v0.1.layout.txt`.
Its stored SHA-256 is
`de8444574a59e1520222062587bc6c55f7184cf0e384d7d499f5ea24ad653175`
(173,815 bytes). Removing the repository text file's final line-feed after the
PDF form-feed reproduces the raw `pdftotext -layout` bytes with SHA-256
`e31699cb803edb1b86d01b04a230fd71418a5865965313bac376758f3e0f1a10`
(173,814 bytes). E0 produced those raw bytes with `pdftotext 24.02.0` from
Ubuntu package `poppler-utils 24.02.0-1ubuntu9.9`. The immutable PDF remains
authoritative; the derivative exists only for deterministic offline replay.

Hashes were calculated from the repository copies. PDF page counts were read
from PDF metadata. The first two digests exactly match the owner-declared
validated copies; the archive digest exactly matches the supplied copy.

## Normative use

The technical specification is normative for requirements, evidence, gates,
and deliverables. The architecture document supplies rationale. The official
logo archive supplies visual assets; it is not a software dependency and its
marks remain separate from the code license.

The owner explicitly instructed these exact baseline copies to be retained in
the project. Their inclusion does not relicense pre-existing material or any
third-party mark. Public derivatives must use the official Morphoia SVG and
palette (`#040B16`, gradient `#6DDFF5` to `#D795EF`) without creating a
Morphoia-SALOME composite mark.

## Verification commands

```bash
sha256sum docs/engine/baselines/*
pdfinfo docs/engine/baselines/Morphoia_Engine_Architecture_Reference_v0.2.pdf
pdfinfo docs/engine/baselines/Morphoia_Engine_Cahier_des_charges_technique_v0.1.pdf
python3 scripts/extract_engine_requirements.py --check
python3 scripts/extract_engine_requirements.py --check --extract-pdf
```
