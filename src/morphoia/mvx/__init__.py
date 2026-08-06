"""Morphoia Visual Exchange experimental validation tools.

The P0 module contains protocol and corpus-split infrastructure only. It does
not claim to implement the MVX 0.2.1 geometry codec.
"""

from .protocol import PROTOCOL_VERSION, protocol_root, verify_protocol

__all__ = ["PROTOCOL_VERSION", "protocol_root", "verify_protocol"]
