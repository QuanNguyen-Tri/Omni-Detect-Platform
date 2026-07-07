from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from omni_detect.schemas import (
    DetectionKind,
    DetectionResult,
    ErrorDetail,
    JobResponse,
    JobStatus,
)


class JobNotFound(KeyError):
    pass


class InvalidJobTransition(RuntimeError):
    pass


@dataclass
class DetectionJob:
    job_id: str
    kind: DetectionKind
    payload: Dict[str, Any]
    estimated_cost: float
    sequence: int
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[DetectionResult] = None
    error: Optional[ErrorDetail] = None
    runpod_job_id: Optional[str] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, DetectionJob] = {}
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def create_job(
        self,
        *,
        kind: DetectionKind,
        payload: Dict[str, Any],
        estimated_cost: float,
    ) -> DetectionJob:
        now = _utcnow()
        async with self._lock:
            self._sequence += 1
            job = DetectionJob(
                job_id=str(uuid4()),
                kind=kind,
                payload=payload,
                estimated_cost=estimated_cost,
                sequence=self._sequence,
                status=JobStatus.QUEUED,
                created_at=now,
                updated_at=now,
                queued_at=now,
            )
            self._jobs[job.job_id] = job
            return job

    async def get_job(self, job_id: str) -> Optional[DetectionJob]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def mark_running(self, job_id: str) -> DetectionJob:
        async with self._lock:
            job = self._require_job(job_id)
            self._transition(job, JobStatus.RUNNING)
            now = _utcnow()
            job.status = JobStatus.RUNNING
            job.started_at = now
            job.updated_at = now
            return job

    async def set_runpod_job_id(self, job_id: str, runpod_job_id: str) -> DetectionJob:
        async with self._lock:
            job = self._require_job(job_id)
            if job.status != JobStatus.RUNNING:
                raise InvalidJobTransition(
                    f"cannot set runpod_job_id while job is {job.status.value}"
                )
            job.runpod_job_id = runpod_job_id
            job.updated_at = _utcnow()
            return job

    async def mark_succeeded(
        self, job_id: str, result: DetectionResult
    ) -> DetectionJob:
        async with self._lock:
            job = self._require_job(job_id)
            self._transition(job, JobStatus.SUCCEEDED)
            now = _utcnow()
            job.status = JobStatus.SUCCEEDED
            job.result = result
            job.error = None
            job.completed_at = now
            job.updated_at = now
            return job

    async def mark_failed(
        self,
        job_id: str,
        *,
        code: str,
        message: str,
        details: Optional[Any] = None,
    ) -> DetectionJob:
        async with self._lock:
            job = self._require_job(job_id)
            self._transition(job, JobStatus.FAILED)
            now = _utcnow()
            job.status = JobStatus.FAILED
            job.error = ErrorDetail(code=code, message=message, details=details)
            job.completed_at = now
            job.updated_at = now
            return job

    async def mark_cancelled(self, job_id: str) -> DetectionJob:
        async with self._lock:
            job = self._require_job(job_id)
            self._transition(job, JobStatus.CANCELLED)
            now = _utcnow()
            job.status = JobStatus.CANCELLED
            job.completed_at = now
            job.updated_at = now
            return job

    def _require_job(self, job_id: str) -> DetectionJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    @staticmethod
    def _transition(job: DetectionJob, new_status: JobStatus) -> None:
        allowed = {
            JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
            JobStatus.RUNNING: {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            },
        }
        if new_status not in allowed.get(job.status, set()):
            raise InvalidJobTransition(
                f"cannot transition job {job.job_id} from "
                f"{job.status.value} to {new_status.value}"
            )


def job_to_response(job: DetectionJob) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        kind=job.kind,
        estimated_cost=job.estimated_cost,
        created_at=job.created_at,
        updated_at=job.updated_at,
        queued_at=job.queued_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=job.result,
        error=job.error,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
