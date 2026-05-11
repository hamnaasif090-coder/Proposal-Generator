"""
main.py — FastAPI application entry point.

Run with:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

Or via the convenience script:
    python -m backend.main
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import export_router, profiles_router, proposals_router
from backend.config import settings
from backend.db.database import init_db
from backend.logger import configure_logging, get_logger
from backend.middleware import register_exception_handlers, register_middleware

log = get_logger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown logic for the FastAPI app."""
    # ── Startup ────────────────────────────────────────────────────────────────
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        logs_dir=settings.logs_dir,
    )
    log.info(
        "Starting up",
        extra={
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )

    # Ensure runtime directories exist
    settings.ensure_directories()

    # Initialise database (create tables if missing)
    init_db()

    log.info("Application ready", extra={"port": settings.backend_port})
    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    log.info("Shutting down", extra={"app": settings.app_name})


# ── App factory ────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered business proposal generator. "
            "Convert raw client requirements into professional proposals automatically."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware ──────────────────────────────────────────────────────
    register_middleware(app)
    register_exception_handlers(app)

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(proposals_router)
    app.include_router(export_router)
    app.include_router(profiles_router)

    # ── Health & meta endpoints ────────────────────────────────────────────────
    @app.get("/health", tags=["meta"], summary="Health check")
    def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        }

    @app.get("/", tags=["meta"], summary="API root")
    def root() -> dict:
        return {
            "message": f"Welcome to {settings.app_name}",
            "version": settings.app_version,
            "docs": "/docs",
        }

    return app


# ── Module-level app instance (used by uvicorn) ────────────────────────────────
app = create_app()


# ── Dev runner ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
