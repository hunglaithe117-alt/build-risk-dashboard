"""Request logging middleware to trace requests, durations and identity.

- Adds a unique X-Request-ID header to responses (and uses any incoming header)
- Logs method, path, status, duration, client IP, user subject (from cookie/jwt)
- Does not log request/response bodies to avoid leaking sensitive data
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from jose import jwt
from jose.exceptions import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request/response metadata for tracing.

    Safe defaults: does not print request/response bodies or headers that may
    contain secrets. Extracts a `sub` claim from JWT if available to include
    the active user id in logs.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        start = time.monotonic()

        # Request id
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id

        # Determine user from cookie or authorization header
        user_sub: Optional[str] = None
        jwt_token = None
        # Prefer cookie (set in OAuth flow) then Authorization header
        if "access_token" in request.cookies:
            jwt_token = request.cookies.get("access_token")
        else:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.lower().startswith("bearer "):
                jwt_token = auth_header.split(None, 1)[1]

        if jwt_token:
            try:
                payload = jwt.decode(
                    jwt_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
                )
                user_sub = payload.get("sub")
            except JWTError:
                # Not valid or expired — don't fail the request
                user_sub = None

        # Call the downstream handler
        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - we still want to log then reraise
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.exception(
                "Unhandled exception during request: method=%s path=%s client=%s req_id=%s duration_ms=%d user=%s",
                request.method,
                request.url.path,
                request.client.host if request.client else None,
                request_id,
                duration_ms,
                user_sub,
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "request method=%s path=%s status=%s duration_ms=%d client=%s req_id=%s user=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.client.host if request.client else None,
            request_id,
            user_sub,
        )

        # Return request-id to client so traces can be correlated externally
        response.headers.setdefault("X-Request-ID", request_id)
        return response
