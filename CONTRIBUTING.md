# Contribuer à MORPHOIA

MORPHOIA est un dépôt public dirigé par Olivier Ami et distribué sous la licence MIT publiée
dans `LICENSE`.

## Règles de contribution

1. Ouvrir une issue décrivant le besoin, les standards concernés et les critères de validation.
2. Créer une branche dédiée ; ne pas pousser directement sur `main`.
3. Conserver les références bibliographiques et la provenance des données.
4. Ajouter ou mettre à jour les tests associés à toute modification de code.
5. Signaler explicitement les pertes de sémantique, ambiguïtés et dépendances propriétaires.
6. Ne jamais inclure de données industrielles confidentielles, de secrets ou de credentials.
7. Faire relire toute modification normative, géométrique ou brevet par un expert du domaine concerné.
8. Ajouter une ADR pour toute décision architecturale structurante.
9. Ajouter un CJR avant tout nouveau composant qui duplique ou remplace une solution existante.
10. Distinguer dans les documents et API ce qui est implémenté, spécifié, expérimental ou planifié.

## Documents PDF et identité MORPHOIA

Tout PDF ajouté au dépôt doit respecter la charte graphique MORPHOIA version 1.0 et conserver
`Olivier Ami` comme auteur du document. Les contributeurs restent crédités par leurs commits et,
si nécessaire, dans une section de contributions.

Les nouveaux PDF doivent :

1. utiliser les masters officiels de `assets/brand/` sans les modifier ni les rasteriser ;
2. employer le thème partagé `reporting/morphoia_brand.py` ;
3. incorporer Aldrich et Barlow, sans police de substitution ;
4. être déclarés dans `reports.json` avec leur générateur et leur validateur ;
5. être reconstruits et vérifiés par `make check` avant toute pull request.

La CI refuse automatiquement un PDF suivi par Git qui n'est pas déclaré ou conforme.

## Convention d'auteur

Olivier Ami reste l'auteur et l'initiateur du projet MORPHOIA. Les contributeurs conservent l'attribution de leurs commits et contributions spécifiques.

## Phase 1 et candidat Phase 2

La Phase 1 interdit de concevoir prématurément un nouveau langage. Toute proposition d'architecture ou de représentation doit être reliée à l'étude de faisabilité, aux standards existants et à une lacune démontrée.

La façade textuelle et l'IR de Phase 2 sont expérimentales. Aucune contribution ne peut les
qualifier de standard stable avant exécution P1/P2 sur deux backends, conformité publique et
bénéfice industriel mesuré.
