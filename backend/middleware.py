"""
middleware.py — FastAPI middleware stack.

Middleware (applied in reverse order — bottom runs first):
1. RequestIDMiddleware  — injects a UUID into every request for log tracing
2. TimingMiddleware     — logs request duration on every response
3. Global exception handler — converts unhandled exceptions to JSON 500s
"""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.logger import get_logger, set_request_id

log = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a UUID to every request and propagate it in the response header.

    The ID is stored in a ContextVar so all log statements within the
    request automatically include it via the JsonFormatter.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        log.info(
            "Request handled",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        return response


def register_middleware(app: FastAPI) -> None:
    """Attach all middleware to the FastAPI app."""
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.error(
            "Unhandled exception",
            extra={
                "method": request.method,
                "path": request.url.path,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal server error occurred.",
                "error_type": type(exc).__name__,
            },
        )
