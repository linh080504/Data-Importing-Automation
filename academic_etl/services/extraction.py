"""Rule-based extraction of university fields and program/major candidates.

Every value returned carries the metadata needed to build a FieldEvidence row:
source_url, page_type, page_title, css_selector, text_snippet, confidence.
"""

import re

from academic_etl.models import DegreeLevel

from .normalize import EMAIL_RE, PHONE_RE, clean_text, normalize_email, normalize_phone

# ---- degree level classification -------------------------------------------

# (regex, degree_level, is_higher_education) — order matters, first match wins.
# Patterns cover English, Vietnamese, Hindi, Chinese, Japanese, Korean, French,
# German, Spanish, Arabic, Portuguese, Indonesian, Russian, Turkish, Italian so
# the pipeline classifies programs correctly for any country.
DEGREE_PATTERNS = [
    # PhD / Doctorate — all languages
    (r"\bph\.?\s?d\b|\bdoctor(al|ate)\b|\bd\.?phil\b"
     r"|\btiến\s?sĩ\b|\btien\s?si\b"             # Vietnamese
     r"|\bडॉक्टरेट\b"                              # Hindi
     r"|\b博士\b"                                    # Chinese/Japanese
     r"|\b박사\b"                                    # Korean
     r"|\bdoctorat\b"                               # French
     r"|\bdoktor(at)?\b"                            # German/Turkish
     r"|\bdoctorado\b"                              # Spanish
     r"|\bdoutorado\b"                              # Portuguese
     r"|\bدكتوراه\b"                                # Arabic
     r"|\bаспирантура\b"                            # Russian
     , DegreeLevel.PHD, True),
    # Postgrad cert/diploma
    (r"\bpost\s*graduate\s+(certificate|cert)\b|\bpg\s*cert\b", DegreeLevel.POSTGRAD_CERT, True),
    (r"\bpost\s*graduate\s+diploma\b|\bpg\s*dip(loma)?\b", DegreeLevel.POSTGRAD_DIPLOMA, True),
    # Master — all languages
    (r"\bmaster(?:'?s)?\b|\bm\.?\s?(sc|a|com|ed|tech|eng|phil|arch|pharm|ca)\b|\bmba\b|\bmca\b|\bllm\b"
     r"|\bthạc\s?sĩ\b|\bthac\s?si\b"              # Vietnamese
     r"|\bस्नातकोत्तर\b"                             # Hindi
     r"|\b硕士\b|\b研究生\b"                          # Chinese
     r"|\b修士\b"                                    # Japanese
     r"|\b석사\b"                                    # Korean
     r"|\bmaîtrise\b"                               # French
     r"|\bmagist(er|rale)\b"                        # German/Italian
     r"|\bmaestr[ií]a\b"                            # Spanish
     r"|\bmestrado\b"                               # Portuguese
     r"|\byüksek\s*lisans\b"                        # Turkish
     r"|\bماجستير\b"                                 # Arabic
     r"|\bмагистр\b"                                # Russian
     r"|\bmagister\b"                               # Indonesian
     , DegreeLevel.MASTER, True),
    # Bachelor — all languages
    (r"\bbachelor(?:'?s)?\b|\bb\.?\s?(sc|a|com|ed|tech|eng|arch|pharm|ba)\b|\bbba\b|\bbca\b|\bllb\b|\bmbbs\b|\bb\.?voc\b"
     r"|\bcử\s?nhân\b|\bcu\s?nhan\b|\bkỹ\s?sư\b|\bky\s?su\b"  # Vietnamese
     r"|\bस्नातक\b"                                  # Hindi
     r"|\b学士\b|\b本科\b"                            # Chinese/Japanese
     r"|\b학사\b"                                    # Korean
     r"|\blicence\b"                                 # French
     r"|\blicenciatura\b|\bgrado\b"                  # Spanish
     r"|\bbacharelado\b"                             # Portuguese
     r"|\blaurea\b"                                  # Italian
     r"|\blisans\b"                                  # Turkish
     r"|\bsarjana\b"                                 # Indonesian
     r"|\bبكالوريوس\b"                               # Arabic
     r"|\bбакалавр\b"                                # Russian
     , DegreeLevel.BACHELOR, True),
    # Associate
    (r"\bassociate\s+degree\b|\bassociate\s+of\b|\bcao\s?đẳng\b|\bcao\s?dang\b"
     r"|\bdiplôme\b"                                # French (2-year)
     , DegreeLevel.ASSOCIATE, True),
    # Diploma
    (r"\badvanced\s+diploma\b|\bdiploma\b|\bdiplom\b", DegreeLevel.DIPLOMA, True),
    # Generic English
    (r"\bundergraduate\b", DegreeLevel.BACHELOR, True),
    (r"\bpostgraduate\b", DegreeLevel.MASTER, True),
    # Non-degree offerings — never auto-imported
    (r"\bshort\s+course\b|\bworkshop\b|\bseminar\b|\bwebinar\b|\bkhóa\s?học\s?ngắn\s?hạn\b|\bkhoa\s?hoc\s?ngan\s?han\b",
     DegreeLevel.NON_DEGREE, False),
    (r"\bboot\s*camp\b|\bbootcamp\b", DegreeLevel.NON_DEGREE, False),
    (r"\blanguage\s+(course|prep|program)\b|\bielts\b|\btoefl\b", DegreeLevel.NON_DEGREE, False),
    (r"\bcertificate\b|\bchứng\s?chỉ\b|\bchung\s?chi\b", DegreeLevel.NON_DEGREE, False),
]

PROGRAM_LINK_KEYWORDS = [
    "program", "programme", "major", "academic", "department", "course",
    "undergraduate", "postgraduate", "bachelor", "master", "phd", "degree",
]

_NOISE_RE = re.compile(
    r"^(home|about|contact|login|apply now|read more|learn more|click here|menu|search)$",
    re.IGNORECASE,
)

# News / announcement / event titles that contain degree keywords but are NOT
# programs (common on Vietnamese university homepages). Dropped at candidacy.
_ANNOUNCEMENT_RE = re.compile(
    r"thông báo|thong bao|lễ\s|kế hoạch|ke hoach|danh sách|danh sach|kết quả|ket qua|"
    r"lịch\s|tin tức|tin tuc|sự kiện|su kien|hội thảo|hoi thao|luận án|luan an|"
    r"công khai|cong khai|nhận bài|tạp chí|tap chi|"
    r"\bannouncement\b|\bnews\b|\bnotice\b|\bceremony\b|\bschedule\b|\bresults?\b|\bevent\b",
    re.IGNORECASE,
)


def classify_degree_level(text: str) -> tuple[str, bool | None, float]:
    """Return (degree_level, is_higher_education, confidence)."""
    lowered = f" {clean_text(text).lower()} "
    for pattern, level, is_he in DEGREE_PATTERNS:
        if re.search(pattern, lowered):
            return level, is_he, 0.8
    return DegreeLevel.UNKNOWN, None, 0.3


# ---- university field extraction --------------------------------------------


def _evidence(value, page, selector, snippet, confidence, extractor):
    return {
        "value": value,
        "source_url": page.get("final_url") or page.get("url", ""),
        "page_title": page.get("title", ""),
        "page_type": page.get("page_type", ""),
        "css_selector": selector,
        "text_snippet": clean_text(snippet)[:500],
        "confidence": confidence,
        "extractor": extractor,
        "raw_html_hash": page.get("html_hash", ""),
    }


def extract_university_fields(pages: list[dict]) -> dict:
    """pages: crawl results with parsed 'soup'. Returns {field: evidence-dict}."""
    fields = {}
    by_type = {}
    for page in pages:
        if page.get("soup") is not None:
            by_type.setdefault(page["page_type"], []).append(page)

    home = (by_type.get("homepage") or [None])[0]

    # name: h1 > og:site_name > <title>
    if home is not None:
        soup = home["soup"]
        h1 = soup.find("h1")
        if h1 and clean_text(h1.get_text()):
            fields["name"] = _evidence(clean_text(h1.get_text())[:500], home, "h1",
                                       h1.get_text(), 0.85, "h1_name")
        else:
            og = soup.find("meta", property="og:site_name")
            if og and og.get("content"):
                fields["name"] = _evidence(clean_text(og["content"])[:500], home,
                                           "meta[property=og:site_name]", og["content"], 0.8, "og_site_name")
            elif home["title"]:
                name = re.split(r"\s*[|\-–:]\s*", home["title"])[0]
                fields["name"] = _evidence(clean_text(name)[:500], home, "title",
                                           home["title"], 0.6, "title_name")

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and clean_text(meta_desc.get("content", "")):
            fields["description"] = _evidence(clean_text(meta_desc["content"]), home,
                                              "meta[name=description]", meta_desc["content"],
                                              0.75, "meta_description")

    # description fallback: first long paragraph on about page / homepage
    if "description" not in fields:
        for page in (by_type.get("about") or []) + ([home] if home else []):
            for p in page["soup"].find_all("p"):
                text = clean_text(p.get_text())
                if len(text) > 120:
                    fields["description"] = _evidence(text[:2000], page, "p", text, 0.6, "first_long_paragraph")
                    break
            if "description" in fields:
                break

    # emails / phones: prefer admissions & contact pages
    contactish = (by_type.get("admissions") or []) + (by_type.get("contact") or []) + ([home] if home else [])
    for page in contactish:
        text = page["soup"].get_text(" ", strip=True)
        if "admissions_contact" not in fields:
            m = EMAIL_RE.search(text)
            if m:
                conf = 0.8 if page["page_type"] in ("admissions", "contact") else 0.55
                fields["admissions_contact"] = _evidence(normalize_email(m.group(0)), page, "",
                                                         text[max(0, m.start() - 60): m.end() + 60], conf, "email_regex")
        if "admissions_phone" not in fields:
            for m in PHONE_RE.finditer(text):
                phone = normalize_phone(m.group(0))
                if not phone:
                    continue
                conf = 0.7 if page["page_type"] in ("admissions", "contact") else 0.5
                fields["admissions_phone"] = _evidence(phone, page, "",
                                                       text[max(0, m.start() - 60): m.end() + 60], conf, "phone_regex")
                break

    # admissions page link
    admissions_pages = by_type.get("admissions") or []
    if admissions_pages:
        page = admissions_pages[0]
        fields["admissions_page_link"] = _evidence(page.get("final_url") or page["url"], page,
                                                   "", page.get("title", ""), 0.85, "admissions_page")

    # tuition / financials: first sentence mentioning fees with a currency/amount
    for page in (by_type.get("tuition") or []) + (by_type.get("admissions") or []):
        text = page["soup"].get_text(" ", strip=True)
        m = re.search(r"[^.]*?(tuition|fee|fees)[^.]*?(₹|rs\.?|inr|\$|usd|eur|£)\s?[\d,]+[^.]*\.", text, re.IGNORECASE)
        if m:
            fields["financials"] = _evidence(clean_text(m.group(0))[:500], page, "",
                                             m.group(0), 0.6, "tuition_sentence")
            break

    # campus life
    for page in by_type.get("campus_life") or []:
        paragraphs = [clean_text(p.get_text()) for p in page["soup"].find_all("p")]
        long_ps = [p for p in paragraphs if len(p) > 80]
        if long_ps:
            fields["campus_student_life"] = _evidence(" ".join(long_ps)[:2000], page, "p",
                                                      long_ps[0], 0.6, "campus_life_paragraphs")
            break

    # international students: a sentence on the international page, value = the
    # ratio/percentage when present (e.g. "12% international students").
    for page in by_type.get("international") or []:
        text = page["soup"].get_text(" ", strip=True)
        m = re.search(r"([^.]*\binternational\s+students?\b[^.]*\.)", text, re.IGNORECASE)
        if m:
            sentence = clean_text(m.group(1))
            pct = re.search(r"\d{1,3}(?:\.\d+)?\s?%|\b1\s+in\s+\d+\b", sentence)
            value = (pct.group(0) if pct else sentence)[:50]
            fields["international_student_ratio"] = _evidence(value, page, "", sentence,
                                                             0.55, "international_info")
            break

    # number of students: "12,000 students"
    for page in pages:
        if page.get("soup") is None:
            continue
        text = page["soup"].get_text(" ", strip=True)
        m = re.search(r"([\d,]{3,})\+?\s+(students|learners)", text, re.IGNORECASE)
        if m:
            fields["number_of_students"] = _evidence(m.group(1).replace(",", ""), page, "",
                                                     text[max(0, m.start() - 60): m.end() + 60],
                                                     0.5, "students_count_regex")
            break

    return fields


# ---- program extraction ------------------------------------------------------

PROGRAM_PAGE_TYPES = ("programs", "departments", "academics")


def extract_programs(pages: list[dict], max_programs: int = 60) -> list[dict]:
    """Extract program/major candidates with evidence metadata."""
    candidates = {}
    program_pages = [p for p in pages if p.get("soup") is not None and p["page_type"] in PROGRAM_PAGE_TYPES]
    # homepage nav links often list programs too
    if not program_pages:
        program_pages = [p for p in pages if p.get("soup") is not None]

    for page in program_pages:
        soup = page["soup"]
        # 1) links whose text looks like a degree/program name
        for a in soup.find_all("a", href=True):
            text = clean_text(a.get_text(" ", strip=True))
            _consider(candidates, text, page, "a", a["href"])
            if len(candidates) >= max_programs:
                break
        # 2) headings & list items
        for tag in soup.find_all(["h2", "h3", "h4", "li"]):
            text = clean_text(tag.get_text(" ", strip=True))
            _consider(candidates, text, page, tag.name, "")
            if len(candidates) >= max_programs:
                break
        if len(candidates) >= max_programs:
            break
    return list(candidates.values())


def _consider(candidates: dict, text: str, page: dict, selector: str, href: str):
    if not text or len(text) < 3 or len(text) > 150 or _NOISE_RE.match(text):
        return
    if _ANNOUNCEMENT_RE.search(text):  # news/event title, not a program
        return
    level, is_he, conf = classify_degree_level(text)
    if level == DegreeLevel.UNKNOWN:
        return
    key = (re.sub(r"\W+", " ", text.lower()).strip(), level)
    if key in candidates:
        return
    from urllib.parse import urljoin
    program_url = urljoin(page.get("final_url") or page.get("url", ""), href) if href else ""
    candidates[key] = {
        "program_name": text[:500],
        "degree_level": level,
        "is_higher_education_program": is_he,
        "confidence": conf,
        "program_url": program_url[:1000],
        "evidence": _evidence(text, page, selector, text, conf, "program_keyword"),
    }
