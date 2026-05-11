"""
core/export_service.py — Exports a completed proposal to Markdown, PDF, and JSON.

Formats
-------
* Markdown (.md)  — clean, structured document ready for GitHub, Notion, etc.
* PDF     (.pdf)  — print-ready via WeasyPrint (HTML → PDF pipeline).
* JSON    (.json) — machine-readable metadata + all section content.

All files are written to ``settings.generated_dir / {proposal_id}/``.
The service returns the three file paths for storage in the database.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import markdown as md_lib
from weasyprint import CSS, HTML

from backend.config import settings
from backend.db.models import Proposal
from backend.logger import get_logger

log = get_logger(__name__)

# ── Section display order and labels ──────────────────────────────────────────
SECTION_ORDER = [
    ("executive_summary",  "Executive Summary"),
    ("technical_approach", "Technical Approach"),
    ("milestones",         "Project Milestones"),
    ("estimated_timeline", "Estimated Timeline"),
    ("pricing_structure",  "Pricing Structure"),
    ("risks",              "Risk Assessment"),
    ("deliverables",       "Deliverables"),
    ("next_steps",         "Next Steps"),
]


# ── PDF stylesheet ─────────────────────────────────────────────────────────────
_PDF_CSS = CSS(string="""
    @page {
        size: A4;
        margin: 2.2cm 2.5cm;
        @bottom-right {
            content: "Page " counter(page) " of " counter(pages);
            font-size: 9pt;
            color: #888;
        }
    }
    body {
        font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
        font-size: 10.5pt;
        line-height: 1.65;
        color: #1a1a1a;
    }
    h1 { font-size: 22pt; color: #0f1923; border-bottom: 2px solid #0057b7;
         padding-bottom: 6pt; margin-top: 0; }
    h2 { font-size: 15pt; color: #0057b7; margin-top: 28pt; margin-bottom: 4pt; }
    h3 { font-size: 12pt; color: #2d3a4a; margin-top: 16pt; margin-bottom: 2pt; }
    p  { margin: 6pt 0; }
    ul, ol { margin: 6pt 0 6pt 18pt; padding: 0; }
    li { margin-bottom: 3pt; }
    strong { color: #0f1923; }
    .meta-block {
        background: #f4f7fb;
        border-left: 4px solid #0057b7;
        padding: 10pt 14pt;
        margin: 16pt 0;
        border-radius: 3pt;
    }
    .meta-block p { margin: 2pt 0; font-size: 9.5pt; }
    .section-break { page-break-before: always; }
    hr { border: none; border-top: 1px solid #dde3ec; margin: 18pt 0; }
    code { background: #f0f3f7; padding: 1pt 4pt; border-radius: 2pt;
           font-size: 9pt; font-family: "Courier New", monospace; }
    pre  { background: #f0f3f7; padding: 10pt; border-radius: 4pt;
           overflow-x: auto; font-size: 9pt; }
""")


class ExportService:
    """Converts a completed Proposal ORM object into exportable files.

    Usage::

        service = ExportService()
        paths   = await service.export_all(proposal)
        # paths = {"markdown": "...", "pdf": "...", "json": "..."}
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._base_dir = output_dir or settings.generated_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def export_all(self, proposal: Proposal) -> dict[str, str]:
        """Export to all three formats. Returns dict of format → file path."""
        output_dir = self._proposal_dir(proposal.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths: dict[str, str] = {}

        markdown_content = self._build_markdown(proposal)

        # 1. Markdown
        md_path = output_dir / f"proposal_{proposal.id}.md"
        md_path.write_text(markdown_content, encoding="utf-8")
        paths["markdown"] = str(md_path)
        log.info("Markdown exported", extra={"proposal_id": proposal.id, "path": str(md_path)})

        # 2. PDF (via HTML intermediate)
        try:
            pdf_path = output_dir / f"proposal_{proposal.id}.pdf"
            self._write_pdf(markdown_content, proposal, pdf_path)
            paths["pdf"] = str(pdf_path)
            log.info("PDF exported", extra={"proposal_id": proposal.id, "path": str(pdf_path)})
        except Exception as exc:
            log.error("PDF export failed", extra={"proposal_id": proposal.id, "error": str(exc)})
            paths["pdf"] = ""

        # 3. JSON
        json_path = output_dir / f"proposal_{proposal.id}.json"
        self._write_json(proposal, json_path)
        paths["json"] = str(json_path)
        log.info("JSON exported", extra={"proposal_id": proposal.id, "path": str(json_path)})

        return paths

    def export_markdown(self, proposal: Proposal) -> str:
        """Export to Markdown only. Returns file path."""
        output_dir = self._proposal_dir(proposal.id)
        output_dir.mkdir(parents=True, exist_ok=True)
        content = self._build_markdown(proposal)
        path = output_dir / f"proposal_{proposal.id}.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def export_pdf(self, proposal: Proposal) -> str:
        """Export to PDF only. Returns file path."""
        output_dir = self._proposal_dir(proposal.id)
        output_dir.mkdir(parents=True, exist_ok=True)
        content = self._build_markdown(proposal)
        path = output_dir / f"proposal_{proposal.id}.pdf"
        self._write_pdf(content, proposal, path)
        return str(path)

    def export_json(self, proposal: Proposal) -> str:
        """Export to JSON only. Returns file path."""
        output_dir = self._proposal_dir(proposal.id)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"proposal_{proposal.id}.json"
        self._write_json(proposal, path)
        return str(path)

    def get_markdown_content(self, proposal: Proposal) -> str:
        """Return the Markdown string without writing to disk."""
        return self._build_markdown(proposal)

    # ── Markdown builder ───────────────────────────────────────────────────────

    def _build_markdown(self, proposal: Proposal) -> str:
        now = datetime.now(timezone.utc).strftime("%B %d, %Y")
        lines: list[str] = []

        # Title block
        lines += [
            f"# Proposal for {proposal.client_name}",
            "",
            f"> **Prepared by:** {'Our Agency'}  ",
            f"> **Date:** {now}  ",
            f"> **Budget:** {proposal.budget}  ",
            f"> **Timeline:** {proposal.timeline}  ",
            f"> **Tone:** {proposal.tone.capitalize()}  ",
            f"> **Reference:** `{proposal.id}`",
            "",
            "---",
            "",
        ]

        # Each section
        for i, (field_name, display_name) in enumerate(SECTION_ORDER):
            content = getattr(proposal, field_name, None)
            if not content:
                continue

            if i > 0:
                lines.append("")

            lines += [
                f"## {display_name}",
                "",
                content.strip(),
                "",
            ]

        # Footer
        lines += [
            "---",
            "",
            f"*This proposal was generated on {now} and is valid for 30 days.*",
        ]

        return "\n".join(lines)

    # ── PDF builder ────────────────────────────────────────────────────────────

    def _write_pdf(self, markdown_content: str, proposal: Proposal, path: Path) -> None:
        """Convert Markdown → HTML → PDF via WeasyPrint."""
        body_html = md_lib.markdown(
            markdown_content,
            extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        )

        # Add section-break class to h2 elements (except the first)
        body_html = self._inject_page_breaks(body_html)

        html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Proposal — {proposal.client_name}</title>
</head>
<body>
{body_html}
</body>
</html>"""

        HTML(string=html_doc).write_pdf(str(path), stylesheets=[_PDF_CSS])

    @staticmethod
    def _inject_page_breaks(html: str) -> str:
        """Add page-break class to every <h2> after the first."""
        count = 0

        def replacer(m: re.Match) -> str:
            nonlocal count
            count += 1
            if count == 1:
                return m.group(0)
            return m.group(0).replace("<h2", '<h2 class="section-break"', 1)

        return re.sub(r"<h2[^>]*>", replacer, html)

    # ── JSON builder ───────────────────────────────────────────────────────────

    def _write_json(self, proposal: Proposal, path: Path) -> None:
        """Serialize proposal to structured JSON metadata + content."""
        payload = {
            "metadata": {
                "proposal_id": proposal.id,
                "client_name": proposal.client_name,
                "budget": proposal.budget,
                "timeline": proposal.timeline,
                "tone": proposal.tone,
                "status": proposal.status,
                "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
                "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
                "generation_duration_ms": proposal.generation_duration_ms,
                "company_profile_id": proposal.company_profile_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            },
            "inputs": {
                "project_description": proposal.project_description,
                "goals": proposal.goals,
            },
            "sections": {
                field_name: getattr(proposal, field_name, None)
                for field_name, _ in SECTION_ORDER
            },
            "export_paths": {
                "markdown": proposal.markdown_path,
                "pdf": proposal.pdf_path,
                "json": str(path),
            },
        }

        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _proposal_dir(self, proposal_id: str) -> Path:
        return self._base_dir / proposal_id
