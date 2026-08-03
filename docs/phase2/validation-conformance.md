# Validation et conformité MORPHOIA

## 1. Statut

MORPHOIA est un **candidat expérimental 0.1**. Le dépôt fournit quelques
validateurs exécutables, mais aucune suite de conformité industrielle, aucun
backend géométrique qualifié et aucune certification.

Dans ce document :

- **validation** signifie qu'un contrôle déterminé a été exécuté ;
- **conformité candidate** signifie qu'un profil, une version, un backend, une
  plateforme et un corpus ont tous été explicitement identifiés ;
- **certification** est réservée à une gouvernance et un organisme qui
  n'existent pas encore.

Le succès du prototype Python ne démontre ni compatibilité STEP, ni validité
B-rep, ni portabilité multi-CAO.

## 2. Contrôles réellement implémentés

| Contrôle | État 0.1 | Preuve dans le dépôt | Ce qu'il ne prouve pas |
|---|---|---|---|
| Erreurs lexicales et syntaxiques | **Implémenté** | `lexer.py`, `parser.py`, `validator.py` | Sémantique géométrique |
| Version de façade `0.1` | **Implémenté** | `MORPH-E001` | Compatibilité future |
| Doublons de déclarations | **Implémenté** | `MORPH-E101` | Unicité globale multi-document |
| Références inconnues | **Implémenté** | `MORPH-E102` | Résolution dans une B-rep réelle |
| Cycles du graphe de construction | **Implémenté** | `MORPH-E103` | Cycles algébriques du solveur |
| Cohérence dimensionnelle de paramètres | **Partiel** | `MORPH-E110` | Analyse complète de toutes les expressions et PMI |
| Disponibilité des opérations par profil | **Partiel** | `MORPH-E120` | Exécution réelle de P1-P4 |
| Forme minimale des références persistantes | **Partiel** | `MORPH-E130` à `E134` | Nommage persistant après opérations de noyau |
| Quatre catégories de tolérance | **Partiel** | `MORPH-E140` | Calcul ou vérification métrologique |
| Provenance des hypothèses | **Partiel** | `MORPH-E150` | Authenticité ou qualité de la preuve |
| Résolution `unique/ambiguous/missing` | **Implémenté sur candidats fournis** | `topology.py`, tests unitaires | Recherche, lignée ou score sur B-rep |
| Hash sémantique déterministe | **Implémenté en Python** | `compiler.py`, test de répétition | Hash multi-langage ou équivalence géométrique |
| Commit/rollback et undo/redo atomiques | **Implémenté en mémoire** | `runtime.py`, tests unitaires | Persistance, concurrence distribuée ou géométrie |
| Conflit de révision optimiste | **Implémenté en mémoire** | `RevisionConflict` | Verrouillage multi-processus |
| Preuves et décisions acceptées | **Partiel** | `provenance.py` | Intégration automatique au graphe et vérification de la source |
| Schéma JSON de l'IR | **Contrat candidat** | `morphoia-ir-0.1.schema.json` | Le compilateur ne le valide pas automatiquement |
| Registre des pertes | **Partiel** | `losses.py` et schéma 0.1 | Construction manuelle ; aucun backend ne le produit automatiquement |
| Manifest backend | **Schéma candidat uniquement** | `morphoia-backend-manifest-0.1.schema.json` | Aucun plugin n'est découvert ou qualifié |

Il n'existe actuellement aucun contrôle de solide, de surface, de topologie
OCCT, de healing, de propriétés de masse, de PMI, de STEP round-trip, de
scénario d'édition ou de comparaison multi-backend.

## 3. Niveaux de validation cibles

| Niveau | Objet | État actuel |
|---|---|---|
| V0 - Source | lexer, parser, types, unités, symboles et DAG | Partiel |
| V1 - Graphe canonique | JSON Schema, invariants, profils, provenance et hash | Partiel |
| V2 - Préflight backend | manifest, capacités, licence, environnement et quotas | Non implémenté |
| V3 - Géométrie | B-rep, manifold, tolérances, propriétés et healing | Non implémenté |
| V4 - Comportement | scénarios d'édition, lignée et références | Non implémenté |
| V5 - Interopérabilité | export/import, STEP/AP242, PMI et pertes | Non implémenté |
| V6 - Différentiel | mêmes cas sur deux noyaux ou CAO | Non implémenté |
| V7 - Conformité | corpus public, implémentation indépendante et gouvernance | Non atteint |

Un niveau supérieur n'annule jamais les résultats inférieurs. Un modèle peut
être syntaxiquement valide et géométriquement invalide, ou géométriquement
valide et comportementalement non conforme.

## 4. Modèle de verdict

Chaque contrôle cible retourne l'un des verdicts suivants :

| Verdict | Sens |
|---|---|
| `pass` | exigence satisfaite avec preuve |
| `fail` | exigence obligatoire violée |
| `warning` | résultat utilisable selon politique, perte déclarée |
| `skipped` | contrôle prévu mais non exécuté |
| `not_applicable` | contrôle hors du profil déclaré |

Un contrôle `skipped` ne peut pas être interprété comme `pass`. Un rapport de
conformité doit échouer si un contrôle obligatoire du profil est `skipped`, si
une ambiguïté est résolue silencieusement ou si une perte requise est absente.

Chaque résultat cible contient au minimum : identifiant d'exigence, profil,
verdict, mesure, seuil, unité, IDs canoniques affectés, preuves, backend,
environnement et diagnostics.

## 5. Validation du graphe

La pipeline cible V0/V1 est :

1. parser la façade candidate ou lire directement l'IR ;
2. valider le JSON Schema correspondant à la version exacte ;
3. résoudre imports, namespaces et extensions ;
4. vérifier types, dimensions et unités ;
5. vérifier unicité des IDs et intégrité des références ;
6. construire le DAG et refuser les cycles de construction ;
7. vérifier profils et capacités demandées ;
8. vérifier preuves, licences et états d'incertitude ;
9. recalculer le hash sémantique ;
10. produire un rapport structuré.

Le prototype exécute seulement une partie de ces étapes sur la façade source.

## 6. Validation géométrique cible

Pour chaque résultat B-rep, V3 doit contrôler :

- validité topologique selon le noyau et vérifications indépendantes possibles ;
- orientation des shells et fermeture des solides ;
- manifold/non-manifold selon le profil ;
- courbes 3D, p-curves et cohérence arête-face ;
- tolérances par entité et dépassements ;
- auto-intersections, singularités et géométries dégénérées ;
- nombre de corps, shells, faces, arêtes et sommets ;
- boîte englobante, aire, volume, centre de masse et inertie ;
- correspondance entre rôles topologiques attendus et entités produites ;
- événements de healing, avec état avant/après et perte associée.

La valeur exacte des seuils appartient au profil et au corpus. Une réparation
qui modifie topologie, dimension ou association PMI n'est jamais un succès
silencieux.

## 7. Validation comportementale cible

Un scénario d'édition contient :

- révision de départ et environnement verrouillé ;
- patch de paramètres ou de structure ;
- propriétés attendues ou invariants ;
- références qui doivent rester uniques, devenir ambiguës ou disparaître ;
- résultat attendu : commit ou rollback ;
- tolérances de comparaison ;
- pertes autorisées et interdites.

Le corpus minimal couvre variation nominale, valeurs limites, suppression,
réordonnancement lorsque permis, changement de motif, collision, résultat vide,
référence cassée et cas dégénéré.

La réussite géométrique de l'état initial ne remplace pas ces scénarios.

## 8. Registre des pertes

Chaque import, exécution, migration, export ou round-trip non lossless produit
un document conforme à
[`morphoia-loss-register-0.1.schema.json`](../../schemas/morphoia-loss-register-0.1.schema.json).

Le format **réellement produit** par `LossRegister.to_dict()` contient :

- `schema = "morphoia.loss-register/0.1"` ;
- opération, backend source et backend cible ;
- `blocks_commit` ;
- une liste `records`.

Chaque record contient code, catégorie, sévérité, sujet, message, capacités
source/cible, mitigation et caractère réversible. Les catégories implémentées
couvrent géométrie, topologie, historique paramétrique, contraintes, PMI,
matériau, assemblage, provenance, identité et comportement. Les sévérités sont
`info`, `warning`, `error` et `fatal`.

`blocks_commit` doit être vrai dès qu'au moins un record est `error` ou `fatal`,
et faux sinon. Le schéma 0.1 encode cette relation. La classe Python calcule
également cette valeur.

Le prototype ne relie pas encore automatiquement un registre à un backend, une
transaction ou un rapport de validation. Les éléments suivants restent la
cible d'une version ultérieure : identifiant de transformation, environnement
verrouillé, objets source/cible, preuves, fallback structuré et résumé par
catégorie.

## 9. Qualification d'un backend

Un backend cible fournit un manifest conforme à
[`morphoia-backend-manifest-0.1.schema.json`](../../schemas/morphoia-backend-manifest-0.1.schema.json).
La qualification est toujours bornée par :

```text
backend x version x plateforme x profil x opération x format x PMI x configuration
```

Étapes cibles :

1. valider le manifest et l'intégrité du binaire ;
2. vérifier licence, redistribution et mode cloud ;
3. exécuter microcas et corpus golden ;
4. exécuter cas négatifs et adversariaux ;
5. répéter en mode déterministe ;
6. mesurer performance et mémoire ;
7. exécuter scénarios d'édition ;
8. comparer à un second backend lorsque requis ;
9. produire rapport, matrice de capacités et registres des pertes ;
10. signer le résultat de qualification.

En série 0.1, `qualification.status` est limité à `untested`, `self-tested` ou
`candidate`. Le terme `certified` n'est pas autorisé.

## 10. Profils candidats

| Profil | Périmètre minimal | Condition de claim |
|---|---|---|
| P1 | esquisse contrainte, extrusion, révolution, trou, booléen, motif, miroir, congé et chanfrein constants | toutes les opérations déclarées testées, pertes et fallbacks explicites |
| P2 | P1 + matériau, datums, tolérances et PMI borné | associations PMI validées après édition et round-trip |
| P3 | P2 + occurrences, placements, mates et configurations simples | définition/occurrence et scénarios d'assemblage validés |
| P4 | surfaces/features avancées | profil séparé ; ne bloque pas P1/P2 |

Une claim candidate doit prendre la forme :

```text
MORPHOIA candidate 0.1 / profil P1 / backend <nom>@<version> /
plateforme <système-architecture> / suite <version> / rapport <URI>
```

Les termes « compatible MORPHOIA », « conforme » ou « certifié » sans cette
portée sont interdits.

## 11. Corpus et séparation des données

| Corpus | Fondation | MVP | Cible 1.0 conditionnelle |
|---|---:|---:|---:|
| Microcas noyau | 1 000 | 10 000 | 50 000 |
| Pièces P1/P2 | 500-2 000 | 10 000+ | 50 000+ |
| Scénarios d'édition | 5+ par pièce | 50 000+ | 250 000+ |
| Cas adversariaux | 250 | 2 000 | 10 000 |
| Backends/oracles | 2 | 2 noyaux + 2 CAO | 2 noyaux + 4 CAO |

Les splits se font par famille, fournisseur et date. Des variantes proches ne
doivent pas se retrouver à la fois dans apprentissage et test. Le jeu de
qualification industrielle final reste aveugle et ses droits sont enregistrés.

## 12. Gates mesurables

Les seuils suivants sont des objectifs, pas des performances obtenues :

| Indicateur | Gate POC/MVP |
|---|---:|
| Validité B-rep sur cas supportés | au moins 99 % |
| Dimensions explicitement cotées | 100 % ou abstention |
| Conservation unités/tolérances du profil | 100 % |
| Scénarios d'édition réussis sur acceptés | au moins 95 % |
| Ambiguïtés résolues silencieusement | 0 |
| Round-trip AP242 + propriétés | au moins 99 % |
| Pièces hors profil correctement refusées | au moins 95 % |
| Temps humain médian économisé | au moins 40 % |
| Gain p95 d'un portage GPU accepté | au moins x2 sans perte de précision |

G1 exige P1 et P2 sur deux backends indépendants. G2 exige corpus et suite de
conformité publics ainsi qu'une implémentation indépendante. G3 exige le gain
industriel sur deux pilotes. Le statut de standard candidat reste interdit avant
G1, G2 et G3.

## 13. Performance et reproductibilité

Tout benchmark enregistre :

- modèle CPU/GPU, mémoire, OS, compilateur et drivers ;
- versions du runtime, backend, solveur et dépendances ;
- corpus, digest et conditions d'accès ;
- warm-up, nombre de répétitions et concurrence ;
- temps p50/p95, mémoire maximale et taux d'échec ;
- précision, tolérances et divergences ;
- modes déterministes et seeds ;
- intervalles de confiance lorsque pertinents.

Le déterminisme sémantique exige le même graphe et le même hash. Le déterminisme
de profil exige les mêmes propriétés dans les tolérances avec le même lockfile.
L'équivalence multi-backend n'exige pas les mêmes octets ou la même numérotation
topologique.

## 14. Commandes disponibles aujourd'hui

```bash
PYTHONPATH=src python -m morphoia validate examples/mounting_plate.morph
PYTHONPATH=src python -m morphoia compile examples/mounting_plate.morph \
  -o build/mounting_plate.mcir.json
PYTHONPATH=src python -m unittest discover -s tests -v
```

Ces commandes couvrent V0 et une fraction de V1. Elles ne doivent pas être
présentées comme une suite de conformité.

## 15. Prochain incrément vérifiable

Le prochain incrément cohérent est limité à :

1. valider automatiquement l'IR, les manifests et les registres par JSON Schema ;
2. produire un registre de pertes pour chaque backend, y compris JSON ;
3. ajouter un backend OCCT P1 avec résultat explicite ;
4. mesurer propriétés et validité B-rep ;
5. exécuter au moins cinq scénarios d'édition par pièce ;
6. connecter FreeCAD ou un second oracle ;
7. publier la matrice des pertes et non une claim générale de compatibilité.
