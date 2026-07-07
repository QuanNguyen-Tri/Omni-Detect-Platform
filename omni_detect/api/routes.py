from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from omni_detect.api.errors import api_error
from omni_detect.config import Settings
from omni_detect.jobs import JobStore, job_to_response
from omni_detect.schemas import (
    DetectTextRequest,
    DetectionKind,
    JobCreateResponse,
    JobResponse,
)
from omni_detect.scheduler import DetectionScheduler

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    settings: Settings = request.app.state.settings
    return {
        "status": "ok",
        "max_concurrent_gpu_jobs": settings.max_concurrent_gpu_jobs,
    }


@router.post(
    "/v1/detect/text",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def detect_text(body: DetectTextRequest, request: Request) -> JobCreateResponse:
    estimated_cost = body.estimated_cost or estimate_text_cost(body.text)
    job = await _jobs(request).create_job(
        kind=DetectionKind.TEXT,
        payload={"text": body.text, "metadata": body.metadata or {}},
        estimated_cost=estimated_cost,
    )
    await _scheduler(request).enqueue(job)
    return _create_response(job.job_id, job.status, job.kind, job.estimated_cost)


@router.post(
    "/v1/detect/image",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def detect_image(
    request: Request,
    file: UploadFile = File(...),
    estimated_cost: Optional[float] = Form(default=None),
) -> JobCreateResponse:
    settings: Settings = request.app.state.settings
    _validate_estimated_cost(estimated_cost)
    _validate_content_type(
        file.content_type,
        settings.allowed_image_content_types,
        "unsupported_image_type",
        "Unsupported image content type",
    )
    contents = await _read_upload(file, settings.max_image_upload_bytes)
    cost = estimated_cost or estimate_binary_cost(contents)
    job = await _jobs(request).create_job(
        kind=DetectionKind.IMAGE,
        payload=_upload_payload(file, contents),
        estimated_cost=cost,
    )
    await _scheduler(request).enqueue(job)
    return _create_response(job.job_id, job.status, job.kind, job.estimated_cost)


@router.post(
    "/v1/detect/file",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def detect_file(
    request: Request,
    file: UploadFile = File(...),
    estimated_cost: Optional[float] = Form(default=None),
) -> JobCreateResponse:
    settings: Settings = request.app.state.settings
    _validate_estimated_cost(estimated_cost)
    _validate_content_type(
        file.content_type,
        settings.allowed_file_content_types,
        "unsupported_file_type",
        "Unsupported file content type",
    )
    contents = await _read_upload(file, settings.max_file_upload_bytes)
    cost = estimated_cost or estimate_binary_cost(contents)
    job = await _jobs(request).create_job(
        kind=DetectionKind.FILE,
        payload=_upload_payload(file, contents),
        estimated_cost=cost,
    )
    await _scheduler(request).enqueue(job)
    return _create_response(job.job_id, job.status, job.kind, job.estimated_cost)


@router.get("/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, request: Request) -> JobResponse:
    job = await _jobs(request).get_job(job_id)
    if job is None:
        raise api_error(404, code="job_not_found", message="Job not found")
    return job_to_response(job)


def estimate_text_cost(text: str) -> float:
    return round(max(1.0, len(text) / 4_000.0), 4)


def estimate_binary_cost(contents: bytes) -> float:
    return round(max(1.0, len(contents) / (1024 * 1024)), 4)


def _jobs(request: Request) -> JobStore:
    return request.app.state.jobs


def _scheduler(request: Request) -> DetectionScheduler:
    return request.app.state.scheduler


def _create_response(
    job_id: str,
    status_value,
    kind: DetectionKind,
    estimated_cost: float,
) -> JobCreateResponse:
    return JobCreateResponse(
        job_id=job_id,
        status=status_value,
        kind=kind,
        estimated_cost=estimated_cost,
        status_url=f"/v1/jobs/{job_id}",
    )


def _validate_estimated_cost(estimated_cost: Optional[float]) -> None:
    if estimated_cost is not None and not (0 < estimated_cost <= 1_000):
        raise api_error(
            422,
            code="validation_error",
            message="estimated_cost must be greater than 0 and less than or equal to 1000",
        )


def _validate_content_type(
    content_type: Optional[str],
    allowed: tuple,
    code: str,
    message: str,
) -> None:
    if content_type not in allowed:
        raise api_error(
            415,
            code=code,
            message=message,
            details={"content_type": content_type, "allowed": list(allowed)},
        )


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    contents = await file.read(max_bytes + 1)
    if len(contents) > max_bytes:
        raise api_error(
            413,
            code="upload_too_large",
            message="Uploaded file exceeds the configured size limit",
            details={"max_bytes": max_bytes},
        )
    if not contents:
        raise api_error(400, code="empty_upload", message="Uploaded file is empty")
    return contents


def _upload_payload(file: UploadFile, contents: bytes):
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "data_base64": base64.b64encode(contents).decode("ascii"),
    }

