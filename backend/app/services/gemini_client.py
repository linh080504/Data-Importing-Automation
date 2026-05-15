from __future__ import annotations

import logging
from typing import Sequence

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GeminiConfigurationError(RuntimeError):
    pass


class GeminiResponseError(RuntimeError):
    pass


class GeminiRateLimitError(RuntimeError):
    pass


def configured_gemini_api_keys() -> list[str]:
    return get_settings().gemini_api_keys_list()


def configured_gemini_models() -> list[str]:
    return get_settings().gemini_models_list()


class RotatingGeminiJSONClient:
    def __init__(self, *, api_keys: Sequence[str], models: Sequence[str]) -> None:
        self.api_keys = [key.strip() for key in api_keys if key and key.strip()]
        self.models = [model.strip() for model in models if model and model.strip()]

    def generate_json(self, *, prompt: str) -> str:
        if not self.api_keys:
            raise GeminiConfigurationError("GEMINI_API_KEY is not configured")
        if not self.models:
            raise GeminiConfigurationError("GEMINI_MODEL is not configured")

        last_error: Exception | None = None
        total_models = len(self.models)
        total_keys = len(self.api_keys)
        for model_index, model in enumerate(self.models, start=1):
            for key_index, api_key in enumerate(self.api_keys, start=1):
                try:
                    response = httpx.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": api_key},
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"responseMimeType": "application/json"},
                        },
                        timeout=60,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    candidates = payload.get("candidates") or []
                    if not candidates:
                        raise GeminiResponseError("Gemini returned no candidates")

                    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
                    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
                    if not text:
                        raise GeminiResponseError("Gemini returned an empty response")
                    return text
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status_code = exc.response.status_code if exc.response is not None else None
                    if status_code == 429 and key_index < total_keys:
                        logger.warning("Gemini model %s key %s/%s hit rate limit; rotating to next configured key.", model, key_index, total_keys)
                        continue
                    if status_code in {400, 404} and model_index < total_models:
                        logger.warning("Gemini model %s is unavailable for this project; rotating to next configured model.", model)
                        break
                    if status_code == 429 and model_index < total_models:
                        logger.warning("All keys for Gemini model %s are rate-limited; rotating to next configured model.", model)
                        break
                    if status_code == 429:
                        raise GeminiRateLimitError("All configured Gemini API keys are rate-limited") from exc
                    raise
                except Exception as exc:
                    last_error = exc
                    raise

        if last_error is not None:
            raise last_error
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured")


def build_gemini_client() -> RotatingGeminiJSONClient:
    return RotatingGeminiJSONClient(api_keys=configured_gemini_api_keys(), models=configured_gemini_models())
