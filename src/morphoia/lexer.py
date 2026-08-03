"""Dependency-free lexer for the experimental MORPHOIA textual facade."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .model import Span


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: str
    span: Span


class LexError(ValueError):
    def __init__(self, message: str, span: Span):
        super().__init__(message)
        self.span = span


_TWO_CHARACTER_OPERATORS = {"->", "==", "!=", "<=", ">=", "~=", "&&", "||"}
_ONE_CHARACTER_TOKENS = set("{}()[],:;.=+-*/^<>@")


def tokenize(source: str) -> tuple[Token, ...]:
    tokens: list[Token] = []
    index = 0
    line = 1
    column = 1
    length = len(source)

    def advance(text: str) -> None:
        nonlocal line, column
        newlines = text.count("\n")
        if newlines:
            line += newlines
            column = len(text.rsplit("\n", 1)[-1]) + 1
        else:
            column += len(text)

    def span_for(start_line: int, start_column: int, text: str) -> Span:
        end_line = start_line + text.count("\n")
        if "\n" in text:
            end_column = len(text.rsplit("\n", 1)[-1]) + 1
        else:
            end_column = start_column + len(text)
        return Span(start_line, start_column, end_line, end_column)

    while index < length:
        char = source[index]

        if char.isspace():
            start = index
            while index < length and source[index].isspace():
                index += 1
            advance(source[start:index])
            continue

        if source.startswith("//", index):
            start = index
            newline = source.find("\n", index)
            index = length if newline == -1 else newline
            advance(source[start:index])
            continue

        if source.startswith("/*", index):
            start_line, start_column = line, column
            end = source.find("*/", index + 2)
            if end == -1:
                raise LexError(
                    "unterminated block comment",
                    Span(start_line, start_column, start_line, start_column + 2),
                )
            text = source[index : end + 2]
            index = end + 2
            advance(text)
            continue

        start_line, start_column = line, column

        if char == '"':
            quote = char
            start = index
            index += 1
            escaped = False
            while index < length:
                current = source[index]
                if current == "\n" and not escaped:
                    raise LexError(
                        "newline in string literal",
                        span_for(start_line, start_column, source[start:index]),
                    )
                if current == quote and not escaped:
                    index += 1
                    break
                if current == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
                index += 1
            else:
                raise LexError(
                    "unterminated string literal",
                    span_for(start_line, start_column, source[start:index]),
                )
            raw = source[start:index]
            try:
                value = json.loads(raw)
            except (ValueError, json.JSONDecodeError) as error:
                raise LexError(
                    f"invalid string escape: {error}", span_for(start_line, start_column, raw)
                ) from error
            tokens.append(Token("STRING", value, span_for(start_line, start_column, raw)))
            advance(raw)
            continue

        if char.isdigit() or (char == "." and index + 1 < length and source[index + 1].isdigit()):
            start = index
            if char == ".":
                index += 1
            while index < length and source[index].isdigit():
                index += 1
            if index < length and source[index] == ".":
                index += 1
                while index < length and source[index].isdigit():
                    index += 1
            if index < length and source[index] in "eE":
                exponent = index
                index += 1
                if index < length and source[index] in "+-":
                    index += 1
                digit_start = index
                while index < length and source[index].isdigit():
                    index += 1
                if digit_start == index:
                    index = exponent
            raw = source[start:index]
            tokens.append(Token("NUMBER", raw, span_for(start_line, start_column, raw)))
            advance(raw)
            continue

        if (char.isascii() and char.isalpha()) or char == "_":
            start = index
            index += 1
            while index < length and (
                (source[index].isascii() and source[index].isalnum()) or source[index] == "_"
            ):
                index += 1
            raw = source[start:index]
            tokens.append(Token("IDENT", raw, span_for(start_line, start_column, raw)))
            advance(raw)
            continue

        pair = source[index : index + 2]
        if pair in _TWO_CHARACTER_OPERATORS:
            tokens.append(Token(pair, pair, span_for(start_line, start_column, pair)))
            index += 2
            advance(pair)
            continue

        if char in _ONE_CHARACTER_TOKENS:
            tokens.append(Token(char, char, span_for(start_line, start_column, char)))
            index += 1
            advance(char)
            continue

        raise LexError(
            f"unexpected character {char!r}",
            Span(start_line, start_column, start_line, start_column + 1),
        )

    eof_span = Span(line, column, line, column)
    tokens.append(Token("EOF", "", eof_span))
    return tuple(tokens)
