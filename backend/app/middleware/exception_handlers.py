"""Global exception handlers for standardized error responses.

Catches HTTPException, RequestValidationError, and unhandled exceptions
to return consistent JSON error format with request correlation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.middleware.error_codes import ErrorCode, get_error_code

logger = logging.getLogger("app.exception")


def build_error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build standardized error response."""
    request_id = getattr(request.state, "request_id", None)

    body: dict[str, Any] = {
        "success": False,
        "error": {
            "code": code.value,
            "message": message,
            "request_id": request_id,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if details:
        body["error"]["details"] = details

    return JSONResponse(status_code=status_code, content=body)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTPException with standardized format."""
    error_code = get_error_code(exc.status_code)

    # Log server errors
    if exc.status_code >= 500:
        logger.error(
            "HTTPException status=%s detail=%s request_id=%s",
            exc.status_code,
            exc.detail,
            getattr(request.state, "request_id", None),
        )

    return build_error_response(
        request=request,
        status_code=exc.status_code,
        code=error_code,
        message=str(exc.detail),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with field-level details."""
    details = []
    for error in exc.errors():
        loc = " -> ".join(str(x) for x in error.get("loc", []))
        details.append(
            {
                "field": loc,
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
        )

    return build_error_response(
        request=request,
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="Validation error: Please check your request data",
        details=details,
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions - returns 500 with minimal info."""
    request_id = getattr(request.state, "request_id", None)

    # Log full exception for debugging
    logger.exception(
        "Unhandled exception request_id=%s path=%s",
        request_id,
        request.url.path,
    )

    return build_error_response(
        request=request,
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred. Please try again later.",
    )
