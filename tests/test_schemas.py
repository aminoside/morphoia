from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from morphoia.compiler import compile_document
from morphoia.losses import (
    LossCategory,
    LossRecord,
    LossRegister,
    LossSeverity,
)
from morphoia.validator import validate_file

ROOT = Path(__file__).resolve().parents[1]


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


class SchemaTests(unittest.TestCase):
    def test_all_schemas_are_valid_draft_2020_12(self) -> None:
        for name in (
            "morphoia-ir-0.1.schema.json",
            "morphoia-loss-register-0.1.schema.json",
            "morphoia-backend-manifest-0.1.schema.json",
        ):
            with self.subTest(name=name):
                Draft202012Validator.check_schema(load_schema(name))

    def test_compiled_example_matches_ir_schema(self) -> None:
        result = validate_file(ROOT / "examples" / "mounting_plate.morph")
        self.assertTrue(result.ok)
        assert result.document is not None
        Draft202012Validator(load_schema("morphoia-ir-0.1.schema.json")).validate(
            compile_document(result.document)
        )

    def test_loss_register_matches_its_schema(self) -> None:
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
                    "construction history is not representable in glTF",
                    source_capability="parametric_history",
                    target_capability=None,
                    mitigation="retain the canonical graph beside the derived view",
                ),
            ),
        )
        Draft202012Validator(load_schema("morphoia-loss-register-0.1.schema.json")).validate(
            register.to_dict()
        )


if __name__ == "__main__":
    unittest.main()
