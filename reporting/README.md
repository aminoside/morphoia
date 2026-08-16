# Génération des PDF MORPHOIA

Le thème partagé `morphoia_brand.py` applique la charte graphique MORPHOIA version 1.0 à tous les
rapports du dépôt. Il centralise la palette sRGB officielle, les polices incorporées, le rendu
vectoriel du logo, les métadonnées, la couverture, l'en-tête et le pied de page.

## Créer un nouveau rapport

1. Importer les styles et fonctions depuis `reporting.morphoia_brand`.
2. Utiliser `draw_cover_base()` sur la couverture et `draw_page_chrome()` sur les autres pages.
3. Utiliser `BrandedCanvas`, Aldrich pour les titres et Barlow pour tout autre texte.
4. Conserver les marges `PORTRAIT_MARGIN` ou `LANDSCAPE_MARGIN`.
5. Renseigner le titre et le sujet ; les auteurs restent `Louis Manhès et Olivier Ami`.
6. Déclarer le PDF, son générateur et son validateur dans `reports.json`.
7. Reconstruire le document puis exécuter `make check`.

La CI refuse tout PDF généré suivi par Git qui n'est pas déclaré, qui utilise une autre identité
visuelle, qui n'incorpore pas les polices officielles ou dont la métadonnée d'auteur diffère de
`Louis Manhès; Olivier Ami`. Les documents de référence immuables sont validés séparément.

## Contraintes visuelles

- Fond de couverture : `SPACE #080F19`.
- Texte courant : `ARDOISE #2A3442` sur blanc.
- Titres : Aldrich Regular ; texte : Barlow.
- Logo : masters SVG officiels inchangés.
- Dégradé : `#6DDFF5` vers `#D795EF`, avec ombre verticale `#0000BA` jusqu'à 37,5 %.
- Baseline : `DESIGN INTENT. PARAMETRIC REALITY.`
- Aucun troisième caractère typographique ou couleur hors charte.
