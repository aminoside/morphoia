# MORPHOIA

MORPHOIA is a research and engineering project for reconstructing, modifying,
validating, and generating parametric CAD models by humans and AI systems.

**Author and project initiator: Olivier Ami**

*Experimental STEP AP242-centered construction graph, Python SDK, and
validation framework for trustworthy AI-assisted parametric CAD reconstruction
and interoperability.*

| Component | Version | Status |
|---|---:|---|
| `.morph` facade and canonical IR | 0.1 | experimental, non-normative |
| Python SDK | 0.2.0.dev0 | pre-alpha |
| Morphoia Engine native component | 0.0.1 | E0 bootstrap, not released |
| Python | >= 3.12 | minimum supported version |

## Status

The public repository contains two legacy research phases and a dedicated
Morphoia Engine integration track:

- **Phase 1**: scientific and industrial state of the art, feasibility study,
  and Go/No-Go criteria;
- **Phase 2**: experimental 0.1 candidate, testable specification, and
  reference prototype;
- **Engine**: headless C++20/C11 interoperability, provenance, evidence, and
  orchestration work developed on the `engine` branch.

The `.morph` facade and MORPHOIA IR 0.1 are neither an ISO standard, a stable
format, nor a universal round-trip promise. Phase 1 forbids freezing syntax
before:

1. running P1/P2 profiles on at least two independent backends;
2. publishing a conformance suite; and
3. measuring industrial benefit on representative pilots.

The research hypothesis is a STEP-centered trust layer, not a replacement for
STEP, Open CASCADE, or industrial geometry kernels. Morphoia Engine is a
research tool and makes no clinical, diagnostic, or medical-device claim.

## Deliverables

### Phase 1

- [PDF report](docs/phase1/MORPHOIA_phase1_etat_art_faisabilite.pdf)
- [Report source](docs/phase1/MORPHOIA_phase1_etat_art_faisabilite.md)

### Phase 2

- [Experimental 0.1 candidate PDF](docs/phase2/MORPHOIA_phase2_standard_candidate_v0.1.pdf)
- [Specification index](docs/phase2/README.md)
- [Traceable requirements](docs/phase2/requirements.md)
- [Architecture](docs/phase2/architecture.md)
- [Textual facade specification](docs/phase2/language-specification.md)
- [EBNF grammar](docs/phase2/grammar.ebnf)
- [SDK and API](docs/phase2/sdk-api.md)
- [Validation and conformance](docs/phase2/validation-conformance.md)
- [CAD interoperability](docs/phase2/interoperability.md)
- [AI and GPU](docs/phase2/ai-gpu.md)
- [Roadmap and governance](docs/phase2/roadmap-governance.md)
- [Costs and risks](docs/phase2/costs-risks.md)

### Engine

- [Current status](docs/engine/STATUS.md)
- [Living execution plan](docs/engine/EXECUTION_PLAN.md)
- [Compliance matrix](docs/engine/COMPLIANCE_MATRIX.md)
- [Architecture decisions](docs/engine/DECISIONS.md)
- [Threat model](docs/engine/THREAT_MODEL.md)
- [Immutable baseline register](docs/engine/BASELINES.md)

### Quick links

- [User guide](docs/phase2/user-guide.md)
- [Developer guide](docs/phase2/developer-guide.md)
- [Tutorials and FAQ](docs/phase2/tutorials-faq.md)
- [Operation catalog](docs/phase2/operation-catalog.md)
- [References](docs/phase2/references.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Architecture under study

```text
Multimodal sources and evidence
              |
              v
AI candidates + confidence + abstention
              |
              v
Canonical construction graph mapped to STEP
              |
              v
Typed, deterministic, transactional runtime
        /            |             \
      OCCT        FreeCAD       licensed backends
              |
              v
Exact B-rep + PMI + properties + loss register
              |
     AP242 / CAD / glTF / OpenUSD / JT
```

The `.morph` facade is intentionally bounded, non-Turing-complete, and
replaceable. Canonical JSON 0.1 is experimental; the intended mechanical
exchange authority remains STEP AP242 with ISO 10303-42/-55/-108/-109/-111/
-112/-113 resources.

## Implemented prototype

The current development version provides:

- a lexer and parser with no runtime dependency;
- strict lexical rules, exact decimals, and units;
- symbol, dimensional type, DAG, profile, and tolerance validation;
- compilation to a deterministic canonical JSON graph;
- UUIDv5 identifiers and SHA-256 semantic hashes;
- explicit `unique`, `ambiguous`, or `missing` topology resolution;
- atomic transactions, optimistic conflict detection, undo, and redo;
- minimal provenance, decision, and loss-register models; and
- a CLI, JSON schemas, examples, and unit tests.

It does not yet provide an OCCT backend, sketch solver, B-rep, STEP import or
export, or CAD adapter. Those components are specified for reuse and must be
qualified during POC/Alpha work; this repository does not simulate them.

## Quick start

Prerequisite: Python 3.12 or newer.

```bash
git clone https://github.com/Aminoside/morphoia.git
cd morphoia
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
morphoia validate examples/mounting_plate.morph
morphoia compile examples/mounting_plate.morph -o build/mounting_plate.mcir.json
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`.

### Full verification

The repository includes the official Aldrich and Barlow fonts. Reproducible
report generation requires the report and development dependencies:

```bash
python -m pip install -e '.[report,dev]'
make test
make check
```

`make check` rebuilds and validates both generated PDFs, checks schemas, runs
the tests, and validates the example. Engine CI uses hash-locked dependency
profiles documented in [requirements/README.md](requirements/README.md).

## Repository layout

```text
MORPHOIA/
├── cpp/                  Morphoia Engine native bootstrap
├── docs/engine/          Engine plan, evidence, and immutable baselines
├── docs/phase1/          scientific and industrial study
├── docs/phase2/          requirements, specification, and guides
├── examples/             experimental MORPHOIA sources
├── schemas/              experimental JSON encodings
├── spec/                 Engine ADRs and machine-readable requirements
├── src/morphoia/         Python reference SDK and tools
├── tests/                syntax, semantics, native, and evidence tests
├── scripts/              reproducibility and validation controls
└── .github/              CI and code ownership
```

## Design governance

- Reuse existing standards, kernels, solvers, and SDKs before creating new ones.
- Require a component justification record before adding a new component.
- Distinguish geometry, intent, post-edit behavior, and evidence.
- Never hide ambiguity, repair, or semantic loss.
- Validate AI output with rules, solvers, exact kernels, and editing scenarios.
- Keep kernel tolerance, sensor uncertainty, dimensional tolerance, and GD&T
  distinct.

## Citation

[CITATION.cff](CITATION.cff) contains the reference citation metadata:
**MORPHOIA**, Olivier Ami, version 0.2.0-dev, August 3, 2026. No DOI has been
assigned at this stage.

## Licensing

Licensing is file- and component-specific. Pre-existing prototype code remains
under the repository's [MIT license](LICENSE). New original Morphoia Engine
code is offered under [Apache-2.0](LICENSE-APACHE) OR
[MIT](LICENSE-MIT), and new original Engine documentation is CC BY 4.0.
Validated baseline documents and official brand assets retain their own
rights and trademark terms; they are not relicensed as software.

[REUSE.toml](REUSE.toml), the SPDX annotations, [NOTICE](NOTICE), and
[DEPENDENCIES.md](DEPENDENCIES.md) provide the authoritative file-level
inventory and dependency boundaries. No license statement grants rights to
third-party material beyond its recorded terms.
