"""
api/routes_proposals.py — Proposal generation and management endpoints.

Endpoints
---------
POST   /api/proposals/generate        Submit inputs → kick off generation
GET    /api/proposals                  List all proposals (paginated)
GET    /api/proposals/{id}             Get single proposal
DELETE /api/proposals/{id}             Delete proposal
POST   /api/proposals/{id}/regenerate  Re-generate a single section
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.proposal_builder import ProposalBuilder
from backend.db import crud, get_db
from backend.db.models import CompanyProfile
from backend.logger import get_logger
from backend.schemas.proposal import (
    GenerateResponse,
    ProposalCreate,
    ProposalListResponse,
    ProposalResponse,
)

router = APIRouter(prefix="/api/proposals", tags=["proposals"])
log = get_logger(__name__)

# Shared builder instance (stateless — safe for concurrent use)
_builder = ProposalBuilder()


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_proposal_or_404(proposal_id: str, db: Session) -> object:
    proposal = crud.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id!r} not found")
    return proposal


# ── Background task ────────────────────────────────────────────────────────────

async def _run_generation(proposal_id: str, data: ProposalCreate, db: Session) -> None:
    """Background task: generate all sections and persist results."""
    from backend.core.export_service import ExportService

    crud.update_proposal_status(db, proposal_id, "generating")

    try:
        # Load company profile if requested
        company_profile: Optional[CompanyProfile] = None
        if data.company_profile_id:
            company_profile = crud.get_profile(db, data.company_profile_id)

        # Generate
        result = await _builder.generate(
            proposal_id=proposal_id,
            data=data,
            company_profile=company_profile,
        )

        # Persist sections
        crud.update_proposal_sections(
            db, proposal_id, result.sections, duration_ms=result.duration_ms
        )

        # Auto-export all formats
        proposal = crud.get_proposal(db, proposal_id)
        if proposal:
            service = ExportService()
            paths = service.export_all(proposal)
            crud.update_proposal_export_paths(
                db,
                proposal_id,
                markdown_path=paths.get("markdown"),
                pdf_path=paths.get("pdf"),
                json_path=paths.get("json"),
            )

        log.info("Background generation complete", extra={"proposal_id": proposal_id})

    except Exception as exc:
        log.error(
            "Background generation failed",
            extra={"proposal_id": proposal_id, "error": str(exc)},
        )
        crud.update_proposal_status(
            db, proposal_id, "failed", error_message=str(exc)
        )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new proposal for generation",
)
async def generate_proposal(
    data: ProposalCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> GenerateResponse:
    """Accept proposal inputs and kick off async generation.

    Returns immediately with a ``proposal_id`` that the client can poll
    via ``GET /api/proposals/{id}`` to track progress.
    """
    proposal = crud.create_proposal(db, data)
    background_tasks.add_task(_run_generation, proposal.id, data, db)

    log.info(
        "Proposal generation queued",
        extra={"proposal_id": proposal.id, "client": data.client_name},
    )
    return GenerateResponse(
        proposal_id=proposal.id,
        status="pending",
        message="Proposal generation started. Poll GET /api/proposals/{id} for status.",
    )


@router.get(
    "",
    response_model=ProposalListResponse,
    summary="List all proposals",
)
def list_proposals(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    db: Session = Depends(get_db),
) -> ProposalListResponse:
    proposals = crud.list_proposals(db, skip=skip, limit=limit, status=status)
    return ProposalListResponse(
        items=proposals,
        total=len(proposals),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{proposal_id}",
    response_model=ProposalResponse,
    summary="Get a single proposal by ID",
)
def get_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
) -> ProposalResponse:
    proposal = _get_proposal_or_404(proposal_id, db)
    return ProposalResponse.model_validate(proposal)


@router.delete(
    "/{proposal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a proposal",
)
def delete_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
) -> None:
    deleted = crud.delete_proposal(db, proposal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id!r} not found")


@router.post(
    "/{proposal_id}/regenerate",
    response_model=dict,
    summary="Re-generate a single section",
)
async def regenerate_section(
    proposal_id: str,
    section: str = Query(..., description="Section name to regenerate"),
    db: Session = Depends(get_db),
) -> dict:
    """Re-generate one section of an existing completed proposal.

    Useful when the client wants a different tone or more detail
    on a specific section without regenerating the entire proposal.
    """
    proposal = _get_proposal_or_404(proposal_id, db)

    if proposal.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot regenerate sections on a proposal with status '{proposal.status}'",
        )

    # Re-use original inputs
    from backend.schemas.proposal import ProposalCreate
    data = ProposalCreate(
        client_name=proposal.client_name,
        project_description=proposal.project_description,
        budget=proposal.budget,
        timeline=proposal.timeline,
        goals=proposal.goals,
        tone=proposal.tone,
        company_profile_id=proposal.company_profile_id,
    )

    company_profile = None
    if proposal.company_profile_id:
        company_profile = crud.get_profile(db, proposal.company_profile_id)

    new_content = await _builder.regenerate_section(
        section=section,
        data=data,
        company_profile=company_profile,
    )

    # Patch the specific field
    from backend.schemas.proposal import ProposalSectionUpdate
    patch = ProposalSectionUpdate(**{section: new_content})
    crud.update_proposal_sections(db, proposal_id, patch)

    return {"section": section, "content": new_content, "proposal_id": proposal_id}
