"""Command-line interface for the MORPHOIA experimental reference tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .compiler import compile_document
from .validator import validate_file


def _diagnostic_payload(diagnostic) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": diagnostic.code,
        "severity": diagnostic.severity.value,
        "message": diagnostic.message,
    }
    if diagnostic.span:
        payload["location"] = {
            "line": diagnostic.span.line,
            "column": diagnostic.span.column,
            "end_line": diagnostic.span.end_line,
            "end_column": diagnostic.span.end_column,
        }
    if diagnostic.hint:
        payload["hint"] = diagnostic.hint
    return payload


def _print_diagnostics(path: Path, result, *, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "file": str(path),
                    "valid": result.ok,
                    "diagnostics": [_diagnostic_payload(item) for item in result.diagnostics],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not result.diagnostics:
        print(f"{path}: valid")
        return
    for diagnostic in result.diagnostics:
        location = ""
        if diagnostic.span:
            location = f":{diagnostic.span.line}:{diagnostic.span.column}"
        print(
            f"{path}{location}: {diagnostic.severity.value} {diagnostic.code}: {diagnostic.message}",
            file=sys.stderr if diagnostic.severity.value == "error" else sys.stdout,
        )
        if diagnostic.hint:
            print(f"  hint: {diagnostic.hint}")


def command_validate(arguments: argparse.Namespace) -> int:
    path = Path(arguments.source)
    result = validate_file(path)
    _print_diagnostics(path, result, as_json=arguments.json)
    return 0 if result.ok else 1


def command_compile(arguments: argparse.Namespace) -> int:
    path = Path(arguments.source)
    result = validate_file(path)
    _print_diagnostics(path, result, as_json=False)
    if not result.ok or result.document is None:
        return 1
    ir = compile_document(result.document)
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(ir, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {output} ({ir['semantic_sha256']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="morphoia",
        description="Experimental MORPHOIA parser, semantic validator and canonical IR compiler",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate source syntax and semantics")
    validate_parser.add_argument("source")
    validate_parser.add_argument(
        "--json", action="store_true", help="emit machine-readable diagnostics"
    )
    validate_parser.set_defaults(function=command_validate)

    compile_parser = subparsers.add_parser("compile", help="compile source to canonical JSON IR")
    compile_parser.add_argument("source")
    compile_parser.add_argument("-o", "--output", required=True)
    compile_parser.set_defaults(function=command_compile)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    return int(arguments.function(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
