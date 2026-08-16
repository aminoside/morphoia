# ADR-0002 - Façade textuelle expérimentale

- Statut : accepté sous condition
- Date : 2026-08-03
- Auteurs du projet : Louis Manhès et Olivier Ami

## Contexte

EXPRESS spécifie des données mais n'est pas un langage d'exécution. FeatureScript est lié à Onshape. CadQuery réutilise Python généraliste. MLIR n'a pas de sémantique mécanique. Aucune option ne réunit syntaxe bornée, génération IA, identité explicite, provenance et exécution multi-backend.

## Décision

Expérimenter une façade `.morph` déclarative, sans effets de bord et compilée vers le graphe canonique. Elle reste non normative en 0.x.

## Critères de maintien

- 100 % de round-trip sémantique du profil ;
- deux parseurs indépendants produisant les mêmes hashes ;
- gain significatif de validité IA face à CadQuery et MLIR générique ;
- réduction préenregistrée du temps de correction humaine ;
- absence d'I/O et terminaison démontrée.

## Condition d'abandon

Si ces avantages ne sont pas démontrés, conserver uniquement le graphe STEP-centrique et l'API Python typée.
