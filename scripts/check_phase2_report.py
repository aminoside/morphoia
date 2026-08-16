#!/usr/bin/env python3
"""Validate the generated MORPHOIA Phase 2 PDF and its normative warnings."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "docs" / "phase2" / "MORPHOIA_phase2_standard_candidate_v0.1.pdf"
EXPECTED_AUTHOR = "Louis Manhès; Olivier Ami"
REQUIRED_TERMS = {
    "MORPHOIA",
    "Louis Manhès",
    "Olivier Ami",
    "candidat expérimental",
    "STEP AP242",
    "Open CASCADE",
    "Parasolid",
    "Topological Naming Problem",
    "Component Justification Record",
    "registre de pertes",
    "deux backends",
    "CUDA",
    "ONNX",
    "EBNF",
}


def main() -> None:
    if not PDF.is_file():
        raise SystemExit(f"Missing report: {PDF}")

    reader = PdfReader(str(PDF))
    metadata = reader.metadata or {}
    title = metadata.get("/Title", "")
    author = metadata.get("/Author", "")

    if "MORPHOIA" not in title or "Phase 2" not in title or "0.1" not in title:
        raise SystemExit(f"Unexpected PDF title: {title!r}")
    if author != EXPECTED_AUTHOR:
        raise SystemExit(f"Unexpected PDF author: {author!r}")
    if len(reader.pages) < 45:
        raise SystemExit(f"Unexpectedly short Phase 2 report: {len(reader.pages)} pages")

    page_texts = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(page_texts)
    missing = sorted(term for term in REQUIRED_TERMS if term.casefold() not in text.casefold())
    if missing:
        raise SystemExit(f"Missing required terms: {', '.join(missing)}")

    blank_pages = [index + 1 for index, page_text in enumerate(page_texts) if not page_text.strip()]
    if blank_pages:
        raise SystemExit(f"Blank pages detected: {blank_pages}")

    links = 0
    for page in reader.pages:
        for annotation in page.get("/Annots") or []:
            if annotation.get_object().get("/Subtype") == "/Link":
                links += 1
    if links < 20:
        raise SystemExit(f"Unexpectedly low link count: {links}")

    if "non normatif" not in text.casefold():
        raise SystemExit("The experimental/non-normative warning is missing")

    print(
        f"Validated {PDF.name}: {len(reader.pages)} pages, {links} links, "
        f"title={title!r}, author={author!r}"
    )


if __name__ == "__main__":
    main()
