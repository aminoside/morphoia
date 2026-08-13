# Changelog

All notable changes to MORPHOIA are documented in this file.

## [Unreleased]

### Morphoia Engine qualified IR inspection 0.1 (prospective)

- added a bounded, case-sensitive ten-literal unit qualification profile with
  exact SI tuples, one additive sized C ABI operation, and an exact eight-symbol
  Linux export boundary without implementing general UCUM or unit conversion;
- added deterministic metadata-only Engine IR inspection through Python and
  CLI surfaces, explicit no-payload/no-transform behavior, and a documented
  thread-safety and lifetime matrix;
- added a frozen public-IR historical replay bridge plus a separate
  fail-closed traceability, artifact-manifest, 20-report-vector, and CycloneDX
  evidence profile;
- recorded successful bounded local sub-gates, including 45/45 targeted tests,
  86/86 predecessor regressions plus 20 native graph validations, two isolated
  CMake 3.20.5 runs with 10/10 CTests and consumer 1/1 each, ASan/UBSan, an
  installed-wheel smoke, 4/4 evidence tests, and the final 206/206 Python
  regression;
- retained one failed non-isolated in-tree CMake attempt without unsupported
  causal attribution, and kept LSan, byte-reproducible wheel proof, hosted
  Python 3.12/3.13, review, integration, vulnerability, and dependency-license
  analyses `NOT_RUN`;
- kept ADR-021 `Proposed` and MOR-IR-006, MOR-API-006, and MOR-QA-017
  `NOT_RUN` until the hosted, review, and integration gate is executed
  successfully.

### Morphoia Engine public IR 0.1

- added a distinct, versioned Engine IR manifest and replay identity domain
  without reinterpreting the legacy prototype schema or serializers;
- verified a bounded core-CPU lot for strict manifest validation, native
  canonicalization, Python and CLI replay, explicit migration, and exactly 20
  small synthetic IR graphs with frozen canonical vectors;
- added an exact requirement-to-test mapping, a closed artifact manifest, and
  a deterministic CycloneDX inventory with mutation-tested confinement and
  atomic publication;
- integrated the bounded profile into `engine` through PR #8 and accepted
  ADR-020 after exact-merge Python 3.12/3.13, native, hygiene, and REUSE checks;
- kept byte-reproducible distribution construction, vulnerability analysis,
  remote CAS, greater-than-2-GiB artifacts, real SALOME, GPU backends, full
  corpus conformance, and MVX explicitly `NOT_RUN` until their named evidence
  is executed.

### Morphoia Engine E0 bootstrap

- added an immutable baseline register and a machine-readable catalogue of all
  320 Engine requirements with a separate fail-closed traceability overlay;
- added the C++20 shared core bootstrap, versioned C11 ABI, strict CMake 3.20
  package, C and C++ smoke tests, external-consumer test, and sanitizer path;
- added resumable execution state, ADR-001 through ADR-017, capability and
  resource reports, a threat model, license metadata, deterministic SBOM, and
  hash-locked CPU CI profiles;
- kept SALOME, GPU, HPC, domain-library, vulnerability-scan, and MVX evidence
  explicitly `NOT_RUN` or `BLOCKED` where the required runtime or validated
  specification is unavailable.

### Modifié

- application de l'identité visuelle officielle MORPHOIA aux rapports PDF des phases 1 et 2 ;
- utilisation du logo vectoriel officiel, de la palette MORPHOIA et des polices Aldrich/Barlow ;
- attribution visible et métadonnées PDF normalisées au nom d'Olivier Ami ;
- ajout d'un thème de rapport réutilisable et d'un manifeste imposant ces règles à tout futur
  PDF suivi par Git.

### Qualité

- contrôle CI de l'intégrité des SVG officiels, des polices incorporées, de la mise en page A4,
  des métadonnées et de la présence de chaque PDF dans le manifeste ;
- détection de dérive étendue aux contenus graphiques, polices, images et dégradés.

## [0.2.0-dev] - 2026-08-03

### Ajouté

- candidat expérimental Phase 2 avec cahier des charges, architecture et spécification ;
- grammaire EBNF, catalogue des opérations et exemple `.morph` ;
- lexer, parseur, validateur sémantique et compilateur vers l'IR JSON canonique ;
- hash sémantique, décimaux exacts et identifiants déterministes ;
- résolveur de références topologiques à trois états ;
- runtime transactionnel de référence avec rollback, undo/redo et détection des conflits ;
- contrats de provenance, décisions IA et registre des pertes ;
- schémas JSON de l'IR, des backends et des pertes ;
- guides utilisateur/développeur, interopérabilité, IA/GPU, validation, coûts et roadmap ;
- rapport PDF Phase 2 reproductible et contrôles CI.
- alignement sur la licence MIT choisie à la création du dépôt GitHub, avec attribution à
  Olivier Ami.

### Limites déclarées

- aucun backend B-rep, solveur, import/export STEP ou connecteur CAO n'est encore implémenté ;
- la syntaxe et l'IR 0.1 restent non normatifs jusqu'aux gates de la Phase 1.

## [0.1.0] - 2026-08-03

### Ajouté

- création du projet MORPHOIA ;
- rapport Phase 1 - État de l'art et étude de faisabilité ;
- source Markdown et générateur PDF reproductible ;
- contrôle automatique du titre, de l'auteur, de la pagination et des liens ;
- métadonnées d'auteur Olivier Ami et gouvernance initiale.
