from __future__ import annotations

import unittest
from decimal import Decimal

from morphoia.losses import (
    LossCategory,
    LossRecord,
    LossRegister,
    LossSeverity,
)
from morphoia.provenance import Decision, DecisionStatus, Evidence, EvidenceKind
from morphoia.runtime import RevisionConflict, RuntimeStore, TransactionError


class RuntimeTests(unittest.TestCase):
    def test_commit_undo_and_redo_are_atomic(self) -> None:
        store = RuntimeStore({"format": "test", "value": 1})
        transaction = store.begin()
        transaction.graph["value"] = 2
        committed = transaction.commit("change value")
        self.assertEqual(committed.number, 1)
        self.assertEqual(store.current.graph["value"], 2)
        self.assertEqual(store.undo().graph["value"], 1)
        self.assertEqual(store.redo().graph["value"], 2)

    def test_stale_transaction_is_rejected(self) -> None:
        store = RuntimeStore({"format": "test"})
        stale = store.begin()
        current = store.begin()
        current.commit("advance")
        with self.assertRaises(RevisionConflict):
            stale.commit("stale write")

    def test_failed_validator_does_not_change_current_revision(self) -> None:
        store = RuntimeStore({"format": "test"})
        transaction = store.begin()

        def reject(_graph):
            raise ValueError("invalid geometry")

        with self.assertRaises(ValueError):
            transaction.commit("invalid", validators=(reject,))
        self.assertEqual(store.current.number, 0)

    def test_closed_transaction_cannot_be_reused(self) -> None:
        store = RuntimeStore({"format": "test"})
        transaction = store.begin()
        transaction.rollback()
        with self.assertRaises(TransactionError):
            transaction.commit("invalid reuse")


class TrustContractTests(unittest.TestCase):
    def test_accepted_decision_requires_evidence_and_actor(self) -> None:
        with self.assertRaises(ValueError):
            Decision("d1", "width", DecisionStatus.ACCEPTED, ())

    def test_provenance_and_loss_register(self) -> None:
        evidence = Evidence(
            "e1",
            EvidenceKind.DRAWING,
            "urn:morphoia:drawing:1",
            "a" * 64,
            "view:front/dimension:12",
        )
        decision = Decision(
            "d1",
            "width",
            DecisionStatus.ACCEPTED,
            (evidence.identity,),
            confidence=Decimal("0.99"),
            decided_by="rule:explicit-dimension",
        )
        self.assertEqual(decision.status, DecisionStatus.ACCEPTED)

        register = LossRegister(
            "export",
            "canonical",
            "gltf",
            (
                LossRecord(
                    "MORPH-L001",
                    LossCategory.PARAMETRIC_HISTORY,
                    LossSeverity.ERROR,
                    "model",
                    "glTF does not preserve the construction history",
                ),
            ),
        )
        self.assertTrue(register.blocks_commit)
        self.assertTrue(register.to_dict()["blocks_commit"])


if __name__ == "__main__":
    unittest.main()
