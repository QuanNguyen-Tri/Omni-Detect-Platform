from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Mapping, Optional, Protocol

import httpx

from omni_detect.config import Settings
from omni_detect.schemas import (
    DetectionKind,
    DetectionResult,
    FileDetectionResult,
    FileSection,
    ImageDetectionResult,
    ImageRegion,
    TextDetectionResult,
    TextSpan,
)


class RunPodJobError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class RunPodResultPending(RuntimeError):
    pass


class RunPodClient(Protocol):
    async def submit_detection_job(
        self,
        *,
        job_id: str,
        kind: DetectionKind,
        payload: Mapping[str, Any],
    ) -> str:
        ...

    async def get_result(self, runpod_job_id: str) -> DetectionResult:
        ...

    async def cancel_job(self, runpod_job_id: str) -> None:
        ...


class HTTPRunPodClient:
    _RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: Settings,
        *,
        client: Optional[httpx.AsyncClient] = None,
        owns_client: Optional[bool] = None,
    ) -> None:
        settings.require_runpod_http_config()
        self._settings = settings
        self._runpod_to_kind: Dict[str, DetectionKind] = {}
        self._owns_client = client is None if owns_client is None else owns_client
        self._client = client or httpx.AsyncClient(
            base_url=settings.runpod_api_base_url,
            headers={"Authorization": f"Bearer {settings.runpod_api_key}"},
            timeout=settings.runpod_request_timeout_seconds,
        )

    async def submit_detection_job(
        self,
        *,
        job_id: str,
        kind: DetectionKind,
        payload: Mapping[str, Any],
    ) -> str:
        response = await self._request(
            "POST",
            f"/v2/{self._settings.runpod_endpoint_id}/run",
            json={"input": {"job_id": job_id, "kind": kind.value, "payload": payload}},
        )
        data = _decode_json(response)
        runpod_job_id = data.get("id") or data.get("job_id")
        if not runpod_job_id:
            raise RunPodJobError(
                "runpod_bad_response",
                "RunPod submit response did not include a job id",
                details={"operation": "submit", "response": data},
            )
        runpod_job_id = str(runpod_job_id)
        self._runpod_to_kind[runpod_job_id] = kind
        return runpod_job_id

    async def get_result(self, runpod_job_id: str) -> DetectionResult:
        response = await self._request(
            "GET",
            f"/v2/{self._settings.runpod_endpoint_id}/status/{runpod_job_id}"
        )
        data = _decode_json(response)
        status = str(data.get("status", "")).upper()
        if status in {"IN_QUEUE", "IN_PROGRESS", "RUNNING", "PENDING"}:
            raise RunPodResultPending()
        if status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
            message = str(data.get("error") or data.get("message") or status)
            raise RunPodJobError(
                "runpod_job_failed",
                message,
                details={
                    "operation": "get_result",
                    "runpod_job_id": runpod_job_id,
                    "status": status,
                },
            )
        output = data.get("output")
        if output is None:
            raise RunPodJobError(
                "runpod_bad_response",
                "RunPod completed without an output payload",
                details={
                    "operation": "get_result",
                    "runpod_job_id": runpod_job_id,
                    "response": data,
                },
            )
        if not isinstance(output, Mapping):
            raise RunPodJobError(
                "runpod_bad_response",
                "RunPod output must be a JSON object",
                details={
                    "operation": "get_result",
                    "runpod_job_id": runpod_job_id,
                    "output": output,
                },
            )
        kind = self._kind_for_result(runpod_job_id, output)
        try:
            return parse_detection_result(kind, output.get("result", output))
        except Exception as exc:
            raise RunPodJobError(
                "runpod_bad_response",
                "RunPod output did not match the expected detection result schema",
                details={
                    "operation": "get_result",
                    "runpod_job_id": runpod_job_id,
                    "kind": kind.value,
                    "error": str(exc),
                },
            ) from exc

    async def cancel_job(self, runpod_job_id: str) -> None:
        await self._request(
            "POST",
            f"/v2/{self._settings.runpod_endpoint_id}/cancel/{runpod_job_id}"
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Mapping[str, Any]] = None,
    ) -> httpx.Response:
        attempts = self._settings.runpod_max_request_retries + 1
        last_error: Optional[RunPodJobError] = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.request(method, path, json=json)
            except httpx.TimeoutException as exc:
                last_error = RunPodJobError(
                    "runpod_request_timeout",
                    "RunPod request timed out",
                    details=_request_error_details(method, path, attempt, attempts),
                )
                if attempt >= attempts:
                    raise last_error from exc
                await self._sleep_before_retry(attempt)
                continue
            except httpx.RequestError as exc:
                last_error = RunPodJobError(
                    "runpod_request_error",
                    "RunPod request failed before receiving a response",
                    details={
                        **_request_error_details(method, path, attempt, attempts),
                        "error": str(exc),
                    },
                )
                if attempt >= attempts:
                    raise last_error from exc
                await self._sleep_before_retry(attempt)
                continue

            if response.status_code < 400:
                return response

            error = self._http_error(method, path, response, attempt, attempts)
            if (
                response.status_code not in self._RETRYABLE_STATUS_CODES
                or attempt >= attempts
            ):
                raise error
            last_error = error
            await self._sleep_before_retry(attempt)

        if last_error is not None:
            raise last_error
        raise RunPodJobError(
            "runpod_request_error",
            "RunPod request failed without an available response",
            details={"method": method, "path": path},
        )

    async def _sleep_before_retry(self, attempt: int) -> None:
        await asyncio.sleep(
            self._settings.runpod_retry_base_delay_seconds * (2 ** (attempt - 1))
        )

    def _http_error(
        self,
        method: str,
        path: str,
        response: httpx.Response,
        attempt: int,
        attempts: int,
    ) -> RunPodJobError:
        response_payload = _safe_response_payload(response)
        message = _extract_error_message(response_payload) or response.reason_phrase
        code = "runpod_http_error"
        if response.status_code == 429:
            code = "runpod_rate_limited"
        elif response.status_code >= 500:
            code = "runpod_server_error"
        return RunPodJobError(
            code,
            f"RunPod returned HTTP {response.status_code}: {message}",
            details={
                **_request_error_details(method, path, attempt, attempts),
                "status_code": response.status_code,
                "response": response_payload,
            },
        )

    def _kind_for_result(
        self, runpod_job_id: str, output: Mapping[str, Any]
    ) -> DetectionKind:
        kind = self._runpod_to_kind.get(runpod_job_id)
        if kind is not None:
            return kind
        try:
            return DetectionKind(output.get("kind"))
        except ValueError as exc:
            raise RunPodJobError(
                "runpod_bad_response",
                "RunPod output did not include a valid detection kind",
                details={
                    "operation": "get_result",
                    "runpod_job_id": runpod_job_id,
                    "kind": output.get("kind"),
                },
            ) from exc


class FakeRunPodClient:
    def __init__(
        self,
        *,
        fail: bool = False,
        delay_seconds: float = 0.0,
        results_by_job_id: Optional[Dict[str, DetectionResult]] = None,
    ) -> None:
        self.fail = fail
        self.delay_seconds = delay_seconds
        self.results_by_job_id = results_by_job_id or {}
        self.submitted_job_ids: List[str] = []
        self.cancelled_runpod_job_ids: List[str] = []
        self._runpod_to_job_id: Dict[str, str] = {}
        self._runpod_to_kind: Dict[str, DetectionKind] = {}

    async def submit_detection_job(
        self,
        *,
        job_id: str,
        kind: DetectionKind,
        payload: Mapping[str, Any],
    ) -> str:
        self.submitted_job_ids.append(job_id)
        runpod_job_id = f"fake-runpod-{job_id}"
        self._runpod_to_job_id[runpod_job_id] = job_id
        self._runpod_to_kind[runpod_job_id] = kind
        return runpod_job_id

    async def get_result(self, runpod_job_id: str) -> DetectionResult:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.fail:
            raise RunPodJobError("mock_runpod_failure", "Mock RunPod job failed")
        job_id = self._runpod_to_job_id[runpod_job_id]
        if job_id in self.results_by_job_id:
            return self.results_by_job_id[job_id]
        return default_detection_result(self._runpod_to_kind[runpod_job_id])

    async def cancel_job(self, runpod_job_id: str) -> None:
        self.cancelled_runpod_job_ids.append(runpod_job_id)


def build_runpod_client(settings: Settings) -> RunPodClient:
    if settings.runpod_backend.lower() == "http":
        return HTTPRunPodClient(settings)
    return FakeRunPodClient()


def parse_detection_result(kind: DetectionKind, payload: Mapping[str, Any]) -> DetectionResult:
    if kind == DetectionKind.TEXT:
        return TextDetectionResult.model_validate(payload)
    if kind == DetectionKind.IMAGE:
        return ImageDetectionResult.model_validate(payload)
    return FileDetectionResult.model_validate(payload)


def _request_error_details(
    method: str, path: str, attempt: int, attempts: int
) -> Dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "attempt": attempt,
        "max_attempts": attempts,
    }


def _decode_json(response: httpx.Response) -> Dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RunPodJobError(
            "runpod_bad_response",
            "RunPod response was not valid JSON",
            details={
                "status_code": response.status_code,
                "body": response.text[:500],
            },
        ) from exc
    if not isinstance(payload, dict):
        raise RunPodJobError(
            "runpod_bad_response",
            "RunPod response JSON must be an object",
            details={"status_code": response.status_code, "response": payload},
        )
    return payload


def _safe_response_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]


def _extract_error_message(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if value:
                return str(value)
    if isinstance(payload, str) and payload:
        return payload
    return None


def default_detection_result(kind: DetectionKind) -> DetectionResult:
    if kind == DetectionKind.TEXT:
        return TextDetectionResult(
            overall_ai_probability=0.12,
            spans=[
                TextSpan(
                    start_char=0,
                    end_char=12,
                    text="mock result",
                    ai_probability=0.12,
                    label="likely_human",
                )
            ],
        )
    if kind == DetectionKind.IMAGE:
        return ImageDetectionResult(
            overall_ai_probability=0.18,
            regions=[
                ImageRegion(
                    x=0,
                    y=0,
                    width=64,
                    height=64,
                    ai_probability=0.18,
                    label="likely_human",
                )
            ],
        )
    return FileDetectionResult(
        overall_ai_probability=0.22,
        sections=[
            FileSection(
                section_id="page-1",
                title="Page 1",
                start_page=1,
                end_page=1,
                ai_probability=0.22,
                label="likely_human",
            )
        ],
    )
