#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Fail-closed validation for the durable Morphoia Engine checkpoint.

This validator intentionally uses only the Python standard library.  The JSON
Schema is a published contract, while the checks below also verify filesystem
hashes and invariants that JSON Schema cannot express.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable


STATUS_VALUES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
BRANCH_RE = re.compile(r"^engine(?:-p[0-9]+-[a-z0-9][a-z0-9-]*)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED_BASELINES = {
    "docs/engine/baselines/Morphoia_Engine_Cahier_des_charges_technique_v0.1.pdf": (
        "40cdb3288e7b1a38a557d1459147aed7ac1d5646aaa5d6ab09a287abc9b22263"
    ),
    "docs/engine/baselines/Morphoia_Engine_Architecture_Reference_v0.2.pdf": (
        "8519bba50ab9a05d469780ec074588034714d83d24ef09404705d292bfa02368"
    ),
    "docs/engine/baselines/morphoia-logo-vectoriel.zip": (
        "d9957fb70c18f2cdea37b7a036e3ddab6b05492d1a3ea978f5ea9f33313c00c5"
    ),
}
TOP_LEVEL_FIELDS = {
    "schema_version",
    "license",
    "updated_at",
    "project_state",
    "phase",
    "lot",
    "remote",
    "git",
    "tasks",
    "environment",
    "source_digests",
    "commands",
    "tests",
    "parameters",
    "seeds",
    "inputs",
    "outputs",
    "job_ids",
    "decisions",
    "deviations",
    "external_dependencies",
    "next_action",
}


class DuplicateKeyError(ValueError):
    """Raised when a JSON object contains the same key more than once."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError) as error:
        raise ValueError(f"cannot read canonical checkpoint JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("checkpoint root must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repository_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("repository path must be a non-empty string")
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts or "." in posix.parts:
        raise ValueError(f"unsafe repository path: {value!r}")
    candidate = root.joinpath(*posix.parts)
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"repository path escapes root: {value!r}") from error
    return candidate


def tree_sha256(root: Path, directory: str, excluded: Iterable[str]) -> str:
    base = repository_path(root, directory)
    if not base.is_dir():
        raise ValueError(f"source digest path is not a directory: {directory}")
    excluded_set = set(excluded)
    records: list[bytes] = []
    for path in sorted(item for item in base.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded_set:
            continue
        if path.is_symlink():
            raise ValueError(f"source digest tree contains a symbolic link: {relative}")
        try:
            path.resolve(strict=True).relative_to(root.resolve())
        except ValueError as error:
            raise ValueError(f"source digest file escapes repository root: {relative}") from error
        records.append(relative.encode("utf-8") + b"\0" + sha256_file(path).encode("ascii") + b"\n")
    digest = hashlib.sha256()
    for record in records:
        digest.update(record)
    return digest.hexdigest()


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unique_strings(value: Any, name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(_is_nonempty_string(item) for item in value):
        errors.append(f"{name} must be an array of non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{name} must not contain duplicates")
    return value


def _exact_fields(value: Any, fields: set[str], name: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return False
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        errors.append(f"{name} is missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{name} has unknown fields: {', '.join(unknown)}")
    return not missing and not unknown


def _validate_status(value: Any, name: str, errors: list[str]) -> None:
    if not isinstance(value, str) or value not in STATUS_VALUES:
        errors.append(f"{name} must be one of {sorted(STATUS_VALUES)}")


def validate_checkpoint(data: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()

    _exact_fields(data, TOP_LEVEL_FIELDS, "checkpoint", errors)
    if data.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if data.get("license") != "CC-BY-4.0":
        errors.append("checkpoint document license must be CC-BY-4.0")
    if not isinstance(data.get("updated_at"), str) or not DATE_RE.fullmatch(data["updated_at"]):
        errors.append("updated_at must be an ISO YYYY-MM-DD date")
    if not _is_nonempty_string(data.get("project_state")):
        errors.append("project_state must be a non-empty string")
    phase = data.get("phase")
    if phase not in {*(f"E{index}" for index in range(10)), "WAITING_FOR_MVX_SPEC"}:
        errors.append("phase must be E0-E9 or WAITING_FOR_MVX_SPEC")
    if not _is_nonempty_string(data.get("lot")):
        errors.append("lot must be a non-empty string")

    remote_fields = {
        "canonical_name",
        "canonical_url",
        "repository",
        "visibility",
        "default_branch",
        "integration_branch",
        "publication_status",
        "publication_note",
    }
    remote = data.get("remote")
    if _exact_fields(remote, remote_fields, "remote", errors):
        if remote["canonical_name"] != "origin":
            errors.append("remote.canonical_name must be origin for this checkpoint")
        if remote["canonical_url"].lower() != "https://github.com/aminoside/morphoia.git":
            errors.append("remote.canonical_url is not the canonical repository URL")
        if remote["repository"] != "Aminoside/morphoia":
            errors.append("remote.repository must be Aminoside/morphoia")
        if remote["visibility"] not in {"public", "private", "internal"}:
            errors.append("remote.visibility is invalid")
        if remote["integration_branch"] != "engine":
            errors.append("remote.integration_branch must be engine")
        _validate_status(remote["publication_status"], "remote.publication_status", errors)
        if not _is_nonempty_string(remote["publication_note"]):
            errors.append("remote.publication_note must be non-empty")

    git_fields = {
        "branch",
        "upstream",
        "base_parent",
        "integration_branch_initially_present",
        "branch_protection_observed",
        "published_commit_sha",
        "note",
    }
    git = data.get("git")
    if _exact_fields(git, git_fields, "git", errors):
        if not isinstance(git["branch"], str) or not BRANCH_RE.fullmatch(git["branch"]):
            errors.append("git.branch is not engine or an authorized engine-p* branch")
        if git["upstream"] != f"origin/{git['branch']}":
            errors.append("git.upstream must match origin/<git.branch>")
        if not isinstance(git["base_parent"], str) or not COMMIT_RE.fullmatch(git["base_parent"]):
            errors.append("git.base_parent must be a lowercase 40-hex commit id")
        for name in ("integration_branch_initially_present", "branch_protection_observed"):
            if not isinstance(git[name], bool):
                errors.append(f"git.{name} must be boolean")
        published = git["published_commit_sha"]
        if published is not None and (
            not isinstance(published, str) or not COMMIT_RE.fullmatch(published)
        ):
            errors.append("git.published_commit_sha must be null or a lowercase 40-hex commit id")
        if not _is_nonempty_string(git["note"]):
            errors.append("git.note must be non-empty")

    tasks = data.get("tasks")
    task_fields = {"completed", "in_progress", "remaining"}
    if _exact_fields(tasks, task_fields, "tasks", errors):
        task_sets: list[set[str]] = []
        for field in sorted(task_fields):
            values = _unique_strings(tasks[field], f"tasks.{field}", errors)
            task_sets.append(set(values))
        if any(
            task_sets[left] & task_sets[right]
            for left in range(3)
            for right in range(left + 1, 3)
        ):
            errors.append(
                "task identifiers must be disjoint across completed/in_progress/remaining"
            )

    environment = data.get("environment")
    if not isinstance(environment, dict) or not environment:
        errors.append("environment must be a non-empty object")

    source = data.get("source_digests")
    source_fields = {"algorithm", "excluded", "paths", "note"}
    if _exact_fields(source, source_fields, "source_digests", errors):
        if source["algorithm"] != "sha256 over sorted path, NUL, file sha256, LF records":
            errors.append("source_digests.algorithm is not the defined algorithm")
        excluded = _unique_strings(source["excluded"], "source_digests.excluded", errors)
        if "docs/engine/checkpoint.json" not in excluded:
            errors.append("source_digests.excluded must contain docs/engine/checkpoint.json")
        paths = source["paths"]
        if not isinstance(paths, list) or not paths:
            errors.append("source_digests.paths must be a non-empty array")
        else:
            seen_paths: set[str] = set()
            for index, item in enumerate(paths):
                label = f"source_digests.paths[{index}]"
                if not _exact_fields(item, {"path", "sha256", "status"}, label, errors):
                    continue
                path_value = item["path"]
                if not _is_nonempty_string(path_value):
                    errors.append(f"{label}.path must be a non-empty string")
                    continue
                if path_value in seen_paths:
                    errors.append(f"{label}.path is duplicated")
                seen_paths.add(path_value)
                _validate_status(item["status"], f"{label}.status", errors)
                digest = item["sha256"]
                if item["status"] == "PASS":
                    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                        errors.append(f"{label}.sha256 must be set for PASS")
                    else:
                        try:
                            actual = tree_sha256(root, path_value, excluded)
                            if actual != digest:
                                errors.append(f"{label}.sha256 does not match the repository tree")
                        except (OSError, ValueError) as error:
                            errors.append(f"{label}: {error}")
                elif digest is not None:
                    errors.append(f"{label}.sha256 must be null unless status is PASS")
            if not {"cpp", "spec", "docs/engine"}.issubset(seen_paths):
                errors.append("source_digests.paths must include cpp, spec, and docs/engine")

    commands = data.get("commands")
    if not isinstance(commands, list):
        errors.append("commands must be an array")
    else:
        for index, item in enumerate(commands):
            label = f"commands[{index}]"
            if not _exact_fields(item, {"command", "result", "summary"}, label, errors):
                continue
            if not _is_nonempty_string(item["command"]) or not _is_nonempty_string(item["summary"]):
                errors.append(f"{label} command and summary must be non-empty")
            _validate_status(item["result"], f"{label}.result", errors)

    tests = data.get("tests")
    if not isinstance(tests, list):
        errors.append("tests must be an array")
    else:
        test_ids: set[str] = set()
        for index, item in enumerate(tests):
            label = f"tests[{index}]"
            allowed = {"id", "profile", "status", "count", "reason"}
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            missing = {"id", "profile", "status"} - set(item)
            unknown = set(item) - allowed
            if missing:
                errors.append(f"{label} is missing fields: {', '.join(sorted(missing))}")
                continue
            if unknown:
                errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
            identifier = item["id"]
            if not _is_nonempty_string(identifier):
                errors.append(f"{label}.id must be non-empty and unique")
            elif identifier in test_ids:
                errors.append(f"{label}.id must be non-empty and unique")
            else:
                test_ids.add(identifier)
            if not _is_nonempty_string(item["profile"]):
                errors.append(f"{label}.profile must be non-empty")
            _validate_status(item["status"], f"{label}.status", errors)
            if item["status"] != "PASS" and not _is_nonempty_string(item.get("reason")):
                errors.append(f"{label}.reason is required for non-PASS status")
            if "count" in item and (
                not isinstance(item["count"], int)
                or isinstance(item["count"], bool)
                or item["count"] < 0
            ):
                errors.append(f"{label}.count must be a non-negative integer")

    parameters = data.get("parameters")
    parameter_fields = {
        "maximum_single_download_bytes",
        "maximum_job_seconds",
        "maximum_disk_fraction",
        "maximum_disk_consumption_gib_at_probe",
    }
    if _exact_fields(parameters, parameter_fields, "parameters", errors):
        maximum_download = parameters["maximum_single_download_bytes"]
        if (
            not isinstance(maximum_download, int)
            or isinstance(maximum_download, bool)
            or maximum_download <= 0
            or maximum_download > 2 * 1024**3
        ):
            errors.append("maximum_single_download_bytes must be an integer no greater than 2 GiB")
        maximum_seconds = parameters["maximum_job_seconds"]
        if (
            not isinstance(maximum_seconds, int)
            or isinstance(maximum_seconds, bool)
            or maximum_seconds <= 0
            or maximum_seconds > 3600
        ):
            errors.append("maximum_job_seconds must be an integer no greater than 3600")
        fraction = parameters["maximum_disk_fraction"]
        if (
            not isinstance(fraction, (int, float))
            or isinstance(fraction, bool)
            or fraction > 0.7
            or fraction <= 0
        ):
            errors.append("maximum_disk_fraction must be greater than zero and no greater than 0.7")
        disk = parameters["maximum_disk_consumption_gib_at_probe"]
        if not isinstance(disk, (int, float)) or isinstance(disk, bool) or disk <= 0:
            errors.append("maximum_disk_consumption_gib_at_probe must be positive")

    seeds = data.get("seeds")
    if not isinstance(seeds, list) or any(
        not isinstance(item, (str, int)) or isinstance(item, bool) for item in seeds
    ):
        errors.append("seeds must be an array of strings or integers")
    elif len(seeds) != len({str(item) for item in seeds}):
        errors.append("seeds must not contain duplicates")

    inputs = data.get("inputs")
    input_map: dict[str, str] = {}
    if not isinstance(inputs, list):
        errors.append("inputs must be an array")
    else:
        for index, item in enumerate(inputs):
            label = f"inputs[{index}]"
            if not _exact_fields(item, {"path", "sha256"}, label, errors):
                continue
            path_value, digest = item["path"], item["sha256"]
            if not _is_nonempty_string(path_value):
                errors.append(f"{label}.path must be a non-empty string")
                continue
            if path_value in input_map:
                errors.append(f"{label}.path is duplicated")
            input_map[path_value] = digest
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                errors.append(f"{label}.sha256 must be lowercase SHA-256")
                continue
            try:
                path = repository_path(root, path_value)
                if not path.is_file():
                    errors.append(f"{label}.path does not name a regular file")
                elif sha256_file(path) != digest:
                    errors.append(f"{label}.sha256 does not match the file")
            except (OSError, ValueError) as error:
                errors.append(f"{label}: {error}")
        for path_value, expected in REQUIRED_BASELINES.items():
            if input_map.get(path_value) != expected:
                errors.append(
                    f"inputs must include immutable baseline {path_value} with its validated digest"
                )

    outputs = data.get("outputs")
    if not isinstance(outputs, list):
        errors.append("outputs must be an array")
    else:
        output_uris: set[str] = set()
        for index, item in enumerate(outputs):
            label = f"outputs[{index}]"
            allowed = {"uri", "sha256", "status", "note"}
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            missing = {"uri", "sha256", "status", "note"} - set(item)
            unknown = set(item) - allowed
            if missing:
                errors.append(f"{label} is missing fields: {', '.join(sorted(missing))}")
                continue
            if unknown:
                errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
            uri = item["uri"]
            if not _is_nonempty_string(uri):
                errors.append(f"{label}.uri must be non-empty, scheme-qualified, and unique")
                uri = ""
            elif ":" not in uri or uri in output_uris:
                errors.append(f"{label}.uri must be non-empty, scheme-qualified, and unique")
            else:
                output_uris.add(uri)
            _validate_status(item["status"], f"{label}.status", errors)
            digest = item["sha256"]
            if item["status"] == "PASS":
                if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                    errors.append(f"{label}.sha256 must be set for PASS")
                elif isinstance(uri, str) and uri.startswith("repo:"):
                    try:
                        path = repository_path(root, uri.removeprefix("repo:"))
                        if not path.is_file() or sha256_file(path) != digest:
                            errors.append(f"{label}.sha256 does not match the repository output")
                    except (OSError, ValueError) as error:
                        errors.append(f"{label}: {error}")
            elif digest is not None:
                errors.append(f"{label}.sha256 must be null unless status is PASS")
            if not _is_nonempty_string(item["note"]):
                errors.append(f"{label}.note must be non-empty")

    _unique_strings(data.get("job_ids"), "job_ids", errors)
    _unique_strings(data.get("decisions"), "decisions", errors)
    _unique_strings(data.get("deviations"), "deviations", errors)

    dependencies = data.get("external_dependencies")
    if not isinstance(dependencies, list):
        errors.append("external_dependencies must be an array")
    else:
        names: set[str] = set()
        for index, item in enumerate(dependencies):
            label = f"external_dependencies[{index}]"
            allowed = {"name", "status", "blocking_scope", "reason"}
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            missing = {"name", "status"} - set(item)
            unknown = set(item) - allowed
            if missing:
                errors.append(f"{label} is missing fields: {', '.join(sorted(missing))}")
                continue
            if unknown:
                errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
            name = item["name"]
            if not _is_nonempty_string(name):
                errors.append(f"{label}.name must be non-empty and unique")
            elif name in names:
                errors.append(f"{label}.name must be non-empty and unique")
            else:
                names.add(name)
            _validate_status(item["status"], f"{label}.status", errors)
            if item["status"] in {"BLOCKED", "NOT_RUN", "FAIL"} and not any(
                _is_nonempty_string(item.get(field)) for field in ("blocking_scope", "reason")
            ):
                errors.append(f"{label} needs blocking_scope or reason for {item['status']}")

    if not _is_nonempty_string(data.get("next_action")) or len(data["next_action"].strip()) < 20:
        errors.append("next_action must be one precise, non-empty idempotent action")

    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "checkpoint",
        nargs="?",
        type=Path,
        default=Path("docs/engine/checkpoint.json"),
        help="checkpoint JSON to validate",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root used for path and digest verification",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    checkpoint = arguments.checkpoint
    if not checkpoint.is_absolute():
        checkpoint = arguments.root / checkpoint
    try:
        data = load_json(checkpoint)
        errors = validate_checkpoint(data, arguments.root)
    except ValueError as error:
        errors = [str(error)]
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: checkpoint is structurally valid and recorded hashes match ({checkpoint})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
