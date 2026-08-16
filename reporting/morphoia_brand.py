"""Canonical MORPHOIA visual identity for generated PDF documents.

The vector logo and wordmark are always read from the official SVG masters.  The
small renderer below supports the exact path commands used by those masters and
keeps the mark vectorial in generated PDFs.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = ROOT / "assets" / "brand"
FONT_DIR = BRAND_DIR / "fonts"
LOGO_SVG = BRAND_DIR / "morphoia-logo.svg"
WORDMARK_SVG = BRAND_DIR / "morphoia-typographie.svg"

BRAND_NAME = "MORPHOIA"
BRAND_VERSION = "1.0"
AUTHORS = ("Louis Manhès", "Olivier Ami")
AUTHOR = "; ".join(AUTHORS)
AUTHOR_DISPLAY = " et ".join(AUTHORS)
BASELINE = "DESIGN INTENT. PARAMETRIC REALITY."
CREATOR = "MORPHOIA document pipeline 1.0"

EXPECTED_MASTER_SHA256 = {
    LOGO_SVG: "1ada94d18db5a0003db972a5f54e6ade13ba6843fbfd7efe8c130745800714c3",
    WORDMARK_SVG: "abc0d796aa4fc7314acce12828282b644f1a896269243a8bb7a5396fef2433c4",
}

# Official sRGB palette.  The brand guide states that these RGB values prevail;
# CMYK/Pantone equivalents remain subject to press proofing.
SPACE = HexColor("#080F19")
GRAPHITE = HexColor("#141A26")
ARDOISE = HexColor("#2A3442")
BRUME = HexColor("#E6E9F2")
WHITE = HexColor("#FFFFFF")
AZUR = HexColor("#00C2FF")
INDIGO = HexColor("#5A62F6")
VIOLET = HexColor("#885CF6")
CORAIL = HexColor("#FF8A65")
AMBRE = HexColor("#FFC857")
GRADIENT_CYAN = HexColor("#6DDFF5")
GRADIENT_MAUVE = HexColor("#D795EF")
GRADIENT_SHADE = HexColor("#0000BA")

FONT_TITLE = "MOR-Aldrich"
FONT_TEXT = "MOR-Barlow"
FONT_TEXT_LIGHT = "MOR-Barlow-Light"
FONT_TEXT_MEDIUM = "MOR-Barlow-Medium"
FONT_TEXT_SEMIBOLD = "MOR-Barlow-SemiBold"
FONT_TEXT_BOLD = "MOR-Barlow-Bold"
FONT_TEXT_ITALIC = "MOR-Barlow-Italic"
FONT_TEXT_BOLD_ITALIC = "MOR-Barlow-BoldItalic"

PORTRAIT_MARGIN = 18 * mm
LANDSCAPE_MARGIN = 17 * mm

_SVG_NS = "{http://www.w3.org/2000/svg}"
_PATH_TOKEN = re.compile(r"[MLCZ]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_TRANSFORM = re.compile(r"(translate|scale)\s*\(([^)]*)\)")
_SYMBOL_VIEWBOX = (219.0, 252.0, 606.0, 568.0)


class BrandedCanvas(Canvas):
    """Canvas whose initial resource is the embedded Barlow font, not Helvetica."""

    def __init__(self, *args, **kwargs):
        register_fonts()
        kwargs.setdefault("initialFontName", FONT_TEXT)
        kwargs.setdefault("initialFontSize", 9.4)
        super().__init__(*args, **kwargs)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def verify_brand_assets() -> None:
    """Fail closed if a canonical brand master is missing or altered."""

    for path, expected in EXPECTED_MASTER_SHA256.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing official MORPHOIA asset: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"Official MORPHOIA asset changed: {path} ({actual} != {expected})")


def register_fonts() -> None:
    """Register the bundled OFL fonts with no system-font fallback."""

    verify_brand_assets()
    files = {
        FONT_TITLE: "Aldrich-Regular.ttf",
        FONT_TEXT: "Barlow-Regular.ttf",
        FONT_TEXT_LIGHT: "Barlow-Light.ttf",
        FONT_TEXT_MEDIUM: "Barlow-Medium.ttf",
        FONT_TEXT_SEMIBOLD: "Barlow-SemiBold.ttf",
        FONT_TEXT_BOLD: "Barlow-Bold.ttf",
        FONT_TEXT_ITALIC: "Barlow-Italic.ttf",
        FONT_TEXT_BOLD_ITALIC: "Barlow-BoldItalic.ttf",
    }
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename in files.items():
        if name in registered:
            continue
        path = FONT_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing bundled MORPHOIA font: {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        FONT_TEXT,
        normal=FONT_TEXT,
        bold=FONT_TEXT_BOLD,
        italic=FONT_TEXT_ITALIC,
        boldItalic=FONT_TEXT_BOLD_ITALIC,
    )


@lru_cache(maxsize=4)
def _svg_data(path: str) -> tuple[tuple[float, float, float, float], tuple[dict, ...]]:
    root = ET.parse(path).getroot()
    viewbox = tuple(float(value) for value in root.attrib["viewBox"].split())
    groups: list[dict] = []
    for group in root.findall(f"{_SVG_NS}g"):
        groups.append(
            {
                "transform": group.attrib.get("transform", ""),
                "paths": tuple(item.attrib["d"] for item in group.findall(f"{_SVG_NS}path")),
            }
        )
    return viewbox, tuple(groups)


def _append_svg_path(path, data: str) -> None:
    tokens = _PATH_TOKEN.findall(data)
    index = 0
    command: str | None = None
    while index < len(tokens):
        token = tokens[index]
        if token in {"M", "L", "C", "Z"}:
            command = token
            index += 1
            if command == "Z":
                path.close()
                command = None
                continue
        if command is None:
            raise ValueError(f"Invalid SVG path near token {token!r}")
        if command in {"M", "L"}:
            if index + 2 > len(tokens):
                raise ValueError("Incomplete SVG point")
            x, y = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            if command == "M":
                path.moveTo(x, y)
                command = "L"
            else:
                path.lineTo(x, y)
        elif command == "C":
            if index + 6 > len(tokens):
                raise ValueError("Incomplete SVG cubic curve")
            values = [float(value) for value in tokens[index : index + 6]]
            index += 6
            path.curveTo(*values)


def _combined_path(canvas, path_data: Iterable[str]):
    path = canvas.beginPath()
    for data in path_data:
        _append_svg_path(path, data)
    return path


def _apply_viewbox(canvas, x: float, y: float, width: float, height: float, viewbox) -> None:
    vx, vy, vw, vh = viewbox
    canvas.translate(x, y + height)
    canvas.scale(width / vw, -height / vh)
    canvas.translate(-vx, -vy)


def _apply_svg_transform(canvas, transform: str) -> None:
    for name, values_text in _TRANSFORM.findall(transform):
        values = [float(value) for value in re.split(r"[ ,]+", values_text.strip()) if value]
        if name == "translate":
            canvas.translate(values[0], values[1] if len(values) > 1 else 0)
        elif name == "scale":
            canvas.scale(values[0], values[1] if len(values) > 1 else values[0])


def _draw_group(canvas, group: dict, color: Color) -> None:
    canvas.saveState()
    _apply_svg_transform(canvas, group["transform"])
    canvas.setFillColor(color)
    canvas.drawPath(_combined_path(canvas, group["paths"]), stroke=0, fill=1, fillMode=0)
    canvas.restoreState()


def _clip_group(canvas, group: dict) -> None:
    _apply_svg_transform(canvas, group["transform"])
    canvas.clipPath(_combined_path(canvas, group["paths"]), stroke=0, fill=0, fillMode=0)


def _draw_gradient_symbol(canvas, x: float, y: float, width: float, height: float, viewbox) -> None:
    _, groups = _svg_data(str(LOGO_SVG))

    canvas.saveState()
    _apply_viewbox(canvas, x, y, width, height, viewbox)
    _clip_group(canvas, groups[0])
    canvas.linearGradient(
        219.0,
        0,
        824.0,
        0,
        [GRADIENT_CYAN, GRADIENT_MAUVE],
        positions=[0, 1],
    )
    canvas.restoreState()

    # PDF axial shadings do not vary opacity.  Sixty-four clipped vector strips
    # reproduce the official 0 -> 37.5% vertical blue overlay without rasterising.
    canvas.saveState()
    _apply_viewbox(canvas, x, y, width, height, viewbox)
    _clip_group(canvas, groups[1])
    top, bottom = 252.0, 820.0
    steps = 64
    strip = (bottom - top) / steps
    canvas.setFillColor(GRADIENT_SHADE)
    for index in range(steps):
        alpha = 0.375 * (index + 0.5) / steps
        canvas.setFillAlpha(alpha)
        canvas.rect(218.5, top + index * strip, 607.0, strip + 0.15, stroke=0, fill=1)
    canvas.restoreState()


def draw_full_logo(canvas, x: float, y: float, width: float) -> float:
    """Draw the official dark-background lockup and return its height."""

    verify_brand_assets()
    viewbox, groups = _svg_data(str(LOGO_SVG))
    height = width * viewbox[3] / viewbox[2]
    _draw_gradient_symbol(canvas, x, y, width, height, viewbox)

    canvas.saveState()
    _apply_viewbox(canvas, x, y, width, height, viewbox)
    _draw_group(canvas, groups[2], WHITE)
    canvas.restoreState()
    return height


def draw_symbol(
    canvas,
    x: float,
    y: float,
    width: float,
    *,
    color: Color = INDIGO,
    gradient: bool = False,
) -> float:
    """Draw the exact official symbol, cropped from the canonical SVG."""

    verify_brand_assets()
    height = width * _SYMBOL_VIEWBOX[3] / _SYMBOL_VIEWBOX[2]
    if gradient:
        _draw_gradient_symbol(canvas, x, y, width, height, _SYMBOL_VIEWBOX)
        return height
    _, groups = _svg_data(str(LOGO_SVG))
    canvas.saveState()
    _apply_viewbox(canvas, x, y, width, height, _SYMBOL_VIEWBOX)
    _draw_group(canvas, groups[0], color)
    canvas.restoreState()
    return height


def draw_wordmark(canvas, x: float, y: float, width: float, *, color: Color = ARDOISE) -> float:
    """Draw the official vector wordmark in a permitted monochrome colour."""

    verify_brand_assets()
    viewbox, groups = _svg_data(str(WORDMARK_SVG))
    height = width * viewbox[3] / viewbox[2]
    canvas.saveState()
    _apply_viewbox(canvas, x, y, width, height, viewbox)
    _draw_group(canvas, groups[0], color)
    canvas.restoreState()
    return height


def set_pdf_metadata(canvas, *, title: str, subject: str) -> None:
    canvas.setTitle(title)
    canvas.setAuthor(AUTHOR)
    canvas.setSubject(subject)
    canvas.setCreator(CREATOR)
    canvas.setKeywords(f"MORPHOIA; {AUTHOR}; brand-{BRAND_VERSION}; sRGB")


def _draw_construction_motif(canvas, page_width: float, page_height: float) -> None:
    """One restrained isometric construction motif for report covers."""

    canvas.saveState()
    canvas.setStrokeColor(INDIGO)
    canvas.setStrokeAlpha(0.20)
    canvas.setLineWidth(0.8)
    cx = page_width - 48 * mm
    cy = page_height - 63 * mm
    dx = 28 * mm
    dy = 16 * mm
    depth = 38 * mm
    top = (cx, cy + dy)
    right = (cx + dx, cy)
    bottom = (cx, cy - dy)
    left = (cx - dx, cy)
    points = [top, right, bottom, left, top]
    for start, end in pairwise(points):
        canvas.line(start[0], start[1], end[0], end[1])
        canvas.line(start[0], start[1], start[0], start[1] - depth)
        canvas.line(start[0], start[1] - depth, end[0], end[1] - depth)
    canvas.line(top[0], top[1], bottom[0], bottom[1] - depth)
    canvas.line(left[0], left[1], right[0], right[1] - depth)
    canvas.setFillAlpha(1)
    canvas.setFillColor(AZUR)
    canvas.circle(top[0], top[1], 1.4, stroke=0, fill=1)
    canvas.restoreState()


def draw_cover_base(
    canvas,
    page_size,
    *,
    title: str,
    subject: str,
    logo_width: float = 56 * mm,
) -> None:
    """Draw the shared branded cover background, official lockup and metadata."""

    register_fonts()
    width, height = page_size
    canvas.saveState()
    canvas.setFillColor(SPACE)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    _draw_construction_motif(canvas, width, height)

    logo_height = logo_width * _svg_data(str(LOGO_SVG))[0][3] / _svg_data(str(LOGO_SVG))[0][2]
    draw_full_logo(canvas, 24 * mm, height - 24 * mm - logo_height, logo_width)

    text = canvas.beginText(24 * mm, 18 * mm)
    text.setFont(FONT_TEXT_SEMIBOLD, 7.8)
    text.setFillColor(BRUME)
    text.setCharSpace(3)
    text.textLine(BASELINE)
    canvas.drawText(text)
    set_pdf_metadata(canvas, title=title, subject=subject)
    canvas.restoreState()


def draw_page_chrome(
    canvas,
    doc,
    page_size,
    *,
    label: str,
    footer: str,
) -> None:
    """Draw shared header/footer chrome on portrait or landscape content pages."""

    register_fonts()
    width, height = page_size
    margin = PORTRAIT_MARGIN if height >= width else LANDSCAPE_MARGIN
    canvas.saveState()

    symbol_width = 6.4 * mm
    draw_symbol(
        canvas,
        margin,
        height - 14.0 * mm,
        symbol_width,
        color=INDIGO,
        gradient=False,
    )
    canvas.setFont(FONT_TEXT_SEMIBOLD, 7.8)
    canvas.setFillColor(SPACE)
    canvas.drawString(margin + 10 * mm, height - 10.7 * mm, label)

    section = getattr(doc, "current_section", "")
    if len(section) > 82:
        section = section[:79] + "..."
    canvas.setFont(FONT_TEXT, 7.8)
    canvas.setFillColor(ARDOISE)
    canvas.drawRightString(width - margin, height - 10.7 * mm, section)
    canvas.setStrokeColor(BRUME)
    canvas.setLineWidth(0.5)
    canvas.line(margin, height - 17 * mm, width - margin, height - 17 * mm)

    canvas.line(margin, 13 * mm, width - margin, 13 * mm)
    canvas.setFont(FONT_TEXT, 7)
    canvas.setFillColor(ARDOISE)
    canvas.drawString(margin, 8 * mm, f"{AUTHOR_DISPLAY}  ·  {footer}")

    page_number = max(1, canvas.getPageNumber() - 1)
    page_x = width - margin
    canvas.setFont(FONT_TEXT_SEMIBOLD, 7)
    canvas.drawRightString(page_x, 8 * mm, f"{page_number:02d}")
    wordmark_width = 26 * mm
    draw_wordmark(
        canvas,
        page_x - wordmark_width - 10 * mm,
        7.4 * mm,
        wordmark_width,
        color=ARDOISE,
    )
    canvas.restoreState()
