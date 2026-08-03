# Catalogue d'opérations candidate

## 1. Règles communes

Chaque opération possède :

- un nom qualifié et une version ;
- un profil minimal ;
- des arguments typés et nommés ;
- des préconditions ;
- des résultats immuables ;
- des rôles topologiques de sortie ;
- des cas d'échec explicites ;
- un mapping STEP conceptuel ;
- un fallback et un registre des pertes ;
- des scénarios d'édition obligatoires.

Aucun défaut influençant la géométrie ne dépend silencieusement du backend. Les noms exacts des entités EXPRESS ne seront figés qu'après analyse des schémas officiels SMRL.

## 2. Esquisses, contraintes et dimensions

### Sketch

| Champ | Contrat |
|---|---|
| Entrées | Plan ou frame2 explicite, unités, entités, contraintes, politique solveur |
| Sorties | Esquisse, régions fermées, état de contrainte, diagnostics |
| Profil | P1 |
| Invariants | Repère explicite, aucune Workplane implicite, branches du solveur enregistrées |
| Réemploi | ISO 10303-112, FreeCAD Sketcher ou SolveSpace |

### Constraint

Le profil initial couvre coïncidence, horizontalité, verticalité, parallélisme, perpendicularité, tangence, concentricité, égalité, symétrie, distance, angle, rayon, diamètre, point-sur-courbe et fixité explicite.

Les contraintes industrielles sont dures. Les poids probabilistes appartiennent au générateur IA et ne sont pas conservés comme règles autoritatives.

### Dimension

Une dimension relie une cible, une quantité typée, un mode `driving` ou `reference`, une provenance et, en P2, une tolérance dimensionnelle. Une dimension explicitement observée doit être exacte ou provoquer abstention.

## 3. Features volumiques P1

### Extrude

| Champ | Contrat |
|---|---|
| Entrées | Région2, direction, limite initiale, limite finale, dépouille explicite |
| Sorties | Solide ou surface, rôles `cap.start`, `cap.end`, `lateral` |
| Echecs | Profil ouvert, auto-intersection, direction nulle, résultat non-manifold |
| Edition | Distance, sens, symétrie, région et dépouille |
| Mapping | ISO 10303-111/-113, géométrie résultat ISO 10303-42 |

### Cut

`cut` est un booléen soustractif spécialisé qui conserve l'intention de poche ou d'enlèvement. Il exige cible, outil, politique d'intersection et comportement si l'outil n'intersecte pas la cible.

### Revolve

Entrées : région, axe, angle, sens, limite et politique de fermeture. Les cas où le profil croise l'axe, crée une auto-intersection ou produit une feuille nulle doivent être définis par le profil et non par un défaut backend.

### Boolean

Opérations `union`, `subtract` et `intersect`. La cible primaire et les outils sont ordonnés, car la lignée topologique et la robustesse numérique peuvent dépendre de l'ordre même si la théorie ensembliste paraît commutative.

Le backend rapporte : succès exact, succès avec healing déclaré, résultat vide, non-manifold, tolérance dépassée ou divergence.

### Hole

| Paramètre | Valeurs minimales |
|---|---|
| Support | Plan, face ou datum résolu de manière unique |
| Placement | Point2 ou motif de points dans un repère explicite |
| Axe | Direction ou référence d'axe |
| Forme | Simple, counterbore, countersink, spotface |
| Terminaison | Blind, through_all, up_to_face, up_to_next |
| Filetage | None, cosmetic, semantic ou modeled |
| Sorties | `hole.wall`, `hole.bottom`, `entry`, axe sémantique |

### Pattern

Le motif réexécute ou transforme une seed selon une politique explicite. Les variantes linéaire, circulaire et table finie sont P1. Chaque instance possède une clé stable ; l'identité ne dépend pas seulement de sa position dans une liste.

Le comportement en cas de collision, suppression d'une instance, fusion de résultats et références externes doit être déclaré.

### Mirror

Entrées : seed, plan ou frame, politique de copie ou de fusion. Le miroir doit déclarer le traitement de la chiralité, des repères locaux et des PMI associés.

### Fillet

P1 couvre rayon constant et continuité G1. Les arêtes sont des références persistantes. Les débordements, coins, tangences, rayons impossibles et propagation tangentielle sont explicites. Les lois variables relèvent de P4.

### Chamfer

Modes : deux distances, distance-angle ou symétrique. La face de référence, le sens et le comportement aux sommets sont explicites.

## 4. Géométrie avancée P4

### Sweep

Entrées : profil, chemin, frame d'orientation, lois d'échelle/torsion, continuité, coins et politique d'auto-intersection. Les variantes Frenet, corrected Frenet et direction fixe ne sont pas interchangeables.

### Loft

Entrées : sections ordonnées, guides, correspondance des sommets, continuité et conditions aux extrémités. La résolution automatique de correspondance doit être enregistrée comme décision ou refusée.

### Blend

`blend` désigne une surface de transition entre frontières ou surfaces avec continuité G0/G1/G2. Il ne doit pas être confondu avec la feature d'arrondi d'arêtes `fillet`.

### Shell

Entrées : corps, faces retirées, épaisseur, côté, stratégie de coins. Les changements topologiques, auto-intersections et zones d'épaisseur nulle sont des erreurs ou pertes déclarées.

### Draft

Entrées : faces, direction de tirage, élément neutre, angle et traitement des faces tangentes. Un draft automatique propre à une CAO n'est pas portable sans contrat supplémentaire.

## 5. Références et construction

### Datum

Datums de point, axe, plan et cible. En P2, la sémantique GD&T distingue le datum théorique, le datum feature et le datum simulé.

### Coordinate System

Origine, axes, chiralité et unités. Les axes doivent être orthogonaux et normalisés dans la tolérance noyau. La forme canonique n'utilise pas d'angles d'Euler ambigus.

### Reference Plane

Créé à partir d'un datum, d'un frame, d'une face plane ou d'un offset explicite. L'orientation et le sens normal sont obligatoires.

### Reference Axis

Créé à partir d'une ligne, d'une face cylindrique, de deux points ou d'un repère. La référence source reste persistante et doit être unique.

## 6. P2 - matériau, tolérances et PMI

### Material

Le matériau référence désignation, norme, version, propriétés, température, source et incertitude. MORPHOIA ne crée pas une nouvelle base matériaux ; il relie des identifiants externes et conserve les valeurs nécessaires à la validation.

### Thread

Le filetage déclare standard, désignation, diamètre, pas, classe, sens, longueur et représentation `semantic`, `cosmetic` ou `modeled`. Un export qui remplace un filetage modélisé par une annotation produit une perte explicite.

### Tolerance

`kernel_tolerance`, `measurement_uncertainty`, `dimensional_tolerance` et `gdt_zone` sont quatre types distincts. La cible, l'unité, la distribution ou zone et la provenance sont obligatoires selon le type.

### PMI

Le PMI porte sémantique et association exacte. P2 couvre dimensions, datums, tolérances de forme/orientation/localisation bornées, état de surface et notes structurées. La présentation graphique est optionnelle et dérivée.

Le glyphe seul n'est jamais considéré comme tolérance sémantique.

## 7. P3 - Assembly

Un assemblage distingue :

- définition produit ;
- occurrence ;
- transformation rigide ;
- mate/contrainte ;
- configuration ;
- substitution ;
- BOM ;
- enveloppe et interférence.

Le profil initial couvre occurrences rigides, coïncidence, concentricité, distance, angle, fixité et cinématique simple. Flexibilité, déformation, câblage et grands mécanismes nécessitent des extensions ultérieures.

## 8. Mécanisme d'ajout d'opérations

Une opération d'extension doit fournir :

1. URI, version et digest ;
2. types d'entrée et de sortie ;
3. préconditions et postconditions ;
4. rôles topologiques ;
5. déterminisme et limites ;
6. mapping STEP ou écart ;
7. fallback B-rep ;
8. registre des pertes par backend ;
9. cas dégénérés ;
10. scénarios d'édition ;
11. suite golden et adversariale ;
12. Component Justification Record.

Une opération inconnue peut être préservée dans le graphe. Elle ne peut pas être exécutée sans implémentation et manifest validés.

## 9. Matrice de réemploi

| Domaine | Réemploi obligatoire ou prioritaire |
|---|---|
| Procédures | ISO 10303-55 |
| Paramètres/contraintes | ISO 10303-108 |
| Assemblages | ISO 10303-109 et AP242 |
| Solides procéduraux | ISO 10303-111 |
| Esquisses | ISO 10303-112 |
| Features mécaniques | ISO 10303-113 |
| Géométrie et topologie | ISO 10303-42 |
| Produit, configuration, PMI | AP242 |
| Noyau | OCCT, backends commerciaux optionnels |
| Solveur | FreeCAD Sketcher, SolveSpace ou D-Cubed |

Cette matrice interdit de déclarer une opération nouvelle simplement parce qu'une API existante est moins agréable. L'écart sémantique doit être démontré.
