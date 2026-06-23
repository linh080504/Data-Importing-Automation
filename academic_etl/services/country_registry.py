"""Centralized country configuration registry.

Replaces scattered hardcoded country data (COUNTRY_CODES, _COUNTRY_META,
COUNTRY_OPTIONS, _NON_ENGLISH_URL_MARKERS) with a single DB-backed registry
that falls back to built-in defaults when no CountryConfig row exists.
"""

import functools
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in defaults — migrated from discovery.py, gemini_enrich.py, crawler.py
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, dict] = {
    "IN": {
        "country_name": "India", "currency_code": "INR", "numeric_code": "356",
        "denomination_config": {"k": 1_000, "L": 100_000, "lakh": 100_000, "Cr": 10_000_000, "crore": 10_000_000},
        "primary_languages": ["hi", "en"],
        "url_language_markers": ["/hi/", "/hindi/"],
        "degree_level_map": {
            "स्नातक": "bachelor",
            "स्नातकोत्तर": "master",
            "डॉक्टरेट": "phd",
        },
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "VN": {
        "country_name": "Vietnam", "currency_code": "VND", "numeric_code": "704",
        "denomination_config": {"k": 1_000, "tr": 1_000_000, "triệu": 1_000_000, "m": 1_000_000, "tỷ": 1_000_000_000},
        "primary_languages": ["vi", "en"],
        "url_language_markers": ["/vi/", "/vi-vn", "/vn/", "/tieng-viet", "lang=vi", "language=vi"],
        "degree_level_map": {
            "tiến sĩ": "phd", "tien si": "phd",
            "thạc sĩ": "master", "thac si": "master",
            "cử nhân": "bachelor", "cu nhan": "bachelor",
            "kỹ sư": "bachelor", "ky su": "bachelor",
            "cao đẳng": "associate", "cao dang": "associate",
        },
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "US": {
        "country_name": "United States", "currency_code": "USD", "numeric_code": "840",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en"],
        "url_language_markers": [],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "GB": {
        "country_name": "United Kingdom", "currency_code": "GBP", "numeric_code": "826",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en"],
        "url_language_markers": [],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "AU": {
        "country_name": "Australia", "currency_code": "AUD", "numeric_code": "036",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en"],
        "url_language_markers": [],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "CA": {
        "country_name": "Canada", "currency_code": "CAD", "numeric_code": "124",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en", "fr"],
        "url_language_markers": ["/fr/", "/francais"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "DE": {
        "country_name": "Germany", "currency_code": "EUR", "numeric_code": "276",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["de", "en"],
        "url_language_markers": ["/de/", "/deutsch"],
        "degree_level_map": {"diplom": "bachelor", "doktor": "phd", "magister": "master"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "FR": {
        "country_name": "France", "currency_code": "EUR", "numeric_code": "250",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["fr", "en"],
        "url_language_markers": ["/fr/", "/francais"],
        "degree_level_map": {"licence": "bachelor", "maîtrise": "master", "doctorat": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "JP": {
        "country_name": "Japan", "currency_code": "JPY", "numeric_code": "392",
        "denomination_config": {"k": 1_000, "万": 10_000, "man": 10_000},
        "primary_languages": ["ja", "en"],
        "url_language_markers": ["/ja/", "/jp/", "/japanese"],
        "degree_level_map": {"学士": "bachelor", "修士": "master", "博士": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "CN": {
        "country_name": "China", "currency_code": "CNY", "numeric_code": "156",
        "denomination_config": {"k": 1_000, "万": 10_000, "元": 1},
        "primary_languages": ["zh", "en"],
        "url_language_markers": ["/zh/", "/cn/", "/chinese", "/zh-cn", "/zh-hans"],
        "degree_level_map": {
            "学士": "bachelor", "本科": "bachelor",
            "硕士": "master", "研究生": "master",
            "博士": "phd",
        },
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "SG": {
        "country_name": "Singapore", "currency_code": "SGD", "numeric_code": "702",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en", "zh", "ms", "ta"],
        "url_language_markers": ["/zh/", "/ms/"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "KR": {
        "country_name": "South Korea", "currency_code": "KRW", "numeric_code": "410",
        "denomination_config": {"k": 1_000, "만": 10_000, "원": 1},
        "primary_languages": ["ko", "en"],
        "url_language_markers": ["/ko/", "/kr/", "/korean"],
        "degree_level_map": {"학사": "bachelor", "석사": "master", "박사": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "MY": {
        "country_name": "Malaysia", "currency_code": "MYR", "numeric_code": "458",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["ms", "en"],
        "url_language_markers": ["/ms/", "/bm/", "/malay"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "TH": {
        "country_name": "Thailand", "currency_code": "THB", "numeric_code": "764",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["th", "en"],
        "url_language_markers": ["/th/", "/thai"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "ID": {
        "country_name": "Indonesia", "currency_code": "IDR", "numeric_code": "360",
        "denomination_config": {"k": 1_000, "jt": 1_000_000, "juta": 1_000_000, "M": 1_000_000},
        "primary_languages": ["id", "en"],
        "url_language_markers": ["/id/", "/indonesian"],
        "degree_level_map": {"sarjana": "bachelor", "magister": "master", "doktor": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "PH": {
        "country_name": "Philippines", "currency_code": "PHP", "numeric_code": "608",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["tl", "en"],
        "url_language_markers": ["/tl/", "/filipino"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "NL": {
        "country_name": "Netherlands", "currency_code": "EUR", "numeric_code": "528",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["nl", "en"],
        "url_language_markers": ["/nl/", "/dutch"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "BR": {
        "country_name": "Brazil", "currency_code": "BRL", "numeric_code": "076",
        "denomination_config": {"k": 1_000, "M": 1_000_000, "mil": 1_000},
        "primary_languages": ["pt", "en"],
        "url_language_markers": ["/pt/", "/pt-br", "/portugues"],
        "degree_level_map": {"bacharelado": "bachelor", "mestrado": "master", "doutorado": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "MX": {
        "country_name": "Mexico", "currency_code": "MXN", "numeric_code": "484",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["es", "en"],
        "url_language_markers": ["/es/", "/espanol"],
        "degree_level_map": {"licenciatura": "bachelor", "maestría": "master", "doctorado": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "EG": {
        "country_name": "Egypt", "currency_code": "EGP", "numeric_code": "818",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["ar", "en"],
        "url_language_markers": ["/ar/", "/arabic"],
        "degree_level_map": {
            "بكالوريوس": "bachelor",
            "ماجستير": "master",
            "دكتوراه": "phd",
        },
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "SA": {
        "country_name": "Saudi Arabia", "currency_code": "SAR", "numeric_code": "682",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["ar", "en"],
        "url_language_markers": ["/ar/", "/arabic"],
        "degree_level_map": {
            "بكالوريوس": "bachelor",
            "ماجستير": "master",
            "دكتوراه": "phd",
        },
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "AE": {
        "country_name": "United Arab Emirates", "currency_code": "AED", "numeric_code": "784",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["ar", "en"],
        "url_language_markers": ["/ar/", "/arabic"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "NG": {
        "country_name": "Nigeria", "currency_code": "NGN", "numeric_code": "566",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en"],
        "url_language_markers": [],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "KE": {
        "country_name": "Kenya", "currency_code": "KES", "numeric_code": "404",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en", "sw"],
        "url_language_markers": ["/sw/"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "ZA": {
        "country_name": "South Africa", "currency_code": "ZAR", "numeric_code": "710",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en", "af", "zu"],
        "url_language_markers": ["/af/", "/zu/"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "ES": {
        "country_name": "Spain", "currency_code": "EUR", "numeric_code": "724",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["es", "en"],
        "url_language_markers": ["/es/", "/espanol"],
        "degree_level_map": {"grado": "bachelor", "licenciatura": "bachelor", "maestría": "master", "doctorado": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "IT": {
        "country_name": "Italy", "currency_code": "EUR", "numeric_code": "380",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["it", "en"],
        "url_language_markers": ["/it/", "/italiano"],
        "degree_level_map": {"laurea": "bachelor", "laurea magistrale": "master", "dottorato": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "RU": {
        "country_name": "Russia", "currency_code": "RUB", "numeric_code": "643",
        "denomination_config": {"k": 1_000, "тыс": 1_000, "M": 1_000_000},
        "primary_languages": ["ru", "en"],
        "url_language_markers": ["/ru/", "/russian"],
        "degree_level_map": {
            "бакалавр": "bachelor",
            "магистр": "master",
            "аспирантура": "phd",
        },
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "TR": {
        "country_name": "Turkey", "currency_code": "TRY", "numeric_code": "792",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["tr", "en"],
        "url_language_markers": ["/tr/", "/turkce"],
        "degree_level_map": {"lisans": "bachelor", "yüksek lisans": "master", "doktora": "phd"},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "PK": {
        "country_name": "Pakistan", "currency_code": "PKR", "numeric_code": "586",
        "denomination_config": {"k": 1_000, "L": 100_000, "lakh": 100_000, "Cr": 10_000_000},
        "primary_languages": ["ur", "en"],
        "url_language_markers": ["/ur/", "/urdu"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
    "BD": {
        "country_name": "Bangladesh", "currency_code": "BDT", "numeric_code": "050",
        "denomination_config": {"k": 1_000, "L": 100_000, "lakh": 100_000},
        "primary_languages": ["bn", "en"],
        "url_language_markers": ["/bn/", "/bangla"],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
    },
}

# Name -> code lookup (migrated from discovery.py COUNTRY_CODES)
_NAME_TO_CODE: dict[str, str] = {}
_CODE_TO_NAME: dict[str, str] = {}
for _code, _cfg in _DEFAULTS.items():
    _name_lower = _cfg["country_name"].lower()
    _NAME_TO_CODE[_name_lower] = _code
    _CODE_TO_NAME[_code] = _cfg["country_name"]
# Extra aliases
_NAME_TO_CODE.update({
    "viet nam": "VN", "korea, republic of": "KR",
    "south korea": "KR", "united states of america": "US",
})


# ---------------------------------------------------------------------------
# In-memory cache for DB lookups
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=256)
def _cached_db_lookup(country_code: str) -> dict | None:
    """Fetch a CountryConfig from DB, cached across calls in the same process."""
    try:
        from academic_etl.models import CountryConfig
        obj = CountryConfig.objects.filter(country_code=country_code.upper()).first()
        if obj is None:
            return None
        return {
            "country_name": obj.country_name,
            "country_code": obj.country_code,
            "currency_code": obj.currency_code,
            "numeric_code": obj.numeric_code,
            "denomination_config": obj.denomination_config or {},
            "primary_languages": obj.primary_languages or [],
            "url_language_markers": obj.url_language_markers or [],
            "degree_level_map": obj.degree_level_map or {},
            "preferred_providers": obj.preferred_providers or [],
            "max_institutions": obj.max_institutions,
            "crawl_frequency": obj.crawl_frequency,
            "is_active": obj.is_active,
        }
    except Exception:
        return None


def clear_cache():
    """Clear the in-memory cache (call after DB updates)."""
    _cached_db_lookup.cache_clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_country_config(country_code: str) -> dict:
    """Return the config dict for a country. DB first, then built-in defaults.

    Always returns a dict (never None). Unknown countries get a minimal config
    with USD currency and empty collections.
    """
    code = (country_code or "").strip().upper()
    if not code:
        return _minimal_config("", "")

    db_cfg = _cached_db_lookup(code)
    if db_cfg is not None:
        return db_cfg

    defaults = _DEFAULTS.get(code)
    if defaults is not None:
        return {**defaults, "country_code": code, "max_institutions": 200, "crawl_frequency": "monthly", "is_active": True}

    return _minimal_config(code, _CODE_TO_NAME.get(code, code))


def get_currency(country_code: str) -> str:
    """ISO 4217 currency code for a country (default: USD)."""
    return get_country_config(country_code).get("currency_code", "USD") or "USD"


def get_numeric_code(country_code: str) -> str:
    """ISO 3166-1 numeric code for a country."""
    return get_country_config(country_code).get("numeric_code", "")


def get_denomination_config(country_code: str) -> dict:
    """Denomination abbreviations and multipliers for financial formatting."""
    return get_country_config(country_code).get("denomination_config", {})


def get_degree_level_map(country_code: str) -> dict:
    """Local degree terms -> canonical DegreeLevel values."""
    return get_country_config(country_code).get("degree_level_map", {})


def get_language_markers(country_code: str) -> list:
    """Non-English URL path markers for this country's local language sites."""
    return get_country_config(country_code).get("url_language_markers", [])


def get_primary_languages(country_code: str) -> list:
    """ISO 639-1 language codes for this country."""
    return get_country_config(country_code).get("primary_languages", [])


def get_preferred_providers(country_code: str) -> list:
    """Ordered list of discovery providers for this country."""
    return get_country_config(country_code).get("preferred_providers", ["wikipedia", "wikidata"])


def resolve_country(country: str = "", country_code: str = "") -> tuple[str, str]:
    """Resolve a country name or code to (name, code) pair.

    Replaces discovery.resolve_country() with registry-backed lookup.
    """
    name = (country or "").strip()
    code = (country_code or "").strip().upper()
    if name and not code:
        code = _NAME_TO_CODE.get(name.lower(), "")
        if not code:
            # Try DB lookup by name
            try:
                from academic_etl.models import CountryConfig
                obj = CountryConfig.objects.filter(country_name__iexact=name).first()
                if obj:
                    code = obj.country_code
            except Exception:
                pass
    if code and not name:
        cfg = get_country_config(code)
        name = cfg.get("country_name", code)
    return name, code


def resolve_numeric_country(numeric_code: str) -> tuple[str, str]:
    """Resolve an ISO 3166-1 numeric country code to (name, alpha-2 code).

    Uses CountryConfig rows first, then the built-in registry. Unknown numeric
    codes return ("", "") so callers can preserve the original value without
    inventing a country.
    """
    numeric = (numeric_code or "").strip().zfill(3)
    if not numeric:
        return "", ""
    try:
        from academic_etl.models import CountryConfig
        obj = CountryConfig.objects.filter(numeric_code=numeric).first()
        if obj:
            return obj.country_name, obj.country_code
    except Exception:
        pass
    for code, cfg in _DEFAULTS.items():
        if cfg.get("numeric_code") == numeric:
            return cfg["country_name"], code
    return "", ""


def get_all_country_options() -> list[tuple[str, str]]:
    """Return (name, code) pairs for the dashboard dropdown.

    Replaces the hardcoded COUNTRY_OPTIONS list in views.py.
    """
    try:
        from academic_etl.models import CountryConfig
        db_options = list(
            CountryConfig.objects.filter(is_active=True)
            .order_by("country_name")
            .values_list("country_name", "country_code")
        )
        if db_options:
            return db_options
    except Exception:
        pass
    return sorted(
        [(cfg["country_name"], code) for code, cfg in _DEFAULTS.items()],
        key=lambda x: x[0],
    )


def get_all_non_english_markers(country_code: str = "") -> tuple:
    """Build the full set of non-English URL markers.

    Combines universal markers with country-specific ones from the registry.
    Replaces the hardcoded _NON_ENGLISH_URL_MARKERS in crawler.py.
    """
    universal = ["/zh/", "/ja/", "/ko/", "/fr/", "/de/", "/es/", "/ru/", "/th/", "/lo/", "/km/"]
    if country_code:
        country_markers = get_language_markers(country_code)
        return tuple(dict.fromkeys(universal + country_markers))
    return tuple(universal)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_config(code: str, name: str) -> dict:
    return {
        "country_name": name or code,
        "country_code": code,
        "currency_code": "USD",
        "numeric_code": "",
        "denomination_config": {"k": 1_000, "M": 1_000_000},
        "primary_languages": ["en"],
        "url_language_markers": [],
        "degree_level_map": {},
        "preferred_providers": ["wikipedia", "wikidata"],
        "max_institutions": 200,
        "crawl_frequency": "monthly",
        "is_active": True,
    }
