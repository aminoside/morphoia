"""CLI handlers for the MVX validation programme."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .artifacts import (
    FreezeArtifactError,
    commit_freeze_transaction,
    write_public_json_once,
)
from .cohort import FROZEN_EXACT_TARGETS, CohortFreezeError, freeze_cohort
from .custody import (
    create_custody_precommit,
    sha256_hex,
    synthetic_dry_run,
)
from .protocol import (
    PROJECT_ROOT,
    create_seal,
    load_yaml,
    protocol_root,
    verify_protocol,
    write_g0_verdict,
)


def command_protocol_verify(arguments: argparse.Namespace) -> int:
    verification = verify_protocol(require_seal=True)
    payload = {
        "valid": verification.ok,
        "protocol_root_sha256": verification.root_sha256,
        "checks": [
            {"id": item.identifier, "passed": item.passed, "evidence": item.evidence}
            for item in verification.checks
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if verification.ok else 1


def command_protocol_seal(arguments: argparse.Namespace) -> int:
    seal = create_seal()
    verification = verify_protocol(require_seal=True)
    verdict = write_g0_verdict(verification)
    print(
        json.dumps(
            {
                "protocol_root_sha256": seal["protocol_root_sha256"],
                "G0": verdict["verdict"],
            },
            indent=2,
        )
    )
    return 0 if verification.ok else 1


def _read_secret_fd(descriptor: int, *, name: str) -> str:
    if descriptor in {0, 1, 2}:
        raise SystemExit(f"{name} must use a dedicated inherited file descriptor")
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = 4097 - total
        if remaining <= 0:
            raise SystemExit(f"{name} exceeds the maximum secret length")
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > 4096:
        raise SystemExit(f"{name} exceeds the maximum secret length")
    payload = b"".join(chunks)
    try:
        value = payload.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise SystemExit(f"{name} must contain hexadecimal ASCII") from error
    return value


def command_cohort_freeze(arguments: argparse.Namespace) -> int:
    if arguments.selection_secret_fd == arguments.split_secret_fd:
        raise SystemExit("selection and split secrets require distinct file descriptors")
    private_directory = Path(arguments.private_dir).resolve()
    release_directory = Path(arguments.release_dir).resolve()
    if private_directory == release_directory:
        raise SystemExit("private and release directories must be distinct")
    if private_directory.is_relative_to(PROJECT_ROOT.resolve()):
        raise SystemExit("the private custody directory must be outside the repository")
    if release_directory.is_relative_to(private_directory) or private_directory.is_relative_to(
        release_directory
    ):
        raise SystemExit("private and release directories may not contain one another")

    input_path = Path(arguments.input)
    precommit_path = Path(arguments.precommit)
    publication_receipt_path = Path(arguments.publication_receipt)
    records = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selection_secret = _read_secret_fd(
        arguments.selection_secret_fd, name="selection secret"
    )
    split_secret = _read_secret_fd(arguments.split_secret_fd, name="split secret")
    split_spec = load_yaml("docs/mvx/validation/p0/split-spec.yaml")
    try:
        precommit = json.loads(precommit_path.read_text(encoding="utf-8"))
        publication_receipt = json.loads(
            publication_receipt_path.read_text(encoding="utf-8")
        )
        frozen = freeze_cohort(
            records,
            protocol_root_sha256=protocol_root(),
            snapshot_sha256=arguments.snapshot_sha256,
            expected_input_records_sha256=arguments.eligible_records_sha256,
            selection_seed_hex=selection_secret,
            split_secret_hex=split_secret,
            exact_targets=split_spec["confirmation_targets"],
            precommit=precommit,
            publication_receipt=publication_receipt,
        )
        receipt = commit_freeze_transaction(
            frozen=frozen,
            precommit=precommit,
            publication_receipt=publication_receipt,
            private_directory=private_directory,
            release_directory=release_directory,
        )
    except (OSError, ValueError, json.JSONDecodeError, CohortFreezeError, FreezeArtifactError) as error:
        raise SystemExit(f"cohort freeze failed closed: {error}") from error
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "freeze_id": receipt["freeze_id"],
                "selected": len(frozen.selected_records),
                "reserve": len(frozen.reserve_records),
                "private_dir": str(private_directory),
                "release_dir": str(release_directory),
            },
            indent=2,
        )
    )
    return 0


def command_custody_precommit(arguments: argparse.Namespace) -> int:
    if arguments.selection_secret_fd == arguments.split_secret_fd:
        raise SystemExit("selection and split secrets require distinct file descriptors")
    selection_secret = _read_secret_fd(
        arguments.selection_secret_fd, name="selection secret"
    )
    split_secret = _read_secret_fd(arguments.split_secret_fd, name="split secret")
    precommit = create_custody_precommit(
        protocol_root_sha256=protocol_root(),
        snapshot_sha256=arguments.snapshot_sha256,
        eligible_records_sha256=arguments.eligible_records_sha256,
        configuration_sha256=sha256_hex(FROZEN_EXACT_TARGETS),
        selection_seed=selection_secret,
        split_salt=split_secret,
    )
    status = write_public_json_once(Path(arguments.output), precommit)
    print(
        json.dumps(
            {
                "status": "PRECOMMITTED" if status == "WRITTEN" else "ALREADY_PRECOMMITTED",
                "freeze_id": precommit["freeze_id"],
                "precommit_sha256": sha256_hex(precommit),
                "output": str(Path(arguments.output).resolve()),
            },
            indent=2,
        )
    )
    return 0


def command_custody_dry_run(arguments: argparse.Namespace) -> int:
    print(json.dumps(synthetic_dry_run(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def configure_mvx_parser(subparsers: argparse._SubParsersAction) -> None:
    mvx_parser = subparsers.add_parser("mvx", help="MVX experimental validation tools")
    mvx_commands = mvx_parser.add_subparsers(dest="mvx_command", required=True)

    protocol_parser = mvx_commands.add_parser("protocol", help="verify or seal the P0 protocol")
    protocol_commands = protocol_parser.add_subparsers(dest="protocol_command", required=True)
    verify_parser = protocol_commands.add_parser("verify", help="verify the frozen P0 seal")
    verify_parser.set_defaults(function=command_protocol_verify)
    seal_parser = protocol_commands.add_parser("seal", help="create the P0 seal and G0 verdict")
    seal_parser.set_defaults(function=command_protocol_seal)

    cohort_parser = mvx_commands.add_parser("cohort", help="freeze the G1 cohort under custody")
    cohort_commands = cohort_parser.add_subparsers(dest="cohort_command", required=True)
    freeze_parser = cohort_commands.add_parser(
        "freeze", help="select, split and commit the complete eligible P2a census"
    )
    freeze_parser.add_argument("input", help="complete eligible P2a JSONL census")
    freeze_parser.add_argument("--snapshot-sha256", required=True)
    freeze_parser.add_argument("--eligible-records-sha256", required=True)
    freeze_parser.add_argument("--precommit", required=True)
    freeze_parser.add_argument("--publication-receipt", required=True)
    freeze_parser.add_argument("--selection-secret-fd", required=True, type=int)
    freeze_parser.add_argument("--split-secret-fd", required=True, type=int)
    freeze_parser.add_argument("--private-dir", required=True)
    freeze_parser.add_argument("--release-dir", required=True)
    freeze_parser.set_defaults(function=command_cohort_freeze)

    custody_parser = mvx_commands.add_parser(
        "custody", help="exercise the process-locked holdout boundary"
    )
    custody_commands = custody_parser.add_subparsers(dest="custody_command", required=True)
    precommit_parser = custody_commands.add_parser(
        "precommit", help="publish seed/salt commitments before any G1 selection"
    )
    precommit_parser.add_argument("--snapshot-sha256", required=True)
    precommit_parser.add_argument("--eligible-records-sha256", required=True)
    precommit_parser.add_argument("--selection-secret-fd", required=True, type=int)
    precommit_parser.add_argument("--split-secret-fd", required=True, type=int)
    precommit_parser.add_argument("--output", required=True)
    precommit_parser.set_defaults(function=command_custody_precommit)
    dry_run_parser = custody_commands.add_parser(
        "dry-run", help="emit a redacted deterministic synthetic release"
    )
    dry_run_parser.set_defaults(function=command_custody_dry_run)
