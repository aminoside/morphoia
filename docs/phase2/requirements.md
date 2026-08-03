# Cahier des charges traçable

## 1. Règle de conception

Toute décision respecte la règle suivante :

> Un composant nouveau n'est autorisé que si une analyse reproductible démontre qu'aucune solution existante ne satisfait les exigences, ou si un benchmark préenregistré démontre un avantage mesurable de performance, robustesse, interopérabilité ou simplicité.

Cette règle s'applique au langage, au runtime, aux schémas, aux solveurs, aux noyaux, aux bibliothèques GPU, aux modèles d'IA et aux formats d'échange.

## 2. Gates de standardisation

| Gate | Preuve requise | Statut initial |
|---|---|---|
| G0 - Draft expérimental | Spécification, implémentation de référence, 100 cas golden | En cours |
| G1 - Profil portable | P1 et P2 sur deux backends, validité B-rep au moins 99 %, scénarios d'édition au moins 95 % | Non atteint |
| G2 - Conformité publique | Corpus, propriétés de validation, registre des pertes et implémentation indépendante | Non atteint |
| G3 - Valeur industrielle | Gain médian de temps humain au moins 40 % sur deux pilotes | Non atteint |
| G4 - Standard candidate | G1, G2 et G3, gouvernance externe et politique brevets | Interdit avant preuves |

Les artefacts 0.x doivent porter les mots `experimental`, `draft` ou `candidate`. Les mots `standard`, `stable`, `certified` et `1.0` sont réservés aux gates correspondants.

## 3. Exigences de gouvernance et de périmètre

| ID | Exigence | Critère d'acceptation |
|---|---|---|
| GOV-001 | Réutiliser avant de créer. | Chaque composant possède une Component Justification Record, ou une référence explicite à une brique existante. |
| GOV-002 | Ne pas figer le DSL avant G4. | La syntaxe 0.x reste expérimentale et remplaçable. |
| GOV-003 | Comparer sur le même corpus. | Alternatives, versions, licences et conditions de benchmark sont enregistrées. |
| GOV-004 | Séparer spécification, implémentation et certification. | Aucun succès du runtime de référence ne vaut preuve de conformité universelle. |
| SCP-001 | Commencer par P1. | Esquisses, extrusion, révolution, trou, booléen, motif, miroir, congé et chanfrein constants. |
| SCP-002 | Versionner P1, P2, P3 et P4 séparément. | Chaque opération déclare son profil minimal et son fallback. |
| SCP-003 | Refuser explicitement le hors-profil. | Au moins 95 % des pièces hors profil sont refusées ou dirigées vers revue. |

## 4. Exigences sémantiques

| ID | Exigence | Critère d'acceptation |
|---|---|---|
| SEM-001 | Ancrer le modèle dans AP242 et ISO 10303-42/-55/-108/-109/-111/-112/-113. | Chaque concept possède un mapping ou un écart documenté. |
| SEM-002 | Ne pas recréer une ontologie concurrente. | Les extensions sont namespacées et limitées aux écarts démontrés. |
| SEM-003 | Conserver procédure et résultat explicite. | Toute régénération validée lie le graphe, la B-rep, les propriétés et l'environnement. |
| SEM-004 | Employer un graphe typé. | Tous les noeuds et relations nécessaires à la régénération sont explicites. |
| SEM-005 | Déclarer support, approximation, fallback, perte ou refus. | Aucune dégradation silencieuse. |
| SEM-006 | Produire un hash sémantique canonique. | Espaces, commentaires et ordre non significatif ne modifient pas le hash. |
| SEM-007 | Assurer la pérennité. | Le graphe et la dernière représentation explicite restent lisibles sans SDK propriétaire. |

## 5. Exigences d'exécution et de géométrie

| ID | Exigence | Critère d'acceptation |
|---|---|---|
| GEO-001 | Utiliser OCCT comme backend exact ouvert de référence. | Aucun type OCCT ne fuit dans le contrat canonique. |
| GEO-002 | Permettre des backends substituables. | Interface de capacités commune et tests différentiels. |
| GEO-003 | Ne pas réécrire un noyau B-rep. | Aucun budget POC/MVP alloué à un noyau généraliste nouveau. |
| EXE-001 | Verrouiller l'environnement. | Versions du runtime, noyau, solveur, extensions et options sont enregistrées. |
| EXE-002 | Déterminisme sémantique. | Même source validée produit le même graphe et le même hash. |
| EXE-003 | Déterminisme du profil. | Même graphe et même lockfile produisent les mêmes propriétés de validation. |
| EXE-004 | Transaction et rollback. | Un échec ne remplace jamais le dernier état valide. |
| EXE-005 | DAG explicite. | Cycles de construction refusés avant exécution. |
| SOL-001 | Réutiliser un solveur existant. | FreeCAD Sketcher, SolveSpace ou D-Cubed évalué avant toute implémentation nouvelle. |
| SOL-002 | Capturer la sémantique du solveur. | Branche, initialisation, priorités, degrés de liberté, résidus et diagnostics enregistrés. |

## 6. Identité topologique et tolérances

| ID | Exigence | Critère d'acceptation |
|---|---|---|
| REF-001 | Interdire les indices natifs comme identité persistante. | Toute référence combine producteur, rôle, lignée et preuves géométriques ou d'adjacence. |
| REF-002 | Résolution à trois états. | `unique`, `ambiguous` ou `missing`; zéro ambiguïté silencieuse. |
| REF-003 | Tester après édition. | Variation, suppression et réordonnancement pertinents sont testés. |
| REF-004 | Conserver l'UUID de l'intention. | Renommer un symbole ne change pas son UUID explicite. |
| TOL-001 | Séparer quatre tolérances. | Tolérance noyau, incertitude capteur, tolérance dimensionnelle et zone GD&T sont des types distincts. |
| TOL-002 | Interdire le healing silencieux. | Toute réparation est un événement et une perte potentielle. |

## 7. PMI, assemblages et provenance

| ID | Exigence | Critère d'acceptation |
|---|---|---|
| PMI-001 | Porter le PMI sémantique. | Datums, zones, modificateurs, unités et associations survivent aux scénarios P2. |
| ASM-001 | Séparer définition et occurrence. | Identité produit, occurrence, placement et configuration restent distincts. |
| PROV-001 | Relier chaque inférence à une preuve. | Source, région, cote, règle, modèle et confiance sont référencés. |
| PROV-002 | Représenter l'incertitude. | `certain`, `hypothesis`, `ambiguous` et `unknown` sont distincts. |
| LOSS-001 | Produire un registre des pertes. | Chaque import, exécution et export fournit un rapport machine-readable. |

## 8. IA, sécurité et GPU

| ID | Exigence | Critère d'acceptation |
|---|---|---|
| AI-001 | L'IA propose, le runtime valide. | Aucune sortie IA n'est autoritative avant validations déterministes. |
| AI-002 | Autoriser plusieurs hypothèses et l'abstention. | Une dimension absente n'est jamais inventée comme vérité. |
| AI-003 | Décodage contraint. | Au moins 98 % de sorties syntaxiquement valides constitue une cible expérimentale. |
| DAT-001 | Employer des données à droits démontrés. | Licence, consentement contractuel et usages permis attachés à chaque actif. |
| SEC-001 | Interdire les effets de bord dans la source. | Pas d'I/O, réseau, horloge, aléa, récursion ou boucle générale. |
| SEC-002 | Isoler les adaptateurs non fiables. | Quotas CPU, GPU, mémoire, temps et système de fichiers. |
| GPU-001 | GPU pour perception et calcul dense. | Vision, OCR, points, rendu, distances, tessellation et IA priorisés. |
| GPU-002 | CPU/noyau exact pour l'autorité initiale. | Booléens, fillets, solveur, healing et PMI restent qualifiés sur CPU. |
| GPU-003 | Prouver tout portage. | Temps p50/p95, mémoire, précision, déterminisme et taux d'échec comparés au CPU. |

## 9. Interopérabilité et validation

| ID | Exigence | Critère d'acceptation |
|---|---|---|
| INT-001 | AP242 comme autorité d'échange mécanique. | Round-trip géométrie et propriétés au moins 99 % sur le profil supporté. |
| INT-002 | AP238/QIF pour fabrication et qualité. | Liens explicites vers les entités canoniques. |
| INT-003 | JT, glTF et OpenUSD comme vues dérivées. | Une vue maillée ne remplace jamais l'autorité paramétrique. |
| INT-004 | IGES, STL, OBJ et PLY comme frontières héritées. | Informations absentes et reconstruction requise sont déclarées. |
| ADP-001 | Isoler les CAO propriétaires. | Matrice CAO x version x profil, sans dépendance fournisseur dans le coeur. |
| VAL-001 | Séparer les niveaux de validation. | Syntaxe, sémantique, contraintes, géométrie, topologie, comportement et industrie ont des verdicts distincts. |
| VAL-002 | Mesurer les scénarios d'édition. | Au moins 95 % réussis sur les pièces acceptées. |
| VAL-003 | Dimensions explicites exactes ou abstention. | 100 % sur les cas automatiquement acceptés. |
| VAL-004 | Conservation des unités et tolérances. | 100 %. |
| VAL-005 | Validité B-rep. | Au moins 99 % sans healing silencieux. |

## 10. Component Justification Record

Tout composant nouveau doit posséder un fichier `CJR-XXXX.md` contenant :

1. exigences non couvertes ;
2. solutions existantes et versions examinées ;
3. couverture, architecture, performance, licence et pérennité ;
4. corpus et protocole reproductibles ;
5. échec démontré ou avantage quantifié ;
6. coût de développement et de maintenance ;
7. mapping STEP et pertes ;
8. stratégie de remplacement ;
9. décision, approbateurs et date ;
10. condition d'abandon si l'avantage n'est pas confirmé.

Il n'existe pas de seuil universel valable pour tout composant. La métrique doit être préenregistrée : temps, mémoire, taux de succès, robustesse, portabilité, pertes sémantiques, tokens ou temps humain.
