"""
core/prompt_engine.py — Loads, caches, and renders Jinja2 prompt templates.

Design decisions
----------------
* Templates live in /prompts as .j2 files — editable without touching Python.
* Jinja2 Environment is built once and cached; individual templates are loaded
  lazily and cached per name.
* Tone instructions are resolved from a registry here so prompt templates
  only reference ``{{ tone_instructions }}`` without duplicating tone copy.
* Rendering is synchronous (Jinja2 is CPU-bound and fast); no async needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    Template,
    TemplateNotFound,
)

from backend.config import settings
from backend.logger import get_logger

log = get_logger(__name__)

# ── Tone registry ──────────────────────────────────────────────────────────────
TONE_INSTRUCTIONS: dict[str, str] = {
    "professional": (
        "formal, precise, and authoritative. Use clear business language. "
        "Avoid jargon but maintain gravitas. Sentences are declarative and confident."
    ),
    "friendly": (
        "warm, approachable, and conversational. Use 'we' and 'you' freely. "
        "Contractions are welcome. The goal is to feel like a trusted partner, "
        "not a faceless vendor."
    ),
    "technical": (
        "detailed, evidence-based, and engineering-minded. Include specific "
        "technology names, architectural rationale, and performance considerations. "
        "The reader is technically literate — don't over-explain basics."
    ),
    "executive": (
        "concise, outcome-focused, and strategic. Lead with business value, "
        "not implementation detail. Use short paragraphs. Quantify impact wherever "
        "possible. An executive reads this in 90 seconds — make every word count."
    ),
}

# ── Section → template file mapping ───────────────────────────────────────────
SECTION_TEMPLATES: dict[str, str] = {
    "executive_summary":  "executive_summary.j2",
    "technical_approach": "technical_approach.j2",
    "milestones":         "milestones.j2",
    "pricing_structure":  "pricing_structure.j2",
    "risks":              "risks.j2",
    "deliverables":       "deliverables.j2",
    "next_steps":         "next_steps.j2",
}

SYSTEM_TEMPLATE = "system_prompt.j2"


class PromptEngine:
    """Renders Jinja2 prompt templates for proposal generation.

    Usage::

        engine = PromptEngine()
        system = engine.render_system_prompt(context)
        user   = engine.render_section("executive_summary", context)
    """

    def __init__(self, prompts_dir: Optional[Path] = None) -> None:
        self._dir = prompts_dir or settings.prompts_dir
        self._env = self._build_env()
        self._cache: dict[str, Template] = {}
        log.info("PromptEngine initialised", extra={"prompts_dir": str(self._dir)})

    # ── Public API ─────────────────────────────────────────────────────────────

    def render_system_prompt(self, context: dict[str, Any]) -> str:
        """Render the base system prompt with full project context."""
        return self._render(SYSTEM_TEMPLATE, context)

    def render_section(self, section: str, context: dict[str, Any]) -> str:
        """Render a named section's user-turn prompt.

        Parameters
        ----------
        section : str
            One of the keys in ``SECTION_TEMPLATES``.
        context : dict
            Must include at minimum: client_name, project_description,
            budget, timeline, goals, tone.

        Raises
        ------
        ValueError
            If ``section`` is not a known section name.
        """
        if section not in SECTION_TEMPLATES:
            raise ValueError(
                f"Unknown section {section!r}. "
                f"Valid sections: {list(SECTION_TEMPLATES)}"
            )
        return self._render(SECTION_TEMPLATES[section], context)

    def build_context(
        self,
        *,
        client_name: str,
        project_description: str,
        budget: str,
        timeline: str,
        goals: str,
        tone: str = "professional",
        company_profile: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Assemble the template rendering context from raw inputs.

        Returns a dict with all variables referenced across templates,
        including the resolved ``tone_instructions`` string.
        """
        return {
            "client_name": client_name,
            "project_description": project_description,
            "budget": budget,
            "timeline": timeline,
            "goals": goals,
            "tone": tone,
            "tone_instructions": TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["professional"]),
            "company_profile": company_profile,
        }

    def list_sections(self) -> list[str]:
        """Return the ordered list of all generatable sections."""
        return list(SECTION_TEMPLATES.keys())

    def get_template_source(self, section: str) -> str:
        """Return the raw template source for a section (used by the UI editor)."""
        if section == "system":
            template_file = SYSTEM_TEMPLATE
        elif section in SECTION_TEMPLATES:
            template_file = SECTION_TEMPLATES[section]
        else:
            raise ValueError(f"Unknown section: {section!r}")
        return (self._dir / template_file).read_text(encoding="utf-8")

    def save_template(self, section: str, source: str) -> None:
        """Overwrite a template file with new source (used by the UI editor).

        Clears the cached compiled template so the next render picks up
        the new source.
        """
        if section == "system":
            template_file = SYSTEM_TEMPLATE
        elif section in SECTION_TEMPLATES:
            template_file = SECTION_TEMPLATES[section]
        else:
            raise ValueError(f"Unknown section: {section!r}")

        path = self._dir / template_file
        path.write_text(source, encoding="utf-8")

        # Invalidate cache
        self._cache.pop(template_file, None)
        # Rebuild env so FileSystemLoader picks up the new file
        self._env = self._build_env()
        log.info("Template saved", extra={"section": section, "path": str(path)})

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_env(self) -> Environment:
        return Environment(
            loader=FileSystemLoader(str(self._dir)),
            undefined=StrictUndefined,   # raise on missing variables — fail fast
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def _render(self, template_name: str, context: dict[str, Any]) -> str:
        template = self._get_template(template_name)
        try:
            rendered = template.render(**context)
            log.debug(
                "Template rendered",
                extra={"template": template_name, "chars": len(rendered)},
            )
            return rendered.strip()
        except Exception as exc:
            log.error(
                "Template render failed",
                extra={"template": template_name, "error": str(exc)},
            )
            raise

    def _get_template(self, name: str) -> Template:
        if name not in self._cache:
            try:
                self._cache[name] = self._env.get_template(name)
            except TemplateNotFound:
                raise FileNotFoundError(
                    f"Prompt template not found: {self._dir / name}\n"
                    f"Make sure the /prompts directory contains all required .j2 files."
                )
        return self._cache[name]
