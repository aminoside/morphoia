"""Process-lock custody helpers for an MVX blind split.

This module deliberately provides commitments and redacted views, not encryption
and not independent human custody.  The complete private manifest and its secret
must remain in access-controlled storage outside development jobs.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import stat
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

PUBLIC_SCHEMA = "MVX-CUSTODY-PUBLIC"
VISIBLE_SCHEMA = "MVX-CUSTODY-VISIBLE"
SCHEMA_VERSION = "1.0.0"
ALGORITHM_ID = "MVX-CUSTODY-HMAC-SHA256-1"
PRECOMMIT_ALGORITHM_ID = "MVX-G1-PRECOMMIT-SHA256-1"
PRECOMMIT_SCHEMA_VERSION = "0.1.0"
PUBLICATION_RECEIPT_ALGORITHM_ID = "MVX-G1-PRECOMMIT-ED25519-RECEIPT-2"
PUBLICATION_RECEIPT_SCHEMA_VERSION = "0.2.0"
TRUSTED_PUBLISHERS_SCHEMA_VERSION = "0.2.0"
TRUSTED_PUBLISHERS_RELATIVE_PATH = "docs/mvx/validation/p0/trusted-publishers.json"
G1_BLOCKED_STATE = "BLOCKED_UNTIL_EXTERNAL_WORM_PUBLISHER_KEY_IS_VERSIONED"
G1_READY_STATE = "READY_FOR_PRODUCTION_G1"
SYNTHETIC_G0_SEAL_SHA256 = "0" * 64
MAX_RECEIPT_FUTURE_SKEW = timedelta(minutes=5)
SPLITS = ("development", "calibration", "blind", "reserve")
VISIBLE_SPLITS = frozenset(("development", "calibration"))
VISIBLE_ASSIGNMENT_FIELDS = frozenset(
    (
        "lineage_id",
        "leakage_group_id",
        "split",
        "selection_stratum",
        "blind_scope",
        "creator_group",
        "source_uid",
        "source_path",
        "source_sha256",
        "dataset",
        "category",
        "topology_status",
        "complexity_quantile",
    )
)
SENSITIVE_ASSIGNMENT_FIELDS = frozenset(
    (
        "lineage_id",
        "leakage_group_id",
        "creator_group",
        "source_uid",
        "source_path",
        "source_sha256",
    )
)

_HEX_DIGITS = frozenset("0123456789abcdef")
_JSON_PRIMITIVES = (str, int, float, bool, type(None))
_PRODUCTION_STORE_KINDS = frozenset(
    ("GITHUB_SIGNED_COMMIT", "OBJECT_LOCK_VERSION", "INDEPENDENT_WITNESS_LEDGER")
)
_FORBIDDEN_PUBLIC_SECRET_HEX = frozenset(
    (
        "713b129c8347d84b37685cca9ef0734e6599ca90691b852eacb561f4bef148f0",
        "5b627e7f79d5ba855bd52402bc7d8a487a970f52d659f5c7ff6f23997c98c10b",
    )
)
_SYNTHETIC_PUBLISHER_ID = "MVX-SYNTHETIC-PUBLISHER-ONLY"
_SYNTHETIC_PUBLISHER_PUBLIC_KEY_HEX = (
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)


@dataclass(frozen=True, slots=True)
class _ProductionTrustContext:
    """Verified local trust anchors for one production receipt decision."""

    registry: dict[str, Any]
    registry_sha256: str
    registry_epoch: int
    g0_seal_sha256: str
    g0_sealed_at: datetime


class CustodyValidationError(ValueError):
    """Raised when a private manifest cannot be safely released."""


def _validate_json_value(value: Any, *, location: str = "$") -> None:
    """Reject values that cannot be represented deterministically as JSON."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise CustodyValidationError(f"{location} contains a non-string object key")
            try:
                key.encode("utf-8")
            except UnicodeEncodeError as error:
                raise CustodyValidationError(
                    f"{location} contains an invalid Unicode object key"
                ) from error
            _validate_json_value(child, location=f"{location}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json_value(child, location=f"{location}[{index}]")
        return
    if not isinstance(value, _JSON_PRIMITIVES):
        raise CustodyValidationError(
            f"{location} contains unsupported JSON value {type(value).__name__}"
        )
    if isinstance(value, float):
        raise CustodyValidationError(
            f"{location} contains a floating-point number; custody manifests use the "
            "restricted integer-only JCS domain"
        )
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > (2**53 - 1):
        raise CustodyValidationError(f"{location} contains an integer outside I-JSON range")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise CustodyValidationError(f"{location} contains invalid Unicode") from error


def _jcs_prepare(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _jcs_prepare(value[key])
            for key in sorted(value, key=lambda item: item.encode("utf-16-be"))
        }
    if isinstance(value, (list, tuple)):
        return [_jcs_prepare(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON for hashing.

    MVX custody manifests deliberately admit only valid Unicode member names, I-JSON
    integers, strings, booleans, null, arrays and objects.  On that restricted
    no-float domain this encoding is RFC 8785 JCS-equivalent; accepting arbitrary
    binary64 values would require the full ECMAScript number serialiser and is
    therefore rejected fail-closed.
    """

    _validate_json_value(value)
    return json.dumps(
        _jcs_prepare(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")


def sha256_hex(value: bytes | bytearray | memoryview | Any) -> str:
    """Hash bytes directly, or hash any JSON-compatible value canonically."""

    if isinstance(value, (bytes, bytearray, memoryview)):
        payload = bytes(value)
    else:
        payload = canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _parse_utc_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CustodyValidationError(f"{field} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CustodyValidationError(f"{field} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CustodyValidationError(f"{field} must be UTC")
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    """Return the production verification clock (patched only by unit tests)."""

    return datetime.now(UTC)


def _read_regular_bytes(path: Path, *, field: str) -> bytes:
    """Read one trust-anchor file while refusing symbolic links and non-files."""

    try:
        metadata = path.lstat()
    except OSError as error:
        raise CustodyValidationError(f"cannot inspect {field} {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise CustodyValidationError(f"{field} is not a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CustodyValidationError(f"cannot safely open {field} {path}: {error}") from error
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise CustodyValidationError(f"{field} changed while being opened: {path}")
        payload = stream.read()
        after = os.fstat(stream.fileno())
    if (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) != (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    ):
        raise CustodyValidationError(f"{field} changed while being read: {path}")
    return payload


@lru_cache(maxsize=1)
def _normative_public_hex_values() -> frozenset[str]:
    """Return every literal 256-bit hex value in the verified normative tree."""

    try:
        from .protocol import NORMATIVE_PATHS, PROJECT_ROOT
    except ImportError:
        return _FORBIDDEN_PUBLIC_SECRET_HEX
    values = set(_FORBIDDEN_PUBLIC_SECRET_HEX)
    pattern = re.compile(rb"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
    for relative in NORMATIVE_PATHS:
        path = PROJECT_ROOT / relative
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        values.update(match.group().decode("ascii").lower() for match in pattern.finditer(payload))
    return frozenset(values)


def _secret_bytes(
    secret: bytes | bytearray | memoryview | str,
    *,
    allow_public_test_secret: bool = False,
) -> bytes:
    if isinstance(secret, str):
        if len(secret) != 64 or any(character not in _HEX_DIGITS for character in secret.lower()):
            raise CustodyValidationError("secret hex must encode exactly 256 bits")
        try:
            raw = bytes.fromhex(secret)
        except ValueError as error:  # Defensive: the character check above is explicit.
            raise CustodyValidationError("secret hex is invalid") from error
    elif isinstance(secret, (bytes, bytearray, memoryview)):
        raw = bytes(secret)
    else:
        raise CustodyValidationError("secret must be 32 bytes or a 64-character hex string")

    if len(raw) != 32:
        raise CustodyValidationError("secret must contain exactly 256 bits")
    if not allow_public_test_secret and raw.hex() in _normative_public_hex_values():
        raise CustodyValidationError(
            "secret is a public normative value and cannot be used in production"
        )

    # Length is necessary but cannot prove entropy.  Reject common deterministic
    # mistakes and low-diversity/passphrase material; generation still belongs to
    # a cryptographically secure external secret manager.
    periodic = any(raw == raw[:period] * (len(raw) // period) for period in (1, 2, 4, 8, 16))
    printable_ascii = all(0x20 <= byte <= 0x7E for byte in raw)
    if periodic or len(set(raw)) < 16 or printable_ascii:
        raise CustodyValidationError(
            "secret appears weak; use 32 random bytes from a cryptographically secure source"
        )
    return raw


def validate_secret_bytes(
    secret: bytes | bytearray | memoryview | str,
    *,
    allow_public_test_secret: bool = False,
) -> bytes:
    """Validate one production secret and return its exact 32-byte value."""

    return _secret_bytes(secret, allow_public_test_secret=allow_public_test_secret)


def _require_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_DIGITS for character in value)
    ):
        raise CustodyValidationError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _precommit_core(
    *,
    protocol_root_sha256: str,
    snapshot_sha256: str,
    eligible_records_sha256: str,
    configuration_sha256: str,
    selection_seed_sha256: str,
    split_salt_sha256: str,
) -> dict[str, str]:
    return {
        "schema_version": PRECOMMIT_SCHEMA_VERSION,
        "algorithm_id": PRECOMMIT_ALGORITHM_ID,
        "protocol_root_sha256": protocol_root_sha256,
        "snapshot_sha256": snapshot_sha256,
        "eligible_records_sha256": eligible_records_sha256,
        "configuration_sha256": configuration_sha256,
        "selection_seed_sha256": selection_seed_sha256,
        "split_salt_sha256": split_salt_sha256,
    }


def create_custody_precommit(
    *,
    protocol_root_sha256: str,
    snapshot_sha256: str,
    eligible_records_sha256: str,
    configuration_sha256: str,
    selection_seed: bytes | bytearray | memoryview | str,
    split_salt: bytes | bytearray | memoryview | str,
    allow_public_test_secrets: bool = False,
) -> dict[str, str]:
    """Create the public commitment that must be published before G1 selection.

    Only SHA-256 commitments are returned.  The preimages remain with the
    external custodian and are never written by this function.
    """

    protocol_root = _require_sha256(protocol_root_sha256, field="protocol_root_sha256")
    snapshot = _require_sha256(snapshot_sha256, field="snapshot_sha256")
    eligible = _require_sha256(eligible_records_sha256, field="eligible_records_sha256")
    configuration = _require_sha256(configuration_sha256, field="configuration_sha256")
    selection_raw = _secret_bytes(
        selection_seed, allow_public_test_secret=allow_public_test_secrets
    )
    split_raw = _secret_bytes(split_salt, allow_public_test_secret=allow_public_test_secrets)
    if hmac.compare_digest(selection_raw, split_raw):
        raise CustodyValidationError("selection seed and split salt must be independent")

    core = _precommit_core(
        protocol_root_sha256=protocol_root,
        snapshot_sha256=snapshot,
        eligible_records_sha256=eligible,
        configuration_sha256=configuration,
        selection_seed_sha256=hashlib.sha256(selection_raw).hexdigest(),
        split_salt_sha256=hashlib.sha256(split_raw).hexdigest(),
    )
    freeze_id = f"mvx-g1-{sha256_hex(core)[:32]}"
    return {**core, "freeze_id": freeze_id, "state": "PRECOMMITTED"}


def validate_custody_precommit(precommit: Mapping[str, Any]) -> dict[str, str]:
    """Validate a public precommit and its deterministic freeze identifier."""

    if not isinstance(precommit, Mapping):
        raise CustodyValidationError("custody precommit must be a JSON object")
    expected_fields = {
        "schema_version",
        "algorithm_id",
        "protocol_root_sha256",
        "snapshot_sha256",
        "eligible_records_sha256",
        "configuration_sha256",
        "selection_seed_sha256",
        "split_salt_sha256",
        "freeze_id",
        "state",
    }
    if set(precommit) != expected_fields:
        raise CustodyValidationError(
            "custody precommit fields differ from the closed schema: "
            f"missing={sorted(expected_fields - set(precommit))}, "
            f"extra={sorted(set(precommit) - expected_fields)}"
        )
    value = {str(key): str(item) for key, item in precommit.items()}
    if value["schema_version"] != PRECOMMIT_SCHEMA_VERSION:
        raise CustodyValidationError("unsupported custody precommit schema_version")
    if value["algorithm_id"] != PRECOMMIT_ALGORITHM_ID:
        raise CustodyValidationError("unsupported custody precommit algorithm_id")
    if value["state"] != "PRECOMMITTED":
        raise CustodyValidationError("custody precommit state must be PRECOMMITTED")
    for field in (
        "protocol_root_sha256",
        "snapshot_sha256",
        "eligible_records_sha256",
        "configuration_sha256",
        "selection_seed_sha256",
        "split_salt_sha256",
    ):
        _require_sha256(value[field], field=field)
    if hmac.compare_digest(value["selection_seed_sha256"], value["split_salt_sha256"]):
        raise CustodyValidationError("selection and split commitments must differ")
    core = {field: value[field] for field in _precommit_core(
        protocol_root_sha256=value["protocol_root_sha256"],
        snapshot_sha256=value["snapshot_sha256"],
        eligible_records_sha256=value["eligible_records_sha256"],
        configuration_sha256=value["configuration_sha256"],
        selection_seed_sha256=value["selection_seed_sha256"],
        split_salt_sha256=value["split_salt_sha256"],
    )}
    expected_freeze_id = f"mvx-g1-{sha256_hex(core)[:32]}"
    if not hmac.compare_digest(value["freeze_id"], expected_freeze_id):
        raise CustodyValidationError("custody precommit freeze_id is inconsistent")
    return value


def verify_custody_precommit(
    precommit: Mapping[str, Any],
    *,
    protocol_root_sha256: str,
    snapshot_sha256: str,
    eligible_records_sha256: str,
    configuration_sha256: str,
    selection_seed: bytes | bytearray | memoryview | str,
    split_salt: bytes | bytearray | memoryview | str,
    allow_public_test_secrets: bool = False,
) -> dict[str, str]:
    """Fail closed unless a published precommit binds both supplied preimages."""

    validated = validate_custody_precommit(precommit)
    expected = create_custody_precommit(
        protocol_root_sha256=protocol_root_sha256,
        snapshot_sha256=snapshot_sha256,
        eligible_records_sha256=eligible_records_sha256,
        configuration_sha256=configuration_sha256,
        selection_seed=selection_seed,
        split_salt=split_salt,
        allow_public_test_secrets=allow_public_test_secrets,
    )
    for field, expected_value in expected.items():
        if not hmac.compare_digest(validated[field], expected_value):
            raise CustodyValidationError(f"custody precommit mismatch for {field}")
    return validated


def _publication_receipt_core(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: copy.deepcopy(receipt[field])
        for field in (
            "schema_version",
            "algorithm_id",
            "publisher_id",
            "store_kind",
            "object_locator",
            "object_version_id",
            "sequence",
            "published_at",
            "trusted_publishers_sha256",
            "registry_epoch",
            "g0_seal_sha256",
            "protocol_root_sha256",
            "snapshot_sha256",
            "eligible_records_sha256",
            "freeze_id",
            "precommit_sha256",
            "published_object_sha256",
            "state",
        )
    }


def validate_trusted_publishers(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the frozen allow-list used for offline receipt verification."""

    if not isinstance(value, Mapping):
        raise CustodyValidationError("trusted publisher registry must be a JSON object")
    registry = copy.deepcopy(dict(value))
    if set(registry) != {"schema_version", "registry_epoch", "publishers", "g1_state"}:
        raise CustodyValidationError("trusted publisher registry fields differ")
    if registry["schema_version"] != TRUSTED_PUBLISHERS_SCHEMA_VERSION:
        raise CustodyValidationError("unsupported trusted publisher registry version")
    epoch = registry["registry_epoch"]
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise CustodyValidationError("trusted publisher registry requires a positive epoch")
    if registry["g1_state"] not in {G1_BLOCKED_STATE, G1_READY_STATE}:
        raise CustodyValidationError("trusted publisher registry has an unsupported g1_state")
    publishers = registry["publishers"]
    if not isinstance(publishers, list) or not publishers:
        raise CustodyValidationError("trusted publisher registry requires a non-empty array")
    seen: set[str] = set()
    for index, publisher in enumerate(publishers):
        if not isinstance(publisher, Mapping) or set(publisher) != {
            "publisher_id",
            "public_key_ed25519_hex",
            "store_kinds",
            "production",
            "valid_from",
            "valid_until",
            "sequence_minimum",
            "sequence_maximum",
            "object_locator_pattern",
            "object_version_id_pattern",
        }:
            raise CustodyValidationError(f"trusted publisher {index} fields differ")
        publisher_id = publisher["publisher_id"]
        if not isinstance(publisher_id, str) or not publisher_id or publisher_id in seen:
            raise CustodyValidationError("trusted publisher IDs must be non-empty and unique")
        seen.add(publisher_id)
        key_hex = publisher["public_key_ed25519_hex"]
        if (
            not isinstance(key_hex, str)
            or len(key_hex) != 64
            or any(character not in _HEX_DIGITS for character in key_hex)
        ):
            raise CustodyValidationError(f"trusted publisher {publisher_id} key is invalid")
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
        except ValueError as error:
            raise CustodyValidationError(
                f"trusted publisher {publisher_id} key is invalid"
            ) from error
        kinds = publisher["store_kinds"]
        if (
            not isinstance(kinds, list)
            or not kinds
            or len(kinds) != len(set(kinds))
            or any(not isinstance(kind, str) or not kind for kind in kinds)
        ):
            raise CustodyValidationError(f"trusted publisher {publisher_id} stores are invalid")
        if not isinstance(publisher["production"], bool):
            raise CustodyValidationError(f"trusted publisher {publisher_id} production is invalid")
        if publisher["production"] and not set(kinds) <= _PRODUCTION_STORE_KINDS:
            raise CustodyValidationError(
                f"trusted publisher {publisher_id} has a non-WORM production store"
            )
        if publisher["production"] and (
            publisher_id == _SYNTHETIC_PUBLISHER_ID
            or key_hex == _SYNTHETIC_PUBLISHER_PUBLIC_KEY_HEX
        ):
            raise CustodyValidationError(
                f"trusted publisher {publisher_id} promotes a public synthetic test key"
            )
        valid_from = _parse_utc_timestamp(
            publisher["valid_from"], field=f"trusted publisher {publisher_id}.valid_from"
        )
        valid_until = _parse_utc_timestamp(
            publisher["valid_until"], field=f"trusted publisher {publisher_id}.valid_until"
        )
        if valid_until <= valid_from:
            raise CustodyValidationError(
                f"trusted publisher {publisher_id} validity interval is empty"
            )
        minimum = publisher["sequence_minimum"]
        maximum = publisher["sequence_maximum"]
        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or minimum < 1
            or maximum < minimum
            or maximum > 2**53 - 1
        ):
            raise CustodyValidationError(
                f"trusted publisher {publisher_id} sequence bounds are invalid"
            )
        for field in ("object_locator_pattern", "object_version_id_pattern"):
            pattern = publisher[field]
            if (
                not isinstance(pattern, str)
                or not 1 <= len(pattern) <= 512
                or not pattern.startswith("^")
                or not pattern.endswith("$")
            ):
                raise CustodyValidationError(
                    f"trusted publisher {publisher_id} {field} is invalid"
                )
            try:
                re.compile(pattern)
            except re.error as error:
                raise CustodyValidationError(
                    f"trusted publisher {publisher_id} {field} is invalid"
                ) from error
        if publisher["production"] and not publisher["object_locator_pattern"].startswith(
            "^https://"
        ):
            raise CustodyValidationError(
                f"trusted publisher {publisher_id} production locator is not HTTPS-pinned"
            )

    production_publishers = [publisher for publisher in publishers if publisher["production"]]
    if registry["g1_state"] == G1_BLOCKED_STATE and production_publishers:
        raise CustodyValidationError("BLOCKED registry cannot contain a production publisher")
    if registry["g1_state"] == G1_READY_STATE and (
        not production_publishers or len(production_publishers) != len(publishers)
    ):
        raise CustodyValidationError(
            "READY registry requires at least one publisher and every publisher must be production"
        )
    return registry


def _load_production_trust_context(protocol_root_sha256: str) -> _ProductionTrustContext:
    """Load only the sealed normative publisher registry for production G1.

    This is deliberately not parameterised by a path.  The protocol seal binds
    the exact bytes of the registry and the G0 verdict binds the exact seal.
    """

    from . import protocol as protocol_module

    expected_root = _require_sha256(
        protocol_root_sha256, field="production protocol_root_sha256"
    )
    if TRUSTED_PUBLISHERS_RELATIVE_PATH not in protocol_module.NORMATIVE_PATHS:
        raise CustodyValidationError("trusted publisher registry is absent from NORMATIVE_PATHS")
    verification = protocol_module.verify_protocol(require_seal=True)
    if not verification.ok or verification.root_sha256 != expected_root:
        failures = "; ".join(
            f"{check.identifier}: {check.evidence}" for check in verification.failures
        )
        raise CustodyValidationError(
            "production trust requires the current FROZEN sealed protocol"
            + (f": {failures}" if failures else "")
        )

    seal_bytes = _read_regular_bytes(protocol_module.SEAL_PATH, field="G0 seal")
    verdict_bytes = _read_regular_bytes(protocol_module.G0_PATH, field="G0 verdict")
    registry_path = protocol_module.PROJECT_ROOT / TRUSTED_PUBLISHERS_RELATIVE_PATH
    registry_bytes = _read_regular_bytes(registry_path, field="trusted publisher registry")
    try:
        seal = json.loads(seal_bytes)
        verdict = json.loads(verdict_bytes)
        registry_value = json.loads(registry_bytes)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CustodyValidationError("production trust anchor JSON is invalid") from error
    if not isinstance(seal, Mapping) or not isinstance(verdict, Mapping):
        raise CustodyValidationError("G0 seal and verdict must be JSON objects")
    if seal.get("protocol_root_sha256") != expected_root:
        raise CustodyValidationError("G0 seal root differs from the precommit protocol root")
    seal_hash = hashlib.sha256(seal_bytes).hexdigest()
    if (
        verdict.get("gate") != "G0"
        or verdict.get("verdict") != "PASS"
        or verdict.get("protocol_root_sha256") != expected_root
        or verdict.get("blockers") != []
        or not isinstance(verdict.get("criteria"), list)
        or not verdict["criteria"]
        or any(item.get("passed") is not True for item in verdict["criteria"])
        or not isinstance(verdict.get("evidence_hashes"), Mapping)
        or verdict["evidence_hashes"].get("seal.json") != seal_hash
    ):
        raise CustodyValidationError("production trust requires a matching PASS G0 verdict")

    entries = [
        item
        for item in seal.get("files", [])
        if isinstance(item, Mapping)
        and item.get("path") == TRUSTED_PUBLISHERS_RELATIVE_PATH
    ]
    registry_file_hash = hashlib.sha256(registry_bytes).hexdigest()
    if len(entries) != 1 or entries[0].get("sha256") != registry_file_hash:
        raise CustodyValidationError(
            "trusted publisher registry bytes do not match the exact G0 seal entry"
        )
    registry = validate_trusted_publishers(registry_value)
    if registry["g1_state"] != G1_READY_STATE:
        raise CustodyValidationError(
            f"production G1 is blocked by trusted publisher state {registry['g1_state']!r}"
        )
    if any(
        not publisher["production"]
        or "SYNTHETIC_TEST_ONLY" in publisher["store_kinds"]
        for publisher in registry["publishers"]
    ):
        raise CustodyValidationError(
            "production registry contains a synthetic or non-production publisher"
        )
    sealed_at = _parse_utc_timestamp(seal.get("sealed_at"), field="G0 seal sealed_at")
    return _ProductionTrustContext(
        registry=registry,
        registry_sha256=registry_file_hash,
        registry_epoch=registry["registry_epoch"],
        g0_seal_sha256=seal_hash,
        g0_sealed_at=sealed_at,
    )


def _validate_precommit_publication_receipt(
    receipt: Mapping[str, Any],
    *,
    precommit: Mapping[str, Any],
    trusted_publishers: Mapping[str, Any] | None = None,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """Verify a signed external/WORM publication receipt offline.

    A receipt is not generated by the development process.  It must be signed
    by a key in the frozen publisher registry and bind an immutable external
    object version containing the exact precommit.  Production verification
    rejects local/synthetic stores and non-production keys.
    """

    validated_precommit = validate_custody_precommit(precommit)
    production_context: _ProductionTrustContext | None = None
    if allow_synthetic:
        if trusted_publishers is None:
            raise CustodyValidationError(
                "synthetic receipt verification requires its explicit test registry"
            )
        registry = validate_trusted_publishers(trusted_publishers)
        # Synthetic tests have no external file.  Their one permitted byte
        # identity is canonical JSON plus the repository newline convention.
        expected_registry_hash = sha256_hex(canonical_json_bytes(registry) + b"\n")
        expected_registry_epoch = registry["registry_epoch"]
        expected_g0_seal_hash = SYNTHETIC_G0_SEAL_SHA256
    else:
        if trusted_publishers is not None:
            raise CustodyValidationError(
                "production trusted publisher registry cannot be supplied by the caller"
            )
        production_context = _load_production_trust_context(
            validated_precommit["protocol_root_sha256"]
        )
        registry = production_context.registry
        expected_registry_hash = production_context.registry_sha256
        expected_registry_epoch = production_context.registry_epoch
        expected_g0_seal_hash = production_context.g0_seal_sha256
    if not isinstance(receipt, Mapping):
        raise CustodyValidationError("publication receipt must be a JSON object")
    document = copy.deepcopy(dict(receipt))
    expected = {
        "schema_version",
        "algorithm_id",
        "publisher_id",
        "store_kind",
        "object_locator",
        "object_version_id",
        "sequence",
        "published_at",
        "trusted_publishers_sha256",
        "registry_epoch",
        "g0_seal_sha256",
        "protocol_root_sha256",
        "snapshot_sha256",
        "eligible_records_sha256",
        "freeze_id",
        "precommit_sha256",
        "published_object_sha256",
        "state",
        "signature_ed25519_hex",
    }
    if set(document) != expected:
        raise CustodyValidationError("publication receipt fields differ from the closed schema")
    if document["schema_version"] != PUBLICATION_RECEIPT_SCHEMA_VERSION:
        raise CustodyValidationError("unsupported publication receipt schema_version")
    if document["algorithm_id"] != PUBLICATION_RECEIPT_ALGORITHM_ID:
        raise CustodyValidationError("unsupported publication receipt algorithm_id")
    if document["state"] != "PUBLISHED_IMMUTABLE":
        raise CustodyValidationError("publication receipt is not immutable/terminal")
    for field in (
        "protocol_root_sha256",
        "snapshot_sha256",
        "eligible_records_sha256",
        "precommit_sha256",
        "published_object_sha256",
        "trusted_publishers_sha256",
        "g0_seal_sha256",
    ):
        _require_sha256(document[field], field=f"publication_receipt.{field}")
    registry_epoch = document["registry_epoch"]
    if isinstance(registry_epoch, bool) or not isinstance(registry_epoch, int):
        raise CustodyValidationError("publication receipt registry_epoch must be an integer")
    sequence = document["sequence"]
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or not 1 <= sequence <= 2**53 - 1
    ):
        raise CustodyValidationError("publication receipt sequence is outside I-JSON bounds")
    for field in (
        "publisher_id",
        "store_kind",
        "object_locator",
        "object_version_id",
        "published_at",
        "freeze_id",
    ):
        if not isinstance(document[field], str) or not document[field]:
            raise CustodyValidationError(f"publication receipt requires non-empty {field}")
    published_at = _parse_utc_timestamp(
        document["published_at"], field="publication receipt published_at"
    )

    precommit_hash = sha256_hex(validated_precommit)
    bindings = {
        "protocol_root_sha256": validated_precommit["protocol_root_sha256"],
        "snapshot_sha256": validated_precommit["snapshot_sha256"],
        "eligible_records_sha256": validated_precommit["eligible_records_sha256"],
        "freeze_id": validated_precommit["freeze_id"],
        "precommit_sha256": precommit_hash,
        "published_object_sha256": precommit_hash,
        "trusted_publishers_sha256": expected_registry_hash,
        "g0_seal_sha256": expected_g0_seal_hash,
    }
    for field, expected_value in bindings.items():
        if not hmac.compare_digest(document[field], expected_value):
            raise CustodyValidationError(f"publication receipt mismatch for {field}")
    if registry_epoch != expected_registry_epoch:
        raise CustodyValidationError("publication receipt mismatch for registry_epoch")
    if production_context is not None:
        if published_at <= production_context.g0_sealed_at:
            raise CustodyValidationError("publication receipt predates or equals the G0 seal")
        if published_at > _utc_now() + MAX_RECEIPT_FUTURE_SKEW:
            raise CustodyValidationError("publication receipt is too far in the future")

    publishers = {
        publisher["publisher_id"]: publisher for publisher in registry["publishers"]
    }
    publisher = publishers.get(document["publisher_id"])
    if publisher is None:
        raise CustodyValidationError("publication receipt publisher is not trusted")
    if document["store_kind"] not in publisher["store_kinds"]:
        raise CustodyValidationError("publication receipt store is not authorised")
    if not publisher["sequence_minimum"] <= sequence <= publisher["sequence_maximum"]:
        raise CustodyValidationError("publication receipt sequence is outside publisher bounds")
    if re.fullmatch(publisher["object_version_id_pattern"], document["object_version_id"]) is None:
        raise CustodyValidationError(
            "publication receipt object version is outside publisher bounds"
        )
    if re.fullmatch(publisher["object_locator_pattern"], document["object_locator"]) is None:
        raise CustodyValidationError(
            "publication receipt object locator is outside publisher bounds"
        )
    valid_from = _parse_utc_timestamp(
        publisher["valid_from"], field=f"trusted publisher {publisher['publisher_id']}.valid_from"
    )
    valid_until = _parse_utc_timestamp(
        publisher["valid_until"], field=f"trusted publisher {publisher['publisher_id']}.valid_until"
    )
    if not valid_from <= published_at <= valid_until:
        raise CustodyValidationError("publication receipt is outside publisher validity")
    if allow_synthetic:
        if publisher["production"] or document["store_kind"] != "SYNTHETIC_TEST_ONLY":
            raise CustodyValidationError(
                "synthetic verification accepts only a non-production synthetic publisher"
            )
    else:
        if not publisher["production"] or document["store_kind"] not in _PRODUCTION_STORE_KINDS:
            raise CustodyValidationError("publication receipt is not production-authorised")
        if not document["object_locator"].startswith("https://"):
            raise CustodyValidationError("production publication locator must be HTTPS")
        if production_context is None:  # pragma: no cover - guarded by the branch above.
            raise AssertionError("production receipt validation lacks its trust context")

    signature_hex = document["signature_ed25519_hex"]
    if (
        not isinstance(signature_hex, str)
        or len(signature_hex) != 128
        or any(character not in _HEX_DIGITS for character in signature_hex)
    ):
        raise CustodyValidationError("publication receipt signature is invalid")
    public_key = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(publisher["public_key_ed25519_hex"])
    )
    try:
        public_key.verify(bytes.fromhex(signature_hex), canonical_json_bytes(_publication_receipt_core(document)))
    except InvalidSignature as error:
        raise CustodyValidationError("publication receipt signature verification failed") from error
    return document


def validate_precommit_publication_receipt(
    receipt: Mapping[str, Any],
    *,
    precommit: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a production G1 receipt against only the sealed trust registry.

    No caller-controlled registry, path, key, store override, verification clock
    or synthetic-mode switch exists on this production surface.
    """

    return _validate_precommit_publication_receipt(receipt, precommit=precommit)


def _validate_all_declared_hashes(value: Any, *, location: str = "$") -> None:
    """Validate every explicitly named SHA-256 field, including nested artifacts."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key.endswith("_sha256"):
                _require_sha256(child, field=child_location)
            _validate_all_declared_hashes(child, location=child_location)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _validate_all_declared_hashes(child, location=f"{location}[{index}]")


def validate_private_manifest(private_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy a complete private split manifest.

    Validation is intentionally fail-closed: lineage IDs must be unique, each
    leakage group must belong to exactly one split, declared counts must match the
    assignment rows, and all fields named ``*_sha256`` must be valid lowercase
    digests.
    """

    if not isinstance(private_manifest, Mapping):
        raise CustodyValidationError("private manifest must be a JSON object")
    manifest = copy.deepcopy(dict(private_manifest))
    _validate_json_value(manifest)

    for field in ("schema_version", "algorithm_id", "algorithm_version", "freeze_id"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise CustodyValidationError(f"private manifest requires non-empty {field}")
    _require_sha256(manifest.get("protocol_root_sha256"), field="protocol_root_sha256")
    _require_sha256(manifest.get("salt_sha256"), field="salt_sha256")
    _require_sha256(manifest.get("selection_seed_sha256"), field="selection_seed_sha256")
    _require_sha256(manifest.get("precommit_sha256"), field="precommit_sha256")
    _require_sha256(
        manifest.get("publication_receipt_sha256"), field="publication_receipt_sha256"
    )
    _validate_all_declared_hashes(manifest)

    assignments = manifest.get("assignments")
    if not isinstance(assignments, list):
        raise CustodyValidationError("private manifest assignments must be an array")
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        raise CustodyValidationError("private manifest counts must be an object")

    seen_lineages: set[str] = set()
    group_splits: dict[str, set[str]] = defaultdict(set)
    observed: Counter[str] = Counter()
    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, Mapping):
            raise CustodyValidationError(f"assignment {index} must be an object")
        lineage_id = assignment.get("lineage_id")
        leakage_group_id = assignment.get("leakage_group_id")
        split = assignment.get("split")
        if not isinstance(lineage_id, str) or not lineage_id:
            raise CustodyValidationError(f"assignment {index} has invalid lineage_id")
        if lineage_id in seen_lineages:
            raise CustodyValidationError(f"duplicate lineage_id {lineage_id!r}")
        seen_lineages.add(lineage_id)
        if not isinstance(leakage_group_id, str) or not leakage_group_id:
            raise CustodyValidationError(f"assignment {index} has invalid leakage_group_id")
        if split not in SPLITS:
            raise CustodyValidationError(f"assignment {index} has invalid split {split!r}")
        group_splits[leakage_group_id].add(split)
        observed[split] += 1

    leaked_groups = sorted(
        group for group, destinations in group_splits.items() if len(destinations) > 1
    )
    if leaked_groups:
        raise CustodyValidationError(
            "leakage groups cross split boundaries: "
            + ", ".join(repr(group) for group in leaked_groups)
        )

    for split in SPLITS:
        declared = counts.get(split, 0)
        if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
            raise CustodyValidationError(f"counts.{split} must be a non-negative integer")
        if declared != observed[split]:
            raise CustodyValidationError(
                f"counts.{split}={declared} does not match {observed[split]} assignments"
            )
    unsupported_counts = sorted(set(counts) - set(SPLITS))
    if unsupported_counts:
        raise CustodyValidationError(f"unsupported split count keys: {unsupported_counts}")
    return manifest


def _keyed_commitment(secret: bytes, *, purpose: bytes, payload: bytes) -> str:
    return hmac.new(secret, purpose + b"\x00" + payload, hashlib.sha256).hexdigest()


def create_custody_release(
    private_manifest: Mapping[str, Any],
    secret: bytes | bytearray | memoryview | str,
    *,
    allow_public_test_secret: bool = False,
) -> dict[str, dict[str, Any]]:
    """Create public and development/calibration views of a private manifest.

    The public view contains no assignment rows, identifiers, or paths.  The
    visible view contains only complete development/calibration rows.  The input
    is never mutated.  The returned commitments authenticate the private state
    when the same external secret is presented later; they do not encrypt it.
    """

    manifest = validate_private_manifest(private_manifest)
    secret_raw = _secret_bytes(secret, allow_public_test_secret=allow_public_test_secret)
    assignments = manifest["assignments"]
    observed = Counter(str(row["split"]) for row in assignments)

    private_commitment = _keyed_commitment(
        secret_raw,
        purpose=b"MVX-CUSTODY-PRIVATE-MANIFEST-V1",
        payload=canonical_json_bytes(manifest),
    )
    salt_commitment = _keyed_commitment(
        secret_raw,
        purpose=b"MVX-CUSTODY-SALT-V1",
        payload=manifest["salt_sha256"].encode("ascii"),
    )
    public_manifest = {
        "schema": PUBLIC_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "protocol_root_sha256": manifest["protocol_root_sha256"],
        "algorithm_id": ALGORITHM_ID,
        "freeze_id": manifest["freeze_id"],
        "precommit_sha256": manifest["precommit_sha256"],
        "publication_receipt_sha256": manifest["publication_receipt_sha256"],
        "selection_seed_commitment_sha256": manifest["selection_seed_sha256"],
        "split_salt_commitment_sha256": manifest["salt_sha256"],
        "counts": {split: observed[split] for split in SPLITS},
        "salt_commitment_sha256": salt_commitment,
        "private_manifest_commitment_sha256": private_commitment,
    }
    hidden_tokens = {
        str(row[field])
        for row in assignments
        if row["split"] not in VISIBLE_SPLITS
        for field in SENSITIVE_ASSIGNMENT_FIELDS
        if isinstance(row.get(field), str) and len(str(row[field])) >= 8
    }
    visible_assignments = [
        {
            field: copy.deepcopy(row[field])
            for field in sorted(VISIBLE_ASSIGNMENT_FIELDS)
            if field in row
        }
        for row in assignments
        if row["split"] in VISIBLE_SPLITS
    ]
    visible_payload = canonical_json_bytes(visible_assignments).decode("utf-8")
    leaked_tokens = sorted(token for token in hidden_tokens if token in visible_payload)
    if leaked_tokens:
        raise CustodyValidationError(
            "visible assignments contain hidden sensitive tokens: "
            + ", ".join(repr(token) for token in leaked_tokens[:5])
        )
    visible_manifest = {
        "schema": VISIBLE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "protocol_root_sha256": manifest["protocol_root_sha256"],
        "algorithm_id": manifest["algorithm_id"],
        "algorithm_version": manifest["algorithm_version"],
        "freeze_id": manifest["freeze_id"],
        "precommit_sha256": manifest["precommit_sha256"],
        "publication_receipt_sha256": manifest["publication_receipt_sha256"],
        "private_manifest_commitment_sha256": private_commitment,
        "assignments": visible_assignments,
        "counts": {split: observed[split] for split in sorted(VISIBLE_SPLITS)},
    }
    return {"public_manifest": public_manifest, "visible_manifest": visible_manifest}


def verify_private_manifest_commitment(
    private_manifest: Mapping[str, Any],
    secret: bytes | bytearray | memoryview | str,
    expected_commitment_sha256: str,
    *,
    allow_public_test_secret: bool = False,
) -> bool:
    """Verify a previously published private-manifest commitment."""

    expected = _require_sha256(expected_commitment_sha256, field="expected_commitment_sha256")
    manifest = validate_private_manifest(private_manifest)
    actual = _keyed_commitment(
        _secret_bytes(secret, allow_public_test_secret=allow_public_test_secret),
        purpose=b"MVX-CUSTODY-PRIVATE-MANIFEST-V1",
        payload=canonical_json_bytes(manifest),
    )
    return hmac.compare_digest(actual, expected)


def synthetic_dry_run() -> dict[str, dict[str, Any]]:
    """Return a deterministic, non-production custody release for smoke tests."""

    zero_hash = "0" * 64
    one_hash = "1" * 64
    synthetic_selection_secret = hashlib.sha256(
        b"MVX custody synthetic selection seed v1"
    ).digest()
    synthetic_secret = hashlib.sha256(b"MVX custody synthetic dry run v1").digest()
    precommit = create_custody_precommit(
        protocol_root_sha256=zero_hash,
        snapshot_sha256=one_hash,
        eligible_records_sha256="2" * 64,
        configuration_sha256="3" * 64,
        selection_seed=synthetic_selection_secret,
        split_salt=synthetic_secret,
        allow_public_test_secrets=True,
    )
    synthetic_receipt_hash = hashlib.sha256(
        b"MVX custody synthetic receipt placeholder v2"
    ).hexdigest()
    manifest = {
        "schema_version": "0.1.0",
        "algorithm_id": "MVX-GROUP-STRATIFIED-HMAC-2",
        "algorithm_version": "2.0.0",
        "protocol_root_sha256": zero_hash,
        "salt_sha256": precommit["split_salt_sha256"],
        "selection_seed_sha256": precommit["selection_seed_sha256"],
        "precommit_sha256": sha256_hex(precommit),
        "publication_receipt_sha256": synthetic_receipt_hash,
        "freeze_id": precommit["freeze_id"],
        "assignments": [
            {
                "lineage_id": "SYNTH-DEV-001",
                "leakage_group_id": "SYNTH-GROUP-DEV",
                "split": "development",
                "selection_stratum": "synthetic",
                "blind_scope": "NONE",
                "creator_group": "SYNTH-CREATOR-DEV",
                "source_uid": "SYNTH-SOURCE-DEV",
                "source_path": "/synthetic/development.glb",
            },
            {
                "lineage_id": "SYNTH-CAL-001",
                "leakage_group_id": "SYNTH-GROUP-CAL",
                "split": "calibration",
                "selection_stratum": "synthetic",
                "blind_scope": "NONE",
                "creator_group": "SYNTH-CREATOR-CAL",
                "source_uid": "SYNTH-SOURCE-CAL",
                "source_path": "/synthetic/calibration.glb",
            },
            {
                "lineage_id": "SYNTH-BLIND-001",
                "leakage_group_id": "SYNTH-GROUP-BLIND",
                "split": "blind",
                "selection_stratum": "synthetic",
                "blind_scope": "IID",
                "creator_group": "SYNTH-CREATOR-BLIND",
                "source_uid": "SYNTH-SOURCE-BLIND",
                "source_path": "/synthetic/private/blind.glb",
            },
        ],
        "counts": {"development": 1, "calibration": 1, "blind": 1, "reserve": 0},
        "deviations": [],
    }
    # A deterministic fixture secret is acceptable only because no real private
    # state is involved.  Production callers must source their secret externally.
    return create_custody_release(
        manifest,
        synthetic_secret,
        allow_public_test_secret=True,
    )


__all__ = [
    "ALGORITHM_ID",
    "PUBLICATION_RECEIPT_ALGORITHM_ID",
    "CustodyValidationError",
    "canonical_json_bytes",
    "create_custody_precommit",
    "create_custody_release",
    "sha256_hex",
    "synthetic_dry_run",
    "validate_custody_precommit",
    "validate_precommit_publication_receipt",
    "validate_private_manifest",
    "validate_secret_bytes",
    "validate_trusted_publishers",
    "verify_custody_precommit",
    "verify_private_manifest_commitment",
]
