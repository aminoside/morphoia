"""MORPHOIA experimental construction-graph SDK.

Author and project initiator: Olivier Ami.
"""

from .compiler import canonical_json, compile_document, semantic_hash
from .parser import parse
from .runtime import RuntimeStore
from .validator import validate_file, validate_source

__author__ = "Olivier Ami"
__version__ = "0.2.0-dev"

__all__ = [
    "RuntimeStore",
    "canonical_json",
    "compile_document",
    "parse",
    "semantic_hash",
    "validate_file",
    "validate_source",
]
