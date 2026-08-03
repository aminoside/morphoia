# Changelog

Toutes les modifications notables de MORPHOIA seront documentées ici.

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
