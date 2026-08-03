from __future__ import annotations

import unittest
from pathlib import Path

from morphoia.compiler import compile_document, semantic_hash
from morphoia.validator import validate_source

ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    def test_reference_example_is_valid(self) -> None:
        source = (ROOT / "examples" / "mounting_plate.morph").read_text(encoding="utf-8")
        result = validate_source(source)
        self.assertTrue(result.ok, [diagnostic.message for diagnostic in result.diagnostics])

    def test_canonical_hash_is_deterministic(self) -> None:
        source = (ROOT / "examples" / "mounting_plate.morph").read_text(encoding="utf-8")
        first = validate_source(source)
        second = validate_source(source)
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        assert first.document is not None
        assert second.document is not None
        first_ir = compile_document(first.document)
        second_ir = compile_document(second.document)
        self.assertEqual(first_ir, second_ir)
        self.assertEqual(first_ir["semantic_sha256"], semantic_hash(first_ir))

    def test_unknown_reference_is_rejected(self) -> None:
        result = validate_source(
            """morphoia 0.1;
            model Broken [profile = "P1"] {
              parameter width: length = 10 mm;
              feature body: extrude { profile = missing.profile; distance = width; }
            }
            """
        )
        self.assertFalse(result.ok)
        self.assertIn("MORPH-E102", {item.code for item in result.diagnostics})

    def test_dimension_mismatch_is_rejected(self) -> None:
        result = validate_source(
            """morphoia 0.1;
            model Broken [profile = "P1"] {
              parameter width: length = 10 deg;
            }
            """
        )
        self.assertFalse(result.ok)
        self.assertIn("MORPH-E110", {item.code for item in result.diagnostics})

    def test_reference_requires_explicit_uniqueness(self) -> None:
        result = validate_source(
            """morphoia 0.1;
            model Broken [profile = "P1"] {
              parameter width: length = 10 mm;
              sketch base on world.xy { profile p = rectangle(width, width); }
              feature body: extrude { profile = base.p; distance = width; }
              reference cap: face = select(body.faces, role = "cap.end", normal = world.z);
            }
            """
        )
        self.assertFalse(result.ok)
        self.assertIn("MORPH-E131", {item.code for item in result.diagnostics})


if __name__ == "__main__":
    unittest.main()
