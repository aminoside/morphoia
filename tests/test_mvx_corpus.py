from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from morphoia.mvx.cohort import eligible_records_sha256
from morphoia.mvx.corpus import (
    FileRecord,
    build_object_candidates,
    detect_objaverse_duplicates,
    identify_direct_object_format,
    inventory_tree,
    is_test_path,
    parse_manifest,
    reconcile_inventories,
    render_csv,
    render_jsonl,
    write_csv,
    write_jsonl,
)
from morphoia.mvx.corpus.registry import canonicalise_corpus_registry_record

UID_A = "a" * 32
UID_B = "b" * 32
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORPUS_SCHEMA_PATH = REPOSITORY_ROOT / "schemas/mvx/0.2.1/corpus-registry.schema.json"
CORPUS_EXAMPLE_PATH = (
    REPOSITORY_ROOT / "docs/mvx/validation/p0/schema-examples/corpus-registry.valid.json"
)


def _corpus_schema_validator() -> Draft202012Validator:
    schema = json.loads(CORPUS_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _corpus_example() -> dict[str, object]:
    return json.loads(CORPUS_EXAMPLE_PATH.read_text(encoding="utf-8"))


class P2aRegistryToG1ContractTests(unittest.TestCase):
    def test_schema_valid_p2a_record_is_accepted_by_g1_commitment(self) -> None:
        record = _corpus_example()
        _corpus_schema_validator().validate(record)

        digest = eligible_records_sha256([record])

        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_schema_valid_fixture_exception_is_accepted_by_g1_commitment(self) -> None:
        fixture = _corpus_example()
        fixture.update(
            {
                "object_id": "FIXTURE-C0-001",
                "lineage_id": "FIXTURE-LIN-C0-001",
                "leakage_group_id": "FIXTURE-GRP-C0-001",
                "dataset": "fixtures_C0_C9",
                "source_uid": "fixture:C0:001",
                "source_uri": "morphoia-fixture://C0/001",
                "creator_group": "morphoia-analytic-fixtures",
                "category": "C0",
                "selection_stratum": "fixtures_C0_C9",
                "source_format": "analytic_fixture",
                "licence": "MORPHOIA-SYNTHETIC-FIXTURE",
                "licence_source": None,
                "licence_spdx": None,
                "licence_status": "FIXTURE_GENERATED",
                "fixture_exception": {
                    "kind": "SYNTHETIC_PROTOCOL_FIXTURE",
                    "case_id": "C0",
                    "generator_id": "morphoia-analytic-fixtures",
                    "generator_version": "0.1.0",
                },
            }
        )
        _corpus_schema_validator().validate(fixture)

        digest = eligible_records_sha256([fixture])

        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_legacy_import_aliases_emit_one_canonical_outcome_free_record(self) -> None:
        canonical = _corpus_example()
        legacy = copy.deepcopy(canonical)
        legacy["sha256"] = legacy.pop("source_sha256")
        legacy["bytes"] = legacy.pop("source_size_bytes")
        legacy["format"] = legacy.pop("source_format")
        legacy["license"] = legacy.pop("licence")
        legacy["license_status"] = legacy.pop("licence_status")
        legacy["stratum"] = legacy.pop("selection_stratum")
        legacy["terminal_status"] = "FAIL"
        legacy["hd95"] = 999.0

        imported = canonicalise_corpus_registry_record(legacy)

        for alias in ("sha256", "bytes", "format", "license", "license_status", "stratum"):
            self.assertNotIn(alias, imported)
        self.assertNotIn("terminal_status", imported)
        self.assertNotIn("hd95", imported)
        self.assertEqual(imported, canonical)
        self.assertEqual(
            eligible_records_sha256([legacy]),
            eligible_records_sha256([canonical]),
        )

    def test_conflicting_legacy_alias_fails_closed(self) -> None:
        record = _corpus_example()
        record["sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "conflicting corpus registry aliases"):
            canonicalise_corpus_registry_record(record)


class ManifestParsingTests(unittest.TestCase):
    def test_csv_aliases_and_drive_metadata_are_normalised(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stale.csv"
            path.write_text(
                "Drive ID,Folder Path,File Name,Size,md5Checksum,Collection,Objaverse ID,Note\n"
                f'drive-1,Objaverse/chairs,{UID_A}.GLB,"1,024",'
                f"{'f' * 32},objaverse,{UID_A},old\n",
                encoding="utf-8",
            )
            records = parse_manifest(path)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.path, f"Objaverse/chairs/{UID_A}.GLB")
        self.assertEqual(record.file_id, "drive-1")
        self.assertEqual(record.size_bytes, 1024)
        self.assertEqual(record.checksum_algorithm, "md5")
        self.assertEqual(record.objaverse_uid, UID_A)
        self.assertEqual(dict(record.metadata), {"Note": "old"})

    def test_jsonl_is_parsed_and_sorted_independently_of_row_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.jsonl"
            second = Path(temporary) / "second.jsonl"
            rows = [
                {"path": "z/model.stl", "bytes": 4},
                {"path": "a/model.obj", "bytes": 3, "custom": {"b": 2, "a": 1}},
            ]
            first.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            second.write_text(
                "\n".join(json.dumps(row) for row in reversed(rows)), encoding="utf-8"
            )
            parsed_first = parse_manifest(first)
            parsed_second = parse_manifest(second)

        self.assertEqual(parsed_first, parsed_second)
        self.assertEqual([record.path for record in parsed_first], ["a/model.obj", "z/model.stl"])
        self.assertEqual(dict(parsed_first[0].metadata)["custom"], '{"a":1,"b":2}')

    def test_bad_jsonl_row_reports_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.jsonl"
            path.write_text('{"path":"ok.glb"}\n[]\n', encoding="utf-8")
            with self.assertRaisesRegex(TypeError, r":2: JSONL row must be an object"):
                parse_manifest(path)

    def test_live_inventory_has_relative_paths_sizes_and_optional_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "nested" / "shape.obj").write_bytes(b"mesh")
            records = inventory_tree(root, dataset="custom", compute_sha256=True)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].path, "nested/shape.obj")
        self.assertEqual(records[0].size_bytes, 4)
        self.assertEqual(records[0].checksum_algorithm, "sha256")
        self.assertEqual(len(records[0].checksum or ""), 64)
        self.assertEqual(records[0].origin, "live")

    def test_objaverse_dataset_and_uid_are_inferred_from_live_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Objaverse").mkdir()
            (root / "Objaverse" / f"{UID_A}.glb").write_bytes(b"glb")
            records = inventory_tree(root)

        self.assertEqual(records[0].dataset, "objaverse")
        self.assertEqual(records[0].objaverse_uid, UID_A)

        mapped = FileRecord.from_mapping(
            {"path": "asset.glb", "collection": "Objaverse-XL", "uid": UID_B}
        )
        self.assertEqual(mapped.objaverse_uid, UID_B)


class CandidateConstructionTests(unittest.TestCase):
    def test_direct_formats_are_identified_case_insensitively(self) -> None:
        self.assertEqual(identify_direct_object_format("shape.STEP"), "step")
        self.assertEqual(identify_direct_object_format("scan.NII.GZ"), "nifti")
        self.assertEqual(identify_direct_object_format("mesh.glb"), "glb")
        self.assertIsNone(identify_direct_object_format("mesh.mtl"))
        self.assertIsNone(identify_direct_object_format("objects.zip"))

    def test_test_files_are_excluded_without_dropping_dataset_test_split(self) -> None:
        self.assertTrue(is_test_path("tests/shape.glb"))
        self.assertTrue(is_test_path("objects/test_cube.obj"))
        self.assertFalse(is_test_path("modelnet40/test/chair_001.obj"))
        self.assertFalse(is_test_path("objects/contest_winner.obj"))

        result = build_object_candidates(
            [
                FileRecord("tests/debug.glb", origin="live"),
                FileRecord("modelnet40/test/chair_001.obj", origin="live"),
            ]
        )
        self.assertEqual([candidate.logical_name for candidate in result.candidates], ["chair_001"])
        self.assertEqual([record.path for record in result.excluded_files], ["tests/debug.glb"])

    def test_multipart_archives_form_bundles_and_fragments_never_become_objects(self) -> None:
        rows = [
            FileRecord("archives/set.z02", origin="live"),
            FileRecord("archives/set.zip", origin="live"),
            FileRecord("archives/set.z01", origin="live"),
            FileRecord("archives/other.7z.002", origin="live"),
            FileRecord("archives/other.7z.001", origin="live"),
            FileRecord("objects/chair.glb", origin="live"),
            FileRecord("objects/chair.bin", origin="live"),
        ]
        result = build_object_candidates(reversed(rows))

        self.assertEqual(len(rows), 7)
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(len(result.direct_candidates), 1)
        self.assertEqual(len(result.archive_bundles), 2)
        statuses = {
            candidate.package_key: candidate.bundle_status for candidate in result.archive_bundles
        }
        self.assertEqual(statuses["archives/set.zip"], "CONTIGUOUS_WITH_TERMINAL")
        self.assertEqual(statuses["archives/other.7z"], "CONTIGUOUS_SEQUENCE")
        self.assertTrue(all(not bundle.ready_for_lineage for bundle in result.archive_bundles))
        self.assertEqual([record.path for record in result.ignored_files], ["objects/chair.bin"])

    def test_gapped_and_missing_terminal_bundles_are_explicit(self) -> None:
        result = build_object_candidates(
            [
                FileRecord("broken/data.z01", origin="live"),
                FileRecord("broken/data.z03", origin="live"),
                FileRecord("missing/end.r00", origin="live"),
                FileRecord("missing/end.r01", origin="live"),
            ]
        )
        by_key = {candidate.package_key: candidate for candidate in result.archive_bundles}
        self.assertEqual(by_key["broken/data.zip"].bundle_status, "GAPPED_SEQUENCE")
        self.assertIn("missing_fragment_index", by_key["broken/data.zip"].issues)
        self.assertEqual(by_key["missing/end.rar"].bundle_status, "MISSING_TERMINAL")
        self.assertIn("missing_terminal_archive", by_key["missing/end.rar"].issues)

    def test_duplicate_file_rows_produce_one_candidate_not_two_objects(self) -> None:
        result = build_object_candidates(
            [
                FileRecord("objects/same.glb", origin="manifest", file_id="same-id"),
                FileRecord("objects/same.glb", origin="manifest", file_id="same-id"),
            ]
        )
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(len(result.candidates[0].files), 2)
        self.assertIn("duplicate_file_row", result.candidates[0].issues)

    def test_same_drive_name_with_distinct_ids_remains_two_candidates(self) -> None:
        result = build_object_candidates(
            [
                FileRecord("objects/same.glb", origin="live", file_id="drive-a"),
                FileRecord("objects/same.glb", origin="live", file_id="drive-b"),
            ]
        )
        self.assertEqual(len(result.direct_candidates), 2)
        self.assertEqual(len({item.candidate_id for item in result.direct_candidates}), 2)

    def test_objaverse_duplicate_uid_and_normalised_name_are_reported(self) -> None:
        rows = [
            FileRecord(
                "objaverse/a.glb",
                origin="live",
                dataset="Objaverse",
                objaverse_uid=UID_A,
                object_name="Blue Chair",
            ),
            FileRecord(
                "objaverse/b.glb",
                origin="live",
                dataset="objaverse",
                objaverse_uid=UID_A.upper(),
                object_name="blue_chair",
            ),
            FileRecord(
                "objaverse/c.glb",
                origin="live",
                dataset="objaverse",
                objaverse_uid=UID_B,
                object_name="Lamp",
            ),
            FileRecord(
                "other/d.glb",
                origin="live",
                dataset="other",
                objaverse_uid=UID_A,
                object_name="Blue Chair",
            ),
        ]
        candidates = build_object_candidates(rows).candidates
        duplicates = detect_objaverse_duplicates(candidates)

        self.assertEqual(
            [group.field for group in duplicates], ["normalised_name", "objaverse_uid"]
        )
        self.assertEqual({group.value for group in duplicates}, {"blue chair", UID_A})
        self.assertTrue(all(len(group.candidate_ids) == 2 for group in duplicates))


class ReconciliationTests(unittest.TestCase):
    def test_live_inventory_is_authoritative_and_stale_rows_do_not_become_candidates(self) -> None:
        manifest = [
            FileRecord("old/stale.glb", file_id="gone", size_bytes=10),
            FileRecord("old/renamed.glb", file_id="same", size_bytes=20),
            FileRecord("same/changed.obj", file_id="changed", size_bytes=30),
        ]
        live = [
            FileRecord("new/renamed.glb", origin="live", file_id="same", size_bytes=20),
            FileRecord("same/changed.obj", origin="live", file_id="changed", size_bytes=31),
            FileRecord("new/only-live.ply", origin="live", file_id="new", size_bytes=40),
        ]
        result = reconcile_inventories(reversed(manifest), reversed(live))

        self.assertEqual(
            result.counts,
            {"CHANGED": 2, "MISSING_FROM_LIVE": 1, "NEW_IN_LIVE": 1},
        )
        changed = {
            entry.live_record.file_id: entry.changed_fields
            for entry in result.entries
            if entry.status == "CHANGED" and entry.live_record
        }
        self.assertEqual(changed["same"], ("path",))
        self.assertEqual(changed["changed"], ("size_bytes",))
        candidates = result.build_live_candidates()
        self.assertEqual(
            {candidate.package_key for candidate in candidates.direct_candidates},
            {"new/only-live.ply", "new/renamed.glb", "same/changed.obj"},
        )
        self.assertNotIn(
            "old/stale.glb", {candidate.package_key for candidate in candidates.candidates}
        )

    def test_unique_checksum_matches_a_move_but_ambiguous_checksum_is_not_guessed(self) -> None:
        unique_hash = "1" * 64
        duplicate_hash = "2" * 64
        manifest = [
            FileRecord("old/a.glb", checksum=unique_hash, checksum_algorithm="sha256"),
            FileRecord("old/b.glb", checksum=duplicate_hash, checksum_algorithm="sha256"),
            FileRecord("old/c.glb", checksum=duplicate_hash, checksum_algorithm="sha256"),
        ]
        live = [
            FileRecord(
                "new/a.glb", origin="live", checksum=unique_hash, checksum_algorithm="sha256"
            ),
            FileRecord(
                "new/b.glb", origin="live", checksum=duplicate_hash, checksum_algorithm="sha256"
            ),
        ]
        result = reconcile_inventories(manifest, live)

        checksum_matches = [entry for entry in result.entries if entry.match_method == "checksum"]
        self.assertEqual(len(checksum_matches), 1)
        self.assertEqual(checksum_matches[0].changed_fields, ("path",))
        self.assertIn(f"ambiguous_checksum:sha256:{duplicate_hash}", result.issues)
        self.assertEqual(result.counts["MISSING_FROM_LIVE"], 2)
        self.assertEqual(result.counts["NEW_IN_LIVE"], 1)

    def test_content_and_metadata_changes_are_reported(self) -> None:
        manifest = FileRecord(
            "same.glb",
            checksum="1" * 64,
            checksum_algorithm="sha256",
            mime_type="model/gltf-binary",
            modified_time="old",
        )
        live = FileRecord(
            "same.glb",
            origin="live",
            checksum="2" * 64,
            checksum_algorithm="sha256",
            mime_type="application/octet-stream",
            modified_time="new",
        )
        entry = reconcile_inventories([manifest], [live]).entries[0]
        self.assertEqual(entry.status, "CHANGED")
        self.assertEqual(entry.changed_fields, ("checksum", "mime_type", "modified_time"))


class DeterministicEmissionTests(unittest.TestCase):
    def test_jsonl_and_csv_are_input_order_independent(self) -> None:
        records = [
            FileRecord("z.glb", origin="live", size_bytes=2),
            FileRecord("a.obj", origin="live", size_bytes=1),
        ]
        self.assertEqual(render_jsonl(records), render_jsonl(reversed(records)))
        self.assertEqual(render_csv(records), render_csv(reversed(records)))

        json_rows = [json.loads(line) for line in render_jsonl(records).splitlines()]
        self.assertEqual([row["path"] for row in json_rows], ["a.obj", "z.glb"])
        csv_rows = list(csv.DictReader(render_csv(records).splitlines()))
        self.assertEqual([row["path"] for row in csv_rows], ["a.obj", "z.glb"])

    def test_duplicate_identical_rows_are_serialisable(self) -> None:
        record = FileRecord("same.glb", origin="live", size_bytes=4)
        jsonl = render_jsonl([record, record])
        csv_text = render_csv([record, record])
        self.assertEqual(len(jsonl.splitlines()), 2)
        self.assertEqual(len(list(csv.DictReader(csv_text.splitlines()))), 2)

    def test_writers_emit_trailing_newline_and_stable_bytes(self) -> None:
        records = [FileRecord("object.glb", origin="live", size_bytes=4)]
        with tempfile.TemporaryDirectory() as temporary:
            jsonl_path = write_jsonl(records, Path(temporary) / "nested" / "registry.jsonl")
            csv_path = write_csv(records, Path(temporary) / "nested" / "registry.csv")
            first_jsonl = jsonl_path.read_bytes()
            first_csv = csv_path.read_bytes()
            write_jsonl(reversed(records), jsonl_path)
            write_csv(reversed(records), csv_path)

            self.assertEqual(first_jsonl, jsonl_path.read_bytes())
            self.assertEqual(first_csv, csv_path.read_bytes())
            self.assertTrue(first_jsonl.endswith(b"\n"))
            self.assertTrue(first_csv.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
