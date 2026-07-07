from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

from omni_detect.config import Settings
from omni_detect.jobs import DetectionJob, InvalidJobTransition, JobStore
from omni_detect.runpod import RunPodClient, RunPodJobError, RunPodResultPending


@dataclass(frozen=True)
class PendingJob:
    job_id: str
    estimated_cost: float
    sequence: int
    enqueued_at: float


class DetectionScheduler:
    def __init__(
        self,
        *,
        settings: Settings,
        jobs: JobStore,
        runpod: RunPodClient,
    ) -> None:
        self._settings = settings
        self._jobs = jobs
        self._runpod = runpod
        self._pending: List[PendingJob] = []
        self._active: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._event = asyncio.Event()
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._short_streak = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        self._running = False
        self._event.set()
        if self._worker_task is not None:
            await self._worker_task
        for task in list(self._active.values()):
            task.cancel()
        if self._active:
            await asyncio.gather(*self._active.values(), return_exceptions=True)
        close = getattr(self._runpod, "aclose", None)
        if close is not None:
            await close()

    async def enqueue(self, job: DetectionJob) -> None:
        loop = asyncio.get_running_loop()
        async with self._lock:
            if job.job_id not in {pending.job_id for pending in self._pending}:
                self._pending.append(
                    PendingJob(
                        job_id=job.job_id,
                        estimated_cost=job.estimated_cost,
                        sequence=job.sequence,
                        enqueued_at=loop.time(),
                    )
                )
        self._event.set()

    async def run_once(self) -> int:
        selected: List[PendingJob] = []
        loop = asyncio.get_running_loop()
        async with self._lock:
            capacity = self._settings.max_concurrent_gpu_jobs - len(self._active)
            for _ in range(max(0, capacity)):
                pending = self._select_next_locked(loop.time())
                if pending is None:
                    break
                selected.append(pending)

            for pending in selected:
                task = asyncio.create_task(self._execute_job(pending.job_id))
                self._active[pending.job_id] = task
                task.add_done_callback(
                    lambda completed, job_id=pending.job_id: self._job_done(
                        job_id, completed
                    )
                )
        return len(selected)

    async def drain(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(0)
            if not self._pending and not self._active:
                return
            if self._active:
                await asyncio.wait(
                    list(self._active.values()), return_when=asyncio.FIRST_COMPLETED
                )

    def pending_count(self) -> int:
        return len(self._pending)

    def active_count(self) -> int:
        return len(self._active)

    def _select_next_locked(self, now: float) -> Optional[PendingJob]:
        if not self._pending:
            return None

        short_jobs = [
            pending
            for pending in self._pending
            if pending.estimated_cost <= self._settings.short_job_cost_threshold
        ]
        long_jobs = [
            pending
            for pending in self._pending
            if pending.estimated_cost > self._settings.short_job_cost_threshold
        ]

        selected: Optional[PendingJob]
        should_promote_long = bool(long_jobs) and (
            self._short_streak >= self._settings.max_short_job_streak
            or any(
                now - pending.enqueued_at
                >= self._settings.long_job_fairness_wait_seconds
                for pending in long_jobs
            )
        )

        if should_promote_long:
            selected = min(long_jobs, key=lambda pending: pending.sequence)
        elif short_jobs:
            selected = min(short_jobs, key=lambda pending: pending.sequence)
        else:
            selected = min(long_jobs, key=lambda pending: pending.sequence)

        self._pending.remove(selected)
        if selected.estimated_cost <= self._settings.short_job_cost_threshold:
            self._short_streak += 1
        else:
            self._short_streak = 0
        return selected

    async def _worker(self) -> None:
        while self._running:
            await self.run_once()
            if self._pending and self.active_count() < self._settings.max_concurrent_gpu_jobs:
                continue
            await self._event.wait()
            self._event.clear()

    async def _execute_job(self, job_id: str) -> None:
        job = await self._jobs.get_job(job_id)
        if job is None:
            return
        try:
            await self._jobs.mark_running(job_id)
            runpod_job_id = await self._runpod.submit_detection_job(
                job_id=job.job_id,
                kind=job.kind,
                payload=job.payload,
            )
            await self._jobs.set_runpod_job_id(job_id, runpod_job_id)
            result = await self._wait_for_result(runpod_job_id)
            await self._jobs.mark_succeeded(job_id, result)
        except asyncio.CancelledError:
            try:
                await self._jobs.mark_cancelled(job_id)
            except InvalidJobTransition:
                pass
            raise
        except RunPodJobError as exc:
            await self._jobs.mark_failed(
                job_id,
                code=exc.code,
                message=exc.message,
                details=exc.details,
            )
        except Exception as exc:
            await self._jobs.mark_failed(
                job_id, code="internal_error", message=str(exc)
            )

    async def _wait_for_result(self, runpod_job_id: str):
        for _ in range(self._settings.runpod_max_result_polls):
            try:
                return await self._runpod.get_result(runpod_job_id)
            except RunPodResultPending:
                await asyncio.sleep(self._settings.runpod_result_poll_interval_seconds)
        raise RunPodJobError(
            "runpod_timeout", "RunPod job did not complete before the polling timeout"
        )

    def _job_done(self, job_id: str, completed: asyncio.Task[None]) -> None:
        self._active.pop(job_id, None)
        if not completed.cancelled():
            completed.exception()
        self._event.set()
