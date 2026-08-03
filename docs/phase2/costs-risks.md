# Coûts, risques et analyse de faisabilité industrielle

## Portée et méthode

Les valeurs suivantes sont des ordres de grandeur 2026 exprimés hors taxes. Elles couvrent
les équipes, l'infrastructure, les licences de développement, la qualité, le juridique et une
réserve de risque. Elles ne constituent ni devis ni promesse de calendrier. L'intervalle est
large parce que l'accès aux SDK propriétaires, aux corpus industriels et aux experts STEP
domine l'incertitude.

## Estimation par phase

| Phase | Durée | Charge indicative | Coût cumulé |
|---|---:|---:|---:|
| Fondation | 0-3 mois | 4-8 ETP | 0,4-0,8 M EUR |
| POC 0.1 | 3-12 mois | 8-15 ETP.an | 1,8-4,8 M EUR |
| Alpha 0.3 | 12-18 mois | 18-30 personnes | 4-8 M EUR |
| MVP 0.5 | 18-30 mois | 35-60 ETP.an cumulés | 7-19 M EUR |
| Bêta 0.8 | 30-42 mois | 45-80 personnes | 15-35 M EUR |
| Version 1.0 | 42-60 mois | 150-300 ETP.an cumulés | 30-90 M EUR |

Après le MVP, le maintien des versions CAO, SDK, modèles, corpus et règles de conformité
représente environ 18 à 30 % du coût initial par an, soit typiquement 15 à 35 personnes. Une
réserve de 20 à 35 % est recommandée jusqu'au MVP.

## Équipe MVP indicative

- 6 à 10 spécialistes géométrie exacte, STEP, PMI et solveurs ;
- 5 à 8 ingénieurs SDK et adaptateurs CAO ;
- 6 à 10 ingénieurs IA, vision et données ;
- 3 à 5 ingénieurs GPU et plateforme ;
- 5 à 8 spécialistes QA, conformité, métrologie et données de référence ;
- 3 à 5 personnes produit, sécurité, propriété intellectuelle et opérations.

La concentration de compétences rares est un risque en soi : STEP procédural, PMI
sémantique, robustesse B-rep et traduction native disposent de viviers limités. Les revues
externes et partenariats universitaires doivent donc être budgétés dès la fondation.

## Coûts directs à ne pas sous-estimer

1. Licences Parasolid, ACIS, CGM et SDK de traduction, avec environnements de test séparés.
2. Licences et automatisation des versions CATIA, NX, Creo, SolidWorks, Inventor, Fusion 360
   et Rhino.
3. Construction et annotation d'un corpus légal contenant historique, PMI, assemblages et
   scénarios d'édition.
4. Laboratoire matériel multi-OS, GPU NVIDIA/AMD/Intel et CI de longue durée.
5. Audits sécurité, propriété intellectuelle, export control et conformité des données.
6. Participation aux groupes ISO, LOTAR, PDES/CAx-IF et événements d'interopérabilité.
7. Support LTS, migration des schémas et maintenance des backends lors des mises à jour
   annuelles des éditeurs.

## Registre des risques

| Risque | Probabilité | Impact | Signal précoce | Mesure de réduction |
|---|---|---|---|---|
| Périmètre universel prématuré | élevée | critique | ajout de P4 avant stabilité P1 | profils versionnés et gates contractuels |
| Référence topologique cassée | élevée | critique | petite édition invalidant de nombreuses cibles | lignée, rôle, adjacence, signature et abstention |
| Divergence des noyaux | élevée | critique | volumes ou branches différents | tests différentiels, propriétés et pertes explicites |
| Round-trip natif irréalisable | élevée | élevée | historique propriétaire non récupéré | contrats bornés par format/version, pas de promesse universelle |
| Dataset illégal ou biaisé | moyenne | critique | sources sans droits ou benchmark trop facile | audit juridique, splits par famille, test aveugle industriel |
| Hallucination IA | élevée | critique | cotes plausibles sans preuve | preuves obligatoires, décodage contraint, abstention |
| Sur-ajustement au benchmark | moyenne | élevée | forte chute chez les pilotes | corpus secret, adversarial et multi-fournisseur |
| Dépendance SDK fournisseur | élevée | élevée | prix/ABI dicte la roadmap | isolation hors processus et deux backends minimum |
| GPU surestimé | élevée | moyenne | temps dominé par les booléens CPU | profilage de bout en bout avant chaque portage |
| Non-déterminisme numérique | moyenne | élevée | hash ou résultat instable | contrat numérique, versions verrouillées, répétitions |
| Explosion de matrice CAO | élevée | élevée | régressions à chaque version | versions supportées explicites et laboratoire CI |
| Sécurité des fichiers/plugins | moyenne | critique | accès réseau ou système imprévu | sandbox, quotas, processus isolés, signatures |
| Rejet par les ingénieurs | moyenne | critique | corrections répétées ou décisions opaques | UX de preuve, diff, revue et mesure du temps net |
| Litige brevet/licence | faible à moyenne | critique | revendication sur feature ou dataset | FTO, registre SBOM et revue juridique continue |
| Gouvernance capturée | moyenne | élevée | spécification dépendant d'un seul acteur | représentation équilibrée et implémentations indépendantes |

## Verrous scientifiques

### Intention sous-déterminée

Une même B-rep ou photographie correspond à plusieurs historiques paramétriques valides. Il
n'existe généralement pas de reconstruction unique de l'intention. MORPHOIA doit conserver
les alternatives, la provenance et demander une décision lorsque les sources ne départagent
pas les candidats.

### Topological Naming Problem

La continuité d'identité après fusion, scission ou disparition ne peut pas être garantie dans
tous les cas. Le résultat scientifique réaliste est une résolution explicite `unique`,
`ambiguous` ou `missing`, avec scénarios de validation. Toute revendication de solution
universelle serait trompeuse.

### Équivalence procédurale

Deux noyaux peuvent construire des B-rep différentes mais fonctionnellement équivalentes.
L'équivalence doit combiner propriétés, tolérances, PMI et comportement après modification ;
la comparaison octet à octet ne suffit pas. La définition publique de cette équivalence est
un verrou central.

### Robustesse géométrique

Les booléens, offsets, blends, singularités et petits détails restent sensibles aux
tolérances et algorithmes propriétaires. Une couche neutre ne supprime pas ces limites : elle
les rend observables, reproductibles et comparables.

### Validation IA

Les sorties hors distribution et les erreurs de calibration rendent impossible une autonomie
générale sûre à court terme. La voie faisable est une IA de proposition avec exécution
déterministe, preuves, seuils d'abstention et revue humaine.

### B-rep exacte sur GPU

Aucun noyau B-rep général, exact, robuste et déterministe entièrement GPU ne peut aujourd'hui
être considéré comme une brique prête à réutiliser. Le projet doit accélérer les tâches
denses et conserver un chemin CPU de référence.

## Verrous industriels

- accès contractuel aux formats natifs et droits de redistribution ;
- absence de corpus public représentatif avec PMI et historique ;
- qualification multi-version coûteuse des CAO ;
- confidentialité des pièces réelles et contraintes d'export ;
- adoption d'un profil ouvert par des acteurs aux intérêts divergents ;
- responsabilité lorsqu'une reconstruction alimente fabrication ou contrôle qualité ;
- preuve qu'un historique neutre reste modifiable avec le même sens sur plusieurs outils.

## Critères d'arrêt

Le projet doit pouvoir s'arrêter ou réduire son périmètre si l'un des faits suivants est
observé après un pilote correctement instrumenté :

- aucun second backend ne peut exécuter P1 sans dépendre de choix cachés du premier ;
- le gain médian de temps humain reste inférieur à 20 % malgré une précision qualifiée ;
- le taux d'édition réussie reste inférieur à 80 % sur le profil ciblé ;
- les droits nécessaires aux corpus ou SDK rendent une conformance publique impossible ;
- une dépendance propriétaire devient indispensable à la lecture du modèle neutre ;
- le coût par pièce reste supérieur au coût manuel sur les volumes visés.

Ces seuils sont des règles de gouvernance proposées, pas des conclusions déjà démontrées.

## Bénéfices industriels à mesurer

- réduction du temps de reconstruction et de migration ;
- baisse du verrouillage fournisseur pour l'archivage et l'automatisation ;
- traçabilité des cotes, hypothèses et corrections IA ;
- détection plus tôt des pertes PMI et incohérences géométriques ;
- réutilisation des modèles pour simulation, fabrication, métrologie et visualisation ;
- comparaison objective des noyaux et traducteurs ;
- création d'un écosystème de backends et validateurs certifiables.

Le business case doit rapporter ces bénéfices au coût complet : licences, temps de revue,
corrections, calcul, stockage, formation, incidents et maintenance. La métrique centrale est
le temps humain net économisé par pièce acceptée, accompagné du taux d'abstention et du coût
des erreurs évitées.
