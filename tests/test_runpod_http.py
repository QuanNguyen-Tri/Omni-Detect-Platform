from __future__ import annotations

import asyncio
import json
from typing import List

import httpx
import pytest

from omni_detect.config import Settings
from omni_detect.jobs import JobStore
from omni_detect.runpod import HTTPRunPodClient, RunPodJobError, RunPodResultPending
from omni_detect.scheduler import DetectionScheduler
from omni_detect.schemas import DetectionKind, JobStatus


def _settings(**overrides) -> Settings:
    values = {
        "runpod_backend": "http",
        "runpod_api_key": "test-api-key",
        "runpod_endpoint_id": "test-endpoint",
        "runpod_api_base_url": "https://api.runpod.test",
        "runpod_request_timeout_seconds": 0.5,
        "runpod_max_request_retries": 0,
        "runpod_retry_base_delay_seconds": 0.0,
        "runpod_result_poll_interval_seconds": 0.001,
        "runpod_max_result_polls": 1,
    }
    values.update(overrides)
    return Settings(**values)


def _client(
    handler,
    settings: Settings,
) -> HTTPRunPodClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        base_url=settings.runpod_api_base_url,
        headers={"Authorization": f"Bearer {settings.runpod_api_key}"},
        transport=transport,
    )
    return HTTPRunPodClient(settings, client=http_client, owns_client=True)


def test_http_runpod_submit_sends_expected_request():
    async def scenario():
        captured_requests: List[httpx.Request] = []
        settings = _settings()

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json={"id": "runpod-123"})

        client = _client(handler, settings)
        try:
            runpod_job_id = await client.submit_detection_job(
                job_id="omni-job-1",
                kind=DetectionKind.TEXT,
                payload={"text": "hello"},
            )
        finally:
            await client.aclose()

        assert runpod_job_id == "runpod-123"
        request = captured_requests[0]
        assert request.method == "POST"
        assert request.url.path == "/v2/test-endpoint/run"
        assert request.headers["authorization"] == "Bearer test-api-key"
        assert request.content
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content) == {
            "input": {
                "job_id": "omni-job-1",
                "kind": "text",
                "payload": {"text": "hello"},
            }
        }

    asyncio.run(scenario())


def test_http_runpod_get_result_parses_completed_response():
    async def scenario():
        settings = _settings()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/run"):
                return httpx.Response(200, json={"id": "runpod-123"})
            return httpx.Response(
                200,
                json={
                    "status": "COMPLETED",
                    "output": {
                        "result": {
                            "overall_ai_probability": 0.77,
                            "spans": [
                                {
                                    "start_char": 0,
                                    "end_char": 5,
                                    "text": "hello",
                                    "ai_probability": 0.77,
                                    "label": "likely_ai",
                                }
                            ],
                        }
                    },
                },
            )

        client = _client(handler, settings)
        try:
            runpod_job_id = await client.submit_detection_job(
                job_id="omni-job-1",
                kind=DetectionKind.TEXT,
                payload={"text": "hello"},
            )
            result = await client.get_result(runpod_job_id)
        finally:
            await client.aclose()

        assert result.overall_ai_probability == 0.77
        assert result.spans[0].label == "likely_ai"

    asyncio.run(scenario())


def test_http_runpod_get_result_pending_status():
    async def scenario():
        settings = _settings()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "IN_PROGRESS"})

        client = _client(handler, settings)
        try:
            with pytest.raises(RunPodResultPending):
                await client.get_result("runpod-123")
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_http_runpod_cancel_job_sends_expected_request():
    async def scenario():
        captured_requests: List[httpx.Request] = []
        settings = _settings()

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(204)

        client = _client(handler, settings)
        try:
            await client.cancel_job("runpod-123")
        finally:
            await client.aclose()

        request = captured_requests[0]
        assert request.method == "POST"
        assert request.url.path == "/v2/test-endpoint/cancel/runpod-123"
        assert request.headers["authorization"] == "Bearer test-api-key"

    asyncio.run(scenario())


def test_http_runpod_retries_retryable_status_codes():
    async def scenario():
        settings = _settings(runpod_max_request_retries=2)
        calls: List[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if len(calls) < 3:
                return httpx.Response(503, json={"error": "worker unavailable"})
            return httpx.Response(200, json={"id": "runpod-123"})

        client = _client(handler, settings)
        try:
            runpod_job_id = await client.submit_detection_job(
                job_id="omni-job-1",
                kind=DetectionKind.TEXT,
                payload={"text": "hello"},
            )
        finally:
            await client.aclose()

        assert runpod_job_id == "runpod-123"
        assert len(calls) == 3

    asyncio.run(scenario())


def test_http_runpod_non_retryable_http_error_is_structured():
    async def scenario():
        settings = _settings(runpod_max_request_retries=2)
        calls: List[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(401, json={"error": "invalid api key"})

        client = _client(handler, settings)
        try:
            with pytest.raises(RunPodJobError) as error:
                await client.submit_detection_job(
                    job_id="omni-job-1",
                    kind=DetectionKind.TEXT,
                    payload={"text": "hello"},
                )
        finally:
            await client.aclose()

        assert error.value.code == "runpod_http_error"
        assert "HTTP 401" in error.value.message
        assert error.value.details["status_code"] == 401
        assert error.value.details["response"] == {"error": "invalid api key"}
        assert len(calls) == 1

    asyncio.run(scenario())


def test_http_runpod_timeout_error_is_structured():
    async def scenario():
        settings = _settings(runpod_max_request_retries=1)
        calls: List[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            raise httpx.ReadTimeout("timed out", request=request)

        client = _client(handler, settings)
        try:
            with pytest.raises(RunPodJobError) as error:
                await client.submit_detection_job(
                    job_id="omni-job-1",
                    kind=DetectionKind.TEXT,
                    payload={"text": "hello"},
                )
        finally:
            await client.aclose()

        assert error.value.code == "runpod_request_timeout"
        assert error.value.details["attempt"] == 2
        assert error.value.details["max_attempts"] == 2
        assert len(calls) == 2

    asyncio.run(scenario())


def test_http_runpod_bad_completed_payload_is_structured():
    async def scenario():
        settings = _settings()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "COMPLETED",
                    "output": {"result": {"overall_ai_probability": 0.5}},
                },
            )

        client = _client(handler, settings)
        try:
            with pytest.raises(RunPodJobError) as error:
                await client.get_result("runpod-123")
        finally:
            await client.aclose()

        assert error.value.code == "runpod_bad_response"
        assert error.value.details["operation"] == "get_result"

    asyncio.run(scenario())


def test_scheduler_persists_structured_runpod_error_details():
    async def scenario():
        settings = _settings(
            max_concurrent_gpu_jobs=1,
            runpod_max_request_retries=0,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "capacity unavailable"})

        client = _client(handler, settings)
        jobs = JobStore()
        scheduler = DetectionScheduler(settings=settings, jobs=jobs, runpod=client)
        job = await jobs.create_job(
            kind=DetectionKind.TEXT,
            payload={"text": "hello"},
            estimated_cost=1,
        )

        try:
            await scheduler.enqueue(job)
            await scheduler.drain()
        finally:
            await client.aclose()

        failed = await jobs.get_job(job.job_id)
        assert failed.status == JobStatus.FAILED
        assert failed.error.code == "runpod_server_error"
        assert failed.error.details["status_code"] == 500
        assert failed.error.details["response"] == {"error": "capacity unavailable"}

    asyncio.run(scenario())
