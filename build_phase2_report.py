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
)

from build_report import (
    CYAN,
    LIGHT,
    MID,
    NAVY,
    NAVY_2,
    ORANGE,
    ST,
    TEAL,
    ReportDoc,
    Rule,
    parse_markdown,
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
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    canvas.setFillColor(NAVY_2)
    canvas.circle(width * 0.86, height * 0.83, 76 * mm, stroke=0, fill=1)
    canvas.setFillColor(TEAL)
    canvas.circle(width * 0.91, height * 0.84, 55 * mm, stroke=0, fill=1)
    canvas.setFillColor(ORANGE)
    canvas.rect(0, 0, 7 * mm, height, stroke=0, fill=1)
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(1.2)
    for index in range(8):
        y = 29 * mm + index * 5 * mm
        canvas.line(22 * mm, y, 76 * mm + index * 6 * mm, y)
    canvas.setTitle("MORPHOIA - Phase 2 - Candidat de standard expérimental 0.1")
    canvas.setAuthor("Olivier Ami")
    canvas.setSubject("Graphe de construction paramétrique, IA, interopérabilité CAO et conformité")
    canvas.restoreState()


def header_footer(canvas, doc, page_size):
    width, height = page_size
    canvas.saveState()
    canvas.setStrokeColor(LIGHT)
    canvas.setLineWidth(0.5)
    canvas.line(17 * mm, height - 13 * mm, width - 17 * mm, height - 13 * mm)
    canvas.setFont("DV-Bold", 6.7)
    canvas.setFillColor(NAVY)
    canvas.drawString(17 * mm, height - 10 * mm, "MORPHOIA  /  PHASE 2  /  CANDIDAT 0.1")
    section = getattr(doc, "current_section", "Spécification expérimentale")
    if len(section) > 82:
        section = section[:79] + "..."
    canvas.setFont("DV", 6.7)
    canvas.setFillColor(MID)
    canvas.drawRightString(width - 17 * mm, height - 10 * mm, section)
    canvas.line(17 * mm, 12 * mm, width - 17 * mm, 12 * mm)
    canvas.setFont("DV", 6.5)
    canvas.drawString(17 * mm, 8 * mm, "Candidat expérimental - non normatif - 3 août 2026")
    canvas.setFont("DV-Bold", 6.5)
    canvas.drawRightString(width - 17 * mm, 8 * mm, f"{canvas.getPageNumber() - 1:02d}")
    canvas.restoreState()


def on_portrait(canvas, doc):
    header_footer(canvas, doc, A4)


def on_landscape(canvas, doc):
    header_footer(canvas, doc, landscape(A4))


def make_doc(path: Path) -> ReportDoc:
    path.parent.mkdir(parents=True, exist_ok=True)
    portrait_frame = Frame(
        17 * mm,
        17 * mm,
        A4[0] - 34 * mm,
        A4[1] - 34 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=2 * mm,
        bottomPadding=2 * mm,
    )
    land = landscape(A4)
    landscape_frame = Frame(
        17 * mm,
        17 * mm,
        land[0] - 34 * mm,
        land[1] - 34 * mm,
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
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title="MORPHOIA - Phase 2 - Candidat de standard expérimental 0.1",
        author="Olivier Ami",
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
        Spacer(1, 48 * mm),
        Paragraph("MORPHOIA  /  SPÉCIFICATION ET PROTOTYPE DE RÉFÉRENCE", ST["cover_kicker"]),
        Paragraph(
            "MORPHOIA<br/>Phase 2 - Candidat de standard expérimental 0.1",
            ST["cover_title"],
        ),
        Paragraph(
            "Reconstruction, modification, validation et génération de modèles CAO "
            "paramétriques par l'Homme et par l'IA",
            ST["cover_subtitle"],
        ),
        Spacer(1, 9 * mm),
        Rule(CYAN, 2, 8),
        Spacer(1, 5 * mm),
        Paragraph(
            "<b>Projet et auteur</b> : MORPHOIA - Olivier Ami<br/>"
            "<b>Version du document</b> : 0.1 expérimentale<br/>"
            "<b>Date</b> : 3 août 2026<br/>"
            "<b>Autorité d'échange visée</b> : STEP AP242 et ressources ISO 10303<br/>"
            "<b>Statut</b> : proposition testable, non gelée et non normative",
            ST["cover_meta"],
        ),
        Spacer(1, 30 * mm),
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

    toc = TableOfContents()
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
    portrait_width = A4[0] - 34 * mm
    landscape_width = landscape(A4)[0] - 34 * mm
    story = cover_story() + parse_markdown(source_text(), portrait_width, landscape_width)
    doc.multiBuild(story, maxPasses=40)
    print(OUTPUT)


if __name__ == "__main__":
    build()
