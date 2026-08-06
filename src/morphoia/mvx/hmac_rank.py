"""Unambiguous domain-separated HMAC ranking for MVX protocols.

The earlier experimental implementations joined caller-controlled strings with
one delimiter byte.  That representation was ambiguous whenever the delimiter
occurred inside an identifier.  This module uses an explicit protocol prefix
and an unsigned 64-bit byte length before every strict UTF-8 field.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable

ENCODING_ID = "MVX-HMAC-RANK-LP-UTF8-1"
_PREFIX = b"MORPHOIA\x00MVX\x00HMAC-RANK\x00\x01"


def encode_rank_message(
    *,
    algorithm_id: str,
    algorithm_version: str,
    domain: str,
    parts: Iterable[str],
) -> bytes:
    """Encode one rank message without delimiter or tuple-boundary ambiguity."""

    fields = (ENCODING_ID, algorithm_id, algorithm_version, domain, *tuple(parts))
    encoded = bytearray(_PREFIX)
    for index, field in enumerate(fields):
        if not isinstance(field, str):
            raise TypeError(f"HMAC rank field {index} must be a string")
        if index in {1, 2, 3} and not field:
            raise ValueError("algorithm ID, algorithm version and domain must be non-empty")
        try:
            payload = field.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValueError(f"HMAC rank field {index} is not valid Unicode") from error
        encoded.extend(len(payload).to_bytes(8, byteorder="big", signed=False))
        encoded.extend(payload)
    return bytes(encoded)


def hmac_sha256_rank(
    key: bytes,
    *,
    algorithm_id: str,
    algorithm_version: str,
    domain: str,
    parts: Iterable[str],
) -> bytes:
    """Return a 256-bit HMAC rank over a length-prefixed domain-separated tuple."""

    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("HMAC rank key must contain exactly 256 bits")
    message = encode_rank_message(
        algorithm_id=algorithm_id,
        algorithm_version=algorithm_version,
        domain=domain,
        parts=parts,
    )
    return hmac.new(key, message, hashlib.sha256).digest()


__all__ = ["ENCODING_ID", "encode_rank_message", "hmac_sha256_rank"]
