from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def api_error(
    status_code: int,
    *,
    code: str,
    message: str,
    details: Optional[Any] = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "details": details}},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            payload = exc.detail
        else:
            payload = {
                "error": {
                    "code": _status_code_to_error_code(exc.status_code),
                    "message": str(exc.detail),
                    "details": None,
                }
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(payload),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Request validation failed",
                        "details": exc.errors(),
                    }
                }
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error",
                    "details": None,
                }
            },
        )


def _status_code_to_error_code(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 413:
        return "payload_too_large"
    if status_code == 415:
        return "unsupported_media_type"
    return "request_error"
