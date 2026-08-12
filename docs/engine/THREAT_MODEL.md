# Morphoia Engine preliminary threat model

<!-- SPDX-FileCopyrightText: 2026 Olivier Ami -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Version: E0 bootstrap, 2026-08-12
Scope: source tree, native C ABI bootstrap, requirements pipeline, CI, CAS and
adapter architecture planned for the CPU profile

## Assets and security objectives

The protected assets are authoritative scientific bytes and metadata,
provenance/loss records, CAS integrity, build and release identity, credentials,
licensed assets, and any future medical metadata. The primary objectives are
no silent corruption or loss, no untrusted-code execution, bounded resource
use, explicit trust transitions, reproducible evidence, and exclusion of
secrets or identifiable patient data from public systems.

## Trust boundaries and data flow

1. Untrusted user inputs enter a headless CLI/Python/C API boundary.
2. Format adapters validate type, schema, declared size, units, frames, and
   limits before creating IR metadata or CAS objects.
3. The core stores control metadata and immutable hash-addressed references;
   a matching SHA-256 proves byte integrity, not safety or semantics.
4. Optional workers and plugins receive bounded manifests and URIs, execute in
   separate processes where required, and return new immutable artifacts plus
   provenance, repair, copy, synchronization, and loss records.
5. SALOME is a separate-runtime boundary. Only STEP/XAO/MED and bounded
   URI/size/hash control messages cross it; CORBA objects and native pointers do
   not.
6. CI and release publication consume repository-controlled scripts and pinned
   dependencies, then publish checksums/SBOM/evidence. Pull-request code is
   untrusted and receives no persistent checkout credential.

## Threats, controls, and current evidence

| Threat | Required control | E0 evidence/status |
|---|---|---|
| Path or symlink traversal | confine every URI/archive path to an allowed root; reject absolute and `..` entries | logo ZIP confinement/CRC test `PASS`; general input paths `NOT_RUN` |
| Archive/decompression bomb | compressed/uncompressed entry, ratio, count, and total-byte limits | small logo archive bounds `PASS`; general archives `NOT_RUN` |
| Integer overflow or memory exhaustion | checked size arithmetic, format limits, cancellable jobs, resource budget | resource policy `PASS`; adversarial parser tests `NOT_RUN` |
| C ABI misuse | opaque handles, sized/versioned structures, explicit UTF-8 lengths, allocator alignment, exception containment | native C/C++ smoke and ASan/UBSan `PASS`; LSan `NOT_RUN` |
| C++ symbol/exception leakage | hidden shared library and exact C export allow-list | direct shared bootstrap `PASS`; other platforms `NOT_RUN` |
| Silent scientific loss | authoritative representation retained; explicit repair/loss/provenance records | policy and legacy prototype inspection only; Engine IR path `NOT_RUN` |
| CAS substitution | rehash bytes and validate media/schema/size before consumption | architecture control only; Engine CAS `NOT_RUN` |
| Malicious plugin/model/dump | never auto-execute untrusted Python, SHAPER dumps, plugins, or serialized model code; isolate workers | policy only, plugin runtime `NOT_RUN` |
| CI credential theft | immutable Action SHAs, least privilege, no checkout credential retained, hash-locked wheels | workflow inspection `PASS`; hosted runs executed, with native/hygiene/REUSE `PASS` and requirements/report `FAIL` on missing `pdftotext` rather than credentials |
| Supply-chain substitution | exact versions and archive hashes, license inventory, SBOM, vulnerability scan | hash-locked installs, REUSE, and deterministic SBOM `PASS`; vulnerability scanners `NOT_RUN` |
| Secret or personal-data disclosure | synthetic/licensed fixtures only; scan source/logs/pixels/private tags and redact diagnostics | bounded text signature scan at E0; DICOM/pixel inspection `NOT_RUN` |
| Optional-backend overclaim | five evidence states with hardware/runtime/version provenance | evidence vocabulary and policy `PASS`; optional runtimes `NOT_RUN` |

## Abuse cases requiring tests

The E1/E3 hardening backlog must cover malformed sized structures, hostile
allocators, double/invalid handles, oversized lengths, invalid UTF-8, path and
symlink escapes, duplicate/poisoned CAS writes, truncated manifests, extreme
geometry and DICOM metadata, archive bombs, process timeouts, replay attacks,
and malicious capability responses. A framework skip, mock, compile-only run,
or policy inspection is not execution evidence.

## Residual risk and release rule

E0 is not a security certification. No general parser, CAS, DICOM, CAD,
point-cloud, plugin, or isolated-worker implementation exists yet. Static
analysis, bounded fuzzing, vulnerability scanning, LSan, and optional runtimes
remain `NOT_RUN`. Any reachable Sev 1/Sev 2, credential exposure, identifiable
medical data, or unexplained evidence corruption stops publication under
`SECURITY.md`.
