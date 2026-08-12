# E1 public Engine IR 0.1 evidence report

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Date: 2026-08-12
Profile: `e1-public-ir-core-cpu`
Source base: `c475288961d40bb16c4cc10a333034a247acb451`
Lot: `public-ir-0.1-and-20-graph-replay`
Status: `PASS` for the bounded core-CPU profile; unresolved requirements remain `NOT_RUN`

## Scope

This report covers the distinct public Morphoia Engine IR manifest 0.1.0
identity domain proposed by ADR-020. The executed profile includes strict
lexical, JSON Schema Draft 2020-12, and semantic validation; the native
Canonical JSON Profile 1 C ABI; the required-native Python binding; explicit
legacy migration; deterministic replay; and a small synthetic 20-graph
corpus.

The profile does not reinterpret the legacy prototype schema or serializers.
It does not define MVX. It does not establish format-import support from the
synthetic representation kinds. It excludes real SALOME, GPU workers, remote
CAS, domain-format imports, a greater-than-2-GiB artifact, and vulnerability
analysis.

## Entry and inventory boundary

The lot starts from published checkpoint
`c475288961d40bb16c4cc10a333034a247acb451`. The prior E0 and E1 native
evidence profiles remain immutable and were validated byte-for-byte during
this gate. E2 remains a separate SALOME protocol-contract profile; real SALOME
execution is still `NOT_RUN`.

The closed public-IR inventory contains 123 entries: 39 bounded public-IR
source, test, build, workflow, and evidence files; four byte-frozen E1 native
evidence files; 79 synthetic CC BY 4.0 corpus/data-card files; and the
self-hashed CycloneDX document. The fixture tree contains 13 declared invalid
cases and has aggregate digest
`9647bf7be7c40dd39ea533b0677fc09d42eabcdee59b8b5adc5cbdc23f1e25af`
over sorted relative path, NUL, file SHA-256 hex, and line feed records.

All fixture payload references are invented metadata. The referenced payload
bytes do not exist in this corpus. Consequently the profile does not claim a
successful B-Rep, point-cloud, voxel, or other domain-format import.

## Execution record

Exact commands and truth-valued results are retained in
`spec/evidence/e1-public-ir-traceability.json`.

| Check | Status | Executed result and boundary |
|---|---|---|
| Public-IR corpus and Python lot | `PASS` | 20/20 corpus entries; 60/60 contract, migration, native binding, replay, and CLI tests |
| Direct native bootstrap | `PASS` | C ABI, canonical JSON, core, SHA-256, POSIX CAS, and native 20-graph replay |
| Two fresh local clone builds | `PASS` | Strict Debug build/install; native CTest 7/7 and installed consumer 1/1 in each clone |
| AddressSanitizer and UndefinedBehaviorSanitizer | `PASS` | Bounded native suite; LeakSanitizer is `NOT_RUN` |
| Installed-wheel smoke | `PASS` | Origin, validation, replay, and migration from an isolated install |
| Distribution build reproducibility | `NOT_RUN` | Observed setuptools 83.0.0 and wheel 0.47.0; `setuptools>=77` is not hash-locked |
| Python 3.12 | `PASS` | CPython 3.12.13 |
| Python 3.13 | `NOT_RUN` | Hosted matrix is configured but was not executed in this local gate |
| E0, frozen E1, and E2 evidence validators | `PASS` | Exact validators rerun without mutating frozen bytes |
| Ruff, requirements replay, REUSE, secret signatures, whitespace | `PASS` | Executed on the frozen working tree |
| Deterministic public-IR manifest and SBOM | `PASS` | Closed allowlist, exact hashes, provenance DAG, SBOM self hash, and 21/21 evidence tests verified |
| Vulnerability analysis | `NOT_RUN` | Inventory generation is not a vulnerability assessment |

The two fresh clones were local clones of the source-base repository with the
frozen A/B/C working-tree lot applied before either build. They are evidence
for two independent clean builds of these exact prospective bytes, not clones
of a future remote commit.

## Requirement truth boundary

The profile-specific traceability file maps exactly 49 requirements.
Thirty-two bounded claims are `PASS`; 17 broader requirements remain
`NOT_RUN`. The global `spec/requirements/requirements-tracking.yaml` file is
kept byte-exact at its E0 all-`NOT_RUN` baseline because frozen E0 evidence and
tests consume that byte identity. Making the global overlay safely evolvable
requires a separate change control that revises its frozen consumers together;
this is recorded as integration debt, not silently bypassed here. A passing
sub-claim never promotes its broader MUST:

- `MOR-IR-003` remains `NOT_RUN`: the identity/revision/content envelope is
  tested on 20 synthetic manifests, not every Morphoia object.
- `MOR-IR-005` remains `NOT_RUN`: reference fields and mismatch rejection are
  tested, but the referenced payload bytes are absent and all references were
  not resolved.
- `MOR-IR-006` remains `NOT_RUN`: exact positive SI factors are checked, but a
  complete UCUM code/dimension/factor evaluator is absent.
- `MOR-IR-011` remains `NOT_RUN`: `opaque` is not a separately typed MVX
  representation and no owner-validated MVX specification exists.
- `MOR-API-006`, `MOR-API-011`, `MOR-API-012`, and `MOR-API-014` remain
  `NOT_RUN` respectively for incomplete per-family thread-safety
  documentation, absent progress/complete terminal state, absent accepted
  idempotency key, and incomplete package/API/protocol SemVer proof.
- `MOR-DEV-003`, `MOR-DEV-010`, `MOR-DEV-011`, `MOR-DEV-012`, and
  `MOR-DEV-014` remain `NOT_RUN` for Python 3.13, complete native ownership
  inspection, static typing, hash-locked build backend, and final committed
  public-tree policy evidence.
- Only the frozen and rerun `MOR-CAS-001`, `MOR-CAS-003`, `MOR-CAS-004`, and
  `MOR-CAS-008` claims are promoted. `MOR-CAS-006`, `MOR-CAS-010`, and
  `MOR-CAS-012` remain `NOT_RUN` for missing distinct cache/backend roles,
  external-URI adapter, and a persisted transformed CAS block with provenance.
- `MOR-QA-013` remains globally `NOT_RUN`: 20 IR graphs establish one
  sub-criterion, while STEP, SMESH, MED, and three greater-than-2-GiB segments
  were not executed.

The generator enforces the exact requirement order, approved claims,
statuses, test-ID tuples, evidence-path tuples, and blocking scopes. Python
test IDs must exist uniquely in parsed allowlisted test sources. Native test
IDs must exist in the allowlisted CTest registrations. Evidence paths are
confined with dirfd traversal and `O_NOFOLLOW`, require regular single-link
files, and are hashed. Duplicate JSON keys, floats, non-finite constants,
unsafe integers, and lone surrogates fail closed in the evidence profile.

## Evidence publication and supply-chain boundary

The manifest and SBOM generator uses a literal allowlist. It rejects missing
or extra corpus files, aliases, hard links, traversal, byte drift, mismatched
licenses, duplicate identifiers, dangling or cyclic provenance, altered
frozen E1 evidence, and traceability permutations. Output publication uses
dirfd-confined temporary files and Linux `renameat2`; mutation tests cover
absent-target creation, inode swap, in-place mutation before and after final
revalidation, alias targets, temporary-name collision, restoration, and
cleanup.

The CycloneDX file is an inventory. Its root metadata and every artifact state
that vulnerability analysis is `NOT_RUN`. Dependency license review also
remains `NOT_RUN`; REUSE metadata success is not a dependency license audit.
The installed-wheel command is a functional smoke only, because the build
backend version is observed rather than hash-locked.

## Reproduction

From the repository root on the declared Linux x86-64 core-CPU profile:

```bash
cmake --preset engine-cpu-debug
cmake --build --preset engine-cpu-debug --parallel 2
ctest --preset engine-cpu-debug --output-on-failure
MORPHOIA_ENGINE_LIBRARY="$PWD/build/engine-cpu-debug/libmorphoia_engine.so" \
  bash scripts/validate-engine-ir-lot.sh
MORPHOIA_BOOTSTRAP_FORCE_FALLBACK=1 bash scripts/bootstrap-engine.sh
bash scripts/run-engine-sanitizers.sh
MORPHOIA_ENGINE_LIBRARY="$PWD/build/engine-cpu-debug/libmorphoia_engine.so" \
  bash scripts/validate-engine-wheel.sh
python scripts/extract_engine_requirements.py --check
python scripts/validate_engine_e0_evidence.py
python scripts/validate_engine_e1_native_evidence.py
python scripts/generate_engine_e2_sbom.py --check
python scripts/generate_engine_e1_public_ir_sbom.py --check
python -m unittest -v tests.test_e1_public_ir_evidence
python -m reuse lint
bash scripts/scan-secrets.sh
git diff --check
```

The deterministic manifest and CycloneDX SBOM are retained at
`artifacts/manifests/engine-e1-public-ir.json` and
`artifacts/sbom/engine-e1-public-ir.cdx.json`. The manifest contains the SBOM
byte hash. This report does not embed its own manifest hash, avoiding a
circular self-claim.

## Suspended and external claims

- MVX codec, reconstruction, golden vectors, and scientific validation:
  `BLOCKED` outside this profile by the missing owner-validated specification.
- Real SALOME 9.16, SHAPER/GEOM, SMESH, MED, differential comparison, and a
  real greater-than-2-GiB transfer: `NOT_RUN`.
- CUDA, HIP, SYCL, Slurm, EuroHPC, and optional domain libraries: `NOT_RUN`.
- Remote/object CAS, external URI resolution, CAS garbage collection,
  resumable transfer, and replication: `NOT_RUN`.
- Vulnerability analysis and LeakSanitizer: `NOT_RUN`.
- Clinical, diagnostic, or medical-device claims: `NOT_APPLICABLE`; Morphoia
  Engine remains research software.
