from __future__ import annotations

from tests.conftest import wait_for_job


def test_text_detection_request_validation(client):
    response = client.post("/v1/detect/text", json={"text": "   "})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"


def test_image_upload_validation(client):
    response = client.post(
        "/v1/detect/image",
        files={"file": ("image.gif", b"gif-bytes", "image/gif")},
    )

    assert response.status_code == 415
    payload = response.json()
    assert payload["error"]["code"] == "unsupported_image_type"


def test_file_upload_validation(client):
    response = client.post(
        "/v1/detect/file",
        files={"file": ("archive.zip", b"zip-bytes", "application/zip")},
    )

    assert response.status_code == 415
    payload = response.json()
    assert payload["error"]["code"] == "unsupported_file_type"


def test_successful_mocked_runpod_response(client):
    response = client.post("/v1/detect/text", json={"text": "Human looking text."})

    assert response.status_code == 202
    created = response.json()
    payload = wait_for_job(client, created["job_id"], expected_status="succeeded")
    assert payload["kind"] == "text"
    assert payload["result"]["overall_ai_probability"] == 0.12
    assert payload["result"]["spans"][0]["label"] == "likely_human"


def test_failed_mocked_runpod_response(settings):
    from fastapi.testclient import TestClient

    from omni_detect.api.app import create_app
    from omni_detect.runpod import FakeRunPodClient

    fake = FakeRunPodClient(fail=True)
    app = create_app(settings=settings, runpod_client=fake)
    with TestClient(app) as client:
        response = client.post("/v1/detect/text", json={"text": "Human looking text."})
        assert response.status_code == 202
        created = response.json()
        payload = wait_for_job(client, created["job_id"], expected_status="failed")

    assert payload["error"]["code"] == "mock_runpod_failure"
    assert payload["result"] is None

