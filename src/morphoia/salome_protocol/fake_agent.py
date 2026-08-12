"""Explicit fake SALOME agent for protocol tests only.

This module never imports or executes SALOME. Its responses state that they are
simulated and that real SALOME execution is ``NOT_RUN``.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .contract import OPERATIONS, PROTOCOL_VERSION, ProtocolError, ensure_safe_control_value

Clock = Callable[[], datetime]


@dataclass(slots=True)
class _FakeJob:
    job_id: str
    idempotency_key: str
    state: str = "queued"
    sequence: int = 1


class FakeSalomeAgent:
    """In-memory contract double that cannot establish SALOME compatibility."""

    agent_kind = "fake"
    simulation = True
    backend_available = False

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._jobs: dict[str, _FakeJob] = {}
        self._jobs_by_idempotency_key: dict[str, str] = {}
        self._next_job = 1

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Dispatch one already schema-validated request to the fake lifecycle."""

        ensure_safe_control_value(request)
        if request.get("protocol_version") != PROTOCOL_VERSION:
            raise ProtocolError("unsupported SALOME protocol version")
        if request.get("direction") != "request":
            raise ProtocolError("the fake agent accepts request messages only")
        operation = request.get("operation")
        if operation not in OPERATIONS:
            raise ProtocolError(f"unsupported SALOME protocol operation: {operation!r}")
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ProtocolError("request_id must be a non-empty string")
        body = request.get("body")
        if not isinstance(body, Mapping):
            raise ProtocolError("request body must be an object")

        handlers = {
            "ProbeCapabilities": self._probe_capabilities,
            "Submit": self._submit,
            "Observe": self._observe,
            "Cancel": self._cancel,
            "Publish": self._publish,
            "Health": self._health,
        }
        response = handlers[operation](request_id, body)
        ensure_safe_control_value(response)
        return deepcopy(response)

    def _timestamp(self) -> str:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProtocolError("the fake-agent clock must return a timezone-aware datetime")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _response(
        self,
        operation: str,
        request_id: str,
        status: str,
        body: dict[str, Any],
        *,
        attempt: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "message_id": f"fake-response:{operation}:{request_id}",
            "request_id": request_id,
            "direction": "response",
            "agent_kind": "fake",
            "simulation": True,
            "operation": operation,
            "sent_at": self._timestamp(),
            "status": status,
            "body": body,
        }
        if attempt is not None:
            response["attempt"] = attempt
        if diagnostics:
            response["diagnostics"] = diagnostics
        return response

    @staticmethod
    def _not_run_diagnostic() -> dict[str, Any]:
        return {
            "code": "SALOME_NOT_RUN",
            "severity": "warning",
            "message": (
                "This is the explicit fake contract agent; no SALOME runtime was "
                "detected or executed."
            ),
        }

    def _probe_capabilities(
        self, request_id: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        del body
        modules = [
            {"name": name, "version": None, "status": "NOT_RUN"}
            for name in ("SHAPER", "GEOM", "SMESH", "MEDCoupling", "ParaVis")
        ]
        return self._response(
            "ProbeCapabilities",
            request_id,
            "not_available",
            {
                "agent_kind": "fake",
                "simulation": True,
                "backend_available": False,
                "runtime": {
                    "status": "NOT_RUN",
                    "salome_version": None,
                    "python_version": None,
                    "cpp_standard": None,
                    "occt_version": None,
                    "med_file_version": None,
                    "launch_mode": None,
                    "gui_active": False,
                    "detected_at": None,
                },
                "modules": modules,
                "med_formats": [],
                "oss_meshers": [],
                "limits": {
                    "max_control_message_bytes": 1048576,
                    "max_inputs": 256,
                    "max_outputs": 64,
                    "max_parameter_properties": 64,
                    "max_runtime_seconds": 0,
                    "max_memory_bytes": 0,
                    "max_temp_bytes": 0,
                },
                "licenses": [
                    {
                        "component": "morphoia-fake-salome-agent",
                        "expression": "Apache-2.0 OR MIT",
                        "status": "PASS",
                    },
                    {
                        "component": "SALOME runtime",
                        "expression": "NOASSERTION",
                        "status": "NOT_RUN",
                    },
                ],
                "supported_operations": list(OPERATIONS),
            },
            diagnostics=[self._not_run_diagnostic()],
        )

    def _submit(self, request_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        idempotency_key = body.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ProtocolError("Submit requires a non-empty idempotency_key")
        previous_job_id = self._jobs_by_idempotency_key.get(idempotency_key)
        duplicate = previous_job_id is not None
        if previous_job_id is None:
            job_id = f"fake-job-{self._next_job:06d}"
            self._next_job += 1
            job = _FakeJob(job_id=job_id, idempotency_key=idempotency_key)
            self._jobs[job_id] = job
            self._jobs_by_idempotency_key[idempotency_key] = job_id
        else:
            job = self._jobs[previous_job_id]
        return self._response(
            "Submit",
            request_id,
            "accepted",
            {
                "job_id": job.job_id,
                "accepted": True,
                "duplicate": duplicate,
                "execution_profile": "fake-contract",
            },
            attempt=self._attempt(job, terminal=False),
            diagnostics=[self._not_run_diagnostic()],
        )

    def _observe(self, request_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(body)
        job = self._jobs.get(job_id)
        if job is None:
            return self._response(
                "Observe",
                request_id,
                "not_available",
                {
                    "job_id": job_id,
                    "job_state": "not_available",
                    "progress": 0.0,
                    "timeout": {"deadline": None, "exceeded": False},
                },
                attempt=self._missing_attempt(job_id),
                diagnostics=[self._not_run_diagnostic()],
            )
        status = "cancelled" if job.state == "cancelled" else "running"
        return self._response(
            "Observe",
            request_id,
            status,
            {
                "job_id": job_id,
                "job_state": job.state,
                "progress": 0.0,
                "timeout": {"deadline": None, "exceeded": False},
            },
            attempt=self._attempt(job, terminal=job.state == "cancelled"),
            diagnostics=[self._not_run_diagnostic()],
        )

    def _cancel(self, request_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(body)
        job = self._jobs.get(job_id)
        if job is None:
            return self._response(
                "Cancel",
                request_id,
                "not_available",
                {
                    "job_id": job_id,
                    "job_state": "not_available",
                    "cancellation_effect": "not_found",
                    "idempotent": True,
                },
                attempt=self._missing_attempt(job_id),
                diagnostics=[self._not_run_diagnostic()],
            )
        if job.state == "cancelled":
            effect = "already_cancelled"
        elif job.state in {"succeeded", "failed", "timed_out", "not_available"}:
            effect = "already_terminal"
        else:
            job.state = "cancelled"
            job.sequence += 1
            effect = "cancelled"
        return self._response(
            "Cancel",
            request_id,
            "cancelled",
            {
                "job_id": job_id,
                "job_state": "cancelled",
                "cancellation_effect": effect,
                "idempotent": True,
            },
            attempt=self._attempt(job, terminal=True),
            diagnostics=[self._not_run_diagnostic()],
        )

    def _publish(self, request_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(body)
        job = self._jobs.get(job_id)
        if job is None:
            attempt = self._missing_attempt(job_id)
            status = "not_available"
        elif job.state == "cancelled":
            attempt = self._attempt(job, terminal=True)
            status = "cancelled"
        else:
            attempt = self._unavailable_attempt(job)
            status = "not_available"
        return self._response(
            "Publish",
            request_id,
            status,
            {
                "job_id": job_id,
                "artifacts": [],
                "losses": [
                    {
                        "id": "FAKE-NO-SALOME",
                        "category": "backend_unavailable",
                        "severity": "error",
                        "message": (
                            "The fake contract agent never produces STEP, XAO, MED, "
                            "or HDF artifacts."
                        ),
                    }
                ],
                "metrics": [],
            },
            attempt=attempt,
            diagnostics=[self._not_run_diagnostic()],
        )

    def _health(self, request_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        del body
        return self._response(
            "Health",
            request_id,
            "not_available",
            {
                "agent_kind": "fake",
                "simulation": True,
                "runtime_ready": False,
                "salome_status": "NOT_RUN",
                "gui_active": False,
                "temp_space_available_bytes": 0,
                "protocol_version": PROTOCOL_VERSION,
            },
            diagnostics=[self._not_run_diagnostic()],
        )

    @staticmethod
    def _job_id(body: Mapping[str, Any]) -> str:
        job_id = body.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ProtocolError("the operation requires a non-empty job_id")
        return job_id

    def _attempt(self, job: _FakeJob, *, terminal: bool) -> dict[str, Any]:
        return {
            "attempt_id": f"fake-attempt:{job.job_id}",
            "sequence": job.sequence,
            "state": job.state,
            "terminal": terminal,
            "environment": self._environment(),
            "logs": [self._log_record()],
        }

    def _missing_attempt(self, job_id: str) -> dict[str, Any]:
        return {
            "attempt_id": f"fake-attempt:{job_id}",
            "sequence": 1,
            "state": "not_available",
            "terminal": True,
            "environment": self._environment(),
            "logs": [self._log_record()],
        }

    def _unavailable_attempt(self, job: _FakeJob) -> dict[str, Any]:
        return {
            "attempt_id": f"fake-publish-attempt:{job.job_id}",
            "sequence": job.sequence,
            "state": "not_available",
            "terminal": True,
            "environment": self._environment(),
            "logs": [self._log_record()],
        }

    @staticmethod
    def _environment() -> dict[str, Any]:
        return {
            "profile": "fake-contract",
            "os": platform.system() or "unknown",
            "architecture": platform.machine() or "unknown",
            "python_version": platform.python_version(),
            "salome_version": None,
            "salome_status": "NOT_RUN",
        }

    def _log_record(self) -> dict[str, Any]:
        return {
            "time": self._timestamp(),
            "level": "warning",
            "code": "SALOME_NOT_RUN",
            "message": (
                "Fake contract lifecycle only; no SALOME code, module, or runtime "
                f"was executed by Python {sys.version_info.major}.{sys.version_info.minor}."
            ),
        }
