# ADR-0001 - Coeur STEP-centrique

- Statut : accepté pour expérimentation
- Date : 2026-08-03
- Auteurs du projet : Louis Manhès et Olivier Ami

## Contexte

AP242 et ISO 10303-42/-55/-108/-109/-111/-112/-113 couvrent déjà produit, géométrie, procédures, paramètres, contraintes, esquisses et features. Créer une ontologie concurrente violerait GOV-001 et SEM-002.

## Décision

Le modèle abstrait MORPHOIA réutilise ces concepts. Les nouveaux concepts doivent être namespacés, accompagnés d'un mapping ou d'un écart formel, et soumis à une Component Justification Record.

## Conséquences

- AP242 devient l'autorité d'échange mécanique.
- Le JSON 0.1 n'est pas une nouvelle autorité sémantique.
- Les schémas EXPRESS officiels devront être analysés avant de figer des noms d'entités.
- Une dépendance à un SDK STEP unique est interdite.
