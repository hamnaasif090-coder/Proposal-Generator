"""
db/crud.py — Database helper functions (Create / Read / Update / Delete).

All functions accept a SQLAlchemy ``Session`` so they remain testable
and transport-agnostic (works with SQLite in tests, Postgres in production).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.db.models import CompanyProfile, Proposal
from backend.logger import get_logger
from backend.schemas.proposal import ProposalCreate, ProposalSectionUpdate
from backend.schemas.profile import ProfileCreate, ProfileUpdate

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Proposal CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_proposal(db: Session, data: ProposalCreate) -> Proposal:
    """Insert a new proposal row with status=pending."""
    proposal = Proposal(
        client_name=data.client_name,
        project_description=data.project_description,
        budget=data.budget,
        timeline=data.timeline,
        goals=data.goals,
        tone=data.tone,
        company_profile_id=data.company_profile_id,
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    log.info("Proposal created", extra={"proposal_id": proposal.id})
    return proposal


def get_proposal(db: Session, proposal_id: str) -> Optional[Proposal]:
    """Fetch a single proposal by ID. Returns None if not found."""
    return db.get(Proposal, proposal_id)


def list_proposals(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
) -> list[Proposal]:
    """Return proposals ordered by creation date (newest first)."""
    stmt = select(Proposal).order_by(desc(Proposal.created_at))
    if status:
        stmt = stmt.where(Proposal.status == status)
    stmt = stmt.offset(skip).limit(limit)
    return list(db.scalars(stmt))


def update_proposal_status(
    db: Session,
    proposal_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> Optional[Proposal]:
    """Update a proposal's status (and optional error message)."""
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return None
    proposal.status = status
    proposal.error_message = error_message
    proposal.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)
    return proposal


def update_proposal_sections(
    db: Session,
    proposal_id: str,
    sections: ProposalSectionUpdate,
    duration_ms: Optional[int] = None,
) -> Optional[Proposal]:
    """Write generated section content back to the proposal row."""
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return None

    section_map = {
        "executive_summary": sections.executive_summary,
        "technical_approach": sections.technical_approach,
        "milestones": sections.milestones,
        "estimated_timeline": sections.estimated_timeline,
        "pricing_structure": sections.pricing_structure,
        "risks": sections.risks,
        "deliverables": sections.deliverables,
        "next_steps": sections.next_steps,
    }
    for field, value in section_map.items():
        if value is not None:
            setattr(proposal, field, value)

    proposal.status = "completed"
    proposal.updated_at = datetime.now(timezone.utc)
    if duration_ms is not None:
        proposal.generation_duration_ms = duration_ms
    db.commit()
    db.refresh(proposal)
    log.info(
        "Proposal sections updated",
        extra={"proposal_id": proposal_id, "duration_ms": duration_ms},
    )
    return proposal


def update_proposal_export_paths(
    db: Session,
    proposal_id: str,
    markdown_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
    json_path: Optional[str] = None,
) -> Optional[Proposal]:
    """Store file paths after export files have been written to disk."""
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return None
    if markdown_path:
        proposal.markdown_path = markdown_path
    if pdf_path:
        proposal.pdf_path = pdf_path
    if json_path:
        proposal.json_path = json_path
    proposal.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)
    return proposal


def delete_proposal(db: Session, proposal_id: str) -> bool:
    """Hard-delete a proposal. Returns True if deleted, False if not found."""
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return False
    db.delete(proposal)
    db.commit()
    log.info("Proposal deleted", extra={"proposal_id": proposal_id})
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# CompanyProfile CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_profile(db: Session, data: ProfileCreate) -> CompanyProfile:
    """Create a new company profile. If ``is_default=True``, demote others."""
    if data.is_default:
        _clear_default_flags(db)

    profile = CompanyProfile(**data.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    log.info("Company profile created", extra={"profile_id": profile.id})
    return profile


def get_profile(db: Session, profile_id: str) -> Optional[CompanyProfile]:
    """Fetch a single profile by ID."""
    return db.get(CompanyProfile, profile_id)


def get_default_profile(db: Session) -> Optional[CompanyProfile]:
    """Return the profile marked as default, or None."""
    stmt = select(CompanyProfile).where(CompanyProfile.is_default.is_(True)).limit(1)
    return db.scalars(stmt).first()


def list_profiles(db: Session, skip: int = 0, limit: int = 50) -> list[CompanyProfile]:
    """Return all profiles ordered by creation date (newest first)."""
    stmt = (
        select(CompanyProfile)
        .order_by(desc(CompanyProfile.created_at))
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def update_profile(
    db: Session, profile_id: str, data: ProfileUpdate
) -> Optional[CompanyProfile]:
    """Partial update of an existing profile."""
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("is_default"):
        _clear_default_flags(db, exclude_id=profile_id)

    for field, value in update_data.items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


def delete_profile(db: Session, profile_id: str) -> bool:
    """Hard-delete a company profile."""
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        return False
    db.delete(profile)
    db.commit()
    log.info("Company profile deleted", extra={"profile_id": profile_id})
    return True


# ── Private helpers ────────────────────────────────────────────────────────────
def _clear_default_flags(db: Session, exclude_id: Optional[str] = None) -> None:
    """Remove ``is_default=True`` from all profiles (except ``exclude_id``)."""
    stmt = select(CompanyProfile).where(CompanyProfile.is_default.is_(True))
    if exclude_id:
        stmt = stmt.where(CompanyProfile.id != exclude_id)
    for profile in db.scalars(stmt):
        profile.is_default = False
    db.flush()
