"""Gemini API client with structured output support."""

from __future__ import annotations

import logging
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.core.config import (
    GEMINI_CATEGORIZE_MODEL,
    GEMINI_MAX_TOKENS,
    GEMINI_TEMPERATURE,
    settings,
)

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: GeminiClient | None = None


class GeminiClient:
    """Async client for Google Gemini API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        *,
        system: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ) -> T:
        """Generate a structured response validated against a Pydantic model.

        Retries on validation failure up to max_retries times.
        """
        last_error: Exception | None = None
        for _attempt in range(max_retries):
            response = await self._client.aio.models.generate_content(
                model=model or self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=response_model,
                    temperature=self._temperature,
                    max_output_tokens=self._max_tokens,
                ),
            )
            try:
                return response_model.model_validate_json(response.text)
            except ValidationError as e:
                last_error = e
                log.warning("Structured output validation failed, retrying: %s", e)
                continue
        raise RuntimeError(
            f"Structured output failed after {max_retries} retries: {last_error}"
        )

def get_gemini_client() -> GeminiClient:
    """Get or create the singleton GeminiClient."""
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set")
        _client = GeminiClient(
            api_key=settings.gemini_api_key,
            model=GEMINI_CATEGORIZE_MODEL,
            temperature=GEMINI_TEMPERATURE,
            max_tokens=GEMINI_MAX_TOKENS,
        )
    return _client
