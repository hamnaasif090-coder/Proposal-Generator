"""
schemas/proposal.py — Pydantic v2 schemas for the Proposal domain.

Separating schemas from ORM models keeps the API contract explicit
and prevents accidental field leakage from the database layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Tone literal ───────────────────────────────────────────────────────────────
ToneLiteral = Literal["professional", "friendly", "technical", "executive"]
StatusLiteral = Literal["pending", "generating", "completed", "failed"]


# ═══════════════════════════════════════════════════════════════════════════════
# Request schemas  (API → backend)
# ═══════════════════════════════════════════════════════════════════════════════

class ProposalCreate(BaseModel):
    """Payload the Streamlit frontend POSTs to ``/api/proposals``."""

    client_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the client or organisation",
        examples=["Acme Corp"],
    )
    project_description: str = Field(
        ...,
        min_length=20,
        max_length=5000,
        description="What the project is about",
        examples=["Build a customer-facing e-commerce platform with real-time inventory."],
    )
    budget: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Budget range or fixed amount",
        examples=["$50,000 – $75,000"],
    )
    timeline: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Expected project duration",
        examples=["6 months"],
    )
    goals: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Key business goals or success criteria",
        examples=["Increase online sales by 30%, reduce cart abandonment, mobile-first UX."],
    )
    tone: ToneLiteral = Field(
        default="professional",
        description="Writing tone for the generated proposal",
    )
    company_profile_id: Optional[str] = Field(
        default=None,
        description="ID of a saved company profile to embed in the proposal",
    )

    @field_validator("client_name", "project_description", "budget", "timeline", "goals")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class ProposalSectionUpdate(BaseModel):
    """Internal schema used by ProposalBuilder to write generated sections."""

    executive_summary: Optional[str] = None
    technical_approach: Optional[str] = None
    milestones: Optional[str] = None
    estimated_timeline: Optional[str] = None
    pricing_structure: Optional[str] = None
    risks: Optional[str] = None
    deliverables: Optional[str] = None
    next_steps: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Response schemas  (backend → API)
# ═══════════════════════════════════════════════════════════════════════════════

class ProposalSections(BaseModel):
    """The eight generated sections of a proposal."""

    executive_summary: Optional[str] = None
    technical_approach: Optional[str] = None
    milestones: Optional[str] = None
    estimated_timeline: Optional[str] = None
    pricing_structure: Optional[str] = None
    risks: Optional[str] = None
    deliverables: Optional[str] = None
    next_steps: Optional[str] = None


class ProposalExportPaths(BaseModel):
    """File paths for the three export formats."""

    markdown_path: Optional[str] = None
    pdf_path: Optional[str] = None
    json_path: Optional[str] = None


class ProposalResponse(BaseModel):
    """Full proposal record returned to the frontend."""

    model_config = {"from_attributes": True}

    id: str
    client_name: str
    project_description: str
    budget: str
    timeline: str
    goals: str
    tone: ToneLiteral
    status: StatusLiteral
    error_message: Optional[str] = None
    company_profile_id: Optional[str] = None

    # Generated sections
    executive_summary: Optional[str] = None
    technical_approach: Optional[str] = None
    milestones: Optional[str] = None
    estimated_timeline: Optional[str] = None
    pricing_structure: Optional[str] = None
    risks: Optional[str] = None
    deliverables: Optional[str] = None
    next_steps: Optional[str] = None

    # Export paths
    markdown_path: Optional[str] = None
    pdf_path: Optional[str] = None
    json_path: Optional[str] = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    generation_duration_ms: Optional[int] = None

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"


class ProposalListItem(BaseModel):
    """Lightweight summary used in list views."""

    model_config = {"from_attributes": True}

    id: str
    client_name: str
    project_description: str
    budget: str
    timeline: str
    tone: ToneLiteral
    status: StatusLiteral
    created_at: datetime
    generation_duration_ms: Optional[int] = None


class ProposalListResponse(BaseModel):
    """Paginated list of proposals."""

    items: list[ProposalListItem]
    total: int
    skip: int
    limit: int


class GenerateResponse(BaseModel):
    """Immediate response after submitting a generation request."""

    proposal_id: str
    status: StatusLiteral
    message: str = "Proposal generation started"
