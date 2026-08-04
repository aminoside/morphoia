#!/usr/bin/env python3
"""Build the MORPHOIA Phase 1 feasibility study as a searchable PDF."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    LongTable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
    XPreformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents

from reporting.morphoia_brand import (
    AMBRE,
    ARDOISE,
    AUTHOR,
    AZUR,
    BRUME,
    CORAIL,
    CREATOR,
    FONT_TEXT,
    FONT_TEXT_SEMIBOLD,
    FONT_TITLE,
    GRAPHITE,
    INDIGO,
    LANDSCAPE_MARGIN,
    PORTRAIT_MARGIN,
    SPACE,
    WHITE,
    BrandedCanvas,
    draw_cover_base,
    draw_page_chrome,
    register_fonts,
)

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "docs" / "phase1" / "MORPHOIA_phase1_etat_art_faisabilite.md"
OUTPUT = ROOT / "docs" / "phase1" / "MORPHOIA_phase1_etat_art_faisabilite.pdf"

# Backwards-compatible aliases used by the Markdown renderer and Phase 2 builder.
NAVY = SPACE
NAVY_2 = GRAPHITE
TEAL = INDIGO
CYAN = AZUR
ORANGE = AMBRE
PALE = BRUME
PALE_BLUE = BRUME
INK = ARDOISE
MID = ARDOISE
LIGHT = BRUME
VERY_LIGHT = BRUME
RED = CORAIL
GREEN = INDIGO


register_fonts()


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=base["Normal"],
            fontName=FONT_TEXT_SEMIBOLD,
            fontSize=7.8,
            leading=10.9,
            textColor=AZUR,
            spaceAfter=16,
            letterSpacing=1.8,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName=FONT_TITLE,
            fontSize=30,
            leading=33,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=30,
            letterSpacing=0.6,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=base["Normal"],
            fontName=FONT_TEXT,
            fontSize=13,
            leading=18.9,
            textColor=BRUME,
            spaceAfter=24,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta",
            parent=base["Normal"],
            fontName=FONT_TEXT,
            fontSize=9.4,
            leading=13.6,
            textColor=WHITE,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=base["Heading1"],
            fontName=FONT_TITLE,
            fontSize=21,
            leading=26.25,
            textColor=SPACE,
            spaceBefore=16,
            spaceAfter=21,
            letterSpacing=0.6,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            fontName=FONT_TEXT_SEMIBOLD,
            fontSize=12,
            leading=16.2,
            textColor=INDIGO,
            spaceBefore=24,
            spaceAfter=12,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "Heading3",
            parent=base["Heading3"],
            fontName=FONT_TEXT_SEMIBOLD,
            fontSize=10.5,
            leading=14.2,
            textColor=ARDOISE,
            spaceBefore=16,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=9.4,
            leading=13.6,
            textColor=ARDOISE,
            alignment=TA_LEFT,
            spaceAfter=8,
            splitLongWords=False,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=8,
            leading=10.8,
            textColor=ARDOISE,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=9.2,
            leading=13.2,
            textColor=ARDOISE,
            leftIndent=11,
            firstLineIndent=-7,
            bulletIndent=3,
            spaceAfter=4,
        ),
        "number": ParagraphStyle(
            "Number",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=9.2,
            leading=13.2,
            textColor=ARDOISE,
            leftIndent=13,
            firstLineIndent=-10,
            spaceAfter=4,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=9.4,
            leading=13.6,
            textColor=SPACE,
            leftIndent=11,
            rightIndent=6,
            borderColor=INDIGO,
            borderWidth=0,
            borderLeft=3,
            borderPadding=(7, 9, 7, 9),
            backColor=BRUME,
            spaceBefore=6,
            spaceAfter=8,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName=FONT_TEXT_SEMIBOLD,
            fontSize=7,
            leading=9,
            textColor=WHITE,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=6.8,
            leading=8.8,
            textColor=ARDOISE,
        ),
        "table_cell_small": ParagraphStyle(
            "TableCellSmall",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=5.6,
            leading=7.1,
            textColor=ARDOISE,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["BodyText"],
            fontName=FONT_TEXT,
            fontSize=8,
            leading=10.8,
            textColor=ARDOISE,
            alignment=TA_LEFT,
            spaceBefore=2,
            spaceAfter=7,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName=FONT_TEXT,
            fontSize=7.2,
            leading=9.4,
            textColor=SPACE,
            leftIndent=6,
            rightIndent=6,
            borderColor=LIGHT,
            borderWidth=0.5,
            borderPadding=6,
            backColor=BRUME,
            spaceBefore=4,
            spaceAfter=7,
        ),
        "toc1": ParagraphStyle(
            "TOC1",
            parent=base["Normal"],
            fontName=FONT_TEXT_SEMIBOLD,
            fontSize=9,
            leading=12,
            textColor=SPACE,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=4,
        ),
        "toc2": ParagraphStyle(
            "TOC2",
            parent=base["Normal"],
            fontName=FONT_TEXT,
            fontSize=8,
            leading=10.5,
            textColor=ARDOISE,
            leftIndent=13,
            firstLineIndent=0,
            spaceBefore=2,
        ),
        "toc3": ParagraphStyle(
            "TOC3",
            parent=base["Normal"],
            fontName=FONT_TEXT,
            fontSize=7,
            leading=9,
            textColor=ARDOISE,
            leftIndent=26,
            firstLineIndent=0,
            spaceBefore=1,
        ),
    }


ST = styles()


def inline_markup(text: str) -> str:
    """Convert a small safe subset of Markdown to ReportLab paragraph markup."""
    placeholders: list[str] = []

    def link_sub(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        token = f"@@LINK{len(placeholders)}@@"
        safe_label = html.escape(label)
        safe_url = html.escape(url, quote=True)
        placeholders.append(f'<link href="{safe_url}" color="#5A62F6"><u>{safe_label}</u></link>')
        return token

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", link_sub, text)
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(
        r"`([^`]+)`",
        rf'<font name="{FONT_TEXT}" size="7.2">\1</font>',
        escaped,
    )
    escaped = escaped.replace("&lt;br&gt;", "<br/>").replace("&lt;br/&gt;", "<br/>")
    for i, value in enumerate(placeholders):
        escaped = escaped.replace(f"@@LINK{i}@@", value)
    return escaped


class Rule(Flowable):
    def __init__(self, color=TEAL, thickness=1.2, space=8):
        super().__init__()
        self.color = color
        self.thickness = thickness
        self.space = space
        self.height = space

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.height / 2, self._availWidth, self.height / 2)

    def wrap(self, availWidth, availHeight):
        self._availWidth = availWidth
        return availWidth, self.height


class FindingCard(Flowable):
    """Unused visual spacer kept as a hook for future report revisions."""

    def wrap(self, availWidth, availHeight):
        return availWidth, 0

    def draw(self):
        return


class ReportDoc(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        self._heading_counter = 0
        self.current_section = "Synthèse"

    def beforeDocument(self):
        self._heading_counter = 0
        self.current_section = "Synthèse"

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in {
            "Heading1",
            "Heading2",
            "Heading3",
        }:
            level = {"Heading1": 0, "Heading2": 1, "Heading3": 2}[flowable.style.name]
            text = flowable.getPlainText()
            self._heading_counter += 1
            key = f"h{self._heading_counter}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=False)
            self.notify("TOCEntry", (level, text, self.page, key))
            if level == 0:
                self.current_section = text


def on_cover(canvas, doc):
    draw_cover_base(
        canvas,
        A4,
        title="MORPHOIA - Phase 1 - Etat de l'art et etude de faisabilite",
        subject="CAO parametrique, standards, IA et acceleration GPU",
    )


def header_footer(canvas, doc, page_size):
    draw_page_chrome(
        canvas,
        doc,
        page_size,
        label="PHASE 1  /  ÉTAT DE L'ART",
        footer="Rapport arrêté au 3 août 2026",
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
        title="MORPHOIA - Phase 1 - Etat de l'art et étude de faisabilité",
        author=AUTHOR,
        subject="CAO parametrique, standards, IA et acceleration GPU",
        creator=CREATOR,
        keywords="MORPHOIA; Olivier Ami; brand-1.0; sRGB",
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
        Paragraph("PHASE 1  /  REVUE SCIENTIFIQUE ET INDUSTRIELLE", ST["cover_kicker"]),
        Paragraph(
            "État de l’art et<br/>étude de faisabilité",
            ST["cover_title"],
        ),
        Paragraph(
            "Reconstruction paramétrique de pièces mécaniques, interopérabilité CAO, "
            "standards ouverts, intelligence artificielle et accélération GPU",
            ST["cover_subtitle"],
        ),
        Rule(INDIGO, 2, 8),
        Spacer(1, 8 * mm),
        Paragraph(
            "<b>Auteur</b> : Olivier Ami<br/>"
            "<b>Date d’arrêté des recherches</b> : 3 août 2026<br/>"
            "<b>Nature du document</b> : étude de faisabilité, non-spécification<br/>"
            "<b>Statut</b> : décision de cadrage - aucune proposition de nouveau langage",
            ST["cover_meta"],
        ),
        Spacer(1, 24 * mm),
        Paragraph(
            "Analyse de publications, thèses, brevets, normes ISO, formats industriels, "
            "noyaux géométriques, logiciels CAO, projets open source, travaux IA, bibliothèques GPU et SDK.",
            ST["cover_meta"],
        ),
        NextPageTemplate("portrait"),
        PageBreak(),
    ]


def parse_table(lines: list[str], avail_width: float, small=False):
    rows = []
    for raw in lines:
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in rows[1]):
        rows.pop(1)
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]

    lengths = []
    for col in range(ncols):
        vals = [len(re.sub(r"\[[^]]+\]\([^)]+\)", "link", r[col])) for r in rows]
        lengths.append(max(8, min(max(vals), 45)))
    total = sum(lengths)
    min_w = 18 * mm if ncols <= 5 else 12 * mm
    widths = [max(min_w, avail_width * x / total) for x in lengths]
    scale = avail_width / sum(widths)
    widths = [w * scale for w in widths]

    data = []
    cell_style = ST["table_cell_small"] if small or ncols >= 7 else ST["table_cell"]
    for ridx, row in enumerate(rows):
        style = ST["table_header"] if ridx == 0 else cell_style
        data.append([Paragraph(inline_markup(cell), style) for cell in row])

    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, -1), FONT_TEXT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for ridx in range(1, len(data)):
        commands.append(
            ("BACKGROUND", (0, ridx), (-1, ridx), VERY_LIGHT if ridx % 2 == 0 else WHITE)
        )
    table.setStyle(TableStyle(commands))
    return table


def parse_markdown(text: str, portrait_width: float, landscape_width: float):
    story = []
    lines = text.splitlines()
    i = 0
    current_width = portrait_width
    para_buf: list[str] = []

    def flush_para():
        nonlocal para_buf
        if para_buf:
            joined = " ".join(x.strip() for x in para_buf).strip()
            if joined:
                story.append(Paragraph(inline_markup(joined), ST["body"]))
            para_buf = []

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        if stripped == "[[TOC]]":
            flush_para()
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
            story.append(toc)
            i += 1
            continue
        if stripped == "[[PAGEBREAK]]":
            flush_para()
            story.append(PageBreak())
            i += 1
            continue
        if stripped == "[[LANDSCAPE]]":
            flush_para()
            story.extend([NextPageTemplate("landscape"), PageBreak()])
            current_width = landscape_width
            i += 1
            continue
        if stripped == "[[PORTRAIT]]":
            flush_para()
            story.extend([NextPageTemplate("portrait"), PageBreak()])
            current_width = portrait_width
            i += 1
            continue
        if stripped == "---":
            flush_para()
            story.append(Rule())
            i += 1
            continue
        if stripped.startswith("# "):
            flush_para()
            story.append(Paragraph(inline_markup(stripped[2:]), ST["h1"]))
            i += 1
            continue
        if stripped.startswith("## "):
            flush_para()
            story.append(Paragraph(inline_markup(stripped[3:]), ST["h2"]))
            i += 1
            continue
        if stripped.startswith("### "):
            flush_para()
            story.append(Paragraph(inline_markup(stripped[4:]), ST["h3"]))
            i += 1
            continue
        if stripped.startswith("> "):
            flush_para()
            quote = [stripped[2:]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote.append(lines[i].strip()[2:])
                i += 1
            story.append(Paragraph(inline_markup(" ".join(quote)), ST["quote"]))
            continue
        if stripped.startswith("```"):
            flush_para()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i].rstrip("\n"))
                i += 1
            if i >= len(lines):
                raise ValueError("unterminated fenced code block in Markdown source")
            i += 1
            code = "\n".join(code_lines) or " "
            story.append(XPreformatted(html.escape(code), ST["code"]))
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_para()
            table_lines = [stripped]
            i += 1
            while (
                i < len(lines)
                and lines[i].strip().startswith("|")
                and lines[i].strip().endswith("|")
            ):
                table_lines.append(lines[i].strip())
                i += 1
            story.append(
                parse_table(table_lines, current_width, small=current_width > portrait_width)
            )
            story.append(Spacer(1, 5))
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            flush_para()
            story.append(Paragraph("• " + inline_markup(bullet.group(1)), ST["bullet"]))
            i += 1
            continue
        numbered = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if numbered:
            flush_para()
            story.append(
                Paragraph(
                    f"<b>{numbered.group(1)}.</b> " + inline_markup(numbered.group(2)), ST["number"]
                )
            )
            i += 1
            continue
        if stripped.startswith(("_Légende :", "_Note :")):
            flush_para()
            story.append(Paragraph(inline_markup(stripped.strip("_")), ST["caption"]))
            i += 1
            continue
        para_buf.append(stripped)
        i += 1
    flush_para()
    return story


def build():
    if not INPUT.exists():
        raise SystemExit(f"Missing source: {INPUT}")
    doc = make_doc(OUTPUT)
    portrait_width = A4[0] - 2 * PORTRAIT_MARGIN
    landscape_width = landscape(A4)[0] - 2 * LANDSCAPE_MARGIN
    source = INPUT.read_text(encoding="utf-8")
    story = cover_story() + parse_markdown(source, portrait_width, landscape_width)
    doc.multiBuild(story, maxPasses=30, canvasmaker=BrandedCanvas)
    print(OUTPUT)


if __name__ == "__main__":
    build()
