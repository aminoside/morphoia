"""Minimal dimensional type system used by the reference validator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .model import Binary, Call, Expression, ListExpression, Literal, Name, Unary

UNIT_DIMENSIONS: dict[str, str] = {
    "nm": "length",
    "um": "length",
    "mm": "length",
    "cm": "length",
    "m": "length",
    "in": "length",
    "ft": "length",
    "rad": "angle",
    "deg": "angle",
    "mg": "mass",
    "g": "mass",
    "kg": "mass",
    "ms": "time",
    "s": "time",
    "min": "time",
    "N": "force",
    "Pa": "pressure",
    "MPa": "pressure",
}

TYPE_ALIASES: dict[str, str] = {
    "real": "scalar",
    "number": "scalar",
    "float": "scalar",
    "int": "integer",
    "bool": "boolean",
    "str": "string",
}

CALL_RETURN_TYPES: dict[str, str] = {
    "rectangle": "profile",
    "circle": "profile",
    "polygon": "profile",
    "distance": "length",
    "angle": "angle",
    "select": "entity",
    "vec2": "vector2",
    "vec3": "vector3",
    "manifold": "boolean",
    "valid": "boolean",
    "resolves": "boolean",
    "within": "boolean",
    "interference_free": "boolean",
}


@dataclass(frozen=True, slots=True)
class InferredType:
    name: str
    certain: bool = True


def normalize_type(name: str | None) -> str | None:
    if name is None:
        return None
    return TYPE_ALIASES.get(name, name)


def infer_expression_type(
    expression: Expression,
    symbols: dict[str, str | None],
) -> InferredType:
    if isinstance(expression, Literal):
        if expression.unit:
            return InferredType(
                UNIT_DIMENSIONS.get(expression.unit, "unknown"), expression.unit in UNIT_DIMENSIONS
            )
        if isinstance(expression.value, bool):
            return InferredType("boolean")
        if isinstance(expression.value, int):
            return InferredType("integer")
        if isinstance(expression.value, Decimal):
            return InferredType("scalar")
        if isinstance(expression.value, str):
            return InferredType("string")
        return InferredType("null")

    if isinstance(expression, Name):
        root = expression.parts[0]
        return InferredType(normalize_type(symbols.get(root)) or "unknown", root in symbols)

    if isinstance(expression, Call):
        return InferredType(
            CALL_RETURN_TYPES.get(expression.function.text, "unknown"),
            expression.function.text in CALL_RETURN_TYPES,
        )

    if isinstance(expression, Unary):
        if expression.operator == "not":
            return InferredType("boolean")
        return infer_expression_type(expression.operand, symbols)

    if isinstance(expression, Binary):
        if expression.operator in {"==", "!=", "<", "<=", ">", ">=", "~=", "and", "or", "&&", "||"}:
            return InferredType("boolean")
        left = infer_expression_type(expression.left, symbols)
        right = infer_expression_type(expression.right, symbols)
        if left.name == right.name:
            return InferredType(left.name, left.certain and right.certain)
        if left.name in {"integer", "scalar"} and right.name in {"integer", "scalar"}:
            return InferredType("scalar")
        return InferredType("unknown", False)

    if isinstance(expression, ListExpression):
        return InferredType("list")

    return InferredType("unknown", False)
