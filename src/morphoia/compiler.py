"""Canonical JSON lowering for the MORPHOIA construction graph candidate."""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from .model import (
    Binary,
    Call,
    Document,
    Expression,
    ListExpression,
    Literal,
    Model,
    Name,
    Node,
    Unary,
)
from .semantic import dependency_order

IR_FORMAT = "morphoia.canonical-construction-graph"
IR_VERSION = "0.1"
_ID_NAMESPACE = uuid.UUID("22b8aa1e-a037-5d7b-89f8-b7af0c8fc2ad")


def _attribute_value(node: Node | Model, name: str) -> Expression | None:
    return dict(node.attributes).get(name)


def _explicit_id(node: Node | Model) -> str | None:
    value = _attribute_value(node, "id")
    if isinstance(value, Literal) and isinstance(value.value, str):
        return value.value
    return None


def _stable_id(path: str, node: Node | Model) -> str:
    return _explicit_id(node) or str(uuid.uuid5(_ID_NAMESPACE, path))


def expression_to_ir(expression: Expression) -> dict[str, Any]:
    if isinstance(expression, Literal):
        if isinstance(expression.value, Decimal):
            value: Any = format(expression.value, "f")
            result: dict[str, Any] = {
                "kind": "literal",
                "value": value,
                "numeric_encoding": "decimal",
            }
        else:
            result = {"kind": "literal", "value": expression.value}
        if expression.unit:
            result["unit"] = expression.unit
        return result
    if isinstance(expression, Name):
        return {"kind": "reference", "path": expression.text}
    if isinstance(expression, Call):
        return {
            "kind": "call",
            "operation": expression.function.text,
            "arguments": [expression_to_ir(argument) for argument in expression.arguments],
            "keywords": {
                key: expression_to_ir(value)
                for key, value in sorted(expression.keywords, key=lambda item: item[0])
            },
        }
    if isinstance(expression, Unary):
        return {
            "kind": "unary",
            "operator": expression.operator,
            "operand": expression_to_ir(expression.operand),
        }
    if isinstance(expression, Binary):
        return {
            "kind": "binary",
            "operator": expression.operator,
            "left": expression_to_ir(expression.left),
            "right": expression_to_ir(expression.right),
        }
    if isinstance(expression, ListExpression):
        return {"kind": "list", "items": [expression_to_ir(item) for item in expression.items]}
    raise TypeError(f"unsupported expression {type(expression)!r}")


def _attributes_to_ir(node: Node | Model) -> dict[str, Any]:
    return {
        key: expression_to_ir(value)
        for key, value in sorted(node.attributes, key=lambda item: item[0])
        if key != "id"
    }


def _node_to_ir(node: Node, parent_path: str) -> dict[str, Any]:
    identity_component = node.name or f"{node.kind}@{node.span.line}:{node.span.column}"
    path = f"{parent_path}/{identity_component}"
    result: dict[str, Any] = {
        "id": _stable_id(path, node),
        "kind": node.kind,
    }
    if node.name:
        result["name"] = node.name
    if node.type_name:
        result["type"] = node.type_name
    if node.value is not None:
        result["value"] = expression_to_ir(node.value)
    if node.context is not None:
        result["context"] = expression_to_ir(node.context)
    attributes = _attributes_to_ir(node)
    if attributes:
        result["attributes"] = attributes
    if node.body:
        result["body"] = [_node_to_ir(child, path) for child in node.body]
    return result


def _model_to_ir(document: Document, model: Model) -> dict[str, Any]:
    namespace = document.namespace or "local"
    path = f"{namespace}/{model.name}"
    return {
        "id": _stable_id(path, model),
        "name": model.name,
        "attributes": _attributes_to_ir(model),
        "dependency_order": dependency_order(model),
        "declarations": [_node_to_ir(node, path) for node in model.body],
    }


def compile_document(document: Document) -> dict[str, Any]:
    """Lower a validated document to deterministic, backend-neutral JSON IR."""

    ir = {
        "format": IR_FORMAT,
        "format_version": IR_VERSION,
        "source_language": f"morphoia/{document.version}",
        "namespace": document.namespace or "local",
        "imports": [
            {"source": imported.source, **({"alias": imported.alias} if imported.alias else {})}
            for imported in document.imports
        ],
        "models": [_model_to_ir(document, model) for model in document.models],
        "execution_contract": {
            "authority": "semantic-construction-graph",
            "explicit_result_required": True,
            "ambiguity_policy": "error-or-human-decision",
            "numeric_mode": "backend-profile-locked",
            "step_anchor": [
                "ISO-10303-42",
                "ISO-10303-55",
                "ISO-10303-108",
                "ISO-10303-109",
                "ISO-10303-111",
                "ISO-10303-112",
                "ISO-10303-113",
                "ISO-10303-242",
            ],
        },
    }
    ir["semantic_sha256"] = semantic_hash(ir)
    return ir


def canonical_json(ir: dict[str, Any], *, indent: int | None = 2) -> str:
    return (
        json.dumps(
            ir,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":") if indent is None else None,
            indent=indent,
        )
        + "\n"
    )


def semantic_hash(ir: dict[str, Any]) -> str:
    payload = dict(ir)
    payload.pop("semantic_sha256", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
