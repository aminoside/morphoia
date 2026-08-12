# Dependency policy and E0 inventory

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Last updated: 2026-08-12

The base distribution must remain fully open source and usable through its CPU
path without proprietary software. Dependencies are accepted component by
component after version, provenance, license, linkage, redistribution,
vulnerability, and reproducibility review. Process isolation is not a license
exception.

## Observed repository/runtime inventory

| Component | Role | Observed status | License/audit state |
|---|---|---|---|
| Python 3.12 standard library | Existing prototype and tests | Executed | PSF license; external system tool, not a shipped Engine dependency |
| GCC 13 / libstdc++ / OpenMP | Available compiler/runtime | C++20/OpenMP and shared-ABI tests PASS | Toolchain/system dependency; source SBOM does not claim system package closure |
| Existing Python package | Prototype parser/runtime/CLI | Unified 50-test suite and CLI smoke PASS | Pre-existing package remains MIT; ADR-017 separates its version from Engine |
| `jsonschema` 4.25.1 and transitive wheels | Schema-test helper | Hash-locked install and Draft 2020-12 tests PASS | Test-only, exact wheels/hashes inventoried; component license/vulnerability audit remains NOT_RUN |
| CMake 3.20.5 | Minimum build-system validation | Hash-locked tool, configure/build/install/consumer PASS | Validation tool only; not a runtime dependency |
| REUSE 6.2.0 plus Poetry Core 2.4.1 build backend | License-metadata validation | Separate hash-locked build/runtime installs and 161-file lint PASS | Development-only; exact inputs inventoried, vulnerability audit remains NOT_RUN |
| Poppler `pdftotext` 24.02.0 (`poppler-utils` 24.02.0-1ubuntu9.9) | One-time and explicit PDF-to-layout provenance check | Local `--extract-pdf` byte comparison PASS; absent on the observed hosted runner | System validation tool only; CI replays the hash-verified retained extraction, vulnerability audit remains NOT_RUN |

## Planned Engine dependency boundaries

| Component family | Intended boundary | Profile | Current evidence | License control |
|---|---|---|---|---|
| OCCT/XDE | Direct native adapter | cad | NOT_RUN | LGPL-2.1 with exception; exact release and notices require audit |
| VTK | Direct adapter/headless output | scientific | NOT_RUN | BSD-3-Clause; exact release audit required |
| ITK plus DICOM library | Direct medical adapter | medical | NOT_RUN | Select exact stack and audit transitive codecs before redistribution |
| PDAL plus LAS/LAZ/COPC codecs | Direct point adapter | points | NOT_RUN | Audit PDAL and each codec separately |
| MEDCoupling/MEDLoader | Separate dynamically linked package | med | NOT_RUN | LGPL boundary and MED-file dependencies require component audit |
| SALOME 9.16 | Isolated external process | salome | NOT_RUN | Audit modules, image, patches, prerequisites, and redistribution separately; exclude MeshGems |
| Kokkos | Shared worker sources | compute | NOT_RUN | Apache-2.0 with LLVM exception; exact release audit required |
| DLPack | External tensor interchange | ai | NOT_RUN | Header/version/license and lifetime behavior require audit/test |
| Apache Arrow C Data/Device | External columnar/device interchange | ai | NOT_RUN | Apache-2.0; exact components and linkage require audit |
| PyTorch / ONNX Runtime | External runtimes | ai | NOT_RUN | Optional; audit wheel/binary/provider licenses separately |
| Slurm, Spack, Apptainer, ADIOS2 | External HPC tooling/formats | hpc | NOT_RUN | Recipes and each redistributed artifact require audit |
| PETSc/MFEM | Optional solver adapters | compute | NOT_RUN | Exact configuration and transitive solver licenses require audit |
| OpenUSD, ANARI, Vulkan, Hydra | Optional visualization/scene adapters | render | NOT_RUN | Never infer compatibility across the family; audit individually |
| CUDA/cuDNN and proprietary CAD SDKs | User-installed external backend | proprietary | NOT_RUN | Must not enter the OSS base distribution or become mandatory |

## Admission checklist

Before adding a dependency: document the reuse rationale and alternatives;
select an exact version; pin source/binary integrity; record SPDX identity and
notices; inspect transitive dependencies and codecs; determine static/dynamic/
process linkage; scan known vulnerabilities; add an offline/reproducible install
path where applicable; update the SBOM; and execute the relevant profile tests.

No copied third-party code, untrusted install script, unpinned GitHub Action, or
unclear redistributable binary may be merged into the shipped profile.
