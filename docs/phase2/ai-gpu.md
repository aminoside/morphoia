# Intelligence artificielle et accélération GPU

## 1. Principe de sûreté

L'IA ne construit pas directement l'état autoritatif. Elle produit des observations, des candidats, une confiance et des preuves. Le runtime déterministe décide si un candidat est valide. Une ambiguïté matérielle entraîne abstention ou revue humaine.

```text
Entree -> extraction -> candidats -> compilation -> execution -> validation
                       |                              |
                       +---- preuves et confiance ----+
```

Une cote explicitement lisible doit être exacte ou rejetée. Une dimension absente ne peut jamais être remplie comme vérité sans règle ou décision.

## 2. Architectures comparées

| Architecture | Forces | Faiblesses | Rôle MORPHOIA |
|---|---|---|---|
| CNN | Localité, coût maîtrisé, OCR/segmentation | Contexte global limité | Détection de traits, symboles, vues, défauts |
| Vision Transformer | Contexte global et multimodalité | Besoin de données, coût quadratique ou approximations | Plans, photos, vidéos, association cote-entité |
| Transformer autoregressif | Génération séquentielle, texte/code | Erreurs cumulatives, hallucinations, ordre arbitraire | Proposer une source `.morph` sous grammaire contrainte |
| Diffusion | Diversité de candidats et formes | Validation exacte difficile, latence | Hypothèses de géométrie/structure, jamais autorité |
| GNN | Topologie, adjacence, contraintes, B-rep | Construction du graphe et scaling | Encodage B-rep, DAG, matching d'entités |
| Modèle multimodal | Fusion image, texte, points et CAO | Alignement, données rares, calibration | Architecture cible de reconstruction |
| Agent | Appels d'outils, itération avec validateur | Boucles coûteuses, erreurs d'outil | Orchestration bornée et auditable |
| JEPA/world model | Représentation prédictive sans pixel-level exhaustif | Applications CAO encore exploratoires | Préentraînement de vues/états et cohérence multi-vues |

La meilleure architecture n'est probablement pas un modèle unique. Un système composite sépare perception, génération de graphe, exécution et classement.

## 3. Pipeline multimodal

### 3.1 Dessins industriels et vues orthographiques

1. rectification, débruitage et segmentation des vues ;
2. OCR du cartouche, des cotes et notes ;
3. détection des traits, axes, hachures, coupes et symboles ;
4. association cote-entité avec graphe biparti ;
5. cohérence entre vues et génération de primitives 3D candidates ;
6. recherche de séquences P1 compatibles ;
7. génération contrainte de plusieurs graphes ;
8. exécution et comparaison aux vues ;
9. abstention si l'inversion reste multiple.

Les vues en coupe et auxiliaires ajoutent des frames explicites. Les annotations ISO et PMI deviennent preuves structurées, pas texte décoratif.

### 3.2 Croquis manuscrits

La pipeline estime traits, jonctions, symboles et incertitude. Les proportions ne sont pas interprétées comme cotes. Les valeurs textuelles ou décisions utilisateur pilotent la géométrie.

### 3.3 Photographies et vidéo

Calibration, pose, silhouettes, profondeur multi-vues, NeRF/3DGS ou reconstruction dense produisent un champ de preuves. L'échelle doit venir d'une référence connue. La vidéo aide l'occlusion et la multi-vue, mais ne révèle pas les cavités invisibles ni l'intention.

### 3.4 Scans et nuages de points

Nettoyage, normales, segmentation, fitting de primitives, symétries et courbes d'intersection produisent surfaces candidates. L'incertitude capteur est conservée séparément des tolérances de conception.

### 3.5 STL, OBJ, PLY et meshes

Le mesh fournit forme et parfois groupes/matériaux. Une GNN ou un encodeur mesh propose faces fonctionnelles, primitives et ordre de features. La B-rep et l'historique restent des hypothèses validées par écart géométrique et scénarios.

### 3.6 STEP, IGES, Parasolid et ACIS

La géométrie exacte réduit l'incertitude de forme. Des encodeurs B-rep, signatures et recherche de motifs proposent l'intention. Les formats natifs peuvent révéler davantage via API autorisée, mais leur sémantique reste versionnée.

### 3.7 Texte et voix

La voix est transcrite avec horodatage et confiance. Un LLM transforme la commande en patch de graphe, affiche le diff, compile et demande confirmation pour toute valeur ou référence ambiguë. Le modèle ne reçoit pas de pouvoir d'I/O arbitraire.

## 4. Génération contrainte

Trois stratégies sont comparées :

1. **Token grammar constrained decoding** : le décodeur ne peut produire qu'un token syntaxiquement valide. Simple et immédiatement testable.
2. **AST/graph generation** : le modèle génère des noeuds typés et des arêtes. Meilleur contrôle sémantique, entraînement plus complexe.
3. **Tool-using agent** : le modèle ajoute ou corrige un noeud après diagnostics. Utile pour raffinement, mais borné en nombre d'étapes.

Le choix initial combine 1 et 3. Le graphe généré passe ensuite par types, unités, DAG, backend et scénarios.

## 5. Objectifs d'apprentissage

Le score ne se limite pas à Chamfer ou IoU. Une fonction multi-objectif peut inclure :

- validité syntaxique ;
- validité du graphe ;
- satisfaction des cotes et contraintes ;
- validité B-rep ;
- propriétés de masse ;
- distance géométrique ;
- stabilité des références ;
- scénarios d'édition ;
- conservation PMI ;
- nombre de pertes ;
- coût de correction humaine ;
- calibration et abstention.

Les contraintes dures ne deviennent pas une simple pénalité molle : un candidat non conforme est rejeté.

## 6. Données nécessaires

### 6.1 Unité de donnée

Une unité idéale contient :

- sources originales ;
- graphe de construction et versions ;
- B-rep/snapshots ;
- paramètres et contraintes ;
- PMI et matériaux ;
- assemblages/configurations si profil ;
- scénarios de modification ;
- liens de provenance ;
- droits d'entraînement et de publication ;
- corrections humaines et temps.

### 6.2 Corpus

| Niveau | Fondation | MVP | 1.0 |
|---|---:|---:|---:|
| Microcas noyau | 1 000 | 10 000 | 50 000 |
| Pièces P1/P2 | 500-2 000 | 10 000+ | 50 000+ |
| Scénarios d'édition | 5+ par pièce | 50 000+ | 250 000+ |
| Cas adversariaux | 250 | 2 000 | 10 000 |
| Backends/oracles | 2 | 2 noyaux + 2 CAO | 2 noyaux + 4 CAO |

Les splits se font par famille de pièce, fournisseur et date. Des variantes proches ne doivent pas traverser train/test. Le jeu industriel final est aveugle.

### 6.3 Sources existantes

Fusion 360 Gallery, DeepCAD, SketchGraphs, ABC, Fusion 360 Reconstruction, CADFS et BenchCAD sont utiles pour préentraînement et comparaison. Aucun ne remplace un corpus légal réunissant historique, PMI, assemblages et scénarios industriels.

## 7. Entraînement

### Etape A - préentraînement

Préentraînement auto-supervisé sur vues, B-rep, points et texte. Les objectifs possibles sont masked modeling, contrastive alignment, prédiction de relations et JEPA multi-vues.

### Etape B - supervision structurée

Apprentissage de séquences et graphes P1 avec curriculum : sketch simple, extrusion, perçage, motifs, puis références et PMI.

### Etape C - exécution dans la boucle

Les candidats sont compilés et exécutés. Les diagnostics deviennent supervision. Cette étape doit sandboxer chaque programme et limiter temps/mémoire.

### Etape D - préférences ingénieur

Classement par lisibilité, intention, stabilité après édition et temps de correction. Les préférences ne peuvent corriger une violation dimensionnelle ou PMI.

### Etape E - calibration

Temperature scaling, conformal prediction ou méthodes équivalentes calibrent acceptation, revue et abstention. Cible expérimentale ECE au plus 0,05 sur domaine validé.

## 8. Métriques IA

| Métrique | Cible expérimentale MVP |
|---|---:|
| Source syntaxiquement valide sous décodage contraint | 98 % ou plus |
| Dimensions explicites automatiquement acceptées | 100 % exactes ou abstention |
| Détection hors profil | 95 % ou plus |
| Rappel top-5 de graphes candidats | 90 % ou plus sur P1 ciblé |
| ECE de confiance | 0,05 ou moins |
| Ambiguïtés silencieuses | 0 |
| Scénarios d'édition réussis sur acceptés | 95 % ou plus |
| Temps humain médian économisé | 40 % ou plus |

Ces valeurs sont des gates à tester, pas des performances acquises.

## 9. Carte CPU/GPU

| Tâche | CPU | GPU | Autorité initiale |
|---|---|---|---|
| OCR/vision | Possible | Très favorable | GPU avec validation |
| Encodeur point/mesh/B-rep échantillonnée | Lent à grande échelle | Très favorable | GPU |
| LLM/multimodal | Peu compétitif | Tensor Cores | GPU |
| Nearest-neighbor/Chamfer | Possible | Très favorable | GPU non autoritatif |
| Rendu/ray tracing | Possible | RTX/OptiX favorable | Dérivé |
| Tessellation en lots | Possible | Favorable selon pipeline | Dérivé ou contrôlé |
| Solveur d'esquisse | Robuste/mature | Gain incertain, divergence | CPU qualifié |
| Booléens/fillets B-rep | Noyaux matures | Recherche, divergence forte | CPU exact |
| Persistent naming | Branching et graphes | Accélération partielle | CPU qualifié |
| PMI et règles | Faible coût | Inutile initialement | CPU |

## 10. Technologies GPU

### CUDA et Tensor Cores

Voie de performance initiale pour entraînement, inférence, points, distances et batching. TensorRT ou ONNX Runtime peuvent servir l'inférence. Les kernels custom utilisent CUDA uniquement après profilage.

### RTX et OptiX

Ray casting, visibilité, génération de vues, occlusions et rendu synthétique. Les résultats sont des preuves ou vues dérivées, pas une topologie exacte.

### Vulkan Compute

Option portable pour visualisation et kernels simples côté client. Son adoption dépend d'un gain par rapport au rendu existant et du coût de maintenance shader.

### DirectML

Déploiement Windows multi-vendeur pertinent pour certaines CAO clientes. Priorité après preuve d'un besoin desktop.

### OpenCL

Large portabilité historique, mais écosystème ML moderne moins cohérent. Maintenu comme option d'intégration, non priorité MVP.

### ROCm

Option serveur AMD pour entraînement/inférence. Ne doit pas être financée en parallèle de CUDA avant au moins deux besoins clients ou infrastructurels.

### SYCL/oneAPI

Option Intel/HPC et portabilité C++. Appropriée pour kernels ciblés si le benchmark et les pilotes la justifient.

## 11. Estimations de performance

Les estimations suivantes sont hypothèses à mesurer sur corpus identique :

| Sous-système | Hypothèse de gain GPU | Risque |
|---|---:|---|
| Inférence vision/transformer en batch | x5 a x50 vs CPU serveur | Dépend du modèle et batch |
| Distance points/mesh | x10 a x100 | Transferts mémoire et précision |
| Ray casting multi-vues RTX | x10 a x100 | Scène et cohérence drivers |
| Tessellation massive | x2 a x20 | Noyau peut rester dominant |
| Booléens B-rep exacts | Pas de gain assumé | Divergence et cas dégénérés |

Un portage n'est accepté que si le protocole mesure p50, p95, mémoire, précision, déterminisme et taux d'échec. Une cible de gain p95 x2 sans perte est raisonnable pour décider un portage local, mais ne vaut pas seuil universel.

## 12. Portabilité ML

Les modèles sont entraînés avec PyTorch ou équivalent, exportés vers ONNX lorsque la couverture opérateur le permet, puis déployés via ONNX Runtime, TensorRT, OpenXLA/IREE ou TVM selon plateforme. Les opérateurs géométriques spécifiques nécessitent une Component Justification Record.

## 13. Sécurité MLOps

- provenance et licence de chaque dataset ;
- modèle, tokenizer et runtime épinglés ;
- poids et artefacts signés ;
- aucune donnée client réutilisée sans droit ;
- isolation des workers ;
- prompts et sorties journalisés selon politique de confidentialité ;
- évaluation hors distribution ;
- red teaming des fichiers et programmes malveillants ;
- possibilité de déploiement souverain ou hors ligne.
