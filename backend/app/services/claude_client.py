from __future__ import annotations

from dataclasses import dataclass

from anthropic import Anthropic

from app.core.config import get_settings


class ClaudeConfigurationError(RuntimeError):
    pass


@dataclass
class ClaudeJSONClient:
    api_key: str
    model: str
    timeout_seconds: float

    def generate_json(self, *, prompt: str) -> str:
        client = Anthropic(api_key=self.api_key, timeout=self.timeout_seconds)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts: list[str] = []
        for block in response.content:
            candidate = getattr(block, "text", None)
            if isinstance(candidate, str) and candidate.strip():
                text_parts.append(candidate)
        if not text_parts:
            raise ClaudeConfigurationError("Claude returned an empty response")
        return "".join(text_parts)


def build_claude_client(*, model_name: str | None = None, timeout_seconds: float | None = None) -> ClaudeJSONClient:
    settings = get_settings()
    if not settings.has_anthropic_api_key():
        raise ClaudeConfigurationError("ANTHROPIC_API_KEY is not configured")

    configured_model = str(model_name or "").strip()
    if not configured_model:
        configured_model = str(settings.judge_model or settings.extraction_model or "default").strip()

    model_mapping = {
        "default": "claude-sonnet-4-6",
        "default-4-7": "claude-opus-4-7",
    }
    resolved_model = model_mapping.get(configured_model, configured_model)
    resolved_timeout = timeout_seconds if timeout_seconds is not None else float(settings.judge_timeout_seconds)

    return ClaudeJSONClient(
        api_key=str(settings.anthropic_api_key).strip(),
        model=resolved_model,
        timeout_seconds=resolved_timeout,
    )

