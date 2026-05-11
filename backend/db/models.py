"""
db/models.py — SQLAlchemy ORM models.

Tables
------
proposals        — every generated proposal, its inputs, outputs, and status.
company_profiles — reusable company context injected into prompt templates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base


# ── Helpers ────────────────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ── Proposal ───────────────────────────────────────────────────────────────────
class Proposal(Base):
    """Stores one complete proposal lifecycle: inputs → generation → outputs."""

    __tablename__ = "proposals"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid, index=True
    )

    # ── Input fields (what the user submitted) ─────────────────────────────
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_description: Mapped[str] = mapped_column(Text, nullable=False)
    budget: Mapped[str] = mapped_column(String(100), nullable=False)
    timeline: Mapped[str] = mapped_column(String(100), nullable=False)
    goals: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(
        Enum("professional", "friendly", "technical", "executive", name="tone_enum"),
        nullable=False,
        default="professional",
    )

    # ── Company profile (optional FK) ──────────────────────────────────────
    company_profile_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("company_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Generation status ──────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        Enum("pending", "generating", "completed", "failed", name="status_enum"),
        nullable=False,
        default="pending",
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Generated content (each section stored separately) ─────────────────
    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technical_approach: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    milestones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_timeline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pricing_structure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deliverables: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Export file paths ──────────────────────────────────────────────────
    markdown_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    json_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    generation_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    company_profile: Mapped[Optional["CompanyProfile"]] = relationship(
        "CompanyProfile", back_populates="proposals", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<Proposal id={self.id!r} client={self.client_name!r} "
            f"status={self.status!r}>"
        )

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"

    @property
    def has_all_sections(self) -> bool:
        sections = [
            self.executive_summary,
            self.technical_approach,
            self.milestones,
            self.estimated_timeline,
            self.pricing_structure,
            self.risks,
            self.deliverables,
            self.next_steps,
        ]
        return all(s is not None for s in sections)


# ── Company Profile ────────────────────────────────────────────────────────────
class CompanyProfile(Base):
    """Reusable company context injected into every proposal.

    Store your agency's name, tagline, services, and contact details once
    and reference them across proposals without re-entering.
    """

    __tablename__ = "company_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid, index=True
    )

    # ── Identity ───────────────────────────────────────────────────────────
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tagline: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Capabilities ───────────────────────────────────────────────────────
    services_offered: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    industries_served: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    team_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    years_in_business: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Social proof ───────────────────────────────────────────────────────
    notable_clients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    case_study_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Defaults ───────────────────────────────────────────────────────────
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    proposals: Mapped[list["Proposal"]] = relationship(
        "Proposal", back_populates="company_profile", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<CompanyProfile id={self.id!r} name={self.company_name!r}>"
