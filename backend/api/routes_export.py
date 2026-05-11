"""
api/routes_export.py — File download endpoints for generated proposals.

Endpoints
---------
GET /api/export/{proposal_id}/markdown   Stream the .md file
GET /api/export/{proposal_id}/pdf        Stream the .pdf file
GET /api/export/{proposal_id}/json       Stream the .json file
GET /api/export/{proposal_id}/status     Check which formats are ready
POST /api/export/{proposal_id}/regenerate-files  Re-export all formats from DB
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.core.export_service import ExportService
from backend.db import crud, get_db
from backend.logger import get_logger

router = APIRouter(prefix="/api/export", tags=["export"])
log = get_logger(__name__)
_export_service = ExportService()


def _get_completed_proposal(proposal_id: str, db: Session):
    proposal = crud.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id!r} not found")
    if proposal.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is not complete yet (status: {proposal.status}). "
                   "Wait for generation to finish before exporting.",
        )
    return proposal


@router.get("/{proposal_id}/markdown", summary="Download proposal as Markdown")
def download_markdown(proposal_id: str, db: Session = Depends(get_db)) -> FileResponse:
    proposal = _get_completed_proposal(proposal_id, db)

    # Regenerate if path missing or file deleted
    if not proposal.markdown_path or not Path(proposal.markdown_path).exists():
        path = _export_service.export_markdown(proposal)
        crud.update_proposal_export_paths(db, proposal_id, markdown_path=path)
    else:
        path = proposal.markdown_path

    filename = f"proposal_{proposal.client_name.replace(' ', '_')}.md"
    return FileResponse(path=path, media_type="text/markdown", filename=filename)


@router.get("/{proposal_id}/pdf", summary="Download proposal as PDF")
def download_pdf(proposal_id: str, db: Session = Depends(get_db)) -> FileResponse:
    proposal = _get_completed_proposal(proposal_id, db)

    if not proposal.pdf_path or not Path(proposal.pdf_path).exists():
        path = _export_service.export_pdf(proposal)
        crud.update_proposal_export_paths(db, proposal_id, pdf_path=path)
    else:
        path = proposal.pdf_path

    filename = f"proposal_{proposal.client_name.replace(' ', '_')}.pdf"
    return FileResponse(path=path, media_type="application/pdf", filename=filename)


@router.get("/{proposal_id}/json", summary="Download proposal metadata as JSON")
def download_json(proposal_id: str, db: Session = Depends(get_db)) -> FileResponse:
    proposal = _get_completed_proposal(proposal_id, db)

    if not proposal.json_path or not Path(proposal.json_path).exists():
        path = _export_service.export_json(proposal)
        crud.update_proposal_export_paths(db, proposal_id, json_path=path)
    else:
        path = proposal.json_path

    filename = f"proposal_{proposal.client_name.replace(' ', '_')}.json"
    return FileResponse(path=path, media_type="application/json", filename=filename)


@router.get("/{proposal_id}/status", summary="Check export file availability")
def export_status(proposal_id: str, db: Session = Depends(get_db)) -> dict:
    proposal = crud.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return {
        "proposal_id": proposal_id,
        "proposal_status": proposal.status,
        "exports": {
            "markdown": {
                "path": proposal.markdown_path,
                "available": bool(
                    proposal.markdown_path and Path(proposal.markdown_path).exists()
                ),
            },
            "pdf": {
                "path": proposal.pdf_path,
                "available": bool(
                    proposal.pdf_path and Path(proposal.pdf_path).exists()
                ),
            },
            "json": {
                "path": proposal.json_path,
                "available": bool(
                    proposal.json_path and Path(proposal.json_path).exists()
                ),
            },
        },
    }


@router.post("/{proposal_id}/regenerate-files", summary="Re-export all formats")
def regenerate_export_files(proposal_id: str, db: Session = Depends(get_db)) -> dict:
    """Force re-export all formats from the current DB state."""
    proposal = _get_completed_proposal(proposal_id, db)
    paths = _export_service.export_all(proposal)
    crud.update_proposal_export_paths(
        db,
        proposal_id,
        markdown_path=paths.get("markdown"),
        pdf_path=paths.get("pdf"),
        json_path=paths.get("json"),
    )
    log.info("Export files regenerated", extra={"proposal_id": proposal_id})
    return {"proposal_id": proposal_id, "paths": paths}
