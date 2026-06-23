"""Unified LLM provider with automatic fallback.

Tries providers in the order configured by ETL_LLM_PROVIDER_ORDER (default:
fanar, gemini). If the first provider fails or is not configured, falls back
to the next.

This module is the single entry point for LLM-based enrichment — callers
should use this instead of calling fanar_enrich or gemini_enrich directly.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _provider_order() -> list[str]:
    order = getattr(settings, "ETL_LLM_PROVIDER_ORDER", ["fanar", "gemini"])
    if isinstance(order, str):
        order = [p.strip() for p in order.split(",") if p.strip()]
    return order


def _fanar_available() -> bool:
    try:
        from .fanar_enrich import fanar_is_configured
        return fanar_is_configured()
    except Exception:
        return False


def _gemini_available() -> bool:
    try:
        from .gemini_enrich import is_configured
        return is_configured()
    except Exception:
        return False


def get_active_provider() -> str | None:
    """Return the name of the first available provider, or None."""
    for provider in _provider_order():
        if provider == "fanar" and _fanar_available():
            return "fanar"
        if provider == "gemini" and _gemini_available():
            return "gemini"
    return None


def get_provider_status() -> list[dict]:
    """Return status of all providers for the dashboard."""
    statuses = []
    for provider in _provider_order():
        if provider == "fanar":
            statuses.append({
                "name": "Fanar",
                "key": "fanar",
                "configured": _fanar_available(),
                "model": getattr(settings, "FANAR_MODEL", ""),
                "rate_limit": "50 req/min",
            })
        elif provider == "gemini":
            statuses.append({
                "name": "Gemini",
                "key": "gemini",
                "configured": _gemini_available(),
                "model": getattr(settings, "GEMINI_MODEL", ""),
                "rate_limit": "~20 req/day/key (free)",
            })
    return statuses


def enrich_institution(
    name: str, country: str, country_code: str = "",
    city: str = "", wikipedia_url: str = "",
) -> tuple[dict, str]:
    """Enrich a single institution using the first available LLM provider.

    Returns (result_dict, provider_name). Falls back automatically if the
    primary provider fails.
    """
    errors = []

    for provider in _provider_order():
        if provider == "fanar" and _fanar_available():
            try:
                from .fanar_enrich import enrich_institution_fanar
                result = enrich_institution_fanar(
                    name=name, country=country, country_code=country_code,
                    city=city, wikipedia_url=wikipedia_url,
                )
                if result:
                    return result, "fanar"
            except Exception as exc:
                logger.warning("Fanar enrichment failed for %s, trying next provider: %s", name, exc)
                errors.append(("fanar", str(exc)))

        elif provider == "gemini" and _gemini_available():
            try:
                from .gemini_enrich import enrich_institution as gemini_enrich_inst
                result = gemini_enrich_inst(
                    name=name, country=country, country_code=country_code,
                    city=city, wikipedia_url=wikipedia_url,
                )
                fields = result.get("fields", {}) if isinstance(result, dict) else {}
                if fields:
                    return fields, "gemini"
            except Exception as exc:
                logger.warning("Gemini enrichment failed for %s: %s", name, exc)
                errors.append(("gemini", str(exc)))

    if errors:
        logger.error("All LLM providers failed for %s: %s", name, errors)
    else:
        logger.error("No LLM providers configured for enrichment")
    return {}, ""


def enrich_majors(
    name: str, country: str, country_code: str = "",
) -> tuple[list[dict], str]:
    """Enrich majors/programs for an institution.

    Returns (list_of_programs, provider_name).
    """
    for provider in _provider_order():
        if provider == "fanar" and _fanar_available():
            try:
                from .fanar_enrich import enrich_majors_fanar
                result = enrich_majors_fanar(name=name, country=country, country_code=country_code)
                if result:
                    return result, "fanar"
            except Exception as exc:
                logger.warning("Fanar majors failed for %s, trying next: %s", name, exc)

        elif provider == "gemini" and _gemini_available():
            try:
                from .gemini_enrich import enrich_majors as gemini_enrich_majors
                result = gemini_enrich_majors(name=name, country=country)
                if result:
                    return result, "gemini"
            except Exception as exc:
                logger.warning("Gemini majors failed for %s: %s", name, exc)

    return [], ""


def translate_text(text: str, source_lang: str = "auto") -> str:
    """Translate text to English. Currently only Fanar has a dedicated translation model."""
    if not text or not text.strip():
        return text

    if _fanar_available():
        try:
            from .fanar_enrich import translate_to_english
            return translate_to_english(text, source_lang)
        except Exception as exc:
            logger.warning("Fanar translation failed: %s", exc)

    # Fallback: use Gemini or Fanar chat for translation
    for provider in _provider_order():
        if provider == "fanar" and _fanar_available():
            try:
                from .fanar_enrich import _chat_completion
                resp = _chat_completion([
                    {"role": "system", "content": "You are a translator. Translate the following text to English. Return only the translation, nothing else."},
                    {"role": "user", "content": text},
                ])
                if resp:
                    return resp.strip()
            except Exception:
                pass
        elif provider == "gemini" and _gemini_available():
            try:
                from .gemini_enrich import _call_gemini
                resp = _call_gemini(
                    f"Translate the following text to English. Return only the translation:\n\n{text}",
                    use_grounding=False,
                )
                if resp:
                    return resp.strip()
            except Exception:
                pass

    return text
