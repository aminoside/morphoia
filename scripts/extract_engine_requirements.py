#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Extract and validate the immutable Morphoia Engine requirements catalogue.

The source PDF is authoritative. Normal validation consumes a hash-pinned,
layout-preserving text artifact and therefore does not require Poppler. The
explicit ``--extract-pdf`` audit compares a fresh ``pdftotext -layout`` result
with that artifact without rewriting it. Immutable baseline records and
mutable project tracking deliberately live in different files: regeneration
may replace the former, but it never rewrites an existing tracking overlay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable


SOURCE_PDF_SHA256 = "40cdb3288e7b1a38a557d1459147aed7ac1d5646aaa5d6ab09a287abc9b22263"
EXTRACTION_SHA256 = "e31699cb803edb1b86d01b04a230fd71418a5865965313bac376758f3e0f1a10"
LAYOUT_ARTIFACT_SHA256 = "de8444574a59e1520222062587bc6c55f7184cf0e384d7d499f5ea24ad653175"
RECORDS_SHA256 = "5e65c204e35ba98453669095ede587b2573d3a6f35d7841d16d26104794131ba"
# Digest of every immutable record field, including source coordinates,
# quality flags, derived fields, and per-record hashes. This is intentionally
# distinct from the compact, published RECORDS_SHA256 above.
IMMUTABLE_RECORDS_SHA256 = "b846a2f284ad0510b43ca6fdba8ad4fae7d1b40daf2f77305c8153e6a9de4072"

CATALOGUE_SCHEMA_VERSION = "1.1.0"
TRACKING_SCHEMA_VERSION = "1.0.0"
CATALOGUE_SCHEMA_REF = "./requirements-catalog.schema.json"
TRACKING_SCHEMA_REF = "./requirements-tracking.schema.json"
SOURCE_PDF_PATH = (
    "docs/engine/baselines/"
    "Morphoia_Engine_Cahier_des_charges_technique_v0.1.pdf"
)
LAYOUT_ARTIFACT_PATH = (
    "spec/requirements/"
    "Morphoia_Engine_Cahier_des_charges_technique_v0.1.layout.txt"
)
LAYOUT_NORMALIZATION = "remove_one_lf_after_terminal_form_feed"
STATUS_VOCABULARY = ["PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"]

ROW_RE = re.compile(
    r"^\s*(MOR-[A-Z]{2,4}-\d{3})\s+(.*?)\s{2,}"
    r"(MUST|SHOULD|MAY)\s+"
    r"(P[0-4](?:-P[0-4]|\+)?)\s+"
    r"([TIAD](?:/[TIAD])*)\s*$"
)
CONTINUATION_RE = re.compile(r"^ {26}(\S.*)$")
REQUIREMENT_ID_RE = re.compile(r"^MOR-([A-Z]{2,4})-(\d{3})$")

EXPECTED_FAMILY_COUNTS = {
    "SCP": 15,
    "ARC": 14,
    "DEV": 16,
    "API": 18,
    "IR": 18,
    "CAS": 12,
    "IO": 19,
    "DIC": 14,
    "VIS": 10,
    "CMP": 19,
    "AI": 17,
    "MVX": 18,
    "PLG": 10,
    "SAL": 27,
    "HPC": 16,
    "SEC": 20,
    "PER": 16,
    "QA": 18,
    "LIC": 13,
    "GOV": 10,
}
EXPECTED_PRIORITIES = {"MUST": 305, "SHOULD": 10, "MAY": 5}
EXPECTED_PHASES = {
    "P0-P1": 136,
    "P0-P2": 87,
    "P0-P3": 30,
    "P0-P4": 17,
    "P0": 14,
    "P1-P2": 10,
    "P1": 7,
    "P2": 6,
    "P3": 5,
    "P2+": 3,
    "P4": 2,
    "P2-P3": 2,
    "P3+": 1,
}
EXPECTED_PROOFS = {
    "T/I": 121,
    "T": 55,
    "T/A": 47,
    "I/T": 40,
    "I": 21,
    "T/I/A/D": 17,
    "T/D": 13,
    "D": 6,
}
MODAL_PRIORITY_MISMATCHES = {
    "MOR-IR-004",
    "MOR-AI-015",
    "MOR-LIC-003",
    "MOR-CMP-008",
    "MOR-HPC-016",
    "MOR-MVX-015",
    "MOR-SAL-003",
    "MOR-PER-011",
    "MOR-CAS-002",
    "MOR-VIS-008",
}

PROOF_NAMES = {
    "T": "test",
    "I": "inspection",
    "A": "analysis",
    "D": "demonstration",
}

FAMILY_TRACKING = {
    "SCP": ("spec", "WP0"),
    "ARC": ("architecture", "WP0"),
    "DEV": ("build", "WP0"),
    "API": ("capi", "WP1"),
    "IR": ("core/ir", "WP1"),
    "CAS": ("core/cas", "WP1"),
    "IO": ("io", "WP2"),
    "DIC": ("io/dicom", "WP3"),
    "VIS": ("io/vtk-and-connectors", "WP6"),
    "CMP": ("compute-and-workers", "WP4"),
    "AI": ("ai-interop", "WP4"),
    "MVX": ("plugins/mvx", "WP4"),
    "PLG": ("plugins/sdk", "WP6"),
    "SAL": ("salome-protocol-and-agent", "WP5"),
    "HPC": ("hpc", "WP7"),
    "SEC": ("security", "WP8"),
    "PER": ("performance", "WP8"),
    "QA": ("quality-and-conformance", "WP8"),
    "LIC": ("licensing", "WP0"),
    "GOV": ("governance", "WP0"),
}

BASELINE_METADATA = {
    "title": "Morphoia Engine - Cahier des charges technique",
    "document_version": "0.1",
    "date": "2026-08-06",
    "language": "fr",
    "source_pdf_sha256": SOURCE_PDF_SHA256,
    "layout_artifact": LAYOUT_ARTIFACT_PATH,
    "layout_artifact_sha256": LAYOUT_ARTIFACT_SHA256,
    "layout_normalization": LAYOUT_NORMALIZATION,
    "layout_extraction_sha256": EXTRACTION_SHA256,
    "records_sha256": RECORDS_SHA256,
    "immutable_records_sha256": IMMUTABLE_RECORDS_SHA256,
    "normative_precedence": 3,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def strict_equal(left: Any, right: Any) -> bool:
    """Compare JSON-compatible values without bool/integer coercion."""
    try:
        return canonical_json_digest(left) == canonical_json_digest(right)
    except (TypeError, ValueError):
        return False


def paths_alias(left: Path, right: Path) -> bool:
    """Reject lexical, symbolic-link, and hard-link aliases fail-closed."""
    if left.resolve() == right.resolve():
        return True
    if not left.exists() or not right.exists():
        return False
    try:
        return os.path.samefile(left, right)
    except OSError as error:
        raise ValueError(
            f"cannot establish path identity for {left} and {right}: {error}"
        ) from error


def validate_distinct_paths(paths: dict[str, Path]) -> None:
    entries = list(paths.items())
    for index, (left_name, left_path) in enumerate(entries):
        for right_name, right_path in entries[index + 1 :]:
            if paths_alias(left_path, right_path):
                raise ValueError(
                    f"{left_name} must not alias {right_name}: {left_path}"
                )


def extract_text(pdf: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="morphoia-requirements-") as directory:
        target = Path(directory) / "requirements.txt"
        try:
            subprocess.run(
                ["pdftotext", "-layout", str(pdf), str(target)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise RuntimeError("pdftotext is required only for --extract-pdf") from error
        except subprocess.CalledProcessError as error:
            detail = error.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"pdftotext failed: {detail}") from error
        return target.read_bytes()


def normalize_layout_artifact(stored: bytes) -> bytes:
    """Remove only the repository's documented terminal LF wrapper.

    ``pdftotext`` ends this PDF with a form-feed byte. The versioned text file
    has one additional LF so it remains a conventional text file. No other
    whitespace or newline normalization is permitted.
    """
    if not stored.endswith(b"\f\n"):
        raise ValueError(
            "layout artifact must end with form-feed followed by its single storage LF"
        )
    normalized = stored[:-1]
    actual = sha256_bytes(normalized)
    if actual != EXTRACTION_SHA256:
        raise ValueError(
            "normalized layout extraction digest mismatch: "
            f"expected {EXTRACTION_SHA256}, got {actual}"
        )
    return normalized


def load_layout_artifact(path: Path) -> bytes:
    stored = path.read_bytes()
    actual = sha256_bytes(stored)
    if actual != LAYOUT_ARTIFACT_SHA256:
        raise ValueError(
            "layout artifact storage digest mismatch: "
            f"expected {LAYOUT_ARTIFACT_SHA256}, got {actual}"
        )
    return normalize_layout_artifact(stored)


def compare_pdf_extraction(pdf: Path, versioned_layout: bytes) -> None:
    extracted = extract_text(pdf)
    actual = sha256_bytes(extracted)
    if actual != EXTRACTION_SHA256:
        raise ValueError(
            "fresh PDF layout extraction digest mismatch: "
            f"expected {EXTRACTION_SHA256}, got {actual}"
        )
    if extracted != versioned_layout:
        raise ValueError("fresh PDF layout extraction differs from versioned layout artifact")


def phase_details(raw: str) -> dict[str, Any]:
    if raw not in EXPECTED_PHASES:
        raise ValueError(f"unsupported phase expression: {raw}")
    open_ended = raw.endswith("+")
    if open_ended:
        start = int(raw[1])
        end = 4
    elif "-" in raw:
        left, right = raw.split("-", maxsplit=1)
        start = int(left[1])
        end = int(right[1])
    else:
        start = end = int(raw[1])
    return {
        "raw": raw,
        "start": start,
        "end": end,
        "open_ended": open_ended,
    }


def gates_for_phase(raw: str) -> list[str]:
    phase = phase_details(raw)
    return [f"G{number + 1}" for number in range(phase["start"], phase["end"] + 1)]


def proof_details(raw: str) -> dict[str, Any]:
    if raw not in EXPECTED_PROOFS:
        raise ValueError(f"unsupported proof expression: {raw}")
    return {
        "raw": raw,
        "methods": [PROOF_NAMES[token] for token in raw.split("/")],
    }


def source_digest(requirement_id: str, source: dict[str, Any]) -> str:
    return canonical_json_digest(
        {
            "id": requirement_id,
            "pdf": source["pdf"],
            "pdf_sha256": source["pdf_sha256"],
            "text_lines": source["text_lines"],
            "fragments": source["fragments"],
        }
    )


def record_digest_full(record: dict[str, Any]) -> str:
    content = {key: value for key, value in record.items() if key != "record_sha256"}
    return canonical_json_digest(content)


def parse_records(text: bytes) -> list[dict[str, Any]]:
    decoded = text.decode("utf-8")
    lines = decoded.split("\n")
    records: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = ROW_RE.match(lines[index])
        if match is None:
            index += 1
            continue

        requirement_id, first_fragment, priority, phase_raw, proof_raw = match.groups()
        fragments = [first_fragment.strip()]
        source_lines = [index + 1]
        if index + 1 < len(lines):
            continuation = CONTINUATION_RE.match(lines[index + 1])
            if continuation is not None:
                fragments.append(continuation.group(1).strip())
                source_lines.append(index + 2)
                index += 1

        id_match = REQUIREMENT_ID_RE.fullmatch(requirement_id)
        if id_match is None:
            raise ValueError(f"invalid requirement identifier: {requirement_id}")
        family = id_match.group(1)
        ordinal = int(id_match.group(2))
        flags = []
        if requirement_id in MODAL_PRIORITY_MISMATCHES:
            flags.append("modal_priority_mismatch")

        source = {
            "pdf": SOURCE_PDF_PATH,
            "pdf_sha256": SOURCE_PDF_SHA256,
            "text_lines": source_lines,
            "fragments": fragments,
        }
        source["source_sha256"] = source_digest(requirement_id, source)
        record = {
            "id": requirement_id,
            "family": family,
            "ordinal": ordinal,
            "wording_fr": " ".join(fragments),
            "priority": priority,
            "phase": phase_details(phase_raw),
            "proof": proof_details(proof_raw),
            "source": source,
            "quality_flags": flags,
        }
        record["record_sha256"] = record_digest_full(record)
        records.append(record)
        index += 1
    return records


def increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def fail(failures: list[str], context: str, message: str) -> None:
    failures.append(f"{context}: {message}")


def exact_keys(
    value: Any,
    expected: set[str],
    context: str,
    failures: list[str],
) -> bool:
    if not isinstance(value, dict):
        fail(failures, context, "must be an object")
        return False
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        fail(failures, context, f"object keys mismatch; missing={missing}, extra={extra}")
        return False
    return True


def valid_nonempty_strings(
    value: Any,
    context: str,
    failures: list[str],
    *,
    unique: bool = True,
) -> bool:
    if not isinstance(value, list):
        fail(failures, context, "must be an array")
        return False
    if any(not isinstance(item, str) or not item.strip() for item in value):
        fail(failures, context, "items must be non-empty strings")
        return False
    if unique and len(set(value)) != len(value):
        fail(failures, context, "items must be unique")
        return False
    return True


def record_digest(records: list[dict[str, Any]]) -> str:
    compact = [
        {
            "id": record["id"],
            "wording": record["wording_fr"],
            "priority": record["priority"],
            "phase": record["phase"]["raw"],
            "proof": record["proof"]["raw"],
        }
        for record in records
    ]
    encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def immutable_records_digest(records: list[dict[str, Any]]) -> str:
    return canonical_json_digest(records)


def validate_records(records: Any) -> list[dict[str, Any]]:
    failures: list[str] = []
    if not isinstance(records, list):
        raise ValueError("requirements: must be an array")
    if len(records) != 320:
        fail(failures, "requirements", f"expected 320 requirements, got {len(records)}")

    family_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    proof_counts: dict[str, int] = {}
    ids: list[str] = []
    continuations = 0

    record_keys = {
        "id",
        "family",
        "ordinal",
        "wording_fr",
        "priority",
        "phase",
        "proof",
        "source",
        "quality_flags",
        "record_sha256",
    }
    source_keys = {
        "pdf",
        "pdf_sha256",
        "text_lines",
        "fragments",
        "source_sha256",
    }

    for position, record in enumerate(records):
        context = f"requirements[{position}]"
        if not exact_keys(record, record_keys, context, failures):
            continue
        requirement_id = record["id"]
        if not isinstance(requirement_id, str):
            fail(failures, f"{context}.id", "must be a string")
            continue
        id_match = REQUIREMENT_ID_RE.fullmatch(requirement_id)
        if id_match is None:
            fail(failures, f"{context}.id", "invalid requirement identifier")
            continue
        ids.append(requirement_id)
        family = id_match.group(1)
        ordinal = int(id_match.group(2))
        if record["family"] != family:
            fail(failures, f"{context}.family", f"expected {family}")
        if type(record["ordinal"]) is not int or record["ordinal"] != ordinal:
            fail(failures, f"{context}.ordinal", f"expected {ordinal}")
        if family not in EXPECTED_FAMILY_COUNTS:
            fail(failures, f"{context}.family", f"unknown family {family}")
        else:
            increment(family_counts, family)

        wording = record["wording_fr"]
        if not isinstance(wording, str) or not wording:
            fail(failures, f"{context}.wording_fr", "must be a non-empty string")
        elif not wording.endswith((".", ";")):
            fail(failures, f"{context}.wording_fr", "has no terminal punctuation")

        priority = record["priority"]
        if not isinstance(priority, str) or priority not in EXPECTED_PRIORITIES:
            fail(failures, f"{context}.priority", f"invalid value {priority!r}")
        else:
            increment(priority_counts, priority)

        phase = record["phase"]
        if exact_keys(phase, {"raw", "start", "end", "open_ended"}, f"{context}.phase", failures):
            try:
                expected_phase = phase_details(phase["raw"])
            except (TypeError, ValueError) as error:
                fail(failures, f"{context}.phase.raw", str(error))
            else:
                if not strict_equal(phase, expected_phase):
                    fail(
                        failures,
                        f"{context}.phase",
                        f"derived fields must equal {expected_phase}",
                    )
                increment(phase_counts, phase["raw"])

        proof = record["proof"]
        if exact_keys(proof, {"raw", "methods"}, f"{context}.proof", failures):
            try:
                expected_proof = proof_details(proof["raw"])
            except (TypeError, ValueError) as error:
                fail(failures, f"{context}.proof.raw", str(error))
            else:
                if not strict_equal(proof, expected_proof):
                    fail(
                        failures,
                        f"{context}.proof",
                        f"derived fields must equal {expected_proof}",
                    )
                increment(proof_counts, proof["raw"])

        source = record["source"]
        if exact_keys(source, source_keys, f"{context}.source", failures):
            if source["pdf"] != SOURCE_PDF_PATH:
                fail(failures, f"{context}.source.pdf", f"expected {SOURCE_PDF_PATH}")
            if source["pdf_sha256"] != SOURCE_PDF_SHA256:
                fail(failures, f"{context}.source.pdf_sha256", "baseline digest mismatch")
            lines = source["text_lines"]
            fragments = source["fragments"]
            valid_lines = (
                isinstance(lines, list)
                and len(lines) in {1, 2}
                and all(type(line) is int and line > 0 for line in lines)
                and lines == sorted(set(lines))
                and (len(lines) == 1 or lines[1] == lines[0] + 1)
            )
            if not valid_lines:
                fail(
                    failures,
                    f"{context}.source.text_lines",
                    "must contain one or two consecutive positive lines",
                )
            valid_fragments = valid_nonempty_strings(
                fragments,
                f"{context}.source.fragments",
                failures,
                unique=False,
            )
            if valid_lines and valid_fragments:
                if len(lines) != len(fragments):
                    fail(failures, f"{context}.source", "line and fragment counts differ")
                continuations += len(fragments) - 1
                if wording != " ".join(fragments):
                    fail(failures, f"{context}.wording_fr", "does not match source fragments")
            try:
                expected_source_digest = source_digest(requirement_id, source)
            except (KeyError, TypeError, ValueError) as error:
                fail(failures, f"{context}.source.source_sha256", f"cannot derive digest: {error}")
            else:
                if source["source_sha256"] != expected_source_digest:
                    fail(failures, f"{context}.source.source_sha256", "digest mismatch")

        flags = record["quality_flags"]
        expected_flags = (
            ["modal_priority_mismatch"]
            if requirement_id in MODAL_PRIORITY_MISMATCHES
            else []
        )
        if flags != expected_flags:
            fail(failures, f"{context}.quality_flags", f"expected {expected_flags}")

        try:
            expected_record_digest = record_digest_full(record)
        except (TypeError, ValueError) as error:
            fail(failures, f"{context}.record_sha256", f"cannot derive digest: {error}")
        else:
            if record["record_sha256"] != expected_record_digest:
                fail(failures, f"{context}.record_sha256", "digest mismatch")

    if len(set(ids)) != len(ids):
        fail(failures, "requirements", "requirement identifiers are not unique")
    if family_counts != EXPECTED_FAMILY_COUNTS:
        fail(failures, "summary.families", f"distribution mismatch: {family_counts}")
    if priority_counts != EXPECTED_PRIORITIES:
        fail(failures, "summary.priorities", f"distribution mismatch: {priority_counts}")
    if phase_counts != EXPECTED_PHASES:
        fail(failures, "summary.phases", f"distribution mismatch: {phase_counts}")
    if proof_counts != EXPECTED_PROOFS:
        fail(failures, "summary.proof_methods", f"distribution mismatch: {proof_counts}")
    if continuations != 135:
        fail(failures, "summary.source_continuation_rows", f"expected 135, got {continuations}")

    try:
        digest = record_digest(records)
    except (KeyError, TypeError) as error:
        fail(failures, "baseline.records_sha256", f"cannot derive digest: {error}")
    else:
        if digest != RECORDS_SHA256:
            fail(failures, "baseline.records_sha256", f"expected {RECORDS_SHA256}, got {digest}")
    try:
        full_digest = immutable_records_digest(records)
    except (TypeError, ValueError) as error:
        fail(failures, "baseline.immutable_records_sha256", f"cannot derive digest: {error}")
    else:
        if full_digest != IMMUTABLE_RECORDS_SHA256:
            fail(
                failures,
                "baseline.immutable_records_sha256",
                f"expected {IMMUTABLE_RECORDS_SHA256}, got {full_digest}",
            )
    if failures:
        raise ValueError("; ".join(failures))
    return records


def summary_metadata() -> dict[str, Any]:
    return {
        "total": 320,
        "families": EXPECTED_FAMILY_COUNTS,
        "priorities": EXPECTED_PRIORITIES,
        "phases": EXPECTED_PHASES,
        "proof_methods": EXPECTED_PROOFS,
        "source_continuation_rows": 135,
        "modal_priority_mismatches": sorted(MODAL_PRIORITY_MISMATCHES),
    }


def catalogue(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$schema": CATALOGUE_SCHEMA_REF,
        "schema_version": CATALOGUE_SCHEMA_VERSION,
        "baseline": BASELINE_METADATA,
        "status_vocabulary": STATUS_VOCABULARY,
        "summary": summary_metadata(),
        "requirements": records,
    }


def default_tracking(record: dict[str, Any]) -> dict[str, Any]:
    component, work_package = FAMILY_TRACKING[record["family"]]
    return {
        "component": component,
        "work_package": work_package,
        "issue": None,
        "test_ids": [],
        "evidence": [],
        "gate_candidates": gates_for_phase(record["phase"]["raw"]),
        "dependencies": [],
        "dependency_mapping": "UNMAPPED",
        "status": "NOT_RUN",
        "status_reason": None,
        "mapping_status": "PARTIAL",
    }


def tracking_catalogue(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$schema": TRACKING_SCHEMA_REF,
        "schema_version": TRACKING_SCHEMA_VERSION,
        "baseline_records_sha256": RECORDS_SHA256,
        "baseline_immutable_records_sha256": IMMUTABLE_RECORDS_SHA256,
        "status_vocabulary": STATUS_VOCABULARY,
        "entries": {record["id"]: default_tracking(record) for record in records},
    }


def validate_catalogue(data: Any) -> list[dict[str, Any]]:
    failures: list[str] = []
    keys = {
        "$schema",
        "schema_version",
        "baseline",
        "status_vocabulary",
        "summary",
        "requirements",
    }
    if not exact_keys(data, keys, "catalogue", failures):
        raise ValueError("; ".join(failures))
    if data["$schema"] != CATALOGUE_SCHEMA_REF:
        fail(failures, "catalogue.$schema", f"expected {CATALOGUE_SCHEMA_REF}")
    if data["schema_version"] != CATALOGUE_SCHEMA_VERSION:
        fail(failures, "catalogue.schema_version", f"expected {CATALOGUE_SCHEMA_VERSION}")
    if not strict_equal(data["baseline"], BASELINE_METADATA):
        fail(failures, "catalogue.baseline", "metadata mismatch")
    if not strict_equal(data["status_vocabulary"], STATUS_VOCABULARY):
        fail(failures, "catalogue.status_vocabulary", "vocabulary mismatch")
    if not strict_equal(data["summary"], summary_metadata()):
        fail(failures, "catalogue.summary", "derived summary mismatch")
    try:
        records = validate_records(data["requirements"])
    except ValueError as error:
        fail(failures, "catalogue.requirements", str(error))
        records = []
    if failures:
        raise ValueError("; ".join(failures))
    return records


def validate_tracking(data: Any, records: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    keys = {
        "$schema",
        "schema_version",
        "baseline_records_sha256",
        "baseline_immutable_records_sha256",
        "status_vocabulary",
        "entries",
    }
    if not exact_keys(data, keys, "tracking", failures):
        raise ValueError("; ".join(failures))
    if data["$schema"] != TRACKING_SCHEMA_REF:
        fail(failures, "tracking.$schema", f"expected {TRACKING_SCHEMA_REF}")
    if data["schema_version"] != TRACKING_SCHEMA_VERSION:
        fail(failures, "tracking.schema_version", f"expected {TRACKING_SCHEMA_VERSION}")
    if data["baseline_records_sha256"] != RECORDS_SHA256:
        fail(failures, "tracking.baseline_records_sha256", "baseline digest mismatch")
    if data["baseline_immutable_records_sha256"] != IMMUTABLE_RECORDS_SHA256:
        fail(failures, "tracking.baseline_immutable_records_sha256", "baseline digest mismatch")
    if not strict_equal(data["status_vocabulary"], STATUS_VOCABULARY):
        fail(failures, "tracking.status_vocabulary", "vocabulary mismatch")

    entries = data["entries"]
    if not isinstance(entries, dict):
        fail(failures, "tracking.entries", "must be an object")
        entries = {}
    records_by_id = {record["id"]: record for record in records}
    if set(entries) != set(records_by_id):
        fail(
            failures,
            "tracking.entries",
            f"identifier set mismatch; missing={sorted(set(records_by_id) - set(entries))}, "
            f"extra={sorted(set(entries) - set(records_by_id))}",
        )

    entry_keys = {
        "component",
        "work_package",
        "issue",
        "test_ids",
        "evidence",
        "gate_candidates",
        "dependencies",
        "dependency_mapping",
        "status",
        "status_reason",
        "mapping_status",
    }
    for requirement_id in sorted(set(entries) & set(records_by_id)):
        entry = entries[requirement_id]
        context = f"tracking.entries.{requirement_id}"
        if not exact_keys(entry, entry_keys, context, failures):
            continue
        record = records_by_id[requirement_id]
        expected_component, expected_work_package = FAMILY_TRACKING[record["family"]]
        if entry["component"] != expected_component:
            fail(failures, f"{context}.component", f"expected {expected_component}")
        if entry["work_package"] != expected_work_package:
            fail(failures, f"{context}.work_package", f"expected {expected_work_package}")
        expected_gates = gates_for_phase(record["phase"]["raw"])
        if entry["gate_candidates"] != expected_gates:
            fail(failures, f"{context}.gate_candidates", f"expected {expected_gates}")

        issue = entry["issue"]
        if issue is not None and (not isinstance(issue, str) or not issue.strip()):
            fail(failures, f"{context}.issue", "must be null or a non-empty string")
        reason = entry["status_reason"]
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            fail(failures, f"{context}.status_reason", "must be null or a non-empty string")
        tests_valid = valid_nonempty_strings(entry["test_ids"], f"{context}.test_ids", failures)
        evidence_valid = valid_nonempty_strings(entry["evidence"], f"{context}.evidence", failures)
        dependencies_valid = valid_nonempty_strings(
            entry["dependencies"],
            f"{context}.dependencies",
            failures,
        )
        status = entry["status"]
        if status not in STATUS_VOCABULARY:
            fail(failures, f"{context}.status", f"invalid value {status!r}")
        dependency_mapping = entry["dependency_mapping"]
        if not isinstance(dependency_mapping, str) or dependency_mapping not in {
            "UNMAPPED",
            "PARTIAL",
            "COMPLETE",
            "NOT_APPLICABLE",
        }:
            fail(failures, f"{context}.dependency_mapping", f"invalid value {dependency_mapping!r}")
        mapping_status = entry["mapping_status"]
        if not isinstance(mapping_status, str) or mapping_status not in {
            "UNMAPPED",
            "PARTIAL",
            "COMPLETE",
        }:
            fail(failures, f"{context}.mapping_status", f"invalid value {mapping_status!r}")

        if status in ("PASS", "FAIL"):
            if tests_valid and not entry["test_ids"]:
                fail(
                    failures,
                    f"{context}.test_ids",
                    f"{status} requires an executed test reference",
                )
            if evidence_valid and not entry["evidence"]:
                fail(failures, f"{context}.evidence", f"{status} requires evidence")
        if status == "PASS":
            if mapping_status != "COMPLETE":
                fail(failures, f"{context}.mapping_status", "PASS requires COMPLETE mapping")
            if dependency_mapping not in ("COMPLETE", "NOT_APPLICABLE"):
                fail(
                    failures,
                    f"{context}.dependency_mapping",
                    "PASS requires reviewed dependency mapping",
                )
        if status == "BLOCKED":
            if reason is None:
                fail(failures, f"{context}.status_reason", "BLOCKED requires a reason")
            if evidence_valid and not entry["evidence"]:
                fail(failures, f"{context}.evidence", "BLOCKED requires blocker evidence")
            if dependencies_valid and not entry["dependencies"]:
                fail(failures, f"{context}.dependencies", "BLOCKED requires a dependency")
        if status == "NOT_APPLICABLE":
            if reason is None:
                fail(failures, f"{context}.status_reason", "NOT_APPLICABLE requires a reason")
            if evidence_valid and not entry["evidence"]:
                fail(
                    failures,
                    f"{context}.evidence",
                    "NOT_APPLICABLE requires justification evidence",
                )

    if failures:
        raise ValueError("; ".join(failures))


def load_json(path: Path) -> Any:
    def reject_nonstandard_number(value: str) -> None:
        raise ValueError(f"non-standard JSON numeric constant: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key in {path}: {key}")
            value[key] = item
        return value

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_nonstandard_number,
    )


def load_and_validate_catalogue(path: Path) -> list[dict[str, Any]]:
    return validate_catalogue(load_json(path))


def load_and_validate_tracking(path: Path, records: list[dict[str, Any]]) -> None:
    validate_tracking(load_json(path), records)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    output_mode = (
        path.stat().st_mode & 0o777
        if path.is_file() and not path.is_symlink()
        else 0o644
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, output_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def validate_schema_files(paths: Iterable[Path]) -> None:
    for path in paths:
        schema = load_json(path)
        if not isinstance(schema, dict):
            raise ValueError(f"{path}: schema must be an object")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError(f"{path}: must declare JSON Schema draft 2020-12")
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise ValueError(f"{path}: top-level object must reject additional properties")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=Path(SOURCE_PDF_PATH))
    parser.add_argument(
        "--layout-text",
        type=Path,
        default=Path(LAYOUT_ARTIFACT_PATH),
        help="hash-pinned layout text used for normal validation and regeneration",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("spec/requirements/requirements.yaml"),
    )
    parser.add_argument(
        "--tracking-output",
        type=Path,
        default=Path("spec/requirements/requirements-tracking.yaml"),
    )
    parser.add_argument(
        "--catalog-schema",
        type=Path,
        default=Path("spec/requirements/requirements-catalog.schema.json"),
    )
    parser.add_argument(
        "--tracking-schema",
        type=Path,
        default=Path("spec/requirements/requirements-tracking.schema.json"),
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--extract-pdf",
        action="store_true",
        help="run pdftotext and compare it with the versioned layout without rewriting",
    )
    args = parser.parse_args()

    validate_distinct_paths(
        {
            "baseline PDF": args.pdf,
            "layout artifact": args.layout_text,
            "catalogue schema": args.catalog_schema,
            "tracking schema": args.tracking_schema,
            "immutable catalogue output": args.output,
            "tracking overlay output": args.tracking_output,
        }
    )

    validate_schema_files([args.catalog_schema, args.tracking_schema])
    pdf_bytes = args.pdf.read_bytes()
    actual_pdf_sha = sha256_bytes(pdf_bytes)
    if actual_pdf_sha != SOURCE_PDF_SHA256:
        raise ValueError(f"baseline PDF digest mismatch: {actual_pdf_sha}")
    text = load_layout_artifact(args.layout_text)
    extracted_records = parse_records(text)
    validate_records(extracted_records)
    if args.extract_pdf:
        compare_pdf_extraction(args.pdf, text)
    if args.check:
        catalogue_records = load_and_validate_catalogue(args.output)
        if not strict_equal(catalogue_records, extracted_records):
            raise ValueError(
                "catalogue records differ from the hash-pinned versioned layout extraction"
            )
        load_and_validate_tracking(args.tracking_output, catalogue_records)
        extraction_audit = (
            "; fresh pdftotext extraction matched the versioned layout"
            if args.extract_pdf
            else ""
        )
        print(
            "PASS: PDF, versioned layout, immutable catalogue, and preserved "
            "tracking overlay contain the exact 320-record baseline"
            f"{extraction_audit}"
        )
        return 0

    if args.tracking_output.exists():
        original_tracking = args.tracking_output.read_bytes()
        load_and_validate_tracking(args.tracking_output, extracted_records)
        tracking_result = "preserved existing tracking overlay byte-for-byte"
    else:
        original_tracking = None
        write_json_atomic(args.tracking_output, tracking_catalogue(extracted_records))
        tracking_result = "created initial fail-closed tracking overlay"

    write_json_atomic(args.output, catalogue(extracted_records))
    if original_tracking is not None and args.tracking_output.read_bytes() != original_tracking:
        raise RuntimeError("tracking overlay changed during immutable catalogue regeneration")
    extraction_audit = (
        "; fresh pdftotext extraction matched the versioned layout"
        if args.extract_pdf
        else ""
    )
    print(
        f"PASS: parsed {len(extracted_records)} immutable requirements from the "
        f"versioned layout to {args.output}; "
        f"{tracking_result}{extraction_audit}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
