"""Typed syntax tree and diagnostics for the experimental MORPHOIA source form."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True, slots=True)
class Span:
    """One-based source location."""

    line: int
    column: int
    end_line: int
    end_column: int


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    span: Span | None = None
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class Name:
    parts: tuple[str, ...]
    span: Span

    @property
    def text(self) -> str:
        return ".".join(self.parts)


@dataclass(frozen=True, slots=True)
class Literal:
    value: str | Decimal | int | bool | None
    span: Span
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class Call:
    function: Name
    arguments: tuple[Expression, ...]
    keywords: tuple[tuple[str, Expression], ...]
    span: Span


@dataclass(frozen=True, slots=True)
class Unary:
    operator: str
    operand: Expression
    span: Span


@dataclass(frozen=True, slots=True)
class Binary:
    left: Expression
    operator: str
    right: Expression
    span: Span


@dataclass(frozen=True, slots=True)
class ListExpression:
    items: tuple[Expression, ...]
    span: Span


type Expression = Name | Literal | Call | Unary | Binary | ListExpression
type Attribute = tuple[str, Expression]


@dataclass(frozen=True, slots=True)
class Node:
    """Uniform declaration/statement node used by the candidate grammar.

    ``kind`` carries the declaration class (parameter, feature, constraint,
    scenario, ...). ``type_name`` is a dimensional type or operation name.
    ``context`` is used by declarations such as ``sketch ... on ...``.
    """

    kind: str
    span: Span
    name: str | None = None
    type_name: str | None = None
    value: Expression | None = None
    context: Expression | None = None
    attributes: tuple[Attribute, ...] = ()
    body: tuple[Node, ...] = ()


@dataclass(frozen=True, slots=True)
class Import:
    source: str
    span: Span
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class Model:
    name: str
    span: Span
    attributes: tuple[Attribute, ...] = ()
    body: tuple[Node, ...] = ()


@dataclass(frozen=True, slots=True)
class Document:
    version: str
    span: Span
    namespace: str | None = None
    imports: tuple[Import, ...] = ()
    models: tuple[Model, ...] = ()


@dataclass(slots=True)
class ValidationResult:
    document: Document | None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.document is not None and not any(
            diagnostic.severity is Severity.ERROR for diagnostic in self.diagnostics
        )
