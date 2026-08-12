# Engine IR 0.1 synthetic replay corpus

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

## Summary

This corpus contains exactly 20 small, deterministic Morphoia Engine IR 0.1
manifests. It exists to test lexical, schema, semantic, native canonicalization,
identity, and replay contracts. It contains no patient, personal, proprietary,
clinical, or real-world source data.

## Provenance and license

- Producer: Morphoia project synthetic fixture generator, 2026-08-12.
- Method: programmatic construction from invented identifiers, names, hashes,
  timestamps, and metadata.
- Classification: synthetic/public.
- License: CC BY 4.0 for every file in this directory.
- Personal or medical data: none.
- External downloads: none.

Every manifest references invented payload identities. Those payload bytes do
not exist and are not evidence that STEP, Arrow, Zarr, or another domain format
was imported. Media types exercise only the Engine IR reference contract.

## Layout

- `index.json`: allow-list and SHA-256 inventory for 20 entries.
- `inputs/`: human-readable manifest inputs with terminal line feeds.
- `goldens/`: native Profile 1 canonical `content` bytes, with no terminal line
  feed.
- `replays/`: closed five-step deterministic replay recipes.
- `invalid/`: committed lexical, schema, and semantic rejection fixtures.
- `migration/`: frozen legacy bytes, explicit migration metadata, and an
  unsealed Engine content golden.

## Intended use

The corpus may demonstrate deterministic Engine IR contract replay only when
the declared native, Python, and CLI commands actually execute and agree with
all committed hashes. It must not be used to claim:

- CAD, DICOM, LAS/LAZ/COPC, MED, XAO, SALOME, GPU, or HPC compatibility;
- real payload resolution or safety;
- complete UCUM validation;
- cryptographic signature verification;
- MVX encoding, reconstruction, or scientific fidelity.

## Known limitations

The examples are small and structurally varied, not statistically
representative scientific data. Exact UUIDs and timestamps are artificial.
Payload URI/hash/size metadata is internally consistent but references no
distributed payload. The migration profile intentionally leaves most legacy
construction semantics inside the retained opaque source and declares those
losses.
