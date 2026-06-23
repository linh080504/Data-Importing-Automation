"""CSV export of reviewed staging data.

Two deliverables a reviewer can download straight from the UI:
- universities CSV — same column shape as the project's sample import CSV
  (`sample_data/University_Import_Clean-7.csv`), but correctly aligned.
- majors CSV — one row per program/major with its detail fields + provenance.

Pure functions return ``(header, rows)`` so they are unit-testable without HTTP.
"""

from .lang import is_english

# University columns, in the sample CSV's order (the leading unnamed index column
# and `id` are prepended in `university_rows`).
UNIVERSITY_EXPORT_FIELDS = [
    "name", "location", "description", "slug", "sponsored", "website",
    "global_rank", "financials", "student_loan_available", "campus_student_life",
    "number_of_students", "student_to_faculty_ratio", "international_student_ratio",
    "housing_availability", "admissions_contact", "admissions_phone",
    "contact_person", "admissions_page_link", "immigration_support",
    "university_campuses",
]
_UNIVERSITY_BOOL_FIELDS = {
    "sponsored", "student_loan_available", "housing_availability", "immigration_support",
}

MAJOR_EXPORT_FIELDS = [
    "university_name", "university_slug", "country", "country_code",
    "program_name", "degree_level", "field_of_study", "faculty_or_school",
    "description", "duration", "study_mode", "language", "tuition_fee", "currency",
    "intake", "application_deadline", "admission_requirements", "career_outcomes",
    "accreditation", "is_higher_education_program", "program_url", "source_url",
    "confidence_score",
]


# Minimal majors deliverable: one row per (university, major) with its link.
SIMPLE_MAJOR_EXPORT_HEADER = ["University Name", "Major Name", "Source URL"]


def simple_major_rows(queryset, english_only: bool = True):
    """(header, rows) for the minimal majors CSV — exactly three columns:
    University Name | Major Name | Source URL. One row per program (1-to-many to
    its university). With english_only, non-English major names are skipped so the
    deliverable is English. Source URL is the major's own page when known, else the
    page it was found on."""
    header = list(SIMPLE_MAJOR_EXPORT_HEADER)
    rows = []
    for program in queryset:
        if english_only and not is_english(program.program_name):
            continue
        source = program.program_url or program.source_url or ""
        rows.append([program.extracted_university.name, program.program_name, source])
    return header, rows


def _csv_value(field: str, value) -> str:
    if field == "sponsored":
        return "0"
    if value is None:
        return ""
    if isinstance(value, bool) or field in _UNIVERSITY_BOOL_FIELDS:
        if value in (True, False):
            return "1" if value else "0"
        return ""
    return str(value)


def university_rows(queryset, english_only: bool = True):
    """(header, rows) for the universities CSV, matching the sample CSV columns.
    With english_only, rows whose name/description aren't English are skipped so
    the deliverable is a single-language (English) catalog."""
    header = ["", "id"] + UNIVERSITY_EXPORT_FIELDS
    rows = []
    i = 0
    for uni in queryset:
        if english_only and not (is_english(uni.name) and is_english(uni.description)):
            continue
        i += 1
        row = [i, uni.external_id or uni.pk]
        row += [_csv_value(f, getattr(uni, f, "")) for f in UNIVERSITY_EXPORT_FIELDS]
        rows.append(row)
    return header, rows


def major_rows(queryset, english_only: bool = True):
    """(header, rows) for the majors CSV — one row per program with provenance.
    With english_only, non-English program names are skipped."""
    header = [""] + MAJOR_EXPORT_FIELDS
    rows = []
    i = 0
    for program in queryset:
        if english_only and not is_english(program.program_name):
            continue
        i += 1
        row = [i]
        for field in MAJOR_EXPORT_FIELDS:
            if field == "university_name":
                value = program.extracted_university.name
            elif field == "university_slug":
                value = program.extracted_university.slug or program.university_slug
            else:
                value = getattr(program, field, "")
            row.append(_csv_value(field, value))
        rows.append(row)
    return header, rows
