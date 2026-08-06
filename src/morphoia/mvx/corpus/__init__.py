"""Corpus discovery and stale-manifest reconciliation for MVX P1.

The types in this package deliberately distinguish filesystem rows from
candidate object packages.  Neither is an experimental statistical unit;
lineages are assigned only after P1 adjudication.
"""

from .registry import (
    DIRECT_OBJECT_FORMATS,
    CandidateBuildResult,
    DuplicateGroup,
    FileRecord,
    ObjectCandidate,
    ReconciliationEntry,
    ReconciliationResult,
    build_object_candidates,
    detect_objaverse_duplicates,
    identify_direct_object_format,
    inventory_tree,
    is_test_path,
    parse_manifest,
    reconcile_inventories,
    render_csv,
    render_jsonl,
    write_csv,
    write_jsonl,
)

__all__ = [
    "DIRECT_OBJECT_FORMATS",
    "CandidateBuildResult",
    "DuplicateGroup",
    "FileRecord",
    "ObjectCandidate",
    "ReconciliationEntry",
    "ReconciliationResult",
    "build_object_candidates",
    "detect_objaverse_duplicates",
    "identify_direct_object_format",
    "inventory_tree",
    "is_test_path",
    "parse_manifest",
    "reconcile_inventories",
    "render_csv",
    "render_jsonl",
    "write_csv",
    "write_jsonl",
]
