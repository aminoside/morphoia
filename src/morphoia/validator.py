"""Public validation facade."""

from __future__ import annotations

from pathlib import Path

from .lexer import LexError
from .model import Diagnostic, Severity, ValidationResult
from .parser import ParseError, parse
from .semantic import validate_semantics


def validate_source(source: str) -> ValidationResult:
    try:
        document = parse(source)
    except LexError as error:
        return ValidationResult(
            None,
            [Diagnostic("MORPH-E000", Severity.ERROR, str(error), error.span)],
        )
    except ParseError as error:
        return ValidationResult(
            None,
            [Diagnostic("MORPH-E010", Severity.ERROR, str(error), error.span)],
        )
    return ValidationResult(document, validate_semantics(document))


def validate_file(path: str | Path) -> ValidationResult:
    return validate_source(Path(path).read_text(encoding="utf-8"))
