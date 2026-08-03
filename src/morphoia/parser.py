"""Recursive-descent parser for the MORPHOIA 0.1 experimental source form."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .lexer import LexError, Token, tokenize
from .model import (
    Attribute,
    Binary,
    Call,
    Document,
    Expression,
    Import,
    ListExpression,
    Literal,
    Model,
    Name,
    Node,
    Span,
    Unary,
)


class ParseError(ValueError):
    def __init__(self, message: str, span: Span):
        super().__init__(message)
        self.span = span


_SIMPLE_DECLARATIONS = {
    "parameter",
    "constant",
    "datum",
    "reference",
    "material",
    "pmi",
    "tolerance",
}
_NAMED_VALUE_STATEMENTS = {"profile", "dimension", "let", "output"}
_EXPRESSION_STATEMENTS = {"constraint", "assert", "expect"}
_BLOCKS_WITHOUT_NAMES = {"units", "metadata", "validate"}
_NAMED_BLOCKS = {"assembly", "scenario", "extension"}


def _merge(first: Span, last: Span) -> Span:
    return Span(first.line, first.column, last.end_line, last.end_column)


@dataclass(slots=True)
class Parser:
    tokens: tuple[Token, ...]
    index: int = 0

    @classmethod
    def from_source(cls, source: str) -> Parser:
        return cls(tokenize(source))

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def peek(self, offset: int = 1) -> Token:
        target = min(self.index + offset, len(self.tokens) - 1)
        return self.tokens[target]

    def advance(self) -> Token:
        token = self.current
        if token.kind != "EOF":
            self.index += 1
        return token

    def match(self, value: str) -> Token | None:
        if self.current.kind == value or self.current.value == value:
            return self.advance()
        return None

    def expect(self, value: str, message: str | None = None) -> Token:
        token = self.match(value)
        if token is None:
            raise ParseError(
                message or f"expected {value!r}, found {self.current.value!r}", self.current.span
            )
        return token

    def expect_identifier(self, message: str = "expected identifier") -> Token:
        if self.current.kind != "IDENT":
            raise ParseError(message, self.current.span)
        return self.advance()

    def parse(self) -> Document:
        start = self.expect("morphoia", "document must start with 'morphoia'")
        if self.current.kind not in {"NUMBER", "STRING", "IDENT"}:
            raise ParseError("expected language version", self.current.span)
        version = self.advance().value
        self.expect(";")

        namespace: str | None = None
        imports: list[Import] = []
        models: list[Model] = []

        if self.match("namespace"):
            namespace_name = self.parse_name()
            namespace = namespace_name.text
            self.expect(";")

        while self.match("import"):
            import_start = self.tokens[self.index - 1]
            if self.current.kind != "STRING":
                raise ParseError("import requires a quoted URI or path", self.current.span)
            source = self.advance()
            alias = None
            if self.match("as"):
                alias = self.expect_identifier().value
            end = self.expect(";")
            imports.append(Import(source.value, _merge(import_start.span, end.span), alias))

        while self.current.kind != "EOF":
            models.append(self.parse_model())

        if not models:
            raise ParseError("document must contain at least one model", self.current.span)

        end_span = models[-1].span
        return Document(
            version=str(version),
            span=_merge(start.span, end_span),
            namespace=namespace,
            imports=tuple(imports),
            models=tuple(models),
        )

    def parse_model(self) -> Model:
        start = self.expect("model", "expected a model declaration")
        name = self.expect_identifier("expected model name")
        attributes = self.parse_attributes()
        body, end = self.parse_block()
        return Model(name.value, _merge(start.span, end.span), attributes, body)

    def parse_block(self) -> tuple[tuple[Node, ...], Token]:
        self.expect("{")
        nodes: list[Node] = []
        while self.current.kind != "}":
            if self.current.kind == "EOF":
                raise ParseError("unterminated block", self.current.span)
            nodes.append(self.parse_node())
        end = self.expect("}")
        return tuple(nodes), end

    def parse_node(self) -> Node:
        if self.current.kind != "IDENT":
            raise ParseError("expected declaration or statement", self.current.span)

        kind_token = self.advance()
        kind = kind_token.value

        # In operation blocks, property names may coincide with declaration
        # keywords (for example ``profile = outline.outer``). Assignment is
        # therefore recognized before keyword dispatch.
        if self.current.kind in {"=", "."}:
            parts = [kind]
            while self.match("."):
                parts.append(self.expect_identifier().value)
            self.expect("=")
            value = self.parse_expression()
            end = self.expect(";")
            return Node(
                "assign", _merge(kind_token.span, end.span), name=".".join(parts), value=value
            )

        if kind in _SIMPLE_DECLARATIONS:
            return self.parse_simple_declaration(kind_token)
        if kind == "sketch":
            return self.parse_sketch(kind_token)
        if kind == "feature":
            return self.parse_feature(kind_token)
        if kind in _BLOCKS_WITHOUT_NAMES:
            attributes = self.parse_attributes()
            body, end = self.parse_block()
            return Node(kind, _merge(kind_token.span, end.span), attributes=attributes, body=body)
        if kind in _NAMED_BLOCKS:
            name = self.expect_identifier(f"expected {kind} name")
            attributes = self.parse_attributes()
            body, end = self.parse_block()
            return Node(
                kind,
                _merge(kind_token.span, end.span),
                name=name.value,
                attributes=attributes,
                body=body,
            )
        if kind in _NAMED_VALUE_STATEMENTS:
            return self.parse_named_value_statement(kind_token)
        if kind in _EXPRESSION_STATEMENTS:
            value = self.parse_expression()
            attributes = self.parse_attributes()
            end = self.expect(";")
            return Node(kind, _merge(kind_token.span, end.span), value=value, attributes=attributes)
        if kind == "set":
            target = self.parse_name()
            self.expect("=")
            value = self.parse_expression()
            end = self.expect(";")
            return Node(kind, _merge(kind_token.span, end.span), name=target.text, value=value)

        # Extension-friendly generic statement: ``verb expression;`` or
        # ``verb name { ... }``. Unknown verbs remain explicit in the AST.
        if self.current.kind == "IDENT" and self.peek().kind == "{":
            name = self.advance()
            body, end = self.parse_block()
            return Node(kind, _merge(kind_token.span, end.span), name=name.value, body=body)
        value = self.parse_expression()
        attributes = self.parse_attributes()
        end = self.expect(";")
        return Node(kind, _merge(kind_token.span, end.span), value=value, attributes=attributes)

    def parse_simple_declaration(self, start: Token) -> Node:
        name = self.expect_identifier(f"expected {start.value} name")
        type_name = None
        if self.match(":"):
            type_name = self.parse_name().text
        value = None
        if self.match("="):
            value = self.parse_expression()
        attributes = self.parse_attributes()
        if self.current.kind == "{":
            body, end = self.parse_block()
        else:
            body = ()
            end = self.expect(";")
        return Node(
            start.value,
            _merge(start.span, end.span),
            name=name.value,
            type_name=type_name,
            value=value,
            attributes=attributes,
            body=body,
        )

    def parse_sketch(self, start: Token) -> Node:
        name = self.expect_identifier("expected sketch name")
        self.expect("on", "sketch requires an 'on' reference plane")
        context = self.parse_expression()
        attributes = self.parse_attributes()
        body, end = self.parse_block()
        return Node(
            "sketch",
            _merge(start.span, end.span),
            name=name.value,
            context=context,
            attributes=attributes,
            body=body,
        )

    def parse_feature(self, start: Token) -> Node:
        name = self.expect_identifier("expected feature name")
        self.expect(":", "feature requires an operation type after ':'")
        operation = self.parse_name().text
        attributes = self.parse_attributes()
        body, end = self.parse_block()
        return Node(
            "feature",
            _merge(start.span, end.span),
            name=name.value,
            type_name=operation,
            attributes=attributes,
            body=body,
        )

    def parse_named_value_statement(self, start: Token) -> Node:
        name = self.expect_identifier(f"expected {start.value} name")
        type_name = None
        if self.match(":"):
            type_name = self.parse_name().text
        self.expect("=", f"{start.value} requires '='")
        value = self.parse_expression()
        attributes = self.parse_attributes()
        end = self.expect(";")
        return Node(
            start.value,
            _merge(start.span, end.span),
            name=name.value,
            type_name=type_name,
            value=value,
            attributes=attributes,
        )

    def parse_attributes(self) -> tuple[Attribute, ...]:
        if not self.match("["):
            return ()
        attributes: list[Attribute] = []
        if self.match("]"):
            return ()
        while True:
            key = self.expect_identifier("expected attribute name")
            self.expect("=")
            attributes.append((key.value, self.parse_expression()))
            if self.match("]"):
                break
            self.expect(",")
        return tuple(attributes)

    def parse_name(self) -> Name:
        first = self.expect_identifier()
        parts = [first.value]
        last = first
        while self.match("."):
            last = self.expect_identifier("expected identifier after '.'")
            parts.append(last.value)
        return Name(tuple(parts), _merge(first.span, last.span))

    def parse_expression(self, minimum_precedence: int = 0) -> Expression:
        left = self.parse_prefix()
        while True:
            operator, precedence, right_associative = self.binary_operator()
            if operator is None or precedence < minimum_precedence:
                break
            self.advance()
            next_precedence = precedence if right_associative else precedence + 1
            right = self.parse_expression(next_precedence)
            left = Binary(left, operator, right, _merge(left.span, right.span))
        return left

    def parse_prefix(self) -> Expression:
        token = self.current
        if token.kind in {"+", "-"} or token.value == "not":
            self.advance()
            operand = self.parse_expression(70)
            return Unary(token.value, operand, _merge(token.span, operand.span))

        if token.kind == "NUMBER":
            self.advance()
            value: int | Decimal
            value = (
                Decimal(token.value)
                if any(char in token.value for char in ".eE")
                else int(token.value)
            )
            unit = None
            end_span = token.span
            if self.current.kind == "IDENT" and self.current.value not in {"and", "or"}:
                unit_token = self.advance()
                unit = unit_token.value
                end_span = unit_token.span
            return Literal(value, _merge(token.span, end_span), unit)

        if token.kind == "STRING":
            self.advance()
            return Literal(token.value, token.span)

        if token.kind == "IDENT":
            if token.value in {"true", "false", "null"}:
                self.advance()
                value = {"true": True, "false": False, "null": None}[token.value]
                return Literal(value, token.span)
            name = self.parse_name()
            if self.match("("):
                return self.finish_call(name)
            return name

        if self.match("("):
            start = token
            expression = self.parse_expression()
            end = self.expect(")")
            # Preserve the expression type while widening its span only when
            # possible; grouping has no semantic node of its own.
            if isinstance(expression, Name):
                return Name(expression.parts, _merge(start.span, end.span))
            return expression

        if self.match("["):
            start = token
            items: list[Expression] = []
            if not self.match("]"):
                while True:
                    items.append(self.parse_expression())
                    if self.match("]"):
                        break
                    self.expect(",")
            end = self.tokens[self.index - 1]
            return ListExpression(tuple(items), _merge(start.span, end.span))

        raise ParseError(f"expected expression, found {token.value!r}", token.span)

    def finish_call(self, function: Name) -> Call:
        arguments: list[Expression] = []
        keywords: list[tuple[str, Expression]] = []
        if not self.match(")"):
            while True:
                if self.current.kind == "IDENT" and self.peek().kind == "=":
                    key = self.advance().value
                    self.expect("=")
                    keywords.append((key, self.parse_expression()))
                else:
                    arguments.append(self.parse_expression())
                if self.match(")"):
                    break
                self.expect(",")
        end = self.tokens[self.index - 1]
        return Call(function, tuple(arguments), tuple(keywords), _merge(function.span, end.span))

    def binary_operator(self) -> tuple[str | None, int, bool]:
        token = self.current
        operator = token.value
        precedences = {
            "or": 10,
            "||": 10,
            "and": 20,
            "&&": 20,
            "==": 30,
            "!=": 30,
            "<": 30,
            "<=": 30,
            ">": 30,
            ">=": 30,
            "~=": 30,
            "+": 40,
            "-": 40,
            "*": 50,
            "/": 50,
            "^": 60,
        }
        if operator not in precedences:
            return None, -1, False
        return operator, precedences[operator], operator == "^"


def parse(source: str) -> Document:
    """Parse source and raise :class:`LexError` or :class:`ParseError`."""

    return Parser.from_source(source).parse()


__all__ = ["LexError", "ParseError", "Parser", "parse"]
