from __future__ import annotations

import unittest

from morphoia.topology import (
    EntityCandidate,
    ReferenceQuery,
    ResolutionStatus,
    resolve_reference,
)


class TopologyReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = ReferenceQuery(
            kind="face",
            producer="blank",
            role="cap.end",
            signature=(("normal", "+Z"),),
        )
        self.first = EntityCandidate(
            identity="face-a",
            kind="face",
            producer="blank",
            role="cap.end",
            signature=(("normal", "+Z"),),
        )

    def test_unique(self) -> None:
        result = resolve_reference(self.query, [self.first])
        self.assertEqual(result.status, ResolutionStatus.UNIQUE)
        self.assertEqual(result.entity.identity, "face-a")

    def test_ambiguous_is_not_silently_ranked(self) -> None:
        second = EntityCandidate(
            identity="face-b",
            kind="face",
            producer="blank",
            role="cap.end",
            signature=(("normal", "+Z"),),
        )
        result = resolve_reference(self.query, [second, self.first])
        self.assertEqual(result.status, ResolutionStatus.AMBIGUOUS)
        self.assertEqual([item.identity for item in result.candidates], ["face-a", "face-b"])
        with self.assertRaises(LookupError):
            _ = result.entity

    def test_missing(self) -> None:
        result = resolve_reference(self.query, [])
        self.assertEqual(result.status, ResolutionStatus.MISSING)


if __name__ == "__main__":
    unittest.main()
