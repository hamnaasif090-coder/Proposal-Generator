"""
core/llm_client.py — Async wrapper around the Anthropic Claude API.

Responsibilities
----------------
* Single-section generation (one API call per section).
* Full-proposal generation (all sections in parallel with asyncio.gather).
* Exponential-backoff retry on transient errors (rate limits, 5xx).
* Token usage tracking per call and aggregate.
* Clean error surfacing — never swallows exceptions silently.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from backend.config import settings
from backend.logger import get_logger

log = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 2.0      # doubles each retry: 2 → 4 → 8
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


# ── Data classes ───────────────────────────────────────────────────────────────
@dataclass
class LLMResponse:
    """A single Claude API response with metadata."""
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    duration_ms: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TokenUsage:
    """Aggregate token usage across multiple calls."""
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, response: LLMResponse) -> None:
        self.input_tokens += response.input_tokens
        self.output_tokens += response.output_tokens
        self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __str__(self) -> str:
        return (
            f"TokenUsage(calls={self.calls}, "
            f"input={self.input_tokens}, "
            f"output={self.output_tokens}, "
            f"total={self.total_tokens})"
        )


# ── Client ─────────────────────────────────────────────────────────────────────
class LLMClient:
    """Async Claude API client with retry, logging, and token tracking.

    Usage::

        client = LLMClient()

        # Single call
        response = await client.complete(system="...", user="...")

        # Multiple sections in parallel
        results = await client.complete_parallel([
            {"section": "executive_summary", "system": s, "user": u},
            ...
        ])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.anthropic_api_key,
        )
        self.model = model or settings.anthropic_model
        self.max_tokens = max_tokens or settings.anthropic_max_tokens
        self._usage = TokenUsage()
        log.info(
            "LLMClient initialised",
            extra={"model": self.model, "max_tokens": self.max_tokens},
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    async def complete(
        self,
        system: str,
        user: str,
        section_name: str = "unknown",
    ) -> LLMResponse:
        """Call Claude with retry logic. Returns an LLMResponse.

        Parameters
        ----------
        system : str       System prompt (rendered from template)
        user   : str       User-turn prompt (the section instructions)
        section_name : str For logging only
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._call_api(system, user, section_name, attempt)
                self._usage.add(response)
                return response

            except anthropic.RateLimitError as exc:
                last_exc = exc
                wait = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                log.warning(
                    "Rate limit hit — backing off",
                    extra={"section": section_name, "attempt": attempt, "wait_s": wait},
                )
                await asyncio.sleep(wait)

            except anthropic.APIStatusError as exc:
                if exc.status_code in _RETRYABLE_STATUS_CODES:
                    last_exc = exc
                    wait = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    log.warning(
                        "Retryable API error",
                        extra={
                            "section": section_name,
                            "status": exc.status_code,
                            "attempt": attempt,
                            "wait_s": wait,
                        },
                    )
                    await asyncio.sleep(wait)
                else:
                    log.error(
                        "Non-retryable API error",
                        extra={"section": section_name, "status": exc.status_code, "error": str(exc)},
                    )
                    raise

            except anthropic.APIConnectionError as exc:
                last_exc = exc
                wait = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                log.warning(
                    "Connection error — retrying",
                    extra={"section": section_name, "attempt": attempt, "wait_s": wait},
                )
                await asyncio.sleep(wait)

        log.error(
            "All retries exhausted",
            extra={"section": section_name, "attempts": _MAX_RETRIES},
        )
        raise RuntimeError(
            f"Claude API call failed after {_MAX_RETRIES} attempts "
            f"for section '{section_name}'"
        ) from last_exc

    async def complete_parallel(
        self,
        tasks: list[dict],
        max_concurrency: int = 4,
    ) -> dict[str, LLMResponse]:
        """Generate multiple sections concurrently.

        Parameters
        ----------
        tasks : list of dicts, each with keys:
            - section : str   (section name, used as result key)
            - system  : str   (rendered system prompt)
            - user    : str   (rendered section user prompt)
        max_concurrency : int
            Semaphore limit to avoid hammering the API.

        Returns
        -------
        dict mapping section name → LLMResponse
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded(task: dict) -> tuple[str, LLMResponse]:
            async with semaphore:
                section = task["section"]
                response = await self.complete(
                    system=task["system"],
                    user=task["user"],
                    section_name=section,
                )
                return section, response

        log.info(
            "Starting parallel generation",
            extra={"sections": [t["section"] for t in tasks], "concurrency": max_concurrency},
        )
        start = time.monotonic()
        results = await asyncio.gather(*[_bounded(t) for t in tasks])
        elapsed_ms = int((time.monotonic() - start) * 1000)

        log.info(
            "Parallel generation complete",
            extra={
                "sections": len(results),
                "duration_ms": elapsed_ms,
                "usage": str(self._usage),
            },
        )
        return dict(results)

    @property
    def usage(self) -> TokenUsage:
        """Cumulative token usage for this client instance."""
        return self._usage

    def reset_usage(self) -> None:
        """Reset token counters (useful between proposals in tests)."""
        self._usage = TokenUsage()

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _call_api(
        self,
        system: str,
        user: str,
        section_name: str,
        attempt: int,
    ) -> LLMResponse:
        """Make a single raw API call and return a structured LLMResponse."""
        start = time.monotonic()

        log.debug(
            "Calling Claude API",
            extra={
                "section": section_name,
                "model": self.model,
                "attempt": attempt,
                "system_chars": len(system),
                "user_chars": len(user),
            },
        )

        message = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        # Extract text from content blocks
        content = "\n".join(
            block.text
            for block in message.content
            if hasattr(block, "text")
        ).strip()

        response = LLMResponse(
            content=content,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            model=message.model,
            duration_ms=duration_ms,
        )

        log.info(
            "Claude API call succeeded",
            extra={
                "section": section_name,
                "duration_ms": duration_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "attempt": attempt,
            },
        )
        return response
