#!/usr/bin/env python3
"""Validate the official MORPHOIA identity on every PDF tracked by Git."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reports.json"
A4_PORTRAIT = (595.276, 841.89)
A4_LANDSCAPE = tuple(reversed(A4_PORTRAIT))
SUBSET_PREFIX = re.compile(r"^/[A-Z]{6}\+")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tracked_pdfs() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--", "*.pdf"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def normalized_font_name(value: object) -> str:
    return SUBSET_PREFIX.sub("", str(value))


def embedded_font_names(reader: PdfReader) -> tuple[set[str], set[str]]:
    names: set[str] = set()
    unembedded: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        for reference in (resources.get("/Font") or {}).values():
            font = reference.get_object()
            name = normalized_font_name(font.get("/BaseFont", ""))
            if not name:
                continue
            names.add(name)
            descriptor = font.get("/FontDescriptor")
            descriptor = descriptor.get_object() if descriptor else None
            embedded = bool(
                descriptor
                and any(descriptor.get(key) for key in ("/FontFile", "/FontFile2", "/FontFile3"))
            )
            if not embedded:
                unembedded.add(name)
    return names, unembedded


def close_size(actual: tuple[float, float], expected: tuple[float, float]) -> bool:
    return all(abs(left - right) <= 0.75 for left, right in zip(actual, expected))


def validate_report(path: Path, brand: dict) -> tuple[int, set[str]]:
    reader = PdfReader(str(path))
    metadata = reader.metadata or {}
    title = str(metadata.get("/Title", ""))
    author = str(metadata.get("/Author", ""))
    creator = str(metadata.get("/Creator", ""))
    keywords = str(metadata.get("/Keywords", ""))

    if brand["name"] not in title:
        raise SystemExit(f"{path}: missing MORPHOIA in /Title")
    if author != brand["author"]:
        raise SystemExit(f"{path}: unexpected /Author {author!r}")
    if creator != brand["creator"]:
        raise SystemExit(f"{path}: unexpected /Creator {creator!r}")
    if f"brand-{brand['version']}" not in keywords:
        raise SystemExit(f"{path}: missing brand version in /Keywords")

    language = str(reader.trailer["/Root"].get("/Lang", ""))
    if language != "fr-FR":
        raise SystemExit(f"{path}: unexpected document language {language!r}")

    for number, page in enumerate(reader.pages, start=1):
        size = (float(page.mediabox.width), float(page.mediabox.height))
        if not (close_size(size, A4_PORTRAIT) or close_size(size, A4_LANDSCAPE)):
            raise SystemExit(f"{path}: page {number} is not A4: {size}")

    cover_text = reader.pages[0].extract_text() or ""
    for required in (brand["author"], brand["baseline"]):
        if required not in cover_text:
            raise SystemExit(f"{path}: cover is missing visible {required!r}")

    cover_resources = reader.pages[0].get("/Resources") or {}
    if not (cover_resources.get("/Shading") or {}):
        raise SystemExit(f"{path}: cover lacks the vector signature gradient")

    fonts, unembedded = embedded_font_names(reader)
    if not any("Aldrich-Regular" in name for name in fonts):
        raise SystemExit(f"{path}: Aldrich is missing")
    if not any("Barlow-Regular" in name for name in fonts):
        raise SystemExit(f"{path}: Barlow is missing")
    disallowed = sorted(name for name in fonts if "Aldrich" not in name and "Barlow" not in name)
    if disallowed:
        raise SystemExit(f"{path}: disallowed fonts: {', '.join(disallowed)}")
    if unembedded:
        raise SystemExit(f"{path}: unembedded fonts: {', '.join(sorted(unembedded))}")

    return len(reader.pages), fonts


def validate_brand_document(entry: dict, brand: dict) -> int:
    path = ROOT / entry["path"]
    if not path.is_file():
        raise SystemExit(f"Missing brand document: {path}")
    actual = sha256(path)
    if actual != entry["sha256"]:
        raise SystemExit(f"Brand document changed: {path} ({actual})")

    reader = PdfReader(str(path))
    metadata = reader.metadata or {}
    if str(metadata.get("/Title", "")) != entry["title"]:
        raise SystemExit(f"{path}: unexpected /Title")
    if (
        str(metadata.get("/Author", "")) != entry["author"]
        or entry["author"] != brand["author"]
    ):
        raise SystemExit(f"{path}: unexpected /Author")
    if f"brand-{brand['version']}" not in str(metadata.get("/Keywords", "")):
        raise SystemExit(f"{path}: missing brand version in /Keywords")
    if str(reader.trailer["/Root"].get("/Lang", "")) != "fr-FR":
        raise SystemExit(f"{path}: unexpected document language")

    for number, page in enumerate(reader.pages, start=1):
        size = (float(page.mediabox.width), float(page.mediabox.height))
        if not (close_size(size, A4_PORTRAIT) or close_size(size, A4_LANDSCAPE)):
            raise SystemExit(f"{path}: page {number} is not A4: {size}")

    cover_text = reader.pages[0].extract_text() or ""
    if brand["baseline"] not in cover_text:
        raise SystemExit(f"{path}: cover lacks the MORPHOIA baseline")
    cover_resources = reader.pages[0].get("/Resources") or {}
    if not (cover_resources.get("/XObject") or {}):
        raise SystemExit(f"{path}: cover lacks the MORPHOIA visual identity")
    return len(reader.pages)


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    brand = data["brand"]
    if data.get("schema_version") != 1:
        raise SystemExit("Unsupported reports.json schema")

    for path_key, digest_key in (
        ("logo", "logo_sha256"),
        ("wordmark", "wordmark_sha256"),
    ):
        asset = ROOT / brand[path_key]
        if not asset.is_file():
            raise SystemExit(f"Missing official brand asset: {asset}")
        actual = sha256(asset)
        if actual != brand[digest_key]:
            raise SystemExit(f"Official brand asset changed: {asset} ({actual})")

    brand_documents = data.get("brand_documents", [])
    declared = [entry["path"] for entry in data["reports"]]
    declared.extend(entry["path"] for entry in brand_documents)
    if len(declared) != len(set(declared)):
        raise SystemExit("Duplicate PDF path in reports.json")
    tracked = tracked_pdfs()
    if sorted(declared) != tracked:
        missing = sorted(set(tracked) - set(declared))
        absent = sorted(set(declared) - set(tracked))
        raise SystemExit(f"PDF manifest mismatch; undeclared={missing}, not-tracked={absent}")

    for entry in data["reports"]:
        for key in ("generator", "validator"):
            support = ROOT / entry[key]
            if not support.is_file():
                raise SystemExit(f"Missing {key} for {entry['path']}: {support}")
        report = ROOT / entry["path"]
        pages, fonts = validate_report(report, brand)
        print(
            f"Branded {entry['path']}: {pages} pages, author={brand['author']!r}, "
            f"fonts={','.join(sorted(fonts))}"
        )

    for entry in brand_documents:
        pages = validate_brand_document(entry, brand)
        print(
            f"Reference {entry['path']}: {pages} pages, author={entry['author']!r}, "
            f"sha256={entry['sha256']}"
        )


if __name__ == "__main__":
    main()
