"""
core/proposal_builder.py — Orchestrates full proposal generation.

Workflow
--------
1. Receive a ProposalCreate payload + optional CompanyProfile ORM object.
2. Build the shared template context via PromptEngine.
3. Render one system prompt (shared) + 8 user-turn prompts (one per section).
4. Fire all 8 API calls in parallel via LLMClient.complete_parallel.
5. Assemble results into a ProposalSectionUpdate for the CRUD layer.
6. Return the sections + timing metadata to the caller (route handler).

The builder is stateless — instantiate once at app startup (lifespan),
then call ``generate()`` concurrently from multiple requests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from backend.core.llm_client import LLMClient, TokenUsage
from backend.core.prompt_engine import PromptEngine
from backend.db.models import CompanyProfile
from backend.logger import get_logger
from backend.schemas.proposal import ProposalCreate, ProposalSectionUpdate

log = get_logger(__name__)


# ── Result dataclass ───────────────────────────────────────────────────────────
@dataclass
class GenerationResult:
    """Full output from a single proposal generation run."""
    sections: ProposalSectionUpdate
    duration_ms: int
    usage: TokenUsage
    proposal_id: str


# ── Builder ────────────────────────────────────────────────────────────────────
class ProposalBuilder:
    """Orchestrates the end-to-end generation of a proposal.

    Usage (from a FastAPI route)::

        builder = ProposalBuilder()   # once at startup
        result  = await builder.generate(
            proposal_id="abc-123",
            data=proposal_create_schema,
            company_profile=profile_orm_obj,  # or None
        )
    """

    # All eight sections, in the order they appear in the final document
    SECTIONS = [
        "executive_summary",
        "technical_approach",
        "milestones",
        "pricing_structure",
        "risks",
        "deliverables",
        "next_steps",
    ]

    def __init__(
        self,
        prompt_engine: Optional[PromptEngine] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self._engine = prompt_engine or PromptEngine()
        self._client = llm_client or LLMClient()
        log.info("ProposalBuilder initialised")

    # ── Public API ─────────────────────────────────────────────────────────────

    async def generate(
        self,
        proposal_id: str,
        data: ProposalCreate,
        company_profile: Optional[CompanyProfile] = None,
    ) -> GenerationResult:
        """Generate all proposal sections and return structured results.

        Parameters
        ----------
        proposal_id    : str               Used for log correlation.
        data           : ProposalCreate    User-submitted form data.
        company_profile: CompanyProfile?   ORM object, may be None.

        Returns
        -------
        GenerationResult with all sections populated and token usage.

        Raises
        ------
        RuntimeError   If the LLM call fails after all retries.
        """
        start = time.monotonic()
        log.info(
            "Proposal generation started",
            extra={
                "proposal_id": proposal_id,
                "client": data.client_name,
                "tone": data.tone,
                "sections": len(self.SECTIONS),
            },
        )

        # 1. Build shared context dict
        context = self._engine.build_context(
            client_name=data.client_name,
            project_description=data.project_description,
            budget=data.budget,
            timeline=data.timeline,
            goals=data.goals,
            tone=data.tone,
            company_profile=company_profile,
        )

        # 2. Render system prompt (same for all sections)
        system_prompt = self._engine.render_system_prompt(context)

        # 3. Render all user-turn prompts
        tasks = []
        for section in self.SECTIONS:
            user_prompt = self._engine.render_section(section, context)
            tasks.append({
                "section": section,
                "system": system_prompt,
                "user": user_prompt,
            })

        # 4. Fire all calls in parallel
        try:
            responses = await self._client.complete_parallel(
                tasks,
                max_concurrency=min(4, len(tasks)),
            )
        except Exception as exc:
            log.error(
                "Proposal generation failed",
                extra={"proposal_id": proposal_id, "error": str(exc)},
            )
            raise

        # 5. Assemble sections
        sections = ProposalSectionUpdate(
            executive_summary=responses["executive_summary"].content,
            technical_approach=responses["technical_approach"].content,
            milestones=responses["milestones"].content,
            # Note: estimated_timeline is derived from milestones in the full doc
            estimated_timeline=self._extract_timeline_summary(
                responses["milestones"].content,
                data.timeline,
            ),
            pricing_structure=responses["pricing_structure"].content,
            risks=responses["risks"].content,
            deliverables=responses["deliverables"].content,
            next_steps=responses["next_steps"].content,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        usage = self._client.usage

        log.info(
            "Proposal generation complete",
            extra={
                "proposal_id": proposal_id,
                "duration_ms": duration_ms,
                "total_tokens": usage.total_tokens,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
        )

        return GenerationResult(
            sections=sections,
            duration_ms=duration_ms,
            usage=usage,
            proposal_id=proposal_id,
        )

    async def regenerate_section(
        self,
        section: str,
        data: ProposalCreate,
        company_profile: Optional[CompanyProfile] = None,
    ) -> str:
        """Re-generate a single section (used by the UI's 'Regenerate' button).

        Returns the raw section content string.
        """
        if section not in self.SECTIONS:
            raise ValueError(f"Unknown section: {section!r}")

        context = self._engine.build_context(
            client_name=data.client_name,
            project_description=data.project_description,
            budget=data.budget,
            timeline=data.timeline,
            goals=data.goals,
            tone=data.tone,
            company_profile=company_profile,
        )
        system_prompt = self._engine.render_system_prompt(context)
        user_prompt = self._engine.render_section(section, context)

        log.info(
            "Regenerating single section",
            extra={"section": section, "client": data.client_name},
        )
        response = await self._client.complete(
            system=system_prompt,
            user=user_prompt,
            section_name=section,
        )
        return response.content

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_timeline_summary(milestones_content: str, raw_timeline: str) -> str:
        """Derive a concise estimated timeline string from the milestones section.

        This is stored separately so the frontend can display it in a summary
        card without parsing the full milestones markdown.
        """
        # Count milestones by counting ### headers (at start of line)
        import re
        milestone_count = len(re.findall(r"^###\s", milestones_content, re.MULTILINE))
        return (
            f"**Total duration:** {raw_timeline} across "
            f"{milestone_count} milestone{'s' if milestone_count != 1 else ''}. "
            f"See Milestones section for full breakdown."
        )
