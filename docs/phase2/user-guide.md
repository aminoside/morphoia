# Guide utilisateur de MORPHOIA

## 1. Statut à lire avant toute utilisation

MORPHOIA est actuellement un **candidat expérimental 0.1**. La façade textuelle
`.morph`, son modèle de données et ses profils peuvent changer ou être abandonnés.
Ils ne constituent ni une norme, ni un format CAO stable, ni un outil certifié.

Deux versions apparaissent actuellement dans le dépôt :

| Élément | Version actuelle | Signification |
|---|---:|---|
| Façade textuelle et IR canonique | `0.1` | Version expérimentale acceptée dans les fichiers `.morph` |
| Paquet Python et CLI | `0.2.0-dev` | Version de développement de l'implémentation de référence |

Un document doit donc commencer par :

```morphoia
morphoia 0.1;
```

La commande `morphoia --version` affiche la version du paquet, pas celle de la
façade. Cette distinction est volontaire pendant le prototypage.

La Phase 1 impose de réutiliser STEP/AP242, les ressources ISO 10303, OCCT et les
solveurs existants avant de créer un composant nouveau. Le prototype actuel sert à
évaluer une syntaxe et un graphe de construction ; il ne démontre pas encore la
portabilité géométrique industrielle.

## 2. Ce que le prototype sait réellement faire

### Implémenté

- analyser lexicalement et syntaxiquement un document MORPHOIA 0.1 ;
- produire des diagnostics localisés, en texte ou en JSON ;
- vérifier une partie des symboles, profils, unités et dépendances ;
- refuser les cycles détectés dans le graphe de déclarations ;
- contrôler le contrat minimal des références topologiques persistantes ;
- distinguer les quatre catégories de tolérances ;
- imposer une preuve aux déclarations marquées `hypothesis`, `ambiguous` ou
  `inferred` ;
- compiler le document vers un graphe canonique JSON déterministe ;
- calculer un hash sémantique SHA-256 ;
- représenter séparément les résultats de résolution topologique `unique`,
  `ambiguous` et `missing` dans l'API Python ;
- gérer en mémoire des révisions immuables avec transaction, commit atomique,
  rollback, undo/redo et rejet des écritures concurrentes obsolètes ;
- représenter des preuves, décisions et abstentions avec contrôles minimaux ;
- produire un registre machine-readable des pertes et bloquer un commit applicatif
  lorsque ce registre contient une perte `error` ou `fatal`.

### Pas encore implémenté

- exécution des opérations par Open CASCADE ou un autre noyau géométrique ;
- création ou validation d'une B-rep ;
- solveur d'esquisse et de contraintes ;
- import ou export STEP/AP242, IGES, Parasolid, ACIS, FreeCAD ou glTF ;
- validation géométrique, topologique, PMI/GD&T ou industrielle ;
- exécution réelle des scénarios d'édition ;
- persistance durable des révisions transactionnelles ;
- raccordement automatique du registre des pertes aux commandes CLI ;
- visualisation 3D ;
- compilation inverse d'un modèle CAO vers une histoire paramétrique ;
- backend GPU, inférence IA ou API asynchrone ;
- résolution et téléchargement des imports ou extensions.

Une source peut donc être déclarée « valide » par le prototype tout en décrivant une
opération géométriquement impossible. Le verdict actuel porte sur la syntaxe et le
sous-ensemble sémantique implémenté, pas sur la fabricabilité ni sur une B-rep.

## 3. Installation

### 3.1 Prérequis

- Python 3.12 ou plus récent ;
- Git ;
- le dépôt MORPHOIA.

```bash
git clone https://github.com/aminoside/morphoia.git
cd morphoia
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Sous PowerShell, l'activation de l'environnement virtuel est :

```powershell
.venv\Scripts\Activate.ps1
```

Pour contribuer et exécuter les outils de développement :

```bash
python -m pip install -e '.[dev]'
```

Il est aussi possible d'utiliser directement un checkout sans installation :

```bash
PYTHONPATH=src python -m morphoia --version
```

## 4. Premier parcours

### 4.1 Valider l'exemple fourni

Depuis la racine du dépôt :

```bash
morphoia validate examples/mounting_plate.morph
```

Résultat attendu :

```text
examples/mounting_plate.morph: valid
```

Sans installation éditable :

```bash
PYTHONPATH=src python -m morphoia validate examples/mounting_plate.morph
```

La commande retourne le code de sortie `0` si le sous-ensemble contrôlé est valide
et `1` si au moins une erreur est détectée.

### 4.2 Compiler vers le graphe canonique JSON

```bash
morphoia compile examples/mounting_plate.morph \
  -o build/mounting_plate.mcir.json
```

La commande crée le dossier de sortie si nécessaire, valide d'abord la source puis
écrit un document JSON trié. Elle affiche le hash sémantique :

```text
wrote build/mounting_plate.mcir.json (<sha256>)
```

Ce JSON est une IR de débogage et d'échange entre composants du prototype. Ce n'est
ni un fichier STEP, ni une B-rep, ni un modèle visualisable.

### 4.3 Obtenir des diagnostics lisibles par une machine

```bash
morphoia validate examples/mounting_plate.morph --json
```

La sortie contient :

- le chemin du fichier ;
- le booléen `valid` ;
- le code, la sévérité et le message de chaque diagnostic ;
- la ligne et la colonne lorsqu'elles sont disponibles ;
- une suggestion facultative dans `hint`.

## 5. Écrire un document 0.1

### 5.1 En-tête, namespace et modèle

```morphoia
morphoia 0.1;
namespace org.example.parts;

model Spacer [
  profile = "P1",
  id = "20000000-0000-4000-8000-000000000001"
] {
  // déclarations
}
```

Le `namespace` est facultatif. Un document doit contenir au moins un modèle. Le
profil par défaut est P1 ; il est néanmoins préférable de le déclarer explicitement.

### 5.2 Paramètres et unités

```morphoia
parameter diameter: length = 20 mm [
  min = 5 mm,
  max = 100 mm,
  status = observed,
  evidence = "drawing:D1"
];
parameter angle_a: angle = 45 deg;
```

Le registre minimal connaît notamment `nm`, `um`, `mm`, `cm`, `m`, `in`, `ft`,
`rad`, `deg`, `mg`, `g`, `kg`, `ms`, `s`, `min`, `N`, `Pa` et `MPa`.

Le typage dimensionnel est encore partiel. Le validateur contrôle en particulier la
dimension d'un littéral affecté à un paramètre :

```morphoia
parameter width: length = 10 deg; // MORPH-E110
```

Les unités composées, conversions avancées et types géométriques complets relèvent
encore de la cible.

### 5.3 Les quatre tolérances non interchangeables

```morphoia
tolerance build_precision: kernel_tolerance = 0.001 mm;
tolerance scan_precision: measurement_uncertainty = 0.05 mm;
tolerance drawing_size: dimensional_tolerance = 0.10 mm;
tolerance position_zone: gdt_zone = 0.20 mm;
```

Le prototype refuse tout autre nom de catégorie avec `MORPH-E140`. Cette séparation
évite d'utiliser une tolérance fonctionnelle comme marge numérique de réparation.

### 5.4 Esquisse et feature

La syntaxe réellement acceptée par le parser actuel utilise un bloc pour chaque
feature :

```morphoia
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
```

Le parser conserve les affectations du bloc. Il ne vérifie pas encore toutes les
préconditions propres à `extrude` et n'exécute pas l'opération.

### 5.5 Référence topologique persistante

```morphoia
reference top_face: face = select(
  body.faces,
  role = "cap.end",
  normal = world.z,
  cardinality = unique
);
```

Le validateur exige actuellement :

- un appel `select(...)` ;
- une collection source positionnelle ;
- un `role` sémantique ;
- `cardinality = unique` ou `one` ;
- au moins une preuve parmi `normal`, `surface`, `area`, `radius`, `adjacent` ou
  `signature`.

Le prototype vérifie le contrat de la requête, mais ne dispose pas encore des faces
d'une B-rep pour l'évaluer. Le module Python `morphoia.topology` contient séparément
le résolveur à trois états utilisé par les tests.

### 5.6 Provenance et incertitude

```morphoia
parameter inferred_width: length = 80 mm [
  status = inferred,
  evidence = "drawing:D1:dimension-7"
];
```

Sans attribut `evidence`, les états `hypothesis`, `ambiguous` et `inferred`
produisent `MORPH-E150`. Ce mécanisme ne transforme pas une estimation en vérité :
la décision et la validation déterministe restent des fonctions cibles.

### 5.7 Scénarios d'édition

```morphoia
validate {
  assert manifold(body);
  scenario Wider {
    set diameter = 30 mm;
    expect valid(body);
  }
}
```

Le parser et le compilateur conservent ces nœuds. Le runtime actuel ne régénère pas
encore la géométrie et n'évalue donc pas réellement les assertions.

## 6. Profils actuels

| Profil | Opérations reconnues par le validateur | Réalité d'exécution |
|---|---|---|
| P1 | `extrude`, `cut`, `revolve`, `boolean`, `hole`, `pattern`, `mirror`, `fillet`, `chamfer` | Non exécutées |
| P2 | P1 + `thread` | Non exécutées |
| P3 | Hérite de P2 ; blocs `assembly` parsables | Aucun moteur d'assemblage |
| P4 | P3 + `sweep`, `loft`, `blend`, `shell`, `draft` | Non exécutées |

Le fait qu'une opération soit reconnue signifie seulement qu'elle n'est pas rejetée
comme hors profil. Cela ne constitue pas une implémentation géométrique.

## 7. Comprendre les diagnostics

| Code | Contrôle actuellement associé |
|---|---|
| `MORPH-E000` | caractère, commentaire ou chaîne invalide |
| `MORPH-E010` | syntaxe invalide |
| `MORPH-E001` | version de façade autre que `0.1` |
| `MORPH-E100` | profil inconnu |
| `MORPH-E101` | déclaration de modèle dupliquée |
| `MORPH-E102` | référence inconnue |
| `MORPH-E103` | cycle de dépendances |
| `MORPH-E110` | dimension incompatible sur un paramètre contrôlé |
| `MORPH-E120` | opération non autorisée par le profil |
| `MORPH-E130..134` | contrat de référence persistante incomplet |
| `MORPH-E140` | catégorie de tolérance invalide |
| `MORPH-E150` | hypothèse ou inférence sans preuve |

Ces contrôles sont volontairement incomplets. Une absence de diagnostic n'est pas
une certification.

## 8. Utiliser l'API Python

```python
from pathlib import Path

from morphoia import RuntimeStore, canonical_json, compile_document, validate_source

source = Path("examples/mounting_plate.morph").read_text(encoding="utf-8")
result = validate_source(source)

if not result.ok or result.document is None:
    for diagnostic in result.diagnostics:
        print(diagnostic.code, diagnostic.message)
    raise SystemExit(1)

ir = compile_document(result.document)
print(ir["semantic_sha256"])
print(canonical_json(ir))

store = RuntimeStore(ir)
transaction = store.begin()
transaction.graph["review_status"] = "reviewed"
revision = transaction.commit("record review status")
print(revision.number, revision.semantic_sha256)
```

Utiliser `validate_source` ou `validate_file` pour les entrées non fiables. La
fonction `parse` lève directement `LexError` ou `ParseError`.

`RuntimeStore` est uniquement un magasin en mémoire servant de contrat exécutable
pour l'atomicité. Il ne lance pas de backend et ne persiste pas ses révisions entre
deux processus.

## 9. Bonnes pratiques pendant la phase expérimentale

- conserver `morphoia 0.1;` tant que le parser ne supporte aucune autre version ;
- attribuer un UUID explicite aux modèles et déclarations qui doivent survivre à un
  renommage ;
- déclarer unités, profil, tolérances et provenance ;
- ne jamais employer un numéro de face de noyau comme identité persistante ;
- exiger une cardinalité unique au lieu de choisir silencieusement un candidat ;
- versionner la source et le JSON canonique utile aux tests, mais ne pas présenter
  ce dernier comme une B-rep ;
- conserver séparément tout STEP ou résultat géométrique de référence ;
- considérer chaque import ou extension comme non résolu dans le prototype actuel ;
- accompagner tout composant nouveau d'un Component Justification Record.

## 10. Gates hérités de la Phase 1

| Gate | Preuve requise | Statut |
|---|---|---|
| G0 | Spécification, implémentation de référence, 100 cas golden | En cours |
| G1 | P1/P2 sur deux backends, B-rep valide ≥99 %, scénarios ≥95 % | Non atteint |
| G2 | Corpus et conformité publics, registre des pertes, seconde implémentation | Non atteint |
| G3 | Gain médian de temps humain ≥40 % sur deux pilotes | Non atteint |
| G4 | G1-G3, gouvernance externe et politique brevets | Interdit avant preuves |

Tant que ces gates ne sont pas franchis, les termes `standard`, `stable`,
`certified` et `1.0` ne doivent pas qualifier MORPHOIA.

## 11. Documents associés

- [Spécification candidate](language-specification.md)
- [Grammaire actuellement implémentée](grammar.ebnf)
- [Catalogue des opérations](operation-catalog.md)
- [Guide développeur](developer-guide.md)
- [Tutoriels et FAQ](tutorials-faq.md)
- [Exigences et gates](requirements.md)
