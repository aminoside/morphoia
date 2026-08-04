#!/usr/bin/env python3
"""Compare the committed and regenerated MORPHOIA reports semantically."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader


def report_signature(path: Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    metadata = reader.metadata or {}
    pages: list[dict[str, Any]] = []

    for page in reader.pages:
        content = page.get_contents()
        content_data = content.get_data() if content else b""
        resources = page.get("/Resources") or {}
        fonts = []
        for reference in (resources.get("/Font") or {}).values():
            font = reference.get_object()
            fonts.append(str(font.get("/BaseFont", "")))

        images: list[str] = []
        for reference in (resources.get("/XObject") or {}).values():
            item = reference.get_object()
            if item.get("/Subtype") == "/Image":
                images.append(hashlib.sha256(item.get_data()).hexdigest())

        external_links: list[str] = []
        link_count = 0
        for annotation in page.get("/Annots") or []:
            item = annotation.get_object()
            if item.get("/Subtype") != "/Link":
                continue
            link_count += 1
            action = item.get("/A")
            if action and action.get("/URI"):
                external_links.append(str(action.get("/URI")))

        pages.append(
            {
                "text": page.extract_text() or "",
                "width": round(float(page.mediabox.width), 3),
                "height": round(float(page.mediabox.height), 3),
                "link_count": link_count,
                "external_links": external_links,
                "content_sha256": hashlib.sha256(content_data).hexdigest(),
                "fonts": sorted(fonts),
                "image_sha256": sorted(images),
                "shading_count": len(resources.get("/Shading") or {}),
            }
        )

    return {
        "title": metadata.get("/Title", ""),
        "author": metadata.get("/Author", ""),
        "subject": metadata.get("/Subject", ""),
        "creator": metadata.get("/Creator", ""),
        "keywords": metadata.get("/Keywords", ""),
        "language": str(reader.trailer["/Root"].get("/Lang", "")),
        "pages": pages,
    }


def digest(signature: dict[str, Any]) -> str:
    payload = json.dumps(signature, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_report_drift.py COMMITTED.pdf REBUILT.pdf")

    committed = Path(sys.argv[1])
    rebuilt = Path(sys.argv[2])
    before = report_signature(committed)
    after = report_signature(rebuilt)

    if before != after:
        raise SystemExit(
            "The regenerated report differs semantically from the committed PDF: "
            f"{digest(before)} != {digest(after)}"
        )

    print(f"No semantic PDF drift: {digest(after)}")


if __name__ == "__main__":
    main()
