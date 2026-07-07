from __future__ import annotations

import asyncio

import pytest

from omni_detect.config import Settings
from omni_detect.jobs import InvalidJobTransition, JobStore
from omni_detect.runpod import FakeRunPodClient
from omni_detect.scheduler import DetectionScheduler
from omni_detect.schemas import DetectionKind, JobStatus, TextDetectionResult


def test_job_state_transitions():
    async def scenario():
        jobs = JobStore()
        job = await jobs.create_job(
            kind=DetectionKind.TEXT,
            payload={"text": "hello"},
            estimated_cost=1,
        )

        assert job.status == JobStatus.QUEUED
        await jobs.mark_running(job.job_id)
        result = TextDetectionResult(overall_ai_probability=0.1, spans=[])
        await jobs.mark_succeeded(job.job_id, result)
        finished = await jobs.get_job(job.job_id)
        assert finished.status == JobStatus.SUCCEEDED

        with pytest.raises(InvalidJobTransition):
            await jobs.mark_failed(
                job.job_id, code="already_done", message="already done"
            )

        queued = await jobs.create_job(
            kind=DetectionKind.TEXT,
            payload={"text": "queued"},
            estimated_cost=1,
        )
        with pytest.raises(InvalidJobTransition):
            await jobs.mark_succeeded(queued.job_id, result)

    asyncio.run(scenario())


def test_scheduler_prioritizes_short_jobs():
    async def scenario():
        settings = Settings(
            max_concurrent_gpu_jobs=1,
            short_job_cost_threshold=2,
            max_short_job_streak=10,
        )
        jobs = JobStore()
        fake = FakeRunPodClient()
        scheduler = DetectionScheduler(settings=settings, jobs=jobs, runpod=fake)
        long_job = await jobs.create_job(
            kind=DetectionKind.TEXT,
            payload={"text": "long"},
            estimated_cost=10,
        )
        short_one = await jobs.create_job(
            kind=DetectionKind.TEXT,
            payload={"text": "short one"},
            estimated_cost=1,
        )
        short_two = await jobs.create_job(
            kind=DetectionKind.TEXT,
            payload={"text": "short two"},
            estimated_cost=1,
        )

        await scheduler.enqueue(long_job)
        await scheduler.enqueue(short_one)
        await scheduler.enqueue(short_two)
        await scheduler.drain()

        assert fake.submitted_job_ids == [
            short_one.job_id,
            short_two.job_id,
            long_job.job_id,
        ]

    asyncio.run(scenario())


def test_scheduler_does_not_starve_long_jobs():
    async def scenario():
        settings = Settings(
            max_concurrent_gpu_jobs=1,
            short_job_cost_threshold=2,
            max_short_job_streak=2,
            long_job_fairness_wait_seconds=999,
        )
        jobs = JobStore()
        fake = FakeRunPodClient()
        scheduler = DetectionScheduler(settings=settings, jobs=jobs, runpod=fake)
        long_job = await jobs.create_job(
            kind=DetectionKind.TEXT,
            payload={"text": "long"},
            estimated_cost=10,
        )
        short_jobs = []
        for index in range(5):
            short_jobs.append(
                await jobs.create_job(
                    kind=DetectionKind.TEXT,
                    payload={"text": f"short {index}"},
                    estimated_cost=1,
                )
            )

        await scheduler.enqueue(long_job)
        for job in short_jobs:
            await scheduler.enqueue(job)
        await scheduler.drain()

        assert fake.submitted_job_ids[:3] == [
            short_jobs[0].job_id,
            short_jobs[1].job_id,
            long_job.job_id,
        ]

    asyncio.run(scenario())

