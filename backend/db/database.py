"""
db/database.py — SQLAlchemy engine, session factory, and base model.

Usage (in a FastAPI route):
    from backend.db.database import get_db
    def my_route(db: Session = Depends(get_db)):
        ...
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings
from backend.logger import get_logger

log = get_logger(__name__)

# ── Engine ─────────────────────────────────────────────────────────────────────
_connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    # SQLite: enable WAL mode + foreign keys per connection
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=settings.debug,          # SQL logging in debug mode only
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


# ── Session factory ────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── Declarative base ───────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Common declarative base for all ORM models."""
    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """Yield a database session and guarantee cleanup.

    Use as a FastAPI ``Depends`` injection:

        def route(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Startup helper ─────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create all tables defined in ORM models (idempotent).

    Called once during FastAPI lifespan startup.
    Import all model modules BEFORE calling this so their metadata
    is registered on ``Base``.
    """
    # Import models so their metadata is registered
    from backend.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    log.info("Database initialised", extra={"url": settings.database_url})
