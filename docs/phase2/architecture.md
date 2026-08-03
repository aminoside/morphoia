# Architecture de référence

## 1. Décision synthétique

MORPHOIA adopte une architecture hybride, STEP-centrique et multi-backend. Le coeur n'est ni un nouveau noyau, ni un format maillé, ni une IA générative. Il s'agit d'une couche de confiance qui relie :

- preuves d'entrée et provenance ;
- graphe de construction typé ;
- exécution déterministe ;
- noyaux et solveurs existants ;
- résultat B-rep explicite ;
- validation comportementale ;
- registre des pertes ;
- sorties spécialisées.

```text
Sources immuables
plans | images | texte | scans | meshes | STEP | CAO native
        |
        v
Extraction multimodale et graphe de preuves
        |
        v
Candidats IA classes + confiance + abstention
        |
        v
Graphe canonique STEP-centrique
        |
        v
Runtime deterministe et transactionnel
        |
        +--> solveur existant
        +--> OCCT reference ouverte
        +--> FreeCAD oracle ouvert
        +--> Parasolid/ACIS/CAO en option
        |
        v
B-rep + PMI + proprietes + registre des pertes
        |
        +--> AP242 / AP238 / QIF
        +--> FreeCAD / CAO natives
        +--> JT / glTF / OpenUSD / Blender
```

## 2. Alternatives comparées

| Stratégie | Avantage | Limite décisive | Décision |
|---|---|---|---|
| IA vers fichier natif | Démonstration rapide | Verrou fournisseur, faible vérifiabilité | Adaptateur seulement |
| STEP seul sans runtime | Pérennité et richesse normative | Sémantique d'exécution peu implémentée | Autorité sémantique, insuffisante seule |
| CadQuery ou Python comme standard | Productivité et OCCT | Langage général, effets de bord, PMI incomplet | SDK et frontend de comparaison |
| FeatureScript | Features et requêtes riches | Runtime propriétaire Onshape | Référence de conception |
| MLIR comme format public | Typage, passes et dialectes | Pas de sémantique mécanique intrinsèque | IR de compilation optionnelle |
| Mesh/implicite comme autorité | GPU, scan et formes complexes | Perte d'intention, PMI et B-rep | Représentation complémentaire |
| Nouveau noyau exact | Contrôle complet | 50-150 M€+, 7-12 ans, risque extrême | Rejeté |
| Façade textuelle + graphe STEP | Lisibilité, sûreté, IA et Git | Adoption à démontrer | Draft 0.x falsifiable |

## 3. Couches et responsabilités

### 3.1 Sources et preuves

Chaque source est immuable et identifiée par URI, type MIME, empreinte, unité connue ou inconnue, licence et règles d'usage. Une preuve peut viser une cote, une région d'image, un primitive de nuage de points, une entité STEP, une phrase ou une décision humaine.

Cette couche réutilise PDF, DXF, STEP, JT, QIF et les SDK de traduction. MORPHOIA n'invente pas un conteneur multimédia.

### 3.2 Extraction multimodale

La vision, l'OCR et les encodeurs 3D produisent des observations, jamais des vérités géométriques. Ils peuvent proposer plusieurs candidats et doivent calibrer leur confiance. Les sorties restent séparées du graphe accepté.

### 3.3 Graphe canonique

Le graphe porte produit, paramètres, opérations, contraintes, références, PMI, configurations, preuves et scénarios. Son vocabulaire est mappé aux ressources ISO 10303. Le JSON 0.1 n'est qu'un encodage testable ; l'abstract data model constitue le contrat.

La structure de lecture est un arbre. Les dépendances de calcul forment un DAG. Les contraintes forment un hypergraphe séparé qui peut contenir des cycles algébriques.

### 3.4 Runtime

Le runtime effectue :

1. parsing et résolution des versions ;
2. typage et unités ;
3. construction du DAG ;
4. vérification des capacités ;
5. résolution des contraintes ;
6. exécution des opérations ;
7. propagation des lignées ;
8. résolution des références ;
9. validation géométrique et PMI ;
10. scénarios d'édition ;
11. commit atomique ou rollback.

Le runtime de confiance n'exécute jamais de Python arbitraire généré par IA.

### 3.5 Noyaux et solveurs

OCCT fournit le backend exact ouvert initial. OCAF/XDE sont réutilisés pour documents, transactions, structure produit et échange STEP. FreeCAD apporte un oracle de recompute et un solveur d'esquisse ouvert. Parasolid, ACIS, CGM, C3D et les CAO natives restent des plugins optionnels soumis à licence.

La frontière de plugin expose des types MORPHOIA et des handles opaques. Aucun pointeur ou identifiant natif de noyau n'est sérialisé comme identité canonique.

### 3.6 Validation

La validation est indépendante de l'exécution : un backend peut construire un solide mais échouer la conformité comportementale. Chaque rapport contient verdicts, preuves, versions, propriétés, ambiguïtés, réparations et pertes.

### 3.7 Sorties

AP242 est la sortie mécanique neutre privilégiée. AP238 et QIF couvrent fabrication et qualité. JT, glTF et OpenUSD restent des vues dérivées. Les formats natifs sont produits par des adaptateurs versionnés et ne deviennent jamais une dépendance du coeur.

## 4. Double représentation

Chaque révision validée conserve :

- le graphe procédural ;
- la représentation explicite exacte ;
- les propriétés de validation ;
- l'environnement verrouillé ;
- le lien entre entités canoniques et entités du résultat ;
- le registre des pertes.

Ce principe reprend ISO 10303-55. La B-rep permet d'ouvrir et d'inspecter le dernier état même si une opération future n'est plus exécutable. Le graphe reste l'autorité d'édition.

## 5. Identité et topological naming

Une identité persistante n'est pas un index de face. Elle comprend :

1. UUID de l'intention ;
2. feature productrice ;
3. rôle de sortie ;
4. lignée de création, modification, fusion ou scission ;
5. filtre géométrique typé ;
6. contexte d'adjacence ;
7. signature de vérification ;
8. cardinalité attendue.

La résolution retourne `unique`, `ambiguous` ou `missing`. Un score peut ordonner les candidats pour l'affichage, mais ne transforme jamais une ambiguïté en choix automatique.

## 6. Transactions, undo/redo et versioning

Chaque modification crée une transaction comprenant source, paramètres modifiés, DAG affecté, résultats, propriétés, logs et verdicts. Le commit n'a lieu qu'après les validations exigées par le profil. Undo et redo rejouent des révisions immuables ; ils ne tentent pas d'inverser numériquement une opération.

Git versionne les sources, spécifications et manifests. Les gros résultats B-rep peuvent être placés dans un stockage de contenu adressé par hash ou Git LFS. Le hash sémantique ignore les détails de mise en forme mais couvre chaque décision géométrique.

## 7. Déterminisme

Trois niveaux sont distingués :

- déterminisme sémantique : même graphe et mêmes décisions ;
- déterminisme d'un profil : même noyau, solveur, versions et options ;
- équivalence multi-backend : propriétés dans les tolérances, sans exiger les mêmes octets.

Les opérations parallèles indépendantes peuvent être calculées simultanément. Leur ordre de commit est fixé par le DAG puis l'UUID. Les réductions GPU non déterministes ne participent pas à une propriété autoritative sans mode qualifié.

## 8. Système d'extensions

Une extension est identifiée par URI, version exacte, empreinte, licence, types, opérations, effets, rôles topologiques, mapping STEP, fallback et suite de tests. Une extension inconnue peut être préservée, mais pas exécutée.

Le code natif arbitraire n'est jamais embarqué dans un document. Les implémentations sont des plugins signés ou, après expérimentation, des modules WebAssembly sans I/O dans un profil déterministe.

## 9. MLIR, LLVM, OpenXLA et ONNX

MLIR est approprié pour représenter opérations, types, attributs, interfaces et passes. Un dialecte interne MORPHOIA pourra accélérer la vérification et le lowering C++/GPU. Il ne devient pas le format d'archive : il ne porte pas nativement produit, PMI, provenance ou identité topologique.

LLVM compile le runtime et les extensions sûres. ONNX Runtime, OpenXLA, IREE et TVM déploient les modèles IA. Aucun de ces outils ne définit la sémantique CAO.

## 10. Frontières de confiance

| Zone | Confiance | Mesures |
|---|---|---|
| Source validée | Haute après validation | Schéma, types, unités, DAG, quotas |
| Modèle IA | Non fiable | Décodage contraint, abstention, provenance |
| Parser de format externe | Non fiable | Processus isolé, limites, fuzzing |
| Backend ouvert qualifié | Conditionnelle | Version pinning, corpus, propriétés |
| SDK propriétaire | Conditionnelle | Worker isolé, contrat de licence, matrice de versions |
| Vue glTF/USD/JT | Dérivée | Jamais autorité paramétrique |

## 11. Composants réellement nouveaux

La Phase 1 justifie seulement :

- profil exécutable des ressources STEP procédurales ;
- runtime neutre de référence ;
- mapping de features vers les backends avec pertes ;
- référence persistante multi-stratégie avec abstention ;
- validateur comportemental et différentiel ;
- graphe de preuves et d'hypothèses ;
- registre de pertes ;
- suite de conformité paramétrique.

La façade `.morph` est un composant expérimental. Elle doit être abandonnée si elle n'améliore pas de manière mesurable la validité IA, la sécurité ou le temps humain par rapport aux alternatives.
