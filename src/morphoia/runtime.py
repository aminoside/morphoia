"""Small transactional store for immutable canonical construction graphs.

This is the executable reference for atomic commit, optimistic concurrency and
undo/redo. Geometry execution remains the responsibility of qualified backends.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .compiler import semantic_hash


class TransactionError(RuntimeError):
    pass


class RevisionConflict(TransactionError):
    pass


@dataclass(frozen=True, slots=True)
class Revision:
    number: int
    semantic_sha256: str
    graph: dict[str, Any]
    message: str


class Transaction:
    def __init__(self, store: RuntimeStore, base: Revision):
        self._store = store
        self.base = base
        self.graph = deepcopy(base.graph)
        self._closed = False

    def replace_graph(self, graph: dict[str, Any]) -> None:
        self._ensure_open()
        self.graph = deepcopy(graph)

    def commit(
        self,
        message: str,
        *,
        validators: tuple[Callable[[dict[str, Any]], None], ...] = (),
    ) -> Revision:
        self._ensure_open()
        if not message.strip():
            raise TransactionError("a commit message is required")
        for validator in validators:
            validator(self.graph)
        revision = self._store._commit(self.base.number, self.graph, message)
        self._closed = True
        return revision

    def rollback(self) -> None:
        self._ensure_open()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise TransactionError("transaction is already closed")


class RuntimeStore:
    """In-memory immutable revision store.

    A production implementation may persist content-addressed revisions, but it
    must preserve the same atomic behavior and must never mutate a committed
    graph in place.
    """

    def __init__(self, initial_graph: dict[str, Any]):
        graph = deepcopy(initial_graph)
        digest = semantic_hash(graph)
        self._history: list[Revision] = [Revision(0, digest, graph, "initial")]
        self._cursor = 0

    @property
    def current(self) -> Revision:
        return self._history[self._cursor]

    @property
    def can_undo(self) -> bool:
        return self._cursor > 0

    @property
    def can_redo(self) -> bool:
        return self._cursor + 1 < len(self._history)

    def begin(self) -> Transaction:
        return Transaction(self, self.current)

    def undo(self) -> Revision:
        if not self.can_undo:
            raise TransactionError("no revision to undo")
        self._cursor -= 1
        return self.current

    def redo(self) -> Revision:
        if not self.can_redo:
            raise TransactionError("no revision to redo")
        self._cursor += 1
        return self.current

    def _commit(self, base_number: int, graph: dict[str, Any], message: str) -> Revision:
        if base_number != self.current.number:
            raise RevisionConflict(
                f"transaction started at revision {base_number}, current is {self.current.number}"
            )
        graph_copy = deepcopy(graph)
        graph_copy.pop("semantic_sha256", None)
        digest = semantic_hash(graph_copy)
        graph_copy["semantic_sha256"] = digest
        self._history = self._history[: self._cursor + 1]
        revision = Revision(self.current.number + 1, digest, graph_copy, message)
        self._history.append(revision)
        self._cursor += 1
        return revision
