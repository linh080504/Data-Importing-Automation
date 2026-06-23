"""Classify institutions as higher-education (crawlable) or not, by name keywords.

Conservative by design: anything ambiguous gets needs_review instead of valid,
so it is never auto-crawled/auto-imported.
"""

import re

from academic_etl.models import (
    INVALID_INSTITUTION_TYPES,
    VALID_INSTITUTION_TYPES,
    InstitutionSeed,
    InstitutionType,
)

# Junk entries: Wikipedia categories/concepts that aren't specific institutions
_JUNK_RE = re.compile(
    r"^(list of|lists of|affiliating|deemed university$|state university \(|"
    r"central university \(|skill university \(|private university \(|"
    r"education in|higher education in|history of)",
    re.IGNORECASE,
)

# Order matters: more specific patterns first. (pattern, type, confidence)
_INVALID_PATTERNS = [
    (r"\bhigh\s*school\b", InstitutionType.HIGH_SCHOOL),
    (r"\bsecondary\s*school\b", InstitutionType.SECONDARY_SCHOOL),
    (r"\bprimary\s*school\b", InstitutionType.PRIMARY_SCHOOL),
    (r"\belementary\s*school\b", InstitutionType.PRIMARY_SCHOOL),
    (r"\bkindergarten\b|\bpre-?school\b", InstitutionType.KINDERGARTEN),
    (r"\blanguage\s*(center|centre|school|institute)\b", InstitutionType.LANGUAGE_CENTER),
    (r"\btraining\s*(center|centre)\b", InstitutionType.TRAINING_CENTER),
    (r"\bcoaching\b", InstitutionType.COACHING_CENTER),
    (r"\bboot\s*camp\b|\bbootcamp\b", InstitutionType.BOOTCAMP),
    (r"\btuition\s*(center|centre)\b", InstitutionType.COACHING_CENTER),
]


def is_junk_entry(name: str) -> bool:
    """True if the name is a Wikipedia category/concept, not a specific institution."""
    return bool(_JUNK_RE.search((name or "").strip()))

_VALID_PATTERNS = [
    (r"\binstitute\s+of\s+technology\b|\biit\b|\bnit\b", InstitutionType.INSTITUTE_OF_TECHNOLOGY, 0.95),
    (r"\bmedical\s+(university|college|school)\b|\bmedicine\b|\bdental\b|\bayurved",
     InstitutionType.MEDICAL_UNIVERSITY, 0.9),
    (r"\bbusiness\s+school\b|\bmanagement\s+(institute|school)\b|\bschool\s+of\s+business\b",
     InstitutionType.BUSINESS_SCHOOL, 0.9),
    (r"\b(art|arts|design|music|fine\s+arts)\s+(school|academy|college|institute)\b|\bschool\s+of\s+(art|design|music)\b",
     InstitutionType.ART_SCHOOL, 0.85),
    (r"\bgraduate\s+school\b", InstitutionType.GRADUATE_SCHOOL, 0.9),
    (r"\bpost\s*graduate\b|\bpostgraduate\b", InstitutionType.POSTGRADUATE_INSTITUTE, 0.85),
    (r"\bpolytechnic\b", InstitutionType.POLYTECHNIC, 0.95),
    # University — multilingual patterns
    (r"\buniversit"                                   # EN/DE/FR/IT/ID
     r"|大学"                                          # Chinese/Japanese
     r"|대학교"                                        # Korean
     r"|विश्वविद्यालय"                                  # Hindi
     r"|\buniversité\b"                               # French
     r"|\büniversite\b"                               # Turkish
     r"|\buniversidade\b"                             # Portuguese
     r"|\bجامعة\b"                                    # Arabic
     r"|\bуниверситет\b"                              # Russian
     , InstitutionType.UNIVERSITY, 0.95),
    # Institute — multilingual
    (r"\binstitut"                                     # EN/FR/DE
     r"|学院"                                          # Chinese
     r"|\bинститут\b"                                 # Russian
     r"|\bمعهد\b"                                     # Arabic
     , InstitutionType.INSTITUTE, 0.8),
    # College
    (r"\bcollege\b"
     r"|대학\b"                                        # Korean (college, without 교)
     r"|\bkollej\b"                                   # Turkish
     r"|\bكلية\b"                                     # Arabic
     , InstitutionType.COLLEGE, 0.75),
    # École / Hochschule / Fachhochschule
    (r"\bécole\b|\bhochschule\b|\bfachhochschule\b", InstitutionType.INSTITUTE, 0.8),
    (r"\bacademy\b", InstitutionType.INSTITUTE, 0.55),
    (r"\bschool\s+of\b", InstitutionType.INSTITUTE, 0.6),
]

# Academic TLD patterns boost confidence for ambiguous names.
_ACADEMIC_DOMAIN_RE = re.compile(
    r"\.(edu|ac)(\.[a-z]{2})?$|\.edu\.[a-z]{2}$", re.IGNORECASE
)


def classify_institution(name: str, website: str = "") -> tuple[str, str, float]:
    """Return (institution_type, seed_status, confidence).

    seed_status is one of InstitutionSeed.Status: VALID, INVALID, NEEDS_REVIEW.
    """
    lowered = (name or "").lower()

    if is_junk_entry(name):
        return InstitutionType.UNKNOWN, InstitutionSeed.Status.INVALID, 0.95

    for pattern, itype in _INVALID_PATTERNS:
        if re.search(pattern, lowered):
            return itype, InstitutionSeed.Status.INVALID, 0.9

    best = None
    for pattern, itype, conf in _VALID_PATTERNS:
        if re.search(pattern, lowered):
            best = (itype, conf)
            break

    domain_is_academic = bool(website) and bool(
        _ACADEMIC_DOMAIN_RE.search(_host(website))
    )

    if best is None:
        if domain_is_academic:
            return InstitutionType.UNKNOWN, InstitutionSeed.Status.NEEDS_REVIEW, 0.5
        return InstitutionType.UNKNOWN, InstitutionSeed.Status.NEEDS_REVIEW, 0.3

    itype, conf = best
    if domain_is_academic:
        conf = min(1.0, conf + 0.05)

    # Colleges need human confirmation that they offer bachelor+ programs
    if itype == InstitutionType.COLLEGE:
        return itype, InstitutionSeed.Status.NEEDS_REVIEW, min(conf, 0.6)
    if itype in VALID_INSTITUTION_TYPES and conf >= 0.7:
        return itype, InstitutionSeed.Status.VALID, conf
    if itype in INVALID_INSTITUTION_TYPES:
        return itype, InstitutionSeed.Status.INVALID, conf
    return itype, InstitutionSeed.Status.NEEDS_REVIEW, conf


def _host(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url if "//" in url else f"http://{url}").netloc
    except ValueError:
        return ""
