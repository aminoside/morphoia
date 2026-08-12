"""Command-line interface for the MORPHOIA experimental reference tools."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from ._engine_native import NativeEngine, NativeLibraryError
from .compiler import compile_document
from .engine_ir import read_bounded_file, replay_manifest, validate_manifest
from .engine_ir_contract import ContractError
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


def _engine_ir_error_payload(error: BaseException) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "FAIL",
        "error_type": type(error).__name__,
        "message": str(error),
    }
    if hasattr(error, "status_name"):
        payload["native_status"] = error.status_name
    return payload


def _write_engine_ir_error(error: BaseException, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(_engine_ir_error_payload(error), sort_keys=True), file=sys.stderr)
    else:
        print(f"morphoia: {type(error).__name__}: {error}", file=sys.stderr)


def _absolute_lexical_path(value: str, label: str) -> Path:
    if "\x00" in value:
        raise ValueError(f"{label} path contains NUL")
    path = Path(value)
    if any(component == ".." for component in path.parts):
        raise ValueError(f"{label} path must not contain '..'")
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.abspath(path))


def command_engine_ir_validate(arguments: argparse.Namespace) -> int:
    try:
        with NativeEngine(arguments.library) as engine:
            result = validate_manifest(
                read_bounded_file(_absolute_lexical_path(arguments.source, "source")),
                engine=engine,
            )
    except (OSError, ContractError, NativeLibraryError, TypeError, ValueError) as error:
        _write_engine_ir_error(error, as_json=arguments.json)
        return 1
    payload = {
        "status": "PASS",
        "format": result.document["format"],
        "format_version": result.document["format_version"],
        "manifest_sha256": result.manifest_sha256,
        "content_sha256": result.content_sha256,
        "canonical_manifest_size": len(result.canonical_manifest),
        "canonical_content_size": len(result.canonical_content),
    }
    if arguments.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"{arguments.source}: PASS Engine IR {payload['format_version']} "
            f"content sha256:{payload['content_sha256']}"
        )
    return 0


def command_engine_ir_replay(arguments: argparse.Namespace) -> int:
    cancellation = None
    try:
        with NativeEngine(arguments.library) as engine:
            result = replay_manifest(
                read_bounded_file(_absolute_lexical_path(arguments.recipe, "recipe")),
                _absolute_lexical_path(arguments.manifest, "manifest"),
                workspace_root=_absolute_lexical_path(arguments.workspace, "workspace"),
                engine=engine,
                timeout_seconds=arguments.timeout,
                cancellation=cancellation,
            )
    except (OSError, ContractError, NativeLibraryError, TypeError, ValueError) as error:
        _write_engine_ir_error(error, as_json=arguments.json)
        return 1
    payload = {
        "status": "PASS",
        "operation_key": result.operation_key,
        "manifest_sha256": result.manifest_sha256,
        "content_sha256": result.content_sha256,
        "resumed": result.resumed,
        "checkpoint": str(result.checkpoint_path),
    }
    if arguments.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        mode = "resumed" if result.resumed else "executed"
        print(
            f"{arguments.recipe}: PASS {mode} content sha256:{result.content_sha256} "
            f"operation {result.operation_key}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="morphoia",
        description=(
            "Morphoia Engine IR tools and experimental legacy construction-graph prototype"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate source syntax and semantics")
    validate_parser.add_argument("source")
    validate_parser.add_argument(
        "--json", action="store_true", help="emit machine-readable diagnostics"
    )
    validate_parser.set_defaults(function=command_validate)

    compile_parser = subparsers.add_parser(
        "compile",
        help="compile with the non-authoritative legacy prototype identity domain",
    )
    compile_parser.add_argument("source")
    compile_parser.add_argument("-o", "--output", required=True)
    compile_parser.set_defaults(function=command_compile)

    engine_ir_parser = subparsers.add_parser(
        "engine-ir",
        help="validate or replay public Engine IR through the required native library",
    )
    engine_ir_commands = engine_ir_parser.add_subparsers(
        dest="engine_ir_command", required=True
    )
    engine_ir_validate = engine_ir_commands.add_parser(
        "validate", help="validate and hash one public Engine IR manifest"
    )
    engine_ir_validate.add_argument("source")
    engine_ir_validate.add_argument("--library", type=Path)
    engine_ir_validate.add_argument("--json", action="store_true")
    engine_ir_validate.set_defaults(function=command_engine_ir_validate)

    engine_ir_replay = engine_ir_commands.add_parser(
        "replay", help="resolve and replay one immutable public Engine IR manifest"
    )
    engine_ir_replay.add_argument("recipe")
    engine_ir_replay.add_argument("--manifest", required=True)
    engine_ir_replay.add_argument("--workspace", required=True)
    engine_ir_replay.add_argument("--library", type=Path)
    engine_ir_replay.add_argument("--timeout", type=float, default=30.0)
    engine_ir_replay.add_argument("--json", action="store_true")
    engine_ir_replay.set_defaults(function=command_engine_ir_replay)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    return int(arguments.function(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
