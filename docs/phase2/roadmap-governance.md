# Feuille de route, gouvernance et adoption

## Statut de ce document

Ce chapitre de la Phase 2 décrit une trajectoire conditionnelle. Il ne transforme pas la
façade textuelle MORPHOIA 0.1 en standard. La Phase 1 impose trois conditions cumulatives
avant toute stabilisation normative : exécution qualifiée du profil P1/P2 sur au moins deux
backends indépendants, publication d'une suite de conformité et mesure d'un bénéfice
industriel. Jusqu'à leur satisfaction, la grammaire, l'IR JSON et les API restent
expérimentales.

## Principes de conduite

1. Réutiliser avant de développer : STEP/AP242 porte l'autorité d'échange, OCCT le backend
   ouvert de référence et les solveurs existants sont évalués avant tout remplacement.
2. Limiter le périmètre par profils : aucune opération P4 ne bloque la qualification P1.
3. Mesurer avant d'optimiser : chaque composant nouveau est précédé d'un Component
   Justification Record (CJR) et d'un benchmark reproductible.
4. Ne jamais masquer une perte, une réparation géométrique, une ambiguïté ou une hypothèse
   issue de l'IA.
5. Garder la géométrie exacte et les décisions normatives sur CPU tant qu'une voie accélérée
   n'a pas démontré une équivalence bornée.

## Profils de conformité proposés

| Profil | Périmètre | Gate principal |
|---|---|---|
| P0 - syntaxe | parsing, types, unités, DAG, diagnostics, IR canonique | corpus syntaxique public et hash stable |
| P1 - pièce mécanique | croquis 2D, extrude, cut, revolve, hole, fillet, chamfer, pattern, mirror, propriétés | OCCT et un second backend, scénarios d'édition >= 95 % |
| P2 - MBD | paramètres, datums, PMI sémantique, tolérances, matériaux, AP242 | association PMI et round-trip >= 99 % |
| P3 - assemblage | occurrences, placements rigides, configurations, mates simples | deux CAO et aucun degré de liberté caché |
| P4 - géométrie avancée | sweep, loft, blend, shell, draft, lois variables | qualification opération par opération |

Un produit peut annoncer plusieurs profils, mais doit publier le manifeste exact de ses
capacités. Un export partiel produit obligatoirement un registre de pertes.

## Étapes et gates

### Fondation - mois 0 à 3

Livrables :

- gel des exigences issues de la Phase 1 et matrice de traçabilité ;
- étude de liberté d'exploitation, politique brevets et contrats de données ;
- définition précise de P0, P1 et P2 ;
- API backend et manifeste de capacités ;
- 100 cas golden, microcas dégénérés et propriétés attendues ;
- procédure ADR/RFC/CJR et politique de sécurité.

Gate : aucune sémantique nouvelle n'est acceptée sans mapping STEP ou CJR approuvé.

Budget indicatif : 0,4 à 0,8 M EUR.

### 0.1 POC - mois 3 à 12

Livrables :

- parseur, validateur, IR canonique et SDK Python ;
- runtime C++ minimal avec ABI C versionnée ;
- backend OCCT/XDE, import/export STEP et propriétés de validation ;
- 8 à 12 opérations P1 ;
- résolveur de références à trois états ;
- 500 à 2 000 pièces et au moins cinq scénarios d'édition par pièce ;
- premier rapport public de divergences et de pertes.

Gate : validité B-rep >= 98 %, zéro ambiguïté choisie silencieusement, reproduction du hash
sémantique sur 100 exécutions et démonstration de la réversibilité des transactions.

Budget cumulé : 1,8 à 4,8 M EUR.

### 0.3 Alpha - mois 12 à 18

Livrables :

- backend FreeCAD headless ou autre deuxième implémentation effectivement indépendante ;
- comparaison différentielle OCCT/second backend ;
- pipeline IA multimodal initial avec décodage contraint et abstention ;
- accélération CUDA des tâches denses, export Blender/glTF ;
- deux pilotes industriels ;
- documentation SDK, notebooks et laboratoire de compatibilité.

Gate : deux backends exécutent le même sous-profil, les écarts sont expliqués et les pilotes
montrent que les données sont légalement utilisables.

Budget cumulé : 4 à 8 M EUR.

### 0.5 MVP vertical - mois 18 à 30

Le MVP cible volontairement les pièces usinées prismatiques et tournées reconstruites depuis
des plans, STEP sans historique ou scans simples. Il couvre P1 et un sous-ensemble borné P2.

Critères de passage :

- validité B-rep >= 99 % ;
- dimensions explicitement cotées : 100 % correctes ou abstention ;
- scénarios d'édition réussis >= 95 % ;
- round-trip AP242 avec propriétés de validation >= 99 % ;
- détection hors profil >= 95 % ;
- gain médian de temps humain >= 40 % ;
- coût total par pièce inférieur à 50 % du coût manuel de référence ;
- au moins 10 000 pièces de test, séparées par famille, fournisseur et date.

Budget cumulé : 7 à 19 M EUR, réserve de risque comprise.

### 0.8 Bêta - mois 30 à 42

Livrables : P3 simple, matrice de versions CAO, suite de conformité publique, télémétrie
consentie, processus de vulnérabilités, cinq à dix clients et premier événement
d'interopérabilité indépendant.

Gate : deux implémentations indépendantes et plusieurs organisations reproduisent les
résultats du profil candidat sans accès à un oracle privé.

Budget cumulé : 15 à 35 M EUR.

### 1.0 - mois 42 à 60

La version 1.0 n'est autorisée que si les trois gates de la Phase 1 sont franchis. Elle doit
comprendre :

- P1/P2 qualifiés sur deux backends ;
- quatre intégrations CAO maintenues avec versions explicites ;
- migration de schéma documentée et LTS d'au moins 24 mois ;
- conformance suite et corpus de référence publiés ;
- gouvernance externe effective ;
- preuve économique indépendante et reproductible.

Budget cumulé : 30 à 90 M EUR. Une fondation industrielle à grande échelle peut ajouter 8 à
30 M EUR.

## Organisation cible

### Organes

- Comité technique : architecture, runtime, SDK et qualité.
- Comité normes et conformité : mappings ISO, profils et certification.
- Comité données, propriété intellectuelle et sécurité : corpus, licences, confidentialité,
  brevets et incidents.
- Mainteneurs de backends : qualification de chaque noyau et version CAO.
- Conseil utilisateurs industriels : priorités, critères d'acceptation et retour d'usage.

Aucun fournisseur de noyau ne doit disposer seul d'un veto sur le modèle neutre. Une décision
normative exige au minimum deux implémentations ou une preuve formelle qu'elle ne dépend pas
d'un backend particulier.

### Processus de décision

- Une ADR enregistre les décisions irréversibles ou structurantes.
- Une RFC publique précède les évolutions du modèle canonique.
- Un CJR est obligatoire pour tout composant inventé ou toute dépendance stratégique.
- Les modifications incompatibles suivent SemVer et fournissent une migration exécutable.
- Les minutes, votes, conflits d'intérêts et résultats de conformité sont publics dès
  l'ouverture du projet.
- Les cas de test deviennent normatifs seulement après revue croisée et reproductibilité.

### Cycle de publication

Les séries 0.x peuvent évoluer rapidement, mais chaque artefact doit déclarer sa version. Les
versions 1.x suivent un cycle prévisible : proposition, période de commentaires, release
candidate, campagne de conformité, publication, puis support LTS. Une extension ne peut
redéfinir silencieusement une opération du coeur.

## Licences et politique de propriété intellectuelle

Le dépôt public a été créé sous licence MIT par Olivier Ami. Le code, les spécifications et
les rapports contenus dans cette version suivent donc le fichier `LICENSE`. Cette licence ne
s'applique pas automatiquement aux standards tiers, SDK commerciaux, jeux de données,
modèles ou marques cités.

Avant une version normative et avant l'arrivée de contributions externes substantielles, une
revue juridique doit comparer le maintien de MIT à une politique différenciée, par exemple :

- Apache License 2.0 pour les futures versions du runtime, du SDK, des outils et du validateur,
  notamment pour sa clause de licence de brevets ;
- CC BY 4.0 pour de futures éditions de la spécification et des guides ;
- licence de données séparée et vérifiée pour chaque corpus ;
- licences commerciales pour les adaptateurs propriétaires, jeux de données sensibles ou
  modèles qui ne peuvent pas être ouverts ;
- politique de marque distincte pour le nom et le label de conformité MORPHOIA.

Une modification future ne retire pas rétroactivement les droits déjà accordés sous MIT. Le
choix doit être précédé d'une revue juridique d'OCCT, FreeCAD, Blender, CUDA/OptiX, des SDK
commerciaux, des brevets et des droits sur les données. Les contributions peuvent suivre un
DCO ou un CLA ; le mécanisme retenu doit préserver l'attribution tout en protégeant la
capacité de standardisation et de gestion des brevets.

## Stratégie d'adoption

1. Résoudre un périmètre étroit avant de revendiquer l'universalité.
2. S'intégrer dans les CAO existantes ; ne pas demander aux ingénieurs de les remplacer.
3. Afficher pour chaque résultat la source, l'hypothèse, la perte, le diff et les scénarios
   d'édition.
4. Publier des connecteurs de lecture et des validateurs avant les outils de création.
5. Organiser des plugfests avec CAx-IF, intégrateurs, éditeurs, fabricants et métrologues.
6. Proposer les profils matures à une organisation de standardisation seulement après deux
   implémentations indépendantes.

Le bénéfice industriel attendu est la réduction des reconstructions manuelles, une meilleure
traçabilité des décisions IA, un archivage moins dépendant d'un éditeur, des migrations CAO
mesurables et une réutilisation plus sûre des actifs mécaniques. Ces bénéfices restent des
hypothèses tant qu'ils ne sont pas mesurés sur les pilotes aveugles définis ci-dessus.
