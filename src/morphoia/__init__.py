"""MORPHOIA experimental construction-graph SDK.

Project authors: Louis Manhès and Olivier Ami.
"""

from .compiler import canonical_json, compile_document, semantic_hash
from .parser import parse
from .runtime import RuntimeStore
from .validator import validate_file, validate_source

__author__ = "Louis Manhès; Olivier Ami"
__authors__ = ("Louis Manhès", "Olivier Ami")
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
