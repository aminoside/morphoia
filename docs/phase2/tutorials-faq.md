# Tutoriels et FAQ de MORPHOIA

## Préambule

Ces tutoriels concernent le **candidat expérimental MORPHOIA 0.1** et le prototype
Python actuel. Ils montrent le parsing, la validation partielle et la compilation
vers JSON. Ils ne génèrent pas encore de solide CAO.

La version affichée par la CLI peut être `0.2.0-dev` : c'est la version du paquet,
alors que `morphoia 0.1;` désigne la version de la façade source et de l'IR.

## Tutoriel 1 - Valider et compiler l'exemple officiel

### Étape 1 : installer le checkout

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Étape 2 : vérifier la version du paquet

```bash
morphoia --version
```

### Étape 3 : valider

```bash
morphoia validate examples/mounting_plate.morph
```

La sortie attendue est :

```text
examples/mounting_plate.morph: valid
```

### Étape 4 : compiler vers l'IR

```bash
morphoia compile examples/mounting_plate.morph \
  -o build/mounting_plate.mcir.json
```

### Étape 5 : inspecter le JSON

```bash
python -m json.tool build/mounting_plate.mcir.json
```

Rechercher notamment :

- `format = morphoia.canonical-construction-graph` ;
- `format_version = 0.1` ;
- `dependency_order` ;
- `execution_contract` ;
- `semantic_sha256`.

Ce fichier décrit le graphe syntaxique et sémantique connu du prototype. Il ne
contient aucune B-rep évaluée.

## Tutoriel 2 - Écrire une pièce minimale

Créer un fichier `spacer.morph` avec :

```morphoia
morphoia 0.1;
namespace org.example;

model Spacer [
  profile = "P1",
  id = "20000000-0000-4000-8000-000000000001"
] {
  units {
    length = mm;
    angle = deg;
  }

  parameter diameter: length = 20 mm;
  parameter thickness: length = 5 mm;

  datum base_plane: plane = world.xy;

  sketch base on base_plane {
    profile disk = circle(diameter / 2);
  }

  feature body: extrude {
    profile = base.disk;
    distance = thickness;
    direction = +world.z;
    result = solid;
  }
}
```

Puis :

```bash
morphoia validate spacer.morph
morphoia compile spacer.morph -o build/spacer.mcir.json
```

Le fichier doit être accepté. Cela démontre que les symboles, unités simples,
sketch et opération P1 sont représentables. Cela ne démontre pas que le disque a été
extrudé par un noyau.

### Ajouter une contrainte de domaine

Les attributs peuvent conserver des limites :

```morphoia
parameter diameter: length = 20 mm [
  min = 5 mm,
  max = 100 mm,
  status = observed,
  evidence = "drawing:D1"
];
```

Le compilateur conserve ces attributs. Le validateur actuel ne vérifie pas encore
que la valeur se trouve entre `min` et `max`.

## Tutoriel 3 - Comprendre une erreur d'unité

Remplacer temporairement :

```morphoia
parameter diameter: length = 20 mm;
```

par :

```morphoia
parameter diameter: length = 20 deg;
```

Valider :

```bash
morphoia validate spacer.morph
```

Le diagnostic attendu contient :

```text
MORPH-E110: parameter 'diameter' expects length, got angle
```

Pour obtenir une structure JSON :

```bash
morphoia validate spacer.morph --json
```

Corriger l'unité en `mm` avant de poursuivre.

## Tutoriel 4 - Déclarer une référence persistante

Après une feature `body`, ajouter :

```morphoia
reference top_face: face = select(
  body.faces,
  role = "cap.end",
  normal = world.z,
  cardinality = unique
);
```

Cette requête satisfait les quatre contrôles actuels : source, rôle, signature
géométrique et cardinalité.

### Observer l'échec volontaire

Supprimer `cardinality = unique` puis relancer la validation. Le résultat contient
`MORPH-E131`.

Ajouter ensuite la cardinalité, mais supprimer `normal = world.z`. Le résultat
contient `MORPH-E134`, car aucune preuve géométrique ou d'adjacence ne distingue la
face.

Ces règles ne résolvent pas magiquement le Topological Naming Problem. Elles
interdisent seulement les choix silencieux dans le contrat source.

## Tutoriel 5 - Détecter un cycle de dépendances

Le fragment suivant est invalide :

```morphoia
morphoia 0.1;

model Cyclic [profile = "P1"] {
  parameter a: length = b;
  parameter b: length = a;
}
```

```bash
morphoia validate cyclic.morph
```

Le validateur produit `MORPH-E103` et affiche le chemin du cycle. Les cycles de
features sont interdits. À terme, les cycles algébriques d'un solveur d'esquisse
seront traités dans un hypergraphe séparé ; aucun solveur n'est encore connecté.

## Tutoriel 6 - Utiliser l'API Python

```python
from pathlib import Path

from morphoia import canonical_json, compile_document, validate_source

source = Path("examples/mounting_plate.morph").read_text(encoding="utf-8")
validation = validate_source(source)

for diagnostic in validation.diagnostics:
    print(diagnostic.severity.value, diagnostic.code, diagnostic.message)

if not validation.ok or validation.document is None:
    raise SystemExit(1)

ir = compile_document(validation.document)
print("hash:", ir["semantic_sha256"])
Path("build/from_python.mcir.json").parent.mkdir(exist_ok=True)
Path("build/from_python.mcir.json").write_text(
    canonical_json(ir),
    encoding="utf-8",
)
```

`validate_source` capture les erreurs lexicales et syntaxiques dans un
`ValidationResult`. `parse` est plus bas niveau et lève directement une exception.

## Tutoriel 7 - Tester les trois états d'une référence

Le résolveur Python peut être utilisé sans noyau pour tester le contrat :

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

face_a = EntityCandidate(
    identity="face-a",
    kind="face",
    producer="blank",
    role="cap.end",
    signature=(("normal", "+Z"),),
)

assert resolve_reference(query, []).status is ResolutionStatus.MISSING
assert resolve_reference(query, [face_a]).status is ResolutionStatus.UNIQUE

face_b = EntityCandidate(
    identity="face-b",
    kind="face",
    producer="blank",
    role="cap.end",
    signature=(("normal", "+Z"),),
)

ambiguous = resolve_reference(query, [face_b, face_a])
assert ambiguous.status is ResolutionStatus.AMBIGUOUS
assert [item.identity for item in ambiguous.candidates] == ["face-a", "face-b"]
```

L'ordre déterministe des candidats facilite le diagnostic. Il ne choisit pas
`face-a` à la place de l'utilisateur.

## Tutoriel 8 - Vérifier le déterminisme du prototype

```python
from pathlib import Path

from morphoia import compile_document, validate_source

source = Path("examples/mounting_plate.morph").read_text(encoding="utf-8")
first = validate_source(source)
second = validate_source(source)

assert first.ok and first.document is not None
assert second.ok and second.document is not None

first_ir = compile_document(first.document)
second_ir = compile_document(second.document)
assert first_ir["semantic_sha256"] == second_ir["semantic_sha256"]
```

Cette vérification porte sur deux compilations avec la même implémentation. Le gate
de deux implémentations indépendantes n'est pas encore atteint.

## Tutoriel 9 - Utiliser une transaction en mémoire

```python
from morphoia import RuntimeStore

initial_graph = {"format": "example", "value": 1}
store = RuntimeStore(initial_graph)

transaction = store.begin()
transaction.graph["value"] = 2
revision = transaction.commit("change value")

assert revision.number == 1
assert store.current.graph["value"] == 2
assert store.undo().graph["value"] == 1
assert store.redo().graph["value"] == 2
```

Un validateur peut interrompre atomiquement le commit :

```python
transaction = store.begin()


def reject(_graph):
    raise ValueError("invalid geometry")


try:
    transaction.commit("invalid change", validators=(reject,))
except ValueError:
    pass

assert store.current.number == 1
```

Ce magasin est volontairement en mémoire. Il démontre atomicité, undo/redo et
contrôle optimiste ; il n'exécute ni géométrie ni scénario `.morph`.

## Tutoriel 10 - Enregistrer preuve, décision et perte

```python
from decimal import Decimal

from morphoia.losses import LossCategory, LossRecord, LossRegister, LossSeverity
from morphoia.provenance import Decision, DecisionStatus, Evidence, EvidenceKind

evidence = Evidence(
    identity="e1",
    kind=EvidenceKind.DRAWING,
    source_uri="urn:morphoia:drawing:1",
    source_sha256="a" * 64,
    locator="view:front/dimension:12",
)

decision = Decision(
    identity="d1",
    subject="width",
    status=DecisionStatus.ACCEPTED,
    evidence_ids=(evidence.identity,),
    confidence=Decimal("0.99"),
    decided_by="rule:explicit-dimension",
)

losses = LossRegister(
    operation="export",
    source_backend="canonical",
    target_backend="gltf",
    records=(
        LossRecord(
            code="MORPH-L001",
            category=LossCategory.PARAMETRIC_HISTORY,
            severity=LossSeverity.ERROR,
            subject="model",
            message="glTF does not preserve the construction history",
        ),
    ),
)

assert decision.status is DecisionStatus.ACCEPTED
assert losses.blocks_commit
```

Ces primitives ne sont pas encore reliées automatiquement au parser, à l'IR ou à
la CLI. Elles rendent toutefois testables deux exigences de Phase 1 : aucune
inférence acceptée sans preuve, aucune perte critique silencieuse.

## FAQ

### MORPHOIA est-il déjà un nouveau standard CAO ?

Non. MORPHOIA 0.1 est un candidat expérimental. La Phase 1 interdit de le présenter
comme standard avant preuves de portabilité, conformité et valeur industrielle.

### Pourquoi le fichier dit-il 0.1 alors que la CLI affiche 0.2.0-dev ?

`0.1` est la version de la façade `.morph` et de l'IR. `0.2.0-dev` est la version de
développement du paquet Python. Le parser n'accepte actuellement que
`morphoia 0.1;`.

### La commande `compile` produit-elle un modèle CAO ?

Non. Elle produit un graphe JSON canonique. Aucun noyau B-rep n'est exécuté et aucun
STEP n'est écrit.

### Puis-je ouvrir le JSON dans FreeCAD, CATIA, NX ou SolidWorks ?

Non directement. Les adaptateurs et exports correspondants sont des cibles. Le JSON
sert actuellement au débogage, aux tests et aux échanges internes du POC.

### Le dépôt contient-il Open CASCADE ?

Non. Il contient un contrat abstrait de backend et un backend JSON. Un adaptateur
OCCT devra être ajouté sans exposer de types OCCT dans le graphe canonique.

### Pourquoi ne pas écrire directement du CadQuery ?

CadQuery reste une brique de référence et un backend/prototype potentiel. La façade
expérimentale teste des propriétés supplémentaires : absence d'I/O arbitraire,
diagnostics structurés, provenance, profils, tolérances séparées et ambiguïté
topologique explicite. Son maintien dépendra de benchmarks contre CadQuery ; elle
sera abandonnée si aucun avantage mesurable n'est démontré.

### Pourquoi STEP/AP242 n'est-il pas simplement remplacé ?

Il ne doit pas l'être. Le graphe est ancré dans ISO 10303-42/-55/-108/-109/-111/
-112/-113 et AP242. La syntaxe `.morph` n'est qu'une façade candidate plus simple à
écrire et à générer. Les mappings exacts et le round-trip restent à implémenter.

### Les opérations `extrude` et `fillet` fonctionnent-elles ?

Le parser les reconnaît et le validateur contrôle leur appartenance au profil. Il
ne vérifie pas encore toutes leurs signatures et ne les exécute pas. « Reconnue » ne
signifie donc pas « géométriquement implémentée ».

### Pourquoi mon feature incomplet peut-il être déclaré valide ?

Les contrats détaillés d'opération ne sont pas encore branchés au validateur. La
validation actuelle couvre uniquement un sous-ensemble statique. Cette lacune fait
partie du travail G0.

### Quels profils existent ?

- P1 : opérations prismatiques et tournées de base ;
- P2 : P1 plus `thread`, matériaux et PMI cibles ;
- P3 : assemblages et configurations cibles ;
- P4 : géométrie avancée.

Dans le prototype, les profils contrôlent surtout la liste des noms d'opérations.
Aucun profil n'est encore exécuté par un noyau.

### Pourquoi `cardinality = unique` est-il obligatoire ?

Parce que sélectionner silencieusement la première face parmi plusieurs candidats
peut modifier une pièce. Une référence doit être unique, manquante ou ambiguë. Le
dernier état nécessite une décision ou une meilleure requête.

### Puis-je utiliser `cardinality = many` ?

Le modèle cible prévoit des ensembles typés, mais le validateur de références
persistantes actuel exige `unique` ou `one`. Les références multi-entités devront
recevoir un contrat séparé avant d'être acceptées.

### Les UUID sont-ils obligatoires ?

Pas dans le prototype. En leur absence, le compilateur dérive un UUIDv5 du namespace
et du chemin. Comme un renommage modifie ce chemin, un UUID explicite est fortement
recommandé pour tout actif appelé à survivre aux éditions et round-trips.

### Le hash sémantique est-il définitif ?

Non. Il est déterministe dans l'implémentation actuelle, mais le contrat de
canonicalisation peut évoluer en 0.x. Le gate exige encore une seconde
implémentation indépendante et une bijectivité complète.

### Les imports sont-ils téléchargés ?

Non. Le parser conserve une URI ou un chemin et un alias. Aucun resolver, allowlist,
digest ou téléchargement n'est actif.

### Les scénarios `validate` sont-ils exécutés ?

Non. Ils sont parsés et abaissés dans l'IR. Leur exécution transactionnelle après
modification de paramètres est une cible essentielle de conformité comportementale.

### MORPHOIA possède-t-il déjà undo/redo et des transactions ?

Oui, sous forme d'un `RuntimeStore` en mémoire testé unitairement. Il gère commit
atomique, rollback, undo/redo et conflits optimistes sur le graphe JSON. Il n'est pas
encore persistant et n'est pas raccordé à un noyau ou aux scénarios `.morph`.

### Le registre des pertes est-il déjà utilisé par les exports ?

Le type `LossRegister` et sa règle de blocage existent, mais aucun export CAO n'est
encore implémenté. Son intégration aux adaptateurs reste une cible.

### MORPHOIA utilise-t-il déjà l'IA ou le GPU ?

Non. Les documents définissent les pipelines visés, mais le code présent est un
lexer, parser, validateur partiel, compilateur JSON et contrat de référence.

### Peut-on générer des fichiers `.morph` avec un LLM ?

Oui à titre expérimental, à condition de toujours les passer au validateur et de ne
pas confondre validité syntaxique avec exactitude mécanique. La cible de Phase 2 est
au moins 98 % de sorties syntaxiquement valides avec décodage contraint, mais elle
n'est pas encore démontrée.

### Quelle est la licence ?

Le dépôt est distribué sous licence MIT, conformément au fichier `LICENSE` choisi lors de la
création du dépôt GitHub. Les standards tiers, SDK commerciaux, corpus et marques restent
soumis à leurs propres droits. Une éventuelle politique distincte pour la spécification, les
données ou la marque exigera une décision et une revue juridique séparées.

### Comment proposer un composant nouveau ?

Il faut d'abord remplir le
[`Component Justification Record`](decisions/CJR-TEMPLATE.md), comparer les solutions
existantes, préenregistrer la métrique et démontrer le manque ou l'avantage. Une
amélioration esthétique d'API ne suffit pas.

### Quels sont les gates avant une version 1.0 ?

| Gate | Critère principal | Statut |
|---|---|---|
| G0 | Draft, implémentation de référence, 100 cas golden | En cours |
| G1 | Deux backends P1/P2, B-rep ≥99 %, scénarios ≥95 % | Non atteint |
| G2 | Conformité publique et implémentation indépendante | Non atteint |
| G3 | Gain humain médian ≥40 % sur deux pilotes | Non atteint |
| G4 | Gouvernance externe et politique brevets après G1-G3 | Interdit avant preuves |

### Où continuer ?

- [Guide utilisateur](user-guide.md)
- [Guide développeur](developer-guide.md)
- [Spécification candidate](language-specification.md)
- [Grammaire EBNF](grammar.ebnf)
- [Exigences et gates](requirements.md)
