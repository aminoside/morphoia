# Interopérabilité, import et export

## 1. Principe

MORPHOIA ne promet pas un round-trip universel. Chaque frontière produit un **Loss Register** dont les états sont :

- `lossless` : sémantique du profil conservée ;
- `lossy_declared` : information transformée ou abandonnée ;
- `fallback_geometry` : procédure perdue, résultat explicite conservé ;
- `reconstructed_hypothesis` : historique inféré, non certain ;
- `unsupported` : refus explicite.

Les importeurs ne créent jamais un historique certain à partir d'une B-rep ou d'un mesh. Ils créent un corps importé et, séparément, zéro ou plusieurs graphes candidats avec preuves.

## 2. STEP

### STEP AP203

| Aspect | Analyse |
|---|---|
| Avantages | Très diffusé, configuration contrôlée, géométrie exacte, assemblages de base |
| Limites | PMI et MBD modernes limités, pas d'historique paramétrique portable complet |
| Import | Géométrie, produit et assemblage ; source marquée héritée |
| Export | Possible pour clients legacy, avec perte déclarée de PMI/features hors sous-ensemble |
| Rôle | Compatibilité descendante, jamais format MORPHOIA principal |

### STEP AP214

| Aspect | Analyse |
|---|---|
| Avantages | Couleurs, couches, contexte automobile, large base installée |
| Limites | Remplacé fonctionnellement par AP242, sémantique procédurale insuffisante seule |
| Import/export | Comme AP203, avec conservation des présentations supportées |
| Rôle | Legacy automobile et migration vers AP242 |

### STEP AP242

| Aspect | Analyse |
|---|---|
| Avantages | Produit, configuration, géométrie exacte, PMI/GD&T, assemblages, validation properties |
| Limites | Ressources procédurales peu implémentées de bout en bout, performance Part 21 et profils variables |
| Import | Autorité mécanique neutre ; procédure seulement si réellement présente et qualifiée |
| Export | Cible principale, avec propriété de validation et liens vers le graphe |
| Rôle | Contrat d'échange et d'archivage ouvert |

### ISO 10303-55/-108/-109/-111/-112/-113

Ces ressources ancrent le graphe procédural, les paramètres, contraintes, assemblages, solides, esquisses et features. MORPHOIA doit produire un mapping conceptuel puis un mapping EXPRESS vérifié contre les schémas officiels. Une nouvelle entité n'est admise que pour un écart documenté.

## 3. Formats géométriques historiques

### IGES

IGES reste utile pour courbes, surfaces et archives. Il transporte mal topologie moderne, PMI associatif, configuration et historique. L'import réalise sewing/healing déclaré et marque les incertitudes d'unité ou d'orientation. L'export est un mode legacy avec pertes importantes.

### BREP

`B-rep` désigne une famille de représentations, pas un format universel unique. Un fichier BREP OCCT peut préserver une géométrie exacte pour le backend OCCT, mais ne porte pas l'intention complète. Il sert de snapshot ou cache adressé par hash, jamais de source unique du modèle.

### Parasolid XT

| Aspect | Analyse |
|---|---|
| Avantages | B-rep industrielle robuste, écosystème NX/SolidWorks/Onshape et nombreux traducteurs |
| Limites | Spécification et noyau propriétaires, licence OEM, pas d'historique universel |
| Import/export | Adaptateur sous licence ; géométrie et attributs, features seulement via API hôte dédiée |
| Compilateur | Backend optionnel et oracle différentiel, jamais dépendance de lecture du standard |

### ACIS SAT/SAB

| Aspect | Analyse |
|---|---|
| Avantages | B-rep industrielle, format SAT lisible dans certaines versions, large historique |
| Limites | Sémantique et noyau propriétaires, variantes de version, pas d'intention complète |
| Import/export | SDK/licence ou support de traducteur ; registre de version et pertes |
| Compilateur | Backend géométrique optionnel |

## 4. Noyaux et programmabilité ouverte

### Open CASCADE Technology

OCCT est le backend ouvert de référence : B-rep, courbes/surfaces, booléens, fillets, healing, tessellation, OCAF, XDE et STEP. L'adaptateur reçoit le graphe canonique et rend handles, lignées, diagnostics et propriétés. Les classes OCCT ne traversent pas l'API normative.

La compilation inverse d'une TopoDS_Shape produit un `ImportedBody` et des candidats de features ; elle ne reconstitue pas un historique certain.

### FreeCAD

FreeCAD sert de banc d'intégration ouvert, d'oracle de recompute et de cible utilisateur. L'export peut créer un document, des paramètres, Sketcher, PartDesign et liens vers IDs MORPHOIA. Les divergences de comportement sont enregistrées.

L'import d'un document FreeCAD peut récupérer davantage d'historique qu'un STEP, mais les objets Python, workbenches et plugins non reconnus sont isolés ou marqués `unsupported`.

### CadQuery

CadQuery est un frontend et une cible de prototypage OCCT. Un export MORPHOIA vers CadQuery peut générer du Python lisible, mais ce code n'est pas l'autorité et peut perdre PMI, transactions et contrats de référence. Un import repose sur analyse statique limitée ou exécution sandboxée ; Python arbitraire interdit la garantie générale.

### OpenSCAD

OpenSCAD offre CSG et paramétrage lisible. Export pertinent pour formes CSG simples et fabrication maker. Les fillets, B-rep exacte, PMI et sketch constraints sont limités. L'import produit un arbre CSG lorsque possible, sinon un mesh et une perte.

### FeatureScript

FeatureScript constitue une référence pour unités, features, version de contexte et requêtes topologiques. La génération vers Onshape passe par ses API et reste soumise au runtime cloud. L'import de code ne peut être universel car la bibliothèque et le contexte Onshape font partie de la sémantique.

## 5. CAO commerciales

### Fusion 360

- Avantages : historique paramétrique, API, cloud, vaste base utilisateur et données de recherche Autodesk.
- Import : API autorisée, STEP ou formats natifs via SDK ; historique selon exposition de l'API.
- Export : création de sketches/features lorsque le mapping est exact, sinon STEP/B-rep et Loss Register.
- Limite : versions, état de timeline et comportements implicites.

### SolidWorks

- Avantages : CAO mécanique mature, API COM/.NET, large parc et noyau Parasolid.
- Import : document natif via API/SDK autorisé ; équations, configurations et features selon version.
- Export : macro/add-in ou fichier natif, avec tests de rebuild et propriétés.
- Limite : Windows, licences, références et features propriétaires.

### CATIA

- Avantages : assemblages, surfacique, MBD, industrie aéronautique/automobile.
- Import/export : API CAA/Automation et traducteurs licenciés ; mapping par version et atelier.
- Limite : richesse propriétaire, CGM, coûts et matrice de configurations.
- Rôle : cible et oracle, jamais coeur.

### Creo

- Avantages : paramétrique historique, relations, family tables, MBD.
- Import/export : Creo TOOLKIT/J-Link ou SDK de traduction, avec régénération contrôlée.
- Limite : intent manager, IDs et features dépendants de version.

### Siemens NX

- Avantages : Parasolid, NX Open, PMI et manufacturing intégrés.
- Import/export : NX Open et formats JT/STEP/XT ; possibilité de créer features natives bornées.
- Limite : sémantique NX et options de model update non portables.

### Autodesk Inventor

- Avantages : API riche, mécanique et paramètres, intégration Autodesk.
- Import/export : add-in/API sur versions qualifiées, STEP et SAT en fallback.
- Limite : Windows, ShapeManager/ACIS dérivé, features propriétaires.

### Rhino et Grasshopper

- Avantages : NURBS, surfaces libres, openNURBS partiel et graphe computationnel Grasshopper.
- Import : 3DM, objets et, si autorisé, définition Grasshopper.
- Export : géométrie NURBS, paramètres et composants spécialisés ; PMI mécanique limité.
- Rôle : surface/design computationnel et P4, non profil P1 autoritatif.

## 6. DCC et formats de scène

### Blender

Blender est une cible de rendu, de données synthétiques, de visualisation et d'annotation. Son modèle mesh/SubD et ses modifiers ne remplacent pas une B-rep mécanique. L'export passe par glTF, USD ou un worker Blender isolé. Les obligations GPL sont vérifiées par architecture de processus et revue juridique.

### glTF

glTF est excellent pour web, GPU et livraison légère. MORPHOIA exporte mesh, matériaux visuels, hiérarchie et IDs de liaison. Un glTF ne transporte pas l'historique paramétrique, la B-rep ni le PMI sémantique complet. L'import est une source de reconstruction.

### USD et OpenUSD

OpenUSD apporte composition, layers, variants, grandes scènes et collaboration DCC. MORPHOIA peut définir un schéma dérivé reliant prims et IDs canoniques, sans représenter USD comme autorité de conception. Variants USD et configurations mécaniques ne sont pas automatiquement équivalents.

### Siemens JT

JT convient aux grands assemblages, LOD, DMU, PMI et visualisation. L'export garde liens produit/occurrence et identifiants. La création ou lecture complète peut nécessiter un toolkit commercial. JT reste une vue légère et une frontière d'échange, pas l'historique de construction.

## 7. BIM et IFC

IFC est une norme ouverte et mature pour le BIM. Ses objets, relations, property sets et Model View Definitions inspirent gouvernance et profils. Les éléments de bâtiment et la géométrie IFC ne doivent pas être réinterprétés comme features mécaniques générales. Une extension domaine architecture peut mapper vers IFC, séparée des profils P1-P4.

## 8. Meshes et captures

| Format | Import | Export | Limites |
|---|---|---|---|
| STL | Triangle soup avec unité souvent externe | Fabrication/additif | Pas de topologie sémantique, couleur/PMI faibles |
| OBJ | Mesh, groupes, UV et matériaux | DCC/visualisation | Pas d'intention mécanique |
| PLY | Points/mesh et attributs | Scan/recherche | Pas d'historique ni PMI |
| Nuage de points | Preuves et incertitude capteur | Diagnostic | Reconstruction sous-déterminée |

Ces formats alimentent segmentation, primitive fitting et hypothèses. La conversion directe en historique certain est interdite.

## 9. Fabrication et qualité

AP238/STEP-NC et ISO 14649 portent workingsteps et fabrication. QIF porte qualité, inspection et résultats métrologiques. MORPHOIA les relie aux mêmes IDs produit, datums et caractéristiques sans dupliquer leur ontologie.

## 10. SDK de traduction

HOOPS Exchange, 3D InterOp, CAD Exchanger et Datakit offrent une couverture native et PMI plus large que les bibliothèques ouvertes. Ils sont évalués comme adaptateurs licenciés. Leurs objets restent derrière une ABI de plugin et leur indisponibilité ne doit pas empêcher la lecture du graphe ou du snapshot neutre.

## 11. Compilateurs directs

| Cible | Stratégie 0.x | Autorité |
|---|---|---|
| Graphe JSON | Lossless pour le modèle abstrait supporté | Encodage de test |
| OCCT | Exécution P1 puis P2 | Backend de référence |
| STEP AP242 | Mapping + B-rep + PMI + propriétés | Echange neutre principal |
| FreeCAD | Document et recompute | Oracle/cible ouverte |
| Parasolid | Plugin sous licence | Oracle commercial optionnel |
| Blender | Mesh, scène et annotations | Vue dérivée |
| glTF | Mesh/LOD/IDs | Vue web dérivée |

## 12. Compilateurs inverses

| Source | Résultat certain | Résultat hypothétique |
|---|---|---|
| MORPHOIA | Graphe, IDs et profils reconnus | Extension inconnue préservée |
| STEP procédural qualifié | Sous-ensemble mappé | Opérations non reconnues |
| STEP B-rep | Produit, géométrie, PMI présents | Historique et intention |
| Fichier natif via API | Données exposées et versionnées | Etat implicite ou feature non mappée |
| Mesh/scan/images | Observations et preuves | Toutes les features et dimensions non explicites |
| Texte/voix | Commandes et intentions linguistiques | Paramètres absents et choix géométriques |

## 13. Matrice de qualification

Chaque adaptateur publie :

```text
backend x version x plateforme x profil x operation x PMI x configuration
```

Une cellule contient `lossless`, `lossy_declared`, `fallback_geometry`, `unsupported` et le taux de réussite du corpus. Le terme compatible est interdit sans profil et version.
