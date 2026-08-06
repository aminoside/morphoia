from __future__ import annotations

import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from morphoia.mvx.checkpoint import (
    CheckpointValidationError,
    ResumeAction,
    WorkIdentity,
    assess_resume,
    checkpoint_sha256,
    claim_open_once,
    derive_work_id,
    execution_plan_sha256,
    hash_artifacts,
    load_checkpoint,
    make_execution_plan,
    make_stage,
    make_stage_checkpoint,
    open_once_claim_path,
    validate_execution_plan,
    validate_stage_checkpoint,
    write_checkpoint,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "mvx" / "validation" / "p0" / "schema-examples"


def identity(
    stage_id: str,
    *,
    phase_id: str = "P3",
    split: str = "development",
    open_once: bool = False,
    source_sha256: str = "c" * 64,
) -> WorkIdentity:
    return WorkIdentity(
        protocol_root_sha256="a" * 64,
        split_sha256="b" * 64,
        source_sha256=source_sha256,
        lineage_id="LIN-001",
        profile_sha256="d" * 64,
        config_sha256="e" * 64,
        code_sha256="f" * 64,
        environment_sha256="1" * 64,
        phase_id=phase_id,
        stage_id=stage_id,
        split=split,
        open_once=open_once,
    )


def one_stage_plan(*, split: str = "development", open_once: bool = False) -> tuple[dict, str]:
    item = identity("encode", split=split, open_once=open_once)
    stage = make_stage(item, required_artifacts=("run_manifest", "mvx_package"))
    return make_execution_plan("PLAN-ONE", (stage,)), item.work_id


class MvxCheckpointTests(unittest.TestCase):
    def test_work_id_binds_every_required_identity_component(self) -> None:
        baseline = identity("encode")
        baseline_dict = baseline.as_dict()
        baseline_id = baseline.work_id
        replacements = {
            "protocol_root_sha256": "2" * 64,
            "split_sha256": "3" * 64,
            "source_sha256": "4" * 64,
            "lineage_id": "LIN-002",
            "profile_sha256": "5" * 64,
            "config_sha256": "6" * 64,
            "code_sha256": "7" * 64,
            "environment_sha256": "8" * 64,
            "phase_id": "P4",
            "stage_id": "decode",
            "split": "calibration",
            "open_once": True,
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                changed = dict(baseline_dict)
                changed[field] = replacement
                self.assertNotEqual(derive_work_id(changed), baseline_id)

        reversed_mapping = dict(reversed(list(baseline_dict.items())))
        self.assertEqual(derive_work_id(reversed_mapping), baseline_id)

    def test_plan_rejects_unbound_work_id_and_forward_dependency(self) -> None:
        first = make_stage(identity("encode"), required_artifacts=("run_manifest",))
        second = make_stage(
            identity("decode"),
            required_artifacts=("run_manifest",),
            depends_on_work_ids=(first["work_id"],),
        )
        plan = make_execution_plan("CHAIN", (first, second))
        self.assertEqual(validate_execution_plan(plan), plan)

        wrong_id = copy.deepcopy(plan)
        wrong_id["stages"][0]["work_id"] = "0" * 64
        with self.assertRaisesRegex(CheckpointValidationError, "does not bind"):
            validate_execution_plan(wrong_id)

        forward = copy.deepcopy(plan)
        forward["stages"][0]["depends_on_work_ids"] = [second["work_id"]]
        with self.assertRaisesRegex(CheckpointValidationError, "forward, or cyclic"):
            validate_execution_plan(forward)

    def test_terminal_checkpoint_skips_only_with_matching_artifacts(self) -> None:
        plan, work_id = one_stage_plan()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_manifest = root / "run.json"
            package = root / "object.mvx"
            run_manifest.write_text('{"terminal":true}\n', encoding="utf-8")
            package.write_bytes(b"mvx-package")
            paths = {"run_manifest": run_manifest, "mvx_package": package}
            checkpoint = make_stage_checkpoint(
                plan,
                work_id,
                state="TERMINAL",
                terminal_status="PASS",
                error_code="MVX-OK",
                artifact_hashes=hash_artifacts(paths),
            )
            decision = assess_resume(plan, work_id, checkpoint=checkpoint, artifact_paths=paths)
            self.assertEqual(decision.action, ResumeAction.SKIP)

            package.write_bytes(b"tampered")
            decision = assess_resume(plan, work_id, checkpoint=checkpoint, artifact_paths=paths)
            self.assertEqual(decision.action, ResumeAction.RETRY)

            package.unlink()
            decision = assess_resume(plan, work_id, checkpoint=checkpoint, artifact_paths=paths)
            self.assertEqual(decision.action, ResumeAction.RETRY)

    def test_pending_runs_and_partial_or_interrupted_ordinary_work_retries(self) -> None:
        plan, work_id = one_stage_plan()
        pending = make_stage_checkpoint(plan, work_id, state="PENDING")
        self.assertEqual(assess_resume(plan, work_id, checkpoint=pending).action, ResumeAction.RUN)

        partial = make_stage_checkpoint(
            plan,
            work_id,
            state="PARTIAL",
            error_code="WORKER_INTERRUPTED",
            artifact_hashes={"run_manifest": "2" * 64},
        )
        self.assertEqual(
            assess_resume(plan, work_id, checkpoint=partial).action, ResumeAction.RETRY
        )

        interrupted = make_stage_checkpoint(
            plan,
            work_id,
            state="INTERRUPTED",
            error_code="HOST_LOST",
            interruption_reason="workspace reset",
        )
        self.assertEqual(
            assess_resume(plan, work_id, checkpoint=interrupted).action,
            ResumeAction.RETRY,
        )

    def test_blind_open_once_interruption_fails_closed_and_never_auto_reruns(self) -> None:
        plan, work_id = one_stage_plan(split="blind", open_once=True)
        self.assertEqual(assess_resume(plan, work_id).action, ResumeAction.BLOCKED)

        pending = make_stage_checkpoint(plan, work_id, state="PENDING")
        self.assertEqual(
            assess_resume(plan, work_id, checkpoint=pending).action,
            ResumeAction.BLOCKED,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending_path = root / "pending.json"
            claim_directory = root / "claims"
            write_checkpoint(pending_path, pending)
            self.assertEqual(
                assess_resume(
                    plan,
                    work_id,
                    checkpoint=pending,
                    open_once_claim_directory=claim_directory,
                ).action,
                ResumeAction.BLOCKED,
            )
            running = claim_open_once(
                plan,
                work_id,
                pending_checkpoint_path=pending_path,
                claim_directory=claim_directory,
            )
            claim_path = open_once_claim_path(claim_directory, work_id)
            self.assertEqual(running["state"], "RUNNING")
            self.assertEqual(running["previous_checkpoint_sha256"], checkpoint_sha256(pending))
            self.assertEqual(claim_path.stat().st_mode & 0o222, 0)

            stale = assess_resume(
                plan,
                work_id,
                checkpoint=pending,
                open_once_claim_directory=claim_directory,
            )
            self.assertEqual(stale.action, ResumeAction.FAIL_CLOSED)
            self.assertIn("stale PENDING", stale.reason)
            self.assertEqual(
                assess_resume(
                    plan,
                    work_id,
                    checkpoint=running,
                    open_once_claim_directory=claim_directory,
                ).action,
                ResumeAction.FAIL_CLOSED,
            )
            with self.assertRaisesRegex(FileExistsError, "consumed"):
                claim_open_once(
                    plan,
                    work_id,
                    pending_checkpoint_path=pending_path,
                    claim_directory=claim_directory,
                )

        with self.assertRaisesRegex(CheckpointValidationError, "attempt 1"):
            make_stage_checkpoint(plan, work_id, state="PENDING", attempt=2)

    def test_blind_terminal_checkpoint_with_missing_artifact_fails_closed(self) -> None:
        plan, work_id = one_stage_plan(split="blind", open_once=True)
        pending = make_stage_checkpoint(plan, work_id, state="PENDING")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending_path = root / "pending.json"
            claim_directory = root / "claims"
            write_checkpoint(pending_path, pending)
            running = claim_open_once(
                plan,
                work_id,
                pending_checkpoint_path=pending_path,
                claim_directory=claim_directory,
            )
            checkpoint = make_stage_checkpoint(
                plan,
                work_id,
                state="TERMINAL",
                terminal_status="PASS",
                error_code="MVX-OK",
                artifact_hashes={"run_manifest": "2" * 64, "mvx_package": "3" * 64},
                previous_checkpoint=running,
            )
            self.assertEqual(
                assess_resume(
                    plan,
                    work_id,
                    checkpoint=checkpoint,
                    artifact_paths={},
                    open_once_claim_directory=claim_directory,
                ).action,
                ResumeAction.FAIL_CLOSED,
            )

    def test_blind_terminal_skip_requires_the_authoritative_claim_chain(self) -> None:
        plan, work_id = one_stage_plan(split="blind", open_once=True)
        pending = make_stage_checkpoint(plan, work_id, state="PENDING")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending_path = root / "pending.json"
            claim_directory = root / "claims"
            package = root / "object.mvx"
            run_manifest = root / "run.json"
            package.write_bytes(b"mvx")
            run_manifest.write_bytes(b"manifest")
            artifacts = {"run_manifest": run_manifest, "mvx_package": package}
            write_checkpoint(pending_path, pending)
            running = claim_open_once(
                plan,
                work_id,
                pending_checkpoint_path=pending_path,
                claim_directory=claim_directory,
            )
            terminal = make_stage_checkpoint(
                plan,
                work_id,
                state="TERMINAL",
                terminal_status="PASS",
                error_code="MVX-OK",
                artifact_hashes=hash_artifacts(artifacts),
                previous_checkpoint=running,
            )
            self.assertEqual(
                assess_resume(
                    plan,
                    work_id,
                    checkpoint=terminal,
                    artifact_paths=artifacts,
                    open_once_claim_directory=claim_directory,
                ).action,
                ResumeAction.SKIP,
            )

            forged = copy.deepcopy(terminal)
            forged["previous_checkpoint_sha256"] = "9" * 64
            self.assertEqual(
                assess_resume(
                    plan,
                    work_id,
                    checkpoint=forged,
                    artifact_paths=artifacts,
                    open_once_claim_directory=claim_directory,
                ).action,
                ResumeAction.FAIL_CLOSED,
            )

    def test_open_once_claim_is_atomic_across_competing_workers(self) -> None:
        plan, work_id = one_stage_plan(split="blind", open_once=True)
        pending = make_stage_checkpoint(plan, work_id, state="PENDING")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending_path = root / "pending.json"
            claim_directory = root / "claims"
            write_checkpoint(pending_path, pending)
            barrier = Barrier(2)

            def compete() -> str:
                barrier.wait()
                try:
                    claim_open_once(
                        plan,
                        work_id,
                        pending_checkpoint_path=pending_path,
                        claim_directory=claim_directory,
                    )
                except FileExistsError:
                    return "REJECTED"
                return "CLAIMED"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: compete(), range(2)))
            self.assertCountEqual(outcomes, ["CLAIMED", "REJECTED"])

    def test_checkpoint_and_claim_targets_reject_symbolic_links(self) -> None:
        plan, work_id = one_stage_plan(split="blind", open_once=True)
        pending = make_stage_checkpoint(plan, work_id, state="PENDING")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_pending = root / "real-pending.json"
            pending_link = root / "pending-link.json"
            write_checkpoint(real_pending, pending)
            pending_link.symlink_to(real_pending)
            with self.assertRaises(CheckpointValidationError):
                load_checkpoint(pending_link)
            with self.assertRaises(FileExistsError):
                write_checkpoint(pending_link, pending)

            claim_directory = root / "claims"
            claim_directory.mkdir()
            claim_path = open_once_claim_path(claim_directory, work_id)
            claim_path.symlink_to(real_pending)
            with self.assertRaises(FileExistsError):
                claim_open_once(
                    plan,
                    work_id,
                    pending_checkpoint_path=real_pending,
                    claim_directory=claim_directory,
                )
            decision = assess_resume(
                plan,
                work_id,
                checkpoint=pending,
                open_once_claim_directory=claim_directory,
            )
            self.assertEqual(decision.action, ResumeAction.FAIL_CLOSED)
            self.assertIn("not a regular file", decision.reason)

    def test_phase_chain_requires_verified_terminal_dependencies(self) -> None:
        first_identity = identity("encode")
        second_identity = identity("reconstruct", phase_id="P4")
        first = make_stage(first_identity, required_artifacts=("encoded",))
        second = make_stage(
            second_identity,
            required_artifacts=("reconstruction",),
            depends_on_work_ids=(first_identity.work_id,),
        )
        plan = make_execution_plan("CHAIN", (first, second))
        self.assertEqual(assess_resume(plan, second_identity.work_id).action, ResumeAction.BLOCKED)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            encoded = root / "encoded.mvx"
            reconstructed = root / "reconstructed.obj"
            encoded.write_bytes(b"encoded")
            reconstructed.write_bytes(b"reconstructed")
            first_paths = {"encoded": encoded}
            second_paths = {"reconstruction": reconstructed}
            first_checkpoint = make_stage_checkpoint(
                plan,
                first_identity.work_id,
                state="TERMINAL",
                terminal_status="PASS",
                error_code="MVX-OK",
                artifact_hashes=hash_artifacts(first_paths),
            )
            dependencies = {first_identity.work_id: first_checkpoint}
            dependency_paths = {first_identity.work_id: first_paths}
            self.assertEqual(
                assess_resume(
                    plan,
                    second_identity.work_id,
                    dependency_checkpoints=dependencies,
                    dependency_artifact_paths=dependency_paths,
                ).action,
                ResumeAction.RUN,
            )

            second_checkpoint = make_stage_checkpoint(
                plan,
                second_identity.work_id,
                state="TERMINAL",
                terminal_status="PASS",
                error_code="MVX-OK",
                artifact_hashes=hash_artifacts(second_paths),
                dependency_checkpoints=dependencies,
            )
            self.assertEqual(
                assess_resume(
                    plan,
                    second_identity.work_id,
                    checkpoint=second_checkpoint,
                    artifact_paths=second_paths,
                    dependency_checkpoints=dependencies,
                    dependency_artifact_paths=dependency_paths,
                ).action,
                ResumeAction.SKIP,
            )

            changed_dependency = copy.deepcopy(first_checkpoint)
            changed_dependency["error_code"] = "ALREADY_TERMINAL"
            self.assertNotEqual(
                checkpoint_sha256(first_checkpoint), checkpoint_sha256(changed_dependency)
            )
            self.assertEqual(
                assess_resume(
                    plan,
                    second_identity.work_id,
                    checkpoint=second_checkpoint,
                    artifact_paths=second_paths,
                    dependency_checkpoints={first_identity.work_id: changed_dependency},
                    dependency_artifact_paths=dependency_paths,
                ).action,
                ResumeAction.FAIL_CLOSED,
            )

    def test_checkpoint_files_are_immutable_and_idempotent(self) -> None:
        plan, work_id = one_stage_plan()
        checkpoint = make_stage_checkpoint(plan, work_id, state="PENDING")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            write_checkpoint(path, checkpoint)
            self.assertEqual(load_checkpoint(path), checkpoint)
            write_checkpoint(path, checkpoint)

            changed = copy.deepcopy(checkpoint)
            changed["volatile"] = {"host": "different"}
            with self.assertRaises(FileExistsError):
                write_checkpoint(path, changed)

    def test_examples_are_semantically_bound(self) -> None:
        plan = json.loads((EXAMPLES / "execution-plan.valid.json").read_text(encoding="utf-8"))
        checkpoint = json.loads(
            (EXAMPLES / "stage-checkpoint.valid.json").read_text(encoding="utf-8")
        )
        self.assertEqual(execution_plan_sha256(plan), checkpoint["execution_plan_sha256"])
        validate_stage_checkpoint(checkpoint, plan=plan)


if __name__ == "__main__":
    unittest.main()
