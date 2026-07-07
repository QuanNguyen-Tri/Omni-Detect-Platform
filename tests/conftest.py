from __future__ import annotations

import time
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from omni_detect.api.app import create_app
from omni_detect.config import Settings
from omni_detect.runpod import FakeRunPodClient


@pytest.fixture
def settings() -> Settings:
    return Settings(
        max_concurrent_gpu_jobs=1,
        runpod_result_poll_interval_seconds=0.001,
        runpod_max_result_polls=3,
    )


@pytest.fixture
def fake_runpod() -> FakeRunPodClient:
    return FakeRunPodClient()


@pytest.fixture
def client(settings: Settings, fake_runpod: FakeRunPodClient):
    app = create_app(settings=settings, runpod_client=fake_runpod)
    with TestClient(app) as test_client:
        yield test_client


def wait_for_job(
    client: TestClient,
    job_id: str,
    *,
    timeout_seconds: float = 2.0,
    expected_status: Optional[str] = None,
):
    deadline = time.time() + timeout_seconds
    last_payload = None
    while time.time() < deadline:
        response = client.get(f"/v1/jobs/{job_id}")
        response.raise_for_status()
        last_payload = response.json()
        if last_payload["status"] in {"succeeded", "failed", "cancelled"}:
            if expected_status is not None:
                assert last_payload["status"] == expected_status
            return last_payload
        time.sleep(0.01)
    raise AssertionError(f"job did not finish before timeout: {last_payload}")

