# Spécification technique de la façade MORPHOIA 0.1

## 1. Portée et statut

Ce document spécifie la façade textuelle expérimentale `.morph` et son lowering vers le MORPHOIA Canonical Construction Graph, ou MCCG. Le terme `MUST` indique une règle vérifiée par une implémentation conforme au draft. Le terme `SHOULD` indique une recommandation dont toute dérogation doit être documentée.

La façade n'est pas l'autorité normative future. Le modèle abstrait STEP-centrique, les profils d'exécution et la suite de conformité sont prioritaires. La syntaxe peut changer ou être abandonnée avant 1.0.

## 2. Objectifs

La source doit être :

- lisible par un ingénieur ;
- générable par une IA avec décodage contraint ;
- déterministe et sans état implicite ;
- non Turing-complète ;
- versionnable avec Git ;
- typée en unités et entités topologiques ;
- indépendante d'un noyau ou d'une CAO ;
- compilable vers un graphe canonique ;
- capable de préserver provenance, incertitude et pertes.

Elle ne décrit pas seulement une forme finale. Elle décrit une construction paramétrique et des critères permettant de la vérifier après modification.

## 3. Unité de compilation

Un document commence par la version de la façade :

```morphoia
morphoia 0.1;
namespace org.example.parts;
```

Il peut importer des extensions par URI ou chemin. Une implémentation de production MUST verrouiller version et empreinte dans un manifest externe :

```morphoia
import "urn:morphoia:extension:sheet-metal:0.3.1" as sheet;
```

Le document contient un ou plusieurs modèles. Le profil est un attribut du modèle :

```morphoia
model Bracket [profile = "P1", id = "uuid-stable"] {
  // declarations
}
```

## 4. Modèle d'exécution

### 4.1 Pureté

La série 0.1 ne possède ni I/O, ni réseau, ni horloge, ni générateur aléatoire, ni boucle générale, ni récursion. Les opérations sont pures : leurs résultats dépendent uniquement de leurs entrées, du profil d'exécution verrouillé et des décisions explicites.

### 4.2 Affectation unique

Une déclaration nommée ne peut pas être redéfinie dans le même modèle. Les scénarios peuvent appliquer des valeurs temporaires avec `set`, mais créent une transaction isolée. Ils ne modifient pas l'état de référence.

### 4.3 Ordre

L'ordre textuel sert à la lecture et au diff. L'ordre d'évaluation résulte du DAG des dépendances. Les cycles de construction sont des erreurs statiques. Les cycles algébriques internes au solveur de contraintes sont autorisés car ils appartiennent à un hypergraphe distinct.

### 4.4 Atomicité

Une régénération passe par validation, exécution, résolution des références, propriétés et scénarios. Un échec entraîne rollback. Le dernier snapshot valide reste disponible.

## 5. Déclarations

### 5.1 Paramètre et constante

```morphoia
parameter width: length = 80 mm [
  min = 40 mm,
  max = 200 mm,
  status = observed,
  evidence = "drawing:D1"
];
constant pi_value: scalar = 3.141592653589793;
```

Un paramètre peut être `driving`, `measured`, `inferred` ou `reference` via attribut. Une valeur inférée ou ambiguë MUST référencer au moins une preuve.

### 5.2 Tolérances

Les quatre types sont incompatibles :

```morphoia
tolerance build_precision: kernel_tolerance = 0.001 mm;
tolerance scan_precision: measurement_uncertainty = 0.05 mm;
tolerance drawing_size: dimensional_tolerance = 0.10 mm;
tolerance position_zone: gdt_zone = 0.20 mm;
```

Une tolérance dimensionnelle ne peut pas servir à réparer une intersection de noyau. Une incertitude capteur ne devient pas un intervalle fonctionnel sans décision explicite.

### 5.3 Datums et systèmes de coordonnées

```morphoia
datum base_plane: plane = world.xy;
datum axis_z: axis = world.z;
```

Le repère mécanique par défaut est cartésien et droitier. Une esquisse MUST nommer son plan. Aucun Workplane global implicite n'existe. Les transformations d'assemblage P3 sont rigides ; échelle et cisaillement sont interdits dans le profil mécanique.

### 5.4 Esquisse

```morphoia
sketch outline on base_plane {
  profile outer = rectangle(width, depth, centered = true);
  constraint horizontal(outer.bottom);
  constraint vertical(outer.left);
  dimension overall_width: length = width;
}
```

Le bloc porte entités, contraintes, dimensions et régions. L'implémentation de référence 0.1 accepte un noeud générique ; le profil d'exécution doit fournir un contrat de solveur : état de contrainte, branche, initialisation, seuils, redondances et diagnostics.

### 5.5 Feature

```morphoia
feature blank: extrude {
  profile = outline.outer;
  distance = thickness;
  direction = +world.z;
  result = solid;
}
```

Le type après `:` est l'opération qualifiée. Chaque argument influençant la géométrie MUST être présent ou défini par le profil avec une valeur normative. Les valeurs implicites propres à une CAO sont interdites.

Chaque feature produit une nouvelle version immuable du corps :

```text
BodyVersion[n] + Feature[n+1] -> BodyVersion[n+1]
```

### 5.6 Référence topologique

```morphoia
reference top_face: face = select(
  blank.faces,
  role = "cap.end",
  normal = world.z,
  cardinality = unique
);
```

Une référence MUST utiliser `select`, porter une collection liée à la lignée, un rôle, une signature géométrique ou d'adjacence et une cardinalité unique lorsque le consommateur attend une entité. La résolution retourne :

- `unique` avec une entité ;
- `ambiguous` avec tous les candidats ;
- `missing` sans candidat.

Une implémentation MUST NOT choisir le premier candidat, même si un score permet de les classer.

### 5.7 Matériau, PMI et assemblage

```morphoia
material alloy: material = material_record("EN AW-6061 T6");
pmi hole_size: diameter = diameter_dimension(hole_wall, nominal = hole_diameter);

assembly product {
  occurrence left = instance(part_a);
  occurrence right = instance(part_b);
  constraint mate(left.axis, right.axis);
}
```

Les PMI graphiques ne suffisent pas. P2 exige cible, datum reference frame, zone, modificateurs, unités et règle générale. P3 distingue définition produit, occurrence, placement et configuration.

### 5.8 Validation et scénarios

```morphoia
validate {
  assert manifold(finished);
  assert resolves(top_face, unique);
  scenario WiderPlate {
    set width = 100 mm;
    expect valid(finished);
    expect resolves(top_face, unique);
  }
}
```

Un scénario décrit une modification et des invariants observables. Il est la base de la conformité comportementale.

## 6. Système de types

### 6.1 Types fondamentaux

| Famille | Types |
|---|---|
| Logique | `boolean` |
| Numérique | `integer`, `scalar`, `rational` |
| Texte et identité | `string`, `uri`, `uuid`, `digest`, `semver` |
| Quantités | `length`, `angle`, `area`, `volume`, `mass`, `time`, `temperature`, `force`, `pressure`, `density`, `ratio` |
| Coordonnées | `point2`, `vector2`, `direction2`, `point3`, `vector3`, `direction3`, `frame2`, `frame3`, `transform` |
| Géométrie | `curve2`, `curve3`, `surface`, `region2`, `sketch` |
| Topologie | `vertex`, `edge`, `wire`, `face`, `shell`, `solid`, `body_set` |
| Produit | `part`, `occurrence`, `assembly`, `configuration`, `material` |
| MBD | `datum`, `datum_system`, `pmi`, `geometric_tolerance`, `surface_texture` |
| Provenance | `evidence`, `hypothesis`, `decision`, `loss_record` |

La grammaire 0.1 exprime un `TypeRef` qualifié simple. Les types paramétrés comme `Ref<Face, one>` appartiennent au modèle abstrait cible et seront introduits uniquement après preuve d'ergonomie et de parsing indépendant.

### 6.2 Unités

Une quantité physique porte une unité : `25 mm`, `0.5 deg`. Les opérations arithmétiques vérifient les dimensions. `length + angle` est une erreur. `angle` n'est pas assimilé implicitement à `scalar`.

Le registre initial comprend SI et unités industrielles explicitement listées. Le hash sémantique utilise valeur canonique et dimension, tandis que la source conserve l'unité d'écriture. `NaN` et `Infinity` sont interdits.

### 6.3 Types topologiques

Une face, une arête ou un solide ne sont pas interchangeables. Une collection topologique non ordonnée ne peut pas être indexée pour créer une identité persistante. Les opérations doivent déclarer leurs rôles de sortie.

## 7. Identifiants

Une déclaration peut porter `[id = "..."]`. L'ID explicite reste stable après renommage. Si l'ID est absent dans le draft, le compilateur crée un UUIDv5 déterministe à partir du namespace et du chemin symbolique. Cette commodité est réservée au prototypage ; les artefacts destinés au round-trip SHOULD employer des IDs explicites.

Les identifiants internes d'un noyau, offsets de fichier et numéros de face sont interdits comme IDs persistants.

## 8. Expressions

La série 0.1 offre :

- littéraux numériques, chaînes, booléens et null ;
- quantités avec unité ;
- références qualifiées ;
- listes ;
- appels à arguments positionnels ou nommés ;
- opérateurs `+`, `-`, `*`, `/`, `^` ;
- comparaisons ;
- `and`, `or`, `not`.

Les appels nommés utilisent `=` :

```morphoia
rectangle(width, depth, centered = true)
```

L'absence de boucle générale garantit la terminaison syntaxique. Les motifs finis sont des opérations géométriques, pas des boucles du langage.

## 9. Attributs, provenance et incertitude

Les attributs sont une liste clé-valeur située après une déclaration. Les clés standard incluent `id`, `profile`, `status`, `evidence`, `min`, `max`, `step_mapping` et `deprecated`.

Les états de connaissance sont :

- `observed` ou `certain` ;
- `hypothesis` ;
- `ambiguous` ;
- `unknown`.

`hypothesis`, `ambiguous` et `inferred` exigent `evidence`. Une hypothèse ne peut alimenter une sortie automatiquement acceptée avant une décision ou une règle vérifiable.

## 10. Profils

| Profil | Contenu minimal |
|---|---|
| P1 | Pièce prismatique/tournée, paramètres, sketch, extrude, cut, revolve, boolean, hole, pattern, mirror, fillet et chamfer constants |
| P2 | P1 + matériau, datums, PMI/GD&T borné, thread et propriétés de validation |
| P3 | P2 + occurrences, assemblage, mates, configurations et cinématique simple |
| P4 | P3 + sweep, loft, blend, shell, draft, fillets variables et géométrie avancée |

Une opération hors profil est une erreur. Un backend peut déclarer `unsupported`; il ne peut pas produire un résultat approximatif non déclaré.

## 11. Extensions

Une extension comprend URI, version, digest, licence, opérations, types, rôles topologiques, mapping STEP, règles de fallback et tests. Une extension inconnue peut être parsée et conservée. Elle ne peut pas être exécutée.

Les extensions ne contiennent pas de code natif arbitraire. Les implémentations sont fournies par plugins signés ou workers isolés. Un dialecte MLIR peut être généré en interne, mais son assembleur n'est pas l'encodage d'archive.

## 12. Compilation

Ordre logique :

1. UTF-8 et normalisation ;
2. lexing et parsing sans récupération silencieuse ;
3. versions et extensions ;
4. symboles et IDs ;
5. types et unités ;
6. DAG ;
7. capacités du backend ;
8. solveur ;
9. features ;
10. lignée et références ;
11. géométrie, topologie et PMI ;
12. propriétés et scénarios ;
13. export et registre des pertes ;
14. commit atomique.

## 13. Graphe canonique JSON 0.1

Le schéma est publié dans `schemas/morphoia-ir-0.1.schema.json`. Le JSON comprend format, version, namespace, modèles, IDs, expressions, ordre du DAG, contrat d'exécution et hash SHA-256.

L'encodage JSON est destiné au débogage, aux tests et à l'échange entre composants du POC. Une future sérialisation STEP Part 21 ou Part 26 doit réutiliser la sémantique ISO et déclarer les extensions.

## 14. Erreurs minimales

| Code | Signification |
|---|---|
| MORPH-E000 | Erreur lexicale |
| MORPH-E010 | Erreur syntaxique |
| MORPH-E100 | Profil inconnu |
| MORPH-E101 | Déclaration dupliquée |
| MORPH-E102 | Référence inconnue |
| MORPH-E103 | Cycle dans le DAG |
| MORPH-E110 | Type ou unité incompatible |
| MORPH-E120 | Opération hors profil |
| MORPH-E130..134 | Référence persistante incomplète ou ambiguë par contrat |
| MORPH-E140 | Catégorie de tolérance invalide |
| MORPH-E150 | Hypothèse sans preuve |

Les diagnostics doivent être stables, localisés et disponibles en JSON.

## 15. Sécurité et limites

Le parser doit imposer des limites de taille, profondeur, nombre de noeuds et complexité des expressions dans le profil de production. Les imports distants ne sont jamais résolus sans allowlist et digest. Les plugins et parseurs externes sont isolés.

## 16. Critères de maintien de la façade

La syntaxe ne sera maintenue vers 1.0 que si les benchmarks démontrent :

- bijectivité source-graphe-source sur 100 % du profil ;
- hashes identiques pour deux parseurs indépendants ;
- validité syntaxique IA cible au moins 98 % ;
- gain préenregistré de validité sémantique face à CadQuery ;
- réduction préenregistrée du temps de correction humaine ;
- sécurité, terminaison et limites de ressources ;
- portabilité P1/P2 sur deux backends.

En cas d'échec, le graphe canonique et l'API restent ; la façade est abandonnée.
