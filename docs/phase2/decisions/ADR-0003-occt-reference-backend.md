# ADR-0003 - OCCT comme backend ouvert de référence

- Statut : accepté
- Date : 2026-08-03
- Auteurs du projet : Louis Manhès et Olivier Ami

## Contexte

OCCT fournit B-rep exacte, opérations géométriques, OCAF, XDE et STEP. Réécrire un noyau demanderait plusieurs centaines d'ETP-an et n'apporterait pas de bénéfice démontré au POC.

## Décision

OCCT est le premier backend exact. FreeCAD apporte un oracle ouvert. Parasolid, ACIS, CGM ou C3D sont optionnels sous licence.

## Conséquences

- aucune classe OCCT dans le schéma canonique ;
- adaptateur versionné ;
- tests adversariaux et différentiels ;
- healing toujours déclaré ;
- aucun projet de noyau B-rep GPU généraliste dans la roadmap initiale.
