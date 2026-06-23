"""Rule-based extraction of a single program/major detail page.

`extract_program_detail(page)` parses one crawled program page (with a parsed
BeautifulSoup `soup`) and returns ``{field: evidence-dict}`` for the program
fields, reusing the same evidence shape as `extraction._evidence`. Values come
from definition lists (`<dt>/<dd>`), tables (`<th>/<td>`), "Label: value" text
patterns, and labelled sections (requirements / career outcomes).

Degree-level refinement / non-degree flagging is left to the caller
(`pipeline._apply_program_detail`) which classifies on the richer detail text.
"""

import re

from .extraction import _evidence
from .normalize import clean_text

# field -> (label phrases [specific first], confidence, extractor, max length)
# English first, then Vietnamese (with & without diacritics) for VN program pages.
LABELED_FIELDS = {
    "duration": (["course length", "program length", "programme length",
                  "length of study", "duration", "length",
                  "thời gian đào tạo", "thoi gian dao tao", "thời lượng", "thoi luong"],
                 0.7, "label_duration", 100),
    "study_mode": (["mode of study", "study mode", "delivery mode", "mode of delivery",
                    "attendance", "delivery", "mode",
                    "hình thức đào tạo", "hinh thuc dao tao", "hình thức học"],
                   0.65, "label_study_mode", 100),
    "language": (["language of instruction", "medium of instruction",
                  "language of study", "taught in", "language",
                  "ngôn ngữ giảng dạy", "ngon ngu giang day", "ngôn ngữ", "ngon ngu"],
                 0.65, "label_language", 100),
    "tuition_fee": (["tuition fees", "tuition fee", "tuition and fees", "annual tuition",
                     "tuition", "fees", "fee", "học phí", "hoc phi"],
                    0.6, "label_tuition", 255),
    "intake": (["next intake", "intake", "start date", "commencement",
                "semester start", "starts", "entry date",
                "kỳ nhập học", "ky nhap hoc", "thời gian tuyển sinh", "khai giảng"],
               0.6, "label_intake", 255),
    "application_deadline": (["application deadline", "apply by", "closing date", "deadline",
                              "hạn nộp hồ sơ", "han nop ho so", "hạn đăng ký", "thời hạn đăng ký"],
                             0.6, "label_deadline", 255),
    "faculty_or_school": (["faculty of", "school of", "college of", "faculty",
                           "school", "college", "department", "khoa", "viện"],
                          0.6, "label_faculty", 255),
    "field_of_study": (["field of study", "subject area", "study area", "discipline", "field",
                        "ngành học", "chuyên ngành", "chuyen nganh", "ngành", "nganh"],
                       0.55, "label_field", 255),
    "accreditation": (["accredited by", "accreditation", "accredited",
                       "kiểm định", "kiem dinh", "công nhận"], 0.6, "label_accreditation", 255),
}

# (token, ISO code) — symbols checked verbatim, words case-insensitively.
_CURRENCIES = [
    ("₫", "VND"), ("vnd", "VND"), ("đồng", "VND"), ("dong", "VND"),
    ("€", "EUR"), ("eur", "EUR"), ("£", "GBP"), ("gbp", "GBP"),
    ("₹", "INR"), ("inr", "INR"), ("rmb", "CNY"), ("cny", "CNY"),
    ("usd", "USD"), ("us$", "USD"), ("$", "USD"), ("¥", "JPY"), ("jpy", "JPY"),
]

_REQUIREMENT_KEYWORDS = ["entry requirement", "admission requirement", "admissions requirement",
                         "requirements", "eligibility", "prerequisite", "who can apply",
                         "điều kiện", "dieu kien", "yêu cầu", "yeu cau", "đối tượng", "xét tuyển"]
_CAREER_KEYWORDS = ["career outcome", "career prospect", "career opportunit", "employability",
                    "employment", "graduate outcome", "career", "after graduation",
                    "cơ hội nghề nghiệp", "co hoi nghe nghiep", "việc làm", "viec lam",
                    "vị trí việc làm", "nghề nghiệp"]


def _label_matches(label: str, patterns: list[str]) -> str:
    for p in patterns:
        if re.search(r"\b" + re.escape(p) + r"\b", label):
            return p
    return ""


def _labeled_value(soup, full_text: str, patterns: list[str]):
    """Return (value, snippet, selector) for the first label match."""
    # 1) definition lists / table header-value pairs
    for tag in soup.find_all(["dt", "th", "td"]):
        label = clean_text(tag.get_text()).lower()
        if not label or len(label) > 60:
            continue
        if _label_matches(label, patterns):
            sibling = tag.find_next_sibling(["dd", "td"])
            if sibling:
                val = clean_text(sibling.get_text())
                # reject only an empty value or one that is *exactly* a label word
                if val and len(val) < 300 and val.lower() not in patterns:
                    return val, f"{label}: {val}"[:500], f"{tag.name}+{sibling.name}"
    # 2) "Label: value" inline in text
    for p in patterns:
        m = re.search(r"\b" + re.escape(p) + r"\b\s*[:\-–]\s*([^\n.|]{1,120})",
                      full_text, re.IGNORECASE)
        if m:
            val = clean_text(m.group(1))
            if val:
                return val, m.group(0)[:500], "text"
    return "", "", ""


def detect_currency(text: str) -> str:
    low = (text or "").lower()
    for token, code in _CURRENCIES:
        haystack = text if any(ch in token for ch in "₫€£₹¥$") else low
        if token in haystack:
            return code
    return ""


def _section_text(soup, keywords: list[str]) -> str:
    for heading in soup.find_all(["h2", "h3", "h4", "strong", "dt", "th"]):
        label = clean_text(heading.get_text()).lower()
        if not label or not any(k in label for k in keywords):
            continue
        parts = []
        for sib in heading.find_all_next():
            if sib.name in ("h2", "h3", "h4"):
                break
            if sib.name in ("p", "li"):
                t = clean_text(sib.get_text())
                if t:
                    parts.append(t)
            if len(" ".join(parts)) > 600:
                break
        text = " ".join(parts)
        if len(text) > 40:
            return text[:2000]
    return ""


def extract_program_detail(page: dict) -> dict:
    """Return {field: evidence-dict} extracted from one program detail page."""
    soup = page.get("soup")
    if soup is None:
        return {}
    fields = {}
    full_text = soup.get_text(" ", strip=True)

    # program name (h1 / title)
    h1 = soup.find("h1")
    if h1 and clean_text(h1.get_text()):
        fields["program_name"] = _evidence(clean_text(h1.get_text())[:500], page, "h1",
                                           h1.get_text(), 0.8, "program_h1")

    # description: meta description, else first substantial paragraph
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and clean_text(meta.get("content", "")):
        fields["description"] = _evidence(clean_text(meta["content"])[:2000], page,
                                          "meta[name=description]", meta["content"],
                                          0.7, "meta_description")
    else:
        for p in soup.find_all("p"):
            t = clean_text(p.get_text())
            if len(t) > 120:
                fields["description"] = _evidence(t[:2000], page, "p", t, 0.55,
                                                  "first_long_paragraph")
                break

    # labelled scalar fields
    for field, (patterns, conf, extractor, maxlen) in LABELED_FIELDS.items():
        val, snippet, selector = _labeled_value(soup, full_text, patterns)
        if val:
            fields[field] = _evidence(val[:maxlen], page, selector, snippet, conf, extractor)

    # currency derived from the tuition value/snippet
    if "tuition_fee" in fields:
        fee = fields["tuition_fee"]
        cur = detect_currency(f"{fee['value']} {fee['text_snippet']}")
        if cur:
            fields["currency"] = _evidence(cur, page, fee["css_selector"],
                                           fee["text_snippet"], fee["confidence"],
                                           "currency_from_fee")

    # labelled sections
    req = _section_text(soup, _REQUIREMENT_KEYWORDS)
    if req:
        fields["admission_requirements"] = _evidence(req, page, "section", req, 0.55,
                                                     "requirements_section")
    career = _section_text(soup, _CAREER_KEYWORDS)
    if career:
        fields["career_outcomes"] = _evidence(career, page, "section", career, 0.55,
                                              "career_section")

    return fields
