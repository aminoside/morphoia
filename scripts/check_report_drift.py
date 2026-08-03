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
            }
        )

    return {
        "title": metadata.get("/Title", ""),
        "author": metadata.get("/Author", ""),
        "subject": metadata.get("/Subject", ""),
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
