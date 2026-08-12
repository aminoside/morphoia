# Security policy

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

## Supported versions

No stable security-supported release exists during E0. Each pre-release must
declare its delivered profile and support window. Unreleased branches are not a
security compatibility promise.

## Reporting a vulnerability

Prefer GitHub's private vulnerability reporting or a private security advisory
for `Aminoside/morphoia`. If that channel is not enabled, open a minimal public
issue requesting a private contact without including exploit details, secrets,
patient data, or sensitive logs. Do not test against systems or data you do not
own or have explicit authority to test.

Include affected commit/version, environment, reachable attack path, impact,
minimal safe reproduction, suggested mitigation if known, and whether sensitive
data may already be exposed. Maintainers will acknowledge when a private channel
is available; no fixed response SLA is promised during pre-alpha development.

## Severity taxonomy

- **Sev 1 — critical:** reliable remote code execution; repository/release
  signing compromise; exposed live credential; identifiable medical-data leak;
  silent corruption capable of invalidating authoritative data at scale; or a
  comparably catastrophic, reachable impact.
- **Sev 2 — high:** reachable local code execution from an untrusted supported
  input; sandbox/container escape; path traversal with material overwrite or
  disclosure; denial of service with practical severe resource exhaustion;
  privilege boundary bypass; or silent material integrity/provenance failure.
- **Sev 3 — moderate:** constrained availability, integrity, or disclosure issue
  requiring uncommon preconditions or affecting a non-authoritative output.
- **Sev 4 — low:** defense-in-depth weakness with no demonstrated material
  impact.

Any exploitable Sev 1 or Sev 2 in the delivered profile blocks a release.
Pre-existing, development-only, unreachable, or out-of-diff alerts are retained
with evidence and are not described as fixed. A secret or identifiable data
leak stops all publication until contained and assessed.

## Security boundaries

- Treat CAD, DICOM, point-cloud, mesh, archive, job-bundle, model, plugin, and
  SALOME inputs as untrusted.
- A SHA-256 CAS digest authenticates bytes, not safety. Validate schema, media
  type, size, dimensional limits, and declared profile before consumption.
- Do not execute untrusted SHAPER dumps, Python, plugins, serialized model code,
  project scripts, or shell fragments.
- Prevent path traversal, symlink escape, archive bombs, decompression bombs,
  integer/size overflow, excessive topology, and memory exhaustion.
- Containers should be non-root, read-only, capability-minimized, and
  egress-restricted when the runtime permits.
- SALOME is isolated out of process. No CORBA object, native pointer, or SALOME
  runtime dependency crosses into the core.

## Medical and personal data

Only synthetic or explicitly governed public fixtures may enter the repository,
CI, shared CAS, or public evidence. Tag removal is insufficient. Review pixels,
burned-in text, private tags, UIDs, overlays, SR, SEG, per-frame metadata, and
relationships. Logs must be sanitized. Real patient data requires a separate
authorization covering legal basis, ethics, hosting, retention, and access.

## Supply chain and release controls

Pin dependencies by version and integrity hash when supported. Never use
`curl | bash`. Pin third-party GitHub Actions to immutable commit SHAs with
minimal permissions and no secrets exposed to external pull requests. Generate
and inspect an SBOM, scan secrets/licenses/vulnerabilities, run static analysis,
sanitizers and bounded fuzzing, and verify release checksums and remote commit
identity before publication.
