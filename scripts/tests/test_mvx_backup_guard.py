from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "mvx_backup_guard.py"
SPEC = importlib.util.spec_from_file_location("mvx_backup_guard", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def _document(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixture() -> tuple[bytes, dict[str, object], bytes, dict[str, object], dict[str, object]]:
    artifacts = {
        "artifact-id": (b"artifact\n", "artifact.json"),
        "latest-evidence-id": (b"latest evidence\n", None),
        "revision-evidence-id": (b"revision evidence\n", None),
    }
    checkpoint: dict[str, object] = {
        "schema": "MORPHOIA-MVX-DRIVE-CHECKPOINT",
        "schema_version": "2.0.0",
        "checkpoint_id": "cp-test-v3",
        "state": "ARTIFACTS_VERIFIED",
        "publication_model": guard.APPEND_ONLY_MODEL,
        "predecessor_checkpoint_id": "cp-test-v2",
        "predecessor_evidence": {
            "exact_latest_snapshot": {
                "drive_file_id": "latest-evidence-id",
                "bytes": len(artifacts["latest-evidence-id"][0]),
                "sha256": _sha(artifacts["latest-evidence-id"][0]),
                "download_verified": True,
            },
            "revision_evidence": {
                "drive_file_id": "revision-evidence-id",
                "bytes": len(artifacts["revision-evidence-id"][0]),
                "sha256": _sha(artifacts["revision-evidence-id"][0]),
                "download_verified": True,
            },
        },
        "git": {
            "commit_sha": "1" * 40,
            "tree_sha": "2" * 40,
        },
        "protocol": {"root_sha256": "3" * 64},
        "p2a": {
            "scope_commitment_sha256": "4" * 64,
            "public_summary_sha256": "5" * 64,
        },
        "drive": {
            "registry_folder_id": "registry-folder",
            "files": [
                {
                    "drive_file_id": "artifact-id",
                    "name": artifacts["artifact-id"][1],
                    "bytes": len(artifacts["artifact-id"][0]),
                    "sha256": _sha(artifacts["artifact-id"][0]),
                    "download_verified": True,
                }
            ],
        },
    }
    checkpoint_bytes = _document(checkpoint)
    artifact_set = [
        {"drive_file_id": file_id, "sha256": _sha(value[0])} for file_id, value in artifacts.items()
    ]
    completed: dict[str, object] = {
        "schema": "MORPHOIA-MVX-DRIVE-CHECKPOINT-COMPLETED",
        "schema_version": "2.0.0",
        "checkpoint_id": "cp-test-v3",
        "state": "COMPLETED",
        "publication_model": guard.APPEND_ONLY_MODEL,
        "registry_folder_id": "registry-folder",
        "predecessor_checkpoint_id": "cp-test-v2",
        "checkpoint_registry": {
            "drive_file_id": "checkpoint-drive-id",
            "bytes": len(checkpoint_bytes),
            "sha256": _sha(checkpoint_bytes),
            "download_verified": True,
        },
        "artifact_set": artifact_set,
        "git_commit_sha": "1" * 40,
        "git_tree_sha": "2" * 40,
        "protocol_root_sha256": "3" * 64,
        "p2a_scope_commitment_sha256": "4" * 64,
        "p2a_public_summary_sha256": "5" * 64,
    }
    completed_bytes = _document(completed)
    latest: dict[str, object] = {
        "schema": "MORPHOIA-MVX-DRIVE-LATEST",
        "schema_version": "2.0.0",
        "checkpoint_id": "cp-test-v3",
        "state": "COMPLETED",
        "publication_model": guard.LATEST_MODEL,
        "predecessor_checkpoint_id": "cp-test-v2",
        "registry_folder_id": "registry-folder",
        "checkpoint_registry": copy.deepcopy(completed["checkpoint_registry"]),
        "terminal_marker": {
            "drive_file_id": "completed-drive-id",
            "bytes": len(completed_bytes),
            "sha256": _sha(completed_bytes),
            "download_verified": True,
        },
        "git": {"commit_sha": "1" * 40, "tree_sha": "2" * 40},
        "protocol": {"root_sha256": "3" * 64},
        "p2a": {
            "scope_commitment_sha256": "4" * 64,
            "public_summary_sha256": "5" * 64,
            "second_invocation_action": "SKIP",
        },
    }
    return checkpoint_bytes, checkpoint, completed_bytes, completed, latest


class BackupGuardTests(unittest.TestCase):
    def test_exact_chain_authorises_skip(self) -> None:
        checkpoint_bytes, checkpoint, completed_bytes, completed, latest = _fixture()
        result = guard.verify_chain(
            checkpoint_bytes=checkpoint_bytes,
            checkpoint=checkpoint,
            completed_bytes=completed_bytes,
            completed=completed,
            latest=latest,
            completed_drive_id="completed-drive-id",
        )
        self.assertEqual(result["action"], "SKIP")
        self.assertEqual(result["artifact_count"], 3)

    def test_stale_or_tampered_checkpoint_fails_closed(self) -> None:
        checkpoint_bytes, checkpoint, completed_bytes, completed, latest = _fixture()
        checkpoint_bytes += b" "
        with self.assertRaisesRegex(guard.GuardError, "COMPLETED_CHECKPOINT_BYTES_MISMATCH"):
            guard.verify_chain(
                checkpoint_bytes=checkpoint_bytes,
                checkpoint=checkpoint,
                completed_bytes=completed_bytes,
                completed=completed,
                latest=latest,
            )

    def test_latest_must_point_to_terminal_bytes_and_id(self) -> None:
        checkpoint_bytes, checkpoint, completed_bytes, completed, latest = _fixture()
        latest["terminal_marker"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(guard.GuardError, "LATEST_COMPLETED_BYTES_MISMATCH"):
            guard.verify_chain(
                checkpoint_bytes=checkpoint_bytes,
                checkpoint=checkpoint,
                completed_bytes=completed_bytes,
                completed=completed,
                latest=latest,
            )

        _, _, _, _, latest = _fixture()
        with self.assertRaisesRegex(guard.GuardError, "LATEST_COMPLETED_DRIVE_ID_MISMATCH"):
            guard.verify_chain(
                checkpoint_bytes=checkpoint_bytes,
                checkpoint=checkpoint,
                completed_bytes=completed_bytes,
                completed=completed,
                latest=latest,
                completed_drive_id="wrong-id",
            )

    def test_completed_artifact_ids_are_unique_and_exact(self) -> None:
        checkpoint_bytes, checkpoint, completed_bytes, completed, latest = _fixture()
        completed["artifact_set"].append(copy.deepcopy(completed["artifact_set"][0]))
        with self.assertRaisesRegex(guard.GuardError, "COMPLETED_ARTIFACT_NOT_UNIQUE"):
            guard.verify_chain(
                checkpoint_bytes=checkpoint_bytes,
                checkpoint=checkpoint,
                completed_bytes=completed_bytes,
                completed=completed,
                latest=latest,
            )

    def test_materialised_artifacts_are_rehashed(self) -> None:
        _, checkpoint, _, _, _ = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "artifact-id": root / "artifact.json",
                "latest-evidence-id": root / "latest.json",
                "revision-evidence-id": root / "revision.json",
            }
            payloads = {
                "artifact-id": b"artifact\n",
                "latest-evidence-id": b"latest evidence\n",
                "revision-evidence-id": b"revision evidence\n",
            }
            for file_id, path in paths.items():
                path.write_bytes(payloads[file_id])
            guard.verify_materialised_artifacts(checkpoint, paths)
            paths["artifact-id"].write_bytes(b"tampered\n")
            with self.assertRaisesRegex(guard.GuardError, "MATERIALISED_ARTIFACT_MISMATCH"):
                guard.verify_materialised_artifacts(checkpoint, paths)

    def test_symlinked_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text("{}\n")
            link = root / "link.json"
            os.symlink(target, link)
            with self.assertRaisesRegex(guard.GuardError, "INPUT_NOT_REGULAR_FILE"):
                guard._json_bytes(link)

    def test_cli_failure_is_path_free(self) -> None:
        missing = "/private/uid/that-must-not-leak.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = guard.main(
                [
                    "--checkpoint",
                    missing,
                    "--completed",
                    missing,
                    "--latest",
                    missing,
                ]
            )
        self.assertEqual(status, 2)
        self.assertNotIn(missing, output.getvalue())
        self.assertIn('"action":"BLOCKED"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
