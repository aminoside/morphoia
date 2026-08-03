# MORPHOIA - Phase 2

## Statut

Cette branche documentaire constitue le **Draft expérimental 0.1** de MORPHOIA. Elle ne constitue ni une norme ISO, ni une spécification industrielle stable, ni une promesse de compatibilité universelle.

La Phase 1 interdit de figer immédiatement un nouveau langage public. En conséquence, MORPHOIA 0.1 est organisé comme :

1. un profil exécutable, borné et STEP-centrique ;
2. un graphe canonique interne versionné ;
3. une façade textuelle expérimentale destinée à l'humain et à l'IA ;
4. une implémentation de référence permettant de mesurer cette façade ;
5. une suite de validation appelée à devenir une suite de conformité.

Le statut normatif ne pourra être proposé qu'après trois preuves cumulatives :

- profils P1 et P2 exécutés par au moins deux backends indépendants ;
- suite de conformité publique ;
- bénéfice industriel mesuré sur des pilotes représentatifs.

## Livrables

| Document | Objet |
|---|---|
| [Exigences](requirements.md) | Conclusions de la Phase 1 transformées en exigences opposables |
| [Architecture](architecture.md) | Alternatives, choix et responsabilités de chaque couche |
| [Spécification du langage](language-specification.md) | Modèle d'exécution, types, sémantique et extensions |
| [Grammaire EBNF](grammar.ebnf) | Grammaire candidate complète de la façade textuelle 0.1 |
| [Catalogue des opérations](operation-catalog.md) | Contrats minimaux des opérations P1 a P4 |
| [Interopérabilité](interoperability.md) | Import, export, pertes et rôle de chaque standard ou CAO |
| [IA et GPU](ai-gpu.md) | Pipeline multimodal, entraînement, accélération et limites |
| [SDK et API](sdk-api.md) | API Python, coeur C++, plugins et services |
| [Validation](validation-conformance.md) | Validateurs, benchmarks, propriétés et critères de passage |
| [Manuel utilisateur](user-guide.md) | Installation, écriture, validation et compilation |
| [Manuel développeur](developer-guide.md) | Structure du code, conventions, tests et ajout de composants |
| [Roadmap et gouvernance](roadmap-governance.md) | MVP, Alpha, Bêta, 1.0, licences et adoption |
| [Coûts et risques](costs-risks.md) | Estimations, scénarios et plans de réduction du risque |
| [Références](references.md) | Normes et documents primaires |

## Implémentation de référence

La série 0.1 fournit un lexer, un parser, un validateur sémantique, un compilateur vers le graphe canonique JSON et un résolveur de références topologiques à trois états. Elle ne fournit pas encore un noyau géométrique ni un export STEP : ces fonctions doivent réutiliser OCCT et les ressources STEP, conformément à la Phase 1.

```bash
PYTHONPATH=src python -m morphoia validate examples/mounting_plate.morph
PYTHONPATH=src python -m morphoia compile examples/mounting_plate.morph \
  -o build/mounting_plate.mcir.json
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Auteur

MORPHOIA a été initié par **Olivier Ami**.
