#!/usr/bin/env python3
"""Build the MORPHOIA Phase 2 experimental standard candidate report."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
)

from build_report import (
    ST,
    ReportDoc,
    Rule,
    parse_markdown,
)
from reporting.morphoia_brand import (
    AUTHOR,
    AUTHOR_DISPLAY,
    CREATOR,
    FONT_TEXT,
    INDIGO,
    LANDSCAPE_MARGIN,
    PORTRAIT_MARGIN,
    BrandedCanvas,
    draw_cover_base,
    draw_page_chrome,
)

ROOT = Path(__file__).resolve().parent
PHASE2 = ROOT / "docs" / "phase2"
OUTPUT = PHASE2 / "MORPHOIA_phase2_standard_candidate_v0.1.pdf"

CHAPTERS = (
    "README.md",
    "requirements.md",
    "architecture.md",
    "language-specification.md",
    "grammar.ebnf",
    "operation-catalog.md",
    "sdk-api.md",
    "validation-conformance.md",
    "interoperability.md",
    "ai-gpu.md",
    "user-guide.md",
    "developer-guide.md",
    "tutorials-faq.md",
    "roadmap-governance.md",
    "costs-risks.md",
    "references.md",
    "decisions/ADR-0001-step-centred-core.md",
    "decisions/ADR-0002-experimental-text-facade.md",
    "decisions/ADR-0003-occt-reference-backend.md",
    "decisions/CJR-TEMPLATE.md",
)


def on_cover(canvas, _doc):
    draw_cover_base(
        canvas,
        A4,
        title="MORPHOIA - Phase 2 - Candidat de standard expérimental 0.1",
        subject=("Graphe de construction paramétrique, IA, interopérabilité CAO et conformité"),
    )


def header_footer(canvas, doc, page_size):
    draw_page_chrome(
        canvas,
        doc,
        page_size,
        label="PHASE 2  /  CANDIDAT 0.1",
        footer="Candidat expérimental - non normatif - 3 août 2026",
    )


def on_portrait(canvas, doc):
    header_footer(canvas, doc, A4)


def on_landscape(canvas, doc):
    header_footer(canvas, doc, landscape(A4))


def make_doc(path: Path) -> ReportDoc:
    path.parent.mkdir(parents=True, exist_ok=True)
    portrait_frame = Frame(
        PORTRAIT_MARGIN,
        PORTRAIT_MARGIN,
        A4[0] - 2 * PORTRAIT_MARGIN,
        A4[1] - 2 * PORTRAIT_MARGIN,
        leftPadding=0,
        rightPadding=0,
        topPadding=2 * mm,
        bottomPadding=2 * mm,
    )
    land = landscape(A4)
    landscape_frame = Frame(
        LANDSCAPE_MARGIN,
        LANDSCAPE_MARGIN,
        land[0] - 2 * LANDSCAPE_MARGIN,
        land[1] - 2 * LANDSCAPE_MARGIN,
        leftPadding=0,
        rightPadding=0,
        topPadding=2 * mm,
        bottomPadding=2 * mm,
    )
    cover_frame = Frame(
        22 * mm,
        27 * mm,
        A4[0] - 44 * mm,
        A4[1] - 54 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc = ReportDoc(
        str(path),
        pagesize=A4,
        leftMargin=PORTRAIT_MARGIN,
        rightMargin=PORTRAIT_MARGIN,
        topMargin=PORTRAIT_MARGIN,
        bottomMargin=PORTRAIT_MARGIN,
        title="MORPHOIA - Phase 2 - Candidat de standard expérimental 0.1",
        author=AUTHOR,
        subject=("Graphe de construction paramétrique, IA, interopérabilité CAO et conformité"),
        creator=CREATOR,
        keywords=f"MORPHOIA; {AUTHOR}; brand-1.0; sRGB",
        initialFontName=FONT_TEXT,
        initialFontSize=9.4,
        initialLeading=13.6,
        lang="fr-FR",
        invariant=1,
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="cover", pagesize=A4, frames=[cover_frame], onPage=on_cover),
            PageTemplate(id="portrait", pagesize=A4, frames=[portrait_frame], onPage=on_portrait),
            PageTemplate(
                id="landscape", pagesize=land, frames=[landscape_frame], onPage=on_landscape
            ),
        ]
    )
    return doc


def cover_story():
    return [
        Spacer(1, 76 * mm),
        Paragraph("PHASE 2  /  SPÉCIFICATION ET PROTOTYPE DE RÉFÉRENCE", ST["cover_kicker"]),
        Paragraph(
            "Candidat de standard<br/>expérimental 0.1",
            ST["cover_title"],
        ),
        Paragraph(
            "Reconstruction, modification, validation et génération de modèles CAO "
            "paramétriques par l'Homme et par l'IA",
            ST["cover_subtitle"],
        ),
        Rule(INDIGO, 2, 8),
        Spacer(1, 8 * mm),
        Paragraph(
            f"<b>Auteurs</b> : {AUTHOR_DISPLAY}<br/>"
            "<b>Version du document</b> : 0.1 expérimentale<br/>"
            "<b>Date</b> : 3 août 2026<br/>"
            "<b>Autorité d'échange visée</b> : STEP AP242 et ressources ISO 10303<br/>"
            "<b>Statut</b> : proposition testable, non gelée et non normative",
            ST["cover_meta"],
        ),
        Spacer(1, 24 * mm),
        Paragraph(
            "La stabilisation est interdite avant exécution P1/P2 sur deux backends, "
            "publication de la conformité et bénéfice industriel mesuré.",
            ST["cover_meta"],
        ),
        NextPageTemplate("portrait"),
        PageBreak(),
        Paragraph("Table des matières", ST["h1"]),
        parse_toc(),
        PageBreak(),
    ]


def parse_toc():
    from reportlab.platypus.tableofcontents import TableOfContents

    toc = TableOfContents(
        tableStyle=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("FONTNAME", (0, 0), (-1, -1), FONT_TEXT),
            ]
        )
    )
    toc.levelStyles = [ST["toc1"], ST["toc2"], ST["toc3"]]
    return toc


def source_text() -> str:
    documents: list[str] = []
    missing: list[str] = []
    for relative in CHAPTERS:
        path = PHASE2 / relative
        if not path.is_file():
            missing.append(relative)
            continue
        content = path.read_text(encoding="utf-8")
        if path.suffix == ".ebnf":
            content = "# Grammaire EBNF complète\n\n```ebnf\n" + content.rstrip() + "\n```\n"
        documents.append(content.rstrip())
    if missing:
        raise SystemExit("Missing Phase 2 source files: " + ", ".join(missing))
    return "\n\n[[PAGEBREAK]]\n\n".join(documents) + "\n"


def build() -> None:
    doc = make_doc(OUTPUT)
    portrait_width = A4[0] - 2 * PORTRAIT_MARGIN
    landscape_width = landscape(A4)[0] - 2 * LANDSCAPE_MARGIN
    story = cover_story() + parse_markdown(source_text(), portrait_width, landscape_width)
    doc.multiBuild(story, maxPasses=40, canvasmaker=BrandedCanvas)
    print(OUTPUT)


if __name__ == "__main__":
    build()
