# Sommaire

[[TOC]]

[[PAGEBREAK]]

# Résumé exécutif

**Projet : MORPHOIA**
**Auteur : Olivier Ami**

> **Verdict.** Au 3 août 2026, aucune solution existante - norme, noyau, logiciel CAO, langage de script, SDK ou modèle d’IA - ne satisfait seule l’objectif complet de MORPHOIA : reconstruire sans ambiguïté une pièce mécanique en un modèle exact, paramétrique, éditable, porteur de l’intention de conception, du PMI/GD&T, des variantes et des assemblages, puis le reproduire de façon déterministe dans plusieurs systèmes CAO. En revanche, une grande majorité des briques de bas niveau existe déjà et serait réutilisable. Le projet est donc techniquement faisable par paliers, mais un périmètre « universel » dès la première version serait à très haut risque.

L’étude conduit à huit constats structurants.

1. **STEP est plus riche qu’on ne le croit.** AP242 est le meilleur socle normalisé pour la définition mécanique, la géométrie exacte, le PMI, les assemblages et la configuration. Les parties ISO 10303-55, -108, -111 et -112 contiennent déjà des concepts de procédure, paramètres, contraintes, construction de solides et esquisses. Réinventer ces concepts serait inutile.

2. **La capacité normative n’est pas l’interopérabilité réelle.** Les campagnes CAx-IF et LOTAR qualifient surtout la géométrie explicite, les assemblages et le PMI. Aucun programme public ne démontre un round-trip général de l’arbre de features, des contraintes et du comportement de régénération entre CATIA, NX, Creo, SolidWorks, Fusion 360 et Rhino.

3. **Le noyau géométrique n’est pas le modèle de conception.** Open CASCADE Technology (OCCT), Parasolid, ACIS et CGM savent évaluer une géométrie B-rep exacte. Ils ne portent pas, à eux seuls, l’historique utilisateur, l’intention fonctionnelle, les configurations, les règles métier ou le comportement du sketcher.

4. **Les grands logiciels savent presque tout, mais dans des dialectes propriétaires.** CATIA, NX, Creo, SolidWorks et Fusion 360 sont matures pour la CAO mécanique. Leur force vient précisément de sémantiques, solveurs, features, références et formats natifs non interchangeables. Aucun ne peut servir de standard ouvert sans dépendance fournisseur.

5. **Les formats de rendu ne sont pas des formats de conception.** JT, glTF et OpenUSD sont excellents pour le chargement léger, les niveaux de détail, la composition et le GPU. IFC est excellent dans son domaine BIM. Aucun ne représente un historique paramétrique mécanique général avec comportement d’édition.

6. **L’IA a franchi un seuil, mais pas celui de la production arbitraire.** DeepCAD, CAD-SIGNet, TransCAD, CAD-Recode, CADCrafter, CADFS, Pointer-CAD et les générateurs B-rep démontrent des progrès rapides. Les modèles apprennent toutefois surtout sur des pièces simples, des séquences restreintes et des données synthétiques. Les métriques dominantes - Chamfer, IoU, validité ou similarité - ne prouvent ni les tolérances, ni l’intention, ni la stabilité après édition. BenchCAD 2026 confirme l’écart entre forme grossière et programme paramétrique fidèle.

7. **Le GPU est un accélérateur sélectif, pas un substitut au noyau.** CUDA, Warp, Triton, PyTorch3D, Kaolin, OptiX, OpenVDB/NanoVDB et les compilateurs ML accélèrent apprentissage, rendu, échantillonnage, nuages de points, tessellation et calculs différentiables. Aucun noyau open source général de B-rep exacte, paramétrique, robuste et entièrement GPU n’a été identifié.

8. **Le verrou principal est l’équivalence comportementale.** Deux modèles peuvent être géométriquement identiques à l’instant initial et diverger après une modification. Le projet doit donc juger la reconstruction par scénarios d’édition, invariants, PMI, références topologiques et tolérances, pas seulement par ressemblance visuelle.

## Décision de faisabilité

| Question | Réponse du comité |
|---|---|
| Une solution complète existe-t-elle ? | **Non.** Aucun produit ou standard ne couvre l’ensemble avec ouverture, déterminisme et multi-CAO. |
| Le projet est-il scientifiquement faisable ? | **Oui, par sous-ensembles explicitement bornés.** Les primitives, noyaux et travaux de recherche rendent un démonstrateur crédible. |
| Est-il industriellement faisable ? | **Oui sous gouvernance forte**, avec profils de conformité, corpus de référence, contrôle humain et adaptateurs fournisseurs. |
| Faut-il créer immédiatement un nouveau langage ? | **Non.** Il faut d’abord réutiliser STEP procédural/paramétrique et éprouver une représentation intermédiaire interne. Une syntaxe publique serait une décision ultérieure de standardisation. |
| Premier objectif raisonnable | Pièces mécaniques unitaires prismatico-tournées, esquisses contraintes, extrusion/révolution/perçage/motif/congé/chanfrein, unités et tolérances explicites, OCCT comme moteur de référence, export AP242, validation par modifications. |
| Principal risque | Élargir trop tôt aux features surfaciques avancées, tôlerie, assemblages complexes et round-trip natif universel. |

## Recommandation synthétique

À l’issue de l’étude - et seulement à ce stade - la direction la plus prometteuse est une **chaîne hybride, standard-centrée et à exécution vérifiable** : les données d’entrée alimentent un modèle sémantique neutre ancré sur STEP/AP242 et ses ressources procédurales ; l’IA propose des hypothèses structurées et incertaines ; un moteur déterministe vérifie contraintes et dépendances ; un noyau exact calcule la B-rep ; des adaptateurs produisent STEP/QIF et, quand les API le permettent, des modèles natifs. Le GPU est réservé aux étapes massivement parallèles. Cette recommandation est détaillée uniquement en fin de rapport.

---

# Objet, périmètre et méthode

## Question étudiée

L’étude évalue l’existence de solutions permettant de transformer des informations mécaniques hétérogènes - plans 2D, annotations, texte, nuages de points, maillages, B-rep ou CAO native - en modèles reconstruisibles et modifiables, sans perdre les données nécessaires à la fabrication et à l’évolution du produit.

Le besoin de référence est volontairement exigeant : géométrie exacte ; unités ; paramètres ; contraintes ; ordre et dépendances de construction ; références stables ; PMI/GD&T ; matériaux et états de surface ; assemblages ; configurations et variantes ; provenance ; reproductibilité ; compatibilité multi-CAO ; exploitation par l’IA et accélération GPU lorsque pertinente.

Cette phase **ne conçoit pas un nouveau langage**. Elle cherche d’abord les solutions existantes, mesure leur couverture et identifie les seuls manques qui justifieraient un développement.

## Périmètre documentaire

La recherche a couvert, jusqu’au 3 août 2026 :

- normes ISO/IEC, ISO/ASTM et standards de consortiums ;
- documentation officielle des éditeurs et projets open source ;
- publications évaluées par les pairs et prépublications récentes lorsque le domaine évolue plus vite que les cycles éditoriaux ;
- thèses portant sur échange paramétrique, reverse engineering, intention de conception et calcul géométrique GPU ;
- familles de brevets représentatives des axes 2D/3D, IA-vers-CAO, représentation B-rep et échange paramétrique ;
- logiciels industriels de CAO et de reverse engineering ;
- noyaux géométriques, solveurs, traducteurs, SDK et compilateurs ;
- jeux de données, benchmarks et dépôts de code publics.

Les sources primaires ont été privilégiées : ISO, NIST, Khronos, AOUSD, DMSC, CAx-IF, LOTAR, documentation des éditeurs, dépôts officiels, CVF/ACM/IEEE, archives universitaires, arXiv pour les travaux 2025-2026 non encore stabilisés et bases brevets.

## Protocole d’évaluation

Chaque technologie est évaluée selon neuf dimensions imposées : objectif, architecture, modèle de données, performances, avantages, limites, licence, maturité et réutilisation/compatibilité avec un futur standard ouvert.

Quatre règles évitent les faux positifs :

1. Une **B-rep paramétrée mathématiquement** n’est pas nécessairement un **modèle paramétrique éditable**. Une surface NURBS possède des paramètres ; elle ne contient pas pour autant la cote ou la feature qui l’a créée.

2. La **fidélité géométrique instantanée** ne prouve pas la **fidélité comportementale** après modification d’un paramètre.

3. Un logiciel qui **importe ou exporte STEP** ne prend pas nécessairement en charge tout AP242, le PMI sémantique ou les ressources procédurales.

4. Une démonstration IA visuellement convaincante ne prouve pas la validité du solide, les tolérances, la fabricabilité ou la robustesse hors distribution.

## Échelle de maturité utilisée

| Code | Niveau | Signification |
|---|---|---|
| R | Recherche | Prototype, article ou preuve de concept ; corpus limité ; stabilité/API non garanties |
| E | Émergent | Produit ou projet utilisable, mais couverture/interopérabilité encore incomplète |
| M | Mature | Déploiements réguliers, API et communauté/éditeur stables |
| C | Critique industriel | Déployé dans des chaînes de production exigeantes, qualification et support longs |

Les performances sont notées qualitativement quand aucun benchmark public, reproductible et comparable n’existe. Les chiffres marketing non accompagnés de corpus, matériel, tolérances et version ne sont pas traités comme mesures scientifiques.

## Niveaux de sémantique distingués

| Niveau | Contenu | Exemples |
|---|---|---|
| L0 - Visuel | Triangles, matériaux de rendu, scènes, LOD | STL, glTF, OpenUSD, JT léger |
| L1 - Géométrie exacte | Courbes/surfaces analytiques ou NURBS, topologie B-rep | STEP, Parasolid XT, SAT, OCCT |
| L2 - Paramètres/contraintes | Cotes, équations, contraintes géométriques | Sketchers, ISO 10303-108 |
| L3 - Procédure/features | Historique, opérations, dépendances, suppressions | CAO historique, ISO 10303-55/-111/-112 |
| L4 - Intention/PMI | Rôle fonctionnel, GD&T, états de surface, validation | AP242, QIF, MBD natif |
| L5 - Produit | Assemblages, configurations, variantes, cinématique, PLM | AP242, CAO/PLM natifs |
| L6 - Exécution portable | Même résultat et même comportement d’édition entre moteurs | **Non démontré de façon générale** |

## Limites de l’étude

L’étude est exhaustive au sens d’une revue systématique des familles technologiques publiques pertinentes, non au sens d’un audit de chaque version de chaque module commercial. Les limites sont : documentation propriétaire incomplète, tarifs et benchmarks confidentiels, variations de licence par contrat/pays, et délai d’environ dix-huit mois avant publication de certaines demandes de brevet.

La section brevets est une cartographie technique, **pas une analyse de liberté d’exploitation**. Une FTO par conseil en propriété industrielle reste obligatoire avant commercialisation.

[[PAGEBREAK]]

# Normes et formats d’échange

## STEP : architecture et chronologie complète utile

ISO 10303 est une famille modulaire, pas un unique « format STEP ». Son architecture sépare : le langage EXPRESS ; les ressources génériques ; les modules applicatifs ; les protocoles d’application ; les méthodes d’implémentation ; et les suites de conformité. Cette séparation est un atout majeur pour un futur standard ouvert : la sémantique ne dépend ni d’un format de fichier, ni d’un noyau.

| Élément | Objectif et modèle | Performance et maturité | Avantages / limites | Réutilisation |
|---|---|---|---|---|
| ISO 10303-11 EXPRESS | Schéma formel : entités, types, relations, règles et contraintes | C, mature depuis des décennies | Très précis et générateur d’outils ; ce n’est ni un langage d’exécution ni une interface de modélisation | Très élevée pour les schémas |
| ISO 10303-21:2016 | Sérialisation texte Part 21, édition 3 : ancres, références, signatures, UTF-8, archives | C ; universel mais volumineux et batch | Inspectable, diffable à certains niveaux ; parsing et taille moins adaptés au streaming | Très élevée pour échange/archivage |
| ISO/TS 10303-26 | Représentation binaire EXPRESS/HDF5 | E ; adoption limitée | Potentiel grands volumes ; peu d’outillage courant | À évaluer pour stockage interne |
| ISO 10303-28 | Mappage XML | M ; très verbeux | Intégration SI ; coût de volume et parsing | Secondaire |
| SDAI, parties 22-27 | API et bindings historiques C/C++/Java | M mais architecture ancienne | Base d’accès normalisée ; peu adaptée aux usages Python/cloud/GPU modernes | Concepts réutilisables, API à moderniser |

### Protocoles d’application mécaniques

| Version | Objectif | État au 03/08/2026 | Conclusion |
|---|---|---|---|
| AP203 Ed.1, 1994 | Pièces/assemblages mécaniques sous configuration contrôlée | Héritage, remplacé | Important pour archives, pas pour nouveau cœur |
| AP203 Ed.2, 2011 | Extension géométrie, matériaux, PMI et capacités de construction | Retiré/remplacé | Les implémentations historiques sont hétérogènes |
| AP214 Ed.1-3, 1994-2010 | Automobile, structure produit, géométrie, présentation et features | Retiré/remplacé | Le paramétrique général restait hors périmètre |
| AP242 Ed.1, 2014 | Fusion fonctionnelle AP203/AP214, Model-Based Engineering mécanique | M/C selon domaine | Point de bascule industriel |
| AP242 Ed.2, 2020 | Électrique, PDM, PMI, composites et enrichissements mécaniques | M/C | Support commercial variable par profil |
| AP242 Ed.3, 2022 | Corrections/consolidation | M | Version transitoire |
| **AP242 Ed.4, 2025** | Managed model-based 3D engineering : géométrie, PMI, PDM, configuration, scans, contraintes, fabrication | Édition publiée courante | Meilleur socle normatif disponible |
| AP242 Ed.5 | Consolidation suivante | CD, non publiée | À suivre, ne pas cibler comme dépendance normative aujourd’hui |

AP242 Ed.4 couvre filaire, surfaces, B-rep, CSG, tessellation, scans 3D, structure produit, versions/configurations, PMI graphique et sémantique, GD&T, états de surface, accostage, connecteurs, cinématique, composites, harnais, inspection, additif, exigences et vérification. Cette largeur est inégalée, mais aucun éditeur n’implémente nécessairement chaque module.

### Ressources procédurales et paramétriques

| Partie | Objectif / architecture | Modèle de données | Avantages | Limites critiques | Réutilisation |
|---|---|---|---|---|---|
| ISO 10303-55:2005 | Représentation procédurale et hybride | Séquences/hierarchies d’opérations, résultats explicites, opérations supprimées | Conserve procédure et résultat B-rep simultanément | Ne définit pas le catalogue complet d’opérations | Base conceptuelle directe |
| ISO 10303-108:2005 | Paramètres et contraintes explicites | Variables, équations, contraintes 2D/3D, modèles sous-contraints | Neutralise cotes et relations | Exclut historique, solveur, features et comportement d’édition | Base directe, sémantique solveur à compléter |
| ISO 10303-111:2007 | Procédures de modélisation de solides | Commandes de construction et dépendances | Normalise un historique échangeable | Catalogue trop limité face aux features propriétaires | Sous-ensemble initial très utile |
| ISO 10303-112:2006 | Procédures 2D/esquisses | Commandes de construction de profils | Complément naturel au sketcher | Ni heuristiques ni branches de solveur | Très utile pour pièces prismatiques |
| ISO 10303-109:2004 | Contraintes d’assemblage | Liaisons, chemins, paires cinématiques | Couvre une partie de l’accostage | Pas produit/configuration/PMI complet | Complément assemblages |
| ISO 10303-113:2025 | Features mécaniques et identité | Features de fabrication, motifs, identifiants persistants/invariants | Modernise la sémantique de features | Ne garantit pas la stabilité inter-noyaux | Prioritaire à examiner |
| ISO 10303-42:2025 | Géométrie et topologie | Courbes, surfaces, volumes paramétriques, B-splines, B-rep | Géométrie exacte, mature | Aucune intention ou procédure à elle seule | Socle géométrique |

> **Résultat de faisabilité.** La combinaison 55 + 108 + 111 + 112 contient déjà l’essentiel des concepts qu’un système procédural neutre devrait représenter. Le projet doit commencer par une analyse d’écart et une implémentation de profil ; il ne doit pas redéfinir ces notions sous un vocabulaire concurrent.

## Maturité industrielle de STEP

CAx-IF organise des tests d’interopérabilité et publie des pratiques recommandées pour géométrie, assemblages, propriétés de validation, PMI et tessellation. LOTAR utilise AP242 dans l’archivage long terme EN/NAS 9300. Les lots mécaniques publiés portent principalement sur géométrie explicite, assemblages et PMI.

Une feuille de route LOTAR historique mentionnait « CAD 3D parametric » et « parametric assembly » ; ces lots ne figurent toujours pas parmi les lots mécaniques publiés. NISTIR 7433 avait déjà démontré en 2007 un échange semi-automatique d’un sous-ensemble paramétrique et relevé les API opaques, la granularité de feature, les tolérances, le persistent naming et les solveurs comme obstacles.

Il faut donc qualifier trois niveaux séparément :

- conformité syntaxique au schéma ;
- fidélité du résultat géométrique nominal ;
- équivalence du comportement après modification et régénération.

Les deux premiers disposent d’une base industrielle. Le troisième ne dispose pas d’une qualification générale et publique.

## STEP-NC et ISO 14649

ISO 10303-238:2022 AP238 Ed.3 et ISO 14649 décrivent la fabrication par workingsteps, features, opérations, ressources, outils et géométrie. AP238 Ed.4 est au stade DIS en 2026. Ils sont nettement plus sémantiques que le G-code ISO 6983 et permettent un fil AP242-AP238-QIF.

**Performance et maturité.** Des démonstrateurs multi-axes prouvent la faisabilité. L’adoption reste inférieure aux chaînes CAM + post-processeur + G-code ; chaque machine, contrôleur et procédé exige intégration et qualification.

**Licence et ouverture.** Normes ISO payantes ; modèles et démonstrations disponibles via STEP Tools et communautés de standardisation. La réutilisation est très élevée pour la fabrication, mais AP238 ne remplace pas le modèle de conception source.

## Formats mécaniques, de qualité et de fabrication

| Technologie | Objectif / architecture / données | Performance | Licence et maturité | Avantages | Limites | Compatibilité ouverte |
|---|---|---|---|---|---|---|
| **JT / ISO 14306** | Structure produit, facettes compressées, LOD, PMI, variantes et représentations B-rep | Chargement progressif efficace ; très mature en automobile/DMU | ISO 14306 parties 1-4 (2024-2026) ; origine Siemens ; JT Open/toolkits commerciaux | Excellent modèle léger et multi-LOD | Pas d’historique ou contraintes généraux | Élevée comme vue dérivée, faible comme cœur |
| **QIF 3.0 / ISO 23952:2020** | XML modulaire pour MBD, plans de mesure, ressources, règles, résultats, statistiques, UUID | XML plus lourd ; mature en métrologie numérique | Schémas DMSC librement téléchargeables ; norme ISO ; QIF 4 non publié | Boucle qualité et traçabilité PMI | Pas d’historique CAO ou PLM général | Très élevée comme domaine qualité |
| **3MF / ISO/IEC 25422:2025** | Package OPC/ZIP + XML, meshes, composants, build, matériaux, lattice, slices, production, sécurité | Compact et testable ; bon SDK | Spécifications gratuites, engagement brevets RF ; lib3mf BSD-2 | Fabrication additive et packaging modernes | Pas de B-rep exacte ni features | Élevée pour additif uniquement |
| **AMF / ISO/ASTM 52915:2020** | XML/XSD géométrie additive, matériaux, couleurs, constellations | Stable, écosystème moindre que 3MF | Norme payante, XSD disponible | Sémantique additive | Pas de modèle mécanique source | Moyenne, verticale |
| **IGES 5.3** | Entités ASCII courbes, surfaces, solides, dessin | Lourd ; healing fréquent | Standard patrimonial, dernière version 1996 | Très large héritage | Ambiguïtés topologiques/tolérances, aucune intention | Faible ; import patrimonial |
| **DXF** | Sections/codes de groupe ASCII ou binaire, surtout 2D | Simple et répandu | Spécification Autodesk publiée, non ISO | Frontière plans/découpe | Versions/entités variables, faible sémantique | Faible comme cœur |
| **STL / OBJ / PLY** | Triangles, surfaces ou nuages de points | Très simples, efficaces selon volume | Standards de fait | Ubiquité, capture et fabrication | Perte d’unités/topologie/features/PMI selon format | Uniquement frontière terminale |

## Formats de scène et de visualisation

| Technologie | Objectif / architecture / modèle | Performance | Licence / maturité | Avantages | Limites mécaniques | Réutilisation |
|---|---|---|---|---|---|---|
| **glTF 2.0** | JSON + buffers ou GLB ; scènes, nœuds, triangles, PBR, textures, skins, animations et extensions | Très performant web/mobile/GPU grâce aux buffers contigus ; C | ISO/IEC 12113:2022 ; spécification Khronos CC BY 4.0 | Diffusion universelle et rendu temps réel | Aucune B-rep, contrainte, tolérance ou PMI mécanique général | Sortie visuelle prioritaire |
| **OpenUSD** | Stage composé de couches ; prims, attributs, relations, variants, references, payloads, instancing, temps ; Hydra | Très bon pour grandes scènes et chargement différé ; coût sensible au nombre de prims | AOUSD Core 1.0 ratifié 2025 ; code OpenUSD sous TOST 1.0 ; M/C DCC | Composition, variantes, collaboration, extensibilité | Pas de B-rep mécanique normative, GD&T ou régénération paramétrique | Composition/visualisation, pas autorité CAO |
| **IFC** | Schéma EXPRESS par couches, GUID, propriétés, quantités, géométrie, Model View Definitions | Mature BIM ; Part 21 verbeux, périmètre réduit par MVD | ISO 16739-1:2024 ; docs buildingSMART CC BY-ND | Gouvernance, GUID, MVD, certification éprouvés | Domaine AEC ; l’intention mécanique et l’historique ne sont pas le but | Méthodes réutilisables, données non substituables |
| **COLLADA** | XML pour actifs DCC, scènes, effets et animation | Mature mais plus lourd que glTF | ISO 17506:2022 ; Khronos | Échange DCC riche | Aucune sémantique mécanique source | Secondaire |
| **X3D** | Scène 3D réseau et interactive | Stable | ISO/IEC 19775-1:2023 | Publication/simulation interactive | Ni B-rep ni features | Secondaire |
| **PRC / U3D** | Formats binaires compacts incorporables dans PDF | Mature pour documentation | ISO 14739-1:2014 / ECMA-363 | Documentation 3D et archivage visuel | Pas d’édition paramétrique | Sortie documentaire |

## Conclusion sur les standards

STEP/AP242 et ses ressources sont le **socle sémantique à réutiliser**. QIF et AP238 complètent respectivement qualité et fabrication. JT, glTF et OpenUSD sont des **représentations dérivées**. IFC offre des modèles de gouvernance et de certification, mais pas le domaine mécanique. 3MF/AMF couvrent l’additif. IGES, DXF, STL, OBJ et PLY demeurent des frontières d’héritage ou de capture.

Le manque n’est pas un conteneur de plus. Il est l’implémentation cohérente, l’adaptation aux logiciels, la validation comportementale et la preuve de conformité.

[[PAGEBREAK]]

# Noyaux géométriques et solveurs

## Rôle exact d’un noyau

Un noyau géométrique fournit des objets mathématiques et topologiques, des opérateurs et des services : courbes/surfaces, B-rep, booléens, intersections, congés, coques, offsets, tessellation, healing, propriétés de masse et parfois modélisation convergente B-rep/maillage. Il est indispensable, mais insuffisant pour représenter l’intention de conception.

L’arbre de features, les configurations, les relations métier, les assemblages, le PMI et la gestion du cycle de vie sont en général des couches applicatives situées au-dessus du noyau. Une exportation Parasolid XT ou ACIS SAT peut être géométriquement excellente tout en perdant l’arbre SolidWorks, NX ou Inventor.

## Noyaux industriels propriétaires

| Technologie | Objectif / architecture / données | Performance publique | Avantages | Limites | Licence / maturité | Réutilisation et ouverture |
|---|---|---|---|---|---|---|
| **Parasolid v38** | API bas niveau ; B-rep exact/NURBS, manifold/non-manifold, cellules, maillages, treillis, Convergent Modeling ; persistance XT | Fonctions concurrentes et progrès ciblés ; aucun benchmark transversal reproductible | 900+ fonctions ; plus de 350 applications ; utilisé par NX et SolidWorks ; couverture très large | Ni arbre métier, ni PMI/MBD complet, ni structure produit ; identité durable à gérer au-dessus | Commercial Siemens, évaluation ; C | Excellent moteur sous licence ; XT ouvert à l’écosystème mais pas norme ISO ni intention universelle |
| **3D ACIS Modeler 2026** | Opérateurs B-rep exacts, direct/history côté hôte ; attributs et suivi ; SAT/SAB | Thread-safe et certaines API multithreadées ; pas de classement public | Plus de 30 ans ; booléens, fillets, offsets, direct modeling, validation/healing | Historique, PMI et produit restent côté application/3D InterOp ; formats propriétaires | Commercial Spatial/Dassault ; C | Fort sous licence ; standards via traducteurs, dépendance fournisseur |
| **CGM Modeler 2026** | B-rep exacte/tolérante ; opérations, reconnaissance/defeaturing, intégration CATIA/3D InterOp | Qualitative ; aucune comparaison indépendante | Fidélité CATIA, tolérances, préparation simulation/additif | Reconnaissance de trou/poche ≠ historique natif ; verrou Dassault | Commercial Spatial/Dassault ; C | Adaptateur CATIA et moteur sous licence ; faible ouverture du modèle natif |
| **ShapeManager** | Noyau Autodesk dérivé d’ACIS et intégré à Fusion/Inventor | Aucun benchmark SDK public | Longue industrialisation dans Autodesk | Aucun SDK autonome public identifié ; version et interface internes | Propriétaire, non licencié séparément ; C dans produits | Réutilisable seulement via API des produits hôtes |
| **PTC Granite** | Kernel/interoperabilité feature-based Creo ; rollback, IDs, attributs, paramètres, assemblages | Aucune mesure récente publique | Sémantique historique plus riche qu’un noyau pur ; associativité ATB | Documentation/conditions du SDK autonome surtout anciennes ; disponibilité 2026 à confirmer | Propriétaire PTC ; C dans Creo, statut SDK incertain | Pertinent comme adaptateur autorisé, pas comme fondation ouverte |
| **C3D Toolkit 2026** | Modeler, Solver, Converter, Vision, Mesh-to-B-Rep ; C++/wrappers ; B-rep, direct, tôlerie, assemblages | Calcul parallèle revendiqué, sans benchmark comparable | Suite large et modulaire, évaluation accessible | PMI/historique métier à construire ; écosystème plus petit ; diligence de continuité | Commercial annuel/royalties ; M | Alternative réutilisable sous licence ; natif `.c3d` propriétaire |

### Conclusion de performance

Aucun classement Parasolid/ACIS/CGM/C3D n’est scientifiquement défendable à partir des données publiques. Les fournisseurs publient des améliorations par opération, mais ni corpus identique, ni matériel, ni tolérance, ni taux d’échec comparables. Un appel d’offres devra imposer un benchmark interne : succès des opérations, écart géométrique, temps, mémoire, stabilité multithread et comportement sur cas dégénérés.

## Open CASCADE Technology

**Objectif.** OCCT est la principale bibliothèque open source de géométrie 3D exacte utilisée pour construire des applications CAO/FAO/IAO.

**Architecture et données.** Modules Foundation Classes, Modeling Data, Modeling Algorithms, Visualization, Data Exchange et Application Framework. Le modèle TopoDS sépare topologie et géométrie ; Geom/Geom2d portent courbes et surfaces analytiques/NURBS ; OCAF fournit document, labels, attributs, undo/redo et dépendances ; STEP/IGES/glTF/STL et autres traducteurs sont intégrés.

**Performance.** Noyau principalement CPU. Certaines opérations sont parallélisables ou disposent d’options parallèles ; le rendu exploite OpenGL. Les booléens, congés et healing complexes restent sensibles aux tolérances et cas dégénérés. Les versions récentes améliorent continuellement robustesse et parallélisme, mais aucun benchmark standard face aux noyaux commerciaux n’existe.

**Avantages.** Code source, large couverture, formats neutres, communauté ancienne, PythonOCC et intégration FreeCAD/CadQuery/build123d/SALOME. C’est le meilleur candidat open source pour un moteur de référence et pour auditer le résultat exact.

**Limites.** API C++ complexe ; documentation inégale ; pas d’arbre universel de features ; persistent naming historiquement délicat ; solveur d’esquisse et assemblages complets non fournis comme produit intégré ; robustesse de certaines opérations inférieure ou plus difficile à maîtriser que les noyaux commerciaux.

**Licence et maturité.** LGPL-2.1 avec exception OCCT permettant l’usage dans des applications propriétaires selon les termes de l’exception ; C/M selon fonction.

**Réutilisation.** Très élevée comme noyau open source de référence, générateur de B-rep, validateur et backend de prototypage. Compatible STEP. Il ne doit pas être confondu avec le standard sémantique lui-même.

## Autres noyaux et bibliothèques open source

| Technologie | Objectif et modèle | Performance | Licence / maturité | Atouts | Limites / réutilisation |
|---|---|---|---|---|---|
| **CGAL** | Algorithmes de géométrie computationnelle, polyèdres, maillages, arrangements, Nef polyhedra | Très optimisé selon package, parallélisme ponctuel | GPL/commercial, dépend du package ; M | Robustesse exacte/prédicats, immense boîte à outils | Pas de noyau paramétrique B-rep complet ni arbre ; attention copyleft |
| **Manifold** | Booléens robustes sur maillages 2-manifold | Rapide, parallélisme CPU/GPU selon intégration | Apache-2.0 ; E/M | Excellent pour CSG maillé et réparation | Pas de surfaces exactes, features ou PMI ; utile comme backend mesh |
| **BRL-CAD** | CSG, ray tracing et CAO historique défense | Mature pour CSG/ray tracing | LGPL/BSD selon composants ; C niche | Longévité, géométrie analytique/CSG, scripts | Interface et modèle éloignés de la CAO feature moderne ; PMI/STEP paramétrique limités |
| **libfive / f-rep** | Géométrie implicite par fonctions de distance, évaluation adaptative | Parallélisable ; efficace pour formes implicites | MPL-2.0 ; E | Robustesse des booléens implicites, code génératif | Conversion exacte vers B-rep et features industrielles non résolue |
| **OpenCSG** | Prévisualisation CSG via GPU/OpenGL | Rapide pour rendu | GPL-2+ ; M | Prévisualisation interactive | Ne calcule pas un solide exact exploitable en fabrication |
| **OpenVDB / NanoVDB** | Volumes clairsemés et grille GPU-friendly | Très efficace pour voxels/volumes | MPL-2.0 ; C VFX/E industrie | Lattices, champs, conversion et GPU | Pas un modèle B-rep ni historique |
| **OpenNURBS** | Lecture/écriture 3DM et classes NURBS de Rhino | Efficace pour persistance et géométrie | Licence openNURBS, permissive mais spécifique ; M | Accès 3DM, courbes/surfaces de qualité | N’est pas le noyau de modélisation Rhino complet ; pas d’historique général |
| **EGADS / OpenCSM / ESP** | Géométrie paramétrique et analyse multidisciplinaire NASA/EngSketchPad ; primitives, CSM et sensitivités | Conçu pour automatisation et adjoints ; corpus plus ciblé | LGPL-2.1 ; E/M recherche ingénierie | Paramètres, sensibilité et automatisation explicites | Couverture/écosystème inférieur aux CAO généralistes ; très pertinent comme antériorité et banc d’essai |

## Solveurs de contraintes

| Solution | Architecture et modèle | Performance / maturité | Licence | Réutilisation et limite |
|---|---|---|---|---|
| **D-Cubed 2D/3D DCM, PGM, CDM, AEM** | Composants indépendants : géométries, variables, équations, contraintes, degrés de liberté, contacts et mécanismes | Référence industrielle ; parallélisation ciblée et WebAssembly ; aucun benchmark transversal | Commercial Siemens | Très forte sous licence pour sketcher/assemblages ; ne fournit ni B-rep, ni features, ni PMI |
| **SolveSpace / libslvs** | Solveur géométrique paramétrique 2D/3D, contraintes algébriques, esquisses et assemblages simples | Interactif sur modèles modestes ; mature dans son périmètre | GPL-3.0 | Très utile pour prototype et recherche ; copyleft et couverture industrielle limitée |
| **FreeCAD Sketcher** | Solveur de contraintes intégré, basé sur GCS et DogLeg/algorithmes numériques | Interactif ; diagnostic et redondance ; dépend de la taille/condition du système | LGPL-2.1+ dans FreeCAD | Code et cas réels réutilisables ; extraction en composant autonome non triviale |

La sémantique de solveur reste un verrou : transférer les équations ne transfère pas nécessairement la sélection de branche, les priorités, les tolérances, les heuristiques, les messages de diagnostic ou le comportement en sous/sur-contrainte.

# SDK d’interopérabilité et de traduction

| SDK | Objectif / modèle | Performance | Avantages | Limites | Licence / maturité | Réutilisation |
|---|---|---|---|---|---|---|
| **Spatial 3D InterOp 2026** | Readers/writers natifs, modèle intermédiaire, healing ; structure, B-rep, tessellation, métadonnées, PMI | Progrès par version, sans benchmark commun | 30+ formats, AP242 PMI, liens ACIS/CGM | Ne recrée pas l’arbre natif ; décalage de versions | Commercial ; C | Très élevée pour import autorisé |
| **HOOPS Exchange 2026** | API C/C++/C#, modèle intermédiaire, ponts Parasolid/ACIS/OCCT | Incrémental selon lecteur, chiffres non comparables | Matrice explicite formats/B-rep/PMI, 30+ formats | Ni modeleur ni historique ; recompilations possibles | Commercial ; C | Très élevée pour ingestion/export |
| **CAD Exchanger SDK** | C++/C#/Java/JS/Python ; assemblages, B-rep, mesh, PMI, web | Parallélisme revendiqué | Accessibilité, langues, web | Pas de noyau complet ni historique ; cadence formats à contractualiser | Commercial ; M | Bonne pour PME/prototype industriel |
| **Datakit** | Bibliothèques de lecture/écriture CAO natives et neutres | Qualitative | Couverture large et intégration modulaire | Arbre de features généralement absent ; suivi de versions | Commercial ; M/C | Couche d’adaptation |
| **Open Design Alliance SDK** | Accès DWG/DGN et familles BIM/CAO selon offres | Mature sur formats ciblés | Écosystème et pérennité | Adhésion/licence ; pas de sémantique universelle | Commercial consortium ; C | Import patrimonial, pas cœur |
| **JT Open Toolkit** | API C++ JT, structure, LOD, PMI, XT embarqué | Très bon pour gros assemblages légers | JT ISO, diffusion industrielle | Modeleur Parasolid séparé, pas d’historique | Commercial/adhésion ; C | Sortie/entrée JT prioritaire |

Les contrats doivent préciser redistribution, cloud/SaaS, royalties, plateformes, correctifs, délai de prise en charge des versions natives, accès aux anciennes versions, continuité/escrow et droit de créer des corpus de test. Le reverse engineering de formats propriétaires ne constitue pas une stratégie industrielle robuste.

[[PAGEBREAK]]

# Logiciels de CAO commerciaux

## CATIA

**Objectifs.** CAO haut de gamme multidisciplinaire : mécanique, surfaces classe A, composites, systèmes, assemblages, MBD et PLM 3DEXPERIENCE.

**Architecture et données.** Noyau CGM, couches paramétriques/features, Knowledgeware, FT&A/PMI, objets CATPart/CATProduct et plateforme. CAA/automation permettent l’intégration.

**Performance.** Optimisations continues de grands assemblages et fonctions spécialisées ; aucun benchmark public comparable. La performance dépend fortement du workbench, de la plateforme et de la structure produit.

**Avantages.** Couverture surfacique et industrielle exceptionnelle, paramètres/règles, assemblages, composites, PMI/GD&T, intégration PLM.

**Limites.** Historique, relations et règles propriétaires ; CAA complexe ; coûts élevés ; la traduction neutre ne restitue pas universellement le comportement natif.

**Licence/maturité/réemploi.** Commercial fermé, C. À utiliser comme adaptateur, oracle de validation et cible native via API autorisée. Forte compatibilité AP242 en sortie/entrée, faible comme fondation ouverte.

## Siemens NX / Designcenter

**Objectifs.** CAO/FAO/IAO haut de gamme, MBD, fabrication et PLM.

**Architecture et données.** Parasolid, features historiques, synchronous modeling, contraintes D-Cubed, Teamcenter, NX Open. Pièces, expressions, assemblages, PMI, configurations et liens PLM.

**Performance.** Très bonne réputation industrielle et améliorations continues pour grandes structures ; mesures transversales absentes.

**Avantages.** Combinaison historique/direct, intégration CAO-FAO, PMI et JT/Parasolid natifs.

**Limites.** L’intention est une couche NX propriétaire au-dessus de Parasolid ; licences et runtime requis ; XT ne porte pas l’arbre NX.

**Licence/maturité/réemploi.** Commercial fermé, C. NX Open, STEP, JT et Parasolid sont d’excellents points d’intégration ; aucune ouverture de l’historique natif complet.

## PTC Creo

**Objectifs.** Conception mécanique paramétrique, top-down, MBD, grands assemblages, simulation et fabrication.

**Architecture et données.** Granite, arbre historique, relations, références externes, ATB, `.prt/.asm`, Object TOOLKIT.

**Performance.** Industrielle, sans benchmark transversal ; régénération dépendante de la qualité des références et de l’ordre des features.

**Avantages.** Paramétrique et référencement très matures, skeleton/top-down, GD&T/PMI, configurabilité.

**Limites.** Dépendances et comportement de régénération très spécifiques ; toolkit sous licence ; portabilité native limitée.

**Licence/maturité/réemploi.** Commercial fermé, C. API utile comme adaptateur/oracle ; Granite autonome à confirmer contractuellement.

## Dassault Systèmes SolidWorks

**Objectifs.** CAO mécanique généraliste : pièces, assemblages, tôlerie, configurations, mise en plan et MBD.

**Architecture et données.** Parasolid + FeatureManager, mates, configurations, SLDPRT/SLDASM, DimXpert/PMI et API COM/.NET/C++.

**Performance.** Optimisations du chargement lightweight/sélectif ; dépendance à la taille des assemblages et à la qualité de l’arbre ; aucun classement indépendant global.

**Avantages.** Large base installée, API riche, Parasolid natif, nombreux partenaires.

**Limites.** Arbre, configurations, mates et PMI propriétaires ; XT transporte surtout la géométrie.

**Licence/maturité/réemploi.** Commercial, C. Bon banc d’essai et cible native par API ; pas de fondation ouverte.

## Autodesk Fusion 360

**Objectifs.** Plateforme intégrée CAO/FAO/IAO/PCB/PDM, collaboration cloud et prototypage à production.

**Architecture et données.** ShapeManager, timeline paramétrique ou mode direct, T-splines, mesh, composants/occurrences, joints, services cloud, API Python/C++.

**Performance.** Interactive sur modèles courants ; Autodesk documente des ralentissements possibles avec longues timelines, nombreux joints et assemblages de l’ordre de 1 000 composants ou plus - seuil indicatif, non limite dure.

**Avantages.** Intégration large, accès API, historique de données précieux pour la recherche, flux cloud.

**Limites.** Le passage au mode direct peut supprimer la timeline ; dépendance abonnement/cloud ; ShapeManager non disponible seul ; PMI auteur encore en évolution en 2026.

**Licence/maturité/réemploi.** Propriétaire, M/C. API et Gallery Dataset très réutilisables ; timeline non portable par STEP.

## Rhino 3D et Grasshopper

**Objectifs.** Modélisation NURBS libre, surfaces et design computationnel ; Grasshopper ajoute un graphe visuel paramétrique.

**Architecture et données.** Noyau propriétaire Rhino, 3DM, objets NURBS/mesh/SubD, historique limité ; Grasshopper stocke composants, connexions, paramètres et plugins. RhinoCommon, C++ SDK, Python et openNURBS exposent une large surface.

**Performance.** Très efficace pour surfaces et automatisation interactive ; calcul Grasshopper dépend des plugins et du graphe ; grands graphes peuvent devenir séquentiels et lourds.

**Avantages.** Extensibilité exceptionnelle, 3DM documenté via openNURBS, communauté algorithmique, interopérabilité design.

**Limites.** Ce n’est pas une CAO mécanique historique/MBD complète ; Grasshopper dépend de composants/plugins et ne garantit pas la reproductibilité multi-version ; PMI/GD&T et assemblages industriels limités.

**Licence/maturité/réemploi.** Rhino commercial mature ; openNURBS sous licence spécifique gratuite ; Grasshopper inclus. Très utile comme environnement de recherche/adaptateur, non comme cœur mécanique autoritatif.

## Onshape et FeatureScript

**Objectifs.** CAO paramétrique cloud-native et langage intégré pour créer des features.

**Architecture et données.** Documents versionnés, Part Studios multi-corps, assemblages, configurations, références robustes ; FeatureScript est un langage fonctionnel/impératif typé pour opérations 3D, requêtes de topologie, unités et features.

**Performance.** Calcul serveur, collaboration et versionnement très efficaces ; dépend du service, des limites document et des opérations ; absence de benchmark public multi-CAO.

**Avantages.** Code de feature réellement intégré à l’historique ; unités/types 3D ; requêtes topologiques plus robustes que des index bruts ; versionnement et API REST modernes. Le standard library FeatureScript est publié et réutilisable sous MIT.

**Limites.** Le runtime géométrique et la plateforme restent propriétaires et hébergés ; un programme FeatureScript n’est pas exécutable indépendamment ; PMI/assemblage et accès bas niveau ne couvrent pas tout le modèle Onshape.

**Licence/maturité/réemploi.** Service commercial M/C ; langage et bibliothèque ouverts à différents degrés, mais exécution liée à Onshape. Excellente source d’idées et backend possible ; faible comme standard autonome.

## Blender

**Objectifs.** Création numérique, maillage, animation, rendu, VFX, Geometry Nodes et scripting Python.

**Architecture et données.** Meshes, courbes, surfaces, objets/scènes, modificateurs non destructifs, nodes, depsgraph, fichiers `.blend`; Cycles/Eevee et GPU.

**Performance.** Excellente visualisation, maillage, rendu GPU et automatisation ; les opérations exactes et les contraintes mécaniques ne sont pas son cœur.

**Avantages.** GPL, communauté massive, import/export, Geometry Nodes, Python, rendu et génération de données synthétiques.

**Limites.** Maillage dominant ; aucune B-rep exacte industrielle ni arbre de features/PMI/GD&T universel ; booléens maillés sensibles selon cas.

**Licence/maturité/réemploi.** GPL-2+, C dans DCC. Très réutilisable pour rendu, annotation, synthèse de données et visualisation ; pas comme autorité géométrique mécanique.

## Solutions de reverse engineering industriel

| Produit | Objectif / architecture / données | Performance et maturité | Avantages | Limites | Licence / réemploi |
|---|---|---|---|---|---|
| **Geomagic Design X** | Scan/mesh vers surfaces et modèles feature-based ; extraction automatique/guidée, historique et LiveTransfer vers plusieurs CAO | Produit de référence, interactif sur gros scans ; mesures indépendantes rares | Primitives, sections, surfaces exactes, comparaison déviation, transfert natif partiel | Intervention experte fréquente ; historique complexe non universel ; dépendance cible | Commercial ; C. Excellent benchmark concurrent et outil d’annotation, pas standard |
| **PolyWorks Modeler** | Extraction de courbes, surfaces, esquisses paramétriques et features prismatiques depuis modèles polygonaux | C dans métrologie/reverse engineering | Flux guidé, entités optimales comme point de départ CAO | La reconstruction finale et l’intention restent souvent manuelles dans la CAO | Commercial ; C. Réutilisable opérationnellement, API à examiner |
| **ZEISS Reverse Engineering** | Mesh/points vers géométries standard, surfaces libres, booléens, loft/sweep, STEP/IGES/SAT | C en métrologie ; précision forte revendiquée | Intégration inspection, analyses nominal/réel, surfaces précises | Modèle source paramétrique complet non garanti ; expertise nécessaire | Commercial ; C. Outil de comparaison et capture |
| **nTop / nTop Core** | Modélisation implicite paramétrique, lattices, champs et calcul sans maillage intermédiaire | Très performant sur géométries complexes ; chiffres fournisseur ; M/C additif | Robustesse des opérations implicites, complexité, automatisation | Pas de B-rep/history mécanique classique ; format et kernel propriétaires ; PMI/assemblage limités | Commercial. Core embarquable sous accord ; complément implicite, pas substitut général |

Ces produits démontrent que le scan-to-CAD manufacturable est possible, mais ils confirment aussi la distinction **as-built** / **design intent** : ajuster une surface au nuage ne révèle pas automatiquement la cote nominale, le choix d’un motif, la classe de tolérance ou la logique de variante.

[[PAGEBREAK]]

# CAO open source et programmation géométrique

## FreeCAD 1.1

**Objectif.** CAO paramétrique mécanique généraliste, libre et extensible.

**Architecture et données.** C++/Python ; séparation App/Gui ; ateliers Part, Part Design, Sketcher, Assembly, TechDraw et autres ; OCCT pour B-rep ; graphe d’objets dans un document ; `.FCStd` est un conteneur ZIP avec XML paramétrique et caches BREP. OCAF/XDE sont exploités à différents niveaux.

**Performance.** Pas de benchmark transversal. Les temps de recompute dépendent du graphe et des opérations OCCT ; grandes pièces et features fragiles peuvent entraîner une propagation coûteuse. Le rendu est accéléré, la construction exacte reste surtout CPU.

**Avantages.** Pile ouverte la plus complète ; scripting Python ; formats neutres ; architecture de workbenches ; sketcher, assemblage, mise en plan ; accès à des cas réels et à un moteur de recompute.

**Limites.** Cohérence et qualité variables selon ateliers ; API et compatibilité de documents évolutives ; dépendance aux comportements OCCT ; PMI sémantique et round-trip AP242 incomplets ; l’écosystème d’assemblage a longtemps été fragmenté.

**Persistent naming.** Les versions récentes atténuent fortement le problème par des mécanismes issus de LinkStage3 et par des références plus robustes. La documentation FreeCAD précise néanmoins qu’il n’est pas formellement résolu. Une référence qui survit à un cas nominal ne constitue pas une garantie multi-noyaux.

**Licence/maturité/réemploi.** LGPL-2.1-or-later, M. Meilleur banc d’intégration ouvert et excellente application de référence. `.FCStd` peut inspirer persistance et tests, mais reste un modèle FreeCAD, non un standard inter-éditeurs.

## CadQuery 2.8

**Objectif.** Génération paramétrique textuelle en Python, particulièrement efficace pour familles de pièces, automatisation et tests.

**Architecture et données.** API fluide `Workplane`, contexte/piles, sketches, sélecteurs, tags, assemblages et contraintes ; OCCT via OCP. L’intention réside dans le programme Python, le résultat dans des objets B-rep.

**Performance.** Généralement suffisante pour pièces unitaires et automatisation ; coût Python et OCCT ; les fusions d’assemblages peuvent être chères et changer la topologie. Aucun benchmark industriel standard.

**Avantages.** Syntaxe concise, tests unitaires faciles, écosystème Python, export STEP, Apache-2.0.

**Limites.** Python arbitraire complique sandboxing, déterminisme et sérialisation ; selectors/tags réduisent sans éliminer la fragilité topologique ; pas de PMI/GD&T complet ; aucun format neutre de l’historique.

**Maturité/réemploi.** M, Apache-2.0. Excellent frontend de prototypage et cible pour les travaux IA de génération de code. Il ne doit pas être confondu avec une représentation canonique.

## build123d 0.11

**Objectif.** API Python moderne pour B-rep, avec style algébrique et builders.

**Architecture.** Classes 1D/2D/3D, opérations OCCT, assemblages et joints, composition naturelle de Python.

**Performance.** Comparable aux appels OCCT sous-jacents ; la documentation reconnaît que certaines opérations 3D peuvent échouer ou être lentes.

**Avantages.** API explicite, Apache-2.0, typage Python, très adaptée à la génération et aux tests.

**Limites.** Projet plus jeune, solveur de contraintes limité, persistent naming non universel, absence de PMI complet.

**Réemploi.** Très bon banc de R&D et DSL existant à ne pas réinventer ; pas un standard d’échange.

## OpenSCAD

**Objectif.** Modélisation CSG déclarative et reproductible par script, principalement pour fabrication personnelle et pièces géométriques.

**Architecture et données.** Langage spécialisé, arbres CSG, primitives et transformations ; CGAL historiquement pour évaluation, Manifold dans les versions/snapshots récents ; OpenCSG/OpenGL pour prévisualisation. Le script constitue l’historique.

**Performance.** Le moteur Manifold apporte une accélération importante annoncée, sans protocole public comparable aux noyaux B-rep. La tessellation et les booléens mesh dominent.

**Avantages.** Simplicité, reproductibilité, code lisible, communauté large, paramétrage facile.

**Limites.** Pas de B-rep analytique exacte, sketcher contraint, assemblage produit, PMI/GD&T ou références persistantes de faces ; version stable historique ancienne ; géométries libres complexes difficiles.

**Licence/maturité/réemploi.** GPL-2-or-later, M. Référence utile pour CSG et génération programmatique ; copyleft à considérer ; insuffisant comme cœur MBD.

## SALOME SHAPER

**Objectif.** Modélisation paramétrique intégrée aux flux CAE SALOME.

**Architecture.** C++/Python, plugins ModelAPI, Feature/Result/Attribute, transactions, OCCT, sketcher et persistance `.shaper` de la séquence.

**Performance.** Adaptée aux flux ingénierie, sans comparaison publique ; même profil de robustesse OCCT.

**Avantages.** Ouvert, scriptable, bonne continuité vers simulation et maillage.

**Limites.** Écosystème de conception mécanique, assemblages et MBD moins riches que les grands logiciels ; export neutre perd l’historique.

**Licence/maturité/réemploi.** LGPL-2.1, M dans CAE. Très utile pour étudier plugins, transactions et couplage CAO-calcul.

## OpenCSM / ESP / EGADS

**Objectif.** Paramétrage, sensitivités géométriques et optimisation multidisciplinaire, notamment aérospatiale.

**Architecture.** OpenCSM utilise un script ASCII et une pile de corps/features ; EGADS abstrait OCCT ; EGADSlite évalue de façon légère/thread-safe ; ESP fournit client navigateur et serveur.

**Performance.** Conception HPC/threadable et sensitivités, sans benchmark général CAO.

**Avantages.** Historique explicite, automatisation, différentiation/sensitivités, licence ouverte, forte pertinence scientifique.

**Limites.** Vocabulaire et communauté plus spécialisés ; pas de produit MBD, PMI ou assemblage mécanique complet.

**Licence/maturité/réemploi.** LGPL-2.1, M en recherche/industrie spécialisée. Antériorité importante et brique possible pour optimisation.

## BRL-CAD

**Objectif.** CSG, base géométrique hiérarchique, lancer de rayons et analyses, historiquement pour la défense.

**Architecture.** Primitives, combinaisons, régions, base `.g`, BoT, capacités NURBS/B-rep et convertisseurs.

**Performance.** Très mature pour grands arbres CSG et ray tracing ; pas de benchmark face à la CAO feature-based.

**Avantages.** Plus de quarante ans de développement, intention constructive CSG, outils d’analyse.

**Limites.** Interface et modèle spécialisés ; B-rep/tessellation encore des axes de développement ; pas de sketcher, mates ou PMI sémantique général.

**Licence/maturité/réemploi.** Majoritairement LGPL avec composants sous licences variées ; C dans sa niche. Utile pour CSG/ray tracing, non comme pile universelle.

## Synthèse des environnements programmables

| Environnement | Porte l’intention ? | Géométrie exacte | Contraintes | Assemblages | PMI | Ouvert/exécutable hors fournisseur | Verdict |
|---|---|---|---|---|---|---|---|
| FreeCAD | Oui, graphe/features | Oui, OCCT | Oui | Oui, en maturation | Partiel | Oui | Meilleur banc ouvert complet |
| CadQuery | Oui, code Python | Oui, OCCT | Partiel | Oui, basique | Non | Oui | Excellent pour automatisation/IA |
| build123d | Oui, code Python | Oui, OCCT | Limité | Joints | Non | Oui | API moderne de R&D |
| OpenSCAD | Oui, arbre CSG | Non, résultat tessellé/CSG | Non | Non | Non | Oui | Référence de simplicité, couverture faible |
| FeatureScript | Oui, features natives | Oui, runtime Onshape | Oui | Via Onshape | Partiel/plateforme | **Non**, runtime cloud | Référence sémantique, dépendance forte |
| Grasshopper | Oui, graphe | NURBS via Rhino | Plugins | Faible | Faible | Runtime Rhino requis | Référence UX computationnelle |
| OpenCSM | Oui, script/features | Oui via EGADS/OCCT | Paramètres/sensitivités | Faible | Non | Oui | Très pertinent MDAO |
| Geometry Nodes | Oui, graphe | Maillage/volume | Non mécanique | Scène | Non | Oui, GPL | Données synthétiques/visuel |

> **Conclusion.** Il existe déjà de nombreux langages, API et graphes de modélisation. Le besoin non satisfait n’est pas « pouvoir programmer une forme » ; c’est rendre l’intention mécanique portable, associée à une géométrie exacte et au PMI, et prouver son comportement après édition.

[[PAGEBREAK]]

# Intelligence artificielle pour la CAO

## Taxonomie des approches

Les travaux récents se répartissent en cinq familles :

- compréhension de B-rep et reconnaissance de features ;
- génération directe de B-rep ;
- génération/reconstruction de séquences sketch-extrude ;
- génération de programmes CAO exécutables ;
- reconstruction de surfaces ou implicites depuis points/images, sans historique.

Ces familles produisent des objets différents. Une B-rep générée directement est précise et éditable par opérations directes, mais ne possède pas nécessairement un historique de conception. Un programme CadQuery est interprétable et modifiable, mais peut seulement couvrir les opérateurs appris. Un neural SDF ou un mesh est excellent pour la forme, faible pour la sémantique mécanique.

## Jeux de données fondateurs

| Jeu / projet | Contenu et modèle | Taille publique | Avantages | Limites pour l’objectif |
|---|---|---|---|---|
| **ABC Dataset** | Modèles CAD avec courbes/surfaces paramétriques et exports STEP/Parasolid/mesh | 1 million de modèles | Échelle et géométrie exacte ; référence apprentissage B-rep | Pas d’historique utilisateur ni PMI/assemblages ; provenance/licences des formes à gérer |
| **Fusion 360 Gallery** | Séquences humaines dans un vocabulaire simplifié sketch + extrude ; environnement Gym | 8 625 séquences | Historique réel, actions, apprentissage séquentiel | Petit et limité à sketch/extrude ; pas de production complexe |
| **DeepCAD** | Séquences tokenisées de sketches/extrusions | 178 238 séquences | Grande base procédurale standardisée | Vocabulaire très limité, quantification, pièces simples |
| **SketchGraphs** | Graphes d’esquisses et contraintes | 15 millions d’esquisses | Échelle exceptionnelle pour sketcher et solveur | 2D seulement ; biais du logiciel source ; pas de solide/PMI |
| **Fusion 360 Segmentation / BRepNet** | B-rep avec faces annotées par opération créatrice | Plus de 35 000 modèles | Apprentissage direct sur topologie et provenance | Annotations de face ≠ historique complet ; domaine Fusion |
| **CADFS** | Programmes FeatureScript réels, 15 opérations, entrées multimodales | Environ 450 000 modèles | Couverture bien supérieure à sketch/extrude, syntaxe exécutable | Runtime Onshape propriétaire ; opérations encore loin de la CAO complète |
| **BenchCAD** | Programmes CadQuery vérifiés, familles industrielles et standards | 17 900 programmes, 106 familles, 49 % ancrées dans des standards | Évaluation exécutable et hors distribution par famille | Taille encore modeste ; CadQuery/OCCT ; publié en 2026, recul faible |

Le déficit de données est qualitatif : peu de corpus publics contiennent simultanément historique natif, contraintes, assemblages, PMI, tolérances, matériaux, configurations, scans/images associés, modifications et droits de réutilisation pour entraînement commercial.

## Travaux sur esquisses et séquences

| Travail | Entrée → sortie | Architecture / données | Résultat et performance | Limite décisive |
|---|---|---|---|---|
| **DeepCAD, ICCV 2021** | latent → séquence sketch/extrude | Transformer autoencodeur sur 178k séquences | Génération cohérente et interpolation ; code MIT | Uniquement esquisse/extrusion ; quantification ; aucune tolérance/PMI |
| **Vitruvion, 2021** | contexte/partiel → esquisse contrainte | Modèle autoregressif primitives + contraintes | Génère géométrie et contraintes ; utile autocomplete | Ne résout pas le solide 3D ou l’intention métier |
| **SketchGraphs, 2020** | esquisse → graphe/contraintes | GNN et corpus 15M | Base majeure pour inférence de contraintes | Domaine 2D, ambiguïtés et incohérences humaines |
| **SECAD-Net, CVPR 2023** | points/forme → opérations sketch-extrude | Auto-supervision et décomposition | Réduit besoin d’historique annoté | Sous-ensemble prismatico-extrudé ; erreurs cumulatives |
| **SfmCAD, CVPR 2024** | points → features sketch-based | Apprentissage non supervisé | Inférence d’opérations de modélisation | Couverture limitée, pas de preuve industrielle |
| **Draw Step by Step, CVPR 2024** | point cloud → séquence de construction | Reconstruction progressive | Améliore séquences et cohérence | Même dépendance aux vocabulaires restreints |
| **CAD-SIGNet, CVPR 2024** | point cloud → séquence CAD | Transformer avec décodage sketch par couches | État de l’art sur benchmarks de séquences | Pièces et opérations contrôlées ; exactitude fonctionnelle non testée |
| **TransCAD, ECCV 2024** | points → séquence hiérarchique | Transformer hiérarchique | Mesure mAP de séquence et qualité de reconstruction | Les métriques de tokens/forme ne garantissent pas régénération industrielle |

## Reconstruction géométrique et B-rep

| Travail | Approche | Forces | Limites |
|---|---|---|---|
| **BRepNet, 2021** | Message passing sur coedges/faces/arêtes B-rep | Compréhension native sans conversion mesh ; segmentation de features | Analyse, pas génération complète ; dépend des B-rep valides |
| **UV-Net, 2021** | Graphes B-rep + grilles UV échantillonnées | Combine topologie et géométrie locale ; très influent | Échantillonnage approximatif, couverture des attributs limitée ; famille brevetée |
| **SolidGen, 2022** | Transformer autoregressif vertices-edges-faces | Première synthèse directe B-rep structurée | Topologies et surfaces simples ; pas d’historique ni garantie de validité générale |
| **Point2CAD, CVPR 2024** | Segmentation neurale + ajustement analytique + topologie | Bon compromis exactitude/interprétabilité ; surfaces et arêtes explicites | Produit B-rep, non feature tree ; données idéalisées ; tolérances/PMI absents |
| **NeurCADRecon** | Neural SDF préservant arêtes et coins | Surface fidèle depuis points, facilite patching | Sortie implicite/mesh ; passage à B-rep paramétrique reste une étape |
| **DTGBrepGen, CVPR 2025** | Découplage topologie/géométrie pour génération B-rep | Meilleure gestion de la structure | Validité, complexité libre, historique et dimensions exactes non garantis |
| **HiFi-BRep, CVPR 2026** | Représentation latente haute fidélité | Robustesse et qualité de B-rep en progrès | Publication récente ; pas de validation MBD/édition |
| **BrepVGAE, CVPR 2026** | Autoencodeur variationnel de graphes B-rep | Représentation unifiée topo-géométrique | Latent génératif ≠ intention ou programme |
| **BrepGaussian, CVPR 2026** | Multi-vues + Gaussian splatting → B-rep complète | Évite supervision par nuage de points | Entrées visuelles ambiguës ; historique/tolérances absents |
| **FoV-Net, CVPR 2026** | Ray casting invariant à la rotation sur B-rep | Apprentissage de descripteurs robustes | Compréhension, non reconstruction paramétrique complète |

## Génération de programmes et systèmes multimodaux

| Travail | Entrée → sortie | Architecture / performance annoncée | Atouts | Limites |
|---|---|---|---|---|
| **CAD-Recode, ICCV 2025** | point cloud → Python CadQuery | Qwen2-1.5B + projecteur points, entraînement sur 1M programmes synthétiques ; Chamfer moyen annoncé environ 10× meilleur que l’état de l’art ciblé | Programme exécutable, modifiable, syntaxe existante | Familles sketch/extrude dominantes ; données synthétiques ; Chamfer ne teste pas intention/PMI |
| **CADCrafter, CVPR 2025** | image non contrainte → séquence CAD | Données synthétiques et modèle génératif | Franchit l’entrée image unique | Ambiguïté 3D intrinsèque, dimensions non observables, faible garantie OOD |
| **Cadrille, 2025-2026** | points/images/texte → scripts Python | SFT procédural + renforcement ; multimodal | Unifie entrées et code exécutable ; multi-vues améliorent IoU | Domaine synthétique, métriques de forme, pas de garanties industrielles |
| **CADFS, CVPR 2026** | multimodal → FeatureScript | Corpus 450k, 15 opérations | Plus grande diversité de features et données réelles | Runtime propriétaire, seulement 15 opérations, publication très récente |
| **Pointer-CAD, CVPR 2026** | points → séquence avec sélection de faces/arêtes | Pointeurs sur B-rep intermédiaire | Gère références, congés/chanfreins et réduit erreurs de quantification | Dépend du backend et de la validité intermédiaire ; couverture encore bornée |
| **Pointer-CAD v2, juin 2026** | points → plan + construction en valeurs continues | Échelle métrique explicite et paramètres continus | Attaque directement quantification et dimensions | Prépublication très récente ; tolérances/PMI/assemblages non démontrés |
| **CAD-Assistant, ICCV 2025** | vision/langage + outils CAO → tâches | VLLM outillé | Montre l’intérêt d’un agent qui appelle un système exact | Fiabilité dépend des outils et de la boucle de vérification ; pas modèle neutre |
| **CAD-Refiner, CVPR 2026** | modèle → éditions itératives | Boucle de raffinement unifiée | L’itération réduit certaines erreurs | Stabilité et convergence non garanties sur modèles arbitraires |
| **FutureCAD, 2026** | texte → CadQuery avec grounding B-rep | LLM + transformeur de liaison vers faces/arêtes | Relie langage, code et références topologiques | Prépublication ; dépend CadQuery/OCCT ; pas PMI ou tolérances certifiées |
| **CADReasoner, 2026** | demande → programme édité itérativement | Raisonnement/validation en boucle | Meilleure correction d’erreurs que génération one-shot | Coût, non-déterminisme, couverture outils et sécurité du code |
| **CADFit, 2026** | mesh → programme éditable | Opérations extrusion/révolution/fillet/chamfer + optimisation IoU | Combine recherche symbolique et optimisation | Vocabulaire encore restreint ; IoU ne prouve pas intention |

## Dessins 2D vers CAO

Les travaux consacrés aux dessins restent moins nombreux que point-cloud-to-CAD. PICASSO/WACV 2025 reconstruit des esquisses paramétriques 2D depuis images par supervision de rendu. CAD2PROGRAM et Drawing2CAD explorent le passage de dessins vectoriels ou techniques à des programmes/séquences 3D. La thèse de C. Zhang (2025, déposée 2026) traite spécifiquement la reconstruction de modèles paramétriques 3D depuis dessins 2D.

Le problème est structurellement sous-déterminé : vues manquantes, conventions implicites, traits cachés, sections, détails, échelles, tolérances générales, symétries et normes de dessin. Une dimension absente d’un plan ne peut pas être « reconstruite sans ambiguïté » par un modèle probabiliste ; elle doit être demandée, héritée d’une règle explicite ou marquée comme hypothèse.

## Projets industriels récents

| Projet/produit | Positionnement | État public et limite |
|---|---|---|
| **Autodesk Project Bernini / neural CAD** | Modèle génératif 3D depuis texte, images, sketches, voxels et points ; recherche vers formes professionnelles éditables | Preuve de concept puis démonstrations 2025 ; détails de modèle/données/format de sortie et garanties industrielles non publics |
| **Siemens Designcenter/NX Copilot** | Interface en langage naturel, assistance documentation et automatisation ; Industrial Foundation Model pour reconnaissance de features/fabrication | Produit croissant, mais le Copilot public 2025 était d’abord assistance et bonnes pratiques ; aucune portabilité neutre de l’historique annoncée |
| **CATIA AI/Knowledge Assistance** | Contraintes, assistance et ingénierie générative intégrées 3DEXPERIENCE | Fort potentiel car données et kernel natifs ; documentation technique et interopérabilité ouverte limitées |
| **Creo 13 AI guidance / generative design** | Guidance de conception et optimisation intégrées | Fonctionnalités produit, non système ouvert de reconstruction arbitraire |
| **Onshape AI** | Assistance sur plateforme cloud et features | Avantage de données versionnées et FeatureScript ; dépendance complète au service |

## Ce que prouvent réellement les métriques

| Métrique | Ce qu’elle mesure | Ce qu’elle ne prouve pas |
|---|---|---|
| Chamfer distance | Proximité moyenne de points/surfaces échantillonnés | Dimensions critiques, continuité exacte, topology, PMI, feature tree |
| IoU volumique | Recouvrement de volumes | Petits trous/chanfreins, tolérances, état de surface, comportement d’édition |
| Validité B-rep | Cohérence topologique/géométrique selon un validateur | Intention, manufacturabilité, régénération multi-noyaux |
| Exact match de tokens | Séquence identique au corpus | Existence d’autres historiques équivalents ou meilleure intention |
| Succès d’exécution | Programme accepté par un backend/version | Stabilité à d’autres paramètres, versions ou noyaux |
| Jugement visuel | Plausibilité perçue | Toute exigence métrologique ou fonctionnelle |

BenchCAD 2026 fournit le signal le plus pertinent : plus de dix modèles avancés reconstruisent souvent la forme grossière, mais échouent encore à produire des programmes paramétriques fidèles, surtout sur familles inédites. Fine-tuning et renforcement améliorent l’in-distribution sans abolir le problème OOD.

## Verdict IA

L’IA est prête pour : segmentation, reconnaissance de primitives/features, proposition de sketches, génération de candidats de programme, classement d’hypothèses, extraction de PMI, détection d’incohérences et assistance interactive.

Elle n’est pas prête à être seule autorité pour : dimensions non observées, intention unique, tolérances fonctionnelles, pièces arbitraires, assemblages complexes, conformité réglementaire ou régénération multi-CAO garantie.

Le principe industriel sûr est : **l’IA propose ; le solveur, le noyau et les règles vérifient ; l’humain tranche les ambiguïtés matérielles**.

[[PAGEBREAK]]

# Compilateurs, runtimes IA et bibliothèques GPU

## LLVM et MLIR

**LLVM** fournit une infrastructure de compilation mature : représentation intermédiaire SSA, optimisations, génération de code, objets et JIT. **MLIR** étend cette idée à plusieurs niveaux d’abstraction grâce à des dialectes extensibles, des opérations typées, des passes, la conversion entre dialectes et des dialectes GPU/NVGPU.

**Performance.** Ce sont des infrastructures critiques de production, mais leurs performances dépendent du frontend, des passes et de la cible. Elles ne fournissent aucune opération géométrique par défaut.

**Avantages.** Typage, vérification, transformations déclaratives, versionnement de dialectes, abaissement progressif et génération CPU/GPU. MLIR est pertinent pour représenter plusieurs niveaux internes - intention, opérations normalisées, appels de noyau et kernels GPU - sans imposer que l’IR interne devienne le format public.

**Limites.** Concevoir un dialecte ne résout ni la sémantique des features, ni les tolérances, ni le persistent naming. La stabilité d’une IR d’implémentation ne remplace pas une norme d’échange.

**Licence/maturité.** Apache-2.0 avec LLVM exception ; C. Réutilisation très élevée pour compilateur/runtime interne ; compatibilité ouverte élevée.

## OpenXLA, StableHLO, ONNX, IREE et TVM

| Technologie | Objectif / architecture / données | Performance | Licence / maturité | Réutilisation | Limite pour la CAO |
|---|---|---|---|---|---|
| **OpenXLA / StableHLO** | Opérations tenseurs versionnées et portables, compilation XLA | Excellente sur accélérateurs supportés, modèle-dépendant | Apache-2.0 ; M/C IA | Échange d’IR de calcul, entraînement/inférence | Aucune sémantique de B-rep/features ; seulement calcul numérique |
| **ONNX** | Graphe de modèles IA, opérateurs, tensors, versioning | Portabilité élevée ; performance via runtimes | Apache-2.0 ; C | Format de modèles et interchange ML | Ne représente ni données CAO riches ni pipeline de construction |
| **ONNX Runtime** | Exécution optimisée multi-backends CPU/GPU/NPU | C, providers CUDA/TensorRT/DirectML/etc. | MIT ; C | Déploiement des modèles de perception/génération | Les opérateurs géométriques propriétaires exigent extensions |
| **IREE** | Compilation MLIR de modèles vers runtimes légers et multiples accélérateurs | Bon potentiel embarqué/serveur, benchmark à définir | Apache-2.0 ; E/M | Déploiement compilé et déterministe | Pas un noyau géométrique |
| **Apache TVM / TIRx** | Compilation et génération de kernels tenseurs ; DSL kernels récent | Très performant quand autotuné | Apache-2.0 ; M, TIRx E en 2026 | Optimiser kernels IA/GPU spécifiques | Coût d’intégration ; aucune sémantique mécanique |
| **Triton** | Langage/compilateur Python pour kernels GPU par blocs | Hautes performances sur kernels adaptés | MIT ; M | Kernels de sampling, distances, raster, attention | Flux irréguliers/topologiques difficiles ; pas de B-rep |

Ces technologies doivent être utilisées pour exécuter l’IA et les calculs denses, non comme substituts à un modèle sémantique mécanique.

## CUDA et bibliothèques GPU 3D

| Technologie | Objectif / modèle | Performance | Licence / maturité | Avantages | Limites / réemploi |
|---|---|---|---|---|---|
| **CUDA** | Programmation GPU NVIDIA, kernels, mémoire, graphes, bibliothèques | Référence industrielle GPU ; dépend du matériel et kernel | Toolkit propriétaire avec composants variés ; C | Écosystème complet et haut débit | Dépendance NVIDIA ; branchements/allocations irrégulières pénalisent les algorithmes B-rep |
| **NVIDIA Warp** | Kernels Python JIT vers CPU/GPU, différentiation, géométrie/simulation | Très bon pour calculs parallèles structurés | Apache-2.0 depuis 1.6.2 ; M/E | Python, autograd, primitives géométriques, prototypage rapide | Pas de noyau B-rep exact ; compilation et modèles de données spécifiques |
| **PyTorch3D** | Meshes, points, rendus différentiables et CUDA ops | Efficace pour entraînement 3D | BSD-3-Clause ; M recherche | Écosystème PyTorch, losses et rendu | Pas de surfaces exactes, features ou PMI |
| **NVIDIA Kaolin** | Représentations 3D, conversions, différentiable rendering, USD | Efficace GPU ; 0.18 en 2026 | Apache-2.0 pour cœur ; M recherche | Dataset/visualisation 3D, points/meshes/splats | Pas de B-rep/history ; vérifier licences de sous-composants |
| **nvdiffrast** | Rasterisation différentiable CUDA | Très rapide pour raster différentiable | NVIDIA Source Code License ; M recherche | Supervision par rendu | Licence non permissive standard ; pas de géométrie exacte |
| **OptiX** | Ray tracing programmable RTX | Très haute performance sur rayons | SDK propriétaire, usage commercial selon EULA ; C | Sélection, visibilité, simulation optique/rayons | NVIDIA seulement, aucune construction paramétrique |
| **OpenVDB / NanoVDB** | Volumes clairsemés ; NanoVDB compact/GPU-friendly | Très performant pour champs volumétriques | MPL-2.0 ; C VFX, M industrie | SDF, voxels, lattices, traitement scan | Conversion exacte vers B-rep et intention absentes |
| **Dyndrite Engine** | Kernel géométrique hybride GPU, fabrication additive et grands meshes/CAD | Revendique échelles milliard de facettes ; chiffres fournisseur | Propriétaire ; M spécialisé | Préparation additive, gros volumes, Python/C++ | Pas de preuve publique de noyau B-rep paramétrique général ; verrou fournisseur |
| **SMLib** | Ancien noyau NVIDIA NURBS/B-rep, non-manifold | Documentation historique | Propriétaire ; legacy, nouvelles licences suspendues | Preuve qu’un kernel riche peut exploiter écosystème NVIDIA | Non disponible comme choix de produit durable |

## État de l’art GPU pour la géométrie exacte

La thèse *Parallel GPU Algorithms for Mechanical CAD* d’A. Krishnamurthy (2010) accélère évaluation de splines, intersections surface-surface et distances minimales. Des travaux ultérieurs évaluent directement NURBS sur GPU, utilisent CUDA/Tensor Cores pour rendu NURBS, et une approche matricielle 2025 rapporte près de deux ordres de grandeur sur certaines opérations B-spline telles que inversion/projection.

Ces résultats sont importants mais locaux. Un noyau industriel doit aussi gérer : allocations topologiques dynamiques, branchements, exactitude adaptative, tolérances par entité, cas tangents/dégénérés, suivi d’identité, rollback et diagnostics. Ces propriétés réduisent le parallélisme régulier et rendent la reproductibilité CPU/GPU délicate.

> **Verdict GPU.** Accélérer perception, rendu, tessellation, sampling, distances, recherche de voisins, comparaison de formes, génération de données et apprentissage est immédiatement rentable. Réécrire d’emblée booléens, fillets et solveur B-rep général sur GPU serait un programme de recherche autonome à très haut risque.

[[PAGEBREAK]]

# Publications académiques et thèses structurantes

## Fondements de la représentation et de l’interopérabilité

| Référence | Apport | Conséquence pour le projet |
|---|---|---|
| Requicha, *Representations for Rigid Solids*, 1980 | Cadre des représentations solides, validité, complétude et ambiguïté | Une syntaxe lisible ne suffit pas ; la sémantique d’un solide doit être rigoureuse |
| Mäntylä, *An Introduction to Solid Modeling*, 1988 | Topologie, Euler, B-rep et opérations | Base théorique des noyaux actuels, mais pas de l’intention métier |
| Hoffmann et al., travaux sur contraintes et generative modeling | Contraintes, régénération et sémantique de features | Les solveurs et dépendances sont des composants de premier rang |
| Capoyleas, Chen, Hoffmann, 1996 ; Kripac, 1997 | Nommage générique/persistant des entités | Problème ancien, non supprimé par un simple ID de face |
| Rappoport, 2003 | Universal Product Representation pour échange procédural | Une union de capacités réduit la perte mais croît avec chaque système |
| Kim, Pratt, Iyer, Sriram, NISTIR 7433, 2007 | Prototype STEP paramétrique entre systèmes | Faisabilité partielle, barrières API/solveurs/naming déjà identifiées |
| Safdar et al., 2020 | Traduction macro-paramétrique CATIA-NX | Mapping de features, contraintes et naming demeurent les trois verrous |
| González-Lluch et al., 2016 | Taxonomie de qualité des modèles CAO | La qualité sémantique/pragmatique et la réutilisabilité sont moins outillées que la qualité morphologique |

## Thèses sélectionnées

| Thèse | Sujet et résultats | Enseignement de faisabilité |
|---|---|---|
| A. Krishnamurthy, UC Berkeley, 2010 | Algorithmes GPU parallèles pour CAD : splines, intersections, distances | Le GPU accélère des kernels ciblés ; l’intégration dans un noyau robuste reste ouverte |
| V. Borja-Ramirez, Loughborough, 1997 | Modèles de données pour redesign en reverse engineering | L’intention et le contexte de redesign doivent être capturés au-delà de la surface reconstruite |
| F. Boussuge, 2014 | Idéalisation d’assemblages B-rep pour analyse éléments finis | La B-rep commerciale reste une description de bas niveau et doit être enrichie pour le raisonnement |
| K. Li, 2011 | Analyse de forme sur modèles CAO B-rep et symétries | Les symétries sont des priors utiles pour reconnaissance et reconstruction |
| M. Freeman, BYU, 2015 | Forme canonique paramétrique neutre NX-CATIA | Preuve de concept sur primitives contrôlées, pas généralisation |
| J. Staves, BYU, 2016 | Références associatives dans un fichier paramétrique neutre | Bases relationnelles/identité améliorent la traçabilité, pas l’universalité |
| J. F. Gonzalez Avila, 2024 | Faciliter la CAO programmée ; topological naming et interfaces | Confirme l’intérêt du code et la fragilité des références topologiques |
| E. Dupont, Luxembourg, 2025 | Reverse engineering CAO conscient de l’intention | L’intention est une cible d’apprentissage distincte de la géométrie ; ambiguïtés intrinsèques |
| C. Zhang, Arts et Métiers, 2025/2026 | Modèles paramétriques 3D depuis dessins 2D | L’axe le plus proche du besoin ; résultats encore de recherche et sous-ensembles bornés |
| M. Oubari, 2026 | Modèles génératifs profonds pour produits industriels multi-composants sous contraintes | Les assemblages et contraintes multi-composants forment un problème plus large que la pièce unique |

## Lecture critique commune

La littérature de trois décennies établit quatre invariants :

- le modèle géométrique final sous-détermine généralement son historique ;
- une feature a une sémantique dépendante du système et du contexte ;
- les références aux faces/arêtes sont fragiles après modification ;
- la conformité doit tester le comportement, pas seulement la forme.

Les avancées IA 2024-2026 réduisent spectaculairement l’effort d’inférence, mais ne changent pas ces propriétés mathématiques et sémantiques.

[[PAGEBREAK]]

# Cartographie des brevets

## Méthode et avertissement

La recherche a ciblé les classes CPC G06F30/10, G06F30/17, G06F30/27, G06T17/10 et G06N, avec combinaisons « CAD feature », « parametric », « B-rep », « drawing to 3D », « point cloud », « neural network », « feature history » et « exchange ». Les familles ci-dessous sont représentatives des zones de risque et d’antériorité ; elles ne constituent pas une FTO.

Les statuts sont ceux publiquement visibles au 3 août 2026 et doivent être revérifiés par territoire, revendication et événement juridique. Une demande peut être abandonnée dans un pays et active dans un autre ; les demandes non publiées des dix-huit derniers mois ne sont pas visibles.

| Famille / priorité | Objet revendiqué pertinent | Statut public indicatif | Incidence |
|---|---|---|---|
| **US7492364B2**, priorité 23/07/2002, Imagecom | Génération de modèle feature-based depuis vues 2D et format neutre | Expiré pour défaut de taxe selon dossier public | Antériorité forte : l’idée générale 2D→features n’est pas nouvelle |
| **US8346020B2**, priorité 02/05/2008, Zentech | Reconstruction 3D automatisée depuis plusieurs dessins 2D ; relations inter-vues lisibles machine | Actif, échéance ajustée indiquée 02/11/2031 | Risque ciblé si des revendications couvrent le pipeline exact par territoire |
| **US11514214B2**, priorité 29/12/2018, Dassault | Formation d’un dataset pour inférence de features solides depuis dessins libres | Actif, famille jusqu’aux environs de 2040 | Risque dataset/synthèse et feature tree ; analyser revendications, pas seulement résumé |
| **US11922573B2**, même priorité, Dassault | Réseau pour inférer une feature solide, courbes/sweep, arbres CSG/history | Actif, échéance ajustée indiquée 18/07/2042 | Très pertinent pour image/sketch→feature ; FTO indispensable |
| **US11869147B2**, priorité 20/08/2020, Dassault | Réseau produisant un modèle 3D paramétré depuis esquisse 2D, avec paramètres ajustables | Actif, échéance vers 2042 | Zone directe du besoin ; concevoir à partir des revendications et état de la technique |
| **US12002157B2**, même priorité, Dassault | VAE produisant modèles 3D paramétrés et variantes depuis esquisse | Actif | Risque génération probabiliste/variantes paramétriques |
| **EP4293627A1 / US20230410452A1**, priorité 16/06/2022, Dassault | Inférence de géométrie 3D sur esquisse 2D | Demandes publiées, statut par territoire à confirmer | Suivi de famille requis |
| **EP4071658A1 / US12288013B2**, priorité 31/03/2021 | Représentation UV-Net de B-rep pour réseaux : graphe + grilles UV | Brevet US délivré, famille active selon registre public | Important pour encodeurs B-rep utilisant précisément cette représentation |
| **US12265764B2**, priorité 24/05/2023 | IA générant une CAO multi-composants depuis exigences | Actif | Revendications larges sur assembly generation à examiner |
| **US20250200232A1**, priorité 08/03/2021 | Échange CAO par fonctions implicites/SDF exprimées comme code, édition et GPU | Demande publiée/famille en cours selon territoires | Pertinent pour toute stratégie implicite/code de transport |
| **US20160246899A1 / WO2016135674**, Onshape | Système CAO cloud multi-utilisateur paramétrique feature-based | Famille à statut territorial mixte | Antériorité/risque pour collaboration et exécution cloud, non pour échange neutre seul |
| **US20190147317A1** | Suggestion automatique de mates d’assemblage par apprentissage | Demande/famille à vérifier | Pertinent pour reconstruction d’assemblages |
| **US10499031B2**, Dassault | Depth map vers modèle paramétrique d’une classe | Brevet délivré | Risque sur pipeline spécialisé image/profondeur→paramètres |
| **US10943037B2** | Génération d’un modèle CAO depuis maillage éléments finis | Brevet délivré | Voie mesh/FEA→faces géométriques couverte par revendications spécifiques |
| **US5537519** | Conversion B-rep vers CSG | Ancien brevet expiré | Antériorité sur récupération de construction à partir de B-rep |

## Analyse de risque brevet

Les concepts généraux sont largement antériorisés : reverse engineering, CSG/B-rep, feature recognition, construction 3D depuis vues, historique sous forme de commandes et CAO cloud. Le risque n’est donc pas de « breveter l’idée générale », mais de tomber dans une combinaison revendiquée récente : représentation de données précise, méthode d’entraînement, interaction utilisateur, ordre des étapes ou mécanisme de variation.

Trois actions sont nécessaires avant le prototype public :

1. cartographie revendication-par-revendication des familles Dassault, Onshape, Siemens/Autodesk/NVIDIA et des acteurs scan-to-CAD ;
2. recherche de statut et équivalents EP/US/CN/JP/KR, puis avis FTO sur les pays de commercialisation ;
3. journal d’antériorité et d’architecture documentant les choix indépendants, licences de datasets et dates de conception.

Le coût d’une FTO initiale ciblée est inclus dans l’estimation projet ; une opinion complète multi-territoires peut dépasser largement ce budget selon le nombre de familles.

[[LANDSCAPE]]

# Matrice de couverture transversale

_Légende : Oui = capacité native significative ; Part. = sous-ensemble, extension ou dépendance au produit hôte ; Non = hors objectif. « Ouvert » distingue spécification et implémentation. La colonne performance indique le profil dominant, pas un classement absolu._

| Technologie | Géométrie exacte | Paramètres / contraintes | Historique / features | PMI / GD&T | Assemblages / variantes | Spécification ouverte | Implémentation ouverte | IA / GPU | Performance dominante | Maturité | Rôle recommandé |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STEP AP242 + 42 | Oui | Part. | Part. | Oui | Oui | Oui, ISO | Part., outils mixtes | Non | Échange/archivage, textuel | C | Autorité d’échange mécanique |
| STEP 55/108/111/112/113 | Oui via résultat | Oui | Oui, sous-ensemble | Part. via AP242 | Part. | Oui, ISO | Faible | Non | Pas de benchmark commun | R/E industriel | Base sémantique à implémenter |
| JT / ISO 14306 | Oui/embarqué + LOD | Non | Non | Oui | Oui | Oui, ISO | Non, toolkit commercial | GPU-friendly | Très bon grands assemblages | C | Vue légère / DMU |
| QIF | Références géométriques | Non | Non | Oui, qualité | Part. | Oui, ISO + XSD | Oui partiellement | Non | XML, métrologie | M/C | Boucle inspection/qualité |
| glTF | Non, mesh | Non | Non | Non | Scène | Oui | Oui | Oui | Excellent rendu runtime | C | Visualisation web |
| OpenUSD | Part., via schémas/mesh | Variants, pas CAO | Graphe scène, pas features | Non mécanique | Oui, scène | Oui, AOUSD | Oui | Oui | Grandes scènes/streaming | C DCC | Composition et collaboration visuelle |
| IFC | Part. selon géométrie | Domaine BIM | Part. BIM | Propriétés BIM | Oui BIM | Oui, ISO/buildingSMART | Oui | Part. | Gros modèles, MVD | C BIM | Méthodes de gouvernance seulement |
| OCCT | Oui | Non seul | OCAF applicatif | XDE partiel | XDE structure | API ouverte | Oui | Rendu, CPU exact | Bon, cas dégénérés sensibles | M/C | Noyau ouvert de référence |
| Parasolid | Oui | Non seul | Non seul | Non seul | Non seul | Non | Non | Facettisation/convergent | Très haut industriel, NP | C | Backend commercial optionnel |
| ACIS | Oui | Non seul | Non seul | Non seul | Non seul | SAT partiel, pas noyau | Non | CPU exact | Très haut industriel, NP | C | Backend commercial optionnel |
| CGM | Oui | Non seul | Non seul | Non seul | Non seul | Non | Non | CPU exact | Très haut industriel, NP | C | Backend Dassault / oracle |
| FreeCAD | Oui | Oui | Oui | Part. | Oui | Format de fait | Oui | Rendu, CPU exact | Interactif, recompute variable | M | Banc d’intégration ouvert |
| CadQuery | Oui | Part. | Oui, code | Non | Part. | API documentée | Oui | IA-friendly | Pièces/automatisation | M | Frontend et cible IA |
| OpenSCAD | Non analytique | Paramètres de code | Oui, CSG | Non | Non | Langage ouvert de fait | Oui | Preview GPU | Bon CSG mesh, Manifold | M | Référence CSG simple |
| FeatureScript / Onshape | Oui | Oui | Oui | Part./plateforme | Oui | Langage/stdlib visibles | Runtime non | IA/API cloud | Calcul serveur, NP | C | Référence de features/requêtes |
| Blender | Non, mesh/SubD | Nodes, pas mécanique | Modifiers/nodes | Non | Scène/variants partiels | `.blend` code/documenté | Oui, GPL | Oui | Excellent DCC/GPU | C | Rendu et données synthétiques |
| CATIA | Oui | Oui | Oui | Oui | Oui | Non | Non | IA intégrée | Très haut, NP | C | Cible native/oracle |
| NX / Designcenter | Oui | Oui | Oui | Oui | Oui | Non | Non | IA intégrée | Très haut, NP | C | Cible native/oracle |
| Creo | Oui | Oui | Oui | Oui | Oui | Non | Non | IA intégrée | Très haut, NP | C | Cible native/oracle |
| SolidWorks | Oui | Oui | Oui | Oui | Oui | Non | Non | Part. | Haut, NP | C | Cible native/oracle |
| Fusion 360 | Oui | Oui | Oui | En progrès | Oui | Non | Non | Données/IA Autodesk | Bon, cloud, NP | M/C | Cible/API et dataset |
| Rhino/Grasshopper | Oui NURBS | Oui, graphe | Graphe, pas arbre mécanique | Faible | Faible | 3DM/openNURBS part. | Part. | Oui via plugins | Excellent surfaces/design | C | Surface/UX computationnelle |
| LLVM/MLIR | Non | Types/règles génériques | IR/passes, pas CAO | Non | Non | Oui | Oui | Oui | Compilateur CPU/GPU | C | Infrastructure interne |
| OpenXLA/StableHLO | Non | Non CAO | Graphe tenseur | Non | Non | Oui | Oui | Oui | Accélérateurs ML | M/C | Compilation modèles IA |
| ONNX/ORT | Non | Non CAO | Graphe IA versionné | Non | Non | Oui | Oui | Oui | Inférence portable | C | Déploiement IA |
| CUDA/Warp/Triton | Non seuls | Non | Kernels | Non | Non | Mixte | Mixte | Oui | Calcul dense massif | C/M | Accélération ciblée |
| Geomagic/PolyWorks/ZEISS | Oui, reconstruite | Oui/part. | Oui, guidé/partiel | Tolérances/inspection | Faible | Non | Non | Automatisation part. | Scan-to-CAD industriel, NP | C | Référence métier/annotation |
| IA CAD 2024-2026 | Variable | Part. | Part., vocabulaire borné | Non | Très faible | Papiers/code variables | Variable | Oui | Benchmarks académiques | R/E | Proposer et classer des hypothèses |

[[PORTRAIT]]

# Verrous scientifiques restant à résoudre

## 1. Inversion sous-déterminée

Une géométrie finale, un scan ou un ensemble de vues admettent plusieurs historiques, systèmes de cotes et intentions valides. Sans information supplémentaire, aucune méthode - symbolique ou neurale - ne peut retrouver avec certitude l’original. Le système doit représenter l’incertitude et demander une décision lorsque plusieurs solutions satisfont les observations.

## 2. Sémantique universelle des features

Les mots « trou », « poche », « nervure », « congé » ou « motif » cachent options, références, étendues, transitions, réparations et comportements différents. Le mapping many-to-many entre logiciels n’a pas de solution complète. Part 113 améliore le vocabulaire mais ne spécifie pas toutes les variantes propriétaires.

## 3. Identité topologique persistante

Après fusion, scission, suppression, tangence, changement de tolérance ou de noyau, une face peut ne plus avoir d’équivalent unique. Les solutions combinent lignée d’opération, requêtes sémantiques, graphes d’adjacence et signatures géométriques ; aucune n’offre une garantie universelle.

## 4. Robustesse numérique et tolérances

Les noyaux emploient flottants, tolérances locales et approximations d’intersection différentes. Il faut séparer tolérance numérique de construction, précision du capteur, tolérance dimensionnelle et zone GD&T fonctionnelle. Une seule valeur « tolerance » serait scientifiquement incorrecte.

## 5. Sémantique des solveurs

Transférer équations et contraintes ne capture pas sélection de branche, priorités, redondance, valeurs initiales, heuristiques, critères de convergence ou diagnostics. Deux sketchers peuvent choisir des configurations symétriques différentes.

## 6. Features avancées et hybrides

Lofts/sweeps, surfaces classe A, fillets variables, shells, drafts, tôlerie, composites, lattices, SubD, implicites et opérations directes sont encore peu représentés dans les jeux de données et langages académiques.

## 7. Assemblages et configurations

Les contraintes d’accostage ne suffisent pas : occurrences, variantes, substitutions, flexibilité, enveloppes, références inter-pièces, mécanismes, gestion d’interférences et configuration produit doivent rester cohérents.

## 8. PMI/GD&T réellement sémantique

Le glyphe affiché n’est pas la tolérance. Il faut conserver datum reference frames, features de taille, modificateurs de matière, zones, unités, règles générales, état de surface et association exacte aux entités, y compris après régénération.

## 9. Métriques de conformité

Il manque un benchmark combinant : validité B-rep, distance exacte, propriétés de masse, identité topologique, satisfaction des contraintes, scénarios d’édition, PMI, assemblages, export/import et comparaison multi-noyaux. Les métriques IA actuelles sont insuffisantes.

## 10. Déterminisme et versioning

Le résultat dépend de la version du noyau, du solveur, des seuils, de l’ordre des opérations et parfois du parallélisme. Une reconstruction vérifiable doit enregistrer cet environnement et produire des propriétés de validation.

## 11. GPU pour géométrie exacte

Les sous-problèmes denses sont accélérables ; les changements topologiques et cas dégénérés le sont beaucoup moins. La divergence numérique et l’ordre non déterministe des réductions compliquent la qualification.

## 12. Explicabilité de l’intention inférée

Un modèle doit relier chaque choix à une source : cote du plan, géométrie observée, règle de norme, analogie de famille ou hypothèse. Sans provenance, le modèle peut être plausible mais invérifiable.

# Verrous industriels

1. **Accès aux données.** Les historiques CAO réels, PMI et assemblages sont sensibles, couverts par secrets d’affaires et licences. Les modèles publics sont trop simples.

2. **Droits d’entraînement.** Posséder un fichier ne confère pas automatiquement le droit de l’utiliser pour entraîner, publier ou commercialiser un modèle.

3. **API opaques.** Des états implicites, options internes ou références ne sont pas exposés. Les APIs changent par version.

4. **Matrice de compatibilité.** Noyau × CAO × version × format × PMI × configuration × plateforme crée une explosion combinatoire.

5. **Licences OEM.** Royalties, redistribution, cloud, export control, support et escrow peuvent modifier l’économie du projet.

6. **Incitations fournisseurs.** La portabilité complète de l’historique réduit le verrouillage client et peut ne pas être prioritaire pour les éditeurs.

7. **Qualification.** Aéronautique, automobile, médical et défense exigent traçabilité, gestion de configuration, validation et responsabilités nettement supérieures à un outil de création visuelle.

8. **Acceptation ingénieur.** Une automatisation opaque qui modifie la logique de conception augmente le risque et sera rejetée, même si la forme est correcte.

9. **Compétences rares.** Noyaux B-rep, normes STEP, solveurs, GPU, MLOps, métrologie et propriété intellectuelle sont des expertises différentes.

10. **Standardisation lente.** Un consensus ISO et des implémentations multi-éditeurs prennent généralement plusieurs années.

11. **Sécurité.** Le code généré, les plugins et fichiers natifs doivent être sandboxés ; les modèles industriels sont des actifs sensibles.

12. **Pérennité.** Une archive paramétrique doit rester exécutable après disparition d’une version de noyau ou d’un fournisseur.

[[PAGEBREAK]]

# Briques réutilisables, à compléter et inexistantes

## Briques réutilisables sans réinvention

| Domaine | Briques | Usage recommandé |
|---|---|---|
| Schéma mécanique | STEP AP242, ISO 10303-42/-55/-108/-109/-111/-112/-113 | Vocabulaire normatif, géométrie, produit, procédure, paramètres, contraintes et features |
| Fabrication et qualité | AP238/ISO 14649, QIF | Workingsteps, inspection, résultats, traçabilité métrologique |
| Conformité | CAx-IF, LOTAR, validation properties | Profils, modèles de référence, vérification d’export/archivage |
| Noyau ouvert | OCCT, OCAF, XDE | B-rep exacte, document, transactions, structure produit, STEP |
| Noyaux commerciaux | Parasolid, ACIS, CGM, C3D | Backends optionnels lorsque robustesse/support justifient la licence |
| Contraintes | D-Cubed ou FreeCAD Sketcher/SolveSpace selon stratégie | Sketcher et assemblages ; ne pas recréer un solveur complet sans nécessité |
| CAO ouverte | FreeCAD, SALOME SHAPER | Bancs d’intégration et tests de recompute |
| Programmation CAO | CadQuery, build123d, OpenCSM, FeatureScript comme référence | Prototypage, génération, corpus de programmes et comparaison de sémantique |
| Traduction | HOOPS Exchange, 3D InterOp, CAD Exchanger, Datakit | Formats natifs et PMI sous licence |
| Scènes et vues | JT, glTF, OpenUSD | DMU, LOD, web/GPU, collaboration visuelle |
| Géométrie mesh/implicite | CGAL, Manifold, OpenVDB, Polygonica/nTop sous licence | Capture, réparation, additif et calculs complémentaires |
| IA | ONNX/ORT, PyTorch, modèles/datasets académiques | Perception, proposition de candidats, déploiement |
| Compilation/GPU | LLVM/MLIR, StableHLO, TVM/IREE, CUDA/Warp/Triton | Pipeline interne, kernels ciblés, accélération |

## Briques à redévelopper ou compléter

- profils implémentables des ressources STEP procédurales, avec versioning et règles d’exécution ;
- couche de correspondance sémantique entre features neutres et opérations de chaque backend ;
- références persistantes multi-stratégies, détection et exposition des ambiguïtés ;
- validateur comportemental par scénarios de modification ;
- modèle de provenance, hypothèses, confiance, unités et quatre catégories de tolérances ;
- corpus légalement réutilisable contenant historiques, PMI, assemblages et modifications ;
- adaptateurs CAO natifs autorisés et tests continus par version ;
- sandbox d’exécution des programmes générés ;
- observabilité : logs de régénération, causes d’échec, propriétés de validation et comparaison différentielles ;
- interface moderne de requête/diff/streaming autour des modèles STEP, sans redéfinir leur sémantique.

## Briques qui n’existent pas encore de façon satisfaisante

- implémentation ouverte et complète de STEP procédural/paramétrique avec suite de conformité industrielle ;
- représentation universelle prouvée de toutes les features propriétaires et de leur comportement ;
- nommage topologique déterministe à travers toute opération, version et noyau ;
- round-trip natif bidirectionnel et qualifié CATIA-NX-Creo-SolidWorks-Fusion-Rhino ;
- benchmark public couvrant pièces complexes, assemblages, PMI, tolérances et modifications hors distribution ;
- système IA certifié qui retrouve sans ambiguïté l’intention depuis toute entrée ;
- noyau B-rep généraliste, exact, robuste, open source et entièrement GPU ;
- standard ouvert portant simultanément historique exécutable, assemblage, configuration, PMI pleinement associatif et environnement de régénération reproductible.

> **Réponse nette.** Les primitives géométriques, standards, noyaux, solveurs, compilateurs et outils d’IA existent. La couche de confiance interopérable - sémantique, identité, versioning et conformité - est le véritable produit à construire.

[[PAGEBREAK]]

# Risques du projet

## Matrice des risques

| Risque | Probabilité | Impact | Signal précoce | Réduction proposée |
|---|---|---|---|---|
| Périmètre universel prématuré | Élevée | Critique | Ajout de surfacique/tôlerie/assemblages avant stabilité des primitives | Profils de capacité versionnés et critères d’entrée/sortie stricts |
| Sémantique différente entre CAO | Élevée | Critique | Mappings one-off et exceptions par logiciel | Définir équivalence observable, conserver fallback B-rep et marquer pertes |
| Persistent naming insuffisant | Élevée | Critique | Références cassées après petits changements | Lignée + requête sémantique + signature + tests d’édition + ambiguïté explicite |
| Échecs B-rep/cas dégénérés | Moyenne/élevée | Critique | Taux de healing élevé, résultats différents entre noyaux | Corpus adversarial, double backend/oracle, validation topologique/géométrique |
| Dataset trop simple ou non licencié | Élevée | Critique | Très bon benchmark académique, mauvais pilote industriel | Accords de données, anonymisation, familles/versions/PMI, audit juridique |
| Hallucination IA | Élevée | Critique | Programmes exécutables mais dimensions/intentions inventées | Preuves par source, contraintes dures, abstention et revue humaine |
| Dépendance à un SDK fournisseur | Moyenne/élevée | Élevé | Coûts/ABI/versions imposent la roadmap | Interface d’adaptation, au moins deux backends, clauses de continuité/escrow |
| Brevets / FTO | Moyenne | Élevé | Revendications proches sur pipeline ou représentation | FTO précoce, design-around documenté, surveillance trimestrielle |
| Performance GPU surestimée | Élevée | Moyen/élevé | Temps dominant reste boolean/fillet CPU | Profiler avant portage ; GPU sur batch/dense uniquement |
| Divergence CPU/GPU/version | Moyenne | Élevé | Hash/propriétés changent entre exécutions | Modes déterministes, version pinning, tolérances et validation properties |
| Qualification réglementaire | Moyenne | Critique | Les équipes sécurité refusent une sortie IA opaque | QMS, traçabilité, séparation recommandation/autorité, périmètre non safety au début |
| Sécurité du code généré | Moyenne | Élevé | Accès fichier/réseau ou déni de service | IR bornée ou sandbox stricte, quotas, validation statique/dynamique |
| Adoption insuffisante | Moyenne | Élevé | Ingénieurs corrigent systématiquement la reconstruction | UX d’explication, comparaison plan/3D, édition familière, mesure du temps net |
| Coût de standardisation | Élevée | Moyen | Consensus bloqué sur features propriétaires | Publier d’abord profil et suite de conformité ; standardiser après preuves |
| Recrutement d’experts | Élevée | Élevé | Dépendance à une personne par domaine | Consortium, partenariats académiques/éditeurs, documentation et tests |

## Risque de « faux succès »

Le risque le plus dangereux est un démonstrateur spectaculaire qui reconstruit des pièces simples mais ne mesure pas les pertes. Il peut conduire à une architecture figée autour de métriques de forme, puis révéler tardivement l’absence de PMI, d’identité persistante ou de comportement de régénération.

Tout pilote doit donc publier un **registre des pertes** et compter séparément : géométrie valide, dimensions exactes, contraintes satisfaites, scénarios d’édition réussis, PMI conservé, références stables, temps de correction humaine et portabilité.

# Coûts estimés

## Hypothèses

Estimations d’ordre de grandeur en euros 2026, hors TVA, acquisitions d’entreprise et certification produit complète. Hypothèse de coût chargé : **140 à 220 k€ par ETP·an** pour une équipe européenne spécialisée, incluant salaire, charges, management et infrastructure ordinaire. Les SDK OEM sont généralement sur devis et parfois assortis de royalties.

## Scénarios

| Scénario | Contenu | Effort | Durée | Coût estimé | Incertitude |
|---|---|---|---|---|---|
| **A - Démonstrateur de faisabilité** | Pièces unitaires prismatico-tournées ; 8-12 features ; OCCT ; un frontend programme ; export AP242 ; IA candidat ; tests d’édition | 8-15 ETP·an | 9-12 mois | **1,8-4,8 M€** | ±35 % |
| **B - MVP industriel vertical** | Plans 2D + points ; PMI borné ; une industrie ; deux backends/oracles ; adaptateur vers 2 CAO ; sécurité, MLOps et QA | 35-60 ETP·an | 24-30 mois | **7-19 M€** | ±40 % |
| **C - Plateforme multi-CAO et conformité ouverte** | Features étendues, assemblages/configurations, PMI, 4+ CAO, corpus public/privé, organisme de conformité et standardisation | 150-300 ETP·an | 4-6 ans | **30-90 M€** | ±50 % |
| **D - Modèle de fondation industriel** | Acquisition/curation massive de données, multimodal, préentraînement, RL/outillage et infrastructure sécurisée | +40-120 ETP·an + calcul | 2-4 ans en parallèle | **+8-30 M€** | Très forte |
| **Réécriture d’un noyau généraliste** | B-rep, surfacing, booleans, fillets, healing, tessellation, threading, traducteurs et support | Plusieurs centaines d’ETP·an | 7-12+ ans | **50-150 M€+** | Extrême |

## Décomposition du scénario B

| Poste | Fourchette |
|---|---|
| Géométrie, sémantique, solveurs et validation | 2,5-5,0 M€ |
| IA, données, annotation, MLOps | 1,5-4,0 M€ |
| Adaptateurs CAO/SDK et laboratoire de versions | 1,0-3,0 M€ |
| GPU/compute, stockage sécurisé et observabilité | 0,4-1,5 M€ |
| QA, corpus de conformité, métrologie et pilotes | 0,8-2,0 M€ |
| Brevets/FTO, contrats de données, normes et gouvernance | 0,4-1,0 M€ |
| Marge de risque technique | 0,4-2,5 M€ |

La dépense la plus évitable est la réécriture d’un noyau. La dépense la moins compressible est la constitution du corpus, la validation et la maintenance des adaptateurs.

## Coût récurrent

Après MVP, prévoir 18 à 30 % du coût de développement initial par an pour : nouvelles versions CAO, régressions de noyau, ajout de formats, sécurité, support, annotation continue, compute d’inférence, normes et qualification. Une plateforme multi-CAO peut demander une équipe permanente de 15 à 35 personnes avant même l’expansion fonctionnelle.

# Bénéfices industriels

## Sources de valeur

- réduction du temps de reconstruction de plans patrimoniaux, scans et géométries « dumb » ;
- réutilisation d’actifs conçus dans des CAO différentes ;
- diminution du rework lié aux traductions et aux références cassées ;
- génération plus rapide de variantes S/M/L et familles dimensionnelles ;
- continuité MBD : modèle, PMI, fabrication, contrôle et archivage ;
- détection précoce d’ambiguïtés et incohérences de plan ;
- automatisation CAO auditable au lieu de macros spécifiques non gouvernées ;
- souveraineté et réduction du lock-in, sous réserve de ne pas remplacer un verrou par un SDK unique ;
- création d’un actif de données industrielles et d’une suite de conformité différenciante ;
- nouvelles offres : SDK, validation, migration, archivage, reverse engineering, copilote et certification.

## Modèle de valeur quantitatif

La valeur annuelle brute d’automatisation peut être estimée par :

**V × H × C × A**, où V est le volume de pièces/an, H les heures manuelles par pièce, C le coût horaire chargé et A le taux net d’automatisation après revue.

| Hypothèse | Valeur |
|---|---|
| 10 000 pièces/an | V = 10 000 |
| 6 heures de reconstruction moyenne | H = 6 h |
| 90 €/h chargé | C = 90 € |
| 50 % de temps réellement évité après QA | A = 0,50 |
| **Économie brute** | **2,7 M€/an** |

À 1 000 pièces/an, le même calcul donne 0,27 M€/an ; le projet ne s’amortit alors que si les erreurs évitées, la maintenance de patrimoine ou la vente de plateforme ajoutent une valeur significative. À 100 000 pièces/an, le gain potentiel devient 27 M€/an avant coûts d’exploitation.

Cette formule exclut les bénéfices parfois supérieurs : éviter une erreur de tolérance, une reprise d’outillage, un arrêt de chaîne, une non-conformité réglementaire ou la perte d’un modèle critique. Ces gains doivent être mesurés dans les pilotes, non supposés.

## Bénéfices stratégiques

Le bénéfice le plus défendable n’est pas « l’IA dessine à la place de l’ingénieur ». C’est un **fil numérique vérifiable** qui transforme archives et entrées hétérogènes en actifs structurés, comparables, régénérables et exploitables par plusieurs outils. Cela permet ensuite recherche de similarité, automatisation des variantes, estimation de fabricabilité, contrôle automatisé et capitalisation du savoir.

[[PAGEBREAK]]

# Architecture globale la plus prometteuse - conclusion après étude

## Choix entre les stratégies possibles

| Stratégie | Atout | Échec probable | Verdict |
|---|---|---|---|
| IA → fichier natif d’une CAO | Démonstration rapide, richesse de la cible | Verrou fournisseur, faible vérifiabilité, versions et licences | Utile comme adaptateur, pas comme cœur |
| Tout STEP/AP242 sans runtime propre | Normatif et pérenne | Ressources procédurales peu implémentées, sémantique d’exécution incomplète | Base nécessaire, insuffisante seule |
| Mesh/implicite comme autorité | GPU et robustesse sur formes complexes | Perte de B-rep, dimensions, PMI et features | Couche complémentaire uniquement |
| Nouveau langage complet immédiatement | Liberté de conception | Réinvention de STEP/DSL existants, adoption et conformance non prouvées | À écarter en Phase 2 |
| **Chaîne hybride standard-centrée** | Réutilise normes/noyaux, sépare IA et autorité, vérifiable et multi-backend | Coût des mappings et conformité | **Option recommandée** |

## Architecture recommandée

Cette architecture n’est pas la proposition d’un nouveau langage. C’est une répartition de responsabilités à éprouver avec des technologies existantes.

| Couche | Responsabilité | Briques existantes recommandées |
|---|---|---|
| **1. Entrées et preuves** | Plans vectoriels/raster, texte, PMI, scans, meshes, STEP/JT et CAO native ; conserver source, unités et provenance | PDF/DXF/STEP/JT, QIF, HOOPS/3D InterOp/CAD Exchanger, OpenCV/outils vision |
| **2. Extraction multimodale** | Détecter vues, cotes, symboles, primitives, surfaces, features et relations ; produire plusieurs hypothèses avec confiance | Modèles CAD 2024-2026, OCR/vision, BRepNet/UV-style encoders, retrieval |
| **3. Modèle sémantique canonique interne** | Graphe typé de produit, opérations, paramètres, contraintes, références, PMI, variantes et provenance ; résultat explicite associé | Concepts AP242 + ISO 10303-42/-55/-108/-109/-111/-112/-113 ; pas de nouvelle syntaxe publique |
| **4. Vérification et exécution déterministes** | Type/units checks, DAG, solveur, résolution de références, règles, sandbox, journal et propriétés de validation | SolveSpace/FreeCAD Sketcher ou D-Cubed ; règles formelles ; moteur versionné |
| **5. Noyaux géométriques substituables** | Calculer B-rep, healing, tessellation et propriétés ; comparer résultats | OCCT comme référence ouverte ; Parasolid/ACIS/CGM/C3D ou CAO natives comme backends/oracles optionnels |
| **6. Conformité comportementale** | Tester forme, topologie, contraintes, PMI et scénarios d’édition multi-paramètres/multi-noyaux | Méthodes CAx-IF/LOTAR, corpus golden/adversarial, QIF pour qualité |
| **7. Sorties spécialisées** | Autorité neutre, fabrication, qualité, vue légère, scène et natif lorsque autorisé | STEP AP242 Ed.4, AP238, QIF, JT, glTF/OpenUSD, API CATIA/NX/Creo/SolidWorks/Fusion |
| **8. Accélération sélective** | Entraînement/inférence, rendu, sampling, points, distances, recherche et lots | ONNX Runtime/OpenXLA, CUDA/Warp/Triton, PyTorch3D/Kaolin, OpenVDB |

## Principe de double représentation

Le modèle doit conserver simultanément :

- la **procédure et la sémantique** nécessaires à l’édition ;
- le **résultat géométrique explicite** exact, avec propriétés de validation.

Ce principe est déjà prévu par ISO 10303-55. Il permet d’ouvrir le modèle même si une feature n’est pas comprise, de comparer des backends et de diagnostiquer une divergence. La B-rep n’est pas un cache jetable ; elle est une preuve vérifiable du dernier état régénéré.

## Principe d’identité et d’ambiguïté

Une référence ne doit jamais être un simple numéro de face. Elle doit combiner :

- lignée de création/modification ;
- requête sémantique, par exemple « face cylindrique créée par le perçage » ;
- contexte d’adjacence et signature géométrique ;
- état de résolution : unique, multiple ou introuvable.

Lorsque plusieurs entités satisfont la requête, le système doit s’abstenir ou demander une décision. Transformer une ambiguïté en choix silencieux est incompatible avec l’objectif « zéro ambiguïté ».

## Répartition CPU/GPU

| GPU prioritaire | CPU/noyau exact prioritaire |
|---|---|
| Vision/OCR, encodage points/B-rep échantillonnée, rendu différentiable, nearest-neighbor, Chamfer/IoU, génération de candidats, tessellation massive, volumes et lots | Construction B-rep autoritative, booléens/fillets exacts, solveur de contraintes qualifié, healing, persistent naming, règles PMI et décisions de conformité |

Une opération peut migrer vers GPU après preuve de déterminisme, précision et bénéfice au profilage. Le choix ne doit pas être idéologique.

## Profils de conformité recommandés

1. **Profil P1 - Pièce prismatique/tournée.** Esquisse contrainte, extrusion, révolution, perçage, booléen, motif, miroir, congé/chanfrein constant, unités et paramètres.

2. **Profil P2 - MBD pièce.** P1 + datums, dimensions, GD&T borné, états de surface, matériaux et propriétés de validation.

3. **Profil P3 - Assemblage.** P2 + occurrences, mates de base, configurations, BOM et cinématique simple.

4. **Profil P4 - Géométrie avancée.** Sweeps/lofts, fillets variables, coques/drafts, tôlerie et surfaces libres.

Chaque profil doit définir syntaxe de données via normes existantes, sémantique d’exécution, erreurs, tolérances, tests et pertes admises. P4 ne doit pas bloquer l’industrialisation de P1/P2.

# Plan de décision et critères Go/No-Go

## Phase suivante recommandée

Un programme de 9 à 12 mois peut tester la conclusion sans créer de langage public :

1. sélectionner 500 à 2 000 pièces industrielles légalement exploitables, avec plans, historique et modifications ;
2. définir le profil P1 par mapping explicite vers STEP 55/108/111/112/113 ;
3. implémenter une représentation interne versionnée et une exécution OCCT ;
4. connecter un second oracle - FreeCAD, Parasolid ou une CAO commerciale ;
5. entraîner/adapter l’IA à proposer des programmes et mesurer l’abstention ;
6. exécuter un corpus de scénarios d’édition et exports AP242 ;
7. publier la matrice de pertes et le coût de correction humaine.

## Seuils de passage suggérés

| Indicateur | Seuil POC proposé |
|---|---|
| Validité B-rep sur cas supportés | ≥ 99 % après une régénération propre, sans healing silencieux |
| Exactitude des dimensions explicitement cotées | 100 % ou abstention explicite |
| Conservation des unités et tolérances du profil | 100 % |
| Scénarios d’édition réussis sur pièces acceptées | ≥ 95 % |
| Références ambiguës résolues silencieusement | 0 |
| Export/import AP242 géométrie + propriétés de validation | ≥ 99 % |
| Temps humain net économisé sur pilote | ≥ 40 % médian |
| Pièces hors profil correctement refusées/dirigées vers revue | ≥ 95 % |

## Décision finale

**Go conditionnel** pour un démonstrateur et un MVP vertical fondés sur réutilisation. **No-Go** pour une promesse immédiate de reconstruction universelle ou pour la réécriture d’un noyau.

La création éventuelle d’un standard public ne devrait commencer qu’après trois preuves : un profil P1/P2 exécuté par au moins deux backends, une suite de conformité publiée et un bénéfice industriel mesuré. À ce moment, la standardisation devra prioritairement proposer des profils/extensions compatibles avec STEP plutôt qu’un écosystème concurrent.

[[PAGEBREAK]]

# Bibliographie et sources primaires

## Normes, consortiums et qualification

- S01 - [ISO 10303-1:2024 - Overview and fundamental principles](https://www.iso.org/standard/83105.html)
- S02 - [ISO 10303-11:2004 - EXPRESS](https://www.iso.org/standard/38047.html)
- S03 - [ISO 10303-21:2016 - Clear text encoding](https://www.iso.org/standard/63141.html)
- S04 - [ISO/TS 10303-26:2011 - Binary representation using HDF5](https://www.iso.org/standard/50029.html)
- S05 - [ISO 10303-28:2007 - XML representations](https://www.iso.org/standard/40646.html)
- S06 - [ISO 10303-42:2025 - Geometric and topological representation](https://www.iso.org/standard/91386.html)
- S07 - [ISO 10303-55:2005 - Procedural and hybrid representation](https://www.iso.org/standard/38226.html)
- S08 - [ISO 10303-108:2005 - Parameterization and constraints](https://www.iso.org/standard/34697.html)
- S09 - [ISO 10303-109:2004 - Kinematic and geometric constraints for assembly models](https://www.iso.org/standard/38039.html)
- S10 - [ISO 10303-111:2007 - Procedural solid modelling](https://www.iso.org/standard/39561.html)
- S11 - [ISO 10303-112:2006 - Procedural 2D modelling](https://www.iso.org/standard/39581.html)
- S12 - [ISO 10303-113:2025 - Mechanical features](https://www.iso.org/standard/91389.html)
- S13 - [ISO 10303-203:2011 AP203 Edition 2](https://www.iso.org/standard/44305.html)
- S14 - [ISO 10303-214:2010 AP214 Edition 3](https://www.iso.org/standard/43669.html)
- S15 - [ISO 10303-242:2025 AP242 Edition 4](https://www.iso.org/standard/84300.html)
- S16 - [AP242 Edition 5 - Committee Draft](https://www.iso.org/standard/93277.html)
- S17 - [prostep ivip - Fact sheet ISO 10303-242](https://www.prostep.org/mediathek/fact-sheets/iso-10303-242)
- S18 - [CAx Implementor Forum](https://www.cax-if.org/)
- S19 - [CAx-IF Recommended Practice for 3D tessellated geometry](https://www.cax-if.org/documents/rec_prac_3dtess_geo_v1.pdf)
- S20 - [LOTAR - 3D Mechanical workgroup](https://lotar-international.org/lotar-workgroups/3d-mechanical/)
- S21 - [LOTAR standards catalogue](https://lotar-international.org/lotar-standard/)
- S22 - [LOTAR - Validation properties webinar](https://lotar-international.org/wp-content/uploads/2021/02/LOTAR_Web-Seminar_prostepivip_2021_01_29.pdf)
- S23 - [ISO 10303-238:2022 AP238 Edition 3](https://www.iso.org/standard/84898.html)
- S24 - [AP238 Edition 4 - DIS](https://www.iso.org/standard/86074.html)
- S25 - [ISO 14649-10:2004](https://www.iso.org/standard/40895.html)
- S26 - [STEP Tools - STEP-NC demonstrations](https://www.steptools.com/stds/stepnc/demos.html)
- S27 - [ISO 23952:2020 - QIF](https://www.iso.org/standard/77461.html)
- S28 - [DMSC - QIF Standards](https://qifstandards.org/)
- S29 - [ISO 14306-1:2024 - JT Part 1](https://www.iso.org/standard/86063.html)
- S30 - [ISO 14306-2:2024 - JT Part 2](https://www.iso.org/standard/87427.html)
- S31 - [ISO 14306-3:2025 - JT Part 3](https://www.iso.org/standard/89233.html)
- S32 - [ISO 14306-4:2026 - JT Part 4](https://www.iso.org/standard/86064.html)
- S33 - [Khronos glTF](https://www.khronos.org/gltf/)
- S34 - [AOUSD Core Specification 1.0 announcement](https://aousd.org/news/core-spec-announcement/)
- S35 - [OpenUSD performance recommendations](https://openusd.org/24.08/maxperf.html)
- S36 - [OpenUSD license](https://github.com/PixarAnimationStudios/OpenUSD/blob/dev/LICENSE.txt)
- S37 - [ISO 16739-1:2024 - IFC](https://www.iso.org/standard/84123.html)
- S38 - [buildingSMART IFC 4.3.2.0](https://standards.buildingsmart.org/IFC/RELEASE/IFC4_3/)
- S39 - [3MF specifications and ISO/IEC 25422:2025](https://3mf.io/spec/)
- S40 - [lib3mf](https://github.com/3MFConsortium/lib3mf/)
- S41 - [ISO/ASTM 52915:2020 - AMF](https://www.iso.org/standard/74640.html)
- S42 - [NIST review of IGES preservation](https://nvlpubs.nist.gov/nistpubs/jres/121/jres.121.021.pdf)
- S43 - [Autodesk DXF archive](https://aps.autodesk.com/developer/overview/autocad-dxf-archive)
- S44 - [Library of Congress - STL format description](https://www.loc.gov/preservation/digital/formats/fdd/fdd000504.shtml)
- S45 - [ISO 14739-1:2014 - PRC](https://www.iso.org/standard/54948.html)

## Noyaux, CAO, SDK et projets open source

- K01 - [Open CASCADE Technology releases](https://dev.opencascade.org/release)
- K02 - [OCCT Modeling Data](https://dev.opencascade.org/doc/overview/html/occt_user_guides__modeling_data.html)
- K03 - [OCCT OCAF and TNaming](https://dev.opencascade.org/doc/overview/html/occt_user_guides__ocaf.html)
- K04 - [OCCT XDE](https://dev.opencascade.org/doc/overview/html/occt_user_guides__xde.html)
- K05 - [Parasolid v38.0](https://blogs.sw.siemens.com/plm-components/whats-new-in-parasolid-v-38-0/)
- K06 - [Parasolid evaluation](https://resources.sw.siemens.com/en-US/parasolid-free-evaluation/)
- K07 - [Spatial 3D ACIS Modeler](https://www.spatial.com/solutions/3d-modeling/3d-acis-modeler)
- K08 - [Spatial 2026.1 release](https://blog.spatial.com/news/2026-1-0)
- K09 - [Spatial CGM Modeler](https://www.spatial.com/solutions/3d-modeling/cgm-modeler)
- K10 - [C3D Toolkit](https://c3dlabs.com/products/c3d-toolkit/)
- K11 - [C3D licensing](https://c3dlabs.com/company/licensing/)
- K12 - [PTC Granite interoperability kernel](https://support.ptc.com/images/cs/articles/2020/06/1593411762dEcH/PTC_Creo_Granite_Interoperability_Kernel._Final.pdf)
- K13 - [CGAL packages](https://doc.cgal.org/latest/Manual/packages.html)
- K14 - [CGAL licensing](https://www.cgal.org/license.html)
- K15 - [Manifold](https://github.com/elalish/manifold)
- K16 - [ESP / OpenCSM / EGADS](https://acdl.mit.edu/ESP/)
- K17 - [SolveSpace technology](https://solvespace.com/tech.pl)
- K18 - [D-Cubed](https://www.siemens.com/en-us/products/plm-components/d-cubed/)
- K19 - [D-Cubed 2D Components v79](https://blogs.sw.siemens.com/plm-components/d-cubed-2d-components-version-79-release/)
- K20 - [BRL-CAD](https://github.com/BRL-CAD/brlcad)
- K21 - [FreeCAD](https://github.com/FreeCAD/FreeCAD)
- K22 - [FreeCAD FCStd file format](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/File_Format_FCStd.md)
- K23 - [FreeCAD Topological Naming Problem](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md)
- K24 - [CadQuery](https://github.com/CadQuery/cadquery)
- K25 - [CadQuery assemblies](https://cadquery.readthedocs.io/en/latest/assy.html)
- K26 - [build123d](https://github.com/gumyr/build123d)
- K27 - [build123d limitations and tips](https://build123d.readthedocs.io/en/latest/tips.html)
- K28 - [OpenSCAD architecture and licence](https://openscad.org/about.html)
- K29 - [FeatureScript documentation](https://cad.onshape.com/FsDoc/)
- K30 - [FeatureScript standard library](https://cad.onshape.com/FsDoc/library.html)
- K31 - [Onshape versions and microversions architecture](https://onshape-public.github.io/docs/api-intro/architecture/)
- K32 - [SALOME SHAPER introduction](https://docs.salome-platform.org/latest/gui/SHAPER/General/Introduction.html)
- K33 - [Rhino features](https://www.rhino3d.com/features)
- K34 - [rhino3dm](https://github.com/mcneel/rhino3dm)
- K35 - [Blender DNA](https://developer.blender.org/docs/features/core/dna/)
- K36 - [Blender RNA](https://developer.blender.org/docs/features/core/rna/)
- K37 - [Blender licence](https://www.blender.org/about/license/)
- K38 - [CATIA](https://www.3ds.com/products/catia)
- K39 - [CATIA R2026x](https://www.3ds.com/products/catia/3dexperience-catia/latest-release)
- K40 - [Siemens Designcenter / NX June 2026](https://blogs.sw.siemens.com/designcenter/designcenter-is-for-everyone-june-2026-release/)
- K41 - [PTC Creo 13](https://www.ptc.com/en/news/2026/ptc-brings-ai-powered-guidance-to-the-design-environment-with-creo-13)
- K42 - [SolidWorks 2026](https://blogs.solidworks.com/products/solidworks/whats-new-in-solidworks-2026-design/)
- K43 - [SolidWorks API 2026](https://help.solidworks.com/2026/english/SolidWorks/Sldworks/c_solidworks_api.htm)
- K44 - [Autodesk Fusion](https://www.autodesk.com/products/fusion-360/overview)
- K45 - [Fusion large assembly performance guidance](https://help.autodesk.com/view/fusion360/ENU/?caas=caas%2Fsfdcarticles%2Fsfdcarticles%2FPerformance-issues-when-working-with-large-assemblies-in-Fusion-360-and-HSM.html)
- K46 - [HOOPS Exchange 2026.6](https://docs.techsoft3d.com/hoops/exchange/release_notes/2026.6.0.html)
- K47 - [HOOPS Exchange technical overview](https://docs.techsoft3d.com/hoops/exchange/start/technical-overview.html)
- K48 - [Spatial 3D InterOp](https://www.spatial.com/solutions/cad-translation/3d-interop)
- K49 - [CAD Exchanger](https://cadexchanger.com/)
- K50 - [Datakit CrossCad/Ware](https://www.datakit.com/en/crosscad_ware.php)
- K51 - [Siemens JT Open Toolkit](https://www.siemens.com/en-us/products/plm-components/jt/jt-open-toolkit/)
- K52 - [Geomagic Design X](https://hexagon.com/products/geomagic-design-x)
- K53 - [PolyWorks Modeler](https://www.polyworks.com/en-us/products/polyworks-modeler)
- K54 - [ZEISS Reverse Engineering](https://www.zeiss.com/metrology/en/software/zeiss-reverse-engineering.html)
- K55 - [nTop implicit modeling](https://www.ntop.com/software/capabilities/modeling/)
- K56 - [nTop 5 kernel and Core](https://support.ntop.com/hc/en-us/articles/26062971882131-nTop-5-0-New-Implicit-Modeling-Kernel)
- K57 - [Polygonica](https://www.techsoft3d.com/developers/products/polygonica/)

## IA, jeux de données et publications récentes

- A01 - [ABC: A Big CAD Model Dataset, CVPR 2019](https://openaccess.thecvf.com/content_CVPR_2019/html/Koch_ABC_A_Big_CAD_Model_Dataset_for_Geometric_Deep_Learning_CVPR_2019_paper.html)
- A02 - [ABC dataset project](https://deep-geometry.github.io/abc-dataset/)
- A03 - [Fusion 360 Gallery Dataset](https://www.research.autodesk.com/publications/fusion-360-gallery/)
- A04 - [Fusion 360 Gallery code/data](https://github.com/AutodeskAILab/Fusion360GalleryDataset)
- A05 - [SketchGraphs](https://arxiv.org/abs/2007.08506)
- A06 - [DeepCAD, ICCV 2021](https://openaccess.thecvf.com/content/ICCV2021/papers/Wu_DeepCAD_A_Deep_Generative_Network_for_Computer-Aided_Design_Models_ICCV_2021_paper.pdf)
- A07 - [DeepCAD code](https://github.com/rundiwu/DeepCAD)
- A08 - [Vitruvion](https://arxiv.org/abs/2109.14124)
- A09 - [BRepNet](https://arxiv.org/abs/2104.00706)
- A10 - [SolidGen](https://arxiv.org/abs/2203.13944)
- A11 - [SECAD-Net, CVPR 2023](https://openaccess.thecvf.com/content/CVPR2023/papers/Li_SECAD-Net_Self-Supervised_CAD_Reconstruction_by_Learning_Sketch-Extrude_Operations_CVPR_2023_paper.pdf)
- A12 - [Point2CAD, CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/papers/Liu_Point2CAD_Reverse_Engineering_CAD_Models_from_3D_Point_Clouds_CVPR_2024_paper.pdf)
- A13 - [CAD-SIGNet, CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/html/Khan_CAD-SIGNet_CAD_Language_Inference_from_Point_Clouds_using_Layer-wise_Sketch_CVPR_2024_paper.html)
- A14 - [SfmCAD, CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/papers/Li_SfmCAD_Unsupervised_CAD_Reconstruction_by_Learning_Sketch-based_Feature_Modeling_Operations_CVPR_2024_paper.pdf)
- A15 - [Draw Step by Step, CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/papers/Ma_Draw_Step_by_Step_Reconstructing_CAD_Construction_Sequences_from_Point_CVPR_2024_paper.pdf)
- A16 - [TransCAD, ECCV 2024](https://arxiv.org/abs/2407.12702)
- A17 - [PICASSO, WACV 2025](https://openaccess.thecvf.com/content/WACV2025/papers/Karadeniz_PICASSO_A_Feed-Forward_Framework_for_Parametric_Inference_of_CAD_Sketches_WACV_2025_paper.pdf)
- A18 - [CAD-Recode, ICCV 2025](https://openaccess.thecvf.com/content/ICCV2025/papers/Rukhovich_CAD-Recode_Reverse_Engineering_CAD_Code_from_Point_Clouds_ICCV_2025_paper.pdf)
- A19 - [CAD-Recode project](https://cad-recode.github.io/)
- A20 - [CAD-Recode code](https://github.com/filaPro/cad-recode)
- A21 - [CADCrafter, CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/papers/Chen_CADCrafter_Generating_Computer-Aided_Design_Models_from_Unconstrained_Images_CVPR_2025_paper.pdf)
- A22 - [DTGBrepGen, CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/papers/Li_DTGBrepGen_A_Novel_B-rep_Generative_Model_through_Decoupling_Topology_and_CVPR_2025_paper.pdf)
- A23 - [CAD-Assistant, ICCV 2025](https://openaccess.thecvf.com/content/ICCV2025/papers/Mallis_CAD-Assistant_Tool-Augmented_VLLMs_as_Generic_CAD_Task_Solvers_ICCV_2025_paper.pdf)
- A24 - [Cadrille](https://arxiv.org/html/2505.22914v3)
- A25 - [Cadrille code](https://github.com/col14m/cadrille)
- A26 - [CADFS, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/html/Pyatov_CADFS_A_Big_CAD_Program_Dataset_and_Framework_for_Computer-Aided_CVPR_2026_paper.html)
- A27 - [CADFS project](https://voyleg.github.io/cadfs/)
- A28 - [Pointer-CAD, CVPR 2026](https://arxiv.org/abs/2603.04337)
- A29 - [Pointer-CAD v2](https://arxiv.org/abs/2606.29301)
- A30 - [BenchCAD](https://arxiv.org/html/2605.10865v1)
- A31 - [BenchCAD project](https://benchcad.github.io/BenchCAD_webpage/)
- A32 - [BrepGaussian, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/papers/Yu_BrepGaussian_CAD_reconstruction_from_Multi-View_Images_with_Gaussian_Splatting_CVPR_2026_paper.pdf)
- A33 - [HiFi-BRep, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/papers/Hou_HiFi-BRep_High-Fidelity_Latent_Representation_for_Robust_B-Rep_Generation_CVPR_2026_paper.pdf)
- A34 - [BrepVGAE, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/papers/Guo_BrepVGAE_Variational_Graph_Autoencoder_with_Unified_Latent_Representation_for_B-rep_CVPR_2026_paper.pdf)
- A35 - [FoV-Net, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/papers/Ballegeer_FoV-Net_Rotation-Invariant_CAD_B-rep_Learning_via_Field-of-View_Ray_Casting_CVPR_2026_paper.pdf)
- A36 - [CAD-Refiner, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/papers/Yuan_CAD-Refiner_A_Unified_Framework_for_CAD_Generation_and_Iterative_Editing_CVPR_2026_paper.pdf)
- A37 - [CADFit](https://arxiv.org/html/2605.01171v1)
- A38 - [CADReasoner](https://arxiv.org/html/2603.29847v1)
- A39 - [FutureCAD](https://arxiv.org/html/2603.11831v2)
- A40 - [Geometric Deep Learning for CAD - survey](https://arxiv.org/abs/2402.17695)
- A41 - [Survey on Deep Learning in 3D CAD Reconstruction](https://www.mdpi.com/2076-3417/15/12/6681)
- A42 - [Autodesk Project Bernini](https://www.research.autodesk.com/projects/project-bernini/)
- A43 - [Siemens AI-enabled Designcenter](https://www.siemens.com/en-us/products/designcenter/cad-software/ai/)

## Compilateurs, IA et GPU

- G01 - [LLVM Getting Started](https://llvm.org/docs/GettingStarted.html)
- G02 - [LLVM Developer Policy and licence](https://llvm.org/docs/DeveloperPolicy.html)
- G03 - [MLIR overview](https://mlir.llvm.org/)
- G04 - [MLIR dialects](https://mlir.llvm.org/docs/Dialects/)
- G05 - [MLIR dialect conversion](https://mlir.llvm.org/docs/DialectConversion/)
- G06 - [MLIR GPU dialect](https://mlir.llvm.org/docs/Dialects/GPU/)
- G07 - [StableHLO specification](https://openxla.org/stablehlo/spec)
- G08 - [ONNX](https://github.com/onnx/onnx)
- G09 - [ONNX Runtime](https://onnxruntime.ai/docs/)
- G10 - [Apache TVM](https://tvm.apache.org/)
- G11 - [Triton](https://triton-lang.org/)
- G12 - [CUDA Programming Guide](https://docs.nvidia.com/cuda/cuda-programming-guide/index.html)
- G13 - [NVIDIA Warp](https://github.com/NVIDIA/warp)
- G14 - [NVIDIA Kaolin](https://github.com/NVIDIAGameWorks/kaolin)
- G15 - [PyTorch3D](https://pytorch3d.org/)
- G16 - [nvdiffrast](https://github.com/NVlabs/nvdiffrast)
- G17 - [NVIDIA OptiX](https://developer.nvidia.com/rtx/ray-tracing/optix)
- G18 - [OpenVDB](https://www.openvdb.org/)
- G19 - [Dyndrite Engine](https://www.dyndrite.com/technology/engine)
- G20 - [NVIDIA SMLib documentation](https://docs.nvidia.com/smlib/manual/smlib/introduction/index.html)
- G21 - [Krishnamurthy - Parallel GPU Algorithms for Mechanical CAD](https://escholarship.org/uc/item/59n1g12w)
- G22 - [GPU matrix-based B-spline computation, 2025](https://arxiv.org/abs/2504.11498)

## Interopérabilité, qualité, topological naming et thèses

- T01 - [NISTIR 7433 - Data Exchange of Parametric CAD Models Using ISO 10303-108](https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nistir7433.pdf)
- T02 - [Rappoport - An Architecture for Universal CAD Data Exchange](https://dl.acm.org/doi/10.1145/781606.781648)
- T03 - [Altidor et al. - A Programming Language Approach to Parametric CAD Data Exchange](https://doi.org/10.1115/DETC2011-48530)
- T04 - [Safdar et al. - Feature-based translation with macro-parametric approach](https://academic.oup.com/jcde/article/7/5/603/5818508)
- T05 - [González-Lluch et al. - CAD model quality taxonomy](https://arxiv.org/pdf/1611.01765)
- T06 - [Capoyleas, Chen, Hoffmann - Generic naming in generative CAD](https://www.cs.purdue.edu/cgvlab/www/resources/papers/Capoyleas-Computer_aided_design-1996-Generic_naming_in_generative.pdf)
- T07 - [Cardot et al. - Persistent naming](https://www.cad-journal.net/files/vol_16/CAD_16%285%29_2019_985-1002.pdf)
- T08 - [Freeman - Neutral Parametric Canonical Form, thèse 2015](https://scholarsarchive.byu.edu/etd/5688/)
- T09 - [Staves - Associative References in a Neutral Parametric CAD File, thèse 2016](https://scholarsarchive.byu.edu/etd/6222/)
- T10 - [Staves et al. - Associative references, CAD Journal 2017](https://www.cad-journal.net/files/vol_14/CAD_14%284%29_2017_408-421.pdf)
- T11 - [Dupont - Design Intent Aware CAD Reverse Engineering, thèse 2025](https://orbilu.uni.lu/bitstream/10993/65389/1/Thesis_EDupont.pdf)
- T12 - [Zhang - Machine learning-based 3D parametric CAD models, thèse 2025](https://pastel.hal.science/tel-05448751)
- T13 - [Gonzalez Avila - Facilitating Programming-based CAD, thèse 2024](https://hal.science/tel-04740935v1/file/PhD-JohannFelipeGonzalezAvila.pdf)
- T14 - [Boussuge - Idéalisation d’assemblages CAO, thèse 2014](https://theses.hal.science/tel-01071560v1/file/pdf2star-1412240431-40261_BOUSSUGE_2014_diffusion.pdf)
- T15 - [Li - Analyse de forme appliquée aux B-rep, thèse 2011](https://theses.hal.science/tel-00849146/file/Like_thesis_06_12_2011.pdf)
- T16 - [Borja-Ramirez - Redesign supported by data models, thèse](https://repository.lboro.ac.uk/articles/thesis/Redesign_supported_by_data_models_with_particular_reference_to_reverse_engineering/9454523)
- T17 - [Oubari - Deep generative models for industrial multi-component design, thèse 2026](https://theses.hal.science/tel-05702038v1/file/153219_OUBARI_2026_archivage.pdf)

## Brevets représentatifs

- P01 - [US7492364B2 - 2D drawings to feature-based model](https://patents.google.com/patent/US7492364B2/en)
- P02 - [US8346020B2 - Automated 3D model from multiple 2D CAD drawings](https://patents.google.com/patent/US8346020B2/en)
- P03 - [US11514214B2 - Dataset for inference of solid CAD features](https://patents.google.com/patent/US11514214B2/en)
- P04 - [US11922573B2 - Neural network for inference of solid CAD features](https://patents.google.com/patent/US11922573B2/en)
- P05 - [US11869147B2 - Neural network outputting a parameterized 3D model](https://patents.google.com/patent/US11869147B2/en)
- P06 - [US12002157B2 - VAE outputting a 3D model](https://patents.google.com/patent/US12002157B2/en)
- P07 - [US20230410452A1 - Inferring 3D geometry onto a 2D sketch](https://patents.google.com/patent/US20230410452A1/en)
- P08 - [EP4071658A1 - UV-Net representations of CAD objects](https://patents.google.com/patent/EP4071658A1/en)
- P09 - [US12265764B2 - AI-generated multi-component CAD assembly](https://patents.google.com/patent/US12265764B2/en)
- P10 - [US20250200232A1 - CAD exchange using implicit functions as code](https://patents.google.com/patent/US20250200232A1/en)
- P11 - [US20160246899A1 - Multi-user cloud parametric feature-based CAD](https://patents.google.com/patent/US20160246899A1/en)
- P12 - [US20190147317A1 - Automatic assembly mate learning](https://patents.google.com/patent/US20190147317A1/en)
- P13 - [US10499031B2 - Depth map to parameterized 3D model](https://patents.google.com/patent/US10499031B2/en)
- P14 - [US10943037B2 - CAD model from a finite element mesh](https://patents.google.com/patent/US10943037B2/en)
- P15 - [US5537519 - Boundary representation to CSG](https://patents.google.com/patent/US5537519/en)

## Traçabilité de la revue

La bibliographie rassemble plus de 150 documents et pages primaires, dont 45 sources normatives/consortiums, 57 sources éditeurs ou open source, 43 travaux/datasets IA, 22 sources compilateur/GPU, 17 publications/thèses d’interopérabilité et 15 familles de brevets. Les URLs ont été vérifiées pendant l’étude ; leur disponibilité future dépend des organismes éditeurs.
