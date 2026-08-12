"""Versioned SALOME control-plane contracts with no SALOME runtime dependency."""

from .contract import (
    MAX_CONTROL_MESSAGE_BYTES,
    OPERATIONS,
    PROTOCOL_VERSION,
    ProtocolError,
    encode_control_json,
    load_control_json,
)
from .fake_agent import FakeSalomeAgent

__all__ = [
    "MAX_CONTROL_MESSAGE_BYTES",
    "OPERATIONS",
    "PROTOCOL_VERSION",
    "FakeSalomeAgent",
    "ProtocolError",
    "encode_control_json",
    "load_control_json",
]
