"""Semantic checks required by the MORPHOIA experimental P1 profile."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .model import (
    Binary,
    Call,
    Diagnostic,
    Document,
    Expression,
    ListExpression,
    Literal,
    Model,
    Name,
    Node,
    Severity,
    Unary,
)
from .typesystem import UNIT_DIMENSIONS, infer_expression_type, normalize_type

DECLARATION_KINDS = {
    "parameter",
    "constant",
    "datum",
    "sketch",
    "feature",
    "reference",
    "material",
    "assembly",
    "pmi",
    "tolerance",
}

PROFILE_OPERATIONS: dict[str, set[str]] = {
    "P1": {
        "extrude",
        "cut",
        "revolve",
        "boolean",
        "hole",
        "pattern",
        "mirror",
        "fillet",
        "chamfer",
    },
    "P2": {"thread"},
    "P3": set(),
    "P4": {"sweep", "loft", "blend", "shell", "draft"},
}

BUILTIN_ROOTS = {
    "world",
    "origin",
    "x",
    "y",
    "z",
    "xy",
    "xz",
    "yz",
    "true",
    "false",
    "null",
    "unique",
    "one",
    "many",
    "missing",
    "solid",
    "surface",
    "face",
    "edge",
    "vertex",
    "profile",
    "blind",
    "through_all",
    "symmetric",
    "new_body",
    "join",
    "subtract",
    "intersect",
    "observed",
    "certain",
    "hypothesis",
    "ambiguous",
    "inferred",
    "unknown",
}

TOLERANCE_TYPES = {
    "kernel_tolerance",
    "measurement_uncertainty",
    "dimensional_tolerance",
    "gdt_zone",
}


def _attribute_map(node: Node | Model) -> dict[str, Expression]:
    return dict(node.attributes)


def _literal_text(expression: Expression | None) -> str | None:
    if isinstance(expression, Literal):
        return str(expression.value)
    if isinstance(expression, Name):
        return expression.text
    return None


def _expressions(node: Node) -> Iterable[Expression]:
    if node.value is not None:
        yield node.value
    if node.context is not None:
        yield node.context
    for _, value in node.attributes:
        yield value
    for child in node.body:
        yield from _expressions(child)


def _names(expression: Expression, *, include_function: bool = False) -> Iterable[Name]:
    if isinstance(expression, Name):
        yield expression
    elif isinstance(expression, Call):
        if include_function:
            yield expression.function
        for argument in expression.arguments:
            yield from _names(argument, include_function=include_function)
        for _, value in expression.keywords:
            yield from _names(value, include_function=include_function)
    elif isinstance(expression, Unary):
        yield from _names(expression.operand, include_function=include_function)
    elif isinstance(expression, Binary):
        yield from _names(expression.left, include_function=include_function)
        yield from _names(expression.right, include_function=include_function)
    elif isinstance(expression, ListExpression):
        for item in expression.items:
            yield from _names(item, include_function=include_function)


def _local_names(node: Node) -> set[str]:
    return {child.name for child in node.body if child.name}  # type: ignore[misc]


def _profile_operations(profile: str) -> set[str]:
    order = ["P1", "P2", "P3", "P4"]
    if profile not in order:
        return set()
    allowed: set[str] = set()
    for current in order[: order.index(profile) + 1]:
        allowed.update(PROFILE_OPERATIONS[current])
    return allowed


def validate_semantics(document: Document) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if document.version != "0.1":
        diagnostics.append(
            Diagnostic(
                "MORPH-E001",
                Severity.ERROR,
                f"unsupported experimental language version {document.version!r}",
                document.span,
                "use 'morphoia 0.1;' for this reference implementation",
            )
        )
    for model in document.models:
        diagnostics.extend(_validate_model(model))
    return diagnostics


def _validate_model(model: Model) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    attributes = _attribute_map(model)
    profile = _literal_text(attributes.get("profile")) or "P1"
    if profile not in PROFILE_OPERATIONS:
        diagnostics.append(
            Diagnostic(
                "MORPH-E100", Severity.ERROR, f"unknown conformance profile {profile!r}", model.span
            )
        )
        profile = "P1"

    symbols: dict[str, Node] = {}
    for node in model.body:
        if node.kind not in DECLARATION_KINDS or not node.name:
            continue
        if node.name in symbols:
            diagnostics.append(
                Diagnostic(
                    "MORPH-E101",
                    Severity.ERROR,
                    f"duplicate declaration {node.name!r}",
                    node.span,
                )
            )
        else:
            symbols[node.name] = node

    symbol_types = {name: node.type_name for name, node in symbols.items()}
    graph: dict[str, set[str]] = defaultdict(set)

    for name, node in symbols.items():
        local_names = _local_names(node)
        for expression in _expressions(node):
            for reference in _names(expression):
                root = reference.parts[0]
                if root in symbols:
                    graph[name].add(root)
                elif (
                    root not in local_names
                    and not (
                        root in BUILTIN_ROOTS and (len(reference.parts) == 1 or root == "world")
                    )
                    and root not in UNIT_DIMENSIONS
                ):
                    diagnostics.append(
                        Diagnostic(
                            "MORPH-E102",
                            Severity.ERROR,
                            f"unknown reference {reference.text!r}",
                            reference.span,
                        )
                    )

        if node.kind == "parameter" and node.type_name and node.value is not None:
            expected = normalize_type(node.type_name)
            actual = infer_expression_type(node.value, symbol_types)
            if actual.certain and expected != actual.name:
                diagnostics.append(
                    Diagnostic(
                        "MORPH-E110",
                        Severity.ERROR,
                        f"parameter {name!r} expects {expected}, got {actual.name}",
                        node.value.span,
                    )
                )

        if node.kind == "feature":
            operation = (node.type_name or "").split(".")[-1]
            if operation not in _profile_operations(profile):
                diagnostics.append(
                    Diagnostic(
                        "MORPH-E120",
                        Severity.ERROR,
                        f"operation {operation!r} is not available in profile {profile}",
                        node.span,
                        "raise the declared profile or replace the operation with an explicitly supported fallback",
                    )
                )

        if node.kind == "reference":
            diagnostics.extend(_validate_reference(node))

        if node.kind == "tolerance" and node.type_name not in TOLERANCE_TYPES:
            diagnostics.append(
                Diagnostic(
                    "MORPH-E140",
                    Severity.ERROR,
                    "tolerance must declare one of the four non-interchangeable tolerance types",
                    node.span,
                    ", ".join(sorted(TOLERANCE_TYPES)),
                )
            )

        node_attributes = _attribute_map(node)
        status = _literal_text(node_attributes.get("status"))
        if status in {"hypothesis", "ambiguous", "inferred"} and "evidence" not in node_attributes:
            diagnostics.append(
                Diagnostic(
                    "MORPH-E150",
                    Severity.ERROR,
                    f"{status} declaration {name!r} requires evidence provenance",
                    node.span,
                )
            )

    diagnostics.extend(_detect_cycles(graph, symbols))
    return diagnostics


def _validate_reference(node: Node) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not isinstance(node.value, Call) or node.value.function.text != "select":
        return [
            Diagnostic(
                "MORPH-E130",
                Severity.ERROR,
                "persistent reference must use an explicit select(...) query",
                node.span,
            )
        ]
    keywords = dict(node.value.keywords)
    cardinality = _literal_text(keywords.get("cardinality"))
    if cardinality not in {"unique", "one"}:
        diagnostics.append(
            Diagnostic(
                "MORPH-E131",
                Severity.ERROR,
                "persistent reference must require unique cardinality",
                node.value.span,
                "use cardinality = unique; ambiguity is never resolved silently",
            )
        )
    if not node.value.arguments:
        diagnostics.append(
            Diagnostic(
                "MORPH-E132",
                Severity.ERROR,
                "persistent reference requires a lineage-bearing source collection",
                node.value.span,
            )
        )
    if "role" not in keywords:
        diagnostics.append(
            Diagnostic(
                "MORPH-E133",
                Severity.ERROR,
                "persistent reference requires a semantic role",
                node.value.span,
            )
        )
    signature_keys = {"normal", "surface", "area", "radius", "adjacent", "signature"}
    if not signature_keys.intersection(keywords):
        diagnostics.append(
            Diagnostic(
                "MORPH-E134",
                Severity.ERROR,
                "persistent reference requires geometry or adjacency evidence",
                node.value.span,
            )
        )
    return diagnostics


def _detect_cycles(graph: dict[str, set[str]], symbols: dict[str, Node]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    state: dict[str, int] = {}
    stack: list[str] = []
    reported: set[tuple[str, ...]] = set()

    def visit(name: str) -> None:
        state[name] = 1
        stack.append(name)
        for dependency in sorted(graph.get(name, set())):
            if dependency not in symbols:
                continue
            if state.get(dependency, 0) == 0:
                visit(dependency)
            elif state.get(dependency) == 1:
                start = stack.index(dependency)
                cycle = tuple(stack[start:] + [dependency])
                if cycle not in reported:
                    reported.add(cycle)
                    diagnostics.append(
                        Diagnostic(
                            "MORPH-E103",
                            Severity.ERROR,
                            "dependency cycle: " + " -> ".join(cycle),
                            symbols[name].span,
                        )
                    )
        stack.pop()
        state[name] = 2

    for symbol in sorted(symbols):
        if state.get(symbol, 0) == 0:
            visit(symbol)
    return diagnostics


def dependency_order(model: Model) -> list[str]:
    """Return a deterministic topological order for named declarations."""

    symbols = {
        node.name: node for node in model.body if node.name and node.kind in DECLARATION_KINDS
    }
    graph: dict[str, set[str]] = defaultdict(set)
    for name, node in symbols.items():
        local_names = _local_names(node)
        for expression in _expressions(node):
            for reference in _names(expression):
                root = reference.parts[0]
                if root in symbols and root not in local_names and root != name:
                    graph[name].add(root)

    ordered: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        for dependency in sorted(graph.get(name, set())):
            visit(dependency)
        ordered.append(name)

    for name in sorted(symbols):
        visit(name)
    return ordered
