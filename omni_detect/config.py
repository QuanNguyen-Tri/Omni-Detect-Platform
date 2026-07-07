from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _env_non_negative_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be greater than or equal to zero")
    return parsed


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


@dataclass(frozen=True)
class Settings:
    max_concurrent_gpu_jobs: int = 6
    short_job_cost_threshold: float = 1.0
    max_short_job_streak: int = 3
    long_job_fairness_wait_seconds: float = 30.0
    runpod_backend: str = "fake"
    runpod_api_key: Optional[str] = None
    runpod_endpoint_id: Optional[str] = None
    runpod_api_base_url: str = "https://api.runpod.ai"
    runpod_request_timeout_seconds: float = 30.0
    runpod_max_request_retries: int = 3
    runpod_retry_base_delay_seconds: float = 0.25
    runpod_result_poll_interval_seconds: float = 1.0
    runpod_max_result_polls: int = 120
    max_image_upload_bytes: int = 20 * 1024 * 1024
    max_file_upload_bytes: int = 50 * 1024 * 1024
    allowed_image_content_types: Tuple[str, ...] = field(
        default=("image/jpeg", "image/png", "image/webp")
    )
    allowed_file_content_types: Tuple[str, ...] = field(
        default=(
            "application/pdf",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            max_concurrent_gpu_jobs=_env_int("OMNI_MAX_CONCURRENT_GPU_JOBS", 6),
            short_job_cost_threshold=_env_float("OMNI_SHORT_JOB_COST_THRESHOLD", 1.0),
            max_short_job_streak=_env_int("OMNI_MAX_SHORT_JOB_STREAK", 3),
            long_job_fairness_wait_seconds=_env_float(
                "OMNI_LONG_JOB_FAIRNESS_WAIT_SECONDS", 30.0
            ),
            runpod_backend=os.getenv("OMNI_RUNPOD_BACKEND", "fake"),
            runpod_api_key=os.getenv("RUNPOD_API_KEY"),
            runpod_endpoint_id=os.getenv("RUNPOD_ENDPOINT_ID"),
            runpod_api_base_url=os.getenv(
                "RUNPOD_API_BASE_URL", "https://api.runpod.ai"
            ).rstrip("/"),
            runpod_request_timeout_seconds=_env_float(
                "OMNI_RUNPOD_REQUEST_TIMEOUT_SECONDS", 30.0
            ),
            runpod_max_request_retries=_env_non_negative_int(
                "OMNI_RUNPOD_MAX_REQUEST_RETRIES", 3
            ),
            runpod_retry_base_delay_seconds=_env_float(
                "OMNI_RUNPOD_RETRY_BASE_DELAY_SECONDS", 0.25
            ),
            runpod_result_poll_interval_seconds=_env_float(
                "OMNI_RUNPOD_RESULT_POLL_INTERVAL_SECONDS", 1.0
            ),
            runpod_max_result_polls=_env_int("OMNI_RUNPOD_MAX_RESULT_POLLS", 120),
            max_image_upload_bytes=_env_int(
                "OMNI_MAX_IMAGE_UPLOAD_BYTES", 20 * 1024 * 1024
            ),
            max_file_upload_bytes=_env_int(
                "OMNI_MAX_FILE_UPLOAD_BYTES", 50 * 1024 * 1024
            ),
        )

    def require_runpod_http_config(self) -> None:
        if not self.runpod_api_key:
            raise ValueError("RUNPOD_API_KEY is required when OMNI_RUNPOD_BACKEND=http")
        if not self.runpod_endpoint_id:
            raise ValueError(
                "RUNPOD_ENDPOINT_ID is required when OMNI_RUNPOD_BACKEND=http"
            )
