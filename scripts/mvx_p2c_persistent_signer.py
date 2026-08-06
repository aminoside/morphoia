#!/usr/bin/env python3
"""Owner-controlled persistent Ed25519 signer for P2c continuity.

This signer is deliberately narrow.  It can prove continuity of one owner-held
key across restarts and can produce signatures compatible with the P2c anchor
contracts.  It is not an independent witness, a WORM publisher, an encryption
facility, or a solid-validity authority.  The P2c runner remains the authority
for anchor and readback message encodings.  Drive metadata and download flags
are caller-recorded API observations: signing them does not cryptographically
prove Drive origin, immutability, or an independent administrative domain.

Private-key material and private-key-derived copy hashes are written only to
explicit owner-private files.  The CLI never prints them, their paths, or
signatures to stdout or stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

SCHEMA_VERSION = "0.1.0"
MANIFEST_SCHEMA = "MVX-P2C-OWNER-PERSISTENT-SIGNER-MANIFEST"
STORAGE_RECEIPT_SCHEMA = "MVX-P2C-OWNER-PERSISTENT-SIGNER-STORAGE-RECEIPT"
OWNER_COPY_SCHEMA = "MVX-P2C-OWNER-ONLY-DRIVE-READBACK"
TRUST_MODEL = "OWNER_CONTROLLED_PERSISTENT_CONTINUITY_ONLY"
PURPOSE = "P2C_RESTART_CONTINUITY_ONLY_NEVER_SOLID_VALIDITY"
MANIFEST_DOMAIN = "MVX-P2C-OWNER-PERSISTENT-SIGNER-MANIFEST-ED25519-1"
STORAGE_DOMAIN = "MVX-P2C-OWNER-PERSISTENT-SIGNER-STORAGE-ED25519-1"
SIGNATURE_ALGORITHM = "ED25519"
MAX_JSON_BYTES = 16 * 1024 * 1024

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = REPOSITORY_ROOT / "tmp"
P2C_SCRIPT = REPOSITORY_ROOT / "scripts" / "mvx_p2c_exact_intersections.py"

HEX_32 = re.compile(r"^[0-9a-f]{64}$")
HEX_64 = re.compile(r"^[0-9a-f]{128}$")
EXTERNAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,511}$")
ASSURANCES = {
    "continuity_only": True,
    "drive_origin_proof": False,
    "encryption": False,
    "independent": False,
    "owner_controlled": True,
    "worm": False,
}


class SignerError(RuntimeError):
    """Fail-closed error carrying only a non-sensitive stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SignerError("NON_CANONICAL_JSON_VALUE") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pairs_no_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SignerError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _resolved_without_leaf(path: Path) -> Path:
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise SignerError("OUTPUT_PARENT_UNAVAILABLE") from error
    return parent / path.name


def _require_private_location(path: Path) -> None:
    resolved = _resolved_without_leaf(path)
    repository = REPOSITORY_ROOT.resolve(strict=True)
    private = PRIVATE_ROOT.resolve(strict=True)
    if _inside(resolved, repository) and not _inside(resolved, private):
        raise SignerError("PRIVATE_OUTPUT_INSIDE_TRACKED_TREE")


def _prepare_parent(path: Path, *, private: bool) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700 if private else 0o755)
        metadata = path.parent.lstat()
    except OSError as error:
        raise SignerError("OUTPUT_PARENT_UNAVAILABLE") from error
    if not stat.S_ISDIR(metadata.st_mode) or path.parent.is_symlink():
        raise SignerError("OUTPUT_PARENT_NOT_REAL_DIRECTORY")
    if metadata.st_uid != os.getuid():
        raise SignerError("OUTPUT_PARENT_NOT_OWNER_CONTROLLED")
    if private and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise SignerError("PRIVATE_OUTPUT_PARENT_PERMISSIONS")
    if private:
        _require_private_location(path)


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError as error:
        raise SignerError("OUTPUT_DIRECTORY_FSYNC_FAILED") from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise SignerError("OUTPUT_DIRECTORY_FSYNC_FAILED") from error
    finally:
        os.close(descriptor)


def _existing_exact(path: Path, payload: bytes, mode: int) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise SignerError("OUTPUT_INSPECTION_FAILED") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise SignerError("OUTPUT_CONFLICT")
    try:
        existing = path.read_bytes()
    except OSError as error:
        raise SignerError("OUTPUT_INSPECTION_FAILED") from error
    if not hmac.compare_digest(existing, payload):
        raise SignerError("OUTPUT_CONFLICT")
    return True


def _publish_once(path: Path, payload: bytes, *, mode: int, private: bool) -> None:
    _prepare_parent(path, private=private)
    if _existing_exact(path, payload, mode):
        return
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, mode)
    except FileExistsError as error:
        if _existing_exact(path, payload, mode):
            return
        raise SignerError("OUTPUT_CONFLICT") from error
    except OSError as error:
        raise SignerError("OUTPUT_PUBLICATION_FAILED") from error
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise SignerError("OUTPUT_PUBLICATION_FAILED") from error
    _fsync_directory(path.parent)


def _publish_new_private_key(path: Path, payload: bytes) -> None:
    if len(payload) != 32:
        raise SignerError("PRIVATE_KEY_LENGTH")
    _prepare_parent(path, private=True)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError as error:
        raise SignerError("PRIVATE_KEY_ALREADY_EXISTS") from error
    except OSError as error:
        raise SignerError("PRIVATE_KEY_PUBLICATION_FAILED") from error
    try:
        os.fchmod(descriptor, 0o400)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise SignerError("PRIVATE_KEY_PUBLICATION_FAILED") from error
    _fsync_directory(path.parent)


def _safe_bytes(
    path: Path,
    *,
    limit: int,
    allowed_modes: set[int] | None = None,
) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise SignerError("INPUT_UNAVAILABLE") from error
    if not stat.S_ISREG(before.st_mode) or path.is_symlink():
        raise SignerError("INPUT_NOT_REGULAR")
    if before.st_uid != os.getuid():
        raise SignerError("INPUT_NOT_OWNER_CONTROLLED")
    if allowed_modes is not None and stat.S_IMODE(before.st_mode) not in allowed_modes:
        raise SignerError("PRIVATE_INPUT_PERMISSIONS")
    if before.st_size > limit:
        raise SignerError("INPUT_SIZE_LIMIT")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SignerError("INPUT_SAFE_OPEN_FAILED") from error
    try:
        with os.fdopen(descriptor, "rb") as stream:
            payload = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
    except OSError as error:
        raise SignerError("INPUT_READ_FAILED") from error
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != before.st_size:
        raise SignerError("INPUT_CHANGED_DURING_READ")
    return payload


def _json_document(path: Path, *, private: bool = False) -> tuple[bytes, dict[str, Any]]:
    modes = {0o400, 0o600} if private else None
    payload = _safe_bytes(path, limit=MAX_JSON_BYTES, allowed_modes=modes)
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(SignerError("NONFINITE_JSON")),
        )
    except SignerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SignerError("INVALID_JSON") from error
    if not isinstance(value, dict):
        raise SignerError("JSON_ROOT_NOT_OBJECT")
    if payload != _canonical_bytes(value):
        raise SignerError("JSON_NOT_CANONICAL")
    return payload, value


def _p2c_json_document(
    p2c: ModuleType,
    path: Path,
    *,
    private: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    """Read a document using the runner's newline-terminated canonical encoding."""

    modes = {0o400, 0o600} if private else None
    payload = _safe_bytes(path, limit=MAX_JSON_BYTES, allowed_modes=modes)
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(SignerError("NONFINITE_JSON")),
        )
    except SignerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SignerError("INVALID_JSON") from error
    if not isinstance(value, dict):
        raise SignerError("JSON_ROOT_NOT_OBJECT")
    if payload != p2c._canonical_bytes(value):
        raise SignerError("P2C_JSON_NOT_CANONICAL")
    return payload, value


def _private_key(path: Path) -> tuple[bytes, Ed25519PrivateKey]:
    _require_private_location(path)
    raw = _safe_bytes(path, limit=32, allowed_modes={0o400})
    if len(raw) != 32:
        raise SignerError("PRIVATE_KEY_LENGTH")
    try:
        return raw, Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError as error:
        raise SignerError("PRIVATE_KEY_INVALID") from error


def _public_hex(private_key: Ed25519PrivateKey) -> str:
    return (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        .hex()
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _valid_utc(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _manifest_message(core: Mapping[str, Any]) -> bytes:
    return _canonical_bytes({"manifest": dict(core), "signature_domain": MANIFEST_DOMAIN})


def _storage_message(core: Mapping[str, Any]) -> bytes:
    return _canonical_bytes({"receipt": dict(core), "signature_domain": STORAGE_DOMAIN})


def initialize_signer(
    key_path: Path,
    manifest_path: Path,
    *,
    challenge: bytes | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create one write-once raw private key and its public proof-of-possession manifest."""

    if (
        key_path.exists()
        or key_path.is_symlink()
        or manifest_path.exists()
        or manifest_path.is_symlink()
    ):
        raise SignerError("PRIVATE_KEY_ALREADY_EXISTS")
    _prepare_parent(key_path, private=True)
    _prepare_parent(manifest_path, private=False)
    if _resolved_without_leaf(key_path) == _resolved_without_leaf(manifest_path):
        raise SignerError("KEY_AND_MANIFEST_PATH_CONFLICT")
    selected_challenge = challenge if challenge is not None else os.urandom(32)
    if not isinstance(selected_challenge, bytes) or len(selected_challenge) != 32:
        raise SignerError("CHALLENGE_LENGTH")
    selected_time = created_at or _utc_now()
    if not _valid_utc(selected_time):
        raise SignerError("MANIFEST_TIME_INVALID")
    private_key = Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_key_hex = _public_hex(private_key)
    core = {
        "assurances": dict(ASSURANCES),
        "challenge_hex": selected_challenge.hex(),
        "created_at": selected_time,
        "public_key_ed25519_hex": public_key_hex,
        "purpose": PURPOSE,
        "schema": MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "signer_id": f"mvx-p2c-owner-{public_key_hex[:16]}",
        "trust_model": TRUST_MODEL,
    }
    manifest = {
        **core,
        "challenge_signature_hex": private_key.sign(_manifest_message(core)).hex(),
    }
    verify_manifest(manifest)
    _publish_new_private_key(key_path, raw)
    # The raw key remains owner-only and write-once if manifest publication
    # fails.  It is never silently deleted because recovery may still be needed.
    _publish_once(
        manifest_path,
        _canonical_bytes(manifest),
        mode=0o644,
        private=False,
    )
    return manifest


def verify_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "assurances",
        "challenge_hex",
        "challenge_signature_hex",
        "created_at",
        "public_key_ed25519_hex",
        "purpose",
        "schema",
        "schema_version",
        "signature_algorithm",
        "signer_id",
        "trust_model",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != expected:
        raise SignerError("MANIFEST_FIELDS")
    public_key_hex = manifest["public_key_ed25519_hex"]
    challenge_hex = manifest["challenge_hex"]
    signature_hex = manifest["challenge_signature_hex"]
    if (
        manifest["schema"] != MANIFEST_SCHEMA
        or manifest["schema_version"] != SCHEMA_VERSION
        or manifest["signature_algorithm"] != SIGNATURE_ALGORITHM
        or manifest["trust_model"] != TRUST_MODEL
        or manifest["purpose"] != PURPOSE
        or manifest["assurances"] != ASSURANCES
        or not _valid_utc(manifest["created_at"])
        or not isinstance(public_key_hex, str)
        or HEX_32.fullmatch(public_key_hex) is None
        or not isinstance(challenge_hex, str)
        or HEX_32.fullmatch(challenge_hex) is None
        or not isinstance(signature_hex, str)
        or HEX_64.fullmatch(signature_hex) is None
        or manifest["signer_id"] != f"mvx-p2c-owner-{public_key_hex[:16]}"
    ):
        raise SignerError("MANIFEST_CONTRACT")
    core = {name: value for name, value in manifest.items() if name != "challenge_signature_hex"}
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(signature_hex), _manifest_message(core))
    except (InvalidSignature, ValueError) as error:
        raise SignerError("MANIFEST_SIGNATURE") from error
    return dict(manifest)


def _load_manifest(path: Path) -> tuple[bytes, dict[str, Any]]:
    payload, manifest = _json_document(path)
    return payload, verify_manifest(manifest)


def _verify_key_matches_manifest(
    key_path: Path, manifest: Mapping[str, Any]
) -> tuple[bytes, Ed25519PrivateKey]:
    raw, private_key = _private_key(key_path)
    if not hmac.compare_digest(_public_hex(private_key), manifest["public_key_ed25519_hex"]):
        raise SignerError("PRIVATE_KEY_MANIFEST_MISMATCH")
    return raw, private_key


def _load_p2c() -> ModuleType:
    try:
        metadata = P2C_SCRIPT.lstat()
    except OSError as error:
        raise SignerError("P2C_RUNNER_UNAVAILABLE") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or P2C_SCRIPT.is_symlink()
        or metadata.st_uid != os.getuid()
    ):
        raise SignerError("P2C_RUNNER_UNSAFE")
    module_name = "morphoia_mvx_p2c_persistent_signer_runner"
    specification = importlib.util.spec_from_file_location(module_name, P2C_SCRIPT)
    if specification is None or specification.loader is None:
        raise SignerError("P2C_RUNNER_IMPORT")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        raise SignerError("P2C_RUNNER_IMPORT") from error
    return module


def _validated_plan(
    p2c: ModuleType,
    plan_path: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    _, plan = _p2c_json_document(p2c, plan_path, private=True)
    work_id = plan.get("work_id")
    if not isinstance(work_id, str) or HEX_32.fullmatch(work_id) is None:
        raise SignerError("PLAN_WORK_ID")
    try:
        validated = p2c._validate_persisted_plan(plan, work_id)
    except Exception as error:
        raise SignerError("PLAN_CONTRACT") from error
    if (
        validated.get("authority_policy") != p2c.REQUIRE_EXTERNAL_ANCHOR
        or validated.get("external_anchor_public_key_hex") != manifest["public_key_ed25519_hex"]
    ):
        raise SignerError("PLAN_SIGNER_MISMATCH")
    return validated


def _validate_unsigned_anchor(
    p2c: ModuleType,
    value: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != p2c.EXTERNAL_ANCHOR_UNSIGNED_FIELDS:
        raise SignerError("ANCHOR_FIELDS")
    if (
        value.get("schema") != "MVX-P2C-EXTERNAL-COMPLETION-ANCHOR"
        or value.get("schema_version") != "0.1.0"
        or value.get("trust_model") != p2c.EXTERNAL_ANCHOR_TRUST_MODEL
        or value.get("anchor_persistence_policy")
        != (
            "EXTERNAL_SIGNER_MUST_UPLOAD_SIGNED_BYTES_TO_PREALLOCATED_LOCATOR_AND_VERIFY_"
            "READBACK_BEFORE_REUSE"
        )
    ):
        raise SignerError("ANCHOR_CONTRACT")
    try:
        p2c._validate_drive_receipt(value["drive_receipt"])
    except Exception as error:
        raise SignerError("ANCHOR_DRIVE_RECEIPT") from error
    expected = {
        "code_sha256": plan["code_sha256"],
        "input_binding_sha256": p2c._sha256_value(plan["input_binding"]),
        "plan_sha256": p2c._sha256_value(plan),
        "runtime_sha256": p2c._sha256_value(plan["environment"]),
        "source_sha256": plan["source_sha256"],
        "source_size_bytes": plan["source_size_bytes"],
        "work_id": plan["work_id"],
    }
    if any(value.get(name) != expected_value for name, expected_value in expected.items()):
        raise SignerError("ANCHOR_PLAN_BINDING")
    if value.get("external_checkpoint_id") != value["drive_receipt"].get(
        "checkpoint_id"
    ) or value.get("external_checkpoint_sha256") != value["drive_receipt"].get(
        "checkpoint", {}
    ).get("sha256"):
        raise SignerError("ANCHOR_CHECKPOINT_BINDING")
    try:
        for name in ("completed_id", "result_id", "terminal_id"):
            p2c._external_identifier(value[name], f"persistent signer {name}")
        for name in (
            "external_anchor_id",
            "external_anchor_parent_id",
            "external_checkpoint_id",
        ):
            p2c._external_identifier(value[name], f"persistent signer {name}")
    except Exception as error:
        raise SignerError("ANCHOR_IDENTIFIER") from error
    return dict(value)


def sign_anchor(
    key_path: Path,
    manifest_path: Path,
    plan_path: Path,
    unsigned_anchor_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    _, manifest = _load_manifest(manifest_path)
    _, private_key = _verify_key_matches_manifest(key_path, manifest)
    p2c = _load_p2c()
    plan = _validated_plan(p2c, plan_path, manifest)
    _, unsigned = _p2c_json_document(p2c, unsigned_anchor_path, private=True)
    validated = _validate_unsigned_anchor(p2c, unsigned, plan)
    signed = {
        **validated,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "signature_hex": private_key.sign(p2c._external_anchor_message(validated)).hex(),
    }
    verify_signed_anchor_document(p2c, signed, plan, manifest)
    _publish_once(output_path, p2c._canonical_bytes(signed), mode=0o600, private=True)
    return signed


def verify_signed_anchor_document(
    p2c: ModuleType,
    anchor: Mapping[str, Any],
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(anchor, Mapping) or set(anchor) != p2c.EXTERNAL_ANCHOR_FIELDS:
        raise SignerError("SIGNED_ANCHOR_FIELDS")
    unsigned = {
        name: value
        for name, value in anchor.items()
        if name not in {"signature_algorithm", "signature_hex"}
    }
    validated = _validate_unsigned_anchor(p2c, unsigned, plan)
    signature_hex = anchor.get("signature_hex")
    if (
        anchor.get("signature_algorithm") != SIGNATURE_ALGORITHM
        or not isinstance(signature_hex, str)
        or HEX_64.fullmatch(signature_hex) is None
    ):
        raise SignerError("SIGNED_ANCHOR_SIGNATURE_FIELDS")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(manifest["public_key_ed25519_hex"])
        )
        public_key.verify(
            bytes.fromhex(signature_hex),
            p2c._external_anchor_message(validated),
        )
    except (InvalidSignature, ValueError) as error:
        raise SignerError("SIGNED_ANCHOR_SIGNATURE") from error
    return dict(anchor)


def sign_readback(
    key_path: Path,
    manifest_path: Path,
    plan_path: Path,
    anchor_readback_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    _, manifest = _load_manifest(manifest_path)
    _, private_key = _verify_key_matches_manifest(key_path, manifest)
    p2c = _load_p2c()
    plan = _validated_plan(p2c, plan_path, manifest)
    anchor_bytes, anchor = _p2c_json_document(
        p2c,
        anchor_readback_path,
        private=True,
    )
    verify_signed_anchor_document(p2c, anchor, plan, manifest)
    try:
        unsigned = p2c.build_anchor_readback_payload(anchor_readback_path)
    except Exception as error:
        raise SignerError("READBACK_PAYLOAD") from error
    if unsigned.get("anchor_sha256") != _sha256(anchor_bytes):
        raise SignerError("READBACK_BYTES_BINDING")
    receipt = {
        **unsigned,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "signature_hex": private_key.sign(p2c._anchor_readback_message(unsigned)).hex(),
    }
    try:
        p2c._validate_anchor_readback_receipt(receipt, anchor_bytes, anchor, plan)
    except Exception as error:
        raise SignerError("READBACK_RECEIPT_CONTRACT") from error
    _publish_once(output_path, p2c._canonical_bytes(receipt), mode=0o600, private=True)
    return receipt


def _owner_copy(
    copy_path: Path,
    metadata_path: Path,
    *,
    slot: str,
) -> tuple[bytes, dict[str, Any]]:
    payload = _safe_bytes(copy_path, limit=32, allowed_modes={0o400, 0o600})
    if len(payload) != 32:
        raise SignerError("STORAGE_COPY_LENGTH")
    _, metadata = _json_document(metadata_path, private=True)
    expected_fields = {
        "download_verified",
        "drive_file_id",
        "drive_parent_id",
        "owner_only",
        "permission_roles",
        "revision_id",
        "schema",
        "schema_version",
        "sha256",
        "shared",
        "size_bytes",
    }
    if not isinstance(metadata, Mapping) or set(metadata) != expected_fields:
        raise SignerError("STORAGE_METADATA_FIELDS")
    if (
        metadata["schema"] != OWNER_COPY_SCHEMA
        or metadata["schema_version"] != SCHEMA_VERSION
        or metadata["download_verified"] is not True
        or metadata["owner_only"] is not True
        or metadata["shared"] is not False
        or metadata["permission_roles"] != ["owner"]
        or metadata["size_bytes"] != len(payload)
        or metadata["sha256"] != _sha256(payload)
    ):
        raise SignerError("STORAGE_METADATA_CONTRACT")
    for name in ("drive_file_id", "drive_parent_id", "revision_id"):
        value = metadata[name]
        if not isinstance(value, str) or EXTERNAL_ID.fullmatch(value) is None:
            raise SignerError("STORAGE_METADATA_IDENTIFIER")
    row = {
        "download_verified": True,
        "drive_file_id": metadata["drive_file_id"],
        "drive_parent_id": metadata["drive_parent_id"],
        "owner_only": True,
        "permission_roles": ["owner"],
        "revision_id": metadata["revision_id"],
        "sha256": metadata["sha256"],
        "shared": False,
        "size_bytes": metadata["size_bytes"],
        "slot": slot,
    }
    return payload, row


def _storage_receipt_core(
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    copy_a: tuple[bytes, dict[str, Any]],
    copy_b: tuple[bytes, dict[str, Any]],
) -> dict[str, Any]:
    a_bytes, a_row = copy_a
    b_bytes, b_row = copy_b
    if (
        not hmac.compare_digest(a_bytes, b_bytes)
        or a_row["drive_file_id"] == b_row["drive_file_id"]
        or a_row["drive_parent_id"] == b_row["drive_parent_id"]
    ):
        raise SignerError("STORAGE_COPIES_NOT_DISTINCT_IDENTICAL_READBACKS")
    for raw in (a_bytes, b_bytes):
        try:
            candidate = Ed25519PrivateKey.from_private_bytes(raw)
        except ValueError as error:
            raise SignerError("STORAGE_COPY_PRIVATE_KEY_INVALID") from error
        if _public_hex(candidate) != manifest["public_key_ed25519_hex"]:
            raise SignerError("STORAGE_COPY_MANIFEST_MISMATCH")
    return {
        "assurances": dict(ASSURANCES),
        "copies": [a_row, b_row],
        "copies_byte_identical": True,
        "drive_observation_scope": ("CALLER_API_OBSERVED_NOT_CRYPTOGRAPHIC_DRIVE_ORIGIN_PROOF"),
        "manifest_sha256": _sha256(manifest_bytes),
        "private_key_matches_manifest": True,
        "public_key_ed25519_hex": manifest["public_key_ed25519_hex"],
        "purpose": PURPOSE,
        "schema": STORAGE_RECEIPT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "trust_model": TRUST_MODEL,
    }


def create_storage_receipt(
    key_path: Path,
    manifest_path: Path,
    copy_a_path: Path,
    copy_a_metadata_path: Path,
    copy_b_path: Path,
    copy_b_metadata_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    manifest_bytes, manifest = _load_manifest(manifest_path)
    raw, private_key = _verify_key_matches_manifest(key_path, manifest)
    copy_a = _owner_copy(copy_a_path, copy_a_metadata_path, slot="A")
    copy_b = _owner_copy(copy_b_path, copy_b_metadata_path, slot="B")
    if not hmac.compare_digest(raw, copy_a[0]) or not hmac.compare_digest(raw, copy_b[0]):
        raise SignerError("STORAGE_COPY_CANONICAL_KEY_MISMATCH")
    core = _storage_receipt_core(manifest_bytes, manifest, copy_a, copy_b)
    receipt = {
        **core,
        "signature_hex": private_key.sign(_storage_message(core)).hex(),
    }
    verify_storage_receipt_document(receipt, manifest_bytes, manifest, copy_a, copy_b)
    _publish_once(output_path, _canonical_bytes(receipt), mode=0o600, private=True)
    return receipt


def verify_storage_receipt_document(
    receipt: Mapping[str, Any],
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    copy_a: tuple[bytes, dict[str, Any]],
    copy_b: tuple[bytes, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or set(receipt) != {
        "assurances",
        "copies",
        "copies_byte_identical",
        "drive_observation_scope",
        "manifest_sha256",
        "private_key_matches_manifest",
        "public_key_ed25519_hex",
        "purpose",
        "schema",
        "schema_version",
        "signature_algorithm",
        "signature_hex",
        "trust_model",
    }:
        raise SignerError("STORAGE_RECEIPT_FIELDS")
    core = {name: value for name, value in receipt.items() if name != "signature_hex"}
    expected = _storage_receipt_core(manifest_bytes, manifest, copy_a, copy_b)
    if core != expected:
        raise SignerError("STORAGE_RECEIPT_BINDING")
    signature_hex = receipt["signature_hex"]
    if not isinstance(signature_hex, str) or HEX_64.fullmatch(signature_hex) is None:
        raise SignerError("STORAGE_RECEIPT_SIGNATURE_FIELDS")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(manifest["public_key_ed25519_hex"])
        )
        public_key.verify(bytes.fromhex(signature_hex), _storage_message(core))
    except (InvalidSignature, ValueError) as error:
        raise SignerError("STORAGE_RECEIPT_SIGNATURE") from error
    return dict(receipt)


def verify_storage_receipt(
    manifest_path: Path,
    receipt_path: Path,
    copy_a_path: Path,
    copy_a_metadata_path: Path,
    copy_b_path: Path,
    copy_b_metadata_path: Path,
) -> dict[str, Any]:
    manifest_bytes, manifest = _load_manifest(manifest_path)
    _, receipt = _json_document(receipt_path, private=True)
    copy_a = _owner_copy(copy_a_path, copy_a_metadata_path, slot="A")
    copy_b = _owner_copy(copy_b_path, copy_b_metadata_path, slot="B")
    return verify_storage_receipt_document(
        receipt,
        manifest_bytes,
        manifest,
        copy_a,
        copy_b,
    )


def verify_anchor_files(
    manifest_path: Path,
    plan_path: Path,
    anchor_path: Path,
    readback_path: Path | None = None,
) -> None:
    _, manifest = _load_manifest(manifest_path)
    p2c = _load_p2c()
    plan = _validated_plan(p2c, plan_path, manifest)
    anchor_bytes, anchor = _p2c_json_document(p2c, anchor_path, private=True)
    verify_signed_anchor_document(p2c, anchor, plan, manifest)
    if readback_path is not None:
        _, readback = _p2c_json_document(p2c, readback_path, private=True)
        try:
            p2c._validate_anchor_readback_receipt(readback, anchor_bytes, anchor, plan)
        except Exception as error:
            raise SignerError("READBACK_RECEIPT_CONTRACT") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a persistent raw key and public manifest")
    init.add_argument("--key", required=True, type=Path)
    init.add_argument("--manifest", required=True, type=Path)
    init.add_argument(
        "--challenge-hex",
        help="verifier-defined 32-byte pre-execution challenge in lowercase hex",
    )
    init.add_argument(
        "--created-at",
        help="explicit UTC creation time ending in Z",
    )

    verify = commands.add_parser("verify", help="verify public, anchor or storage evidence")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--key", type=Path)
    verify.add_argument("--plan", type=Path)
    verify.add_argument("--anchor", type=Path)
    verify.add_argument("--readback", type=Path)
    verify.add_argument("--storage-receipt", type=Path)
    verify.add_argument("--copy-a", type=Path)
    verify.add_argument("--copy-a-metadata", type=Path)
    verify.add_argument("--copy-b", type=Path)
    verify.add_argument("--copy-b-metadata", type=Path)

    anchor = commands.add_parser("sign-anchor", help="sign one runner-built anchor payload")
    anchor.add_argument("--key", required=True, type=Path)
    anchor.add_argument("--manifest", required=True, type=Path)
    anchor.add_argument("--plan", required=True, type=Path)
    anchor.add_argument("--unsigned-anchor", required=True, type=Path)
    anchor.add_argument("--output", required=True, type=Path)

    readback = commands.add_parser(
        "sign-readback",
        help="sign the exact bytes of a downloaded signed anchor",
    )
    readback.add_argument("--key", required=True, type=Path)
    readback.add_argument("--manifest", required=True, type=Path)
    readback.add_argument("--plan", required=True, type=Path)
    readback.add_argument("--anchor-readback", required=True, type=Path)
    readback.add_argument("--output", required=True, type=Path)

    storage = commands.add_parser(
        "storage-receipt",
        help="sign two exact owner-only Drive key-copy readbacks",
    )
    storage.add_argument("--key", required=True, type=Path)
    storage.add_argument("--manifest", required=True, type=Path)
    storage.add_argument("--copy-a", required=True, type=Path)
    storage.add_argument("--copy-a-metadata", required=True, type=Path)
    storage.add_argument("--copy-b", required=True, type=Path)
    storage.add_argument("--copy-b-metadata", required=True, type=Path)
    storage.add_argument("--output", required=True, type=Path)
    return parser


def _emit(action: str, *, code: str | None = None) -> None:
    payload = {"action": action}
    if code is not None:
        payload["code"] = code
    sys.stdout.write(_canonical_bytes(payload).decode("utf-8"))


def _verify_command(arguments: argparse.Namespace) -> None:
    manifest_bytes, manifest = _load_manifest(arguments.manifest)
    if arguments.key is not None:
        _verify_key_matches_manifest(arguments.key, manifest)
    if arguments.readback is not None and arguments.anchor is None:
        raise SignerError("VERIFY_READBACK_REQUIRES_ANCHOR")
    if arguments.anchor is not None:
        if arguments.plan is None:
            raise SignerError("VERIFY_ANCHOR_REQUIRES_PLAN")
        verify_anchor_files(
            arguments.manifest,
            arguments.plan,
            arguments.anchor,
            arguments.readback,
        )
    storage_arguments = (
        arguments.storage_receipt,
        arguments.copy_a,
        arguments.copy_a_metadata,
        arguments.copy_b,
        arguments.copy_b_metadata,
    )
    if any(value is not None for value in storage_arguments):
        if any(value is None for value in storage_arguments):
            raise SignerError("VERIFY_STORAGE_ARGUMENTS_INCOMPLETE")
        _, receipt = _json_document(arguments.storage_receipt, private=True)
        copy_a = _owner_copy(arguments.copy_a, arguments.copy_a_metadata, slot="A")
        copy_b = _owner_copy(arguments.copy_b, arguments.copy_b_metadata, slot="B")
        verify_storage_receipt_document(
            receipt,
            manifest_bytes,
            manifest,
            copy_a,
            copy_b,
        )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        if arguments.command == "init":
            try:
                challenge = (
                    bytes.fromhex(arguments.challenge_hex)
                    if arguments.challenge_hex is not None
                    and HEX_32.fullmatch(arguments.challenge_hex) is not None
                    else None
                )
            except ValueError as error:  # pragma: no cover - guarded by the regex
                raise SignerError("CHALLENGE_HEX_INVALID") from error
            if arguments.challenge_hex is not None and challenge is None:
                raise SignerError("CHALLENGE_HEX_INVALID")
            initialize_signer(
                arguments.key,
                arguments.manifest,
                challenge=challenge,
                created_at=arguments.created_at,
            )
            _emit("INITIALIZED")
        elif arguments.command == "verify":
            _verify_command(arguments)
            _emit("VERIFIED")
        elif arguments.command == "sign-anchor":
            sign_anchor(
                arguments.key,
                arguments.manifest,
                arguments.plan,
                arguments.unsigned_anchor,
                arguments.output,
            )
            _emit("ANCHOR_SIGNED")
        elif arguments.command == "sign-readback":
            sign_readback(
                arguments.key,
                arguments.manifest,
                arguments.plan,
                arguments.anchor_readback,
                arguments.output,
            )
            _emit("READBACK_SIGNED")
        elif arguments.command == "storage-receipt":
            create_storage_receipt(
                arguments.key,
                arguments.manifest,
                arguments.copy_a,
                arguments.copy_a_metadata,
                arguments.copy_b,
                arguments.copy_b_metadata,
                arguments.output,
            )
            _emit("STORAGE_RECEIPT_SIGNED")
        else:  # pragma: no cover - argparse closes the command set.
            raise SignerError("UNKNOWN_COMMAND")
    except SignerError as error:
        _emit("ERROR", code=error.code)
        return 2
    except Exception:  # noqa: BLE001 - a traceback could disclose private paths or values
        # Never let an unexpected traceback disclose a private path or value.
        _emit("ERROR", code="INTERNAL_ERROR")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
