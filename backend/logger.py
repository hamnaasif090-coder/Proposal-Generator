"""
logger.py — Centralised, structured logging for the entire backend.

Usage:
    from backend.logger import get_logger
    log = get_logger(__name__)
    log.info("Proposal generated", extra={"proposal_id": "abc123", "duration_ms": 420})

Features
--------
* JSON format in staging/production, human-readable text in development.
* Rotating file handler (10 MB / 5 backups).
* Automatic ``request_id`` injection via contextvars (set in middleware).
* Single ``configure_logging()`` call at app startup wires everything up.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Context var for per-request tracing ───────────────────────────────────────
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


# ── JSON formatter ─────────────────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    _RESERVED = frozenset(logging.LogRecord(
        "", 0, "", 0, "", (), None
    ).__dict__.keys()) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        record.message = record.getMessage()

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "request_id": get_request_id(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        # Attach any extra fields the caller passed
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


# ── Text formatter ─────────────────────────────────────────────────────────────
class TextFormatter(logging.Formatter):
    """Human-readable coloured formatter for local development."""

    COLOURS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = self.COLOURS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        rid = get_request_id()
        base = (
            f"{colour}{ts} [{record.levelname:<8}]{self.RESET} "
            f"[{record.name}] [{rid}] {record.getMessage()}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ── Public API ─────────────────────────────────────────────────────────────────
def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    logs_dir: Path = Path("logs"),
) -> None:
    """Wire up root logger with console + rotating file handlers.

    Call this ONCE at application startup (inside FastAPI lifespan).

    Parameters
    ----------
    level:    One of DEBUG / INFO / WARNING / ERROR / CRITICAL.
    fmt:      ``"json"`` for structured output, ``"text"`` for dev-friendly.
    logs_dir: Directory for the rotating log file.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    formatter: logging.Formatter
    if fmt == "json":
        formatter = JsonFormatter()
    else:
        formatter = TextFormatter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    # Rotating file handler — 10 MB × 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid duplicate handlers on hot-reload
    if not root.handlers:
        root.addHandler(console)
        root.addHandler(file_handler)
    else:
        root.handlers.clear()
        root.addHandler(console)
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpcore", "httpx", "anthropic", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging configured",
        extra={"level": level, "format": fmt, "log_file": str(log_file)},
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Always prefer this over ``logging.getLogger`` directly so callers
    don't need to import the logging stdlib themselves.
    """
    return logging.getLogger(name)
