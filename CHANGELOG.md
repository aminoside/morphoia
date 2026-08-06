# Changelog

Toutes les modifications notables de MORPHOIA seront documentées ici.

## [Non publié]

### Ajouté

- pré-enregistrement exécutable P0 de Morphoia Visual Exchange (MVX), avec métriques,
  éligibilité, plan statistique, split groupé déterministe, codes d'erreur et gates G0-G7 ;
- schémas JSON versionnés pour le registre, les lignées, les splits, les runs, les métriques,
  les échecs et les verdicts de gate ;
- commandes `morphoia mvx protocol verify`, `protocol seal` et `split` ;
- empreinte SHA-256 racine du protocole et verdict G0 machine-readable.

### Modifié

- application de l'identité visuelle officielle MORPHOIA aux rapports PDF des phases 1 et 2 ;
- utilisation du logo vectoriel officiel, de la palette MORPHOIA et des polices Aldrich/Barlow ;
- attribution visible et métadonnées PDF normalisées au nom d'Olivier Ami ;
- ajout d'un thème de rapport réutilisable et d'un manifeste imposant ces règles à tout futur
  PDF suivi par Git.

### Qualité

- contrôle CI de l'intégrité des SVG officiels, des polices incorporées, de la mise en page A4,
  des métadonnées et de la présence de chaque PDF dans le manifeste ;
- détection de dérive étendue aux contenus graphiques, polices, images et dégradés.

## [0.2.0-dev] - 2026-08-03

### Ajouté

- candidat expérimental Phase 2 avec cahier des charges, architecture et spécification ;
- grammaire EBNF, catalogue des opérations et exemple `.morph` ;
- lexer, parseur, validateur sémantique et compilateur vers l'IR JSON canonique ;
- hash sémantique, décimaux exacts et identifiants déterministes ;
- résolveur de références topologiques à trois états ;
- runtime transactionnel de référence avec rollback, undo/redo et détection des conflits ;
- contrats de provenance, décisions IA et registre des pertes ;
- schémas JSON de l'IR, des backends et des pertes ;
- guides utilisateur/développeur, interopérabilité, IA/GPU, validation, coûts et roadmap ;
- rapport PDF Phase 2 reproductible et contrôles CI.
- alignement sur la licence MIT choisie à la création du dépôt GitHub, avec attribution à
  Olivier Ami.

### Limites déclarées

- aucun backend B-rep, solveur, import/export STEP ou connecteur CAO n'est encore implémenté ;
- la syntaxe et l'IR 0.1 restent non normatifs jusqu'aux gates de la Phase 1.

## [0.1.0] - 2026-08-03

### Ajouté

- création du projet MORPHOIA ;
- rapport Phase 1 - État de l'art et étude de faisabilité ;
- source Markdown et générateur PDF reproductible ;
- contrôle automatique du titre, de l'auteur, de la pagination et des liens ;
- métadonnées d'auteur Olivier Ami et gouvernance initiale.
