#!/usr/bin/env python3
"""Validate the generated MORPHOIA Phase 1 PDF."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "docs" / "phase1" / "MORPHOIA_phase1_etat_art_faisabilite.pdf"
REQUIRED_TERMS = {
    "MORPHOIA",
    "Olivier Ami",
    "STEP",
    "Open CASCADE",
    "Parasolid",
    "FeatureScript",
    "OpenUSD",
    "MLIR",
    "ONNX",
}


def main() -> None:
    if not PDF.is_file():
        raise SystemExit(f"Missing report: {PDF}")

    reader = PdfReader(str(PDF))
    metadata = reader.metadata or {}
    title = metadata.get("/Title", "")
    author = metadata.get("/Author", "")

    if "MORPHOIA" not in title:
        raise SystemExit(f"Unexpected PDF title: {title!r}")
    if author != "Olivier Ami":
        raise SystemExit(f"Unexpected PDF author: {author!r}")
    if len(reader.pages) < 40:
        raise SystemExit(f"Unexpected page count: {len(reader.pages)}")

    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    missing = sorted(term for term in REQUIRED_TERMS if term not in text)
    if missing:
        raise SystemExit(f"Missing required terms: {', '.join(missing)}")

    links = 0
    for page in reader.pages:
        for annotation in page.get("/Annots") or []:
            if annotation.get_object().get("/Subtype") == "/Link":
                links += 1
    if links < 100:
        raise SystemExit(f"Unexpectedly low link count: {links}")

    print(
        f"Validated {PDF.name}: {len(reader.pages)} pages, "
        f"{links} links, title={title!r}, author={author!r}"
    )


if __name__ == "__main__":
    main()
