<!-- SPDX-FileCopyrightText: 2026 Olivier Ami -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Reproducible CI dependency locks

The lock files pin every Python package and accepted wheel digest used by the
Linux x86-64 CI profiles. CI installs them with both `--require-hashes` and
`--only-binary=:all:`; an unlisted dependency, version, or archive therefore
fails closed.

`engine-ci.lock` covers Python 3.12 and 3.13. Its two `rpds-py` hashes are the
CPython 3.12 and 3.13 manylinux2014 x86-64 wheels. `report-ci.lock` covers the
existing Python 3.12 report workflow. These locks are profile-specific and do
not claim portability to other operating systems or architectures.

`cmake-e0.lock` freezes the exact CMake 3.20.5 manylinux x86-64 wheel used to
exercise the declared minimum CMake version during the E0 audit. It is a
validation tool, not a runtime dependency of Morphoia Engine.

`reuse-e0.lock` freezes REUSE 6.2.0 and its runtime dependencies for the
Python 3.12 Linux license-metadata job. REUSE 6.2.0 is published as a source
distribution, so `reuse-build-e0.lock` separately freezes Poetry Core 2.4.1;
CI installs that build backend first and then builds REUSE with build isolation
disabled. Both installation steps remain hash-locked.

The requirements jobs do not assume that a GitHub-hosted image contains
Poppler. Catalogue replay consumes the hash-verified layout-text derivative in
`spec/requirements/`. The separate `--extract-pdf` provenance check was run
locally with `pdftotext 24.02.0` / `poppler-utils 24.02.0-1ubuntu9.9`; that
system package is not installed or treated as a Python lock dependency in CI.

Regeneration is a reviewed supply-chain change. Resolve in an isolated
environment, record exact download URLs and SHA-256 values, validate package
licenses and vulnerabilities, then run the affected workflow before merging.
