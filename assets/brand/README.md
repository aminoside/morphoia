# Actifs officiels MORPHOIA

Ce dossier est la source graphique canonique des documents produits par le dépôt.

## Charte et kit prêt à l'emploi

- [`MORPHOIA_charte_graphique_v1.0.pdf`](MORPHOIA_charte_graphique_v1.0.pdf) : charte
  graphique officielle, version 1.0, 20 pages A4 paysage ;
- [`morphoia-logo-vectoriel.zip`](morphoia-logo-vectoriel.zip) : kit complet téléchargeable ;
- [`sheet.png`](sheet.png) : planche d'aperçu des principales déclinaisons.

## Masters vectoriels et déclinaisons

- `morphoia-logo.svg` : logotype complet officiel pour fond sombre ;
- `morphoia-logo-fond-clair.svg` : logotype complet pour fond clair ;
- `morphoia-logo-mono.svg` : logotype complet monochrome ;
- `morphoia-symbole.svg` : symbole seul avec dégradé ;
- `morphoia-symbole-mono.svg` : symbole seul monochrome ;
- `morphoia-symbole-blueprint.svg` : symbole avec calque de construction isométrique ;
- `morphoia-typographie.svg` : mot MORPHOIA vectorisé en monochrome.

Des exports PNG transparents d'aperçu sont fournis pour les usages qui ne prennent pas en charge
le SVG. `LISEZ-MOI.txt` documente la construction géométrique, le dégradé et la typographie
vectorisée du kit.

Empreintes approuvées :

```text
23a67711bcb03ebe025dc7c0401de4e6d3abd22d149652704b48b52499dd8f18  MORPHOIA_charte_graphique_v1.0.pdf
1ada94d18db5a0003db972a5f54e6ade13ba6843fbfd7efe8c130745800714c3  morphoia-logo.svg
abc0d796aa4fc7314acce12828282b644f1a896269243a8bb7a5396fef2433c4  morphoia-typographie.svg
2ae65599f4b433577913ecd251e2aef9512262a709864a2cbd80847aebc9b521  morphoia-logo-vectoriel.zip
cf4df2504fe5b729c37eeb962618323e1a910980e79a28edf1032a6c3bc2fa3a  sheet.png
```

Les générateurs PDF lisent directement les tracés de ces fichiers. Le logo reste vectoriel ; il
n'est ni redessiné, ni retapé, ni rasterisé. La planche d'aperçu `sheet.png` n'est pas un actif de
production et ne doit jamais servir à reconstruire le logo.

## Polices

La charte graphique version 1.0 utilise Aldrich Regular pour les titres et Barlow pour le texte.
Les fichiers présents dans `fonts/` proviennent du dépôt officiel `google/fonts`, commit :

```text
2796410152d4f9524b68ed46e69c1b60f8e0f7c3
```

Ils sont redistribués sous SIL Open Font License 1.1. Les textes applicables se trouvent dans
`OFL-Aldrich.txt` et `OFL-Barlow.txt`.

## Règle de production documentaire

Tout rapport PDF généré par le projet doit :

1. être déclaré dans `reports.json` ;
2. utiliser `reporting/morphoia_brand.py` ;
3. afficher le logo officiel et `Olivier Ami` sur la couverture ;
4. déclarer `Olivier Ami` dans la métadonnée `/Author` ;
5. embarquer Aldrich et Barlow ;
6. réussir `python scripts/check_pdf_branding.py`.

Les documents graphiques de référence fournis comme sources de marque sont déclarés séparément
dans `brand_documents` avec une empreinte SHA-256 immuable. Leur intégrité, leur format A4, leur
langue et leur attribution à Olivier Ami sont contrôlés sans leur appliquer les règles propres aux
rapports générés.
