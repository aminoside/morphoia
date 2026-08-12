"""Small, deterministic helpers for the SALOME control-plane JSON contract."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

PROTOCOL_VERSION = "0.1.0"
MAX_CONTROL_MESSAGE_BYTES = 1_048_576
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
OPERATIONS = (
    "ProbeCapabilities",
    "Submit",
    "Observe",
    "Cancel",
    "Publish",
    "Health",
)


class ProtocolError(ValueError):
    """Raised when a control message cannot be decoded or dispatched safely."""


def _reject_constant(value: str) -> NoReturn:
    raise ProtocolError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def ensure_safe_control_value(value: Any, *, path: str = "$") -> None:
    if isinstance(value, str):
        for character in value:
            if 0xD800 <= ord(character) <= 0xDFFF:
                raise ProtocolError(f"lone Unicode surrogate is forbidden at {path}")
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProtocolError(f"non-finite JSON number is forbidden at {path}")
        return
    if isinstance(value, int):
        if not -MAX_SAFE_JSON_INTEGER <= value <= MAX_SAFE_JSON_INTEGER:
            raise ProtocolError(f"integer outside the interoperable JSON range at {path}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolError(f"JSON object key is not a string at {path}")
            ensure_safe_control_value(key, path=f"{path}.<key>")
            ensure_safe_control_value(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            ensure_safe_control_value(item, path=f"{path}[{index}]")
        return
    raise ProtocolError(f"unsupported JSON value type at {path}: {type(value).__name__}")


def load_control_json(document: str | bytes) -> dict[str, Any]:
    """Decode bounded strict JSON and reject unsafe cross-runtime values."""

    if isinstance(document, bytes):
        if len(document) > MAX_CONTROL_MESSAGE_BYTES:
            raise ProtocolError("control JSON exceeds the 1 MiB protocol limit")
        try:
            document = document.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ProtocolError("control JSON must be valid UTF-8") from exc
    else:
        try:
            encoded_size = len(document.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as exc:
            raise ProtocolError("control JSON contains an invalid Unicode scalar value") from exc
        if encoded_size > MAX_CONTROL_MESSAGE_BYTES:
            raise ProtocolError("control JSON exceeds the 1 MiB protocol limit")
    try:
        value = json.loads(
            document,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid control JSON: {exc.msg}") from exc
    except RecursionError as exc:
        raise ProtocolError("control JSON nesting is too deep") from exc
    if not isinstance(value, dict):
        raise ProtocolError("a control message must be a JSON object")
    ensure_safe_control_value(value)
    return value


def encode_control_json(message: Mapping[str, Any]) -> str:
    """Encode bounded deterministic control JSON.

    This stable local transport encoding is not RFC 8785, not Morphoia IR
    canonical JSON, and must not be signed or used as a content identity.
    """

    try:
        ensure_safe_control_value(message)
        encoded = (
            json.dumps(
                dict(message),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        if len(encoded.encode("utf-8")) > MAX_CONTROL_MESSAGE_BYTES:
            raise ProtocolError("control JSON exceeds the 1 MiB protocol limit")
        return encoded
    except ProtocolError:
        raise
    except UnicodeEncodeError as exc:
        raise ProtocolError("control message contains an invalid Unicode scalar value") from exc
    except (RecursionError, TypeError, ValueError) as exc:
        raise ProtocolError(f"control message cannot be encoded as deterministic JSON: {exc}") from exc
