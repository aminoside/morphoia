# E0, E1 native/public-IR, and E2 protocol compliance matrix

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Snapshot: 2026-08-12
Declared profiles: E0 audit/bootstrap, integrated bounded E1 native core,
locally executed E1 public IR 0.1 replay, and E2 SALOME protocol contract on Linux
x86-64 CPU

The complete 320-item catalogue is machine-readable in
`spec/requirements/requirements.yaml`. This view records E0 gate evidence plus
the bounded E1 native, public-IR entry, and E2 contract profiles. It does not
replace the complete per-requirement links and does not assert G1-G5
completion.

| Control | Component/lot | Test or inspection | Evidence | Status |
|---|---|---|---|---|
| Correct public repository and default branch | E0 audit | remote/repository inspection | `STATUS.md` | PASS |
| Canonical remote verified | E0 audit | remote URL and permission inspection | `checkpoint.json` | PASS |
| User changes and worktrees preserved | E0 audit | worktree and ref inspection | `RISKS.md` R-012 | PASS |
| Bootstrap work isolated from default branch | E0 Git | branch/upstream inspection | `engine-p0-bootstrap` | PASS |
| Protected integration branch | Governance | ruleset/protection inspection | inspection executed; no protection observed | FAIL |
| Authenticated checkpoint publication | Publication | app publication and remote tree verification | corrective source checkpoint `8b41fa8435e5812b5bd10ae92e35878d9803e0bc` and PR #4 published | PASS |
| Hosted corrective checks | Publication | GitHub Actions runs `31581879387`, `31581879373` | corrective source SHA `8b41fa8435e5812b5bd10ae92e35878d9803e0bc`: Python 3.12/3.13, hygiene, native GCC/C++20, REUSE, and report jobs all passed | PASS |
| E0 integration into `engine` | Publication | PR #4 merge inspection | merge `7715a7f7897a3058473732915e372b9835317d17`, tree `1a2c31b55e284edd521616c3fec7a7f017b883eb`, parents `fcee715a…` + `66a3526…` | PASS |
| Hosted `engine` push checks | Publication | GitHub Actions run `31582827407` | merge SHA `7715a7f…`: native, Python 3.12/3.13, hygiene, and REUSE jobs all passed | PASS |
| Initial branches/tags/PR/releases/workflows audit | Hosted-state audit | connector inspection | no Engine refs/releases; unrelated PR #3 preserved; existing report workflow observed | PASS |
| GitHub Actions/artifact/LFS/API quotas | Capability | quota inspection | connector did not expose limits; no paid capacity assumed | NOT_RUN |
| Network capability | Capability | environment policy and connector probe | restricted allowlist plus authenticated repository connector | PASS |
| Technical specification bytes | Baselines | SHA-256 plus PDF metadata | `BASELINES.md` | PASS |
| Architecture bytes | Baselines | SHA-256 plus PDF metadata | `BASELINES.md` | PASS |
| Official visual archive bytes | Baselines | SHA-256 | `BASELINES.md` | PASS |
| 320 requirements present and IDs unique | Requirements | Python standard-library structural smoke | 320 unique `MOR-*` IDs | PASS |
| Requirements catalogue conforms to its JSON Schema | Requirements | Draft 2020-12 validator | hash-locked `jsonschema` 4.25.1 on Python 3.12 | PASS |
| Requirement-to-component/test/evidence links complete | Traceability | catalogue/matrix inspection | mapping lot incomplete | NOT_RUN |
| Durable human-readable state | Governance | file inspection | plan, status, decisions, risks | PASS |
| Durable machine-readable state | Governance | fail-closed validators plus mutation tests | checkpoint, manifest and schemas | PASS |
| Resource limits recorded | Capability | probe-to-budget comparison | `RESOURCE_BUDGET.yaml` | PASS |
| Existing Python unit baseline | Existing prototype | targeted modules with `PYTHONPATH=src` | 14 tests executed | PASS |
| Existing CLI smoke | Existing prototype | CLI help/smoke | successful invocation | PASS |
| Native C++20 direct-compiler bootstrap | Engine core | `./scripts/bootstrap-engine.sh` fallback | ABI and core smoke executed with GCC/G++ 13 | PASS |
| Native CMake/CTest bootstrap | Engine core | CMake 3.20.5 configure/build/test | two CTests, install and external C consumer | PASS |
| Unified test discovery | Bootstrap | `PYTHONPATH=src <locked-python> -m unittest discover -s tests -v` | 184 tests on the local public-IR checkpoint | PASS |
| E1/E2 foundations integrated into `engine` | Publication | PR #7 merge inspection | merge `12656708ccc3031670c4b3efd43996e46fa27998`, tree `9c21bc6544ee41c084208412805e93dbd5a85e70`, parents `c84dd152…` + `4eacd006…`; default branch unchanged | PASS |
| E1/E2 exact-merge hosted checks | Publication | Engine run `31593999716` | native `94105119978`, Python 3.12 `94105119984`, REUSE `94105120004`, hygiene `94105120031`, and Python 3.13 `94105120081` passed | PASS |
| Public-IR lot branch and entry bootstrap | E1 public IR | branch/base inspection plus direct CPU bootstrap | `engine-p0-public-ir-replay` starts from exact merge `12656708`; entry smoke passed | PASS |
| Public-IR entry checkpoint validation | E1 public IR | frozen-profile validators, full Python/report/native/license/hygiene suites | 102/102 Python tests, native five-test bootstrap, REUSE 194/194, reports, requirements, secret and diff checks passed | PASS |
| Public-IR entry checkpoint hosted validation | E1 public IR | PR #8 exact-head workflows | Engine `31596165398` passed five jobs; report `31596165378`, job `94112106640`, passed on `a69d35b5` | PASS |
| Public Engine IR 0.1 local implementation | E1 public IR | schema, native/Python/CLI, semantic validation, and migration | bounded Linux x86-64/CPython 3.12 profile passed; ADR-020 remains proposed pending publication/integration | PASS |
| Public Engine IR 20-graph replay | E1 public IR | canonical input/golden corpus replay | 20/20 graphs passed native/Python byte and digest agreement, two workspaces, and checkpoint resume | PASS |
| Public-IR evidence profile | E1 public IR | exact manifest/SBOM/traceability and mutation tests | 32 bounded PASS, 17 broader NOT_RUN, 123 artifacts, 140 CycloneDX components, 22/22 evidence tests | PASS |
| Public-IR first implementation hosted attempt | Publication | exact `5ee8cebc` workflows | report passed; Engine native/hygiene/REUSE and Python 3.12/3.13 tests passed, but both Python jobs failed at the wheel smoke because setuptools was absent | FAIL |
| Public-IR final publication and hosted checks | Publication | corrective exact commit, PR #8, report, review and integration | correction and exact-head replay pending | NOT_RUN |
| Legacy prototype bytes at public-IR entry | E1 public IR | SHA-256 inspection of five declared files | exact hashes recorded in ADR-020 and `STATUS.md`; files are non-authoritative for Engine identity | PASS |
| Immutable normative PDFs excluded from report branding | Baselines/reporting | tracked-report manifest test plus full `make check` | two Engine baseline PDFs remain hash-identical and outside generated-report policy | PASS |
| Second clean bootstrap | Reproducibility | two isolated direct GCC/G++ builds/tests | both executions passed | PASS |
| ASan/UBSan smoke | Security | fail-fast sanitizer script | two native executables | PASS |
| LeakSanitizer | Security | leak detection | deliberately disabled; environment limitation retained | NOT_RUN |
| Secret/sensitive-data scan of E0 diff | Security | bounded fail-closed text signature scan plus binary/hash inspection | no supported signature; not a full PII audit | PASS |
| E0 SBOM | Supply chain | deterministic CycloneDX generator/check | source, artifacts and hashed locks inventoried; vulnerability analysis NOT_RUN | PASS |
| Repository license metadata | Supply chain | hash-locked REUSE 6.2.0 lint | 299/299 public-IR worktree files resolved; component vulnerability analysis NOT_RUN | PASS |
| Public English language policy | Documentation | repository-language inspection | root README and contribution guide are English; legacy Phase 1/2 guides/documents remain French under R-021 | FAIL |
| SALOME 9.16 headless | Optional SALOME | real runtime probe | runtime absent | NOT_RUN |
| CUDA, HIP, and SYCL execution | Optional compute | real hardware execution | hardware/runtime absent | NOT_RUN |
| Container and Slurm execution | Optional HPC | real runtime execution | tools absent | NOT_RUN |
| EuroHPC execution | Optional HPC | platform job evidence | access absent | NOT_RUN |

## Evidence interpretation

`FAIL` for branch protection means inspection executed and the required
condition was absent; compensating PR discipline is documented separately.
A mock, static generator, compiled object, or alternative backend cannot upgrade
an unavailable optional profile to `PASS`.

## E1 public Engine IR 0.1 local profile

| Control | Requirement(s) | Test or inspection | Evidence | Status |
|---|---|---|---|---|
| Distinct versioned public identity domain | MOR-IR-001, MOR-IR-002 | schema/constant agreement across native, Python, CLI, and docs | Draft 2020-12 and Profile 1 contract tests passed; ADR-020 remains proposed until integration | PASS |
| Profile 1 content identity | MOR-IR-002, MOR-CAS-001 | `SHA-256(canonical_profile_1(content))` cross-language golden tests | 20/20 exact native/Python canonical bytes and digests | PASS |
| Native lexical rejection precedes schema validation | MOR-IR-002, MOR-API-003 | duplicate-key, UTF-8, surrogate, numeric, and resource-limit mutations | native and Python mutation suites passed | PASS |
| JSON Schema then bounded semantic validation | MOR-IR-001 | structural and graph-invariant positive/negative corpus | schema and bounded graph invariants passed | PASS |
| Complete UCUM code/dimension/factor validation | MOR-IR-006 | semantic unit registry evaluation | positive exact SI factors were checked, but no complete UCUM evaluator ran | NOT_RUN |
| Lowercase UUIDv7 logical identifiers | MOR-IR-004 | syntax, normalization, collision, and reference-integrity mutations | executed positive and negative tests | PASS |
| Immutable payload reference field sub-claim | MOR-IR-005, MOR-CAS-001, MOR-CAS-003 | exact URI inversion, size/digest, and inline-payload rejection | field and mismatch tests passed | PASS |
| Every payload reference is resolvable | MOR-IR-005 | resolve all declared payload bytes | corpus contains invented metadata references and no payload bytes | NOT_RUN |
| Reverse-DNS-only extensions | MOR-API-018 | unknown core field, round-trip, and invalid extension-key mutations | executed positive and negative tests | PASS |
| C ABI limited to capability and canonicalization additions | MOR-DEV-002, MOR-API-001, MOR-API-002 | exact seven-symbol export list, sized/versioned structs, installed C consumer | two clean build/install/consumer executions plus hostile ABI tests | PASS |
| Reference Python requires the native library on 3.12 | MOR-DEV-003, MOR-API-004, MOR-API-005 | loader-path, absent-library, allocator/lifetime, and no-fallback tests | CPython 3.12.13 passed | PASS |
| Reference Python 3.13 target | MOR-DEV-003 | hosted matrix execution | configured but not locally executed | NOT_RUN |
| Explicit legacy migration with provenance and losses | MOR-API-015, MOR-IR-012, MOR-SCP-004 | migration golden and mutation tests | input bytes preserved, four declared losses, native sealing and semantic validation passed | PASS |
| Legacy prototype remains byte-exact and non-authoritative | Component-version boundary | SHA-256 inspection at lot entry | all five hashes in ADR-020 and `STATUS.md` match | PASS |
| MVX codec, reconstruction, thresholds, or semantics | MVX change-control boundary | scope inspection | explicitly outside this bounded lot; no MVX capability claimed | NOT_APPLICABLE |
| Greater-than-2-GiB public-IR payload execution | Resource-gated CAS profile | real payload create/store/read/replay | no payload executed | NOT_RUN |
| Complete G1/P0 corpus | MOR-QA-013 | 20 IR plus STEP, SMESH, MED and three >2-GiB segments | only 20 synthetic IR graphs executed | NOT_RUN |

## E2 SALOME protocol-only profile

| Control | Requirement(s) | Test or inspection | Evidence | Status |
|---|---|---|---|---|
| Core remains independent from SALOME runtime imports | MOR-ARC-002 | forbidden-import inspection | `tests/test_salome_protocol.py` | PASS |
| Control plane carries bounded metadata and URI/hash/size references | MOR-ARC-007 | positive and negative schema vectors | protocol schema 0.1 and contract tests | PASS |
| Six operations are closed and versioned | MOR-SAL-015 | request/response schema validation | `test_all_six_request_and_fake_response_contracts_validate` | PASS |
| Capability shape is truthful in fake profile | MOR-SAL-016 | fake truth and anti-claim mutations | fake reports null/empty detections and `NOT_RUN` | PASS |
| Submit carries operation, inputs, budgets, outputs, and idempotency | MOR-SAL-017 | lifecycle and schema tests | protocol contract suite | PASS |
| Observe/Cancel model state, attempts, logs, timeout, and terminality | MOR-SAL-018, MOR-SAL-020 | lifecycle and contradiction mutations | protocol contract suite | PASS |
| Publish models immutable artifact metadata, units, losses, and metrics | MOR-SAL-019 | fake publish anti-claim test | no fake output artifact is published | PASS |
| Greater-than-2-GiB metadata shape | MOR-SAL-010 | 3 GiB URI/hash/size schema vector | no payload created or transferred | PASS |
| Greater-than-2-GiB real transfer | MOR-SAL-010 | real bridge transfer | SALOME runtime and payload absent | NOT_RUN |
| Bounded E2 requirement traceability | MOR-ARC-002, MOR-ARC-007, MOR-SAL-010, MOR-SAL-015..020 | schema plus custom fail-closed mutations | E2 traceability JSON | PASS |
| E2 artifact provenance and CycloneDX inventory | Supply chain | deterministic generation and exact allowlist/path/hash/size/license/graph/provenance/source-digest/test-map/lock mutations | separate E2 manifest and SBOM | PASS |
| Closed E0 evidence preservation | Supply chain | exact byte-hash assertions | E0 manifest `df017341…`; E0 SBOM `30db23e7…` | PASS |
| E2 vulnerability analysis | Supply chain security | vulnerability scanner | inventory is not a vulnerability scan | NOT_RUN |
| Published E2 hosted checkpoint | Publication | Engine run `31585426276`; report run `31585425822` | 69 tests ran, 68 passed, sole stale `spec` digest failure | FAIL |
| Corrective E2 hosted checkpoint | Publication | Engine run `31589424865`; report run `31589424850` | source `e3ec245`: Python 3.12 `94090702646`, hygiene `94090702698`, native `94090702707`, REUSE `94090702764`, Python 3.13 `94090702766`, report `94090702397` | PASS |
| Final E2 evidence checkpoint | Publication | Engine run `31590141763`; report run `31590141769` | source `b3dfc084`: five Engine jobs plus report job `94092971258` passed | PASS |
| E2 integration into `engine` | Publication | PR #6 merge plus Engine run `31590418194` | merge `c84dd152`; native `94093829070`, Python 3.12 `94093829134`, Python 3.13 `94093829163`, hygiene `94093829169`, REUSE `94093829190` | PASS |
| Combined E1/E2 reconciliation | Publication | exact-head PR Engine run `31593255255`; report run `31593255344` | two-parent head `5a96abfc`, tree `bc7714b1`: five Engine jobs plus report job `94102764289` passed; branch-push Engine run `31593250364` also passed | PASS |
| Real SALOME 9.16 capability probe | E2/G1 optional backend | real isolated runtime | runtime absent | NOT_RUN |
| SHAPER/GEOM, SMESH/MED, MEDCoupling, fidelity and overhead | E2/G1 optional backend | real isolated runtime | no execution | NOT_RUN |

The metadata-shape row for MOR-SAL-010 is intentionally separate from real
transfer evidence. Similarly, `FakeSalomeAgent` passing its tests proves only
the software contract. It cannot satisfy any row requiring SALOME 9.16.

## E0 disposition

E0/core-CPU is `PASS` and integrated. Corrective source SHA
`8b41fa8435e5812b5bd10ae92e35878d9803e0bc` passed Engine/report runs
`31581879387` and `31581879373`; PR #4 merged the completed lot into `engine` at
`7715a7f7897a3058473732915e372b9835317d17`; `engine` push run `31582827407`
then passed all five jobs. Branch protection and R-021 remain `FAIL`. Full
per-requirement test/evidence mapping outside the nine-item E2 profile is a
living E1+ task and no G1-G5 gate is claimed. The E2 contract profile passes
locally. Its first published hosted checkpoint remains `FAIL`, while corrective
source `e3ec245` passed Engine run `31589424865` and report run `31589424850`;
real SALOME remains `NOT_RUN`.
