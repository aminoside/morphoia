# Guide développeur de MORPHOIA

## 1. Portée et statut

Ce guide décrit l'implémentation présente dans `src/morphoia`, et non le runtime
industriel visé par les documents d'architecture.

La façade source et l'IR sont un **candidat expérimental 0.1**. Le paquet Python est
actuellement en version `0.2.0-dev`. Aucune API n'est stable et aucun succès des
tests unitaires ne vaut conformité CAO, STEP ou industrielle.

La règle de Phase 1 est opposable à toute contribution : un composant nouveau n'est
acceptable qu'après démonstration d'un manque ou d'un avantage mesurable. Il ne faut
notamment réécrire ni noyau B-rep, ni solveur de contraintes, ni ontologie STEP.

## 2. Préparer l'environnement

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
```

Le projet exige Python 3.12 ou plus récent. Les modules du cœur n'ont actuellement
pas de dépendance d'exécution externe.

Sans installation :

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m morphoia validate examples/mounting_plate.morph
```

## 3. Arborescence du prototype

```text
src/morphoia/
├── __init__.py              # API publique et version du paquet
├── __main__.py              # python -m morphoia
├── cli.py                   # commandes validate et compile
├── lexer.py                 # lexer sans dépendance
├── parser.py                # parser descendant récursif 0.1
├── model.py                 # AST, spans et diagnostics
├── typesystem.py            # inférence dimensionnelle minimale
├── semantic.py              # symboles, profils, DAG et règles sémantiques
├── validator.py             # façade de validation sûre
├── compiler.py              # lowering JSON et hash canonique
├── topology.py              # résolution unique/ambiguë/manquante
├── provenance.py            # preuves, décisions et abstention
├── losses.py                # registre machine-readable des pertes
├── runtime.py               # transactions et révisions immuables en mémoire
└── backends/
    ├── base.py              # contrat abstrait de backend
    └── json_backend.py      # sérialisation JSON canonique

examples/
└── mounting_plate.morph

schemas/
└── morphoia-ir-0.1.schema.json

tests/
├── test_parser.py
├── test_runtime.py
└── test_topology.py
```

## 4. Pipeline réellement exécuté

```text
texte UTF-8
   │
   ▼
tokenize()                 lexer.py
   │ tokens + Span
   ▼
Parser.parse()             parser.py
   │ Document / Model / Node / Expression
   ▼
validate_semantics()       semantic.py + typesystem.py
   │ diagnostics, symboles, DAG
   ▼
compile_document()         compiler.py
   │
   └── JSON canonique + semantic_sha256
            │
            └── RuntimeStore optionnel : transaction/commit/undo/redo
```

La CLI `compile` écrit directement le dictionnaire produit par `compile_document`.
La classe `CanonicalJsonBackend` existe comme démonstrateur du contrat de backend,
mais la CLI ne possède pas encore de registre ni de sélection de backends.

Aucun nœud n'est transmis à un noyau géométrique et aucun scénario n'est exécuté.

## 5. Modules et responsabilités

### 5.1 `model.py`

Le modèle syntaxique repose sur des dataclasses typées :

- `Span` utilise des lignes et colonnes indexées à partir de 1 ;
- `Diagnostic` porte code, sévérité, message, span et hint ;
- les expressions sont `Name`, `Literal`, `Call`, `Unary`, `Binary` et
  `ListExpression` ;
- `Node` représente uniformément déclaration, bloc ou instruction ;
- `Document` contient version, namespace, imports et modèles ;
- `ValidationResult.ok` est faux dès qu'un diagnostic de sévérité `ERROR` existe.

Les nœuds syntaxiques sont immuables (`frozen=True`, `slots=True`). Cette propriété
réduit les mutations accidentelles avant canonicalisation.

### 5.2 `lexer.py`

Le lexer reconnaît :

- identifiants ASCII ;
- nombres entiers ou décimaux avec exposant ;
- chaînes à échappements JSON ;
- commentaires `//` et `/* ... */` non imbriqués ;
- opérateurs simples et doubles ;
- positions précises dans le texte.

Il ne résout pas le registre d'unités. Le parser traite actuellement un nombre suivi
d'un identifiant comme une quantité ; le type system détermine ensuite si l'unité
est connue.

### 5.3 `parser.py`

Le parser implémente la grammaire publiée dans `docs/phase2/grammar.ebnf` :

- en-tête `morphoia 0.1;` ;
- namespace et imports ;
- un ou plusieurs modèles ;
- paramètres, constantes, datums, références, matériaux, PMI et tolérances ;
- sketches, features, validation, scénarios et assemblages ;
- attributs `[key = value]` ;
- expressions avec précédence ;
- nœuds génériques destinés aux expérimentations d'extensions.

La syntaxe réelle des arguments nommés est `name = value`, pas `name: value`.
La syntaxe réelle des features est :

```morphoia
feature body: extrude {
  profile = base.outer;
  distance = thickness;
}
```

Le fallback générique préserve un verbe inconnu dans l'AST. Cela ne signifie pas
qu'une extension est résolue ou exécutable.

### 5.4 `typesystem.py`

Le type system est volontairement minimal. Il connaît un registre d'unités, quelques
alias et certains types de retour d'appels. Il vérifie aujourd'hui surtout le type
d'une expression affectée à un paramètre lorsque l'inférence est certaine.

Il ne faut pas documenter comme implémentés :

- l'algèbre dimensionnelle complète ;
- les unités composées ;
- les types génériques de références ;
- la covariance géométrique ;
- les signatures complètes des opérations.

### 5.5 `semantic.py`

Les règles actuelles sont :

- seule la version source `0.1` est acceptée ;
- profils P1 à P4 reconnus ;
- symboles de premier niveau uniques ;
- références de symboles connues ;
- cycles de dépendances refusés ;
- opération autorisée par le profil ;
- référence persistante fondée sur `select` avec source, rôle, preuve et cardinalité
  unique ;
- quatre catégories de tolérances uniquement ;
- preuve obligatoire pour hypothèse, ambiguïté ou inférence.

Le DAG est déduit des références de noms, puis ordonné de manière déterministe en
triant les dépendances. Les corps imbriqués sont parcourus pour trouver les
expressions, mais le symbol table principal reste celui du modèle.

### 5.6 `compiler.py`

Le compilateur transforme l'AST validé en dictionnaire JSON neutre :

- format `morphoia.canonical-construction-graph` ;
- version d'IR `0.1` ;
- source, namespace, imports, modèles et déclarations ;
- ordre de dépendances ;
- contrat d'exécution et ancrages ISO ;
- hash sémantique.

Les clés d'arguments et d'attributs sont triées. Les décimaux sont sérialisés en
chaînes accompagnées de `numeric_encoding = "decimal"`.

Un attribut `[id = "..."]` devient l'ID canonique. Sans ID explicite, un UUIDv5 est
dérivé du namespace et du chemin. Un renommage change donc l'ID dérivé : les actifs
destinés au round-trip doivent employer un UUID explicite.

`semantic_hash()` retire un éventuel champ `semantic_sha256`, sérialise le reste en
JSON compact avec clés triées, puis calcule SHA-256. La stabilité n'est garantie que
pour le même contrat et la même version du prototype ; elle n'est pas encore une
garantie inter-implémentations.

### 5.7 `topology.py`

Ce module est un contrat exécutable indépendant d'une B-rep :

```python
from morphoia.topology import (
    EntityCandidate,
    ReferenceQuery,
    ResolutionStatus,
    resolve_reference,
)

query = ReferenceQuery(
    kind="face",
    producer="blank",
    role="cap.end",
    signature=(("normal", "+Z"),),
)

candidate = EntityCandidate(
    identity="face-a",
    kind="face",
    producer="blank",
    role="cap.end",
    signature=(("normal", "+Z"),),
)

result = resolve_reference(query, [candidate])
assert result.status is ResolutionStatus.UNIQUE
assert result.entity.identity == "face-a"
```

Le filtre utilise type, producteur, rôle, signature et adjacence. Les candidats sont
triés seulement pour rendre le diagnostic déterministe. Plusieurs résultats restent
`AMBIGUOUS` ; le tri n'autorise jamais un choix silencieux.

### 5.8 `provenance.py`

Le contrat minimal de confiance distingue :

- les preuves `drawing`, `pmi`, `cad_model`, `image`, `point_cloud`, `mesh`, `text`,
  `human_decision` et `derived_rule` ;
- les décisions `candidate`, `accepted`, `rejected` et `abstained` ;
- l'identité, l'URI, le digest SHA-256 et le locator d'une preuve ;
- confiance, acteur/règle et justification d'une décision.

Une preuve exige un SHA-256 minuscule de 64 caractères. Une décision acceptée exige
au moins une preuve et un `decided_by`. La confiance, si elle existe, appartient à
l'intervalle fermé `[0, 1]`.

Ce module est un contrat minimal issu de la Phase 1, pas une ontologie universelle
de provenance.

### 5.9 `losses.py`

`LossRecord` classe une perte de géométrie, topologie, historique paramétrique,
contrainte, PMI, matériau, assemblage, provenance, identité ou comportement. Les
sévérités sont `info`, `warning`, `error` et `fatal`.

`LossRegister.blocks_commit` devient vrai si au moins une perte est `error` ou
`fatal`. `to_dict()` produit le schéma `morphoia.loss-register/0.1`. Le registre
n'est pas encore branché automatiquement aux commandes ou backends.

### 5.10 `runtime.py`

`RuntimeStore` fournit un historique en mémoire de graphes immuables :

- `begin()` ouvre une transaction sur la révision courante ;
- `commit()` exige un message et exécute les validateurs fournis avant mutation ;
- `rollback()` ferme sans commit ;
- `undo()` et `redo()` déplacent le curseur ;
- une transaction basée sur une ancienne révision lève `RevisionConflict` ;
- un commit après undo tronque la branche redo ;
- chaque révision reçoit un nouveau hash sémantique.

Le store copie profondément les graphes pour éviter la mutation d'une révision
commise. Il ne fournit ni persistance, ni journal distribué, ni fusion de branches.
La géométrie demeure la responsabilité des backends.

### 5.11 `backends/`

`BackendCapabilities` décrit nom, version, profils, opérations, B-rep exacte, PMI,
mode déterministe et licence. `BackendResult` sépare succès, URI d'artefact,
propriétés de validation, pertes et diagnostics.

Le seul backend concret est `CanonicalJsonBackend`. Il sérialise l'IR sans perte,
mais ne produit aucune géométrie. `exact_brep` vaut donc `False`.

## 6. API Python publique actuelle

Les symboles exportés par `morphoia` sont :

```python
from morphoia import (
    canonical_json,
    compile_document,
    parse,
    semantic_hash,
    validate_file,
    validate_source,
    RuntimeStore,
)
```

Usage sûr :

```python
from morphoia import compile_document, validate_file

result = validate_file("examples/mounting_plate.morph")
if not result.ok or result.document is None:
    raise ValueError([item.message for item in result.diagnostics])

ir = compile_document(result.document)
```

`compile_document` suppose un document déjà validé. Il ne relance pas lui-même le
validateur.

## 7. CLI actuelle

Deux sous-commandes seulement sont disponibles :

```bash
morphoia validate SOURCE [--json]
morphoia compile SOURCE -o OUTPUT
```

`validate` retourne 0 ou 1. `compile` affiche d'abord les diagnostics en texte,
refuse une source invalide puis écrit le JSON. Les commandes `import`, `export`,
`render`, `step`, `occt`, `benchmark` et `serve` ne sont pas encore implémentées.

Pour ajouter une commande :

1. écrire une fonction `command_<name>(arguments) -> int` dans `cli.py` ;
2. enregistrer son sous-parser dans `build_parser()` ;
3. conserver les codes de sortie 0 succès, 1 erreur métier ;
4. fournir une sortie machine-readable si la commande produit des diagnostics ;
5. ajouter des tests de CLI avant de la documenter comme disponible.

## 8. Ajouter ou modifier une construction syntaxique

Ordre recommandé :

1. vérifier que la construction est autorisée par un CJR ou correspond à un concept
   STEP déjà retenu ;
2. mettre à jour la grammaire candidate ;
3. ajouter les tokens strictement nécessaires dans `lexer.py` ;
4. ajouter ou spécialiser le parsing dans `parser.py` ;
5. enrichir les dataclasses seulement si `Node` ne peut préserver la sémantique ;
6. ajouter les règles de symboles, types et profils ;
7. définir le lowering canonique ;
8. ajouter tests valides, invalides et de hash ;
9. documenter séparément « parsé », « validé » et « exécuté ».

Le parser générique ne doit pas servir à prétendre qu'une opération est supportée.

## 9. Ajouter une unité ou une fonction typée

Pour une unité simple :

1. ajouter son symbole et sa dimension dans `UNIT_DIMENSIONS` ;
2. ajouter des tests positifs et d'incompatibilité ;
3. documenter facteur de conversion et standard de référence avant toute
   canonicalisation SI réelle.

Pour une fonction connue du type system, ajouter son type dans
`CALL_RETURN_TYPES`. Cette table ne vérifie encore ni les paramètres ni les unités
dérivées ; toute extension substantielle doit faire évoluer le modèle de signatures
plutôt que multiplier des chaînes spéciales.

## 10. Ajouter une opération à un profil

Les opérations reconnues se trouvent dans `PROFILE_OPERATIONS`. Une opération P2
hérite automatiquement des opérations P1 ; P4 hérite de tous les profils précédents.

Avant ajout, fournir :

- profil minimal ;
- préconditions et postconditions ;
- arguments affectant la géométrie ;
- rôles topologiques ;
- cas dégénérés ;
- mapping STEP ou écart démontré ;
- fallback et registre des pertes ;
- scénarios d'édition ;
- CJR si le composant ou la sémantique est nouveau.

L'ajout dans `PROFILE_OPERATIONS` ne constitue qu'une autorisation syntaxique. Une
implémentation backend et des tests géométriques seront nécessaires pour parler de
support réel.

## 11. Ajouter un backend

Un backend expérimental implémente `Backend` :

```python
from morphoia.backends.base import Backend, BackendCapabilities, BackendResult


class ExampleBackend(Backend):
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name="example",
            version="0.1",
            profiles=("P1",),
            operations=("extrude",),
            exact_brep=False,
            pmi=False,
            deterministic_mode=True,
            license="declare-me",
        )

    def execute(self, canonical_ir: dict[str, object]) -> BackendResult:
        return BackendResult(
            success=False,
            artifact_uri=None,
            validation_properties={},
            losses=(),
            diagnostics=("not implemented",),
        )
```

Un backend OCCT futur doit rester derrière cette frontière : aucun type OCCT ne doit
fuir dans l'IR canonique. Il devra publier capacités, environnement verrouillé,
propriétés, événements de healing et pertes. La Phase 1 interdit de remplacer OCCT
par un nouveau noyau généraliste.

## 12. Tests

La suite actuelle contient quatorze tests unitaires couvrant :

- validité de l'exemple ;
- déterminisme du hash dans la même implémentation ;
- référence inconnue ;
- incompatibilité dimensionnelle ;
- cardinalité obligatoire ;
- résolution topologique unique, ambiguë et manquante ;
- commit, rollback logique, undo/redo et fermeture des transactions ;
- rejet d'une transaction obsolète ;
- absence de mutation après échec d'un validateur de commit ;
- preuve et acteur obligatoires pour une décision acceptée ;
- sérialisation et blocage d'un registre de pertes.

Exécution :

```bash
python -m unittest discover -s tests -v
```

Après installation des dépendances de développement :

```bash
python -m ruff check src tests
python -m pytest
```

Toute correction doit ajouter un test de non-régression. Toute évolution du hash ou
de l'IR doit être considérée comme une modification de contrat et explicitée.

## 13. Diagnostics

Les codes doivent rester stables et structurés :

- lexing `MORPH-E000` ;
- parsing `MORPH-E010` ;
- version `MORPH-E001` ;
- sémantique `MORPH-E100` et suivants.

Un diagnostic doit inclure un span aussi précis que possible et un `hint` seulement
s'il propose une correction sûre. Ne jamais transformer une ambiguïté mécanique en
warning si elle peut changer le résultat.

## 14. Frontières à ne pas franchir silencieusement

| Fonction | Statut actuel | Condition avant annonce de support |
|---|---|---|
| Lexer/parser 0.1 | Implémenté | Corpus golden G0 |
| Validation sémantique | Partielle | Règles et tests exhaustifs par profil |
| JSON canonique | Implémenté comme POC | Deux implémentations et bijectivité |
| Références topologiques | Contrat et tests unitaires | Lignée réelle multi-backend et scénarios |
| Transactions | Store immuable en mémoire | Persistance, intégration backend et tests de panne |
| Provenance et pertes | Primitives et tests unitaires | Intégration source/IR/adaptateurs et schémas de conformité |
| OCCT | Interface seulement | Adaptateur, B-rep, propriétés et tests |
| Solveur | Non implémenté | Évaluation FreeCAD/SolveSpace/D-Cubed |
| STEP/AP242 | Ancrage déclaré seulement | Mapping et round-trip mesurés |
| PMI/assemblage | Syntaxe générique seulement | Modèle, backend et conformité P2/P3 |
| IA/GPU | Non implémenté | Pipeline, benchmark et validation |

## 15. Component Justification Record

Avant tout composant nouveau, copier
[`decisions/CJR-TEMPLATE.md`](decisions/CJR-TEMPLATE.md) et documenter :

- besoin non couvert ;
- alternatives existantes et licences ;
- benchmark reproductible ;
- avantage ou échec démontré ;
- mapping STEP et pertes ;
- coût et stratégie d'abandon.

Une API plus agréable n'est pas, à elle seule, une justification pour réinventer une
brique existante.

## 16. Gates de développement

- **G0, en cours** : spécification, implémentation de référence et 100 cas golden.
- **G1, non atteint** : P1/P2 sur deux backends, B-rep valide ≥99 %, scénarios ≥95 %.
- **G2, non atteint** : conformité publique, registre des pertes et seconde
  implémentation.
- **G3, non atteint** : gain humain médian ≥40 % sur deux pilotes.
- **G4, interdit avant preuves** : candidat à la standardisation.

Le numéro `1.0` et les qualificatifs `stable`, `standard` ou `certified` ne doivent
pas être employés avant les gates correspondants.
