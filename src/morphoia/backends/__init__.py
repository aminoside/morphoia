"""Backend interfaces and reference encoders."""

from .base import Backend, BackendCapabilities, BackendResult
from .json_backend import CanonicalJsonBackend

__all__ = ["Backend", "BackendCapabilities", "BackendResult", "CanonicalJsonBackend"]
