"""
schemas/profile.py — Pydantic v2 schemas for the CompanyProfile domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Request schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileCreate(BaseModel):
    """Payload for creating a new company profile."""

    company_name: str = Field(
        ..., min_length=1, max_length=255, examples=["Axiom Digital Agency"]
    )
    tagline: Optional[str] = Field(
        default=None, max_length=500, examples=["We build things that scale."]
    )
    website: Optional[str] = Field(
        default=None, max_length=255, examples=["https://axiomdigital.io"]
    )
    contact_email: Optional[str] = Field(
        default=None, max_length=255, examples=["hello@axiomdigital.io"]
    )
    contact_phone: Optional[str] = Field(
        default=None, max_length=50, examples=["+1 (555) 000-1234"]
    )
    address: Optional[str] = Field(
        default=None, examples=["123 Tech Street, San Francisco, CA 94105"]
    )
    services_offered: Optional[str] = Field(
        default=None,
        examples=["Web development, mobile apps, cloud architecture, UI/UX design"],
    )
    industries_served: Optional[str] = Field(
        default=None, examples=["FinTech, HealthTech, E-commerce, SaaS"]
    )
    team_size: Optional[str] = Field(default=None, examples=["25–50"])
    years_in_business: Optional[int] = Field(default=None, ge=0, le=200)
    notable_clients: Optional[str] = Field(
        default=None, examples=["Stripe, Shopify, Twilio"]
    )
    case_study_summary: Optional[str] = Field(
        default=None,
        examples=["Built a real-time payments dashboard for FinPay, reducing reconciliation time by 60%."],
    )
    is_default: bool = Field(
        default=False, description="Mark as the default profile for new proposals"
    )

    @field_validator("company_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class ProfileUpdate(BaseModel):
    """Partial update — all fields optional."""

    company_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tagline: Optional[str] = Field(default=None, max_length=500)
    website: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = None
    services_offered: Optional[str] = None
    industries_served: Optional[str] = None
    team_size: Optional[str] = Field(default=None, max_length=50)
    years_in_business: Optional[int] = Field(default=None, ge=0, le=200)
    notable_clients: Optional[str] = None
    case_study_summary: Optional[str] = None
    is_default: Optional[bool] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Response schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileResponse(BaseModel):
    """Full profile record returned to callers."""

    model_config = {"from_attributes": True}

    id: str
    company_name: str
    tagline: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    services_offered: Optional[str] = None
    industries_served: Optional[str] = None
    team_size: Optional[str] = None
    years_in_business: Optional[int] = None
    notable_clients: Optional[str] = None
    case_study_summary: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ProfileListResponse(BaseModel):
    """List of company profiles."""

    items: list[ProfileResponse]
    total: int
