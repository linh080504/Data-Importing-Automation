from __future__ import annotations

from app.core.config import get_settings
from app.services.claude_client import build_claude_client
from app.services.gemini_client import build_gemini_client


class AIProviderRouterError(RuntimeError):
    pass


def build_extractor_client():
    settings = get_settings()
    provider = str(settings.extraction_provider).strip().lower()
    model = str(settings.extraction_model).strip() or "default"
    if provider == "claude":
        return build_claude_client(model_name=model, timeout_seconds=float(settings.extraction_timeout_seconds))
    if provider == "gemini":
        return build_gemini_client(model_name=model, allow_fallback=bool(settings.extraction_allow_fallback))
    raise AIProviderRouterError(f"Unsupported extraction_provider '{settings.extraction_provider}'")


def build_judge_client():
    settings = get_settings()
    provider = str(settings.judge_provider).strip().lower()
    model = str(settings.judge_model).strip() or "default"
    if provider == "claude":
        return build_claude_client(model_name=model, timeout_seconds=float(settings.judge_timeout_seconds))
    if provider == "gemini":
        return build_gemini_client(model_name=model, allow_fallback=bool(settings.judge_allow_fallback))
    raise AIProviderRouterError(f"Unsupported judge_provider '{settings.judge_provider}'")
