"""Grounded, field-level quality enrichment for university catalog data."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from academic_etl.models import FieldEvidence, PipelineRun

from .country_registry import get_currency
from .financial import standardize_financials
from .gemini_enrich import _generate, _grounding_sources, _strip_json, is_configured
from .lang import is_english
from .normalize import normalize_email, normalize_phone, normalize_url, url_domain


QUALITY_PROMPT_VERSION = "university-quality-v2"
FANAR_PROMPT_VERSION = "university-field-v2"
QUALITY_FIELDS = (
    "financials",
    "university_campuses",
    "admissions_contact",
    "admissions_phone",
    "global_rank",
    "campus_student_life",
)
RESOLUTION_KEY = "_quality_resolution"
VALID_STATUSES = {"verified", "verified_absent", "unavailable", "error"}
RANK_RE = re.compile(r"^(QS|THE)\s+(?:\d+|\d+-\d+|\d+\+)$", re.IGNORECASE)
FINANCIAL_RE = re.compile(
    r"^(?P<currency>[A-Z]{3})\s+"
    r"(?P<low>\d+(?:\.\d+)?)(?P<low_unit>[km]?)"
    r"(?:-(?P<high>\d+(?:\.\d+)?)(?P<high_unit>[km]?))?"
    r"\s+\(\$(?P<usd_low>\d+(?:\.\d+)?)"
    r"(?:-(?P<usd_high>\d+(?:\.\d+)?))?\)$",
    re.IGNORECASE,
)
NOISE_MARKERS = (
    "apply now", "exam result", "online payment", "grievance", "quick links",
    "read more", "click here", "email protected", "brochure", "iqac", "nirf",
)
DEFAULT_TUITION_DOMAINS = {
    "topuniversities.com",
    "timeshighereducation.com",
    "studyportals.com",
    "bachelorsportal.com",
    "mastersportal.com",
}
RANKING_DOMAINS = {
    "topuniversities.com",
    "qs.com",
    "timeshighereducation.com",
}
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
}


FANAR_FIELD_PROMPTS = {
    "financials": """Find the typical ANNUAL undergraduate tuition for this university.
Return JSON only: {\"status\":\"verified|unavailable\",\"currency\":\"{currency}\",\"amount_low\":number|null,\"amount_high\":number|null,\"usd_low\":number|null,\"usd_high\":number|null,\"period\":\"annual\",\"confidence\":0.0}.
Use numeric amounts without commas. Do not return monthly, semester, total-program, hostel, application, or exam fees.""",
    "university_campuses": """List the distinct physical campuses operated directly by this university.
Return JSON only: {\"status\":\"verified|unavailable\",\"campus_names\":[\"name\"],\"source_url\":\"official page URL or empty\",\"confidence\":0.0}.
Use verified only when every campus name is stated on the official university website. Do not count affiliated colleges, examination centres, study centres, departments, regional offices, or cities where students can apply. Remove duplicates and return unavailable rather than guessing. Do not return a bare count.""",
    "admissions_contact": """Find the university's official admissions email. If unavailable, return the registrar or official general-contact email.
Return JSON only: {\"status\":\"verified|unavailable\",\"value\":\"email or empty\",\"confidence\":0.0}.""",
    "admissions_phone": """Find the university's official admissions or general-contact telephone number with international country code.
Return JSON only: {\"status\":\"verified|unavailable\",\"value\":\"international phone or empty\",\"confidence\":0.0}.
Do not convert an academic year or a local number without a known country code.""",
    "global_rank": """Find the latest QS World University Ranking or Times Higher Education World University Ranking for this university.
Return JSON only: {\"status\":\"verified|verified_absent|unavailable\",\"value\":\"QS 801-1000 or THE 1201+ or empty\",\"confidence\":0.0}.
Reject NIRF, Webometrics, uniRank, and every national-only ranking.""",
    "campus_student_life": """Describe student life at this specific university in 3-5 factual English sentences.
Return JSON only: {\"status\":\"verified|unavailable\",\"value\":\"text\",\"confidence\":0.0}.
Mention only specific known libraries, laboratories, hostels, sports facilities, clubs, or cultural activities. No generic marketing prose or calls to action.""",
}


FANAR_PROMPT_HEADER = """You answer one factual field for one higher-education institution.
Institution: "{name}"
Country: {country}
City/region: {city}
Known official website: {website}
Expected local currency: {currency}

{question}
If you are not sufficiently confident, return status unavailable. Do not add prose or markdown.
"""


QUALITY_PROMPT = """\
Use Google Search to verify quality-critical catalog fields for exactly one university.

Institution: "{name}"
Country: {country}
Known city/region: {city}
Known official website: {website}
Expected local currency: {currency}
Requested fields: {requested_fields}

Return one valid JSON object and no markdown. Return only the requested keys. Each key must
contain: status (verified, verified_absent, unavailable, or error), value,
source_url, and confidence from 0 to 1. source_url must be a URL actually used in
your grounded answer. Never infer a value only to fill a cell.

{{
  "financials": {{"status":"...", "value":"...", "period":"annual", "source_url":"...", "confidence":0.0}},
  "university_campuses": {{"status":"...", "value":null, "source_url":"...", "confidence":0.0}},
  "admissions_contact": {{"status":"...", "value":"", "source_url":"...", "confidence":0.0}},
  "admissions_phone": {{"status":"...", "value":"", "source_url":"...", "confidence":0.0}},
  "global_rank": {{"status":"...", "value":"", "source_url":"...", "confidence":0.0}},
  "campus_student_life": {{"status":"...", "value":"", "source_url":"...", "confidence":0.0}}
}}

Field rules:
- financials: typical annual undergraduate tuition from the official university
  site or a reputable education/ranking source. Format exactly like
  "INR 50k-200k ($600-2400)". Do not estimate without a published figure.
- university_campuses: integer count only when the official site explicitly names
  or counts main and satellite campuses. Unknown is null, never default to 1.
- admissions_contact: an admissions email, otherwise registrar/general email,
  visibly published on the official university website.
- admissions_phone: an official admissions/general phone in international format,
  visibly published on the official university website.
- global_rank: latest QS World University Ranking or Times Higher Education World
  University Ranking only. Format "QS 801-1000" or "THE 1201+". National rankings,
  NIRF, uniRank, and Webometrics are invalid. Use verified_absent when QS/THE show
  no world ranking for this institution.
- campus_student_life: 3-5 specific factual English sentences grounded in the
  official site. Cover only documented facilities or activities such as libraries,
  laboratories, housing, sports, clubs, or cultural activities. No generic prose,
  menus, calls to action, or invented facts.
"""


def _host(url: str) -> str:
    normalized = normalize_url(url)
    return urlparse(normalized).netloc.lower().removeprefix("www.") if normalized else ""


def _same_domain(left: str, right: str) -> bool:
    a, b = _host(left), _host(right)
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))


def _domain_allowed(url: str, domains: set[str]) -> bool:
    host = _host(url)
    return bool(host and any(host == domain or host.endswith("." + domain) for domain in domains))


def _canonical_url(url: str) -> str:
    return normalize_url(url).lower()


def _is_grounded(source_url: str, grounding_sources: list[str]) -> bool:
    source = _canonical_url(source_url)
    return bool(source and source in {_canonical_url(url) for url in grounding_sources})


def campus_life_is_usable(value: str) -> bool:
    text = " ".join(str(value or "").split())
    lowered = text.lower()
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    return bool(
        180 <= len(text) <= 2000
        and 3 <= len(sentences) <= 5
        and is_english(text)
        and not any(marker in lowered for marker in NOISE_MARKERS)
    )


def _parse_quality_financial(value: str, country_code: str) -> dict:
    raw = " ".join(str(value or "").split())
    match = FINANCIAL_RE.fullmatch(raw)
    if not match:
        return {}
    currency = match.group("currency").upper()
    expected_currency = get_currency(country_code)
    if expected_currency and currency != expected_currency:
        return {}

    def amount(number: str | None, unit: str | None):
        if number is None:
            return None
        multiplier = {"": Decimal("1"), "k": Decimal("1000"), "m": Decimal("1000000")}
        try:
            return Decimal(number) * multiplier[(unit or "").lower()]
        except (InvalidOperation, KeyError):
            return None

    low = amount(match.group("low"), match.group("low_unit"))
    high = amount(match.group("high"), match.group("high_unit")) or low
    usd_low = amount(match.group("usd_low"), "")
    usd_high = amount(match.group("usd_high"), "") or usd_low
    if low is None or high is None or usd_low is None or usd_high is None:
        return {}
    if low <= 0 or high < low or usd_low <= 0 or usd_high < usd_low:
        return {}
    return {
        "raw": raw,
        "formatted": raw,
        "currency": currency,
        "amount_low": low,
        "amount_high": high,
        "usd_low": usd_low,
        "usd_high": usd_high,
        "period": "annual",
    }


def financials_is_usable(value: str, country_code: str) -> bool:
    data = _parse_quality_financial(value, country_code)
    if not data:
        data = standardize_financials(value, country_code=country_code)
    return bool(data.get("formatted") and data.get("amount_low") is not None)


def rank_is_usable(value: str) -> bool:
    return bool(RANK_RE.fullmatch(str(value or "").strip()))


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _compact_amount(value: Decimal, *, local: bool) -> str:
    unit = ""
    display = value
    if local and value >= 1_000_000:
        unit, display = "m", value / Decimal("1000000")
    elif local and value >= 1_000:
        unit, display = "k", value / Decimal("1000")
    display = display.quantize(Decimal("0.01")).normalize()
    return f"{display:f}{unit}"


def _fanar_financial(item: dict, country_code: str) -> dict:
    currency = str(item.get("currency") or "").strip().upper()
    expected = get_currency(country_code)
    low = _decimal(item.get("amount_low"))
    high = _decimal(item.get("amount_high")) or low
    usd_low = _decimal(item.get("usd_low"))
    usd_high = _decimal(item.get("usd_high")) or usd_low
    if (
        str(item.get("period") or "").lower() != "annual"
        or not currency or (expected and currency != expected)
        or low is None or high is None or usd_low is None or usd_high is None
        or low <= 0 or high < low or usd_low <= 0 or usd_high < usd_low
        or high > Decimal("10000000000")
    ):
        return {}
    local = _compact_amount(low, local=True)
    if high != low:
        local += "-" + _compact_amount(high, local=True)
    usd = _compact_amount(usd_low, local=False)
    if usd_high != usd_low:
        usd += "-" + _compact_amount(usd_high, local=False)
    formatted = f"{currency} {local} (${usd})"
    return {
        "raw": json.dumps(item, ensure_ascii=False),
        "formatted": formatted,
        "currency": currency,
        "amount_low": low,
        "amount_high": high,
        "usd_low": usd_low,
        "usd_high": usd_high,
        "period": "annual",
    }


def validate_fanar_candidate(field: str, item: dict, *, country_code: str, website: str) -> dict:
    """Normalize one source-free Fanar answer; return empty when Gemini must handle it."""
    if not isinstance(item, dict):
        return {}
    status = str(item.get("status") or "").strip().lower()
    if status not in {"verified", "verified_absent"}:
        return {}
    try:
        confidence = max(0.0, min(float(item.get("confidence") or 0), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    candidate = {
        "field": field,
        "status": status,
        "confidence": confidence,
        "provider": "fanar",
        "raw": item,
    }
    if field == "financials" and status == "verified":
        financial = _fanar_financial(item, country_code)
        if not financial:
            return {}
        candidate.update(value=financial["formatted"], financial=financial)
    elif field == "university_campuses" and status == "verified":
        names, seen = [], set()
        for raw_name in item.get("campus_names") or []:
            name = " ".join(str(raw_name or "").split()).strip()
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                names.append(name)
        source_url = normalize_url(item.get("source_url") or "")
        if not (
            1 <= len(names) <= 100
            and confidence >= 0.75
            and source_url
            and _same_domain(source_url, website)
        ):
            return {}
        candidate.update(value=len(names), campus_names=names, source_url=source_url)
    elif field == "admissions_contact" and status == "verified":
        value = normalize_email(item.get("value"))
        email_domain = value.rsplit("@", 1)[-1] if value else ""
        official_domain = url_domain(website)
        domain_matches = bool(
            email_domain and official_domain
            and (email_domain == official_domain or email_domain.endswith("." + official_domain))
        )
        if not value or email_domain in PUBLIC_EMAIL_DOMAINS or (official_domain and not domain_matches):
            return {}
        candidate["value"] = value
    elif field == "admissions_phone" and status == "verified":
        value = normalize_phone(item.get("value"))
        if not value:
            return {}
        candidate["value"] = value
    elif field == "global_rank":
        if status == "verified_absent":
            candidate["value"] = ""
        else:
            value = str(item.get("value") or "").strip().upper()
            if not rank_is_usable(value):
                return {}
            candidate["value"] = value
    elif field == "campus_student_life" and status == "verified":
        value = " ".join(str(item.get("value") or "").split())
        if not campus_life_is_usable(value):
            return {}
        candidate["value"] = value
    else:
        return {}
    return candidate


def _fanar_cache_path(name: str, country: str, field: str, prompt: str):
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    identity = f"{FANAR_PROMPT_VERSION}|{name.lower().strip()}|{country.lower().strip()}|{field}|{prompt_hash}"
    directory = settings.FANAR_CACHE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory / ("quality_" + hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".json"), prompt_hash


def enrich_quality_field_fanar(
    field: str, *, name: str, country: str, country_code: str,
    city: str = "", website: str = "", use_cache: bool = True,
) -> dict:
    """Ask Fanar exactly one question for exactly one field."""
    from .fanar_enrich import _chat_completion, _parse_json_response, fanar_is_configured

    if field not in FANAR_FIELD_PROMPTS:
        return {"field": field, "item": {}, "error": "unsupported field", "from_cache": False}
    prompt = FANAR_PROMPT_HEADER.format(
        name=name,
        country=country,
        city=city or "unknown",
        website=website or "unknown",
        currency=get_currency(country_code) or "unknown",
        question=FANAR_FIELD_PROMPTS[field].replace(
            "{currency}", get_currency(country_code) or "unknown",
        ),
    )
    cache_file, prompt_hash = _fanar_cache_path(name, country, field, prompt)
    if use_cache and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if (
                cached.get("prompt_version") == FANAR_PROMPT_VERSION
                and cached.get("prompt_hash") == prompt_hash
                and cached.get("field") == field
            ):
                cached["from_cache"] = True
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    if not fanar_is_configured():
        return {"field": field, "item": {}, "error": "Fanar is not configured", "from_cache": False}
    try:
        raw_text = _chat_completion([
            {"role": "system", "content": "Answer the requested university field as valid JSON only. Never add markdown."},
            {"role": "user", "content": prompt},
        ], temperature=0.0)
        parsed = _parse_json_response(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError("Fanar returned non-object JSON")
        result = {
            "field": field,
            "item": parsed,
            "error": "",
            "raw_text": raw_text,
            "prompt_version": FANAR_PROMPT_VERSION,
            "prompt_hash": prompt_hash,
            "from_cache": False,
        }
        try:
            cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return result
    except Exception as exc:
        return {
            "field": field, "item": {}, "error": str(exc)[:500],
            "prompt_version": FANAR_PROMPT_VERSION, "prompt_hash": prompt_hash,
            "from_cache": False,
        }


def _has_trusted_evidence(university, field: str, source_check) -> bool:
    if not university.pk:
        return False
    evidences = FieldEvidence.objects.filter(
        entity_type="university",
        entity_id=university.pk,
        field_name=field,
    ).order_by("-confidence_score")
    for evidence in evidences:
        if evidence.extraction_method == "manual":
            return True
        if evidence.source_url and source_check(evidence.source_url):
            return True
    return False


def quality_fields_needed(university) -> set[str]:
    resolution = (university.normalized_json or {}).get(RESOLUTION_KEY) or {}
    verified = {
        field for field, state in resolution.items()
        if isinstance(state, dict) and state.get("status") == "verified"
    }
    trusted_tuition = set(getattr(settings, "ETL_TRUSTED_TUITION_DOMAINS", DEFAULT_TUITION_DOMAINS))
    needed = set()
    financial_evidence = _has_trusted_evidence(
        university,
        "financials",
        lambda source: _same_domain(source, university.website) or _domain_allowed(source, trusted_tuition),
    )
    if not (
        financials_is_usable(university.financials, university.country_code)
        and ("financials" in verified or financial_evidence)
    ):
        needed.add("financials")
    campus_evidence = _has_trusted_evidence(
        university, "university_campuses", lambda source: _same_domain(source, university.website),
    )
    if not (
        university.university_campuses
        and ("university_campuses" in verified or campus_evidence)
    ):
        needed.add("university_campuses")
    contact_evidence = _has_trusted_evidence(
        university, "admissions_contact", lambda source: _same_domain(source, university.website),
    )
    if not (
        university.admissions_contact
        and normalize_email(university.admissions_contact) == university.admissions_contact
        and ("admissions_contact" in verified or contact_evidence)
    ):
        needed.add("admissions_contact")
    phone_evidence = _has_trusted_evidence(
        university, "admissions_phone", lambda source: _same_domain(source, university.website),
    )
    if not (
        university.admissions_phone
        and normalize_phone(university.admissions_phone) == university.admissions_phone
        and ("admissions_phone" in verified or phone_evidence)
    ):
        needed.add("admissions_phone")
    rank_state = (resolution.get("global_rank") or {}).get("status")
    rank_evidence = _has_trusted_evidence(
        university, "global_rank", lambda source: _domain_allowed(source, RANKING_DOMAINS),
    )
    if rank_state != "verified_absent" and not (
        rank_is_usable(university.global_rank)
        and ("global_rank" in verified or rank_evidence)
    ):
        needed.add("global_rank")
    life_evidence = _has_trusted_evidence(
        university, "campus_student_life", lambda source: _same_domain(source, university.website),
    )
    if not (
        campus_life_is_usable(university.campus_student_life)
        and ("campus_student_life" in verified or life_evidence)
    ):
        needed.add("campus_student_life")
    return needed


def clear_unverified_quality_values(university, needed: set[str]) -> None:
    """Remove weak values before verification so failures do not preserve bad data."""
    string_fields = {
        "financials", "admissions_contact", "admissions_phone", "global_rank",
        "campus_student_life",
    }
    changed = []
    for field in needed:
        empty = "" if field in string_fields else None
        if getattr(university, field) != empty:
            setattr(university, field, empty)
            changed.append(field)
    if "financials" in needed:
        for field, empty in (
            ("financials_raw", ""),
            ("financials_currency", ""),
            ("financials_amount_low", None),
            ("financials_amount_high", None),
            ("financials_usd_low", None),
            ("financials_usd_high", None),
        ):
            if getattr(university, field) != empty:
                setattr(university, field, empty)
                changed.append(field)
    if university.sponsored is not False:
        university.sponsored = False
        changed.append("sponsored")
    if changed:
        university.save(update_fields=set(changed))


def _cache_path(name: str, country: str, prompt: str):
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    identity = f"{QUALITY_PROMPT_VERSION}|{name.strip().lower()}|{country.strip().lower()}|{prompt_hash}"
    filename = "quality_" + hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".json"
    settings.GEMINI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return settings.GEMINI_CACHE_DIR / filename, prompt_hash


def enrich_university_quality(
    *, name: str, country: str, country_code: str, city: str = "",
    website: str = "", requested_fields=None, use_cache: bool = True,
) -> dict:
    """Make at most one grounded generation call for one university."""
    selected_fields = tuple(
        field for field in QUALITY_FIELDS
        if requested_fields is None or field in set(requested_fields)
    )
    if not selected_fields:
        return {"fields": {}, "sources": [], "error": "", "from_cache": False}
    prompt = QUALITY_PROMPT.format(
        name=name,
        country=country,
        city=city or "unknown",
        website=website or "unknown",
        currency=get_currency(country_code) or "unknown",
        requested_fields=", ".join(selected_fields),
    )
    cache_file, prompt_hash = _cache_path(name, country, prompt)
    if use_cache and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if (
                cached.get("prompt_version") == QUALITY_PROMPT_VERSION
                and cached.get("prompt_hash") == prompt_hash
                and isinstance(cached.get("fields"), dict)
            ):
                cached["from_cache"] = True
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    if not is_configured():
        return {
            "fields": {}, "sources": [], "error": "Gemini is not configured",
            "prompt_version": QUALITY_PROMPT_VERSION, "prompt_hash": prompt_hash,
            "from_cache": False,
        }

    from google.genai import types

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.0,
        http_options=types.HttpOptions(timeout=settings.GEMINI_TIMEOUT * 1000),
    )
    response, model, error = _generate(prompt, config, label=f"{name} (quality)")
    if response is None:
        return {
            "fields": {}, "sources": [], "error": error[:500], "model": "",
            "prompt_version": QUALITY_PROMPT_VERSION, "prompt_hash": prompt_hash,
            "from_cache": False,
        }

    raw_text = getattr(response, "text", "") or ""
    sources = _grounding_sources(response)
    try:
        parsed = json.loads(_strip_json(raw_text))
        if not isinstance(parsed, dict):
            raise ValueError("not a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "fields": {}, "sources": sources, "error": f"json_parse: {exc}"[:500],
            "model": model, "raw_text": raw_text,
            "prompt_version": QUALITY_PROMPT_VERSION, "prompt_hash": prompt_hash,
            "from_cache": False,
        }

    result = {
        "fields": {field: parsed.get(field) for field in selected_fields},
        "sources": sources,
        "error": "",
        "model": model,
        "raw_text": raw_text,
        "prompt_version": QUALITY_PROMPT_VERSION,
        "prompt_hash": prompt_hash,
        "from_cache": False,
    }
    try:
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result


def enrich_university_quality_hybrid(
    *, name: str, country: str, country_code: str, needed: set[str],
    city: str = "", website: str = "", use_cache: bool = True,
) -> dict:
    """Run Fanar once per needed field, then one Gemini call for the remainder."""
    from .fanar_enrich import fanar_is_configured

    fanar_candidates = {}
    fanar_calls = 0
    fanar_errors = 0
    fanar_enabled = fanar_is_configured()
    for field in QUALITY_FIELDS:
        if field not in needed or not fanar_enabled:
            continue
        fanar_calls += 1
        response = enrich_quality_field_fanar(
            field,
            name=name,
            country=country,
            country_code=country_code,
            city=city,
            website=website,
            use_cache=use_cache,
        )
        candidate = validate_fanar_candidate(
            field,
            response.get("item") or {},
            country_code=country_code,
            website=website,
        )
        if candidate:
            fanar_candidates[field] = candidate
        else:
            fanar_errors += 1

    remaining = set(needed) - set(fanar_candidates)
    gemini_result = {"fields": {}, "sources": [], "error": "", "from_cache": False}
    gemini_calls = 0
    if remaining:
        if is_configured():
            gemini_calls = 1
        gemini_result = enrich_university_quality(
            name=name,
            country=country,
            country_code=country_code,
            city=city,
            website=website,
            requested_fields=remaining,
            use_cache=use_cache,
        )
    return {
        "fanar_candidates": fanar_candidates,
        "gemini_result": gemini_result,
        "remaining": remaining,
        "fanar_calls": fanar_calls,
        "gemini_calls": gemini_calls,
        "fanar_errors": fanar_errors,
    }


def _resolution(
    status: str, source_url: str = "", confidence: float = 0.0,
    reason: str = "", provider: str = "gemini", prompt_version: str = QUALITY_PROMPT_VERSION,
):
    return {
        "status": status,
        "source_url": source_url,
        "confidence": round(max(0.0, min(float(confidence or 0), 1.0)), 2),
        "reason": reason,
        "provider": provider,
        "checked_at": timezone.now().isoformat(),
        "prompt_version": prompt_version,
    }


def clear_unverified_fanar_campus_count(university) -> bool:
    """Drop legacy Fanar campus counts that have no official-page provenance.

    Older field prompts accepted a bare list of names, which lets an LLM turn
    regional offices or affiliated colleges into fictitious campuses. Keep the
    cell empty until the quality stage can verify it from an official source.
    """
    metadata = dict(university.normalized_json or {})
    resolutions = dict(metadata.get(RESOLUTION_KEY) or {})
    campus = dict(resolutions.get("university_campuses") or {})
    if campus.get("provider") != "fanar" or campus.get("source_url"):
        return False
    if university.university_campuses is None:
        return False

    university.university_campuses = None
    resolutions["university_campuses"] = _resolution(
        "unavailable",
        reason="Fanar campus list had no official-page provenance; awaiting verified source",
        provider="fanar",
        prompt_version=FANAR_PROMPT_VERSION,
    )
    metadata[RESOLUTION_KEY] = resolutions
    university.normalized_json = metadata
    return True


def downgrade_ungrounded_quality_errors(university) -> bool:
    """Treat source-rejected answers as unknown, not as an API outage."""
    metadata = dict(university.normalized_json or {})
    resolutions = dict(metadata.get(RESOLUTION_KEY) or {})
    changed = False
    for field, state in list(resolutions.items()):
        if not isinstance(state, dict):
            continue
        if state.get("status") != "error" or state.get("reason") not in {
            "source is not grounded",
            "failed field validation",
            "missing field object",
            "invalid status",
        }:
            continue
        resolutions[field] = _resolution(
            "unavailable",
            reason="no verified Google Search grounding for the claimed source",
            provider=state.get("provider") or "gemini",
            prompt_version=state.get("prompt_version") or QUALITY_PROMPT_VERSION,
        )
        changed = True
    if changed:
        metadata[RESOLUTION_KEY] = resolutions
        university.normalized_json = metadata
    return changed


def repair_legacy_quality_metadata(run: PipelineRun) -> dict[str, int]:
    """Clear source-free legacy campus counts and re-label rejected AI values."""
    repaired_campuses = 0
    relabeled_unknown = 0
    removed_evidence = 0
    for university in run.universities.all().iterator():
        campus_cleared = clear_unverified_fanar_campus_count(university)
        errors_downgraded = downgrade_ungrounded_quality_errors(university)
        if campus_cleared or errors_downgraded:
            university.save(update_fields=[
                "university_campuses", "normalized_json", "updated_at",
            ])
        if campus_cleared:
            repaired_campuses += 1
            removed_evidence += FieldEvidence.objects.filter(
                entity_type="university",
                entity_id=university.pk,
                field_name="university_campuses",
                extraction_method="fanar_enrichment",
                source_url="",
            ).delete()[0]
        if errors_downgraded:
            relabeled_unknown += 1

    stats = {
        "campuses_cleared": repaired_campuses,
        "errors_relabelled": relabeled_unknown,
        "evidence_removed": removed_evidence,
    }
    with transaction.atomic():
        PipelineRun.objects.filter(pk=run.pk).update(
            stats_json={
                **(PipelineRun.objects.only("stats_json").get(pk=run.pk).stats_json or {}),
                "quality_repair": {**stats, "completed_at": timezone.now().isoformat()},
            },
            updated_at=timezone.now(),
        )
    return stats


def apply_fanar_candidates(university, candidates: dict) -> list[str]:
    """Persist already-validated Fanar field answers at the coordinator."""
    changed = []
    metadata = dict(university.normalized_json or {})
    resolutions = dict(metadata.get(RESOLUTION_KEY) or {})
    for field, candidate in candidates.items():
        status = candidate["status"]
        if status == "verified":
            setattr(university, field, candidate["value"])
            changed.append(field)
        financial = candidate.get("financial") or {}
        if financial:
            university.financials_raw = financial.get("raw", "")
            university.financials_currency = financial.get("currency", "")
            university.financials_amount_low = financial.get("amount_low")
            university.financials_amount_high = financial.get("amount_high")
            university.financials_usd_low = financial.get("usd_low")
            university.financials_usd_high = financial.get("usd_high")
        resolutions[field] = _resolution(
            status,
            source_url=candidate.get("source_url", ""),
            confidence=candidate.get("confidence", 0),
            provider="fanar",
            prompt_version=FANAR_PROMPT_VERSION,
        )
    university.sponsored = False
    resolutions["sponsored"] = _resolution(
        "verified", confidence=1.0, provider="system", prompt_version="system-v1",
    )
    metadata[RESOLUTION_KEY] = resolutions
    university.normalized_json = metadata
    university.save()

    for field, candidate in candidates.items():
        FieldEvidence.objects.create(
            entity_type="university",
            entity_id=university.pk,
            field_name=field,
            extracted_value=str(candidate.get("value", "")),
            normalized_value=str(candidate.get("value", "")),
            source_url=candidate.get("source_url", ""),
            raw_text=json.dumps(candidate.get("raw") or {}, ensure_ascii=False),
            confidence_score=candidate.get("confidence", 0),
            extractor_name="fanar_field_quality",
            extraction_method="fanar_enrichment",
            validation_notes=candidate["status"],
            crawled_at=timezone.now(),
        )
    return changed


def validate_quality_result(university, needed: set[str], result: dict) -> dict:
    """Return validated field updates plus per-field resolution metadata."""
    output = {"values": {}, "financial": {}, "resolutions": {}, "evidence": []}
    if result.get("error"):
        for field in needed:
            output["resolutions"][field] = _resolution("error", reason=result["error"][:300])
        return output

    fields = result.get("fields") or {}
    sources = result.get("sources") or []
    official_website = university.website
    trusted_tuition = set(getattr(settings, "ETL_TRUSTED_TUITION_DOMAINS", DEFAULT_TUITION_DOMAINS))

    for field in needed:
        item = fields.get(field)
        if not isinstance(item, dict):
            output["resolutions"][field] = _resolution("unavailable", reason="no verified response for this field")
            continue
        status = str(item.get("status") or "").strip().lower()
        source = normalize_url(item.get("source_url") or "")
        try:
            confidence = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if status not in VALID_STATUSES:
            output["resolutions"][field] = _resolution("unavailable", reason="provider returned an unusable status")
            continue
        if status in {"unavailable", "error"}:
            output["resolutions"][field] = _resolution(status, reason=str(item.get("reason") or ""))
            continue
        if not _is_grounded(source, sources):
            output["resolutions"][field] = _resolution(
                "unavailable", reason="no verified Google Search grounding for the claimed source",
            )
            continue

        value = item.get("value")
        valid = False
        normalized = value
        reason = "failed field validation"
        if field == "financials" and status == "verified":
            source_ok = _same_domain(source, official_website) or _domain_allowed(source, trusted_tuition)
            financial = _parse_quality_financial(str(value or ""), university.country_code)
            valid = bool(
                source_ok
                and str(item.get("period") or "").lower() == "annual"
                and financial.get("amount_low") is not None
                and financial.get("formatted")
            )
            if valid:
                normalized = financial["formatted"]
                output["financial"] = financial
        elif field == "university_campuses" and status == "verified":
            try:
                normalized = int(value)
            except (TypeError, ValueError):
                normalized = 0
            valid = _same_domain(source, official_website) and 1 <= normalized <= 100
        elif field == "admissions_contact" and status == "verified":
            normalized = normalize_email(value)
            valid = bool(normalized and _same_domain(source, official_website))
        elif field == "admissions_phone" and status == "verified":
            normalized = normalize_phone(value)
            valid = bool(normalized and _same_domain(source, official_website))
        elif field == "global_rank":
            rank_source = _domain_allowed(source, RANKING_DOMAINS)
            if status == "verified_absent":
                valid = rank_source
                normalized = ""
            else:
                normalized = str(value or "").strip().upper()
                valid = rank_source and rank_is_usable(normalized)
        elif field == "campus_student_life" and status == "verified":
            normalized = " ".join(str(value or "").split())
            valid = _same_domain(source, official_website) and campus_life_is_usable(normalized)

        if not valid:
            output["resolutions"][field] = _resolution("unavailable", source, confidence, reason)
            continue

        output["resolutions"][field] = _resolution(status, source, confidence)
        if status == "verified":
            output["values"][field] = normalized
        output["evidence"].append({
            "field": field,
            "value": normalized if status == "verified" else "",
            "source_url": source,
            "confidence": confidence,
            "raw": item,
            "status": status,
        })
    return output


def apply_quality_result(university, needed: set[str], result: dict) -> list[str]:
    validated = validate_quality_result(university, needed, result)
    changed = []
    for field, value in validated["values"].items():
        setattr(university, field, value)
        changed.append(field)
    financial = validated.get("financial") or {}
    if financial:
        university.financials_raw = financial.get("raw", "")
        university.financials_currency = financial.get("currency", "")
        university.financials_amount_low = financial.get("amount_low")
        university.financials_amount_high = financial.get("amount_high")
        university.financials_usd_low = financial.get("usd_low")
        university.financials_usd_high = financial.get("usd_high")
    university.sponsored = False
    if "sponsored" not in changed:
        changed.append("sponsored")
    metadata = dict(university.normalized_json or {})
    metadata[RESOLUTION_KEY] = {
        **(metadata.get(RESOLUTION_KEY) or {}),
        **validated["resolutions"],
        "sponsored": _resolution(
            "verified", confidence=1.0, provider="system", prompt_version="system-v1",
        ),
    }
    university.normalized_json = metadata
    university.save()

    for evidence in validated["evidence"]:
        FieldEvidence.objects.create(
            entity_type="university",
            entity_id=university.pk,
            field_name=evidence["field"],
            extracted_value=str(evidence["value"]),
            normalized_value=str(evidence["value"]),
            source_url=evidence["source_url"],
            raw_text=json.dumps(evidence["raw"], ensure_ascii=False),
            confidence_score=max(0.0, min(evidence["confidence"], 1.0)),
            extractor_name="gemini_grounded_quality",
            extraction_method="gemini_grounded",
            validation_notes=evidence["status"],
            crawled_at=timezone.now(),
        )
    return changed
