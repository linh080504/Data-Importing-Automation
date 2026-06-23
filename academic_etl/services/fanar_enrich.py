"""Fanar API integration for university data enrichment, translation, and moderation.

Fanar (https://api.fanar.qa) is an OpenAI-compatible LLM API from Qatar with:
- 50 req/min rate limit (much higher than Gemini free tier)
- Dedicated translation model (Fanar-Shaheen-MT-1)
- Agentic model with tool call support (Fanar-Sadiq-Agentic)
- Content moderation (Fanar-Guard-2)

Authentication: Bearer token via FANAR_API_KEY environment variable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path

import requests
from django.conf import settings

from .country_registry import get_currency
from .normalize import normalize_bool, normalize_email, normalize_int, normalize_phone, normalize_url

logger = logging.getLogger(__name__)

# Fields this service fills (same as gemini_enrich for compatibility).
FANAR_FIELDS = (
    "name", "website", "description", "campus_student_life",
    "number_of_students", "financials", "global_rank",
    "student_to_faculty_ratio", "international_student_ratio",
    "admissions_contact", "admissions_phone", "admissions_page_link",
    "contact_person", "university_campuses",
    "housing_availability", "student_loan_available", "immigration_support",
)

_ENRICHMENT_PROMPT = """\
Return a JSON object about this university. No markdown, valid JSON only.
Institution: "{name}"
Country: {country}{city_hint}

RULES: ALL text MUST be in English. Try hard to fill every field.

JSON keys (return ALL, no exceptions):
- name: official English name
- website: official homepage URL (https://)
- description: 2-3 factual sentences IN ENGLISH (type, location, founded year, known for)
- campus_student_life: 2-3 detailed sentences IN ENGLISH about campus facilities, libraries, labs, sports complexes, hostels/dormitories, student clubs, cultural activities. Be specific to THIS university.
- number_of_students: total enrollment integer, or null
- financials: annual tuition as "{currency} <low>-<high> ($<usd_low>-<usd_high>)". Examples: "INR 50k-200k ($600-2400)", "VND 20m-40m ($800-1600)". "" only if truly unknown.
- global_rank: QS or THE world ranking ONLY. "QS 150", "QS 801-1000", "THE 1201+", or "" if unranked.
- student_to_faculty_ratio: e.g. "20" or "18:1", or ""
- international_student_ratio: e.g. "5%", or ""
- admissions_contact: official email (prefer admissions@ or info@), or ""
- admissions_phone: phone with + country code e.g. "+91 11 2659 6631", or ""
- admissions_page_link: admissions URL (same domain as website), or ""
- contact_person: name of admissions head/registrar, or ""
- university_campuses: verified count of campuses (main + satellite), or null
- housing_availability: true if has hostels/dormitories on campus
- student_loan_available: true if offers/facilitates education loans
- immigration_support: true if has international student office for visa help
- sponsored: false
Use null only for number_of_students and university_campuses when truly unknown.\
"""

_MAJORS_PROMPT = """\
List ALL academic degree programs offered by "{name}" in {country}.
Return a JSON array. No markdown, valid JSON only.

CRITICAL — distinguish these levels:
- field_of_study = broad discipline (Engineering, Science, Commerce, Law, Medicine, Arts)
- faculty_or_school = organizational unit (School of Engineering, Department of Physics)
- program_name = the ACTUAL degree students enroll in (B.Tech Computer Science, MBA, MBBS)
- specializations = sub-tracks within a program (AI/ML, Cybersecurity)

DO NOT list faculty/department names as programs.
"Engineering and Technology" is a field_of_study, NOT a program.

Each object MUST have:
- program_name: full degree name, e.g. "B.Tech Computer Science and Engineering"
- degree_level: "bachelor" | "master" | "phd" | "diploma" | "professional"
- field_of_study: e.g. "Engineering", "Science", "Commerce", "Medicine"
- faculty_or_school: e.g. "School of Engineering", "Faculty of Science"
- specializations: array of sub-tracks, e.g. ["AI/ML", "Cybersecurity"] or []
- duration: e.g. "4 years", "2 years"
- program_url: direct URL or ""

Country-specific degree names:
- India: B.Tech, M.Tech, BBA, MBA, MBBS, B.Sc, M.Sc, B.A, M.A, LLB, LLM, BCA, MCA, B.Com, M.Com
- Vietnam: Cử nhân, Thạc sĩ, Tiến sĩ, Kỹ sư

Return 15-50 programs. Empty array [] only if unsure.\
"""


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def fanar_is_configured() -> bool:
    return bool(getattr(settings, "FANAR_API_KEY", ""))


def _api_key() -> str:
    return settings.FANAR_API_KEY


def _base_url() -> str:
    return getattr(settings, "FANAR_API_BASE_URL", "https://api.fanar.qa/v1")


def _model() -> str:
    return getattr(settings, "FANAR_MODEL", "Fanar-C-2-27B")


def _cache_dir() -> Path:
    d = getattr(settings, "FANAR_CACHE_DIR", Path("var/fanar_cache"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timeout() -> int:
    return getattr(settings, "FANAR_TIMEOUT", 30)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_key(name: str, country: str, suffix: str = "") -> str:
    raw = f"{name}|{country}|{suffix}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> dict | None:
    path = _cache_dir() / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _cache_set(key: str, data: dict):
    path = _cache_dir() / f"{key}.json"
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write Fanar cache: %s", exc)


# ---------------------------------------------------------------------------
# Chat Completions API
# ---------------------------------------------------------------------------

_CHAT_MODELS = [
    "Fanar-C-2-27B",
    "Fanar-Sadiq",
    "Fanar-Sadiq-Agentic",
    "Fanar-C-1-8.7B",
    "Fanar-S-1-7B",
    "Fanar",
]
_model_index = 0


def _next_model() -> str:
    """Round-robin across all chat models. 6 models × 50 req/min = 300 req/min."""
    global _model_index
    mdl = _CHAT_MODELS[_model_index % len(_CHAT_MODELS)]
    _model_index += 1
    return mdl


def _chat_completion(messages: list[dict], model: str | None = None, temperature: float = 0.1) -> str:
    """Call Fanar chat completions with round-robin model rotation.

    If a model fails (422/400/429), tries the next model in rotation.
    6 models × 50 req/min = effective 300 req/min throughput.
    """
    url = f"{_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }

    last_error = None
    for _ in range(len(_CHAT_MODELS)):
        mdl = model or _next_model()
        payload = {
            "model": mdl,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 429:
                logger.debug("Fanar %s rate-limited, rotating to next model", mdl)
                model = None
                continue
            if resp.status_code in (422, 400):
                logger.debug("Fanar %s returned %d, rotating", mdl, resp.status_code)
                model = None
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as exc:
            last_error = exc
            model = None
            continue

    raise RuntimeError(f"Fanar API: all {len(_CHAT_MODELS)} models failed. Last: {last_error}")

    raise RuntimeError("Fanar API call failed: max retries exceeded")


def _parse_json_response(text: str) -> dict | list | None:
    """Extract JSON from a possibly fenced response."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding JSON object/array in text
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    logger.warning("Could not parse JSON from Fanar response: %s...", text[:200])
    return None


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def enrich_institution_fanar(
    name: str, country: str, country_code: str = "",
    city: str = "", wikipedia_url: str = "",
) -> dict:
    """Enrich a single institution using Fanar Chat Completions.

    Returns a dict with the same keys as FANAR_FIELDS, or empty dict on failure.
    Cached by name+country to avoid re-billing.
    """
    if not fanar_is_configured():
        raise RuntimeError("Fanar API key not configured (set FANAR_API_KEY in .env)")

    cache_key = _cache_key(name, country, "enrich")
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Fanar cache hit for %s", name)
        return _normalize_contact_fields(cached)

    currency = get_currency(country_code) if country_code else "USD"
    city_hint = f"\n  City: {city}" if city else ""
    wiki_hint = f"\n  Wikipedia: {wikipedia_url}" if wikipedia_url else ""

    prompt = _ENRICHMENT_PROMPT.format(
        name=name, country=country, currency=currency,
        city_hint=city_hint, wiki_hint=wiki_hint,
    )

    messages = [
        {"role": "system", "content": (
            "You are a factual academic data researcher building a global university catalog. "
            "Return precise data in valid JSON. ALL text MUST be in English. "
            "Fill every field — empty values hurt data quality. "
            "For tuition, always include both local currency AND USD equivalent."
        )},
        {"role": "user", "content": prompt},
    ]

    try:
        response_text = _chat_completion(messages)
        result = _parse_json_response(response_text)
        if not isinstance(result, dict):
            logger.warning("Fanar returned non-dict for %s: %s", name, type(result))
            return {}

        # Normalize null -> empty string for text fields, keeping numeric fields
        # nullable so model saves do not receive "" for integer columns.
        for key in FANAR_FIELDS:
            if key in result and result[key] is None:
                result[key] = None if key in {"number_of_students", "university_campuses"} else ""

        result = _normalize_contact_fields(result)

        _cache_set(cache_key, result)
        return result

    except Exception as exc:
        logger.error("Fanar enrichment failed for %s: %s", name, exc)
        return {}


def _normalize_contact_fields(result: dict) -> dict:
    """Normalize LLM contact output before it reaches any pipeline entry point."""
    values = dict(result or {})
    values["website"] = normalize_url(values.get("website", ""))
    values["admissions_page_link"] = normalize_url(values.get("admissions_page_link", ""))
    values["admissions_contact"] = normalize_email(values.get("admissions_contact", ""))
    values["admissions_phone"] = normalize_phone(values.get("admissions_phone", ""))
    values["number_of_students"] = normalize_int(values.get("number_of_students"))
    values["university_campuses"] = normalize_int(values.get("university_campuses"))
    for field in ("housing_availability", "student_loan_available", "immigration_support"):
        values[field] = normalize_bool(values.get(field))
    return values


def enrich_majors_fanar(
    name: str, country: str, country_code: str = "",
) -> list[dict]:
    """Enrich majors/programs for an institution using Fanar.

    Returns a list of program dicts, each with program_name, degree_level,
    faculty_or_school, field_of_study, specializations, etc.
    """
    if not fanar_is_configured():
        raise RuntimeError("Fanar API key not configured")

    cache_key = _cache_key(name, country, "majors")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if isinstance(cached, list) else []

    currency = get_currency(country_code) if country_code else "USD"
    prompt = _MAJORS_PROMPT.format(name=name, country=country, currency=currency)

    messages = [
        {"role": "system", "content": (
            "You are an academic data researcher. List ACTUAL degree programs, "
            "NOT faculty/department names. 'Engineering' is a field_of_study, "
            "not a program. 'B.Tech Computer Science' IS a program."
        )},
        {"role": "user", "content": prompt},
    ]

    try:
        response_text = _chat_completion(messages)
        result = _parse_json_response(response_text)
        if not isinstance(result, list):
            logger.warning("Fanar returned non-list for majors of %s", name)
            return []
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.error("Fanar majors enrichment failed for %s: %s", name, exc)
        return []


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def translate_to_english(text: str, source_lang: str = "auto") -> str:
    """Translate text to English using Fanar Translation API.

    Uses the dedicated Fanar-Shaheen-MT-1 model via /v1/translations endpoint.
    """
    if not text or not text.strip():
        return text
    if not fanar_is_configured():
        return text

    url = f"{_base_url()}/translations"
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    langpair = f"{source_lang}-en" if source_lang != "auto" else "auto-en"
    payload = {
        "model": getattr(settings, "FANAR_TRANSLATION_MODEL", "Fanar-Shaheen-MT-1"),
        "input": [{"role": "user", "content": text}],
        "langpair": langpair,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout())
        resp.raise_for_status()
        data = resp.json()
        # Extract translated text from response
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", text)
        return text
    except Exception as exc:
        logger.warning("Fanar translation failed: %s — returning original text", exc)
        return text


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------

def moderate_content(text: str) -> dict:
    """Check content safety and cultural awareness using Fanar Guard.

    Returns: {safety_score: float, cultural_awareness_score: float, flagged: bool}
    """
    if not text or not fanar_is_configured():
        return {"safety_score": 1.0, "cultural_awareness_score": 1.0, "flagged": False}

    url = f"{_base_url()}/moderations"
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "Fanar-Guard-2",
        "input": text,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout())
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [{}])
        if results:
            r = results[0]
            return {
                "safety_score": r.get("safety_score", 1.0),
                "cultural_awareness_score": r.get("cultural_awareness_score", 1.0),
                "flagged": r.get("flagged", False),
            }
        return {"safety_score": 1.0, "cultural_awareness_score": 1.0, "flagged": False}
    except Exception as exc:
        logger.warning("Fanar moderation failed: %s", exc)
        return {"safety_score": 1.0, "cultural_awareness_score": 1.0, "flagged": False}
