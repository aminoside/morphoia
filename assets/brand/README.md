# Actifs officiels MORPHOIA

Ce dossier est la source graphique canonique des documents produits par le dépôt.

## Masters vectoriels

- `morphoia-logo.svg` : logotype complet officiel pour fond sombre ;
- `morphoia-typographie.svg` : mot MORPHOIA vectorisé en monochrome.

Empreintes approuvées :

```text
1ada94d18db5a0003db972a5f54e6ade13ba6843fbfd7efe8c130745800714c3  morphoia-logo.svg
abc0d796aa4fc7314acce12828282b644f1a896269243a8bb7a5396fef2433c4  morphoia-typographie.svg
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

## Règle de production

Tout PDF suivi par Git doit :

1. être déclaré dans `reports.json` ;
2. utiliser `reporting/morphoia_brand.py` ;
3. afficher le logo officiel et `Olivier Ami` sur la couverture ;
4. déclarer `Olivier Ami` dans la métadonnée `/Author` ;
5. embarquer Aldrich et Barlow ;
6. réussir `python scripts/check_pdf_branding.py`.
