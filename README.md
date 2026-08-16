# MORPHOIA

MORPHOIA est un projet de recherche et d'ingénierie consacré à la reconstruction, la
modification, la validation et la génération de modèles CAO paramétriques par l'Homme comme
par l'IA.

**Auteurs et copropriétaires : Louis Manhès et Olivier Ami**

*Experimental STEP AP242-centred construction graph, Python SDK and validation framework
for trustworthy AI-assisted parametric CAD reconstruction and interoperability.*

| Composant | Version | Statut |
|---|---:|---|
| Architecture générale simplifiée et format natif `.oia` | 0.4.2 | baseline normative candidate, en attente de ratification conjointe |
| Façade `.morph` et IR canonique | 0.1 | expérimental, non normatif |
| SDK Python | 0.2.0.dev0 | pré-alpha |
| Python | ≥ 3.12 | version minimale prise en charge |

## Statut

Le dépôt public contient deux phases :

- **Phase 1** : état de l'art scientifique et industriel, étude de faisabilité et critères
  Go/No-Go ;
- **Phase 2** : candidat expérimental 0.1, spécification testable et prototype de référence.

La façade `.morph` et l'IR MORPHOIA 0.1 ne constituent ni une norme ISO, ni un format
stable, ni une promesse de round-trip universel. Conformément à la Phase 1, aucune syntaxe
ne pourra être gelée avant :

1. l'exécution des profils P1/P2 sur au moins deux backends indépendants ;
2. une suite de conformité publique ;
3. un bénéfice industriel mesuré sur des pilotes représentatifs.

L'hypothèse étudiée est une couche de confiance STEP-centrique, et non un remplacement de
STEP, d'Open CASCADE ou des noyaux industriels.

## Livrables

### Architecture générale

- [Architecture générale simplifiée et format natif v0.4.2](docs/architecture/MORPHOIA_Architecture_generale_simplifiee_v0.4.2.pdf)
- [Statut, provenance et empreinte du document](docs/architecture/README.md)

La v0.4.2 (`MORPHOIA-ARCH-BASELINE-0004.2`) est le document d'architecture candidat le
plus récent publié dans le dépôt. Conformément à son propre statut, elle ne remplace la
baseline v0.3.1 qu'après ratification conjointe par Louis Manhès et Olivier Ami.

### Phase 1

- [Rapport PDF](docs/phase1/MORPHOIA_phase1_etat_art_faisabilite.pdf)
- [Source du rapport](docs/phase1/MORPHOIA_phase1_etat_art_faisabilite.md)

### Phase 2

- [Rapport PDF - candidat expérimental 0.1](docs/phase2/MORPHOIA_phase2_standard_candidate_v0.1.pdf)
- [Index de la spécification](docs/phase2/README.md)
- [Cahier des charges traçable](docs/phase2/requirements.md)
- [Architecture](docs/phase2/architecture.md)
- [Spécification de la façade textuelle](docs/phase2/language-specification.md)
- [Grammaire EBNF](docs/phase2/grammar.ebnf)
- [SDK et API](docs/phase2/sdk-api.md)
- [Validation et conformité](docs/phase2/validation-conformance.md)
- [Interopérabilité CAO](docs/phase2/interoperability.md)
- [IA et GPU](docs/phase2/ai-gpu.md)
- [Roadmap et gouvernance](docs/phase2/roadmap-governance.md)
- [Coûts et risques](docs/phase2/costs-risks.md)

### Identité visuelle

- [Charte graphique officielle, version 1.0](assets/brand/MORPHOIA_charte_graphique_v1.0.pdf)
- [Kit logo vectoriel téléchargeable](assets/brand/morphoia-logo-vectoriel.zip)
- [Masters, déclinaisons et règles d'usage](assets/brand/README.md)

### Accès rapide

- [Guide utilisateur](docs/phase2/user-guide.md)
- [Guide développeur](docs/phase2/developer-guide.md)
- [Tutoriels et FAQ](docs/phase2/tutorials-faq.md)
- [Catalogue des opérations](docs/phase2/operation-catalog.md)
- [Références](docs/phase2/references.md)
- [Contribuer](CONTRIBUTING.md)
- [Historique des versions](CHANGELOG.md)

## Architecture étudiée

```text
Sources et preuves multimodales
              |
              v
Candidats IA + confiance + abstention
              |
              v
Graphe de construction canonique mappé à STEP
              |
              v
Runtime typé, déterministe et transactionnel
        /            |             \
      OCCT        FreeCAD       backends sous licence
              |
              v
B-rep exacte + PMI + propriétés + registre des pertes
              |
     AP242 / CAO / glTF / OpenUSD / JT
```

La façade `.morph` est volontairement bornée, non Turing-complète et remplaçable. Le JSON
canonique 0.1 est un encodage expérimental ; l'autorité d'échange mécanique visée reste STEP
AP242 avec les ressources ISO 10303-42/-55/-108/-109/-111/-112/-113.

## Prototype implémenté

La version de développement fournit actuellement :

- lexer et parseur sans dépendance d'exécution ;
- règles lexicales strictes, décimaux exacts et unités ;
- validation des symboles, types dimensionnels, DAG, profils et tolérances ;
- compilateur vers un graphe canonique JSON déterministe ;
- identifiants UUIDv5 et hash sémantique SHA-256 ;
- résolution topologique explicite `unique`, `ambiguous` ou `missing` ;
- transactions atomiques, conflit optimiste, undo/redo ;
- modèles minimaux de provenance, décision et registre des pertes ;
- CLI, schémas JSON, exemple et tests unitaires.

Il ne fournit pas encore de backend OCCT, de solveur d'esquisse, de B-rep, d'import/export
STEP ou d'adaptateur CAO. Ces composants sont spécifiés comme réemploi et doivent être
qualifiés dans les étapes POC/Alpha ; ils ne sont pas simulés dans ce dépôt.

## Démarrage rapide

Prérequis : Python 3.12+.

```bash
git clone https://github.com/Aminoside/morphoia.git
cd morphoia
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
morphoia validate examples/mounting_plate.morph
morphoia compile examples/mounting_plate.morph -o build/mounting_plate.mcir.json
```

Sous Windows PowerShell, la commande d'activation est
`.venv\Scripts\Activate.ps1`.

### Vérification complète

Les polices officielles Aldrich et Barlow sont incluses dans le dépôt. La génération
reproductible des rapports requiert uniquement les dépendances de rapport et de développement :

```bash
python -m pip install -e '.[report,dev]'
make test
make check
```

`make check` régénère et valide les deux PDF, contrôle les schémas, exécute les tests et
valide l'exemple.

## Organisation

```text
MORPHOIA/
├── docs/architecture/    architecture générale candidate v0.4.2
├── docs/phase1/          étude scientifique et industrielle
├── docs/phase2/          cahier des charges, spécification et guides
├── examples/             sources MORPHOIA expérimentales
├── schemas/              encodages JSON expérimentaux
├── src/morphoia/         SDK et outils de référence Python
├── tests/                tests syntaxiques, sémantiques et transactionnels
├── scripts/              contrôles de rapports et de reproductibilité
└── .github/              CI et propriété du code
```

## Gouvernance de conception

- Réutiliser les standards, noyaux, solveurs et SDK existants avant toute création.
- Exiger un Component Justification Record avant tout composant nouveau.
- Distinguer géométrie, intention, comportement après modification et preuve.
- Ne jamais masquer une ambiguïté, une réparation ou une perte sémantique.
- Valider toute sortie IA par règles, solveur, noyau exact et scénarios d'édition.
- Séparer tolérance noyau, incertitude capteur, tolérance dimensionnelle et GD&T.

## Citation

Le fichier [CITATION.cff](CITATION.cff) contient les métadonnées de citation de référence :
**MORPHOIA**, Louis Manhès et Olivier Ami, version 0.2.0-dev, 3 août 2026. Aucun DOI n'est attribué à ce
stade.

## Licence

Le dépôt est public sous licence [MIT](LICENSE), conformément à la licence choisie lors de sa
création sur GitHub. Copyright 2026 Louis Manhès et Olivier Ami.

Une séparation future entre licence du code, licence documentaire, licences de données et
politique de marque pourra être étudiée avant une version normative. Elle devra faire l'objet
d'une décision explicite, d'une revue juridique et d'une stratégie compatible avec les droits
déjà accordés. Le fichier [LICENSE](LICENSE) reste l'autorité pour la version actuelle.
