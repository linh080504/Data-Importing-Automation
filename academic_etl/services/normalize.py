"""Cleaning / normalization helpers shared by the CSV loader, extractor and validator."""

import re
import unicodedata
from urllib.parse import urlparse

from django.utils.text import slugify

# Common UTF-8-read-as-cp1252 mojibake found in the seed CSV ("â€”", "â€™", ...).
_MOJIBAKE_MARKERS = ("â€", "Ã©", "Ã¨", "Ã¢", "Â")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Require an explicit international prefix. Guessing a country code for a
# local-looking number creates more bad data than it fixes.
PHONE_RE = re.compile(r"(?<![\w+])(?:\+|00)\s*\d[\d\s\-().]{6,24}\d(?!\w)")
_YEAR_RANGE_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}\s*[-/]\s*(?:19|20)\d{2}(?!\d)")


def fix_mojibake(text: str) -> str:
    if not text or not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
        return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def clean_text(value) -> str:
    if value is None:
        return ""
    text = fix_mojibake(str(value))
    # Normalize to NFC so Vietnamese diacritics (often served decomposed/NFD)
    # match our keyword/label patterns reliably.
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(value) -> str:
    url = clean_text(value)
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        return ""
    return url.rstrip("/")


def url_domain(value) -> str:
    url = normalize_url(value)
    if not url:
        return ""
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def normalize_email(value) -> str:
    match = EMAIL_RE.search(clean_text(value))
    return match.group(0).lower() if match else ""


def normalize_phone(value) -> str:
    text = clean_text(value)
    for match in PHONE_RE.finditer(text):
        raw = match.group(0)
        # Academic years such as "2023-2024" were accepted as phone numbers
        # after some upstream sources prefixed them with a country code.
        if _YEAR_RANGE_RE.search(raw):
            continue
        digits = re.sub(r"\D", "", raw)
        if raw.lstrip().startswith("00"):
            digits = digits[2:]
        # E.164: country code plus subscriber number, at most 15 digits.
        if not 8 <= len(digits) <= 15 or digits.startswith("0"):
            continue
        return "+" + digits
    return ""


def is_valid_phone(value) -> bool:
    """True only for a canonical E.164 phone number stored by this project."""
    text = clean_text(value)
    return bool(text) and normalize_phone(text) == text


def normalize_bool(value):
    """'0'/'1'/'true'/'yes' -> bool; empty/unknown -> None."""
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    if text in ("1", "true", "yes", "y"):
        return True
    if text in ("0", "false", "no", "n"):
        return False
    return None


def normalize_int(value):
    text = clean_text(value).replace(",", "")
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def make_slug(name: str, city: str = "") -> str:
    base = slugify(name)
    if city:
        city_slug = slugify(city)
        if city_slug and city_slug not in base:
            base = f"{base}-{city_slug}"
    return base[:490]


def normalize_program_name(name: str) -> str:
    """Canonical key for program dedup: lowercase, collapsed whitespace, no punctuation."""
    text = clean_text(name).lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()
