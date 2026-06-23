"""Gemini grounded enrichment for the required university fields.

The rule-based crawler reads one site's raw HTML and misses anything behind JS,
PDFs, or another language — so coverage of ``campus_student_life`` and
``number_of_students`` is poor. This service asks Gemini the same question a human
would type into a search box, with **Google Search grounding** turned on, so the
answer is built from live search results and carries source URLs we can store as
``FieldEvidence``.

Per institution we request five fields:
    name, website, description, campus_student_life, number_of_students

Design notes:
- Grounding (``google_search`` tool) and structured output (``response_schema``)
  cannot be combined in one Gemini call, so the prompt asks for a JSON object and
  we parse it out of the grounded text (code fences tolerated).
- Responses are cached under ``GEMINI_CACHE_DIR`` keyed by name+country, so
  re-running a country never re-bills the same institution.
- The model is told to return ``null`` for anything it cannot ground, so we
  never fabricate a value to fill a cell.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Text fields this service fills; number_of_students is handled separately (int).
GEMINI_TEXT_FIELDS = (
    "name", "website", "description", "campus_student_life",
    "financials", "global_rank", "student_to_faculty_ratio",
    "international_student_ratio",
    "admissions_contact", "admissions_phone", "admissions_page_link",
    "contact_person",
)
# All fields the service returns (text fields + int/bool fields).
GEMINI_FIELDS = GEMINI_TEXT_FIELDS + (
    "number_of_students", "university_campuses",
    "housing_availability", "student_loan_available", "immigration_support",
)

from .country_registry import get_currency, get_numeric_code
from .normalize import normalize_email, normalize_phone, normalize_url


def country_numeric(code: str) -> str:
    """ISO 3166-1 numeric code (the value the sample CSV stores in `location`)."""
    return get_numeric_code(code)


def country_currency(code: str) -> str:
    return get_currency(code)


_PROMPT_TEMPLATE = """\
You are building a factual catalog of higher-education institutions. Use Google \
Search to verify every fact before answering. Answer ONLY for this specific \
institution:

  Institution: "{name}"
  Country: {country}{city_hint}{wiki_hint}

Return a single JSON object (no prose, no markdown fences) with EXACTLY these keys:

- "name": the institution's official name in English (string).
- "website": the official homepage URL, including https:// (string). The real \
official domain only — not Wikipedia, Facebook, a ranking site, or a directory.
- "description": 2-3 factual sentences in English: what kind of institution it \
is, where it is located, when founded if known, and what it is known for.
- "campus_student_life": 2-3 factual sentences in English about the campus and \
student life (size/location of campus, notable facilities such as library, \
labs, sports, dormitories, student clubs/organisations).
- "number_of_students": the approximate TOTAL student enrolment as an integer \
(no commas, no text), or null if you cannot find a sourced figure.
- "financials": typical ANNUAL undergraduate tuition, formatted EXACTLY as \
"{currency} <amount><unit> ($<usd_low>-<usd_high>)" — use 'm' for millions or \
'k' for thousands as fits {currency}. Examples: "VND 20m-40m ($800-1600)", \
"VND 15m ($600)", "INR 50k-200k ($600-2400)". Use "" if you cannot find tuition.
- "student_to_faculty_ratio": the student-to-faculty ratio as a short string \
such as "24" or "20:1", or "" if unknown.
- "global_rank": the institution's WORLD ranking from a reputable global ranking \
(QS World University Rankings or Times Higher Education), formatted like \
"QS 801-1000" or "THE 1201+". Use "" if the institution is not ranked globally. \
Do NOT use national-only rankings.
- "admissions_contact": the official admissions/general email address (from the \
official website, often in the footer or contact page), or "".
- "admissions_phone": the official phone number in international format (e.g. \
"+84 24 1234 5678", from the official website footer/contact page), or "".
- "admissions_page_link": URL of the official admissions or contact page (same \
domain as the website), or "".
- "contact_person": name of the admissions director or officer, or "".
- "university_campuses": verified number of campuses as an integer, or null.
- "housing_availability": true if the institution has on-campus housing, else false.
- "student_loan_available": true if the institution offers student loans, else false.
- "immigration_support": true if the institution helps international students \
with visa/immigration, else false.
- "international_student_ratio": percentage of international students as a short \
string like "5%", or "".
- "sponsored": false (always false for crawled data).

Rules:
- Ground every field in Google Search results. If you cannot verify a field, use \
null (for number_of_students) or an empty string "" (for the others). Do NOT \
guess or invent — an empty value is correct when unsure.
- ALL text (description, campus_student_life) MUST be in English. Translate if needed.
- Contact details and admissions page must come from the institution's OWN \
official website. The global rank must come from QS or THE.
- Keep description and campus_student_life concise and specific to THIS \
institution — no generic boilerplate.
- Output must be valid JSON parseable by json.loads.
"""


class GeminiNotConfigured(RuntimeError):
    """Raised when no API key / SDK is available."""


def _get_keys() -> list[str]:
    """All configured API keys (GEMINI_API_KEYS list + GEMINI_API_KEY), de-duped
    in order. The daily free quota is per key, so several keys = more budget."""
    keys: list[str] = []
    raw = getattr(settings, "GEMINI_API_KEYS", "") or ""
    for k in raw.split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    single = getattr(settings, "GEMINI_API_KEY", "")
    if single and single not in keys:
        keys.append(single)
    return keys


def _get_models() -> list[str]:
    """Model fallback chain. Daily quota is per model too, so a chain lets one
    key keep going after a model's daily cap."""
    raw = getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash"
    return [m.strip() for m in raw.split(",") if m.strip()]


def is_configured() -> bool:
    return bool(_get_keys())


_clients: dict[str, object] = {}
# (key, model) pairs whose DAILY free quota is exhausted this process — skipped
# so we don't waste calls re-hitting a known-dead bucket.
_exhausted: set[tuple[str, str]] = set()
# Keys rejected with an auth error (invalid/expired) this process — skipped.
_bad_keys: set[str] = set()


def _client_for(api_key: str):
    """Cached google-genai client per key (network/SDK boundary)."""
    if api_key not in _clients:
        try:
            from google import genai  # google-genai SDK
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise GeminiNotConfigured(
                "google-genai is not installed. Run: pip install google-genai"
            ) from exc
        _clients[api_key] = genai.Client(api_key=api_key)
    return _clients[api_key]


def _is_daily_quota(msg: str) -> bool:
    """True if a 429 is the PER-DAY free-tier cap (rotate key/model, don't wait)
    rather than a transient per-minute rate limit (back off and retry)."""
    m = msg.lower().replace(" ", "").replace("_", "")
    if "perminute" in m:
        return False
    return ("perday" in m or "freetierrequests" in m or "requestsperday" in m)


def _is_auth_error(msg: str) -> bool:
    """Credential rejected (expired/invalid key). Not retryable — try next key."""
    m = msg.lower()
    return any(s in m for s in ("401", "unauthenticated", "403", "permission_denied",
                                "api_key_invalid", "api key not valid",
                                "access_token_type_unsupported"))


def _is_transient(msg: str) -> bool:
    if _is_auth_error(msg):
        return False
    m = msg.lower()
    return any(s in m for s in ("429", "resource_exhausted", "rate", "503", "500",
                                "unavailable", "timeout", "deadline",
                                "client has been closed", "client is closed", "connection"))


def _cache_path(name: str, country: str):
    key = hashlib.sha256(f"{name.strip().lower()}|{country.strip().lower()}".encode()).hexdigest()
    cache_dir = settings.GEMINI_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}.json"


def _strip_json(text: str) -> str:
    """Pull a JSON object out of model text that may be fenced or prefixed."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _coerce_int(value):
    """Best-effort enrolment -> positive int, else None (rejects guesses/ranges)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
    else:
        digits = re.sub(r"[^0-9]", "", str(value))
        if not digits:
            return None
        n = int(digits)
    return n if 0 < n <= 2_000_000 else None


def _normalize_contact_fields(fields: dict) -> dict:
    """Keep cached and fresh AI contact values in the project storage format."""
    values = dict(fields or {})
    values["website"] = normalize_url(values.get("website", ""))
    values["admissions_page_link"] = normalize_url(values.get("admissions_page_link", ""))
    values["admissions_contact"] = normalize_email(values.get("admissions_contact", ""))
    values["admissions_phone"] = normalize_phone(values.get("admissions_phone", ""))
    return values


def _grounding_sources(response) -> list[str]:
    """Extract the web source URLs Gemini grounded its answer in."""
    urls: list[str] = []
    try:
        cand = response.candidates[0]
        meta = getattr(cand, "grounding_metadata", None)
        for chunk in (getattr(meta, "grounding_chunks", None) or []):
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", "") if web else ""
            if uri:
                urls.append(uri)
    except (AttributeError, IndexError, TypeError):
        pass
    # de-dupe, keep order
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _build_prompt(name: str, country: str, city: str = "", wikipedia_url: str = "",
                  currency: str = "USD") -> str:
    city_hint = f"\n  Known city/region: {city}" if city else ""
    wiki_hint = f"\n  Wikipedia article (for disambiguation): {wikipedia_url}" if wikipedia_url else ""
    return _PROMPT_TEMPLATE.format(
        name=name, country=country, city_hint=city_hint, wiki_hint=wiki_hint,
        currency=currency,
    )


_MAJORS_PROMPT_TEMPLATE = """\
You are cataloguing the academic programs (majors) offered by ONE university. Use \
Google Search to read the university's OWN official website (especially its \
programs / academics / departments / "ngành đào tạo" pages) before answering.

  University: "{name}"
  Country: {country}{website_hint}{city_hint}

Return a single JSON object (no prose, no markdown fences):

{{
  "programs_page": "<URL of the official page that lists the programs, or ''>",
  "majors": [
    {{"name": "<major/program name in English>", "url": "<URL of that major's page, or ''>"}}
  ]
}}

Rules:
- List the degree programs / majors the university actually offers (bachelor's \
and master's level fields of study, e.g. "Computer Science", "Business \
Administration", "Civil Engineering"). Aim to be COMPLETE.
- Names MUST be in English. If a program is only named in {country}'s language, \
translate it to its standard English equivalent.
- Every major must come from the university's official website. Put the most \
specific official URL you can (the major's own page; else the programs page) in \
"url". Do NOT invent majors or URLs — if you cannot verify the program list, \
return an empty "majors" array.
- Exclude short courses, certificates, language classes and non-degree training.
- Output must be valid JSON parseable by json.loads.
"""


def enrich_majors(name: str, country: str, website: str = "", city: str = "",
                  country_code: str = "", use_cache: bool = True) -> dict:
    """Return the majors of one institution, grounded in its official site.

    Result::

        {"majors": [{"name", "url"}], "programs_page": str, "sources": [...],
         "model": str, "from_cache": bool, "error": ""}

    Never raises for per-institution failures; ``error`` is set and ``majors`` is
    empty instead."""
    cache_file = _cache_path(name + "|majors", country)
    if use_cache and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if "majors" in data:
                data["from_cache"] = True
                return data
        except (json.JSONDecodeError, OSError):
            pass

    from google.genai import types
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.0,
        http_options=types.HttpOptions(timeout=settings.GEMINI_TIMEOUT * 1000),
    )
    website_hint = f"\n  Official website: {website}" if website else ""
    city_hint = f"\n  City/region: {city}" if city else ""
    prompt = _MAJORS_PROMPT_TEMPLATE.format(
        name=name, country=country, website_hint=website_hint, city_hint=city_hint
    )

    response, used_model, err = _generate(prompt, config, label=f"{name} (majors)")
    if response is None:
        return {"majors": [], "programs_page": "", "sources": [], "model": "",
                "from_cache": False, "error": err[:500]}

    raw_text = getattr(response, "text", "") or ""
    sources = _grounding_sources(response)
    try:
        parsed = json.loads(_strip_json(raw_text))
        if not isinstance(parsed, dict):
            raise ValueError("not a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        return {"majors": [], "programs_page": "", "sources": sources, "model": used_model,
                "from_cache": False, "error": f"json_parse: {exc}"[:500]}

    majors = []
    seen = set()
    for item in (parsed.get("majors") or []):
        if isinstance(item, dict):
            mname = str(item.get("name") or "").strip()
            murl = str(item.get("url") or "").strip()
        else:  # tolerate a bare string
            mname, murl = str(item).strip(), ""
        key = mname.lower()
        if not mname or key in seen:
            continue
        seen.add(key)
        majors.append({"name": mname, "url": murl})

    result = {"majors": majors, "programs_page": str(parsed.get("programs_page") or "").strip(),
              "sources": sources, "model": used_model, "from_cache": False, "error": ""}
    try:
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result


def _generate(prompt: str, config, label: str = ""):
    """Run one grounded generation, rotating across (model, key) buckets.

    For each model in the chain, try each key. A per-DAY quota error marks that
    (key, model) bucket exhausted and moves on immediately (no waiting); a
    transient/per-minute error backs off and retries the same bucket. Returns
    ``(response, used_model, "")`` on success, or ``(None, "", error)`` when every
    bucket is exhausted/failed."""
    keys = _get_keys()
    models = _get_models()
    if not keys:
        return None, "", "GEMINI_API_KEY is not set."

    last_err = "all (key, model) buckets exhausted"
    for model in models:
        for key in keys:
            if (key, model) in _exhausted or key in _bad_keys:
                continue
            for attempt in range(settings.GEMINI_MAX_RETRIES):
                try:
                    client = _client_for(key)  # rebuilt if a prior attempt dropped it
                    resp = client.models.generate_content(
                        model=model, contents=prompt, config=config
                    )
                    return resp, model, ""
                except Exception as exc:  # SDK raises various API error types
                    last_err = str(exc)
                    msg = str(exc)
                    if "closed" in msg.lower():
                        _clients.pop(key, None)  # force a fresh client next attempt
                    if _is_auth_error(msg):
                        _bad_keys.add(key)
                        logger.warning("gemini: key …%s rejected (auth) — invalid/expired, skipping",
                                       key[-4:])
                        break  # this key is dead; next key
                    if _is_daily_quota(msg):
                        _exhausted.add((key, model))
                        logger.info("gemini: key …%s exhausted daily quota on %s, rotating",
                                    key[-4:], model)
                        break  # next key / model
                    if _is_transient(msg) and attempt < settings.GEMINI_MAX_RETRIES - 1:
                        sleep = min(2 ** attempt * 2, 30)
                        logger.info("gemini retry %s for %s in %ss (%s)",
                                    attempt + 1, label, sleep, msg[:80])
                        time.sleep(sleep)
                        continue
                    break  # non-retryable for this bucket -> try next
    return None, "", last_err


def enrich_institution(
    name: str,
    country: str,
    city: str = "",
    wikipedia_url: str = "",
    country_code: str = "",
    use_cache: bool = True,
) -> dict:
    """Return enriched fields for one institution.

    Result shape::

        {
          "fields": {name, website, description, campus_student_life, number_of_students},
          "sources": [grounding URLs],
          "raw_text": "<model text>",
          "from_cache": bool,
          "error": "" | "<message>",
        }

    Never raises for per-institution failures (so a batch keeps going); ``error``
    is set instead and ``fields`` is empty. Configuration problems still raise
    ``GeminiNotConfigured`` from :func:`_get_client`.
    """
    cache_file = _cache_path(name, country)
    if use_cache and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_fields = data.get("fields") or {}
            # Only reuse cache that already has the full field set — older cache
            # (pre-expansion) is missing financials/contacts/etc., so re-fetch it.
            if all(k in cached_fields for k in GEMINI_FIELDS):
                data["fields"] = _normalize_contact_fields(cached_fields)
                data["from_cache"] = True
                return data
        except (json.JSONDecodeError, OSError):
            pass  # fall through and re-fetch

    from google.genai import types

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.0,
        http_options=types.HttpOptions(timeout=settings.GEMINI_TIMEOUT * 1000),
    )
    prompt = _build_prompt(name, country, city, wikipedia_url,
                           currency=country_currency(country_code))

    response, used_model, err = _generate(prompt, config, label=name)
    if response is None:
        logger.warning("gemini enrich failed for %s: %s", name, err)
        return {"fields": {}, "sources": [], "raw_text": "", "from_cache": False, "error": err[:500]}

    raw_text = getattr(response, "text", "") or ""
    sources = _grounding_sources(response)
    try:
        parsed = json.loads(_strip_json(raw_text))
        if not isinstance(parsed, dict):
            raise ValueError("not a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("gemini JSON parse failed for %s: %s", name, exc)
        return {"fields": {}, "sources": sources, "raw_text": raw_text, "from_cache": False,
                "error": f"json_parse: {exc}"[:500]}

    fields = _normalize_contact_fields({
        f: str(parsed.get(f) or "").strip() for f in GEMINI_TEXT_FIELDS
    })
    fields["number_of_students"] = _coerce_int(parsed.get("number_of_students"))
    fields["university_campuses"] = _coerce_int(parsed.get("university_campuses"))
    for bf in ("housing_availability", "student_loan_available", "immigration_support"):
        raw = parsed.get(bf)
        if isinstance(raw, bool):
            fields[bf] = raw
        elif isinstance(raw, str):
            fields[bf] = raw.lower() in ("true", "yes", "1")
        else:
            fields[bf] = False
    result = {"fields": fields, "sources": sources, "raw_text": raw_text,
              "model": used_model, "from_cache": False, "error": ""}
    try:
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result
