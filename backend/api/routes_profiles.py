"""
api/routes_profiles.py — Company profile management endpoints.

Endpoints
---------
POST   /api/profiles              Create a new profile
GET    /api/profiles              List all profiles
GET    /api/profiles/default      Get the default profile
GET    /api/profiles/{id}         Get a single profile
PUT    /api/profiles/{id}         Full update
PATCH  /api/profiles/{id}         Partial update
DELETE /api/profiles/{id}         Delete
POST   /api/profiles/{id}/set-default  Make this the default profile
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.db import crud, get_db
from backend.logger import get_logger
from backend.schemas.profile import (
    ProfileCreate,
    ProfileListResponse,
    ProfileResponse,
    ProfileUpdate,
)

router = APIRouter(prefix="/api/profiles", tags=["company-profiles"])
log = get_logger(__name__)


def _get_profile_or_404(profile_id: str, db: Session):
    profile = crud.get_profile(db, profile_id)
    if not profile:
        raise HTTPException(
            status_code=404, detail=f"Profile {profile_id!r} not found"
        )
    return profile


@router.post(
    "",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new company profile",
)
def create_profile(data: ProfileCreate, db: Session = Depends(get_db)) -> ProfileResponse:
    profile = crud.create_profile(db, data)
    log.info("Profile created", extra={"profile_id": profile.id, "name": profile.company_name})
    return ProfileResponse.model_validate(profile)


@router.get(
    "",
    response_model=ProfileListResponse,
    summary="List all company profiles",
)
def list_profiles(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ProfileListResponse:
    profiles = crud.list_profiles(db, skip=skip, limit=limit)
    return ProfileListResponse(items=profiles, total=len(profiles))


@router.get(
    "/default",
    response_model=ProfileResponse,
    summary="Get the default company profile",
)
def get_default_profile(db: Session = Depends(get_db)) -> ProfileResponse:
    profile = crud.get_default_profile(db)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No default profile set. Create a profile with is_default=true.",
        )
    return ProfileResponse.model_validate(profile)


@router.get(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="Get a single profile by ID",
)
def get_profile(profile_id: str, db: Session = Depends(get_db)) -> ProfileResponse:
    return ProfileResponse.model_validate(_get_profile_or_404(profile_id, db))


@router.put(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="Replace a company profile",
)
def update_profile(
    profile_id: str,
    data: ProfileCreate,
    db: Session = Depends(get_db),
) -> ProfileResponse:
    _get_profile_or_404(profile_id, db)
    update_data = ProfileUpdate(**data.model_dump())
    updated = crud.update_profile(db, profile_id, update_data)
    return ProfileResponse.model_validate(updated)


@router.patch(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="Partially update a company profile",
)
def patch_profile(
    profile_id: str,
    data: ProfileUpdate,
    db: Session = Depends(get_db),
) -> ProfileResponse:
    _get_profile_or_404(profile_id, db)
    updated = crud.update_profile(db, profile_id, data)
    return ProfileResponse.model_validate(updated)


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a company profile",
)
def delete_profile(profile_id: str, db: Session = Depends(get_db)) -> None:
    deleted = crud.delete_profile(db, profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id!r} not found")


@router.post(
    "/{profile_id}/set-default",
    response_model=ProfileResponse,
    summary="Mark a profile as the default",
)
def set_default_profile(profile_id: str, db: Session = Depends(get_db)) -> ProfileResponse:
    _get_profile_or_404(profile_id, db)
    updated = crud.update_profile(db, profile_id, ProfileUpdate(is_default=True))
    log.info("Default profile updated", extra={"profile_id": profile_id})
    return ProfileResponse.model_validate(updated)
