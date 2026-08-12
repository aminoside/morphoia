from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

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


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict:
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
    )
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def load_schema(name: str) -> dict:
    return load_json(ROOT / "schemas" / name)


class SchemaTests(unittest.TestCase):
    def test_schema_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory(prefix="morphoia-schema-") as directory:
            schema = Path(directory) / "duplicate.schema.json"
            schema.write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema",'
                '"type":"object","type":"array"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_json(schema)

    def test_all_schemas_are_valid_draft_2020_12(self) -> None:
        for name in (
            "morphoia-ir-0.1.schema.json",
            "morphoia-loss-register-0.1.schema.json",
            "morphoia-backend-manifest-0.1.schema.json",
            "morphoia-salome-protocol-0.1.schema.json",
            "../spec/requirements/requirements-catalog.schema.json",
            "../spec/requirements/requirements-tracking.schema.json",
            "../spec/evidence/e2-salome-protocol-artifact-manifest.schema.json",
            "../spec/evidence/e2-salome-protocol-traceability.schema.json",
        ):
            with self.subTest(name=name):
                Draft202012Validator.check_schema(load_schema(name))

    def test_engine_requirements_match_their_schemas(self) -> None:
        requirements_root = ROOT / "spec" / "requirements"
        for instance_name, schema_name in (
            ("requirements.yaml", "requirements-catalog.schema.json"),
            ("requirements-tracking.yaml", "requirements-tracking.schema.json"),
        ):
            with self.subTest(instance=instance_name):
                instance = json.loads(
                    (requirements_root / instance_name).read_text(encoding="utf-8")
                )
                schema = load_json(requirements_root / schema_name)
                Draft202012Validator(schema).validate(instance)

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
