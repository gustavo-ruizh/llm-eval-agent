import json
import logging
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from .config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClientError(Exception):
    pass


class LLMClient:
    def __init__(self) -> None:
        self._provider = settings.LLM_PROVIDER
        self._api_key = settings.LLM_API_KEY
        self._model = settings.LLM_MODEL
        self._timeout = settings.LLM_TIMEOUT_SECONDS

    def generate_json(self, prompt: str, response_model: Type[T]) -> T:
        if not self._api_key:
            raise LLMClientError("LLM_API_KEY is not configured")

        last_error: Exception | None = None

        for attempt in range(2):
            try:
                raw = self._call_provider(prompt)
                data = self._parse_json(raw)
                return response_model.model_validate(data)
            except LLMClientError:
                raise
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.warning("Attempt %d: parse/validation error: %s", attempt + 1, exc)
            except Exception as exc:
                last_error = exc
                logger.warning("Attempt %d: LLM call error: %s", attempt + 1, exc)

        raise LLMClientError(f"LLM call failed after retry: {last_error}") from last_error

    def _call_provider(self, prompt: str) -> str:
        if self._provider == "openai":
            return self._call_openai(prompt)
        if self._provider == "anthropic":
            return self._call_anthropic(prompt)
        raise LLMClientError(f"Unsupported LLM_PROVIDER: {self._provider}")

    def _call_openai(self, prompt: str) -> str:
        try:
            import openai
        except ImportError as exc:
            raise LLMClientError("openai package is not installed") from exc

        client = openai.OpenAI(api_key=self._api_key, timeout=self._timeout)
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a structured evaluation assistant. "
                        "Always respond with valid JSON matching the requested schema. "
                        "Do not include markdown fences or extra commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    def _call_anthropic(self, prompt: str) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMClientError("anthropic package is not installed") from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=4096,
            timeout=self._timeout,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are a structured evaluation assistant. "
                        "Always respond with valid JSON matching the requested schema. "
                        "Do not include markdown fences or extra commentary.\n\n"
                        + prompt
                    ),
                }
            ],
        )
        return message.content[0].text

    def _parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
        return json.loads(raw)
