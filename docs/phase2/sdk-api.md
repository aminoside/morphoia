# SDK et API MORPHOIA

## 1. Statut et portée

Ce document décrit à la fois l'API **réellement implémentée** dans le prototype
Python et l'**architecture cible** du SDK. Ces deux états ne doivent pas être
confondus.

MORPHOIA reste un **candidat expérimental 0.1**. Il ne s'agit ni d'un SDK stable,
ni d'une norme, ni d'une promesse de compatibilité binaire ou fonctionnelle.
La façade textuelle et l'encodage JSON peuvent encore être remplacés si les
benchmarks ne démontrent pas leur utilité.

Le module Python annonce actuellement `0.2.0-dev` et la métadonnée de
distribution `0.2.0.dev0`. Ces versions de développement du paquet ne changent
pas le statut des contrats de données : la façade source, le graphe canonique,
les manifests et les registres décrits ici restent des formats candidats `0.1`.

### Légende de maturité

| Marqueur | Signification |
|---|---|
| **Implémenté 0.1** | Code présent et couvert au moins par un test local |
| **Partiel 0.1** | Prototype présent, mais contrat ou couverture incomplet |
| **Cible** | Architecture prévue, sans implémentation utilisable dans le dépôt |
| **Hors périmètre 0.1** | Ne doit pas être attendu du prototype actuel |

## 2. Principes imposés par la Phase 1

1. STEP/AP242 et ISO 10303-42/-55/-108/-109/-111/-112/-113 restent les
   ancres sémantiques ; le SDK ne crée pas une ontologie mécanique concurrente.
2. OCCT doit être réutilisé comme premier noyau exact ouvert. MORPHOIA ne
   réécrit pas un noyau B-rep.
3. Le modèle canonique ne contient aucun type, pointeur ou index natif d'un
   noyau ou d'une CAO.
4. L'IA propose des candidats. Le runtime, les solveurs, les noyaux et les
   validateurs décident si un candidat peut être accepté.
5. Toute approximation, réparation, substitution, omission ou incompatibilité
   produit une perte machine-readable. Il n'existe pas de fallback silencieux.
6. Le résultat explicite, les propriétés de validation, l'environnement et le
   graphe procédural doivent pouvoir être conservés ensemble.

## 3. Inventaire exact du prototype Python

| Capacité | État | Module ou commande | Limite explicite |
|---|---|---|---|
| Lexer et parser de la façade `.morph` | **Implémenté 0.1** | `morphoia.parser.parse` | Façade expérimentale, non standardisée |
| Validation syntaxique et sémantique | **Partiel 0.1** | `validate_source`, `validate_file` | Ne valide ni B-rep, ni STEP, ni PMI exécuté |
| Compilation vers graphe JSON canonique | **Implémenté 0.1** | `compile_document` | Produit un dictionnaire ; aucun noyau n'est appelé |
| JSON canonique et hash sémantique | **Implémenté 0.1** | `canonical_json`, `semantic_hash` | Déterminisme testé seulement dans le prototype Python |
| Résolution topologique à trois états | **Partiel 0.1** | `morphoia.topology` | Filtrage exact sur candidats fournis ; ne résout pas le problème universel de nommage |
| Contrat Python abstrait de backend | **Partiel 0.1** | `morphoia.backends.base` | Pas de découverte, manifest, isolation ou négociation automatique |
| Backend de sérialisation JSON | **Implémenté 0.1** | `CanonicalJsonBackend` | Encodeur uniquement ; aucune géométrie exacte |
| Révisions et transactions en mémoire | **Partiel 0.1** | `morphoia.runtime.RuntimeStore` | Aucun stockage persistant, backend ou verrouillage multi-processus |
| Preuves et décisions | **Partiel 0.1** | `morphoia.provenance` | Primitives isolées ; pas encore reliées automatiquement au graphe |
| Registre des pertes Python | **Partiel 0.1** | `morphoia.losses` | Création manuelle ; aucun adaptateur ne le produit automatiquement |
| CLI `validate` | **Implémenté 0.1** | `python -m morphoia validate` | Diagnostics syntaxiques/sémantiques seulement |
| CLI `compile` | **Implémenté 0.1** | `python -m morphoia compile` | Écrit le graphe JSON ; aucun choix de backend |
| Schéma JSON du graphe | **Partiel 0.1** | `schemas/morphoia-ir-0.1.schema.json` | Le prototype ne lance pas automatiquement un validateur JSON Schema |
| Schéma du registre des pertes | **Partiel 0.1** | `morphoia-loss-register-0.1.schema.json` | Reflète `LossRegister.to_dict()` ; validation non automatique |
| Manifest backend | **Contrat candidat 0.1** | `morphoia-backend-manifest-0.1.schema.json` | Aucun chargeur ou négociateur n'est encore implémenté |
| Backend OCCT, STEP ou FreeCAD | **Cible** | - | Absent du dépôt actuel |
| Backend Parasolid ou CAO commerciale | **Cible optionnelle** | - | Nécessite SDK, contrat et licence |
| Coeur C++, ABI C et bindings | **Cible** | - | Aucun code C/C++ présent |
| Service réseau, sandbox et plugins signés | **Cible** | - | Aucun daemon ni mécanisme de sécurité correspondant |

La déclaration des profils `P1` à `P4` par le backend JSON signifie qu'il peut
préserver les noeuds JSON correspondants. Elle ne prouve pas qu'il sait exécuter
leur géométrie ou qu'il est conforme à ces profils.

## 4. API Python réellement disponible

Les seuls symboles exportés à la racine du paquet sont :

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

### 4.1 Validation sûre

```python
from morphoia import compile_document, validate_source

source = """morphoia 0.1;
model Block [profile = "P1"] {
  parameter height: length = 10 mm;
}
"""

result = validate_source(source)
if not result.ok or result.document is None:
    for diagnostic in result.diagnostics:
        print(diagnostic.code, diagnostic.severity.value, diagnostic.message)
else:
    ir = compile_document(result.document)
    print(ir["semantic_sha256"])
```

`validate_source(source: str) -> ValidationResult` capture les erreurs du lexer
et du parser, puis applique les règles sémantiques disponibles.
`validate_file(path) -> ValidationResult` lit un fichier UTF-8 et appelle la
même pipeline. Les erreurs d'accès au fichier ne sont pas transformées en
diagnostics MORPHOIA.

`parse(source: str) -> Document` est une API de plus bas niveau. Elle peut lever
`LexError` ou `ParseError` et ne lance pas la validation sémantique.

### 4.2 Compilation candidate

`compile_document(document) -> dict[str, Any]` abaisse un AST en graphe JSON
déterministe et ajoute `semantic_sha256`. Le contrat d'appel impose de valider
le document avant compilation ; la fonction ne répète pas elle-même toutes les
validations.

`canonical_json(ir, indent=2) -> str` trie les clés et termine par une nouvelle
ligne. `semantic_hash(ir) -> str` calcule SHA-256 sur l'encodage compact trié en
ignorant le champ `semantic_sha256` déjà présent.

Ces fonctions ne prouvent ni la reproductibilité multi-langage, ni
l'équivalence de deux B-rep, ni le déterminisme d'un noyau.

### 4.3 AST et diagnostics

`morphoia.model` contient des dataclasses immuables pour les positions,
expressions, noeuds, modèles et documents. `ValidationResult.ok` est vrai si un
document existe et qu'aucun diagnostic de sévérité `error` n'est présent.

Ces classes sont nécessaires au prototype, mais elles ne sont pas exportées à
la racine et ne bénéficient d'aucune garantie de stabilité 0.x.

### 4.4 Références topologiques

`resolve_reference(query, candidates)` filtre les candidats sur :

- type d'entité ;
- feature productrice ;
- rôle sémantique ;
- termes exacts de signature ;
- contexte d'adjacence demandé.

Le résultat est `unique`, `ambiguous` ou `missing`. Accéder à `.entity` sur un
résultat non unique lève `LookupError`. Le score flou, la propagation de lignée
au travers d'opérations OCCT et la résolution après édition sont des cibles,
pas des capacités actuelles.

### 4.5 Backend Python minimal

Le contrat actuel est volontairement petit :

```python
class Backend(ABC):
    def capabilities(self) -> BackendCapabilities: ...
    def execute(self, canonical_ir: dict[str, Any]) -> BackendResult: ...
```

`BackendCapabilities` contient actuellement `name`, `version`, `profiles`,
`operations`, `exact_brep`, `pmi`, `deterministic_mode` et `license`.
`BackendResult` contient `success`, `artifact_uri`, `validation_properties`,
`losses` et `diagnostics`.

`CanonicalJsonBackend` écrit un graphe JSON et retourne son hash comme propriété
de validation. Il ne valide pas le graphe contre son JSON Schema et ne produit
pas encore un registre de pertes conforme au schéma candidat.

### 4.6 Transactions, provenance et pertes

`RuntimeStore` fournit un historique immuable **en mémoire**. Une transaction
travaille sur une copie du graphe, peut recevoir des fonctions de validation,
effectue un commit atomique ou un rollback, détecte une révision de base
obsolète et permet undo/redo. Cette preuve de contrat ne fournit pas de
persistance, d'isolation entre processus, de solveur ou d'exécution géométrique.

`Evidence` vérifie notamment la forme d'un SHA-256. `Decision` représente
`candidate`, `accepted`, `rejected` ou `abstained`, borne la confiance à
`[0, 1]` et exige preuve et acteur pour une décision acceptée. Ces objets ne
sont pas encore sérialisés dans l'IR ni résolus par le runtime.

`LossRecord` et `LossRegister` fournissent un registre simple sérialisable en
dictionnaire. Une perte `error` ou `fatal` fait passer `blocks_commit` à vrai.
Le schéma 0.1 reflète cette représentation. Les IDs de transformation,
environnements verrouillés, liens de preuves et compteurs détaillés décrits
plus loin restent une cible d'enrichissement.

## 5. CLI disponible

```bash
PYTHONPATH=src python -m morphoia validate model.morph
PYTHONPATH=src python -m morphoia validate model.morph --json
PYTHONPATH=src python -m morphoia compile model.morph -o model.mcir.json
```

Codes de sortie : `0` si la validation réussit, `1` si elle échoue. La commande
`compile` valide d'abord la source, puis écrit le JSON. Il n'existe actuellement
aucune commande `execute`, `export-step`, `diff`, `bench`, `serve` ou
`backend list`.

## 6. Architecture cible du SDK

Les sections suivantes décrivent une cible et non du code livré.

### 6.1 Coeur C++ et ABI de plugins

Le coeur déterministe cible C++ et doit porter :

- modèle canonique typé ;
- unités et quatre catégories de tolérances distinctes ;
- transactions, DAG, commit et rollback ;
- solveur et résolution des références ;
- exécution de backend ;
- propriétés de validation et rapports structurés ;
- limites de ressources et journalisation.

Les plugins doivent utiliser une ABI C versionnée avec handles opaques. Une API
C++ ergonomique peut l'envelopper, mais elle ne constitue pas l'ABI stable.
Aucun type OCCT, Parasolid, FreeCAD ou CAO native ne traverse cette frontière.

### 6.2 Manifest backend

Tout backend cible fournit un document conforme à
[`morphoia-backend-manifest-0.1.schema.json`](../../schemas/morphoia-backend-manifest-0.1.schema.json).
Le manifest déclare notamment :

- identité, version et état expérimental ;
- mode d'entrée : bibliothèque, worker ou service ;
- profils, opérations et formats réellement supportés ;
- B-rep exacte, PMI, assemblages et modes déterministes ;
- plateformes, GPU, isolation et permissions ;
- licence, redistribution, cloud et restrictions ;
- état de qualification et lien vers le rapport de test.

Le chargement cible suit : découverte, validation du manifest, contrôle de
licence et d'intégrité, négociation de capacités, préflight, exécution isolée,
validation, collecte du registre des pertes, puis destruction du contexte.

### 6.3 API cible par responsabilité

| Domaine | Responsabilité cible |
|---|---|
| `model` | documents, révisions, noeuds, expressions et IDs canoniques |
| `profiles` | P1-P4, opérations, capacités et règles de fallback |
| `execution` | planification, transactions, solveur et backend |
| `topology` | lignée, requêtes, ambiguïtés et décisions humaines |
| `validation` | propriétés, scénarios, diff et rapports |
| `losses` | production, fusion et validation du registre des pertes |
| `io` | STEP/AP242, QIF, AP238 et vues dérivées |
| `provenance` | sources, preuves, licences, décisions et confiance |
| `ml` | candidats IA non autoritatifs |
| `bench` | corpus, environnements et résultats reproductibles |

### 6.4 Backends cibles

| Backend | Mode cible | Rôle autorisé |
|---|---|---|
| OCCT/OCAF/XDE | bibliothèque ou worker | backend exact ouvert initial, STEP et propriétés |
| FreeCAD | worker headless versionné | oracle de recompute, Sketcher et cible ouverte |
| Parasolid/ACIS/CGM/C3D | plugin sous licence | backend ou oracle optionnel |
| CAO native | worker par produit/version | import/export borné et cible utilisateur |
| Blender | worker isolé | rendu et données synthétiques uniquement |
| glTF/OpenUSD/JT | encodeur de vue | représentation dérivée, jamais autorité |

### 6.5 Services cibles

Un service réseau éventuel enveloppe les mêmes contrats et ne remplace pas le
SDK local. Les appels longs utilisent des jobs idempotents avec artefacts
adressés par contenu. Un résultat doit inclure versions, environnement,
diagnostics, propriétés et registre des pertes.

Le transport cible peut être gRPC ou HTTP, mais aucune route ou compatibilité
réseau n'est promise en 0.1.

## 7. Erreurs, pertes et diagnostics

Le prototype utilise des diagnostics `MORPH-E...` structurés pour la source,
mais les diagnostics de backend sont encore de simples chaînes.

La cible impose :

- un code stable et namespacé ;
- une sévérité ;
- une localisation source ou un ID canonique ;
- le backend, sa version et l'opération ;
- une preuve ou propriété mesurée ;
- une action recommandée ;
- un lien vers une perte lorsque le résultat est dégradé.

Le prototype peut construire manuellement un document conforme à
[`morphoia-loss-register-0.1.schema.json`](../../schemas/morphoia-loss-register-0.1.schema.json).
Il ne branche toutefois pas automatiquement ce registre sur les backends ou
les transactions et ne le valide pas automatiquement. La cible exige qu'une
transformation non lossless produise ce registre sans intervention du caller,
puis l'enrichisse dans une version ultérieure avec environnement, preuves et
références canoniques.

## 8. Versioning et compatibilité

- Les versions du paquet, de la façade, de l'IR, des profils, des schémas et de
  chaque backend sont indépendantes.
- Toute révision `0.x` peut rompre la compatibilité avec justification et note
  de migration.
- Un backend n'est jamais déclaré « compatible MORPHOIA » sans profil, version,
  plateforme et rapport de test.
- Une extension inconnue peut être préservée, mais elle n'est pas exécutée.
- Les mots `stable`, `certified`, `standard` et `1.0` sont interdits avant les
  gates définis dans le cahier des charges.

## 9. Sécurité cible

- aucune exécution de Python arbitraire dans le chemin de confiance ;
- parseurs et adaptateurs externes hors processus ;
- quotas CPU, GPU, mémoire, taille d'entrée et temps ;
- réseau et système de fichiers refusés par défaut ;
- manifests, plugins, modèles et artefacts signés après G1 ;
- aucune donnée client réutilisée pour l'entraînement sans droit explicite ;
- logs sans secrets et provenance de chaque artefact.

Ces protections sont **non implémentées** dans le prototype Python actuel.

## 10. Gates d'implémentation SDK

| Gate | Preuve minimale |
|---|---|
| SDK-0 | APIs Python actuelles, tests parser/topologie et schémas candidats |
| SDK-1 | Validation JSON Schema automatique et registres de pertes produits |
| SDK-2 | Backend OCCT P1, résultat B-rep et propriétés de validation |
| SDK-3 | Second backend indépendant, manifeste et tests différentiels |
| SDK-4 | ABI C, bindings Python, sandbox et matrice multi-plateforme |
| SDK-5 | Deux implémentations indépendantes et suite de conformité publique |

Le dépôt actuel se situe à **SDK-0 partiel**.
